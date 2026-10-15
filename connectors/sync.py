"""Sync engine (PLAN.md "Ingestion pipeline" steps 1-3, 6, 7).

One sync per scope at a time through a durable lease with a fencing token.
Pages of changes are written to the inbox together with the cursor in one
fenced transaction; nothing reaches the pipeline before the row is durable.
`process_inbox` applies rows in order; `reconcile` stamps rows and grants with
a generation and sweeps only after the barrier holds.
"""

from __future__ import annotations

import logging
import secrets
import socket
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from infra.api import metrics, with_org
from knowledge.api import (
    DRIFT,
    OBSOLETE,
    STALE,
    UNSUPPORTED,
    ChangeEvent,
    apply_change,
    revoke_link_drive_grants,
    revoke_scope_grants,
    sweep_not_seen,
)

from .api import set_link_status
from .http import AuthError, ProviderError, ResyncRequired, ScopeLost
from .models import ChangeInbox, ConnectorLink, SyncLease, SyncRun, SyncScope
from .providers.base import Page, ProviderClient

log = logging.getLogger(__name__)

BUSY = "busy"
LEASE_LOST = "lease_lost"
MAX_INBOX_ATTEMPTS = 2


class LeaseLost(Exception):
    pass


# --- lease -----------------------------------------------------------------


def acquire_lease(scope: SyncScope) -> str | None:
    token = secrets.token_hex(16)
    now = timezone.now()
    with with_org(scope.organization_id):
        updated = SyncLease.objects.filter(scope=scope, expires_at__lt=now).update(
            lease_token=token,
            holder=socket.gethostname()[:128],
            expires_at=now + timedelta(seconds=settings.LEASE_TTL_S),
        )
    return token if updated else None


def release_lease(scope: SyncScope, token: str) -> None:
    with with_org(scope.organization_id):
        SyncLease.objects.filter(scope=scope, lease_token=token).update(expires_at=timezone.now())


def _fenced_renew(scope: SyncScope, token: str) -> None:
    """Inside a transaction: renew the lease or raise LeaseLost."""
    now = timezone.now()
    updated = SyncLease.objects.filter(scope=scope, lease_token=token, expires_at__gt=now).update(
        expires_at=now + timedelta(seconds=settings.LEASE_TTL_S)
    )
    if not updated:
        metrics.lease_lost_total.inc()
        raise LeaseLost(str(scope.id))


# --- checkpointing -----------------------------------------------------------


def _item_payload(item) -> dict:
    sd = item.document
    if sd is None:
        return {"drive_id": item.drive_id}
    return {
        "source_type": sd.source_type,
        "source_id": sd.source_id,
        "version_label": sd.version_label,
        "title": sd.title,
        "mime_type": sd.mime_type,
        "source_url": sd.source_url,
        "path": sd.path,
        "drive_id": sd.drive_id,
        "site_id": sd.site_id,
        "author": sd.author,
        "created_at": sd.created_at.isoformat() if sd.created_at else None,
        "modified_at": sd.modified_at.isoformat() if sd.modified_at else None,
        "size": sd.size,
        "extra": sd.extra,
    }


def checkpoint(
    scope: SyncScope,
    token: str,
    page: Page,
    run: SyncRun,
    generation: int | None,
    cursor: str | None,
) -> int:
    """Write a page's inbox rows and the cursor in one fenced transaction.
    Repeated items within a page collapse to the last occurrence."""
    with with_org(scope.organization_id):
        with transaction.atomic():
            _fenced_renew(scope, token)
            scope_row = SyncScope.objects.select_for_update().get(id=scope.id)
            last_seen: dict[str, object] = {}
            for item in page.items:
                last_seen[item.source_id or f"drive:{item.drive_id}"] = item
            rows = []
            seq = scope_row.last_seq
            for item in last_seen.values():
                seq += 1
                rows.append(
                    ChangeInbox(
                        organization_id=scope.organization_id,
                        link_id=scope.link_id,
                        scope=scope_row,
                        seq=seq,
                        source_id=item.source_id or f"drive:{item.drive_id}",
                        kind=item.kind,
                        payload=_item_payload(item),
                        observed_at=page.observed_at,
                        reconcile_generation=generation,
                    )
                )
            ChangeInbox.objects.bulk_create(rows, ignore_conflicts=True)
            scope_row.last_seq = seq
            if cursor is not None:
                scope_row.cursor_value = cursor
            scope_row.save(update_fields=["last_seq", "cursor_value"])
            SyncRun.objects.filter(id=run.id).update(
                pages_done=F("pages_done") + 1, changes_seen=F("changes_seen") + len(rows)
            )
            metrics.sync_checkpoint_seq.labels(scope=str(scope.id)).set(seq)
            return len(rows)


# --- sync -------------------------------------------------------------------


def _due_for_reconcile(scope: SyncScope) -> bool:
    if not scope.bootstrapped:
        return False
    if scope.last_reconcile_at is None:
        return True
    return timezone.now() - scope.last_reconcile_at >= timedelta(
        seconds=settings.FULL_RECONCILE_INTERVAL_S
    )


def sync_scope(scope: SyncScope, client: ProviderClient, *, force_reconcile: bool = False) -> str:
    """Run one sync for the scope and process its inbox. Returns the run kind,
    BUSY when another sync holds the lease, or LEASE_LOST."""
    token = acquire_lease(scope)
    if token is None:
        return BUSY
    link = _link_of(scope)
    try:
        if not scope.bootstrapped:
            kind = SyncRun.KIND_BOOTSTRAP
        elif force_reconcile or _due_for_reconcile(scope):
            kind = SyncRun.KIND_RECONCILE
        else:
            kind = SyncRun.KIND_INCREMENTAL
        generation = None
        if kind in (SyncRun.KIND_BOOTSTRAP, SyncRun.KIND_RECONCILE):
            generation = _allocate_generation(scope, token)
        with with_org(scope.organization_id):
            run = SyncRun.objects.create(
                organization_id=scope.organization_id,
                link=link,
                scope=scope,
                kind=kind,
                reconcile_generation=generation,
            )
        try:
            _listing(scope, client, token, run, kind, generation)
        except ResyncRequired:
            # Cursor invalid: switch this run into a full reconcile from scratch.
            kind = SyncRun.KIND_RECONCILE
            generation = _allocate_generation(scope, token)
            with with_org(scope.organization_id):
                SyncRun.objects.filter(id=run.id).update(kind=kind, reconcile_generation=generation)
            _listing(scope, client, token, run, kind, generation)
        _finish_run(scope, run, SyncRun.STATUS_COMPLETED, "")
    except LeaseLost:
        log.warning("lease lost during sync", extra={"scope_id": str(scope.id)})
        return LEASE_LOST
    except ScopeLost:
        _finish_run(scope, run, SyncRun.STATUS_FAILED, "scope_lost")
        revoke_scope_grants(scope, "scope_lost")
        release_lease(scope, token)
        return kind
    except AuthError as exc:
        _finish_run(scope, run, SyncRun.STATUS_FAILED, exc.code)
        set_link_status(link, ConnectorLink.STATUS_ERROR, exc.code)
        release_lease(scope, token)
        return kind
    except ProviderError as exc:
        _finish_run(scope, run, SyncRun.STATUS_FAILED, exc.code)
        release_lease(scope, token)
        return kind

    # Apply the durable rows, then the barrier-guarded sweep, still under the lease.
    try:
        process_inbox(scope, client, token=token)
        if kind in (SyncRun.KIND_BOOTSTRAP, SyncRun.KIND_RECONCILE) and generation is not None:
            finish_reconcile(scope, generation, token=token)
    except LeaseLost:
        log.warning("lease lost during inbox processing", extra={"scope_id": str(scope.id)})
        return LEASE_LOST
    release_lease(scope, token)
    return kind


def _allocate_generation(scope: SyncScope, token: str) -> int:
    """A unique generation per started reconcile, independent of the last
    completed sweep, so a blocked attempt never shares numbers with the next."""
    with with_org(scope.organization_id):
        with transaction.atomic():
            _fenced_renew(scope, token)
            SyncScope.objects.filter(id=scope.id).update(
                reconcile_counter=F("reconcile_counter") + 1
            )
            value = (
                SyncScope.objects.filter(id=scope.id)
                .values_list("reconcile_counter", flat=True)
                .get()
            )
    scope.reconcile_counter = value
    return value


def _listing(scope, client, token, run, kind, generation) -> None:
    if kind == SyncRun.KIND_INCREMENTAL:
        pages = client.list_changes(scope, scope.cursor_value)
        start_cursor = None
    else:
        start_cursor = client.bootstrap_cursor(scope)
        pages = client.list_all(scope)
    for page in pages:
        cursor = None
        if page.done_cursor is not None:
            # Google full listing: the token captured before listing. Graph and
            # Google incremental: the cursor the provider returned at the end.
            cursor = start_cursor if start_cursor is not None else page.done_cursor
        elif kind == SyncRun.KIND_INCREMENTAL and page.next_cursor:
            cursor = page.next_cursor  # resumable mid-listing
        checkpoint(scope, token, page, run, generation, cursor)
    with with_org(scope.organization_id):
        if kind != SyncRun.KIND_INCREMENTAL:
            SyncScope.objects.filter(id=scope.id).update(bootstrapped=True)
        scope.refresh_from_db()


def _finish_run(scope, run, status, error_code) -> None:
    with with_org(scope.organization_id):
        SyncRun.objects.filter(id=run.id).update(
            status=status, finished_at=timezone.now(), error_code=error_code[:64]
        )
        if status == SyncRun.STATUS_COMPLETED:
            SyncScope.objects.filter(id=scope.id).update(last_ok_at=timezone.now())


# --- inbox processing -----------------------------------------------------------


def _event_from_row(row: ChangeInbox) -> ChangeEvent:
    from datetime import datetime

    from knowledge.api import SourceDocument

    p = row.payload
    sd = None
    if row.kind == ChangeInbox.KIND_UPSERT:
        sd = SourceDocument(
            source_type=p["source_type"],
            source_id=p["source_id"],
            version_label=p["version_label"],
            title=p.get("title", ""),
            mime_type=p.get("mime_type", ""),
            source_url=p.get("source_url", ""),
            path=p.get("path", ""),
            drive_id=p.get("drive_id", ""),
            site_id=p.get("site_id", ""),
            author=p.get("author", ""),
            created_at=datetime.fromisoformat(p["created_at"]) if p.get("created_at") else None,
            modified_at=datetime.fromisoformat(p["modified_at"]) if p.get("modified_at") else None,
            size=p.get("size"),
            extra=p.get("extra") or {},
        )
    return ChangeEvent(
        kind=row.kind,
        source_id=row.source_id,
        seq=row.seq,
        observed_at=row.observed_at,
        reconcile_generation=row.reconcile_generation,
        document=sd,
    )


def _link_of(scope: SyncScope) -> ConnectorLink:
    with with_org(scope.organization_id):
        return ConnectorLink.objects.get(id=scope.link_id)


def process_inbox(
    scope: SyncScope, client: ProviderClient, token: str | None = None
) -> dict[str, int]:
    counts: dict[str, int] = {}
    link = _link_of(scope)
    while True:
        with with_org(scope.organization_id):
            if token is not None:
                with transaction.atomic():
                    _fenced_renew(scope, token)
            row = (
                ChangeInbox.objects.filter(scope=scope, status=ChangeInbox.STATUS_PENDING)
                .order_by("seq")
                .first()
            )
        if row is None:
            break
        try:
            if row.kind == "drive_removed":
                revoke_link_drive_grants(link, row.payload.get("drive_id", ""))
                outcome = "revoked"
            else:
                outcome = apply_change(link, scope, _event_from_row(row), client.fetch)
        except AuthError as exc:
            set_link_status(link, ConnectorLink.STATUS_ERROR, exc.code)
            break
        except ProviderError as exc:
            outcome = f"error:{exc.code}"
        except Exception as exc:
            log.exception("inbox row failed", extra={"inbox_id": str(row.id)})
            outcome = f"error:{type(exc).__name__}"
        counts[outcome] = counts.get(outcome, 0) + 1
        with with_org(scope.organization_id):
            if outcome == STALE and row.attempts + 1 < MAX_INBOX_ATTEMPTS:
                ChangeInbox.objects.filter(id=row.id).update(attempts=F("attempts") + 1)
                continue  # requeued once; the retry takes the fast path
            if outcome == OBSOLETE:
                status, code = ChangeInbox.STATUS_OBSOLETE, ""
            elif outcome == UNSUPPORTED:
                # Terminal and safely quarantined: a complete access observation,
                # so it satisfies the reconcile barrier.
                status, code = ChangeInbox.STATUS_DONE, UNSUPPORTED
            elif outcome in (DRIFT, STALE) or outcome.startswith("error:"):
                status, code = ChangeInbox.STATUS_FAILED, outcome[:64]
            else:
                status, code = ChangeInbox.STATUS_DONE, ""
                # A newer event for the same item supersedes older failed rows,
                # so they no longer block the reconcile barrier.
                ChangeInbox.objects.filter(
                    scope=scope,
                    source_id=row.source_id,
                    seq__lt=row.seq,
                    status=ChangeInbox.STATUS_FAILED,
                ).update(status=ChangeInbox.STATUS_OBSOLETE)
            ChangeInbox.objects.filter(id=row.id).update(
                status=status, error_code=code, attempts=F("attempts") + 1
            )
    with with_org(scope.organization_id):
        metrics.inbox_pending.set(
            ChangeInbox.objects.filter(status=ChangeInbox.STATUS_PENDING).count()
        )
    return counts


def reconcile_barrier_holds(scope: SyncScope, generation: int) -> bool:
    with with_org(scope.organization_id):
        blocked = ChangeInbox.objects.filter(
            scope=scope,
            reconcile_generation=generation,
            status__in=[ChangeInbox.STATUS_PENDING, ChangeInbox.STATUS_FAILED],
        ).exists()
        completed = SyncRun.objects.filter(
            scope=scope, reconcile_generation=generation, status=SyncRun.STATUS_COMPLETED
        ).exists()
    return completed and not blocked


def finish_reconcile(scope: SyncScope, generation: int, token: str | None = None) -> int:
    """Sweep grants the completed generation did not touch, when the barrier holds."""
    if not reconcile_barrier_holds(scope, generation):
        return -1
    if token is not None:
        with with_org(scope.organization_id), transaction.atomic():
            _fenced_renew(scope, token)
    swept = sweep_not_seen(scope, generation)
    with with_org(scope.organization_id):
        SyncScope.objects.filter(id=scope.id).update(
            current_reconcile_generation=generation, last_reconcile_at=timezone.now()
        )
        scope.refresh_from_db()
    return swept
