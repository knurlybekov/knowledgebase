"""Authorization predicates (PLAN.md "Authorization rules"). One implementation
for retrieval, answers, MCP tools and the UI."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from organizations.api import Membership

from .models import AccessGrant, Document, DocumentVersion


def freshness_cutoff():
    return timezone.now() - timedelta(seconds=settings.PERMISSION_FRESHNESS_MAX_AGE_S)


def membership_active(principal) -> bool:
    user = principal.user
    if user is None or not getattr(user, "is_active", False):
        return False
    return Membership.objects.filter(
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        status=Membership.STATUS_ACTIVE,
    ).exists()


def valid_grants(principal):
    """Grants that authorize `principal.user` right now. Explicit organization
    predicate first; RLS is the second layer."""
    if not membership_active(principal):
        return AccessGrant.objects.none()
    return AccessGrant.objects.filter(
        organization_id=principal.organization_id,
        revoked_at__isnull=True,
        last_revalidated_at__gte=freshness_cutoff(),
        link__status="active",
        link__user_id=principal.user_id,
        link__user__is_active=True,
        link__organization_id=principal.organization_id,
    )


def visible_versions(principal):
    """Document versions with content that `principal` may read."""
    return DocumentVersion.objects.filter(
        organization_id=principal.organization_id,
        content_state=DocumentVersion.CONTENT_PRESENT,
        document__status=Document.STATUS_ACTIVE,
        id__in=valid_grants(principal).values("version_id"),
    )


def visible_documents(principal):
    return Document.objects.filter(
        organization_id=principal.organization_id,
        status=Document.STATUS_ACTIVE,
        id__in=visible_versions(principal).values("document_id"),
    )


def versions_visible(principal, version_ids) -> bool:
    """True only when every id in `version_ids` is visible to `principal`."""
    ids = {str(v) for v in version_ids}
    if not ids:
        return True
    visible = {
        str(v) for v in visible_versions(principal).filter(id__in=ids).values_list("id", flat=True)
    }
    return visible == ids
