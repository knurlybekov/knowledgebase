"""Microsoft Graph (SharePoint / OneDrive) client over httpx with MSAL tokens.

Facts used (verified 2026-10-14): `/drives/{id}/root/delta` enumerates everything
on the first call and returns `@odata.deltaLink` at the end; deleted items carry
the `deleted` facet; HTTP 410 means re-enumerate; item ids are unique per drive,
so the canonical id is `sp:<driveId>:<itemId>` (shared wrappers use remoteItem);
current content is fetched through `/content` and validated by `cTag` before and
after, because pinned downloads exist only for previous versions; `sharedWithMe`
is not used (degraded, data no longer returned from November 2026).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote

import httpx
from django.conf import settings

from knowledge.api import DownloadResult, RevisionDrift, SourceDocument

from ..http import AuthError, ProviderError, ResyncRequired, ScopeLost, request_with_retry
from .base import MAX_DOWNLOAD_RETRIES, Item, Page

GRAPH = "https://graph.microsoft.com/v1.0"
DELTA_SELECT = (
    "id,name,file,folder,deleted,cTag,eTag,size,webUrl,createdDateTime,lastModifiedDateTime,"
    "parentReference,remoteItem,createdBy"
)


class GraphApi(Protocol):
    def get(self, url: str) -> dict: ...

    def download(self, url: str) -> bytes: ...


def canonical_id(drive_id: str, item_id: str) -> str:
    return f"sp:{drive_id}:{item_id}"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def to_source_document(item: dict, drive_id: str, site_id: str = "") -> SourceDocument | None:
    if "folder" in item or ("file" not in item and "remoteItem" not in item):
        return None
    remote = item.get("remoteItem")
    if remote is not None:
        drive_id = (remote.get("parentReference") or {}).get("driveId", drive_id)
        item_id = remote.get("id", item["id"])
        file_facet = remote.get("file") or item.get("file") or {}
        ctag = remote.get("cTag") or item.get("cTag") or remote.get("eTag") or item.get("eTag", "")
    else:
        item_id = item["id"]
        file_facet = item.get("file") or {}
        ctag = item.get("cTag") or item.get("eTag", "")
    if not file_facet:
        return None
    parent = item.get("parentReference") or {}
    created_by = ((item.get("createdBy") or {}).get("user") or {}).get("email", "")
    return SourceDocument(
        source_type="sharepoint",
        source_id=canonical_id(drive_id, item_id),
        version_label=ctag or "unknown",
        title=item.get("name", ""),
        mime_type=file_facet.get("mimeType", ""),
        source_url=item.get("webUrl", ""),
        path=(parent.get("path") or ""),
        drive_id=drive_id,
        site_id=site_id or parent.get("siteId", ""),
        author=created_by,
        created_at=_parse_time(item.get("createdDateTime")),
        modified_at=_parse_time(item.get("lastModifiedDateTime")),
        size=item.get("size"),
        extra={"item_id": item_id},
    )


class GraphClient:
    def __init__(self, api: GraphApi, *, max_bytes: int | None = None):
        self.api = api
        self.max_bytes = max_bytes or settings.DOWNLOAD_MAX_BYTES

    def bootstrap_cursor(self, scope) -> str | None:
        return None  # the deltaLink of the first full enumeration is the cursor

    def _walk(self, scope, url: str) -> Iterator[Page]:
        drive_id = scope.external_id
        while True:
            now = datetime.now(UTC)
            data = self.api.get(url)
            items: list[Item] = []
            for item in data.get("value", []):
                if "deleted" in item:
                    remote = item.get("remoteItem") or {}
                    rid = remote.get("id", item["id"])
                    rdrive = (remote.get("parentReference") or {}).get("driveId", drive_id)
                    items.append(Item("remove", canonical_id(rdrive, rid)))
                    continue
                sd = to_source_document(item, drive_id)
                if sd is not None:
                    items.append(Item("upsert", sd.source_id, sd))
            if data.get("@odata.nextLink"):
                url = data["@odata.nextLink"]
                yield Page(items, now, next_cursor=url)
                continue
            yield Page(items, now, done_cursor=data.get("@odata.deltaLink", ""))
            return

    def list_all(self, scope) -> Iterator[Page]:
        yield from self._walk(
            scope, f"{GRAPH}/drives/{quote(scope.external_id)}/root/delta?$select={DELTA_SELECT}"
        )

    def list_changes(self, scope, cursor: str) -> Iterator[Page]:
        yield from self._walk(scope, cursor)

    def refresh(self, sd: SourceDocument) -> SourceDocument | None:
        _, drive_id, item_id = sd.source_id.split(":", 2)
        try:
            item = self.api.get(
                f"{GRAPH}/drives/{quote(drive_id)}/items/{quote(item_id)}?$select={DELTA_SELECT}"
            )
        except ProviderError as exc:
            if exc.status == 404:
                return None
            raise
        return to_source_document(item, drive_id, sd.site_id)

    def fetch(self, sd: SourceDocument) -> DownloadResult:
        _, drive_id, item_id = sd.source_id.split(":", 2)
        base = f"{GRAPH}/drives/{quote(drive_id)}/items/{quote(item_id)}"
        for _attempt in range(MAX_DOWNLOAD_RETRIES):
            before = self.api.get(f"{base}?$select=id,cTag,eTag,file,name,size")
            label = before.get("cTag") or before.get("eTag", "")
            if label != sd.version_label:
                raise RevisionDrift(f"{sd.source_id}: {sd.version_label} -> {label}")
            if (before.get("size") or 0) > self.max_bytes:
                raise ProviderError("too_large")
            content = self.api.download(f"{base}/content")
            after = self.api.get(f"{base}?$select=id,cTag,eTag")
            if (after.get("cTag") or after.get("eTag", "")) == sd.version_label:
                return DownloadResult(
                    content=content,
                    version_label=sd.version_label,
                    mime_type=sd.mime_type,
                    filename=sd.title,
                )
        raise RevisionDrift(f"{sd.source_id} changed during download")

    # --- discovery for the selection UI ------------------------------------
    def my_drive(self) -> dict:
        return self.api.get(f"{GRAPH}/me/drive?$select=id,name,webUrl")

    def followed_sites(self) -> list[dict]:
        return self.api.get(f"{GRAPH}/me/followedSites?$select=id,displayName,webUrl").get(
            "value", []
        )

    def search_sites(self, text: str) -> list[dict]:
        return self.api.get(
            f"{GRAPH}/sites?search={quote(text)}&$select=id,displayName,webUrl"
        ).get("value", [])

    def resolve_site(self, hostname: str, path: str) -> dict:
        return self.api.get(
            f"{GRAPH}/sites/{quote(hostname)}:{quote(path)}?$select=id,displayName,webUrl"
        )

    def site_drives(self, site_id: str) -> list[dict]:
        return self.api.get(f"{GRAPH}/sites/{quote(site_id)}/drives?$select=id,name,webUrl").get(
            "value", []
        )


class GraphHttpApi:
    """httpx-backed GraphApi with MSAL refresh-token acquisition."""

    def __init__(self, refresh_token: str, *, client: httpx.Client | None = None):
        self._refresh_token = refresh_token
        self._client = client or httpx.Client(timeout=60.0, follow_redirects=True)
        self._token: str | None = None

    def _access_token(self) -> str:
        if self._token:
            return self._token
        import msal

        app = msal.ConfidentialClientApplication(
            settings.MICROSOFT_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{settings.MICROSOFT_TENANT}",
            client_credential=settings.MICROSOFT_CLIENT_SECRET,
        )
        result = app.acquire_token_by_refresh_token(
            self._refresh_token, scopes=["Files.Read.All", "Sites.Read.All"]
        )
        if "access_token" not in result:
            raise AuthError("token_refresh_failed", result.get("error_description", ""))
        self._token = result["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json"}

    def _handle(self, response: httpx.Response, url: str):
        if response.status_code == 401:
            raise AuthError("unauthorized", status=401)
        if response.status_code == 410:
            raise ResyncRequired("resync", status=410)
        if response.status_code in (403, 404) and "/root/delta" in url:
            raise ScopeLost("scope_lost", status=response.status_code)
        if response.status_code >= 400:
            raise ProviderError("http_error", response.text[:200], status=response.status_code)

    def get(self, url: str) -> dict:
        response = request_with_retry(self._client, "GET", url, headers=self._headers())
        self._handle(response, url)
        return response.json()

    def download(self, url: str) -> bytes:
        response = request_with_retry(self._client, "GET", url, headers=self._headers())
        self._handle(response, url)
        return response.content
