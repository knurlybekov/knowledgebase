"""Refuse to serve on a database role that bypasses row-level security."""

from django.core.exceptions import ImproperlyConfigured
from django.db import connection

_verified: set[str] = set()


def _role_bypasses_rls() -> bool:
    with connection.cursor() as cur:
        cur.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        row = cur.fetchone()
    return bool(row and row[0])


def ensure_rls_enforcing_role() -> None:
    """Raise ImproperlyConfigured when the connection's role is SUPERUSER or
    BYPASSRLS. Checked once per connection alias per process."""
    alias = connection.alias
    if alias in _verified:
        return
    if _role_bypasses_rls():
        raise ImproperlyConfigured(
            "Refusing to serve: the database role bypasses row-level security. "
            "Connect as kb_app (runtime) or kb_migrator (migrations and tests)."
        )
    _verified.add(alias)
