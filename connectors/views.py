"""Connector link flows. The OAuth callbacks live outside the organization
prefix (providers need one exact redirect URI); the organization travels in the
signed state."""

from __future__ import annotations

import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.api import UserIdentity, link_identity
from infra.api import with_org
from organizations.api import Membership, Organization, org_path

from . import oauth
from .api import ConnectorLink, SyncScope, create_link, ensure_scope, revoke_link
from .models import SyncRun

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive.readonly",
]
MS_SCOPES = [
    "Files.Read.All",
    "Sites.Read.All",
]  # offline_access, openid, profile, email are added by MSAL


def _state(request, organization) -> str:
    nonce = secrets.token_urlsafe(16)
    request.session["connector_oauth_nonce"] = nonce
    return signing.dumps(
        {"org": str(organization.id), "user": str(request.user.pk), "nonce": nonce},
        salt="connector-oauth",
    )


def _read_state(request, raw: str) -> Organization:
    try:
        data = signing.loads(raw, salt="connector-oauth", max_age=900)
    except signing.BadSignature as exc:
        raise PermissionDenied("Invalid OAuth state") from exc
    if data.get("user") != str(request.user.pk) or data.get("nonce") != request.session.pop(
        "connector_oauth_nonce", None
    ):
        raise PermissionDenied("OAuth state does not match this session")
    organization = get_object_or_404(Organization, id=data["org"])
    with with_org(organization.id, request.user.pk):
        if not Membership.objects.filter(
            organization=organization, user=request.user, status="active"
        ).exists():
            raise PermissionDenied("Not a member")
    return organization


@login_required
def connectors_page(request):
    organization = request.organization
    with with_org(organization.id, request.user.pk):
        links = list(
            ConnectorLink.objects.filter(user=request.user)
            .exclude(status=ConnectorLink.STATUS_REVOKED)
            .order_by("provider")
        )
        scopes = {l.id: list(SyncScope.objects.filter(link=l)) for l in links}
        runs = {l.id: SyncRun.objects.filter(link=l).order_by("-started_at").first() for l in links}
    return render(
        request,
        "connectors/index.html",
        {
            "links": links,
            "scopes": scopes,
            "runs": runs,
            "google_configured": bool(settings.GOOGLE_CLIENT_ID),
            "microsoft_configured": bool(settings.MICROSOFT_CLIENT_ID),
        },
    )


@login_required
def google_start(request, slug):
    organization = get_object_or_404(Organization, slug=slug)
    if not settings.GOOGLE_CLIENT_ID:
        return HttpResponseBadRequest("Google connector is not configured")
    url = oauth.google_authorization_url(request, GOOGLE_SCOPES, _state(request, organization))
    return redirect(url)


@login_required
def google_callback(request):
    if "error" in request.GET:
        return HttpResponseBadRequest("Google authorization was refused")
    organization = _read_state(request, request.GET.get("state", ""))
    result = oauth.google_exchange_code(request, GOOGLE_SCOPES, request.GET.get("code", ""))
    identity = link_identity(
        request.user,
        provider=UserIdentity.PROVIDER_GOOGLE,
        external_id=result.subject,
        email=result.email,
        verified_via=UserIdentity.VERIFIED_OAUTH,
    )
    link = create_link(
        organization,
        request.user,
        provider=ConnectorLink.PROVIDER_GOOGLE,
        external_account_id=result.subject,
        email=result.email,
        refresh_token=result.refresh_token,
        oauth_scopes=result.scopes,
        identity=identity,
    )
    ensure_scope(link, kind=SyncScope.KIND_GOOGLE_CHANGES, display_name="Google Drive changes")
    _enqueue_syncs(link)
    messages.success(request, "Google Drive linked. The first sync has started.")
    return redirect(org_path(organization, "/connectors/"))


@login_required
def microsoft_start(request, slug):
    organization = get_object_or_404(Organization, slug=slug)
    if not settings.MICROSOFT_CLIENT_ID:
        return HttpResponseBadRequest("Microsoft connector is not configured")
    return redirect(
        oauth.microsoft_authorization_url(request, MS_SCOPES, _state(request, organization))
    )


@login_required
def microsoft_callback(request):
    if "error" in request.GET:
        return HttpResponseBadRequest("Microsoft authorization was refused")
    organization = _read_state(request, request.GET.get("state", ""))
    result = oauth.microsoft_exchange_code(request, MS_SCOPES, request.GET.get("code", ""))
    identity = link_identity(
        request.user,
        provider=UserIdentity.PROVIDER_MICROSOFT,
        external_id=result.subject,
        email=result.email,
        verified_via=UserIdentity.VERIFIED_OAUTH,
    )
    link = create_link(
        organization,
        request.user,
        provider=ConnectorLink.PROVIDER_SHAREPOINT,
        external_account_id=result.subject,
        email=result.email,
        refresh_token=result.refresh_token,
        oauth_scopes=result.scopes,
        identity=identity,
    )
    messages.success(request, "Microsoft account linked. Choose the libraries to index.")
    return redirect(org_path(organization, f"/connectors/{link.id}/select/"))


@login_required
def sharepoint_select(request, link_id):
    """Explicit library selection: own drive, followed sites, site search or a
    pasted site URL. Only selected drives become sync scopes."""
    from .clients import client_for

    organization = request.organization
    with with_org(organization.id, request.user.pk):
        link = get_object_or_404(
            ConnectorLink, id=link_id, user=request.user, provider=ConnectorLink.PROVIDER_SHAREPOINT
        )
    client = client_for(link)
    if request.method == "POST":
        chosen = request.POST.getlist("drive")
        names = dict(
            zip(request.POST.getlist("drive"), request.POST.getlist("drive_name"), strict=False)
        )
        with with_org(organization.id, request.user.pk):
            ConnectorLink.objects.filter(id=link.id).update(
                selected_scopes=[{"drive_id": d, "name": names.get(d, "")} for d in chosen]
            )
        for drive_id in chosen:
            ensure_scope(
                link,
                kind=SyncScope.KIND_GRAPH_DRIVE,
                external_id=drive_id,
                display_name=names.get(drive_id, ""),
            )
        _enqueue_syncs(link)
        messages.success(request, f"{len(chosen)} libraries selected. Sync has started.")
        return redirect(org_path(organization, "/connectors/"))
    options = []
    my_drive = client.my_drive()
    options.append({"drive_id": my_drive["id"], "name": "My OneDrive", "site": ""})
    sites = list(client.followed_sites())
    query = request.GET.get("q", "").strip()
    if query:
        if query.startswith("https://"):
            from urllib.parse import urlparse

            parsed = urlparse(query)
            sites.append(client.resolve_site(parsed.hostname or "", parsed.path or "/"))
        else:
            sites.extend(client.search_sites(query))
    for site in sites:
        for drive in client.site_drives(site["id"]):
            options.append(
                {
                    "drive_id": drive["id"],
                    "name": drive.get("name", ""),
                    "site": site.get("displayName", ""),
                }
            )
    return render(
        request, "connectors/select.html", {"link": link, "options": options, "query": query}
    )


@login_required
@require_POST
def unlink(request, link_id):
    organization = request.organization
    with with_org(organization.id, request.user.pk):
        link = get_object_or_404(ConnectorLink, id=link_id, user=request.user)
    revoke_link(link)
    messages.success(
        request, "Account unlinked. Documents it provided are no longer visible to you."
    )
    return redirect(org_path(organization, "/connectors/"))


@login_required
@require_POST
def sync_now(request, link_id):
    organization = request.organization
    with with_org(organization.id, request.user.pk):
        link = get_object_or_404(ConnectorLink, id=link_id, user=request.user)
    _enqueue_syncs(link)
    messages.success(request, "Sync requested.")
    return redirect(org_path(organization, "/connectors/"))


def _enqueue_syncs(link: ConnectorLink) -> None:
    from .tasks import sync_scope_task

    with with_org(link.organization_id):
        scope_ids = list(SyncScope.objects.filter(link=link).values_list("id", flat=True))
    for scope_id in scope_ids:
        sync_scope_task.delay(str(link.organization_id), str(scope_id))
