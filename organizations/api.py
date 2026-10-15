"""Public surface of the organizations app."""

from django.core.exceptions import PermissionDenied

from infra.api import with_actor, with_org

from .middleware import OrganizationContextMiddleware
from .models import Membership, Organization
from .principal import Principal


def org_path(organization, path: str) -> str:
    """Re-attach the `/o/<slug>` prefix that the middleware strips."""
    if organization is None:
        return path
    return f"/o/{organization.slug}{path}"


def memberships_for_user(user) -> list[Membership]:
    """Active memberships of this user, readable with no organization selected
    through the `membership_self` policy (actor GUC only)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return []
    with with_actor(user.pk):
        return list(
            Membership.objects.filter(user=user, status=Membership.STATUS_ACTIVE)
            .select_related("organization")
            .order_by("organization__name")
        )


def require_role(principal: Principal, *roles: str) -> None:
    if principal is None or not principal.has_role(*roles):
        raise PermissionDenied("This action needs the role: " + ", ".join(roles))


def remove_member(organization, user, *, actor) -> None:
    """Offboarding: mark the membership removed and revoke everything it
    produced (connector grants, capability tokens, running investigations) in
    one transaction. The revocation hooks are registered by the owning apps."""
    from django.utils import timezone

    require_role(actor, Membership.ROLE_ADMIN)
    with with_org(organization.id, actor.user_id):
        membership = Membership.objects.filter(organization=organization, user=user).first()
        if membership is None:
            return
        membership.status = Membership.STATUS_REMOVED
        membership.removed_at = timezone.now()
        membership.save(update_fields=["status", "removed_at"])
        for hook in _offboarding_hooks:
            hook(organization, user)


def offboard_user_everywhere(user) -> int:
    """User deactivation: run the offboarding hooks in every organization the
    user belongs to (links revoked, investigations cancelled). Memberships stay
    as records; an inactive user is invisible to every authorization predicate."""
    count = 0
    org_ids = [m.organization_id for m in Membership.all_for_user(user)]
    for org_id in org_ids:
        with with_org(org_id, user.pk):
            organization = Organization.objects.get(id=org_id)
            for hook in _offboarding_hooks:
                hook(organization, user)
            count += 1
    return count


_offboarding_hooks: list = []


def register_offboarding_hook(fn) -> None:
    """Apps register `fn(organization, user)` to revoke what a member owned."""
    _offboarding_hooks.append(fn)


__all__ = [
    "Membership",
    "Organization",
    "OrganizationContextMiddleware",
    "Principal",
    "memberships_for_user",
    "offboard_user_everywhere",
    "org_path",
    "register_offboarding_hook",
    "remove_member",
    "require_role",
    "with_org",
]
