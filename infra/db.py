"""Organization scope for database work (D5).

`with_org(org_id)` opens a short transaction, sets `app.org_id` and
`app.actor_id` with SET LOCAL, and restores the prior values on exit so nested
scopes behave. Every write to organization-scoped tables happens inside one.
`with_actor(user_id)` sets only the actor, for the pre-organization membership
lookup that the `membership_self` policy permits.
"""

from contextlib import contextmanager

from django.db import connection, transaction

from .context import actor_id_var, get_actor_id, org_id_var
from .rls import ensure_rls_enforcing_role


def set_org_gucs(cursor, org_id, actor_id=None) -> None:
    cursor.execute("SET LOCAL app.org_id = %s;", [str(org_id) if org_id else ""])
    cursor.execute("SET LOCAL app.actor_id = %s;", [str(actor_id) if actor_id else ""])


def _current(cursor, name: str) -> str:
    cursor.execute("SELECT current_setting(%s, true);", [name])
    row = cursor.fetchone()
    return (row[0] if row else "") or ""


@contextmanager
def with_org(org_id, actor_id=None):
    """Enter an organization's RLS scope for the block. Nestable."""
    ensure_rls_enforcing_role()
    actor = actor_id or get_actor_id()
    token = org_id_var.set(str(org_id))
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                prior_org = _current(cur, "app.org_id")
                prior_actor = _current(cur, "app.actor_id")
                set_org_gucs(cur, org_id, actor)
            yield
            # On an exception the atomic block rolls back, and SET LOCAL values
            # roll back with it; the restore is only needed on the success path.
            if not connection.needs_rollback:
                with connection.cursor() as cur:
                    cur.execute("SET LOCAL app.org_id = %s;", [prior_org])
                    cur.execute("SET LOCAL app.actor_id = %s;", [prior_actor])
    finally:
        org_id_var.reset(token)


@contextmanager
def with_actor(user_id):
    """Set only `app.actor_id` for the block: the self-membership lookup."""
    ensure_rls_enforcing_role()
    token = actor_id_var.set(str(user_id))
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                prior = _current(cur, "app.actor_id")
                cur.execute("SET LOCAL app.actor_id = %s;", [str(user_id)])
            yield
            if not connection.needs_rollback:
                with connection.cursor() as cur:
                    cur.execute("SET LOCAL app.actor_id = %s;", [prior])
    finally:
        actor_id_var.reset(token)


def document_lock(cursor, document_id) -> None:
    """Transaction-scoped advisory lock for one document (publish, revoke, purge)."""
    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s));", [str(document_id)])
