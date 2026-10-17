import json

import pytest
from django.test import Client

from answers.api import (
    Answer,
    AnswerSchema,
    Claim,
    ComposerResult,
    StubComposer,
    answer_question,
    read_answer,
)
from answers.composer.base import EvidenceItem
from connectors.api import revoke_link
from infra.api import with_org
from knowledge.api import apply_change
from knowledge.tests.helpers import ingest_markdown, make_event, principal_for
from organizations.tests.factories import make_membership, make_org, make_user
from web.routing import suggest_mode

pytestmark = pytest.mark.django_db(transaction=True)

VACATION = b"# Vacation policy\nEmployees accrue fifteen vacation days each year. Unused days carry over once.\n"
HOSTING = b"# Hosting decision\nThe platform runs on provider Alpha since March. Provider Beta was rejected on cost.\n"


def setup():
    org, user = make_org("acme"), make_user()
    make_membership(org, user)
    link, scope = ingest_markdown(org, user, {"gdrive:vac": VACATION, "gdrive:host": HOSTING})
    return org, user, link, scope


def test_stub_composer_grounds_claims_in_overlapping_evidence():
    ev = [
        EvidenceItem(1, "Vacation", "Employees accrue fifteen vacation days each year."),
        EvidenceItem(2, "Hosting", "The platform runs on provider Alpha."),
    ]
    out = StubComposer().answer("How many vacation days do employees accrue?", ev)
    assert [c.evidence_indices for c in out.claims] == [[1]] and not out.insufficient
    assert StubComposer().answer("Where is the parking garage?", ev).insufficient


def test_answer_question_returns_claims_with_citations_and_logs_access():
    org, user, *_ = setup()
    principal = principal_for(org, user)
    result = answer_question(principal, "How many vacation days do employees accrue each year?")
    assert result.evidence_state == "sufficient"
    assert result.claims and result.claims[0]["citations"][0]["title"] == "gdrive:vac"
    assert result.claims[0]["citations"][0]["source_url"].startswith("https://docs.google.com/")
    assert "vacation" in result.summary.lower()
    with with_org(org.id):
        row = Answer.objects.get(id=result.id)
        assert row.evidence_version_ids and row.evidence_chunk_ids
        from infra.api import AccessEvent

        assert AccessEvent.objects.filter(kind="answer", object_id=str(row.id)).exists()


def test_insufficient_when_nothing_matches():
    org, user, *_ = setup()
    result = answer_question(principal_for(org, user), "zzqx unknown topic")
    assert result.evidence_state == "insufficient" and not result.claims
    assert "do not establish" in result.summary


def test_invalid_citation_indices_move_claims_to_unsupported(monkeypatch):
    org, user, *_ = setup()

    class BadComposer:
        model_id = "bad"

        def answer(self, question, evidence):
            return ComposerResult(
                claims=[
                    Claim(text="Vacation is fifteen days.", evidence_indices=[1]),
                    Claim(text="The CEO approved it personally.", evidence_indices=[99]),
                ],
                conflicts=["Items 1 and 2 disagree on the year."],
                insufficient=False,
                model_id="bad",
            )

    monkeypatch.setattr("answers.service.get_composer", lambda: BadComposer())
    result = answer_question(principal_for(org, user), "vacation days policy")
    assert [c["text"] for c in result.claims] == ["Vacation is fifteen days."]
    assert result.unsupported == ["The CEO approved it personally."]
    assert result.evidence_state == "conflicting"


def test_d6_whole_answer_withheld_after_revocation_and_purged_text_on_purge():
    org, user, link, scope = setup()
    principal = principal_for(org, user)
    result = answer_question(principal, "How many vacation days do employees accrue?")
    assert read_answer(principal, result.id).withheld is False

    # The answer saw both documents (one cited). Revoking the uncited one still withholds it.
    apply_change(link, scope, make_event(10, None, kind="remove", source_id="gdrive:host"), None)
    again = read_answer(principal, result.id)
    assert again.withheld is True and again.claims == []
    with with_org(org.id):
        assert Answer.objects.get(id=result.id).content_state == "purged"
        assert Answer.objects.get(id=result.id).claims is None

    other = make_user()
    make_membership(org, other)
    assert read_answer(principal_for(org, other), result.id) is None


def test_unlinking_the_account_withholds_answers():
    org, user, link, _ = setup()
    principal = principal_for(org, user)
    result = answer_question(principal, "vacation days")
    revoke_link(link)
    assert read_answer(principal, result.id).withheld is True


def test_search_page_and_json_endpoints(settings):
    org, user, *_ = setup()
    c = Client()
    c.force_login(user)
    page = c.get(f"/o/{org.slug}/search/", {"q": "vacation days each year", "mode": "quick"})
    assert page.status_code == 200 and b"Sources" in page.content
    settings.HERMES_ENABLED = False
    deep = c.get(f"/o/{org.slug}/search/", {"q": "why did we change hosting", "mode": "deep"})
    assert deep.status_code == 200 and b"Deep Investigation is disabled" in deep.content

    res = c.get(f"/o/{org.slug}/api/v1/search", {"q": "vacation", "limit": 5})
    assert res.status_code == 200 and res.json()["results"][0]["title"] == "gdrive:vac"
    assert "text" not in res.json()["results"][0]
    bad = c.get(f"/o/{org.slug}/api/v1/search", {"q": "x", "source_types": "dropbox"})
    assert bad.status_code == 400
    ans = c.post(
        f"/o/{org.slug}/api/v1/answers",
        data=json.dumps({"question": "vacation days each year"}),
        content_type="application/json",
    )
    assert ans.status_code == 200 and ans.json()["evidence_state"] == "sufficient"

    settings.RATE_LIMIT_SEARCH_PER_MIN = 1
    assert c.get(f"/o/{org.slug}/api/v1/search", {"q": "vacation"}).status_code in (200, 429)
    assert c.get(f"/o/{org.slug}/api/v1/search", {"q": "vacation"}).status_code == 429

    outsider = make_user()
    c2 = Client()
    c2.force_login(outsider)
    assert c2.get(f"/o/{org.slug}/api/v1/search", {"q": "vacation"}).status_code == 403


def test_routing_heuristic():
    assert suggest_mode("What is our vacation policy?") == "quick"
    assert suggest_mode("Why did we change our cloud hosting provider?") == "deep"
    assert suggest_mode("What alternatives did we consider before approving this?") == "deep"


def test_answer_schema_roundtrip():
    data = {
        "claims": [{"text": "x", "evidence_indices": [1]}],
        "conflicts": [],
        "insufficient": False,
    }
    assert AnswerSchema.model_validate(data).claims[0].evidence_indices == [1]


def test_publication_time_recheck_withholds_text_when_evidence_vanishes(monkeypatch):
    org, user, link, scope = setup()
    principal = principal_for(org, user)

    class RevokingComposer(StubComposer):
        def answer(self, question, evidence):
            # Access is lost while the model is generating.
            apply_change(
                link, scope, make_event(20, None, kind="remove", source_id="gdrive:vac"), None
            )
            return super().answer(question, evidence)

    monkeypatch.setattr("answers.service.get_composer", lambda: RevokingComposer())
    result = answer_question(principal, "How many vacation days do employees accrue?")
    assert result.withheld is True and result.claims == []
    with with_org(org.id):
        row = Answer.objects.get(id=result.id)
        assert row.content_state == "purged" and row.claims in (None, [])
