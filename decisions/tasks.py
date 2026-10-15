"""Decision extraction task: enqueued after a publish when
DECISION_EXTRACTION_ENABLED is on. Runs as the link owner, so candidates are
proposed only from passages that owner can see."""

from celery import shared_task
from django.conf import settings

from infra.api import OrgAwareTask, with_org
from organizations.api import Membership, Organization, Principal


def on_publish(version, link) -> None:
    if not getattr(settings, "DECISION_EXTRACTION_ENABLED", False):
        return
    extract_for_version.delay(str(version.organization_id), str(version.id), str(link.user_id))


@shared_task(base=OrgAwareTask, name="decisions.tasks.extract_for_version", bind=True)
def extract_for_version(self, org_id, version_id, user_id) -> int:
    from knowledge.api import visible_versions

    from .extraction import extract_candidates_for_version

    with with_org(org_id, user_id):
        organization = Organization.objects.get(id=org_id)
        membership = (
            Membership.objects.filter(
                organization=organization, user_id=user_id, status=Membership.STATUS_ACTIVE
            )
            .select_related("user")
            .first()
        )
        if membership is None:
            return 0
        principal = Principal(user=membership.user, organization=organization, role=membership.role)
        # Only a revision the owner can still see goes to the model.
        version = visible_versions(principal).filter(id=version_id).first()
    if version is None:
        return 0
    return len(extract_candidates_for_version(principal, version))
