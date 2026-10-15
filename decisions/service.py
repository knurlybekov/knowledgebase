"""Decision records: candidate creation from visible evidence, the steward
workflow, evidence-bound visibility, the chronological timeline, and the purge
hook (D6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from infra.api import record_access, with_org
from knowledge.api import versions_visible, visible_versions
from organizations.api import Membership, Principal, require_role
from retrieval.api import chunks_for

from .models import DecisionEvidence, DecisionRecord, Project

log = logging.getLogger(__name__)

STAGES = ["problem", "option", "decision", "rationale", "change", "status"]
TRANSITIONS = {
    DecisionRecord.STATUS_CANDIDATE: {DecisionRecord.STATUS_DRAFT},
    DecisionRecord.STATUS_DRAFT: {DecisionRecord.STATUS_VERIFIED, DecisionRecord.STATUS_CANDIDATE},
    DecisionRecord.STATUS_VERIFIED: {DecisionRecord.STATUS_SUPERSEDED},
}


@dataclass
class EvidenceInput:
    chunk_id: str
    role: str = "decision"
    excerpt: str | None = None


@dataclass
class Timeline:
    stages: dict = field(
        default_factory=dict
    )  # stage -> {"state": "documented"|"unknown", "items": [...]}
    supersedes: list[str] = field(default_factory=list)
    superseded_by: str | None = None


def create_candidate(
    principal: Principal,
    *,
    title: str,
    evidence: list[EvidenceInput],
    origin: str,
    description: str | None = None,
    rationale: str | None = None,
    alternatives=None,
    participants=None,
    decision_date=None,
    approval_status: str = DecisionRecord.APPROVAL_UNKNOWN,
    project: Project | None = None,
) -> DecisionRecord:
    """Create a candidate from chunks the principal can see. Never verified here."""
    if not title.strip():
        raise ValidationError("A title is required.")
    if not evidence:
        raise ValidationError("At least one evidence passage is required.")
    chunks = chunks_for(principal, [e.chunk_id for e in evidence])
    by_id = {str(c.id): c for c in chunks}
    missing = [e.chunk_id for e in evidence if e.chunk_id not in by_id]
    if missing:
        raise PermissionDenied("Some evidence passages are not visible to you.")
    with with_org(principal.organization_id, principal.user_id):
        record = DecisionRecord.objects.create(
            organization_id=principal.organization_id,
            project=project,
            title=title.strip()[:300],
            description=description,
            recorded_rationale=rationale,
            alternatives=alternatives,
            participants=participants,
            decision_date=decision_date,
            approval_status=approval_status,
            origin=origin,
            created_by=principal.user,
            status=DecisionRecord.STATUS_CANDIDATE,
        )
        for item in evidence:
            chunk = by_id[item.chunk_id]
            role = item.role if item.role in STAGES else "decision"
            DecisionEvidence.objects.create(
                organization_id=principal.organization_id,
                record=record,
                document_id=chunk.document_id,
                version=chunk.version,
                version_label=chunk.version.version_label,
                position=chunk.position,
                chunk=chunk,
                role=role,
                excerpt=(item.excerpt or chunk.text)[:1200],
            )
        record_access(
            principal.organization_id,
            principal.user,
            "investigation" if origin == "agent" else "document_read",
            object_type="decision",
            object_id=record.id,
            meta={"action": "create_candidate", "origin": origin},
            investigation_id=getattr(principal.investigation, "id", None),
        )
    return record


def transition(
    principal: Principal,
    record: DecisionRecord,
    to_status: str,
    *,
    superseded_by: DecisionRecord | None = None,
) -> DecisionRecord:
    """Steward-only state machine: candidate -> draft -> verified -> superseded."""
    require_role(principal, Membership.ROLE_STEWARD, Membership.ROLE_ADMIN)
    allowed = TRANSITIONS.get(record.status, set())
    if to_status not in allowed:
        raise ValidationError(f"Cannot move a {record.status} record to {to_status}.")
    with with_org(principal.organization_id, principal.user_id):
        if not record_visible(principal, record):
            raise PermissionDenied("You cannot see all evidence of this record.")
        if to_status == DecisionRecord.STATUS_VERIFIED:
            record.verified_by = principal.user
            record.verified_at = timezone.now()
        if to_status == DecisionRecord.STATUS_SUPERSEDED:
            if superseded_by is None:
                raise ValidationError("A superseding record is required.")
            record.superseded_by = superseded_by
        record.status = to_status
        record.save()
        record_access(
            principal.organization_id,
            principal.user,
            "document_read",
            object_type="decision",
            object_id=record.id,
            meta={"action": f"transition:{to_status}"},
        )
    return record


def _evidence_version_ids(record_ids):
    out: dict = {}
    for rid, vid in DecisionEvidence.objects.filter(record_id__in=record_ids).values_list(
        "record_id", "version_id"
    ):
        out.setdefault(rid, set()).add(vid)
    return out


def record_visible(principal: Principal, record: DecisionRecord) -> bool:
    if record.content_state != DecisionRecord.CONTENT_PRESENT:
        return False
    versions = _evidence_version_ids([record.id]).get(record.id, set())
    return versions_visible(principal, versions)


def visible_records(
    principal: Principal, *, statuses=None, limit: int = 200
) -> list[DecisionRecord]:
    """Evidence-bound: every evidence revision must be visible to the reader."""
    qs = DecisionRecord.objects.filter(
        organization_id=principal.organization_id, content_state=DecisionRecord.CONTENT_PRESENT
    )
    if statuses:
        qs = qs.filter(status__in=list(statuses))
    records = list(qs.select_related("project", "superseded_by")[:limit])
    versions = _evidence_version_ids([r.id for r in records])
    visible = set(visible_versions(principal).values_list("id", flat=True))
    return [r for r in records if versions.get(r.id, set()) <= visible and versions.get(r.id)]


def timeline(record: DecisionRecord) -> Timeline:
    """Original problem, options, decision, rationale, changes, current status.
    A stage with no evidence is labeled unknown; evidence stays the source of truth."""
    tl = Timeline()
    items = list(
        DecisionEvidence.objects.filter(record=record)
        .select_related("document")
        .order_by("created_at")
    )
    for stage in STAGES:
        hits = [
            {
                "evidence_id": e.id,
                "document_id": str(e.document_id),
                "title": e.document.title,
                "version_label": e.version_label,
                "position": e.position,
                "excerpt": e.excerpt,
            }
            for e in items
            if e.role == stage
        ]
        tl.stages[stage] = {"state": "documented" if hits else "unknown", "items": hits}
    if record.recorded_rationale and tl.stages["rationale"]["state"] == "unknown":
        tl.stages["rationale"] = {
            "state": "recorded",
            "items": [{"excerpt": record.recorded_rationale}],
        }
    tl.supersedes = [str(r.id) for r in record.supersedes.all()]
    tl.superseded_by = str(record.superseded_by_id) if record.superseded_by_id else None
    return tl


def pending_approval_count(org_id) -> int:
    return DecisionRecord.objects.filter(
        organization_id=org_id,
        status__in=[DecisionRecord.STATUS_CANDIDATE, DecisionRecord.STATUS_DRAFT],
        content_state=DecisionRecord.CONTENT_PRESENT,
    ).count()


def purge_records_for_version(version) -> int:
    """Purge hook (D6): records with evidence on this revision lose their prose;
    evidence rows keep document, version label and position as tombstones."""
    record_ids = list(
        DecisionEvidence.objects.filter(version=version)
        .values_list("record_id", flat=True)
        .distinct()
    )
    if not record_ids:
        return 0
    DecisionEvidence.objects.filter(version=version).update(chunk=None, excerpt=None)
    return DecisionRecord.objects.filter(id__in=record_ids).update(
        description=None,
        recorded_rationale=None,
        alternatives=None,
        participants=None,
        content_state=DecisionRecord.CONTENT_PURGED,
    )
