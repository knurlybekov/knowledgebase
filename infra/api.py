"""Public surface of the infra app."""

from . import metrics
from .context import (
    actor_id_var,
    get_actor_id,
    get_investigation_id,
    get_org_id,
    get_request_id,
    investigation_id_var,
    org_id_var,
    request_id_var,
)
from .db import document_lock, set_org_gucs, with_actor, with_org
from .models import AccessEvent, AuditLog
from .rls import ensure_rls_enforcing_role
from .sql import (
    audit_trigger_reverse_sql,
    audit_trigger_sql,
    composite_fk_sql,
    org_unique_sql,
    rls_policy_reverse_sql,
    rls_policy_sql,
)
from .tasks import OrgAwareTask


def record_access(organization_id, user, kind: str, *, object_type: str = "", object_id: str = "",
                  meta: dict | None = None, investigation_id=None) -> None:
    """Write one AccessEvent inside the current organization scope."""
    AccessEvent.objects.create(
        organization_id=organization_id,
        user=user if getattr(user, "pk", None) else None,
        kind=kind,
        object_type=object_type,
        object_id=str(object_id or ""),
        meta=meta or {},
        request_id=get_request_id() or "",
        investigation_id=investigation_id,
    )


__all__ = [
    "AccessEvent",
    "AuditLog",
    "OrgAwareTask",
    "actor_id_var",
    "audit_trigger_reverse_sql",
    "audit_trigger_sql",
    "composite_fk_sql",
    "document_lock",
    "ensure_rls_enforcing_role",
    "get_actor_id",
    "get_investigation_id",
    "get_org_id",
    "get_request_id",
    "investigation_id_var",
    "metrics",
    "org_id_var",
    "org_unique_sql",
    "record_access",
    "request_id_var",
    "rls_policy_reverse_sql",
    "rls_policy_sql",
    "set_org_gucs",
    "with_actor",
    "with_org",
]
