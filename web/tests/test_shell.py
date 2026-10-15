import pytest
from django.test import Client

from organizations.tests.factories import make_membership, make_org, make_user

pytestmark = pytest.mark.django_db


def test_healthz():
    assert Client().get("/healthz").status_code == 200


def test_anonymous_is_redirected_to_login():
    org = make_org("acme")
    response = Client().get(f"/o/{org.slug}/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


def test_member_sees_dashboard_and_non_member_is_denied():
    org = make_org("acme")
    member, outsider = make_user(), make_user()
    make_membership(org, member)
    c = Client()
    c.force_login(member)
    assert c.get(f"/o/{org.slug}/").status_code == 200
    c2 = Client()
    c2.force_login(outsider)
    assert c2.get(f"/o/{org.slug}/").status_code == 403


def test_single_membership_redirects_from_home():
    org = make_org("solo")
    user = make_user()
    make_membership(org, user)
    c = Client()
    c.force_login(user)
    response = c.get("/")
    assert response.status_code == 302 and response["Location"] == f"/o/{org.slug}/"


def test_metrics_requires_token():
    c = Client()
    assert c.get("/metrics").status_code == 403
    assert c.get("/metrics", HTTP_AUTHORIZATION="Bearer test-metrics-token").status_code == 200
