import pytest
from django.test import Client

from accounts.api import UserIdentity
from connectors import oauth
from connectors.api import ConnectorLink, SyncScope
from infra.api import with_org
from organizations.tests.factories import make_membership, make_org, make_user

pytestmark = pytest.mark.django_db(transaction=True)


def test_google_link_flow_creates_identity_link_and_scope(monkeypatch, settings):
    settings.GOOGLE_CLIENT_ID = "client"
    org, user = make_org("acme"), make_user()
    make_membership(org, user)
    monkeypatch.setattr(
        oauth,
        "google_authorization_url",
        lambda request, scopes, state: f"https://accounts.google.com/o/oauth2/auth?state={state}",
    )
    monkeypatch.setattr(
        oauth,
        "google_exchange_code",
        lambda request, scopes, code: oauth.OAuthResult(
            subject="sub-123", email="Karen@Example.test", refresh_token="rt-1", scopes=scopes
        ),
    )
    monkeypatch.setattr("connectors.tasks.client_for", lambda link: _FakeClient())

    c = Client()
    c.force_login(user)
    start = c.get(f"/connectors/google/start/{org.slug}/")
    assert start.status_code == 302
    state = start["Location"].split("state=", 1)[1]
    done = c.get(f"/connectors/google/callback/?code=abc&state={state}")
    assert done.status_code == 302 and done["Location"] == f"/o/{org.slug}/connectors/"
    identity = UserIdentity.objects.get(user=user)
    assert (
        identity.provider == "google"
        and identity.external_id == "sub-123"
        and identity.email == "karen@example.test"
    )
    with with_org(org.id):
        link = ConnectorLink.objects.get(user=user)
        assert link.identity_id == identity.id and link.status == "active"
        assert SyncScope.objects.filter(link=link, kind="google_changes").exists()
    assert c.get(f"/o/{org.slug}/connectors/").status_code == 200


def test_oauth_state_from_another_session_is_rejected(monkeypatch, settings):
    settings.GOOGLE_CLIENT_ID = "client"
    org, user, other = make_org("acme"), make_user(), make_user()
    make_membership(org, user)
    make_membership(org, other)
    monkeypatch.setattr(
        oauth,
        "google_authorization_url",
        lambda request, scopes, state: f"https://x/?state={state}",
    )
    c1 = Client()
    c1.force_login(user)
    state = c1.get(f"/connectors/google/start/{org.slug}/")["Location"].split("state=", 1)[1]
    c2 = Client()
    c2.force_login(other)
    assert c2.get(f"/connectors/google/callback/?code=abc&state={state}").status_code == 403


class _FakeClient:
    def bootstrap_cursor(self, scope):
        return "1"

    def list_all(self, scope):
        from datetime import UTC, datetime

        from connectors.providers.base import Page

        yield Page([], datetime.now(UTC), done_cursor="")

    def list_changes(self, scope, cursor):
        from datetime import UTC, datetime

        from connectors.providers.base import Page

        yield Page([], datetime.now(UTC), done_cursor=cursor)

    def fetch(self, sd):
        raise NotImplementedError
