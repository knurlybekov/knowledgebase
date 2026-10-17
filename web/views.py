"""Shell views: health, metrics, organization picker and dashboard."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from answers.api import answer_question, read_answer
from connectors.api import ConnectorLink, SyncRun
from decisions.api import pending_approval_count
from infra.api import with_org
from investigations.api import Investigation
from knowledge.api import visible_documents
from organizations.api import memberships_for_user, org_path

from .api import rate_limited
from .routing import suggest_mode


def healthz(request):
    return JsonResponse({"status": "ok"})


def metrics(request):
    token = settings.METRICS_TOKEN
    auth = request.headers.get("Authorization", "")
    if not token or auth != f"Bearer {token}":
        return HttpResponseForbidden("metrics token required")
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)


@login_required
def home(request):
    if request.organization is not None:
        return render(request, "web/dashboard.html", _dashboard_context(request))
    memberships = memberships_for_user(request.user)
    if len(memberships) == 1:
        return redirect(org_path(memberships[0].organization, "/"))
    return render(request, "web/picker.html", {"memberships": memberships})


def _dashboard_context(request) -> dict:
    """Read-only data for the home page: the member's recent investigations,
    their linked accounts with the last sync, and the steward's pending count."""
    organization = request.organization
    with with_org(organization.id, request.user.pk):
        recent = list(Investigation.objects.filter(user=request.user).order_by("-created_at")[:6])
        links = list(
            ConnectorLink.objects.filter(user=request.user)
            .exclude(status=ConnectorLink.STATUS_REVOKED)
            .order_by("provider")
        )
        runs = {
            link.id: SyncRun.objects.filter(link=link).order_by("-started_at").first()
            for link in links
        }
        documents = visible_documents(request.principal).count()
        pending = (
            pending_approval_count(organization.id)
            if request.membership.role in ("steward", "admin")
            else None
        )
    return {
        "recent": recent,
        "links": links,
        "runs": runs,
        "documents": documents,
        "pending": pending,
        "hermes_enabled": settings.HERMES_ENABLED,
    }


def _number_citations(answer) -> None:
    """Presentation only: give each retrieved passage a number and list the
    numbers each claim cites, so the template can draw matching chips."""
    index = {c.chunk_id: n for n, c in enumerate(answer.citations, start=1)}
    for claim in answer.claims:
        refs = sorted({index[c["chunk_id"]] for c in claim["citations"] if c["chunk_id"] in index})
        claim["refs"] = refs


@login_required
def placeholder(request):
    return render(request, "web/placeholder.html")


@login_required
def search_page(request):
    """Quick Search runs retrieval plus a grounded answer; Deep Investigation
    hands the question to the investigations app (Sprint 2)."""
    question = (request.GET.get("q") or "").strip()
    mode = request.GET.get("mode") or ""
    source_types = [s for s in request.GET.getlist("source") if s in {"google_drive", "sharepoint"}]
    context = {
        "question": question,
        "mode": mode or (suggest_mode(question) if question else "quick"),
        "suggested": suggest_mode(question) if question else "",
        "source_types": source_types,
        "hermes_enabled": settings.HERMES_ENABLED,
        "answer": None,
    }
    if question and context["mode"] == "quick":
        if rate_limited(request, "search", settings.RATE_LIMIT_SEARCH_PER_MIN, 60):
            return HttpResponse("Too many searches. Try again in a minute.", status=429)
        context["answer"] = answer_question(
            request.principal, question, source_types=source_types or None
        )
    elif question and context["mode"] == "deep":
        if not settings.HERMES_ENABLED:
            context["mode"] = "quick"
            context["deep_disabled"] = True
            context["answer"] = answer_question(
                request.principal, question, source_types=source_types or None
            )
        else:
            from investigations.api import start_investigation

            investigation = start_investigation(request.principal, question)
            return redirect(org_path(request.organization, f"/investigations/{investigation.id}/"))
    if context["answer"] is not None:
        _number_citations(context["answer"])
    return render(request, "web/search.html", context)


@login_required
def answer_detail(request, answer_id):
    result = read_answer(request.principal, answer_id)
    if result is None:
        from django.http import Http404

        raise Http404("Unknown answer")
    _number_citations(result)
    return render(
        request,
        "web/search.html",
        {
            "question": result.question,
            "mode": "quick",
            "answer": result,
            "source_types": [],
            "hermes_enabled": settings.HERMES_ENABLED,
        },
    )
