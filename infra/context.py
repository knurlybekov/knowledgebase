"""Per-request and per-task context in ContextVars.

Read by the JSON logger and by the RLS helpers in infra.db.
"""

import contextvars

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
org_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("org_id", default=None)
actor_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("actor_id", default=None)
investigation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "investigation_id", default=None
)


def get_request_id() -> str | None:
    return request_id_var.get()


def get_org_id() -> str | None:
    return org_id_var.get()


def get_actor_id() -> str | None:
    return actor_id_var.get()


def get_investigation_id() -> str | None:
    return investigation_id_var.get()
