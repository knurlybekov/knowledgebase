from celery import shared_task

from infra.api import OrgAwareTask
from organizations.api import Organization

from . import service


@shared_task(base=OrgAwareTask, name="investigations.tasks.run_investigation", bind=True)
def run_investigation(self, org_id, investigation_id) -> str:
    return service.execute(org_id, investigation_id)


@shared_task(name="investigations.tasks.reap_investigations")
def reap_investigations() -> dict:
    totals = {"requeued": 0, "recovered": 0, "interrupted": 0}
    for org_id in Organization.objects.values_list("id", flat=True):
        for key, value in service.reap(org_id).items():
            totals[key] += value
    return totals


@shared_task(name="investigations.tasks.erase_runner_records")
def erase_runner_records(run_keys: list[str]) -> int:
    client = service.RunnerClient()
    count = 0
    for key in run_keys:
        try:
            client.cancel(key)
        except service.RunnerError:
            pass
        try:
            client.delete(key)
            count += 1
        except service.RunnerError:
            continue
    return count


@shared_task(name="investigations.tasks.cancel_runner_runs")
def cancel_runner_runs(run_keys: list[str]) -> int:
    client = service.RunnerClient()
    count = 0
    for key in run_keys:
        try:
            client.cancel(key)
            count += 1
        except service.RunnerError:
            continue
    return count
