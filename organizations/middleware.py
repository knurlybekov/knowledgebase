"""Resolve `/o/<slug>/...` to an organization, require an active membership,
enter the RLS scope for the whole request, and strip the prefix so the URL
resolver sees organization-free paths (templates re-attach it with org_url)."""

import re

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.http import Http404

from infra.api import set_org_gucs

from .models import Membership, Organization
from .principal import Principal

_PREFIX = re.compile(r"^/o/(?P<slug>[-a-zA-Z0-9_]+)(?P<rest>/.*)?$")


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
        with transaction.atomic():
            with connection.cursor() as cur:
                set_org_gucs(cur, organization.id, user.pk)
                cur.execute("SET LOCAL app.request_id = %s;", [getattr(request, "request_id", "")])
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
