"""Decision records: candidate creation, steward workflow, evidence-bound
visibility, timeline with unknown stages, purge, extraction, MCP tools, views."""

from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.utils import timezone

from decisions.api import (
    DecisionEvidence,
    DecisionRecord,
    EvidenceInput,
    create_candidate,
    draft_knowledge_record,
    extract_candidates_for_version,
    find_related_documents,
    pending_approval_count,
    timeline,
    trace_decision,
    transition,
    visible_records,
)
from infra.api import with_org
from investigations.api import Investigation, InvestigationEvidence, mint_token
from knowledge.api import Document, DocumentReference, apply_change
from knowledge.tests.helpers import ingest_markdown, make_event, principal_for
from mcp_server.api import authorize_and_run
from organizations.api import Membership
from organizations.tests.factories import make_membership, make_org, make_user
from retrieval.api import Chunk

pytestmark = pytest.mark.django_db(transaction=True)

DECISION = b"# Hosting decision\nIn March the team selected provider Alpha for hosting after a cost review.\n"
ALTERNATIVE = (
    b"# Alternative proposal\nProvider Beta was proposed as an alternative with lower latency.\n"
)
REVISION = (
    b"# Hosting revision\nIn June the hosting contract moved from Alpha to Gamma after an outage.\n"
)


def corpus():
    org = make_org()
    member, steward = make_user(), make_user()
    make_membership(org, member)
    make_membership(org, steward, Membership.ROLE_STEWARD)
    docs = {
        "gdrive:decision": DECISION,
        "gdrive:alternative": ALTERNATIVE,
        "gdrive:revision": REVISION,
    }
    link, scope = ingest_markdown(org, member, docs)
    # The steward links their own account too: evidence-bound records need the
    # steward to see every passage before any transition.
    ingest_markdown(org, steward, docs)
    with with_org(org.id):
        chunks = {c.document.source_id: c for c in Chunk.objects.select_related("document")}
    return org, member, steward, link, scope, chunks


def test_candidate_workflow_and_timeline():
    org, member, steward, _link, _scope, chunks = corpus()
    p_member, p_steward = principal_for(org, member), principal_for(org, steward, role="steward")
    record = create_candidate(
        p_member,
        title="Hosting provider selection",
        origin="user",
        evidence=[
            EvidenceInput(str(chunks["gdrive:decision"].id), "decision"),
            EvidenceInput(str(chunks["gdrive:alternative"].id), "option"),
            EvidenceInput(str(chunks["gdrive:revision"].id), "change"),
        ],
    )
    assert record.status == "candidate" and record.approval_status == "unknown"
    with with_org(org.id):
        tl = timeline(record)
        assert (
            tl.stages["decision"]["state"] == "documented"
            and tl.stages["option"]["state"] == "documented"
        )
        assert (
            tl.stages["problem"]["state"] == "unknown"
            and tl.stages["rationale"]["state"] == "unknown"
        )
        assert pending_approval_count(org.id) == 1
    with pytest.raises(PermissionDenied):
        transition(p_member, record, "draft")
    with pytest.raises(ValidationError):
        transition(p_steward, record, "verified")  # candidate must go through draft
    transition(p_steward, record, "draft")
    transition(p_steward, record, "verified")
    with with_org(org.id):
        record.refresh_from_db()
        assert record.status == "verified" and record.verified_by_id == steward.pk
    newer = create_candidate(
        p_steward,
        title="Move to Gamma",
        origin="user",
        evidence=[EvidenceInput(str(chunks["gdrive:revision"].id), "decision")],
    )
    transition(p_steward, newer, "draft")
    transition(p_steward, newer, "verified")
    transition(p_steward, record, "superseded", superseded_by=newer)
    with with_org(org.id):
        record.refresh_from_db()
        assert record.status == "superseded" and record.superseded_by_id == newer.id
        assert timeline(newer).supersedes == [str(record.id)]


def test_candidate_requires_visible_evidence_and_visibility_is_evidence_bound():
    org, member, steward, link, scope, chunks = corpus()
    outsider = make_user()
    make_membership(org, outsider)
    with pytest.raises(PermissionDenied):
        create_candidate(
            principal_for(org, outsider),
            title="x",
            origin="user",
            evidence=[EvidenceInput(str(chunks["gdrive:decision"].id))],
        )
    record = create_candidate(
        principal_for(org, member),
        title="Hosting",
        origin="user",
        evidence=[
            EvidenceInput(str(chunks["gdrive:decision"].id)),
            EvidenceInput(str(chunks["gdrive:revision"].id)),
        ],
    )
    with with_org(org.id):
        assert [r.id for r in visible_records(principal_for(org, member))] == [record.id]
        assert visible_records(principal_for(org, outsider)) == []
    # Member loses one evidence document: the whole record disappears for them,
    # while the steward (own grant) still sees it and the content stays.
    apply_change(
        link, scope, make_event(50, None, kind="remove", source_id="gdrive:revision"), None
    )
    with with_org(org.id):
        assert visible_records(principal_for(org, member)) == []
        assert [r.id for r in visible_records(principal_for(org, steward, role="steward"))] == [
            record.id
        ]
        record.refresh_from_db()
        assert record.content_state == "present"
    # The last authorizing grant goes: the revision is purged and the record's prose with it.
    from connectors.api import ConnectorLink, revoke_link

    with with_org(org.id):
        steward_link = ConnectorLink.objects.get(user=steward)
    revoke_link(steward_link)
    with with_org(org.id):
        record.refresh_from_db()
        assert record.content_state == "purged" and record.description is None
        ev = DecisionEvidence.objects.filter(
            record=record, document__source_id="gdrive:revision"
        ).get()
        assert ev.chunk_id is None and ev.excerpt is None and ev.version_label == "v1"


def test_extraction_creates_candidates_only():
    org, member, _steward, _link, _scope, _chunks = corpus()
    with with_org(org.id):
        version = Document.objects.get(source_id="gdrive:decision").versions.get()
    created = extract_candidates_for_version(principal_for(org, member), version)
    assert created and all(r.status == "candidate" and r.origin == "extraction" for r in created)
    assert extract_candidates_for_version(principal_for(org, member), version) == []  # idempotent


def running_token(org, user):
    with with_org(org.id, user.pk):
        row = Investigation.objects.create(
            organization=org,
            user=user,
            question="q",
            status="running",
            attempt=1,
            deadline_at=timezone.now() + timedelta(minutes=5),
            limits={
                "max_turns": 12,
                "max_tool_calls": 50,
                "timeout_s": 180,
                "max_output_chars": 200000,
                "max_retries": 1,
            },
        )
        row.run_key = f"{row.id}:1"
        row.save(update_fields=["run_key"])
        return row, mint_token(row)


def call(raw, tool, args, impl):
    return authorize_and_run({"authorization": f"Bearer {raw}"}, tool, args, impl)


def test_mcp_trace_related_and_draft_tools():
    org, member, steward, _link, _scope, chunks = corpus()
    p_steward = principal_for(org, steward, role="steward")
    verified = create_candidate(
        p_steward,
        title="Hosting provider selection",
        origin="user",
        evidence=[EvidenceInput(str(chunks["gdrive:decision"].id), "decision")],
    )
    transition(p_steward, verified, "draft")
    transition(p_steward, verified, "verified")
    with with_org(org.id):
        d_decision = Document.objects.get(source_id="gdrive:decision")
        d_revision = Document.objects.get(source_id="gdrive:revision")
        DocumentReference.objects.create(
            organization=org,
            from_version=d_revision.versions.get(),
            to_document=d_decision,
            kind="explicit_link",
        )
    row, raw = running_token(org, member)

    trace = call(raw, "trace_decision", {"topic": "hosting"}, trace_decision)
    labels = {i["label"] for i in trace["items"]}
    assert "confirmed" in labels and "inferred" in labels
    confirmed = next(i for i in trace["items"] if i["label"] == "confirmed")
    assert confirmed["status"] == "verified" and confirmed["approval_status"] == "unknown"
    assert "rationale" in confirmed and confirmed["rationale"] == ""  # nothing invented

    related = call(
        raw, "find_related_documents", {"document_id": str(d_decision.id)}, find_related_documents
    )
    assert any(
        e["label"] == "explicit" and e["document_id"] == str(d_revision.id)
        for e in related["explicit"]
    )
    assert all(s["label"] == "similar" for s in related["similar"]) and related["similar"]

    search_payload = call(
        raw,
        "search_knowledge",
        {"query": "hosting alternative"},
        __import__("mcp_server.api", fromlist=["search_knowledge"]).search_knowledge,
    )
    ids = [r["evidence_id"] for r in search_payload["results"]][:2]
    bad = call(
        raw,
        "draft_knowledge_record",
        {
            "topic": "Hosting",
            "evidence_ids": ["chunk:00000000-0000-0000-0000-000000000000@v1[0:1]"],
        },
        draft_knowledge_record,
    )
    assert bad["error"] == "invalid_argument"
    draft = call(
        raw,
        "draft_knowledge_record",
        {"topic": "Hosting change history", "evidence_ids": ids},
        draft_knowledge_record,
    )
    assert draft["status"] == "candidate"
    with with_org(org.id):
        rec = DecisionRecord.objects.get(id=draft["record_id"])
        assert rec.origin == "agent" and rec.verified_by is None
        assert InvestigationEvidence.objects.filter(investigation=row).exists()


def test_views_list_detail_create_and_transition():
    org, member, steward, _link, _scope, chunks = corpus()
    c = Client()
    c.force_login(member)
    assert c.get(f"/o/{org.slug}/decisions/").status_code == 200
    created = c.post(
        f"/o/{org.slug}/decisions/new/",
        {"title": "Hosting", "chunk_id": [str(chunks["gdrive:decision"].id)], "role": ["decision"]},
    )
    assert created.status_code == 302
    detail = c.get(created["Location"])
    assert detail.status_code == 200 and b"unknown" in detail.content
    record_id = created["Location"].rstrip("/").rsplit("/", 1)[1]
    denied = c.post(f"/o/{org.slug}/decisions/{record_id}/transition/", {"to": "draft"})
    assert denied.status_code == 302
    with with_org(org.id):
        assert DecisionRecord.objects.get(id=record_id).status == "candidate"
    s = Client()
    s.force_login(steward)
    s.post(f"/o/{org.slug}/decisions/{record_id}/transition/", {"to": "draft"})
    s.post(f"/o/{org.slug}/decisions/{record_id}/transition/", {"to": "verified"})
    with with_org(org.id):
        assert DecisionRecord.objects.get(id=record_id).status == "verified"
    outsider = make_user()
    make_membership(org, outsider)
    o = Client()
    o.force_login(outsider)
    assert o.get(f"/o/{org.slug}/decisions/{record_id}/").status_code == 404


def test_steward_transition_does_not_restore_purged_prose():
    org, _member, steward, _link, _scope, chunks = corpus()
    p_steward = principal_for(org, steward, role="steward")
    record = create_candidate(
        p_steward,
        title="Hosting",
        origin="user",
        description="prose",
        evidence=[EvidenceInput(str(chunks["gdrive:decision"].id), "decision")],
    )
    # The steward holds a stale instance (content present) while a purge lands.
    with with_org(org.id):
        DecisionRecord.objects.filter(id=record.id).update(description=None, content_state="purged")
    assert record.content_state == "present" and record.description == "prose"
    with pytest.raises(PermissionDenied):
        transition(p_steward, record, "draft")
    with with_org(org.id):
        fresh = DecisionRecord.objects.get(id=record.id)
        assert (
            fresh.content_state == "purged"
            and fresh.description is None
            and fresh.status == "candidate"
        )


def test_superseding_record_title_hidden_from_unauthorized_reader():
    org, member, steward, _link, _scope, chunks = corpus()
    p_steward = principal_for(org, steward, role="steward")
    old = create_candidate(
        p_steward,
        title="Old decision",
        origin="user",
        evidence=[EvidenceInput(str(chunks["gdrive:decision"].id))],
    )
    transition(p_steward, old, "draft")
    transition(p_steward, old, "verified")
    # The steward's private document (only the steward linked it) backs the replacement.
    ingest_markdown(org, steward, {"gdrive:private": b"# Private\nSecret replacement rationale."})
    with with_org(org.id):
        private_chunk = Chunk.objects.get(document__source_id="gdrive:private")
    new = create_candidate(
        p_steward,
        title="SECRET replacement",
        origin="user",
        evidence=[EvidenceInput(str(private_chunk.id))],
    )
    transition(p_steward, new, "draft")
    transition(p_steward, new, "verified")
    transition(p_steward, old, "superseded", superseded_by=new)
    c = Client()
    c.force_login(member)
    page = c.get(f"/o/{org.slug}/decisions/{old.id}/")
    assert page.status_code == 200
    assert b"SECRET replacement" not in page.content and b"a record you cannot see" in page.content
