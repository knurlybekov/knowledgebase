"""Project-wide pytest fixtures.

The suite connects as kb_migrator (DATABASE_URL in .env), which owns the schema
and is still bound by FORCE ROW LEVEL SECURITY. Authorization-path tests also
open a raw psycopg connection as the runtime role kb_app through
`app_role_connection`; `django_db_setup` grants that role access to every table
in the freshly created test database.
"""

import os

import psycopg
import pytest
from django.conf import settings
from django.db import connection


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        with connection.cursor() as cur:
            cur.execute("GRANT USAGE ON SCHEMA public TO kb_app")
            cur.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kb_app"
            )
            cur.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kb_app")
            # Only the trigger writes the audit log (infra migration 0001).
            cur.execute("REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON infra_auditlog FROM kb_app")


def _app_role_dsn() -> str:
    db = settings.DATABASES["default"]
    password = os.environ.get("KB_APP_PASSWORD", "kb_app")
    return (
        f"host={db['HOST']} port={db['PORT']} dbname={connection.settings_dict['NAME']} "
        f"user=kb_app password={password}"
    )


@pytest.fixture
def app_role_connection(db):
    """A raw autocommit psycopg connection as the runtime role kb_app, bound to the
    test database. Rows written by the test through Django are visible to it only
    after commit, so use it with `transaction=True` tests or for catalog checks."""
    with psycopg.connect(_app_role_dsn(), autocommit=True) as conn:
        yield conn
