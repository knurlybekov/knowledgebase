"""Regression tests from the Sprint 2-3 post-build inspection."""

import importlib
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from connectors.api import revoke_link
from infra.api import AccessEvent, with_org
from investigations import service
from investigations.api import (
    CapabilityToken,
    FakeRunner,
    Investigation,
    InvestigationEvidence,
    mint_token,
)
from investigations.results import parse_result, validate_citations
from knowledge.api import apply_change
from knowledge.tests.helpers import ingest_markdown, make_event, principal_for
from mcp_server.api import authorize_and_run, get_document, search_knowledge
from mcp_server.tests.test_mcp_auth import make_running
from organizations.tests.factories import make_membership, make_org, make_user

from .test_lifecycle import CORPUS, run_sync, setup, start

pytestmark = pytest.mark.django_db(transaction=True)


def call(raw, tool, args, impl):
    return authorize_and_run({"authorization": f"Bearer {raw}"}, tool, args, impl)


def test_stale_token_cannot_act_under_a_newer_attempt():
    org, user = make_org(), make_user()
    make_membership(org, user)
    ingest_markdown(org, user, CORPUS)
    row, raw_old = make_running(org, user)
    with with_org(org.id):
        Investigation.objects.filter(id=row.id).update(attempt=2, run_key=f"{row.id}:2")
        row.refresh_from_db()
        raw_new = mint_token(row)
    assert (
        call(raw_old, "search_knowledge", {"query": "hosting"}, search_knowledge)["error"]
        == "not_running"
    )
    assert "results" in call(raw_new, "search_knowledge", {"query": "hosting"}, search_knowledge)


def test_denied_calls_stay_counted_and_audited():
    org, user = make_org(), make_user()
    make_membership(org, user)
    ingest_markdown(org, user, CORPUS)
    row, raw = make_running(org, user)
    out = call(
        raw, "get_document", {"document_id": "00000000-0000-0000-0000-000000000000"}, get_document
    )
    assert out["error"] == "not_found"
    with with_org(org.id):
        assert Investigation.objects.get(id=row.id).tool_calls_used == 1
        assert AccessEvent.objects.filter(kind="denied", investigation_id=row.id).exists()


def test_completion_does_not_resurrect_purged_text(monkeypatch):
    runner = FakeRunner("complete", queries=["hosting decision"], read_first=False)
    org, user, link, scope = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    original_get = runner.get

    def purge_then_get(run_key):
        # The source is removed while the worker reads the terminal record.
        apply_change(
            link, scope, make_event(90, None, kind="remove", source_id="gdrive:decision"), None
        )
        return original_get(run_key)

    runner.get = purge_then_get
    assert run_sync(org, inv.id, runner) == "completed"
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert row.content_state == "purged" and row.result is None


def test_reaper_does_not_restart_a_cancelled_investigation(monkeypatch):
    runner = FakeRunner("hang")
    org, user, *_ = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    old = timezone.now() - timedelta(minutes=10)
    with with_org(org.id):
        Investigation.objects.filter(id=inv.id).update(
            status="running", heartbeat_at=old, run_key=f"{inv.id}:1"
        )
    original_get = runner.get

    def cancel_during_get(run_key):
        with with_org(org.id):
            Investigation.objects.filter(id=inv.id).update(status="cancelled")
        return original_get(run_key)

    runner.get = cancel_during_get
    runner.runs[f"{inv.id}:1"] = {
        "state": "running",
        "events": [],
        "terminal": None,
        "token": "x",
        "question": "q",
        "instructions": "i",
        "exit_code": None,
    }
    service.reap(org.id, client=runner)
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert row.status == "cancelled" and row.attempt == 1


def test_results_without_verified_statements_do_not_present_prose_as_findings():
    text = "## Answer\nThe board approved everything.\n\n## Statements\n- The board approved everything. [chunk:00000000-0000-0000-0000-000000000000@v1[0:1]]"
    parsed = validate_citations(parse_result(text), set())
    assert parsed.answer_verified is False
    assert "does not establish" in parsed.answer
    assert "The board approved everything." in parsed.unsupported_statements


def test_agent_record_depends_on_every_supplied_revision(monkeypatch):
    from decisions.api import DecisionRecord, visible_records

    runner = FakeRunner(
        "draft", queries=["hosting decision", "alternative proposal"], read_first=False
    )
    org, user, link, scope = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    run_sync(org, inv.id, runner)
    with with_org(org.id):
        record = DecisionRecord.objects.get(organization=org)
        supplied = set(record.supplied_version_ids)
        cited = {str(e.version_id) for e in record.evidence.all()}
        seen = {
            str(v)
            for v in InvestigationEvidence.objects.filter(investigation_id=inv.id).values_list(
                "version_id", flat=True
            )
        }
        assert supplied == seen and cited <= supplied
        assert [r.id for r in visible_records(principal_for(org, user))] == [record.id]
    # Removing an uncited-but-supplied source hides and purges the record.
    uncited_source = (
        "gdrive:alternative"
        if any(
            "alternative" in str(e.document.source_id)
            for e in record.evidence.select_related("document")
        )
        is False
        else "gdrive:revision"
    )
    apply_change(link, scope, make_event(95, None, kind="remove", source_id=uncited_source), None)
    with with_org(org.id):
        record.refresh_from_db()
        assert visible_records(principal_for(org, user)) == []
        assert record.content_state == "purged"


def test_unlink_cancels_open_investigations(monkeypatch):
    runner = FakeRunner("hang")
    org, user, link, _scope = setup(monkeypatch, runner)
    inv = start(org, user, monkeypatch)
    revoke_link(link)
    with with_org(org.id):
        row = Investigation.objects.get(id=inv.id)
        assert row.status == "cancelled"
        assert (
            CapabilityToken.objects.filter(investigation=row, revoked_at__isnull=True).count() == 0
        )


def _runner_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("REGISTRY_ROOT", str(tmp_path / "registry"))
    monkeypatch.setenv("RUNNER_SHARED_SECRET", "s")
    monkeypatch.setenv("RUNNER_MAX_CONCURRENT", "1")
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "hermes" / "runner"))
    for name in ("runs", "attestation", "serve"):
        sys.modules.pop(name, None)
    runs = importlib.import_module("runs")
    serve = importlib.import_module("serve")
    (tmp_path / "runs").mkdir()
    (tmp_path / "registry").mkdir()
    return runs, serve


def test_runner_cancel_before_start_and_capacity(tmp_path, monkeypatch):
    runs, serve = _runner_modules(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient

    serve._attestation.update({"ok": True, "detail": "test"})
    client = TestClient(serve.app)
    headers = {"Authorization": "Bearer s"}
    body = {
        "run_key": "inv:1",
        "question": "q",
        "instructions": "i",
        "max_turns": 2,
        "max_tool_calls": 2,
        "timeout_s": 30,
        "mcp_token": "t" * 32,
    }
    assert client.post("/runs", json=body, headers=headers).status_code == 201
    # Capacity counts created runs, not only started ones.
    assert (
        client.post("/runs", json={**body, "run_key": "inv:2"}, headers=headers).status_code == 429
    )
    # Cancel before start: the run is terminal and /start does not launch it.
    cancelled = client.post("/runs/inv:1/cancel", headers=headers).json()
    assert cancelled["state"] == "cancelled" and cancelled["cancelled"] is True
    started = client.post("/runs/inv:1/start", headers=headers).json()
    assert started["state"] == "cancelled"
    assert client.get("/runs/inv:1", headers=headers).json()["terminal"]["outcome"] == "cancelled"
    assert client.delete("/runs/inv:1", headers=headers).status_code == 200
    assert client.get("/runs/inv:1", headers=headers).status_code == 404
    assert client.get("/runs/inv:1").status_code == 401
    assert "disabled_toolsets" in runs.render_config("http://x/mcp", "m", 1, 1)
