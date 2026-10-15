"""Shell views: health, metrics, organization picker and dashboard."""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from organizations.api import memberships_for_user, org_path


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
        return render(request, "web/dashboard.html")
    memberships = memberships_for_user(request.user)
    if len(memberships) == 1:
        return redirect(org_path(memberships[0].organization, "/"))
    return render(request, "web/picker.html", {"memberships": memberships})


@login_required
def placeholder(request):
    return render(request, "web/placeholder.html")
