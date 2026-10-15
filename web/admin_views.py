"""Knowledge Administration: connector health, sync status, inbox backlog,
failures, grant freshness and pending approvals. Admins and stewards only.
Every query carries the explicit organization predicate; RLS is the second layer."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min
from django.shortcuts import render
from django.utils import timezone

from connectors.api import ChangeInbox, ConnectorLink, SyncRun, SyncScope
from knowledge.api import AccessGrant, Document, freshness_cutoff
from organizations.api import Membership, require_role


@login_required
def administration(request):
    require_role(request.principal, Membership.ROLE_ADMIN, Membership.ROLE_STEWARD)
    now = timezone.now()
    org_id = request.organization.id
    links = list(
        ConnectorLink.objects.filter(organization_id=org_id)
        .select_related("user")
        .order_by("user__email", "provider")
    )
    scopes = list(
        SyncScope.objects.filter(organization_id=org_id)
        .select_related("link", "link__user")
        .order_by("link__user__email")
    )
    reconcile_due = now - timedelta(seconds=settings.FULL_RECONCILE_INTERVAL_S)
    for scope in scopes:
        scope.reconcile_overdue = scope.bootstrapped and (
            scope.last_reconcile_at is None or scope.last_reconcile_at < reconcile_due
        )
    inbox = (
        ChangeInbox.objects.filter(organization_id=org_id).values("status").annotate(n=Count("id"))
    )
    inbox_counts = {row["status"]: row["n"] for row in inbox}
    failed_rows = list(
        ChangeInbox.objects.filter(organization_id=org_id, status=ChangeInbox.STATUS_FAILED)
        .select_related("link__user")
        .order_by("-created_at")[:25]
    )
    recent_runs = list(
        SyncRun.objects.filter(organization_id=org_id)
        .select_related("scope", "link__user")
        .order_by("-started_at")[:25]
    )
    grants = AccessGrant.objects.filter(organization_id=org_id, revoked_at__isnull=True)
    oldest = grants.aggregate(oldest=Min("last_revalidated_at"))["oldest"]
    documents = Document.objects.filter(organization_id=org_id)
    stats = {
        "documents_active": documents.filter(status=Document.STATUS_ACTIVE).count(),
        "documents_tombstone": documents.filter(status=Document.STATUS_TOMBSTONE).count(),
        "documents_quarantined": documents.filter(status=Document.STATUS_QUARANTINED).count(),
        "grants_valid": grants.filter(last_revalidated_at__gte=freshness_cutoff()).count(),
        "grants_stale": grants.filter(last_revalidated_at__lt=freshness_cutoff()).count(),
        "oldest_grant_age_hours": round((now - oldest).total_seconds() / 3600, 1)
        if oldest
        else None,
        "freshness_bound_hours": settings.PERMISSION_FRESHNESS_MAX_AGE_S // 3600,
    }
    return render(
        request,
        "web/administration.html",
        {
            "links": links,
            "scopes": scopes,
            "inbox_counts": inbox_counts,
            "failed_rows": failed_rows,
            "recent_runs": recent_runs,
            "stats": stats,
            "pending_approvals": _pending_approvals(org_id),
        },
    )


def _pending_approvals(org_id) -> int:
    try:
        from decisions.api import pending_approval_count
    except ImportError:
        return 0
    return pending_approval_count(org_id)
