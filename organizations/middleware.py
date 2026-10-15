"""Resolve `/o/<slug>/...` to an organization, require an active membership,
set the organization scope for the request, and strip the prefix so the URL
resolver sees organization-free paths (templates re-attach it with org_url).

No request-wide transaction (D5): the GUCs are session-level for the request,
services open short transactions for writes, and external calls run between
them. CONN_MAX_AGE=0 closes the connection at the end; the reset covers pools.
"""

import re

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404

from .models import Membership, Organization
from .principal import Principal

_PREFIX = re.compile(r"^/o/(?P<slug>[-a-zA-Z0-9_]+)(?P<rest>/.*)?$")


def _set_session_gucs(org_id: str, actor_id: str, request_id: str) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.org_id', %s, false)", [org_id])
        cur.execute("SELECT set_config('app.actor_id', %s, false)", [actor_id])
        cur.execute("SELECT set_config('app.request_id', %s, false)", [request_id])


class OrganizationContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        request.membership = None
        request.principal = None
        match = _PREFIX.match(request.path_info)
        if not match:
            return self.get_response(request)

        slug = match.group("slug")
        rest = match.group("rest") or "/"
        organization = Organization.objects.filter(slug=slug).first()
        if organization is None:
            raise Http404("Unknown organization")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

        request.organization = organization
        request.org_prefix = f"/o/{slug}"
        request.path_info = rest
        _set_session_gucs(
            str(organization.id), str(user.pk), str(getattr(request, "request_id", ""))
        )
        try:
            membership = Membership.objects.filter(
                organization=organization, user=user, status=Membership.STATUS_ACTIVE
            ).first()
            if membership is None or not user.is_active:
                raise PermissionDenied("Not a member of this organization")
            request.membership = membership
            request.principal = Principal(
                user=user, organization=organization, role=membership.role
            )
            return self.get_response(request)
        finally:
            if connection.connection is not None and not connection.in_atomic_block:
                _set_session_gucs("", "", "")
