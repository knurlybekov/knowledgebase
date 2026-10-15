"""Regression tests from the Sprint 2-3 reinspection (round 2 of 2): decision tools."""

import pytest

from decisions.api import (
    DecisionRecord,
    EvidenceInput,
    create_candidate,
    draft_knowledge_record,
    trace_decision,
)
from decisions.tasks import extract_for_version
from infra.api import with_org
from investigations.api import Investigation
from knowledge.api import Document, apply_change
from knowledge.tests.helpers import make_event, principal_for

from .test_decisions import call, corpus, running_token

pytestmark = pytest.mark.django_db(transaction=True)


def test_trace_decision_is_bound_to_supplied_revisions():
    org, member, steward, link, scope, chunks = corpus()
    with with_org(org.id):
        alternative = Document.objects.get(source_id="gdrive:alternative").versions.get()
    # Cited: the decision passage. Supplied but uncited: the alternative revision.
    create_candidate(
        principal_for(org, steward, role="steward"),
        title="Hosting provider selection",
        origin="agent",
        evidence=[EvidenceInput(str(chunks["gdrive:decision"].id), "decision")],
        supplied_version_ids=[str(alternative.id)],
    )
    row, raw = running_token(org, member)
    trace = call(raw, "trace_decision", {"topic": "hosting"}, trace_decision)
    assert any(i["kind"] == "record" for i in trace["items"])
    with with_org(org.id):
        row.refresh_from_db()
        assert str(alternative.id) in row.supplied_version_ids  # dependency propagated
    # The member loses the uncited revision: the record disappears from trace_decision.
    apply_change(
        link, scope, make_event(90, None, kind="remove", source_id="gdrive:alternative"), None
    )
    trace = call(raw, "trace_decision", {"topic": "hosting"}, trace_decision)
    assert not any(i["kind"] == "record" for i in trace["items"])


def test_draft_is_refused_for_a_purged_investigation():
    org, member, _steward, _link, _scope, _chunks = corpus()
    row, raw = running_token(org, member)
    with with_org(org.id):
        Investigation.objects.filter(id=row.id).update(content_state="purged")
    out = call(
        raw,
        "draft_knowledge_record",
        {
            "topic": "Hosting",
            "evidence_ids": ["chunk:00000000-0000-0000-0000-000000000000@v1[0:1]"],
        },
        draft_knowledge_record,
    )
    assert out["error"] == "not_running"
    with with_org(org.id):
        assert not DecisionRecord.objects.filter(origin="agent").exists()


def test_extraction_task_skips_a_revision_the_owner_cannot_see(monkeypatch):
    org, member, _steward, link, scope, _chunks = corpus()
    with with_org(org.id):
        version = Document.objects.get(source_id="gdrive:decision").versions.get()
    apply_change(
        link, scope, make_event(91, None, kind="remove", source_id="gdrive:decision"), None
    )

    def never(*a, **k):
        raise AssertionError("the model must not receive an invisible revision")

    monkeypatch.setattr("decisions.extraction.extract_candidates_for_version", never)
    assert extract_for_version(str(org.id), str(version.id), str(member.pk)) == 0
