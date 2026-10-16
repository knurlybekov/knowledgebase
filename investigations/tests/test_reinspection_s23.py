"""Regression tests from the Sprint 2-3 reinspection (round 2 of 2)."""

import dataclasses
import io
import json
import signal
import time

import pytest

from infra.api import with_org
from investigations import service
from investigations.api import Investigation, InvestigationEvidence
from investigations.results import parse_result, validate_citations
from knowledge.api import Document
from knowledge.tests.helpers import ingest_markdown
from mcp_server.api import authorize_and_run, get_document, search_knowledge
from mcp_server.tests.test_mcp_auth import make_running
from organizations.tests.factories import make_membership, make_org, make_user

from .test_inspection_s23 import _runner_modules
from .test_lifecycle import CORPUS

pytestmark = pytest.mark.django_db(transaction=True)


def call(raw, tool, args, impl):
    return authorize_and_run({"authorization": f"Bearer {raw}"}, tool, args, impl)


def test_answer_is_built_from_validated_statements_only():
    ok = "chunk:11111111-1111-1111-1111-111111111111@v1[0:10]"
    text = (
        "## Answer\nThe board approved everything and fired the vendor.\n\n"
        f"## Statements\n- The board approved the migration. [{ok}]\n"
        "- The board fired the vendor. [chunk:00000000-0000-0000-0000-000000000000@v1[0:1]]"
    )
    parsed = validate_citations(parse_result(text), {ok})
    assert parsed.answer_verified is True
    assert parsed.answer == "The board approved the migration."
    assert "fired" not in parsed.answer
    assert parsed.agent_prose.startswith("The board approved everything")
    assert parsed.unsupported_statements == ["The board fired the vendor."]


def test_invalid_argument_is_a_committed_denial():
    org, user = make_org(), make_user()
    make_membership(org, user)
    ingest_markdown(org, user, CORPUS)
    row, raw = make_running(org, user)
    out = call(raw, "get_document", {"document_id": "not-a-uuid"}, get_document)
    assert out["error"] == "invalid_argument"
    with with_org(org.id):
        assert Investigation.objects.get(id=row.id).tool_calls_used == 1


def _span(evidence_id: str) -> tuple[int, int]:
    start, end = evidence_id.rsplit("[", 1)[1].rstrip("]").split(":")
    return int(start), int(end)


def test_evidence_spans_follow_delivered_text():
    org, user = make_org(), make_user()
    make_membership(org, user)
    docs = {
        f"gdrive:d{i}": b"# Doc\n" + (f"Vacation policy paragraph {i}. " * 40).encode()
        for i in range(5)
    }
    ingest_markdown(org, user, docs)
    row, raw = make_running(org, user, max_output_chars=1500)
    out = call(
        raw,
        "search_knowledge",
        {"query": "vacation policy paragraph", "limit": 5},
        search_knowledge,
    )
    assert out["results"]
    with with_org(org.id):
        stored = {
            str(e.chunk_id): (e.span_start, e.span_end)
            for e in InvestigationEvidence.objects.filter(investigation_id=row.id)
        }
    for item in out["results"]:
        start, end = _span(item["evidence_id"])
        assert end - start == len(item["excerpt"])  # the id covers exactly the delivered excerpt
        assert stored[item["chunk_id"]] == (
            start,
            end,
        )  # the persisted span equals the delivered one
    assert len(stored) == len(out["results"])  # dropped results leave no evidence behind
    assert len(json.dumps(out)) < 1500 + 200


def test_document_window_spans_stay_inside_the_window():
    org, user = make_org(), make_user()
    make_membership(org, user)
    body = "\n\n".join(
        f"## Section {i}\n" + (f"Paragraph {i} about hosting. " * 60) for i in range(12)
    )
    ingest_markdown(org, user, {"gdrive:long": ("# Long\n" + body).encode()})
    row, raw = make_running(org, user)
    out = call(raw, "get_document", {"document_id": _doc_id(org, "gdrive:long")}, get_document)
    assert out["window"]["end"] < out["window"]["total_chars"]
    with with_org(org.id):
        rows = list(
            InvestigationEvidence.objects.filter(investigation_id=row.id).select_related("chunk")
        )
    assert rows
    delivered = sum(e.span_end - e.span_start for e in rows)
    assert delivered <= len(out["content"]) + 2 * len(
        rows
    )  # headings and joins aside, no undelivered text
    for e in rows:
        # Spans are chunk-text offsets added to locator start_char (see delivered_evidence).
        start_char = e.chunk.locator["start_char"]
        assert start_char <= e.span_start < e.span_end <= start_char + len(e.chunk.text)


def _doc_id(org, source_id) -> str:
    with with_org(org.id):
        return str(Document.objects.get(source_id=source_id).id)


def test_purge_follows_the_supplied_versions_field_without_evidence_rows():
    org, user = make_org(), make_user()
    make_membership(org, user)
    ingest_markdown(org, user, CORPUS)
    row, _raw = make_running(org, user, status="completed")
    with with_org(org.id):
        version = Document.objects.get(source_id="gdrive:alternative").versions.get()
        Investigation.objects.filter(id=row.id).update(
            supplied_version_ids=[str(version.id)], result={"answer": "x"}
        )
        assert not InvestigationEvidence.objects.filter(investigation_id=row.id).exists()
        assert service.purge_investigations_for_version(version) == 1
        row.refresh_from_db()
        assert row.content_state == "purged" and row.result is None


# --- runner lifecycle -------------------------------------------------------------


def _client(serve):
    from fastapi.testclient import TestClient

    serve._attestation.update({"ok": True, "detail": "test"})
    return TestClient(serve.app), {"Authorization": "Bearer s"}


BODY = {
    "run_key": "inv:1",
    "question": "q",
    "instructions": "i",
    "max_turns": 2,
    "max_tool_calls": 2,
    "timeout_s": 30,
    "mcp_token": "t" * 32,
}


def test_failed_launch_is_terminal_and_releases_capacity(tmp_path, monkeypatch):
    runs, serve = _runner_modules(tmp_path, monkeypatch)
    client, headers = _client(serve)

    def boom(*a, **k):
        raise OSError("no binary")

    monkeypatch.setattr(runs.subprocess, "Popen", boom)
    assert client.post("/runs", json=BODY, headers=headers).status_code == 201
    assert client.post("/runs/inv:1/start", headers=headers).status_code == 500
    state = client.get("/runs/inv:1", headers=headers).json()
    assert state["state"] == "failed" and state["terminal"]["outcome"] == "failed"
    assert "inv:1" not in serve._pending  # credentials left memory
    # Capacity one: the failed run no longer blocks the next create.
    assert (
        client.post("/runs", json={**BODY, "run_key": "inv:2"}, headers=headers).status_code == 201
    )


def test_terminalize_after_delete_does_not_recreate_the_record(tmp_path, monkeypatch):
    runs, serve = _runner_modules(tmp_path, monkeypatch)
    client, headers = _client(serve)
    assert client.post("/runs", json=BODY, headers=headers).status_code == 201
    run = serve._runs["inv:1"]
    assert client.post("/runs/inv:1/cancel", headers=headers).json()["state"] == "cancelled"
    assert client.delete("/runs/inv:1", headers=headers).status_code == 200
    # A late pump that persists after deletion is refused by the lifecycle lock.
    run._terminalize("completed", {"outcome": "completed", "final_text": "secret", "usage": {}}, 0)
    assert runs.RunRecord.load("inv:1") is None
    assert client.get("/runs/inv:1", headers=headers).status_code == 404


def test_signal_group_escalates_when_the_leader_already_exited(tmp_path, monkeypatch):
    runs, _serve = _runner_modules(tmp_path, monkeypatch)
    record = runs.RunRecord(
        run_key="inv:9",
        state="running",
        dir=str(tmp_path / "r"),
        events_path=str(tmp_path / "e.jsonl"),
        pgid=424242,
    )
    run = runs.Run(record)
    sent = []
    monkeypatch.setattr(runs.os, "killpg", lambda pgid, sig: sent.append((pgid, sig)))
    monkeypatch.setattr(runs, "_group_members", lambda pgid: [1])  # a descendant survives
    monkeypatch.setattr(runs, "GRACE_S", 0.3)
    run._signal_group()  # _proc is None: the leader is gone
    assert sent == [(424242, signal.SIGINT), (424242, signal.SIGKILL)]


def test_expire_once_drops_old_terminal_records_on_disk_and_in_memory(tmp_path, monkeypatch):
    runs, serve = _runner_modules(tmp_path, monkeypatch)
    record = runs.RunRecord(
        run_key="inv:7",
        state="completed",
        dir=str(tmp_path / "r7"),
        events_path=str(tmp_path / "e7.jsonl"),
    )
    record.updated_at = time.time() - runs.RECORD_TTL_S - 5
    (runs.REGISTRY_ROOT / "inv_7.json").write_text(json.dumps(dataclasses.asdict(record)))
    run = runs.Run(record)
    serve._runs["inv:7"] = run
    assert serve._expire_once() == 1 or runs.RunRecord.load("inv:7") is None
    assert "inv:7" not in serve._runs


def test_attestation_runs_both_prompts_and_fails_on_a_foreign_tool(tmp_path, monkeypatch):
    runs, _serve = _runner_modules(tmp_path, monkeypatch)
    import attestation

    monkeypatch.setenv(runs.PROVIDER_KEY_ENV, "test-key")
    monkeypatch.setattr(runs, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.setattr(runs, "stop_gateway_for_home", lambda home: 0)

    class Proc:
        def terminate(self):
            pass

    monkeypatch.setattr(attestation, "_start_selfcheck", lambda token, port: Proc())
    seen = json.dumps({"auth_ok": True, "calls": 1}).encode()
    monkeypatch.setattr(attestation.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(seen))
    prompts = []

    def fake_run_prompt(prompt, home, env, max_turns):
        prompts.append(prompt)
        assert env["KNOWLEDGE_MCP_TOKEN"] and env[runs.PROVIDER_KEY_ENV] == "test-key"
        if prompt == attestation.ADVERSARIAL_PROMPT:
            return 0, {"terminal"}, ""
        return 0, {"mcp__knowledge__search_knowledge"}, ""

    monkeypatch.setattr(attestation, "_run_prompt", fake_run_prompt)
    out = attestation.run()
    assert prompts[1] == attestation.ADVERSARIAL_PROMPT and len(prompts) == 2
    assert out["ok"] is False and "foreign=['terminal']" in out["detail"]

    monkeypatch.setattr(
        attestation, "_run_prompt", lambda p, h, e, m: (0, {"mcp__knowledge__search_knowledge"}, "")
    )
    assert attestation.run()["ok"] is True
