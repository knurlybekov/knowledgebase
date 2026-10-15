"""Decision history pages and the steward workflow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from infra.api import with_org
from organizations.api import Membership, org_path

from .models import DecisionRecord
from .service import (
    EvidenceInput,
    create_candidate,
    record_visible,
    timeline,
    transition,
    visible_records,
)


def _is_steward(request) -> bool:
    return request.membership.role in (Membership.ROLE_STEWARD, Membership.ROLE_ADMIN)


@login_required
def decisions_list(request):
    with with_org(request.organization.id, request.user.pk):
        records = visible_records(request.principal)
    pending = [
        r
        for r in records
        if r.status in (DecisionRecord.STATUS_CANDIDATE, DecisionRecord.STATUS_DRAFT)
    ]
    return render(
        request,
        "decisions/list.html",
        {"records": records, "pending": pending, "is_steward": _is_steward(request)},
    )


@login_required
def decision_detail(request, record_id):
    with with_org(request.organization.id, request.user.pk):
        record = (
            DecisionRecord.objects.filter(id=record_id, organization_id=request.organization.id)
            .select_related("superseded_by")
            .first()
        )
        if record is None or not record_visible(request.principal, record):
            raise Http404("Unknown decision")
        tl = timeline(record)
        candidates = (
            list(visible_records(request.principal, statuses=[DecisionRecord.STATUS_VERIFIED]))
            if _is_steward(request)
            else []
        )
    return render(
        request,
        "decisions/detail.html",
        {
            "record": record,
            "timeline": tl,
            "stages": list(tl.stages.items()),
            "is_steward": _is_steward(request),
            "superseders": [c for c in candidates if c.id != record.id],
        },
    )


@login_required
@require_POST
def decision_transition(request, record_id):
    with with_org(request.organization.id, request.user.pk):
        record = DecisionRecord.objects.filter(
            id=record_id, organization_id=request.organization.id
        ).first()
        if record is None:
            raise Http404("Unknown decision")
        superseder = None
        if request.POST.get("superseded_by"):
            superseder = DecisionRecord.objects.filter(
                id=request.POST["superseded_by"], organization_id=request.organization.id
            ).first()
        try:
            transition(
                request.principal, record, request.POST.get("to", ""), superseded_by=superseder
            )
            messages.success(request, f"Record moved to {record.status}.")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(getattr(exc, "message", exc)))
    return redirect(org_path(request.organization, f"/decisions/{record.id}/"))


@login_required
@require_POST
def decision_create(request):
    """Save a candidate from search citations (chunk ids the user just saw)."""
    title = (request.POST.get("title") or "").strip()
    chunk_ids = request.POST.getlist("chunk_id")
    roles = request.POST.getlist("role")
    evidence = [
        EvidenceInput(chunk_id=c, role=(roles[i] if i < len(roles) else "decision"))
        for i, c in enumerate(chunk_ids)
    ]
    try:
        record = create_candidate(
            request.principal,
            title=title,
            evidence=evidence,
            origin=DecisionRecord.ORIGIN_USER,
            description=(request.POST.get("description") or None),
        )
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(getattr(exc, "message", exc)))
        return redirect(org_path(request.organization, "/decisions/"))
    messages.success(request, "Candidate decision record created. A steward can now review it.")
    return redirect(org_path(request.organization, f"/decisions/{record.id}/"))
