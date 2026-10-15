"""Organization isolation under RLS, the self-membership policy, and the
runtime role's missing privileges."""

import psycopg
import pytest
from django.db import connection

from infra.api import with_actor, with_org
from organizations.api import memberships_for_user
from organizations.models import Membership

from .factories import make_membership, make_org, make_user

pytestmark = pytest.mark.django_db(transaction=True)


def test_membership_visible_only_inside_its_organization():
    org_a, org_b = make_org("alpha"), make_org("beta")
    ua, ub = make_user(), make_user()
    make_membership(org_a, ua)
    make_membership(org_b, ub)

    with with_org(org_a.id):
        assert list(Membership.objects.values_list("user_id", flat=True)) == [ua.pk]
    with with_org(org_b.id):
        assert list(Membership.objects.values_list("user_id", flat=True)) == [ub.pk]
    # No scope: nothing.
    assert Membership.objects.count() == 0


def test_write_into_foreign_organization_is_rejected():
    org_a, org_b = make_org(), make_org()
    user = make_user()
    with pytest.raises(Exception, match="row-level security"), with_org(org_a.id):
        Membership.objects.create(organization=org_b, user=user)


def test_self_membership_lookup_without_organization_scope():
    org_a, org_b = make_org(), make_org()
    me, other = make_user(), make_user()
    make_membership(org_a, me)
    make_membership(org_b, me)
    make_membership(org_b, other)

    mine = memberships_for_user(me)
    assert sorted(m.organization_id for m in mine) == sorted([org_a.id, org_b.id])
    with with_actor(me.pk):
        assert not Membership.objects.filter(user=other).exists()


def test_app_role_self_policy_and_denied_privileges(app_role_connection):
    org = make_org()
    me, other = make_user(), make_user()
    make_membership(org, me)
    make_membership(org, other)

    with app_role_connection.cursor() as cur:
        cur.execute("SELECT count(*) FROM organizations_membership")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT set_config('app.actor_id', %s, false)", [str(me.pk)])
        cur.execute("SELECT user_id FROM organizations_membership")
        assert [r[0] for r in cur.fetchall()] == [me.pk]
        # The self policy is SELECT-only: an UPDATE sees no rows.
        cur.execute("UPDATE organizations_membership SET role = 'admin' WHERE user_id = %s", [str(me.pk)])
        assert cur.rowcount == 0
        cur.execute("SELECT set_config('app.actor_id', '', false)")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("ALTER TABLE organizations_membership DISABLE ROW LEVEL SECURITY")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("TRUNCATE organizations_membership")
        cur.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert cur.fetchone()[0] is False


def test_runtime_role_name_is_enforcing():
    with connection.cursor() as cur:
        cur.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert cur.fetchone()[0] is False
