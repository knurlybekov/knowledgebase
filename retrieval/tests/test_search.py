import pytest

from connectors.tests.factories import make_link, make_scope
from infra.api import with_org
from knowledge.api import apply_change
from knowledge.tests.helpers import StaticFetcher, make_event, make_source, principal_for
from organizations.tests.factories import make_membership, make_org, make_user
from retrieval.api import Chunk, Embedding, RetrievalLog, search

pytestmark = pytest.mark.django_db(transaction=True)

VACATION = b"# Vacation policy\nEmployees accrue fifteen days of vacation each year.\n"
HOSTING = b"# Hosting\nThe platform runs on provider Alpha since March.\n"


def ingest(org, user, docs):
    make_membership(org, user)
    link = make_link(org, user)
    scope = make_scope(link)
    for i, (sid, body) in enumerate(docs, start=1):
        apply_change(
            link,
            scope,
            make_event(i, make_source(sid, "v1", title=sid)),
            StaticFetcher({"v1": body}),
        )
    return link, scope


def test_keyword_and_vector_legs_fuse_and_log():
    org, user = make_org(), make_user()
    ingest(org, user, [("gdrive:vac", VACATION), ("gdrive:host", HOSTING)])
    principal = principal_for(org, user)
    results = search(principal, "vacation days each year")
    assert results and results[0].title == "gdrive:vac"
    assert "keyword" in results[0].legs
    assert results[0].evidence_id.startswith("chunk:")
    with with_org(org.id):
        log = RetrievalLog.objects.filter(organization=org).get()
    assert log.denied_count == 0 and log.mode == "quick"

    # The mock embedder is deterministic: a query equal to the chunk text has distance 0.
    with with_org(org.id):
        text = Chunk.objects.get(document__source_id="gdrive:host").text
    results = search(principal, text)
    assert results[0].title == "gdrive:host" and "vector" in results[0].legs


def test_search_respects_visibility_between_users():
    org = make_org()
    ua, ub = make_user(), make_user()
    ingest(org, ua, [("gdrive:vac", VACATION)])
    ingest(org, ub, [("gdrive:host", HOSTING)])
    assert [r.title for r in search(principal_for(org, ua), "vacation hosting provider")] == [
        "gdrive:vac"
    ]
    assert [r.title for r in search(principal_for(org, ub), "vacation hosting provider")] == [
        "gdrive:host"
    ]


def test_vector_leg_ignores_other_embedding_models():
    org, user = make_org(), make_user()
    ingest(org, user, [("gdrive:vac", VACATION)])
    with with_org(org.id):
        Embedding.objects.update(model_id="other-model")
    results = search(principal_for(org, user), "vacation")
    assert results and results[0].legs == ["keyword"]


def test_source_type_filter_and_empty_query():
    org, user = make_org(), make_user()
    ingest(org, user, [("gdrive:vac", VACATION)])
    principal = principal_for(org, user)
    assert search(principal, "vacation", source_types=["sharepoint"]) == []
    assert search(principal, "   ") == []
