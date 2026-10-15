"""Source-independent ingestion (PLAN.md "Ingestion pipeline", steps 4-8).

`apply_change` is called by the connector inbox processor for one event. All
database writes happen in short organization-scoped transactions under the
document's advisory lock; download, parse, chunk and embed run outside.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

from infra.api import document_lock, with_org
from retrieval.api import embed_texts, publish_chunks, version_has_chunks

from .chunking import chunk_document
from .models import AccessGrant, Document, DocumentVersion
from .parsing import parse
from .purge import maybe_purge, run_publish_hooks
from .types import ChangeEvent, DownloadResult, RevisionDrift, SourceDocument, UnsupportedFormat

log = logging.getLogger(__name__)

Fetcher = Callable[[SourceDocument], DownloadResult]

OBSOLETE = "obsolete"
REFRESHED = "refreshed"
PUBLISHED = "published"
REVOKED = "revoked"
STALE = "stale"
UNSUPPORTED = "unsupported"
DRIFT = "drift"
NOOP = "noop"


def _lock_key(org_id, source_type: str, source_id: str) -> str:
    return f"{org_id}:{source_type}:{source_id}"


def _apply_metadata(document: Document, sd: SourceDocument) -> None:
    document.title = sd.title[:512]
    document.mime_type = sd.mime_type[:255]
    document.source_url = sd.source_url[:2000]
    document.path = sd.path[:2000]
    document.drive_id = sd.drive_id[:255]
    document.site_id = sd.site_id[:255]
    document.author = sd.author[:255]
    document.created_at_source = sd.created_at
    document.modified_at_source = sd.modified_at


def _upsert_grant(
    document, version, link, scope, event: ChangeEvent
) -> tuple[AccessGrant, str | None]:
    """Returns (grant, previous_version_id)."""
    grant = AccessGrant.objects.select_for_update().filter(document=document, scope=scope).first()
    previous = None
    if grant is None:
        grant = AccessGrant(
            organization_id=document.organization_id,
            document=document,
            version=version,
            link=link,
            scope=scope,
            first_seen_at=event.observed_at,
            last_revalidated_at=event.observed_at,
            last_event_seq=event.seq,
            last_seen_reconcile_generation=event.reconcile_generation,
        )
    else:
        if grant.version_id != version.id:
            previous = grant.version_id
        grant.version = version
        grant.scope = scope
        grant.last_revalidated_at = max(grant.last_revalidated_at, event.observed_at)
        grant.last_event_seq = event.seq
        if event.reconcile_generation is not None:
            grant.last_seen_reconcile_generation = event.reconcile_generation
        grant.revoked_at = None
        grant.revoke_reason = ""
    grant.save()
    return grant, previous


def apply_change(link, scope, event: ChangeEvent, fetcher: Fetcher) -> str:
    if event.kind == "remove":
        return remove_access(link, scope, event)
    return upsert(link, scope, event, fetcher)


def upsert(link, scope, event: ChangeEvent, fetcher: Fetcher) -> str:
    sd = event.document
    assert sd is not None
    org_id = link.organization_id
    key = _lock_key(org_id, sd.source_type, sd.source_id)

    # Phase 1: metadata, version row, fast path.
    with with_org(org_id):
        with connection.cursor() as cur:
            document_lock(cur, key)
        document, _ = Document.objects.get_or_create(
            organization_id=org_id, source_type=sd.source_type, source_id=sd.source_id
        )
        grant = AccessGrant.objects.filter(document=document, scope=scope).first()
        if grant is not None and event.seq <= grant.last_event_seq:
            return OBSOLETE
        version, _ = DocumentVersion.objects.get_or_create(
            document=document,
            version_label=sd.version_label,
            defaults={"organization_id": org_id},
        )
        _apply_metadata(document, sd)
        if version.content_state == DocumentVersion.CONTENT_PRESENT and version_has_chunks(version):
            _, previous = _upsert_grant(document, version, link, scope, event)
            document.status = Document.STATUS_ACTIVE
            document.generation += 1
            document.save()
            if previous is not None:
                maybe_purge(previous)
            return REFRESHED
        document.generation += 1
        document.save()
        snapshot = document.generation
        document_id = document.id
        version_id = version.id

    # Phase 2: stage outside any transaction.
    try:
        download = fetcher(sd)
    except RevisionDrift:
        log.warning("revision drift; event skipped", extra={"source_id": sd.source_id})
        return DRIFT
    if download.version_label != sd.version_label:
        return DRIFT
    try:
        parsed = parse(
            download.content, download.mime_type or sd.mime_type, download.filename or sd.title
        )
    except UnsupportedFormat as exc:
        with with_org(org_id):
            Document.objects.filter(id=document_id).update(
                status=Document.STATUS_QUARANTINED, updated_at=timezone.now()
            )
        log.info(
            "unsupported format quarantined", extra={"source_id": sd.source_id, "reason": str(exc)}
        )
        return UNSUPPORTED
    drafts = chunk_document(parsed)
    vectors = embed_texts([d.text for d in drafts]) if drafts else []

    # Phase 3: publish under the lock, fenced by generation.
    with with_org(org_id):
        with connection.cursor() as cur:
            document_lock(cur, key)
        document = Document.objects.select_for_update().get(id=document_id)
        if document.generation != snapshot:
            return STALE
        version = DocumentVersion.objects.select_for_update().get(id=version_id)
        publish_chunks(version, drafts, vectors)
        version.content_text = parsed.text
        version.structure = {
            "parser": parsed.parser,
            "sections": [
                {"heading_path": list(s.heading_path), "locator": s.locator, "chars": len(s.text)}
                for s in parsed.sections
            ],
        }
        version.content_hash = _hash(parsed.text)
        version.parser = parsed.parser
        version.extracted_at = timezone.now()
        version.content_state = DocumentVersion.CONTENT_PRESENT
        version.save()
        _, previous = _upsert_grant(document, version, link, scope, event)
        document.status = Document.STATUS_ACTIVE
        document.tombstoned_at = None
        document.generation += 1
        document.save()
        if previous is not None:
            maybe_purge(previous)
        published_version = version
    run_publish_hooks(published_version, link)
    return PUBLISHED


def _hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def remove_access(link, scope, event: ChangeEvent, reason: str = "removed") -> str:
    org_id = link.organization_id
    source_type = event.document.source_type if event.document else link.provider
    with with_org(org_id):
        with connection.cursor() as cur:
            document_lock(cur, _lock_key(org_id, source_type, event.source_id))
        document = (
            Document.objects.select_for_update()
            .filter(organization_id=org_id, source_type=source_type, source_id=event.source_id)
            .first()
        )
        if document is None:
            return NOOP
        grant = (
            AccessGrant.objects.select_for_update().filter(document=document, scope=scope).first()
        )
        if grant is None:
            # Removal before any publish for this scope: persist a fence so the
            # older staged upsert is obsolete when it comes back.
            AccessGrant.objects.create(
                organization_id=org_id,
                document=document,
                version=None,
                link=link,
                scope=scope,
                first_seen_at=event.observed_at,
                last_revalidated_at=event.observed_at,
                last_event_seq=event.seq,
                revoked_at=timezone.now(),
                revoke_reason=reason[:32],
            )
            document.generation += 1
            document.save(update_fields=["generation", "updated_at"])
            return REVOKED
        if event.seq <= grant.last_event_seq:
            return OBSOLETE
        _revoke(grant, reason, event.seq)
        document.generation += 1
        document.save(update_fields=["generation", "updated_at"])
        if grant.version_id is not None:
            maybe_purge(grant.version_id)
        return REVOKED


def _revoke(grant: AccessGrant, reason: str, seq: int | None = None) -> None:
    grant.revoked_at = timezone.now()
    grant.revoke_reason = reason[:32]
    if seq is not None:
        grant.last_event_seq = seq
    grant.save(update_fields=["revoked_at", "revoke_reason", "last_event_seq"])


def _revoke_grants(org_id, grants_qs, reason: str) -> int:
    """Revoke each grant under its document lock, then purge orphaned versions."""
    count = 0
    pairs = list(
        grants_qs.values_list("id", "document_id", "document__source_type", "document__source_id")
    )
    for grant_id, document_id, source_type, source_id in pairs:
        with with_org(org_id):
            with connection.cursor() as cur:
                document_lock(cur, _lock_key(org_id, source_type, source_id))
            grant = (
                AccessGrant.objects.select_for_update()
                .filter(id=grant_id, revoked_at__isnull=True)
                .first()
            )
            if grant is None:
                continue
            _revoke(grant, reason)
            Document.objects.filter(id=document_id).update(generation=models_F("generation") + 1)
            if grant.version_id is not None:
                maybe_purge(grant.version_id)
            count += 1
    return count


def models_F(name):
    from django.db.models import F

    return F(name)


def revoke_link_grants(link, reason: str = "link_error") -> int:
    with with_org(link.organization_id):
        qs = AccessGrant.objects.filter(link=link, revoked_at__isnull=True)
        return _revoke_grants(link.organization_id, qs, reason)


def revoke_scope_grants(scope, reason: str = "scope_lost") -> int:
    with with_org(scope.organization_id):
        qs = AccessGrant.objects.filter(scope=scope, revoked_at__isnull=True)
        return _revoke_grants(scope.organization_id, qs, reason)


def revoke_link_drive_grants(link, drive_id: str, reason: str = "scope_lost") -> int:
    """Google: a shared drive left the account's view; revoke this link's grants on it."""
    if not drive_id:
        return 0
    with with_org(link.organization_id):
        qs = AccessGrant.objects.filter(
            link=link, revoked_at__isnull=True, document__drive_id=drive_id
        )
        return _revoke_grants(link.organization_id, qs, reason)


def sweep_not_seen(scope, generation: int) -> int:
    """Revoke grants of the scope that a completed reconcile generation did not
    touch. The caller has verified the sweep barrier."""
    from django.db.models import Q

    with with_org(scope.organization_id):
        qs = AccessGrant.objects.filter(scope=scope, revoked_at__isnull=True).filter(
            Q(last_seen_reconcile_generation__isnull=True)
            | Q(last_seen_reconcile_generation__lt=generation)
        )
        return _revoke_grants(scope.organization_id, qs, "not_seen")


def expire_stale_grants(org_id) -> int:
    """Expiration sweeper: grants stale beyond freshness + purge grace."""
    cutoff = timezone.now() - timedelta(
        seconds=settings.PERMISSION_FRESHNESS_MAX_AGE_S + settings.PURGE_GRACE_S
    )
    with with_org(org_id):
        qs = AccessGrant.objects.filter(
            organization_id=org_id, revoked_at__isnull=True, last_revalidated_at__lt=cutoff
        )
        return _revoke_grants(org_id, qs, "expired")
