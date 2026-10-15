"""Audit trigger: allowlisted columns only, append-only log, no temp-table shadowing."""

import psycopg
import pytest

from infra.api import with_org
from infra.models import AuditLog
from organizations.models import Membership
from organizations.tests.factories import make_membership, make_org, make_user

pytestmark = pytest.mark.django_db(transaction=True)


def test_trigger_logs_allowlisted_columns_only():
    org, user = make_org(), make_user()
    membership = make_membership(org, user)
    row = AuditLog.objects.filter(
        target_table="organizations_membership", target_id=membership.id
    ).get()
    assert row.action == "insert"
    assert row.organization_id == org.id
    assert row.actor_id == user.pk
    assert set(row.diff) <= {"id", "organization_id", "user_id", "role", "status", "removed_at"}
    assert "created_at" not in row.diff


def test_audit_log_is_append_only():
    org, user = make_org(), make_user()
    make_membership(org, user)
    from django.db import connection

    with pytest.raises(Exception, match="append-only"):
        with connection.cursor() as cur:
            cur.execute("DELETE FROM infra_auditlog")


def test_temp_table_cannot_shadow_audit_log(app_role_connection):
    org, user = make_org(), make_user()
    with app_role_connection.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE infra_auditlog (id uuid, organization_id uuid, actor_id uuid, request_id text, action text, target_table text, target_id uuid, diff jsonb, at timestamptz)"
        )
        cur.execute("SELECT set_config('app.org_id', %s, false)", [str(org.id)])
        cur.execute("SELECT set_config('app.actor_id', %s, false)", [str(user.pk)])
        cur.execute(
            "INSERT INTO organizations_membership (id, organization_id, user_id, role, status, created_at) "
            "VALUES (gen_random_uuid(), %s, %s, 'member', 'active', now())",
            [str(org.id), str(user.pk)],
        )
        cur.execute("SELECT count(*) FROM pg_temp.infra_auditlog")
        assert cur.fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(
                "INSERT INTO public.infra_auditlog (id, action, target_table, diff, at) VALUES (gen_random_uuid(), 'x', 'y', '{}', now())"
            )
    with with_org(org.id):
        assert Membership.objects.filter(user=user).exists()
    assert AuditLog.objects.filter(
        target_table="organizations_membership", actor_id=user.pk
    ).exists()
