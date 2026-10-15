"""KnowledgeAgentService (PLAN.md section 8 adapter) and the fenced lifecycle.

start_investigation -> queued row + Celery task. run_investigation claims the
row (queued -> dispatched), mints the capability token in the worker, creates
the runner run, commits running, starts it, streams events, parses the result,
validates citations against InvestigationEvidence, and transitions with
conditions on status and attempt. Every terminal transition revokes the token.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from infra.api import investigation_id_var, metrics, record_access, with_org
from knowledge.api import versions_visible
from organizations.api import Principal

from .models import CapabilityToken, Investigation, InvestigationEvidence
from .results import parse_result, validate_citations
from .runner_client import RunnerClient, RunnerError

log = logging.getLogger(__name__)

INSTRUCTIONS_PATH = Path(__file__).with_name("prompts") / "investigator.md"


def investigator_instructions() -> str:
    return INSTRUCTIONS_PATH.read_text(encoding="utf-8")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --- public service -----------------------------------------------------------


def start_investigation(principal: Principal, question: str) -> Investigation:
    """Create the queued row and enqueue the worker task."""
    if not settings.HERMES_ENABLED:
        raise PermissionError("Deep Investigation is disabled (HERMES_ENABLED=False)")
    limits = dict(settings.INVESTIGATION_LIMITS)
    with with_org(principal.organization_id, principal.user_id):
        row = Investigation.objects.create(
            organization_id=principal.organization_id,
            user=principal.user,
            question=question.strip(),
            deadline_at=timezone.now() + timedelta(seconds=limits["timeout_s"]),
            limits=limits,
        )
        row.run_key = f"{row.id}:1"
        row.save(update_fields=["run_key"])
        record_access(
            principal.organization_id,
            principal.user,
            "investigation",
            object_type="investigation",
            object_id=row.id,
            meta={"action": "start"},
            investigation_id=row.id,
        )
    from .tasks import run_investigation

    transaction.on_commit(
        lambda: run_investigation.delay(str(principal.organization_id), str(row.id))
    )
    if not transaction.get_connection().in_atomic_block:
        run_investigation.delay(str(principal.organization_id), str(row.id))
    return row


def get_investigation(principal: Principal, investigation_id) -> dict | None:
    """Owner view with the D6 recheck; admins get metadata only."""
    with with_org(principal.organization_id, principal.user_id):
        row = Investigation.objects.filter(
            id=investigation_id, organization_id=principal.organization_id
        ).first()
        if row is None:
            return None
        if row.user_id != principal.user_id:
            if not principal.has_role("admin"):
                return None
            return {
                "id": str(row.id),
                "status": row.status,
                "created_at": row.created_at,
                "finished_at": row.finished_at,
                "metadata_only": True,
            }
        version_ids = list(
            InvestigationEvidence.objects.filter(investigation=row).values_list(
                "version_id", flat=True
            )
        )
        visible = row.content_state == Investigation.CONTENT_PRESENT and versions_visible(
            principal, version_ids
        )
        activity = [
            {
                k: v
                for k, v in e.items()
                if k in ("type", "name", "duration_ms", "is_error", "subtype", "seq")
            }
            for e in (row.activity or [])
        ]
        return {
            "id": str(row.id),
            "question": row.question,
            "status": row.status,
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "deadline_at": row.deadline_at,
            "attempt": row.attempt,
            "activity": activity,
            "usage": row.usage,
            "limits": row.limits,
            "tool_calls_used": row.tool_calls_used,
            "output_chars_used": row.output_chars_used,
            "error_code": row.error_code,
            "status_detail": row.status_detail,
            "withheld": not visible and row.status == Investigation.STATUS_COMPLETED,
            "result": row.result if visible else None,
            "content_state": row.content_state,
        }


def cancel_investigation(
    principal: Principal, investigation_id, *, client: RunnerClient | None = None
) -> bool:
    with with_org(principal.organization_id, principal.user_id):
        row = Investigation.objects.filter(
            id=investigation_id, organization_id=principal.organization_id
        ).first()
        if row is None or (row.user_id != principal.user_id and not principal.has_role("admin")):
            return False
        updated = Investigation.objects.filter(
            id=row.id,
            status__in=[
                Investigation.STATUS_QUEUED,
                Investigation.STATUS_DISPATCHED,
                Investigation.STATUS_RUNNING,
            ],
        ).update(
            status=Investigation.STATUS_CANCELLED,
            finished_at=timezone.now(),
            status_detail="cancelled by user",
        )
        if updated:
            _revoke_tokens(row.id)
            record_access(
                principal.organization_id,
                principal.user,
                "investigation",
                object_type="investigation",
                object_id=row.id,
                meta={"action": "cancel"},
                investigation_id=row.id,
            )
    if updated and row.run_key:
        try:
            (client or RunnerClient()).cancel(row.run_key)
        except RunnerError as exc:
            log.warning(
                "runner cancel failed", extra={"investigation_id": str(row.id), "code": exc.code}
            )
    if updated:
        metrics.investigation_terminal_total.labels(status="cancelled").inc()
    return bool(updated)


# --- tokens -------------------------------------------------------------------


def mint_token(row: Investigation) -> str:
    raw = secrets.token_urlsafe(32)
    CapabilityToken.objects.create(
        token_hash=_hash(raw),
        investigation=row,
        organization_id=row.organization_id,
        user_id=row.user_id,
        attempt=row.attempt,
        expires_at=row.deadline_at + timedelta(seconds=60),
    )
    return raw


def _revoke_tokens(investigation_id) -> int:
    return CapabilityToken.objects.filter(
        investigation_id=investigation_id, revoked_at__isnull=True
    ).update(revoked_at=timezone.now())


# --- worker lifecycle -------------------------------------------------------------


def _transition(row_id, *, from_statuses, attempt=None, **values) -> bool:
    qs = Investigation.objects.filter(id=row_id, status__in=list(from_statuses))
    if attempt is not None:
        qs = qs.filter(attempt=attempt)
    return qs.update(**values) == 1


def _finish(
    org_id,
    row_id,
    status: str,
    *,
    attempt: int,
    error_code: str = "",
    detail: str = "",
    from_statuses=(Investigation.STATUS_RUNNING, Investigation.STATUS_DISPATCHED),
) -> bool:
    with with_org(org_id):
        ok = _transition(
            row_id,
            from_statuses=from_statuses,
            attempt=attempt,
            status=status,
            finished_at=timezone.now(),
            error_code=error_code[:64],
            status_detail=detail[:255],
        )
        if ok:
            _revoke_tokens(row_id)
    if ok:
        metrics.investigation_terminal_total.labels(status=status).inc()
    return ok


def execute(org_id, investigation_id, client: RunnerClient | None = None) -> str:
    """Worker body. Returns the final status word."""
    client = client or RunnerClient()
    token_ctx = investigation_id_var.set(str(investigation_id))
    try:
        return _execute(org_id, investigation_id, client)
    finally:
        investigation_id_var.reset(token_ctx)


def _execute(org_id, investigation_id, client: RunnerClient) -> str:
    now = timezone.now()
    with with_org(org_id):
        claimed = _transition(
            investigation_id,
            from_statuses=[Investigation.STATUS_QUEUED],
            status=Investigation.STATUS_DISPATCHED,
            dispatched_at=now,
            heartbeat_at=now,
        )
        if not claimed:
            return "not_claimed"
        row = Investigation.objects.get(id=investigation_id)
        raw_token = mint_token(row)
    metrics.investigation_attempts_total.inc()
    limits = row.limits or settings.INVESTIGATION_LIMITS
    started = time.monotonic()
    try:
        client.create(
            run_key=row.run_key,
            question=row.question,
            instructions=investigator_instructions(),
            max_turns=limits["max_turns"],
            max_tool_calls=limits["max_tool_calls"],
            timeout_s=max(10, int((row.deadline_at - timezone.now()).total_seconds())),
            mcp_token=raw_token,
        )
    except RunnerError as exc:
        _finish(
            org_id,
            row.id,
            Investigation.STATUS_FAILED,
            attempt=row.attempt,
            error_code=exc.code,
            detail="runner refused the run",
            from_statuses=[Investigation.STATUS_DISPATCHED],
        )
        return Investigation.STATUS_FAILED
    with with_org(org_id):
        running = _transition(
            row.id,
            from_statuses=[Investigation.STATUS_DISPATCHED],
            attempt=row.attempt,
            status=Investigation.STATUS_RUNNING,
            started_at=timezone.now(),
            heartbeat_at=timezone.now(),
        )
    if not running:  # cancelled between claim and start
        try:
            client.cancel(row.run_key)
        except RunnerError:
            pass
        return "cancelled_before_start"
    try:
        client.start(row.run_key)
    except RunnerError as exc:
        _finish(
            org_id,
            row.id,
            Investigation.STATUS_FAILED,
            attempt=row.attempt,
            error_code=exc.code,
            detail="runner start failed",
        )
        return Investigation.STATUS_FAILED

    outcome = _stream(org_id, row, client)
    duration = time.monotonic() - started
    metrics.investigation_duration_seconds.observe(duration)
    return outcome


def _stream(org_id, row: Investigation, client: RunnerClient) -> str:
    after = row.last_event_seq
    terminal_event = None
    while terminal_event is None:
        if timezone.now() > row.deadline_at:
            try:
                client.cancel(row.run_key)
            except RunnerError:
                pass
            _finish(
                org_id,
                row.id,
                Investigation.STATUS_TIMED_OUT,
                attempt=row.attempt,
                error_code="deadline",
                detail="deadline reached",
            )
            return Investigation.STATUS_TIMED_OUT
        try:
            events = client.events(
                row.run_key, after, wait_s=min(20.0, settings.HEARTBEAT_INTERVAL_S)
            )
        except RunnerError as exc:
            _finish(
                org_id,
                row.id,
                Investigation.STATUS_FAILED,
                attempt=row.attempt,
                error_code=exc.code,
                detail="lost the runner while streaming",
            )
            return Investigation.STATUS_FAILED
        activity_add = []
        for event in events:
            after = max(after, int(event.get("seq", 0)))
            kind = event.get("type")
            if kind in ("tool_use", "tool_result", "runner", "system"):
                activity_add.append(
                    {
                        k: event.get(k)
                        for k in ("seq", "type", "subtype", "name", "duration_ms", "is_error")
                    }
                )
            if kind == "terminal":
                terminal_event = event
        with with_org(org_id):
            current = (
                Investigation.objects.filter(id=row.id).values_list("status", flat=True).first()
            )
            if current != Investigation.STATUS_RUNNING:
                return current or "unknown"  # cancelled or reaped elsewhere
            upd = {"heartbeat_at": timezone.now(), "last_event_seq": after}
            if activity_add:
                fresh = Investigation.objects.get(id=row.id)
                upd["activity"] = (fresh.activity or [])[-200:] + activity_add
            Investigation.objects.filter(
                id=row.id, status=Investigation.STATUS_RUNNING, attempt=row.attempt
            ).update(**upd)
    return _complete(org_id, row, client, terminal_event)


def _complete(org_id, row: Investigation, client: RunnerClient, terminal_event: dict) -> str:
    try:
        state = client.get(row.run_key)
    except RunnerError as exc:
        _finish(
            org_id,
            row.id,
            Investigation.STATUS_FAILED,
            attempt=row.attempt,
            error_code=exc.code,
            detail="could not read the terminal record",
        )
        return Investigation.STATUS_FAILED
    terminal = state.terminal or {}
    outcome = terminal.get("outcome") or terminal_event.get("outcome") or "failed"
    usage = terminal.get("usage") or {}
    if outcome == "completed":
        text = terminal.get("final_text") or ""
        with with_org(org_id):
            returned = set(_returned_evidence_ids(row.id))
            parsed = validate_citations(parse_result(text), returned)
            result = {
                "answer": parsed.answer,
                "evidence_summary": parsed.evidence_summary,
                "conflicts": parsed.conflicts,
                "open_questions": parsed.open_questions,
                "statements": parsed.statements,
                "unsupported_statements": parsed.unsupported_statements,
                "cited_evidence_ids": parsed.cited_evidence_ids,
                "malformed": parsed.malformed,
                "citations": _citations_for(row.id, parsed.cited_evidence_ids),
            }
            done = _transition(
                row.id,
                from_statuses=[Investigation.STATUS_RUNNING],
                attempt=row.attempt,
                status=Investigation.STATUS_COMPLETED,
                finished_at=timezone.now(),
                result=result,
                usage=usage,
                content_state=Investigation.CONTENT_PRESENT,
            )
            if not done:
                # Purged during generation, or no longer running: keep purged, write no text.
                done_purged = Investigation.objects.filter(
                    id=row.id,
                    status=Investigation.STATUS_RUNNING,
                    attempt=row.attempt,
                    content_state=Investigation.CONTENT_PURGED,
                ).update(
                    status=Investigation.STATUS_COMPLETED, finished_at=timezone.now(), usage=usage
                )
                done = bool(done_purged)
            if done:
                _revoke_tokens(row.id)
                fresh = Investigation.objects.get(id=row.id)
                metrics.tool_calls_used.observe(fresh.tool_calls_used)
                metrics.output_chars_used.observe(fresh.output_chars_used)
        if done:
            metrics.investigation_terminal_total.labels(status="completed").inc()
            _ack(client, row.run_key)
            return Investigation.STATUS_COMPLETED
        return "superseded"
    if outcome == "cancelled":
        _finish(
            org_id,
            row.id,
            Investigation.STATUS_CANCELLED,
            attempt=row.attempt,
            detail="runner reported cancel",
        )
        _ack(client, row.run_key)
        return Investigation.STATUS_CANCELLED
    if outcome == "timed_out":
        _finish(
            org_id,
            row.id,
            Investigation.STATUS_TIMED_OUT,
            attempt=row.attempt,
            error_code="runner_timeout",
        )
        _ack(client, row.run_key)
        return Investigation.STATUS_TIMED_OUT
    # failed: provider or agent error. One retry with a rotated token and the same budgets.
    error = str(terminal.get("error") or "")[:200]
    max_retries = int(
        (row.limits or {}).get("max_retries", settings.INVESTIGATION_LIMITS["max_retries"])
    )
    if row.attempt <= max_retries and timezone.now() < row.deadline_at:
        with with_org(org_id):
            _revoke_tokens(row.id)
            moved = Investigation.objects.filter(
                id=row.id, status=Investigation.STATUS_RUNNING, attempt=row.attempt
            ).update(
                status=Investigation.STATUS_QUEUED,
                attempt=row.attempt + 1,
                run_key=f"{row.id}:{row.attempt + 1}",
                last_event_seq=0,
                status_detail=f"retry after: {error}"[:255],
            )
        _ack(client, row.run_key)
        if moved:
            from .tasks import run_investigation

            run_investigation.delay(str(org_id), str(row.id))
            return "retrying"
    _finish(
        org_id,
        row.id,
        Investigation.STATUS_FAILED,
        attempt=row.attempt,
        error_code="provider_failure",
        detail=error,
    )
    _ack(client, row.run_key)
    return Investigation.STATUS_FAILED


def _ack(client: RunnerClient, run_key: str) -> None:
    try:
        client.delete(run_key)
    except RunnerError as exc:
        log.warning("runner ack failed", extra={"run_key": run_key, "code": exc.code})


def _returned_evidence_ids(investigation_id) -> list[str]:
    rows = InvestigationEvidence.objects.filter(investigation_id=investigation_id).select_related(
        "version"
    )
    return [
        f"chunk:{e.chunk_id}@{e.version.version_label}[{e.span_start}:{e.span_end}]" for e in rows
    ]


def _citations_for(investigation_id, evidence_ids: list[str]) -> list[dict]:
    wanted = set(evidence_ids)
    out = []
    rows = InvestigationEvidence.objects.filter(investigation_id=investigation_id).select_related(
        "chunk", "chunk__document", "version"
    )
    for e in rows:
        eid = f"chunk:{e.chunk_id}@{e.version.version_label}[{e.span_start}:{e.span_end}]"
        if eid in wanted:
            out.append(
                {
                    "evidence_id": eid,
                    "chunk_id": str(e.chunk_id),
                    "version_id": str(e.version_id),
                    "document_id": str(e.chunk.document_id),
                    "title": e.chunk.document.title,
                    "source_url": e.chunk.document.source_url,
                    "source_type": e.chunk.document.source_type,
                    "version_label": e.version.version_label,
                    "locator": e.chunk.locator,
                    "excerpt": e.chunk.text[e.span_start : e.span_end][:500]
                    if e.span_end
                    else e.chunk.text[:500],
                }
            )
    return out


# --- reaper, purge, offboarding --------------------------------------------------


def reap(org_id, client: RunnerClient | None = None) -> dict:
    """Dispatch recovery and stale-run handling (PLAN.md lifecycle)."""
    client = client or RunnerClient()
    now = timezone.now()
    stale_dispatch = now - timedelta(seconds=settings.DISPATCH_TIMEOUT_S)
    stale_heartbeat = now - timedelta(seconds=2 * settings.HEARTBEAT_INTERVAL_S + 30)
    counts = {"requeued": 0, "recovered": 0, "interrupted": 0}
    from .tasks import run_investigation

    with with_org(org_id):
        queued_stale = list(
            Investigation.objects.filter(
                status=Investigation.STATUS_QUEUED, created_at__lt=stale_dispatch
            ).values_list("id", flat=True)
        )
        stuck = list(
            Investigation.objects.filter(
                status__in=[Investigation.STATUS_DISPATCHED, Investigation.STATUS_RUNNING],
                heartbeat_at__lt=stale_heartbeat,
            )
        )
    for rid in queued_stale:
        run_investigation.delay(str(org_id), str(rid))
        counts["requeued"] += 1
    for row in stuck:
        if now >= row.deadline_at:
            _finish(
                org_id,
                row.id,
                Investigation.STATUS_INTERRUPTED,
                attempt=row.attempt,
                error_code="stale",
                detail="no heartbeat past the deadline",
            )
            counts["interrupted"] += 1
            continue
        # Before restarting, consume a terminal record the runner may already hold.
        try:
            state = client.get(row.run_key)
        except RunnerError:
            state = None
        if state is not None and state.terminal and state.terminal.get("outcome") == "completed":
            _complete(org_id, row, client, {"outcome": "completed"})
            counts["recovered"] += 1
            continue
        try:
            client.cancel(row.run_key)
        except RunnerError:
            pass
        with with_org(org_id):
            _revoke_tokens(row.id)
            Investigation.objects.filter(id=row.id, attempt=row.attempt).update(
                status=Investigation.STATUS_QUEUED,
                attempt=F("attempt") + 1,
                run_key=f"{row.id}:{row.attempt + 1}",
                last_event_seq=0,
                status_detail="recovered after a worker crash",
            )
        run_investigation.delay(str(org_id), str(row.id))
        counts["requeued"] += 1
    return counts


def purge_investigations_for_version(version) -> int:
    """Purge hook (D6): investigations that saw this version lose their text."""
    ids = list(
        InvestigationEvidence.objects.filter(version=version)
        .values_list("investigation_id", flat=True)
        .distinct()
    )
    if not ids:
        return 0
    rows = list(Investigation.objects.filter(id__in=ids))
    for row in rows:
        row.result = None
        row.activity = [{k: v for k, v in e.items() if k != "name"} for e in (row.activity or [])]
        row.content_state = Investigation.CONTENT_PURGED
        row.save(update_fields=["result", "activity", "content_state"])
    _schedule_runner_erase([r.run_key for r in rows])
    return len(rows)


def _schedule_runner_erase(run_keys: list[str]) -> None:
    from .tasks import erase_runner_records

    transaction.on_commit(lambda: erase_runner_records.delay(run_keys))


def cancel_user_investigations(organization, user) -> int:
    """Offboarding hook: cancel open investigations and revoke their tokens."""
    rows = list(
        Investigation.objects.filter(
            organization=organization,
            user=user,
            status__in=[
                Investigation.STATUS_QUEUED,
                Investigation.STATUS_DISPATCHED,
                Investigation.STATUS_RUNNING,
            ],
        )
    )
    for row in rows:
        Investigation.objects.filter(id=row.id).update(
            status=Investigation.STATUS_CANCELLED,
            finished_at=timezone.now(),
            status_detail="member removed",
        )
        _revoke_tokens(row.id)
    run_keys = [r.run_key for r in rows if r.run_key]
    if run_keys:
        from .tasks import cancel_runner_runs

        transaction.on_commit(lambda: cancel_runner_runs.delay(run_keys))
    return len(rows)
