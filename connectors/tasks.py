"""Celery entry points: the beat scheduler and one sync per scope."""

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from infra.api import OrgAwareTask, metrics, with_org
from organizations.api import Organization

from .clients import client_for
from .models import ConnectorLink, SyncScope
from .sync import sync_scope


@shared_task(name="connectors.tasks.schedule_syncs")
def schedule_syncs() -> int:
    """Enqueue a sync for every active scope that is due."""
    due_before = timezone.now() - timedelta(seconds=settings.SYNC_INTERVAL_S)
    reconcile_before = timezone.now() - timedelta(seconds=settings.FULL_RECONCILE_INTERVAL_S)
    count = 0
    overdue = 0
    for org_id in Organization.objects.values_list("id", flat=True):
        with with_org(org_id):
            scopes = list(
                SyncScope.objects.filter(link__status=ConnectorLink.STATUS_ACTIVE)
                .filter(models_or_due(due_before))
                .values_list("id", "last_reconcile_at", "bootstrapped")
            )
        for scope_id, last_reconcile_at, bootstrapped in scopes:
            if bootstrapped and (last_reconcile_at is None or last_reconcile_at < reconcile_before):
                overdue += 1
            sync_scope_task.delay(str(org_id), str(scope_id))
            count += 1
    metrics.reconcile_overdue_scopes.set(overdue)
    return count


def models_or_due(due_before):
    from django.db.models import Q

    return Q(last_attempt_at__isnull=True) | Q(last_attempt_at__lt=due_before)


@shared_task(base=OrgAwareTask, name="connectors.tasks.sync_scope_task", bind=True)
def sync_scope_task(self, org_id, scope_id, force_reconcile: bool = False) -> str:
    with with_org(org_id):
        scope = SyncScope.objects.select_related("link").filter(id=scope_id).first()
        if scope is None or scope.link.status != ConnectorLink.STATUS_ACTIVE:
            return "skipped"
        SyncScope.objects.filter(id=scope_id).update(last_attempt_at=timezone.now())
    return sync_scope(scope, client_for(scope.link), force_reconcile=force_reconcile)
