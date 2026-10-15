"""Every table with an `organization` relation has FORCE RLS; every table
without RLS is on the explicit allow-list."""

import pytest
from django.apps import apps
from django.db import connection

NO_RLS_TABLES = {
    # Resolved at the request edge before the GUC exists.
    "organizations_organization",
    # Trigger-written, read by admins; filtered by organization_id in queries.
    "infra_auditlog",
    # Identity-level rows, not organization-scoped.
    "accounts_user",
    "accounts_user_groups",
    "accounts_user_user_permissions",
    "accounts_useridentity",
    # Global auth table looked up by token hash before the scope is known (plan: MCP step 1).
    "investigations_capabilitytoken",
    # Django internals.
    "auth_group",
    "auth_permission",
    "auth_group_permissions",
    "django_session",
    "django_admin_log",
    "django_content_type",
    "django_migrations",
}


def _org_scoped_tables():
    out = []
    for model in apps.get_models():
        names = {f.name for f in model._meta.get_fields() if hasattr(f, "name")}
        if "organization" in names:
            out.append(model._meta.db_table)
    return out


@pytest.mark.django_db
def test_every_org_scoped_table_has_force_rls():
    tables = _org_scoped_tables()
    assert tables
    failures = []
    with connection.cursor() as cur:
        for table in tables:
            cur.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s AND relkind = 'r'",
                [table],
            )
            row = cur.fetchone()
            if row is None:
                failures.append(f"{table}: missing")
                continue
            if not row[0]:
                failures.append(f"{table}: ENABLE ROW LEVEL SECURITY missing")
            if not row[1]:
                failures.append(f"{table}: FORCE ROW LEVEL SECURITY missing")
    assert not failures, "\n".join(failures)


@pytest.mark.django_db
def test_no_unexpected_table_lacks_rls():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relname FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace AND NOT relrowsecurity ORDER BY relname"
        )
        unprotected = {row[0] for row in cur.fetchall()}
    unexpected = unprotected - NO_RLS_TABLES
    assert not unexpected, "Tables without RLS and not on the allow-list: " + ", ".join(sorted(unexpected))
