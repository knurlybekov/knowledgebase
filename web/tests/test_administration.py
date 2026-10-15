import pytest
from django.test import Client

from knowledge.tests.helpers import ingest_markdown
from organizations.api import Membership
from organizations.tests.factories import make_membership, make_org, make_user

pytestmark = pytest.mark.django_db(transaction=True)


def test_admin_and_steward_see_administration_member_denied():
    org = make_org("acme")
    admin, steward, member = make_user(), make_user(), make_user()
    make_membership(org, admin, Membership.ROLE_ADMIN)
    make_membership(org, steward, Membership.ROLE_STEWARD)
    make_membership(org, member)
    ingest_markdown(org, member, {"gdrive:a": b"# A\nalpha"})
    for user in (admin, steward):
        c = Client()
        c.force_login(user)
        page = c.get(f"/o/{org.slug}/administration/")
        assert page.status_code == 200
        assert b"Access grants" in page.content and b"1 fresh" in page.content
    c = Client()
    c.force_login(member)
    assert c.get(f"/o/{org.slug}/administration/").status_code == 403
