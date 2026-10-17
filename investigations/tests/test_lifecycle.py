"""Investigation lifecycle with the in-process FakeRunner: completion with
chunk-level citations, invented citations, retry, cancel, timeout, reaper,
D6 withholding, purge during generation, offboarding."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from infra.api import AccessEvent, with_org
from investigations import service
from investigations.api import (
    CapabilityToken,
    FakeRunner,
    Investigation,
    InvestigationEvidence,
    cancel_investigation,
    get_investigation,
    start_investigation,
)
from knowledge.api import apply_change
from knowledge.tests.helpers import ingest_markdown, make_event, principal_for
from organizations.api import Membership, remove_member
from organizations.tests.factories import make_membership, make_org, make_user

pytestmark = pytest.mark.django_db(transaction=True)

DECISION = b"# Hosting decision\nIn March the team selected provider Alpha for hosting. The decision followed a cost review.\n"
ALTERNATIVE = b"# Alternative proposal\nProvider Beta was proposed as an alternative with lower latency but higher cost.\n"
REVISION = (
    b"# Hosting revision\nIn June the hosting contract moved from Alpha to Gamma after an outage.\n"
)
CORPUS = {
    "gdrive:decision": DECISION,
    "gdrive:alternative": ALTERNATIVE,
    "gdrive:revision": REVISION,
}


def setup(monkeypatch, runner: FakeRunner, docs=CORPUS):
    org, user = make_org("acme"), make_user()
    make_membership(org, user)
    link, scope = ingest_markdown(org, user, docs)
    monkeypatch.setattr(service, "RunnerClient", lambda *a, **k: runner)
    return org, user, link, scope


def run_sync(org, inv_id, runner):
    """Execute the worker body directly (Celery is eager in tests but we want the fake runner)."""
    return service.execute(org.id, inv_id, client=runner)


def start(
    org,
    user,
    monkeypatch,
    question="Why did we change hosting provider and what alternatives were considered?",
):
    # Celery is eager: stop the real task from running before we hand the fake runner in.
    monkeypatch.setattr("investigations.tasks.run_investigation.delay", lambda *a, **k: None)
    return start_investigation(principal_for(org, user), question)


def test_end_to_end_three_documents_with_chunk_level_citations(monkeypatch):
    runner = FakeRunner("complete")
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    assert run_sync(org, inv.id, runner) == "completed"
    data = get_investigation(principal_for(org, user), inv.id)
    assert data["status"] == "completed" and not data["withheld"]
    result = data["result"]
    titles = {c["title"] for c in result["citations"]}
    assert titles == {"gdrive:decision", "gdrive:alternative", "gdrive:revision"}
    assert result["statements"] and all(s["evidence_ids"] for s in result["statements"])
    assert result["unsupported_statements"] == []
    assert any("not documented" in q for q in result["open_questions"])
    assert "approved" not in result["answer"].lower()
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert row.tool_calls_used == 6 and row.output_chars_used > 0
        assert (
            CapabilityToken.objects.filter(investigation=row, revoked_at__isnull=True).count() == 0
        )
        assert InvestigationEvidence.objects.filter(investigation=row).count() >= 3
        assert AccessEvent.objects.filter(investigation_id=row.id, kind="tool_call").count() == 6
    assert runner.deleted == [row.run_key]
    assert all(
        p.get("notice", "").startswith("The fields below are document data")
        for p in runner.tool_payloads
        if "error" not in p
    )


def test_invented_citation_becomes_unsupported_statement(monkeypatch):
    runner = FakeRunner("invent", queries=["hosting decision"], read_first=False)
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    run_sync(org, inv.id, runner)
    result = get_investigation(principal_for(org, user), inv.id)["result"]
    assert "The board approved the migration unanimously." in result["unsupported_statements"]
    assert all("00000000" not in e for s in result["statements"] for e in s["evidence_ids"])


def test_provider_failure_retries_once_with_rotated_token_then_fails(monkeypatch):
    runner = FakeRunner("fail")
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    delays = []
    monkeypatch.setattr(
        "investigations.tasks.run_investigation.delay", lambda *a, **k: delays.append(a)
    )
    assert run_sync(org, inv.id, runner) == "retrying"
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert row.status == "queued" and row.attempt == 2 and row.run_key == f"{row.id}:2"
        assert CapabilityToken.objects.filter(
            investigation=row, attempt=1, revoked_at__isnull=False
        ).exists()
        deadline_before = row.deadline_at
    assert delays
    assert run_sync(org, inv.id, runner) == "failed"
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert row.status == "failed" and row.error_code == "provider_failure"
        assert row.deadline_at == deadline_before
        assert (
            CapabilityToken.objects.filter(investigation=row, revoked_at__isnull=True).count() == 0
        )


def test_cancel_while_running_revokes_token_and_blocks_tools(monkeypatch):
    runner = FakeRunner("hang")
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    import threading

    done = {}

    def worker():
        from django.db import connection

        try:
            done["outcome"] = run_sync(org, inv.id, runner)
        finally:
            connection.close()

    t = threading.Thread(target=worker)
    t.start()
    for _ in range(100):
        with with_org(org.id):
            if Investigation.objects.get(id=inv.id).status == "running":
                break
        import time

        time.sleep(0.05)
    assert cancel_investigation(principal_for(org, user), inv.id, client=runner) is True
    t.join(timeout=10)
    assert done.get("outcome") == "cancelled"
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert (
            CapabilityToken.objects.filter(investigation=row, revoked_at__isnull=True).count() == 0
        )
        token_hash = CapabilityToken.objects.get(investigation=row).token_hash
    assert f"cancel:{row.run_key}" in runner.calls
    # A late tool call with the revoked token is refused.
    from mcp_server.api import authorize_and_run, search_knowledge

    raw = runner.runs.get(row.run_key, {}).get("token") or "x" * 40
    payload = authorize_and_run(
        {"authorization": f"Bearer {raw}"},
        "search_knowledge",
        {"query": "hosting"},
        search_knowledge,
    )
    assert payload["error"] == "unauthorized" and token_hash


def test_deadline_times_out(monkeypatch, settings):
    runner = FakeRunner("hang")
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    with with_org(org.id):
        Investigation.objects.filter(id=inv.id).update(
            deadline_at=timezone.now() + timedelta(seconds=1)
        )
    settings.HEARTBEAT_INTERVAL_S = 1
    assert run_sync(org, inv.id, runner) == "timed_out"
    with with_org(org.id):
        assert Investigation.objects.get(id=inv.id).status == "timed_out"


def test_reaper_requeues_stale_dispatch_and_interrupts_past_deadline(monkeypatch, settings):
    runner = FakeRunner("hang")
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    delays = []
    monkeypatch.setattr(
        "investigations.tasks.run_investigation.delay", lambda *a, **k: delays.append(a)
    )
    old = timezone.now() - timedelta(minutes=10)
    with with_org(org.id):
        Investigation.objects.filter(id=inv.id).update(created_at=old)
    counts = service.reap(org.id, client=runner)
    assert counts["requeued"] == 1 and delays
    with with_org(org.id):
        Investigation.objects.filter(id=inv.id).update(
            status="running", heartbeat_at=old, deadline_at=old, run_key=f"{inv.id}:1"
        )
    counts = service.reap(org.id, client=runner)
    assert counts["interrupted"] == 1
    with with_org(org.id):
        assert Investigation.objects.get(id=inv.id).status == "interrupted"

    # Stale heartbeat but deadline ahead: recovered to queued with attempt + 1.
    inv2 = start(org, user, monkeypatch)
    with with_org(org.id):
        Investigation.objects.filter(id=inv2.id).update(
            status="running", heartbeat_at=old, run_key=f"{inv2.id}:1"
        )
    service.reap(org.id, client=runner)
    with with_org(org.id):
        row = Investigation.objects.get(id=inv2.id)
        assert row.status == "queued" and row.attempt == 2


def test_d6_result_withheld_after_revocation_and_purged_text(monkeypatch):
    runner = FakeRunner("complete", queries=["hosting decision"], read_first=False)
    org, user, link, scope = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    run_sync(org, inv.id, runner)
    principal = principal_for(org, user)
    assert get_investigation(principal, inv.id)["withheld"] is False
    apply_change(
        link, scope, make_event(50, None, kind="remove", source_id="gdrive:decision"), None
    )
    data = get_investigation(principal, inv.id)
    assert data["withheld"] is True or data["content_state"] == "purged"
    assert data["result"] is None
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert row.content_state == "purged" and row.result is None
        assert all("name" not in e for e in row.activity)
    other = make_user()
    make_membership(org, other)
    assert get_investigation(principal_for(org, other), inv.id) is None
    admin = make_user()
    make_membership(org, admin, Membership.ROLE_ADMIN)
    assert (
        get_investigation(principal_for(org, admin, role="admin"), inv.id)["metadata_only"] is True
    )


def test_offboarding_cancels_open_investigations(monkeypatch):
    runner = FakeRunner("hang")
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    admin = make_user()
    make_membership(org, admin, Membership.ROLE_ADMIN)
    remove_member(org, user, actor=principal_for(org, admin, role="admin"))
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert row.status == "cancelled"
        assert (
            CapabilityToken.objects.filter(investigation=row, revoked_at__isnull=True).count() == 0
        )


def test_views_list_detail_json_and_cancel(monkeypatch, settings):
    runner = FakeRunner("hang")
    org, user, *_ = setup(monkeypatch, runner)
    monkeypatch.setattr("investigations.tasks.run_investigation.delay", lambda *a, **k: None)
    c = Client()
    c.force_login(user)
    assert c.get(f"/o/{org.slug}/investigations/").status_code == 200
    started = c.post(f"/o/{org.slug}/investigations/start/", {"q": "why did hosting change"})
    assert started.status_code == 302
    detail = c.get(started["Location"])
    assert detail.status_code == 200 and b"Queued" in detail.content
    inv_id = started["Location"].rstrip("/").rsplit("/", 1)[1]
    assert c.get(f"/o/{org.slug}/api/v1/investigations/{inv_id}").json()["status"] == "queued"
    frag = c.get(started["Location"], HTTP_HX_REQUEST="true")
    assert b"hx-get" in frag.content
    cancelled = c.post(f"/o/{org.slug}/investigations/{inv_id}/cancel/")
    assert cancelled.status_code == 302
    assert c.get(f"/o/{org.slug}/api/v1/investigations/{inv_id}").json()["status"] == "cancelled"
    outsider = make_user()
    make_membership(org, outsider)
    c2 = Client()
    c2.force_login(outsider)
    assert c2.get(f"/o/{org.slug}/api/v1/investigations/{inv_id}").status_code == 404
    settings.HERMES_ENABLED = False
    assert c.post(f"/o/{org.slug}/investigations/start/", {"q": "x"}).status_code == 409


def test_agent_can_only_draft_candidates(monkeypatch):
    from decisions.api import DecisionRecord

    runner = FakeRunner("draft", queries=["hosting decision", "alternative"], read_first=False)
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    assert run_sync(org, inv.id, runner) == "completed"
    with with_org(org.id):
        records = list(DecisionRecord.objects.filter(organization=org))
        assert len(records) == 1
        assert (
            records[0].status == "candidate"
            and records[0].origin == "agent"
            and records[0].verified_by is None
        )
