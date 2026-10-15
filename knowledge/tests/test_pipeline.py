"""Pipeline behavior: publish, fast path, fencing, revocation, purge,
visibility, concurrency."""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection

from connectors.api import ConnectorLink, set_link_status
from connectors.tests.factories import make_link, make_scope
from infra.api import with_org
from knowledge.api import (
    DRIFT,
    OBSOLETE,
    PUBLISHED,
    REFRESHED,
    REVOKED,
    STALE,
    UNSUPPORTED,
    AccessGrant,
    Document,
    DocumentVersion,
    apply_change,
    expire_stale_grants,
    revoke_link_grants,
    sweep_not_seen,
)
from knowledge.types import RevisionDrift
from organizations.api import Membership, remove_member
from organizations.tests.factories import make_membership, make_org, make_user
from retrieval.api import Chunk, Embedding

from .helpers import (
    StaticFetcher,
    count_visible,
    make_event,
    make_source,
    principal_for,
    visible_labels,
)

pytestmark = pytest.mark.django_db(transaction=True)

DOC_V1 = b"# Hosting decision\nWe selected provider Alpha in March.\n## Alternatives\nProvider Beta was rejected on cost."
DOC_V2 = b"# Hosting decision\nWe selected provider Alpha in March.\n## Revision\nIn June the contract moved to Gamma."


def setup_user():
    org = make_org()
    user = make_user()
    make_membership(org, user)
    link = make_link(org, user)
    scope = make_scope(link)
    return org, user, link, scope


def test_publish_creates_version_grant_chunks_and_embeddings():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1", title="Hosting decision")
    fetcher = StaticFetcher({"v1": DOC_V1})
    assert apply_change(link, scope, make_event(1, sd), fetcher) == PUBLISHED
    with with_org(org.id):
        doc = Document.objects.get(source_id="gdrive:f1")
        version = DocumentVersion.objects.get(document=doc, version_label="v1")
        assert doc.status == "active" and doc.title == "Hosting decision"
        assert version.content_state == "present" and "Alpha" in version.content_text
        chunks = list(Chunk.objects.filter(version=version).order_by("position"))
        assert len(chunks) == 2 and chunks[0].heading_path == ["Hosting decision"]
        assert all(c.search_vector is not None for c in chunks)
        assert Embedding.objects.filter(chunk__in=chunks, model_id="mock").count() == 2
        grant = AccessGrant.objects.get(document=doc, link=link)
        assert grant.version_id == version.id and grant.last_event_seq == 1
    assert count_visible(principal_for(org, user)) == 1


def test_replay_is_obsolete_and_same_label_takes_fast_path():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1", title="Old title")
    fetcher = StaticFetcher({"v1": DOC_V1})
    apply_change(link, scope, make_event(1, sd), fetcher)
    assert apply_change(link, scope, make_event(1, sd), fetcher) == OBSOLETE
    renamed = make_source("gdrive:f1", "v1", title="New title")
    assert apply_change(link, scope, make_event(2, renamed), fetcher) == REFRESHED
    assert fetcher.calls == 1
    with with_org(org.id):
        assert Document.objects.get(source_id="gdrive:f1").title == "New title"
        assert Document.objects.filter(source_type="google_drive").count() == 1


def test_lower_seq_event_is_ignored():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1")
    fetcher = StaticFetcher({"v1": DOC_V1})
    apply_change(link, scope, make_event(5, sd), fetcher)
    assert (
        apply_change(
            link, scope, make_event(3, None, kind="remove", source_id="gdrive:f1"), fetcher
        )
        == OBSOLETE
    )
    with with_org(org.id):
        assert AccessGrant.objects.get(link=link).revoked_at is None


def test_remove_revokes_grant_purges_content_and_hides_document():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1")
    fetcher = StaticFetcher({"v1": DOC_V1})
    apply_change(link, scope, make_event(1, sd), fetcher)
    assert (
        apply_change(
            link, scope, make_event(2, None, kind="remove", source_id="gdrive:f1"), fetcher
        )
        == REVOKED
    )
    with with_org(org.id):
        doc = Document.objects.get(source_id="gdrive:f1")
        version = doc.versions.get()
        assert doc.status == "tombstone"
        assert version.content_state == "purged" and version.content_text is None
        assert not Chunk.objects.filter(version=version).exists()
        assert AccessGrant.objects.get(link=link).revoke_reason == "removed"
    assert count_visible(principal_for(org, user)) == 0


def test_tombstone_rebuild_restores_active():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1")
    fetcher = StaticFetcher({"v1": DOC_V1})
    apply_change(link, scope, make_event(1, sd), fetcher)
    apply_change(link, scope, make_event(2, None, kind="remove", source_id="gdrive:f1"), fetcher)
    assert apply_change(link, scope, make_event(3, sd), fetcher) == PUBLISHED
    assert fetcher.calls == 2
    with with_org(org.id):
        doc = Document.objects.get(source_id="gdrive:f1")
        assert doc.status == "active" and doc.tombstoned_at is None
        assert Chunk.objects.filter(document=doc).count() == 2


def test_two_users_same_revision_share_one_chunk_set():
    org = make_org()
    ua, ub = make_user(), make_user()
    make_membership(org, ua)
    make_membership(org, ub)
    la, lb = make_link(org, ua), make_link(org, ub)
    sa, sb = make_scope(la), make_scope(lb)
    sd = make_source("gdrive:f1", "v1")
    fetcher = StaticFetcher({"v1": DOC_V1})
    assert apply_change(la, sa, make_event(1, sd), fetcher) == PUBLISHED
    assert apply_change(lb, sb, make_event(1, sd), fetcher) == REFRESHED
    with with_org(org.id):
        assert DocumentVersion.objects.count() == 1
        assert Chunk.objects.count() == 2
        assert AccessGrant.objects.count() == 2
    assert count_visible(principal_for(org, ua)) == 1
    assert count_visible(principal_for(org, ub)) == 1


def test_two_users_different_revisions_do_not_share():
    org = make_org()
    ua, ub = make_user(), make_user()
    make_membership(org, ua)
    make_membership(org, ub)
    la, lb = make_link(org, ua), make_link(org, ub)
    sa, sb = make_scope(la), make_scope(lb)
    fetcher = StaticFetcher({"v1": DOC_V1, "v2": DOC_V2})
    apply_change(la, sa, make_event(1, make_source("gdrive:f1", "v1")), fetcher)
    apply_change(lb, sb, make_event(1, make_source("gdrive:f1", "v2")), fetcher)
    with with_org(org.id):
        assert DocumentVersion.objects.count() == 2
    assert visible_labels(principal_for(org, ua)) == ["v1"]
    assert visible_labels(principal_for(org, ub)) == ["v2"]


def test_per_link_revoke_leaves_other_users_grant():
    org = make_org()
    ua, ub = make_user(), make_user()
    make_membership(org, ua)
    make_membership(org, ub)
    la, lb = make_link(org, ua), make_link(org, ub)
    sa, sb = make_scope(la), make_scope(lb)
    sd = make_source("gdrive:f1", "v1")
    fetcher = StaticFetcher({"v1": DOC_V1})
    apply_change(la, sa, make_event(1, sd), fetcher)
    apply_change(lb, sb, make_event(1, sd), fetcher)
    apply_change(la, sa, make_event(2, None, kind="remove", source_id="gdrive:f1"), fetcher)
    assert count_visible(principal_for(org, ua)) == 0
    assert count_visible(principal_for(org, ub)) == 1
    with with_org(org.id):
        assert Chunk.objects.count() == 2  # still granted to B
    revoke_link_grants(lb, "link_error")
    with with_org(org.id):
        assert Chunk.objects.count() == 0


def test_link_error_membership_removal_and_stale_grant_deny_access():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1")
    fetcher = StaticFetcher({"v1": DOC_V1})
    apply_change(link, scope, make_event(1, sd), fetcher)
    principal = principal_for(org, user)
    assert count_visible(principal) == 1

    set_link_status(link, ConnectorLink.STATUS_ERROR, "token_refresh_failed")
    assert count_visible(principal) == 0
    set_link_status(link, ConnectorLink.STATUS_ACTIVE)
    assert count_visible(principal) == 1

    with with_org(org.id):
        AccessGrant.objects.update(last_revalidated_at=datetime.now(UTC) - timedelta(hours=25))
    assert count_visible(principal) == 0, "empty deltas must not keep a grant fresh"
    assert apply_change(link, scope, make_event(2, sd), fetcher) == REFRESHED
    assert count_visible(principal) == 1

    admin = make_user()
    make_membership(org, admin, role=Membership.ROLE_ADMIN)
    remove_member(org, user, actor=principal_for(org, admin, role="admin"))
    assert count_visible(principal) == 0


def test_revalidation_uses_observation_time_not_processing_time():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1")
    fetcher = StaticFetcher({"v1": DOC_V1})
    old = datetime.now(UTC) - timedelta(hours=30)
    apply_change(link, scope, make_event(1, sd, observed_at=old), fetcher)
    assert count_visible(principal_for(org, user)) == 0


def test_expiration_sweep_purges_abandoned_versions():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1")
    fetcher = StaticFetcher({"v1": DOC_V1})
    apply_change(link, scope, make_event(1, sd), fetcher)
    with with_org(org.id):
        AccessGrant.objects.update(last_revalidated_at=datetime.now(UTC) - timedelta(days=5))
    assert expire_stale_grants(org.id) == 1
    with with_org(org.id):
        assert DocumentVersion.objects.get().content_state == "purged"
        assert AccessGrant.objects.get().revoke_reason == "expired"


def test_reconcile_sweep_revokes_not_seen_only():
    org, user, link, scope = setup_user()
    fetcher = StaticFetcher({"v1": DOC_V1})
    apply_change(
        link, scope, make_event(1, make_source("gdrive:seen", "v1"), generation=1), fetcher
    )
    apply_change(
        link, scope, make_event(2, make_source("gdrive:gone", "v1"), generation=1), fetcher
    )
    # Generation 2 re-lists only "seen".
    apply_change(
        link, scope, make_event(3, make_source("gdrive:seen", "v1"), generation=2), fetcher
    )
    assert sweep_not_seen(scope, 2) == 1
    with with_org(org.id):
        assert (
            AccessGrant.objects.get(document__source_id="gdrive:gone").revoke_reason == "not_seen"
        )
        assert AccessGrant.objects.get(document__source_id="gdrive:seen").revoked_at is None


def test_remove_during_download_makes_publish_stale():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:f1", "v1")
    inner = StaticFetcher({"v1": DOC_V1})
    apply_change(link, scope, make_event(1, sd), inner)
    apply_change(link, scope, make_event(2, None, kind="remove", source_id="gdrive:f1"), inner)

    def on_fetch(_sd):
        # A newer remove event lands while the upsert is still staging.
        apply_change(link, scope, make_event(4, None, kind="remove", source_id="gdrive:f1"), inner)

    racing = StaticFetcher({"v1": DOC_V1}, on_fetch=on_fetch)
    assert apply_change(link, scope, make_event(3, sd), racing) == STALE
    with with_org(org.id):
        grant = AccessGrant.objects.get(link=link)
        assert grant.revoked_at is not None and grant.last_event_seq == 4
        assert not Chunk.objects.exists()


def test_revision_drift_skips_event():
    org, user, link, scope = setup_user()

    def drifting(_sd):
        raise RevisionDrift("changed 3 times")

    assert (
        apply_change(link, scope, make_event(1, make_source("gdrive:f1", "v1")), drifting) == DRIFT
    )
    with with_org(org.id):
        assert not AccessGrant.objects.exists()


def test_unsupported_format_is_quarantined():
    org, user, link, scope = setup_user()
    sd = make_source("gdrive:bin", "v1", mime="application/octet-stream")
    fetcher = StaticFetcher({"v1": b"\x00\x01\x02"}, mime="application/octet-stream")
    assert apply_change(link, scope, make_event(1, sd), fetcher) == UNSUPPORTED
    with with_org(org.id):
        assert Document.objects.get(source_id="gdrive:bin").status == "quarantined"
    assert count_visible(principal_for(org, user)) == 0


def test_concurrent_ingestion_of_same_revision_yields_one_chunk_set():
    org = make_org()
    users = [make_user() for _ in range(3)]
    links = []
    for u in users:
        make_membership(org, u)
        link = make_link(org, u)
        links.append((link, make_scope(link)))
    sd = make_source("gdrive:f1", "v1")
    results = []
    errors = []

    def worker(link, scope):
        try:
            results.append(
                apply_change(link, scope, make_event(1, sd), StaticFetcher({"v1": DOC_V1}))
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=pair) for pair in links]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    # Exactly one thread publishes; the others see a changed generation and
    # report stale, which the inbox processor requeues. A retry takes the fast path.
    assert results.count("published") == 1 and set(results) <= {"published", "stale", "refreshed"}
    for link, scope in links:
        outcome = apply_change(link, scope, make_event(1, sd), StaticFetcher({"v1": DOC_V1}))
        assert outcome in (OBSOLETE, REFRESHED)
    with with_org(org.id):
        assert DocumentVersion.objects.count() == 1
        assert Chunk.objects.count() == 2
        assert Embedding.objects.count() == 2
        assert AccessGrant.objects.filter(revoked_at__isnull=True).count() == 3
