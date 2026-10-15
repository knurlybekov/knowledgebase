"""Investigation pages: list, detail with HTMX status polling, cancel."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from infra.api import with_org
from organizations.api import org_path
from web.api import rate_limited

from .api import Investigation, cancel_investigation, get_investigation, start_investigation


@login_required
def investigations_list(request):
    with with_org(request.organization.id, request.user.pk):
        rows = list(Investigation.objects.filter(user=request.user).order_by("-created_at")[:50])
    return render(
        request,
        "investigations/list.html",
        {"rows": rows, "hermes_enabled": settings.HERMES_ENABLED},
    )


@login_required
@require_POST
def investigations_start(request):
    if not settings.HERMES_ENABLED:
        return HttpResponse("Deep Investigation is disabled", status=409)
    if rate_limited(request, "investigation", settings.RATE_LIMIT_INVESTIGATION_PER_HOUR, 3600):
        return HttpResponse("Too many investigations. Try again later.", status=429)
    question = (request.POST.get("q") or "").strip()
    if not question or len(question) > 2000:
        return HttpResponse("A question of at most 2000 characters is required", status=400)
    row = start_investigation(request.principal, question)
    return redirect(org_path(request.organization, f"/investigations/{row.id}/"))


@login_required
def investigation_detail(request, investigation_id):
    data = get_investigation(request.principal, investigation_id)
    if data is None:
        raise Http404("Unknown investigation")
    template = (
        "investigations/_status.html"
        if request.headers.get("HX-Request")
        else "investigations/detail.html"
    )
    return render(
        request, template, {"inv": data, "terminal": data["status"] in Investigation.TERMINAL}
    )


@login_required
def investigation_json(request, investigation_id):
    data = get_investigation(request.principal, investigation_id)
    if data is None:
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(data)


@login_required
@require_POST
def investigation_cancel(request, investigation_id):
    cancelled = cancel_investigation(request.principal, investigation_id)
    if request.headers.get("HX-Request"):
        data = get_investigation(request.principal, investigation_id)
        return render(request, "investigations/_status.html", {"inv": data, "terminal": True})
    return (
        redirect(org_path(request.organization, f"/investigations/{investigation_id}/"))
        if cancelled
        else HttpResponse(status=409)
    )
