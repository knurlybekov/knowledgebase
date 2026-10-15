"""Google Drive client. Logic (canonical ids, export mapping, validated
downloads) is separated from the API surface so tests use an in-memory API.

Facts used (verified 2026-10-14): changes.list only tracks changes after the
start token, so bootstrap captures the token, lists everything, then replays;
`removed` means deletion or loss of access; `version` is monotonic and present
for every file; `headRevisionId` and `md5Checksum` exist only for binary files.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Protocol

from django.conf import settings

from knowledge.api import DownloadResult, RevisionDrift, SourceDocument

from ..http import AuthError, ProviderError
from .base import MAX_DOWNLOAD_RETRIES, Item, Page

FILE_FIELDS = (
    "id,name,mimeType,version,headRevisionId,md5Checksum,modifiedTime,createdTime,"
    "webViewLink,parents,driveId,trashed,size,owners(emailAddress)"
)
EXPORT = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}
SKIP_MIME_PREFIX = "application/vnd.google-apps."  # folders, forms, drawings, shortcuts


class GoogleApi(Protocol):
    """Minimal surface over googleapiclient. Each call returns parsed JSON."""

    def start_page_token(self) -> str: ...

    def list_drives(self, page_token: str | None) -> dict: ...

    def list_files(self, *, corpora: str, drive_id: str | None, page_token: str | None) -> dict: ...

    def list_changes(self, page_token: str) -> dict: ...

    def get_file(self, file_id: str) -> dict: ...

    def download(self, file_id: str) -> bytes: ...

    def export(self, file_id: str, mime: str) -> bytes: ...


def canonical_id(file_id: str) -> str:
    return f"gdrive:{file_id}"


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def to_source_document(meta: dict) -> SourceDocument | None:
    """Map Drive file metadata to a SourceDocument, or None when the type is
    not ingestible (folders, forms, shortcuts)."""
    mime = meta.get("mimeType", "")
    if mime.startswith(SKIP_MIME_PREFIX) and mime not in EXPORT:
        return None
    if mime in EXPORT:
        label = f"v{meta.get('version', '0')}"
        target_mime = EXPORT[mime][0]
    else:
        label = meta.get("headRevisionId") or f"v{meta.get('version', '0')}"
        target_mime = mime
    owners = meta.get("owners") or []
    return SourceDocument(
        source_type="google_drive",
        source_id=canonical_id(meta["id"]),
        version_label=label,
        title=meta.get("name", ""),
        mime_type=target_mime,
        source_url=meta.get("webViewLink", ""),
        path="",
        drive_id=meta.get("driveId", ""),
        author=(owners[0].get("emailAddress", "") if owners else ""),
        created_at=_parse_time(meta.get("createdTime")),
        modified_at=_parse_time(meta.get("modifiedTime")),
        size=int(meta["size"]) if meta.get("size") else None,
        extra={
            "native_mime": mime,
            "version": str(meta.get("version", "")),
            "md5": meta.get("md5Checksum", ""),
        },
    )


class GoogleDriveClient:
    def __init__(self, api: GoogleApi, *, max_bytes: int | None = None):
        self.api = api
        self.max_bytes = max_bytes or settings.DOWNLOAD_MAX_BYTES

    # --- listing -----------------------------------------------------------
    def bootstrap_cursor(self, scope) -> str | None:
        return self.api.start_page_token()

    def _items_from_files(self, files: list[dict]) -> list[Item]:
        items = []
        for meta in files:
            if meta.get("trashed"):
                items.append(Item("remove", canonical_id(meta["id"])))
                continue
            sd = to_source_document(meta)
            if sd is not None:
                items.append(Item("upsert", sd.source_id, sd))
        return items

    def list_all(self, scope) -> Iterator[Page]:
        """User corpus, then each shared drive. The final page carries the
        cursor captured by `bootstrap_cursor` through `extra`."""
        token = None
        while True:
            now = datetime.now(UTC)
            data = self.api.list_files(corpora="user", drive_id=None, page_token=token)
            token = data.get("nextPageToken")
            yield Page(
                self._items_from_files(data.get("files", [])),
                now,
                next_cursor="more" if token else None,
            )
            if not token:
                break
        drive_token = None
        drives: list[dict] = []
        while True:
            data = self.api.list_drives(drive_token)
            drives.extend(data.get("drives", []))
            drive_token = data.get("nextPageToken")
            if not drive_token:
                break
        for drive in drives:
            token = None
            while True:
                now = datetime.now(UTC)
                data = self.api.list_files(corpora="drive", drive_id=drive["id"], page_token=token)
                token = data.get("nextPageToken")
                yield Page(
                    self._items_from_files(data.get("files", [])),
                    now,
                    next_cursor="more" if token else None,
                )
                if not token:
                    break
        yield Page([], datetime.now(UTC), done_cursor="")

    def list_changes(self, scope, cursor: str) -> Iterator[Page]:
        token = cursor
        while True:
            now = datetime.now(UTC)
            data = self.api.list_changes(token)
            items: list[Item] = []
            for change in data.get("changes", []):
                if change.get("changeType") == "drive":
                    if change.get("removed"):
                        items.append(Item("drive_removed", "", drive_id=change.get("driveId", "")))
                    continue
                file_id = change.get("fileId")
                if not file_id:
                    continue
                if change.get("removed") or (change.get("file") or {}).get("trashed"):
                    items.append(Item("remove", canonical_id(file_id)))
                    continue
                sd = to_source_document(change["file"]) if change.get("file") else None
                if sd is not None:
                    items.append(Item("upsert", sd.source_id, sd))
            if data.get("nextPageToken"):
                token = data["nextPageToken"]
                yield Page(items, now, next_cursor=token)
                continue
            yield Page(items, now, done_cursor=data.get("newStartPageToken", token))
            return

    # --- validated download --------------------------------------------------
    def fetch(self, sd: SourceDocument) -> DownloadResult:
        file_id = sd.source_id.split(":", 1)[1]
        native = sd.extra.get("native_mime", sd.mime_type)
        for _attempt in range(MAX_DOWNLOAD_RETRIES):
            before = self.api.get_file(file_id)
            label_before = to_source_document(before)
            if label_before is None:
                raise ProviderError("not_ingestible")
            if label_before.version_label != sd.version_label:
                # The item moved on; the caller handles this as drift.
                raise RevisionDrift(
                    f"{sd.source_id}: {sd.version_label} -> {label_before.version_label}"
                )
            if native in EXPORT:
                mime, suffix = EXPORT[native]
                content = self.api.export(file_id, mime)
            else:
                mime, suffix = sd.mime_type, ""
                content = self.api.download(file_id)
                md5 = before.get("md5Checksum")
                if md5 and hashlib.md5(content).hexdigest() != md5:
                    continue
            if len(content) > self.max_bytes:
                raise ProviderError("too_large")
            after = to_source_document(self.api.get_file(file_id))
            if after is not None and after.version_label == sd.version_label:
                return DownloadResult(
                    content=content,
                    version_label=sd.version_label,
                    mime_type=mime,
                    filename=(sd.title or file_id) + suffix,
                )
        raise RevisionDrift(f"{sd.source_id} changed during download")


class GoogleApiClient:
    """googleapiclient-backed GoogleApi. Built from a link's refresh token."""

    def __init__(self, refresh_token: str):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)

    def _run(self, request):
        from google.auth.exceptions import RefreshError
        from googleapiclient.errors import HttpError

        try:
            return request.execute(num_retries=4)
        except RefreshError as exc:
            raise AuthError("token_refresh_failed", str(exc)[:200], status=401) from exc
        except HttpError as exc:
            status = exc.resp.status
            if status in (401,):
                raise AuthError("unauthorized", status=status) from exc
            raise ProviderError("http_error", str(exc), status=status) from exc

    def start_page_token(self) -> str:
        return self._run(self._service.changes().getStartPageToken(supportsAllDrives=True))[
            "startPageToken"
        ]

    def list_drives(self, page_token):
        return self._run(self._service.drives().list(pageSize=100, pageToken=page_token))

    def list_files(self, *, corpora, drive_id, page_token):
        kwargs = dict(
            pageSize=1000,
            pageToken=page_token,
            fields=f"nextPageToken,files({FILE_FIELDS})",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora=corpora,
            q="trashed = false",
        )
        if drive_id:
            kwargs["driveId"] = drive_id
        return self._run(self._service.files().list(**kwargs))

    def list_changes(self, page_token):
        return self._run(
            self._service.changes().list(
                pageToken=page_token,
                pageSize=1000,
                includeRemoved=True,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields=f"nextPageToken,newStartPageToken,changes(changeType,fileId,driveId,removed,file({FILE_FIELDS}))",
            )
        )

    def get_file(self, file_id):
        return self._run(
            self._service.files().get(fileId=file_id, fields=FILE_FIELDS, supportsAllDrives=True)
        )

    def download(self, file_id):
        return self._run(self._service.files().get_media(fileId=file_id, supportsAllDrives=True))

    def export(self, file_id, mime):
        return self._run(self._service.files().export_media(fileId=file_id, mimeType=mime))
