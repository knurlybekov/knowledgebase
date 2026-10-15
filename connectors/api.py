"""Public surface of the connectors app."""

from django.utils import timezone

from infra.api import with_org

from .crypto import decrypt_token, encrypt_token
from .models import ChangeInbox, ConnectorLink, SyncLease, SyncRun, SyncScope


def create_link(
    organization,
    user,
    *,
    provider: str,
    external_account_id: str,
    email: str,
    refresh_token: str,
    oauth_scopes: list[str] | None = None,
    identity=None,
) -> ConnectorLink:
    with with_org(organization.id, user.pk):
        link, _ = ConnectorLink.objects.update_or_create(
            organization=organization,
            user=user,
            provider=provider,
            external_account_id=external_account_id,
            defaults={
                "email": (email or "").lower(),
                "refresh_token_encrypted": encrypt_token(refresh_token),
                "oauth_scopes": oauth_scopes or [],
                "identity": identity,
                "status": ConnectorLink.STATUS_ACTIVE,
                "status_changed_at": timezone.now(),
                "last_error_code": "",
            },
        )
        return link


def ensure_scope(
    link: ConnectorLink, *, kind: str, external_id: str = "", display_name: str = ""
) -> SyncScope:
    with with_org(link.organization_id):
        scope, _ = SyncScope.objects.get_or_create(
            link=link,
            kind=kind,
            external_id=external_id,
            defaults={"organization_id": link.organization_id, "display_name": display_name},
        )
        SyncLease.objects.get_or_create(
            scope=scope, defaults={"organization_id": link.organization_id}
        )
        return scope


def set_link_status(link: ConnectorLink, status: str, error_code: str = "") -> None:
    """Status changes invalidate grants through `valid_grants` (link.status)."""
    with with_org(link.organization_id):
        ConnectorLink.objects.filter(id=link.id).update(
            status=status, status_changed_at=timezone.now(), last_error_code=error_code[:64]
        )
    link.status = status


def revoke_user_links(organization, user) -> int:
    """Offboarding hook: every link this member owns is revoked and its grants
    are removed. Runs inside the organization scope opened by remove_member."""
    from knowledge.api import revoke_link_grants

    count = 0
    for link in ConnectorLink.objects.filter(organization=organization, user=user).exclude(
        status=ConnectorLink.STATUS_REVOKED
    ):
        link.status = ConnectorLink.STATUS_REVOKED
        link.status_changed_at = timezone.now()
        link.save(update_fields=["status", "status_changed_at"])
        revoke_link_grants(link, "link_revoked")
        count += 1
    return count


def revoke_link(link: ConnectorLink) -> None:
    """User-initiated unlink."""
    from knowledge.api import revoke_link_grants

    set_link_status(link, ConnectorLink.STATUS_REVOKED, "unlinked")
    revoke_link_grants(link, "link_revoked")


__all__ = [
    "ChangeInbox",
    "ConnectorLink",
    "SyncLease",
    "SyncRun",
    "SyncScope",
    "create_link",
    "decrypt_token",
    "encrypt_token",
    "ensure_scope",
    "revoke_link",
    "revoke_user_links",
    "set_link_status",
]
