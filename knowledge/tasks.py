"""Periodic knowledge tasks."""

from celery import shared_task

from organizations.api import Organization

from .pipeline import expire_stale_grants


@shared_task(name="knowledge.tasks.expiration_sweep")
def expiration_sweep() -> int:
    total = 0
    for org_id in Organization.objects.values_list("id", flat=True):
        total += expire_stale_grants(org_id)
    return total
