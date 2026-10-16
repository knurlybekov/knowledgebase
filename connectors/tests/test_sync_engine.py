import pytest
from django.utils import timezone

from connectors.api import ConnectorLink, SyncLease, SyncRun, SyncScope, ensure_scope
from connectors.models import ChangeInbox
from connectors.providers.google import GoogleDriveClient
from connectors.providers.graph import GraphClient
from connectors.sync import BUSY, LEASE_LOST, sync_scope
from connectors.tests.factories import make_link
from infra.api import with_org
from knowledge.api import AccessGrant, Document, DocumentVersion
from knowledge.tests.helpers import count_visible, docx_bytes, principal_for, visible_labels
from organizations.tests.factories import make_membership, make_org, make_user
from retrieval.api import Chunk

from .fakes import FakeGoogleApi, FakeGraphApi

pytestmark = pytest.mark.django_db(transaction=True)


def google_setup():
    org, user = make_org(), make_user()
    make_membership(org, user)
    link = make_link(org, user)
    scope = ensure_scope(link, kind=SyncScope.KIND_GOOGLE_CHANGES)
    api = FakeGoogleApi()
    return org, user, link, scope, api, GoogleDriveClient(api)


def graph_setup():
    org, user = make_org(), make_user()
    make_membership(org, user)
    link = make_link(org, user, provider=ConnectorLink.PROVIDER_SHAREPOINT)
    scope = ensure_scope(link, kind=SyncScope.KIND_GRAPH_DRIVE, external_id="drive-1")
    api = FakeGraphApi()
    return org, user, link, scope, api, GraphClient(api)


def test_google_bootstrap_lists_everything_then_tracks_changes():
    org, user, _link, scope, api, client = google_setup()
    api.add_file("a", "Policy.md", b"# Policy\nVacation is fifteen days.")
    api.add_file("b", "Notes.md", b"# Notes\nMeeting notes.")
    api.add_file(
        "c",
        "Design",
        docx_bytes([("Heading 1", "Design"), ("Normal", "Native doc exported.")]),
        native=True,
    )
    api.drives.append({"id": "shared-1", "name": "Shared"})
    api.add_file("d", "Shared.md", b"# Shared\nShared drive file.", drive_id="shared-1")
    start_token = api.start_page_token()

    assert sync_scope(scope, client) == SyncRun.KIND_BOOTSTRAP
    with with_org(org.id):
        scope.refresh_from_db()
    assert scope.bootstrapped and scope.cursor_value == start_token
    assert scope.current_reconcile_generation == 1 and scope.last_ok_at is not None
    with with_org(org.id):
        assert ChangeInbox.objects.filter(status="done").count() == 4
        assert ChangeInbox.objects.filter(reconcile_generation=1).count() == 4
        assert Document.objects.count() == 4
        assert SyncRun.objects.get().status == "completed"
        assert AccessGrant.objects.filter(last_seen_reconcile_generation=1).count() == 4
    assert count_visible(principal_for(org, user)) == 4

    # Incremental: a modification, a removal, and a shared-drive loss.
    api.modify("a", b"# Policy\nVacation is now twenty days.")
    api.remove("b")
    api.remove_drive("shared-1")
    assert sync_scope(scope, client) == SyncRun.KIND_INCREMENTAL
    with with_org(org.id):
        scope.refresh_from_db()
    assert scope.cursor_value == api.start_page_token()
    with with_org(org.id):
        doc_a = Document.objects.get(source_id="gdrive:a")
        labels = sorted(
            DocumentVersion.objects.filter(document=doc_a).values_list(
                "version_label", "content_state"
            )
        )
        assert labels == [("rev-a-1", "purged"), ("rev-a-2", "present")]
        assert Document.objects.get(source_id="gdrive:b").status == "tombstone"
        assert AccessGrant.objects.get(document__source_id="gdrive:d").revoke_reason == "scope_lost"
    assert sorted(visible_labels(principal_for(org, user))) == ["rev-a-2", "v1"]


def test_lease_busy_and_lease_lost():
    org, _user, _link, scope, api, client = google_setup()
    api.add_file("a", "A.md", b"# A\nalpha")
    with with_org(org.id):
        SyncLease.objects.filter(scope=scope).update(
            lease_token="other", expires_at=timezone.now() + timezone.timedelta(minutes=5)
        )
    assert sync_scope(scope, client) == BUSY
    with with_org(org.id):
        SyncLease.objects.filter(scope=scope).update(expires_at=timezone.now())

    original = api.list_files

    def steal_lease(**kwargs):
        with with_org(org.id):
            SyncLease.objects.filter(scope=scope).update(lease_token="stolen")
        return original(**kwargs)

    api.list_files = steal_lease
    assert sync_scope(scope, client) == LEASE_LOST
    with with_org(org.id):
        assert not ChangeInbox.objects.exists()
        assert not Document.objects.exists()


def test_reconcile_sweeps_not_seen_only_when_barrier_holds():
    org, _user, _link, scope, api, client = google_setup()
    api.add_file("a", "A.md", b"# A\nalpha")
    api.add_file("b", "B.md", b"# B\nbeta")
    sync_scope(scope, client)
    # File b silently disappears from the listing (no change event), as with inherited permission loss.
    api.files.pop("b")
    assert sync_scope(scope, client, force_reconcile=True) == SyncRun.KIND_RECONCILE
    with with_org(org.id):
        scope.refresh_from_db()
    assert scope.current_reconcile_generation == 2
    with with_org(org.id):
        assert AccessGrant.objects.get(document__source_id="gdrive:b").revoke_reason == "not_seen"
        assert AccessGrant.objects.get(document__source_id="gdrive:a").revoked_at is None

    # A failed row in the next generation blocks the sweep.
    api.add_file("c", "C.md", b"# C\ngamma")
    calls = {"n": 0}

    def bump_version(file_id):
        if file_id == "c":
            calls["n"] += 1
            api.files["c"]["version"] = str(100 + calls["n"])
            api.files["c"]["headRevisionId"] = f"rev-c-{100 + calls['n']}"

    api.on_get_file = bump_version  # every metadata read shows a newer revision: drift
    api.files.pop("a")
    sync_scope(scope, client, force_reconcile=True)
    with with_org(org.id):
        scope.refresh_from_db()
    assert scope.current_reconcile_generation == 2, "sweep must not run with a failed row"
    with with_org(org.id):
        assert ChangeInbox.objects.filter(status="failed", error_code="drift").exists()
        assert AccessGrant.objects.get(document__source_id="gdrive:a").revoked_at is None


def test_auth_error_marks_link_and_hides_documents():
    org, user, link, scope, api, client = google_setup()
    api.add_file("a", "A.md", b"# A\nalpha")
    sync_scope(scope, client)
    assert count_visible(principal_for(org, user)) == 1
    api.fail_auth = True
    sync_scope(scope, client)
    with with_org(org.id):
        link.refresh_from_db()
    assert link.status == "error" and link.last_error_code == "unauthorized"
    assert count_visible(principal_for(org, user)) == 0
    with with_org(org.id):
        assert SyncRun.objects.filter(status="failed", error_code="unauthorized").exists()


def test_graph_delta_bootstrap_remote_items_deletes_and_resync():
    org, user, _link, scope, api, client = graph_setup()
    api.add_item("i1", "Plan.md", b"# Plan\nThe plan.")
    api.add_item("i2", "Risks.md", b"# Risks\nRisks here.")
    api.add_item(
        "w1",
        "Shared.md",
        b"# Shared\nFrom another drive.",
        remote={
            "id": "r9",
            "parentReference": {"driveId": "drive-other"},
            "file": {"mimeType": "text/markdown"},
            "cTag": "rc1",
        },
    )
    assert sync_scope(scope, client) == SyncRun.KIND_BOOTSTRAP
    with with_org(org.id):
        scope.refresh_from_db()
    assert scope.cursor_value.endswith("token=3")
    with with_org(org.id):
        ids = set(Document.objects.values_list("source_id", flat=True))
    assert ids == {"sp:drive-1:i1", "sp:drive-1:i2", "sp:drive-other:r9"}
    assert count_visible(principal_for(org, user)) == 3

    api.modify("i1", b"# Plan\nRevised plan.", ctag="c2")
    api.delete("i2")
    assert sync_scope(scope, client) == SyncRun.KIND_INCREMENTAL
    with with_org(org.id):
        assert Document.objects.get(source_id="sp:drive-1:i2").status == "tombstone"
        assert DocumentVersion.objects.filter(
            document__source_id="sp:drive-1:i1", version_label="c2", content_state="present"
        ).exists()

    # Expired cursor: HTTP 410 switches the run into a full reconcile.
    api.invalid_tokens.add(scope.cursor_value.rsplit("token=", 1)[1])
    assert sync_scope(scope, client) == SyncRun.KIND_RECONCILE
    with with_org(org.id):
        scope.refresh_from_db()
    assert scope.current_reconcile_generation == 2
    with with_org(org.id):
        assert SyncRun.objects.filter(kind="full_reconcile", status="completed").exists()


def test_graph_scope_loss_revokes_scope_grants():
    org, user, _link, scope, api, client = graph_setup()
    api.add_item("i1", "Plan.md", b"# Plan\nThe plan.")
    sync_scope(scope, client)
    assert count_visible(principal_for(org, user)) == 1
    api.lost = True
    sync_scope(scope, client)
    with with_org(org.id):
        assert AccessGrant.objects.get().revoke_reason == "scope_lost"
        assert not Chunk.objects.exists()
    assert count_visible(principal_for(org, user)) == 0


def test_oversized_download_is_terminal_and_quarantined(monkeypatch):
    """Live sync 2026-10-16: an 865 MB archive left a `failed` inbox row, which
    would have blocked the reconcile barrier forever. too_large is terminal."""
    from connectors.http import ProviderError

    org, _user, _link, scope, api, client = google_setup()
    api.add_file("big", "Movie.pdf", b"%PDF-1.4 big")

    def too_large(sd):
        raise ProviderError("too_large")

    monkeypatch.setattr(client, "fetch", too_large)
    assert sync_scope(scope, client) == SyncRun.KIND_BOOTSTRAP
    with with_org(org.id):
        row = ChangeInbox.objects.get(source_id="gdrive:big")
        assert (row.status, row.error_code) == ("done", "too_large")
        assert Document.objects.get(source_id="gdrive:big").status == "quarantined"
        assert SyncRun.objects.get().status == "completed"


def test_no_new_reconcile_while_the_previous_listing_is_still_being_applied():
    """Live drive 2026-10-16: with 2,700 bootstrap rows still pending, the next
    poll opened generation 2 and listed all 3,171 items again."""
    from connectors.sync import _due_for_reconcile

    org, _user, _link, scope, api, client = google_setup()
    api.add_file("a", "Policy.md", b"# Policy\nVacation is fifteen days.")
    assert sync_scope(scope, client) == SyncRun.KIND_BOOTSTRAP
    with with_org(org.id):
        scope.refresh_from_db()
        assert _due_for_reconcile(scope) is False  # generation 1 completed and swept
        scope.last_reconcile_at = None
        row = ChangeInbox.objects.get(scope=scope)
        ChangeInbox.objects.filter(id=row.id).update(status=ChangeInbox.STATUS_PENDING)
    assert _due_for_reconcile(scope) is False  # rows of generation 1 still pending
    with with_org(org.id):
        ChangeInbox.objects.filter(id=row.id).update(status=ChangeInbox.STATUS_DONE)
    assert _due_for_reconcile(scope) is True
