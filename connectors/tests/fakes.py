"""In-memory provider APIs for sync engine tests."""

from __future__ import annotations

from connectors.http import AuthError, ProviderError, ResyncRequired

PAGE = 2


class FakeGoogleApi:
    def __init__(self):
        self.files: dict[str, dict] = {}
        self.contents: dict[str, bytes] = {}
        self.drives: list[dict] = []
        self.changes: list[dict] = []
        self.fail_auth = False
        self.on_get_file = None

    # --- mutation helpers -----------------------------------------------------
    def add_file(
        self, file_id, name, content: bytes, *, mime="text/markdown", drive_id=None, native=False
    ):
        meta = {
            "id": file_id,
            "name": name,
            "version": "1",
            "webViewLink": f"https://drive.google.com/file/d/{file_id}",
            "modifiedTime": "2026-01-01T00:00:00Z",
            "createdTime": "2026-01-01T00:00:00Z",
        }
        if native:
            meta["mimeType"] = "application/vnd.google-apps.document"
        else:
            meta["mimeType"] = mime
            meta["headRevisionId"] = f"rev-{file_id}-1"
            import hashlib

            meta["md5Checksum"] = hashlib.md5(content).hexdigest()
        if drive_id:
            meta["driveId"] = drive_id
        self.files[file_id] = meta
        self.contents[file_id] = content
        self.changes.append({"changeType": "file", "fileId": file_id, "file": dict(meta)})
        return meta

    def modify(self, file_id, content: bytes):
        import hashlib

        meta = self.files[file_id]
        meta["version"] = str(int(meta["version"]) + 1)
        if "headRevisionId" in meta:
            meta["headRevisionId"] = f"rev-{file_id}-{meta['version']}"
            meta["md5Checksum"] = hashlib.md5(content).hexdigest()
        self.contents[file_id] = content
        self.changes.append({"changeType": "file", "fileId": file_id, "file": dict(meta)})

    def remove(self, file_id):
        self.files.pop(file_id, None)
        self.changes.append({"changeType": "file", "fileId": file_id, "removed": True})

    def remove_drive(self, drive_id):
        self.drives = [d for d in self.drives if d["id"] != drive_id]
        self.changes.append({"changeType": "drive", "driveId": drive_id, "removed": True})

    # --- GoogleApi --------------------------------------------------------------
    def _auth(self):
        if self.fail_auth:
            raise AuthError("unauthorized", status=401)

    def start_page_token(self):
        self._auth()
        return str(len(self.changes) + 1)

    def list_drives(self, page_token):
        self._auth()
        return {"drives": list(self.drives)}

    def list_files(self, *, corpora, drive_id, page_token):
        self._auth()
        if corpora == "user":
            rows = [f for f in self.files.values() if not f.get("driveId")]
        else:
            rows = [f for f in self.files.values() if f.get("driveId") == drive_id]
        start = int(page_token or 0)
        page = rows[start : start + PAGE]
        out = {"files": [dict(f) for f in page]}
        if start + PAGE < len(rows):
            out["nextPageToken"] = str(start + PAGE)
        return out

    def list_changes(self, page_token):
        self._auth()
        start = int(page_token) - 1
        page = self.changes[start : start + PAGE]
        out = {"changes": [dict(c) for c in page]}
        if start + PAGE < len(self.changes):
            out["nextPageToken"] = str(start + PAGE + 1)
        else:
            out["newStartPageToken"] = str(len(self.changes) + 1)
        return out

    def get_file(self, file_id):
        self._auth()
        if self.on_get_file:
            self.on_get_file(file_id)
        if file_id not in self.files:
            raise ProviderError("not_found", status=404)
        return dict(self.files[file_id])

    def download(self, file_id):
        return self.contents[file_id]

    def export(self, file_id, mime):
        return self.contents[file_id]


class FakeGraphApi:
    """Simulates one drive's delta feed. Items keyed by id; `log` is the change
    history; tokens index into it."""

    def __init__(self, drive_id="drive-1"):
        self.drive_id = drive_id
        self.items: dict[str, dict] = {}
        self.contents: dict[str, bytes] = {}
        self.log: list[dict] = []
        self.invalid_tokens: set[str] = set()
        self.fail_auth = False
        self.lost = False

    def add_item(self, item_id, name, content: bytes, *, ctag="c1", remote: dict | None = None):
        item = {
            "id": item_id,
            "name": name,
            "file": {"mimeType": "text/markdown"},
            "cTag": ctag,
            "eTag": "e1",
            "webUrl": f"https://contoso.sharepoint.com/{name}",
            "size": len(content),
            "parentReference": {"driveId": self.drive_id, "path": "/drive/root:/Docs"},
        }
        if remote:
            item["remoteItem"] = remote
            # The underlying item in the other drive is reachable by its own id.
            self.items[remote["id"]] = {
                "id": remote["id"],
                "name": name,
                "file": remote.get("file", {}),
                "cTag": remote.get("cTag", ""),
                "eTag": "e1",
                "size": len(content),
            }
            self.contents[remote["id"]] = content
        self.items[item_id] = item
        self.contents[item_id] = content
        self.log.append(dict(item))

    def modify(self, item_id, content: bytes, ctag: str):
        self.items[item_id]["cTag"] = ctag
        self.contents[item_id] = content
        self.log.append(dict(self.items[item_id]))

    def delete(self, item_id):
        self.items.pop(item_id, None)
        self.log.append({"id": item_id, "deleted": {}})

    def _check(self, url):
        if self.fail_auth:
            raise AuthError("unauthorized", status=401)
        if self.lost and "/root/delta" in url:
            from connectors.http import ScopeLost

            raise ScopeLost("scope_lost", status=404)

    def get(self, url):
        self._check(url)
        if "/root/delta" in url and "token=" not in url and "full=" not in url:
            return self._snapshot_page(0)
        if "full=" in url:
            return self._snapshot_page(int(url.rsplit("full=", 1)[1]))
        if "token=" in url:
            token = url.rsplit("token=", 1)[1]
            if token in self.invalid_tokens:
                raise ResyncRequired("resync", status=410)
            return self._page(int(token))
        if "/items/" in url:
            item_id = url.split("/items/", 1)[1].split("?", 1)[0].split("/", 1)[0]
            if item_id not in self.items:
                raise ProviderError("not_found", status=404)
            return dict(self.items[item_id])
        raise ProviderError("unexpected_url", url)

    def _snapshot_page(self, start):
        """Full enumeration: every live item once, in its current state."""
        rows = [
            i
            for i in self.items.values()
            if "remoteItem" in i or i.get("parentReference", {}).get("driveId") == self.drive_id
        ]
        page = rows[start : start + PAGE]
        out = {"value": [dict(r) for r in page]}
        nxt = start + PAGE
        if nxt < len(rows):
            out["@odata.nextLink"] = (
                f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root/delta?full={nxt}"
            )
        else:
            out["@odata.deltaLink"] = (
                f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root/delta?token={len(self.log)}"
            )
        return out

    def _page(self, start):
        """Incremental: changes since the token, latest state per item."""
        latest: dict[str, dict] = {}
        for entry in self.log[start:]:
            latest[entry["id"]] = entry
        rows = list(latest.values())
        out = {"value": [dict(r) for r in rows]}
        out["@odata.deltaLink"] = (
            f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root/delta?token={len(self.log)}"
        )
        return out

    def download(self, url):
        item_id = url.split("/items/", 1)[1].split("/content", 1)[0]
        return self.contents[item_id]
