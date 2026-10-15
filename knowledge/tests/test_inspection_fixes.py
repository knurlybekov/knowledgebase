"""Regression tests from the Sprint 1 post-build inspection."""

import pytest

from connectors.api import ConnectorLink, SyncScope, ensure_scope, reconcile_selected_scopes
from connectors.tests.factories import make_link, make_scope
from infra.api import with_org
from knowledge.api import OBSOLETE, PUBLISHED, REVOKED, STALE, AccessGrant, Document, apply_change
from knowledge.purge import authorizing_grants
from organizations.tests.factories import make_membership, make_org, make_user
from retrieval.api import Chunk

from .helpers import StaticFetcher, count_visible, make_event, make_source, principal_for

pytestmark = pytest.mark.django_db(transaction=True)
DOC = b"# Doc\nSome content about hosting.\n"


def test_removal_during_first_ingestion_is_fenced():
    org, user = make_org(), make_user()
    make_membership(org, user)
    link = make_link(org, user)
    scope = make_scope(link)
    sd = make_source("gdrive:f1", "v1")

    def on_fetch(_sd):
        # A removal arrives while the very first download is in flight: no grant exists yet.
        assert (
            apply_change(
                link, scope, make_event(2, None, kind="remove", source_id="gdrive:f1"), None
            )
            == REVOKED
        )

    outcome = apply_change(
        link, scope, make_event(1, sd), StaticFetcher({"v1": DOC}, on_fetch=on_fetch)
    )
    assert outcome == STALE
    # The requeued retry sees the fence and is obsolete.
    assert apply_change(link, scope, make_event(1, sd), StaticFetcher({"v1": DOC})) == OBSOLETE
    with with_org(org.id):
        grant = AccessGrant.objects.get(scope=scope)
        assert (
            grant.revoked_at is not None and grant.version_id is None and grant.last_event_seq == 2
        )
        assert not Chunk.objects.exists()
    assert count_visible(principal_for(org, user)) == 0
    # A later re-add publishes again.
    assert apply_change(link, scope, make_event(3, sd), StaticFetcher({"v1": DOC})) == PUBLISHED
    assert count_visible(principal_for(org, user)) == 1


def test_same_document_through_two_scopes_keeps_independent_fences():
    org, user = make_org(), make_user()
    make_membership(org, user)
    link = make_link(org, user, provider=ConnectorLink.PROVIDER_SHAREPOINT)
    s1 = ensure_scope(link, kind=SyncScope.KIND_GRAPH_DRIVE, external_id="d1")
    s2 = ensure_scope(link, kind=SyncScope.KIND_GRAPH_DRIVE, external_id="d2")
    sd = make_source("sp:d1:i1", "c1", source_type="sharepoint")
    apply_change(link, s1, make_event(10, sd), StaticFetcher({"c1": DOC}))
    # Scope 2 sees the same item with a low sequence of its own: not obsolete.
    assert apply_change(link, s2, make_event(1, sd), StaticFetcher({"c1": DOC})) in (
        "refreshed",
        "published",
    )
    with with_org(org.id):
        assert AccessGrant.objects.filter(document__source_id="sp:d1:i1").count() == 2
    # Removal in scope 2 does not revoke scope 1.
    apply_change(link, s2, make_event(2, None, kind="remove", source_id="sp:d1:i1"), None)
    assert count_visible(principal_for(org, user)) == 1


def test_deselecting_a_library_disables_its_scope_and_revokes_grants():
    org, user = make_org(), make_user()
    make_membership(org, user)
    link = make_link(org, user, provider=ConnectorLink.PROVIDER_SHAREPOINT)
    reconcile_selected_scopes(
        link, kind=SyncScope.KIND_GRAPH_DRIVE, selected={"d1": "Docs", "d2": "Plans"}
    )
    with with_org(org.id):
        s1 = SyncScope.objects.get(link=link, external_id="d1")
    apply_change(
        link,
        s1,
        make_event(1, make_source("sp:d1:i1", "c1", source_type="sharepoint")),
        StaticFetcher({"c1": DOC}),
    )
    assert count_visible(principal_for(org, user)) == 1
    reconcile_selected_scopes(link, kind=SyncScope.KIND_GRAPH_DRIVE, selected={"d2": "Plans"})
    with with_org(org.id):
        assert SyncScope.objects.get(link=link, external_id="d1").enabled is False
        assert SyncScope.objects.get(link=link, external_id="d2").enabled is True
        assert AccessGrant.objects.get(scope=s1).revoke_reason == "deselected"
    assert count_visible(principal_for(org, user)) == 0


def test_user_deactivation_revokes_links_and_purges():
    org, user = make_org(), make_user()
    make_membership(org, user)
    link = make_link(org, user)
    scope = make_scope(link)
    apply_change(
        link, scope, make_event(1, make_source("gdrive:f1", "v1")), StaticFetcher({"v1": DOC})
    )
    user.is_active = False
    user.save()
    with with_org(org.id):
        assert ConnectorLink.objects.get(id=link.id).status == "revoked"
        assert not Chunk.objects.exists()


def test_purge_ignores_grants_that_no_longer_authorize():
    org = make_org()
    a, b = make_user(), make_user()
    make_membership(org, a)
    make_membership(org, b)
    la, lb = make_link(org, a), make_link(org, b)
    sa, sb = make_scope(la), make_scope(lb)
    sd = make_source("gdrive:f1", "v1")
    apply_change(la, sa, make_event(1, sd), StaticFetcher({"v1": DOC}))
    apply_change(lb, sb, make_event(1, sd), StaticFetcher({"v1": DOC}))
    with with_org(org.id):
        ConnectorLink.objects.filter(id=lb.id).update(status="error")
        version_id = Document.objects.get(source_id="gdrive:f1").versions.get().id
        assert authorizing_grants(version_id).count() == 1
    # Revoking A's grant now purges: B's errored link does not keep the content alive.
    apply_change(la, sa, make_event(2, None, kind="remove", source_id="gdrive:f1"), None)
    with with_org(org.id):
        assert not Chunk.objects.exists()


def test_google_refresh_error_maps_to_auth_error(monkeypatch):
    from google.auth.exceptions import RefreshError

    from connectors.http import AuthError
    from connectors.providers.google import GoogleApiClient

    class Req:
        def execute(self, num_retries=0):
            raise RefreshError("invalid_grant")

    client = GoogleApiClient.__new__(GoogleApiClient)
    with pytest.raises(AuthError):
        client._run(Req())
