import pytest

from connectors.providers.google import GoogleDriveClient
from connectors.providers.google import to_source_document as google_sd
from connectors.providers.graph import GraphClient
from connectors.providers.graph import to_source_document as graph_sd
from knowledge.api import RevisionDrift

from .fakes import FakeGoogleApi, FakeGraphApi

pytestmark = pytest.mark.django_db


def test_google_mapping_native_and_binary_labels():
    native = google_sd(
        {
            "id": "x",
            "name": "Doc",
            "mimeType": "application/vnd.google-apps.document",
            "version": "7",
        }
    )
    assert native.version_label == "v7" and native.mime_type.endswith("wordprocessingml.document")
    binary = google_sd(
        {
            "id": "y",
            "name": "Scan.pdf",
            "mimeType": "application/pdf",
            "version": "3",
            "headRevisionId": "abc",
        }
    )
    assert binary.version_label == "abc" and binary.source_id == "gdrive:y"
    assert (
        google_sd({"id": "f", "name": "Folder", "mimeType": "application/vnd.google-apps.folder"})
        is None
    )


def test_google_fetch_validates_revision_and_checksum():
    api = FakeGoogleApi()
    meta = api.add_file("a", "A.pdf", b"%PDF-1.4 content", mime="application/pdf")
    client = GoogleDriveClient(api)
    sd = google_sd(meta)
    result = client.fetch(sd)
    assert result.content.startswith(b"%PDF") and result.version_label == sd.version_label

    # Revision changes between metadata and download on every attempt: drift.
    api.modify("a", b"%PDF-1.4 newer")
    with pytest.raises(RevisionDrift):
        client.fetch(sd)


def test_graph_mapping_uses_remote_item_and_ctag():
    item = {
        "id": "w",
        "name": "Shared.md",
        "file": {"mimeType": "text/markdown"},
        "cTag": "c1",
        "remoteItem": {
            "id": "r1",
            "parentReference": {"driveId": "d2"},
            "file": {"mimeType": "text/markdown"},
            "cTag": "rc7",
        },
    }
    sd = graph_sd(item, "d1")
    assert sd.source_id == "sp:d2:r1" and sd.version_label == "rc7"
    assert graph_sd({"id": "f", "name": "F", "folder": {}}, "d1") is None


def test_graph_fetch_rechecks_ctag():
    api = FakeGraphApi()
    api.add_item("i1", "Plan.md", b"# Plan", ctag="c1")
    client = GraphClient(api)
    sd = graph_sd(api.items["i1"], "drive-1")
    assert client.fetch(sd).content == b"# Plan"
    api.modify("i1", b"# Plan 2", ctag="c2")
    with pytest.raises(RevisionDrift):
        client.fetch(sd)


def test_google_export_size_limit_is_too_large():
    """Live drive 2026-10-16: a sheet above Google's export limit returned HTTP 403
    exportSizeLimitExceeded and was retried as a transient http_error."""
    import httplib2
    import pytest
    from googleapiclient.errors import HttpError

    from connectors.http import ProviderError
    from connectors.providers.google import GoogleApiClient

    body = b'{"error": {"code": 403, "message": "This file is too large to be exported.", "errors": [{"reason": "exportSizeLimitExceeded"}]}}'

    class Request:
        def execute(self, num_retries=0):
            raise HttpError(httplib2.Response({"status": 403}), body)

    client = GoogleApiClient.__new__(GoogleApiClient)
    with pytest.raises(ProviderError) as info:
        client._run(Request())
    assert info.value.code == "too_large"
