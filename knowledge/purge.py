"""Purge of a document revision (PLAN.md "Purge"). Dependents registered by
other apps are invalidated first, then chunks and embeddings go, then the
version's text, then the document becomes a tombstone when nothing is left."""

from __future__ import annotations

import logging

from django.utils import timezone

from infra.api import metrics
from retrieval.api import delete_version_chunks

from .models import AccessGrant, Document, DocumentReference, DocumentVersion

log = logging.getLogger(__name__)
_purge_hooks: list = []


def register_purge_hook(fn) -> None:
    """Apps register `fn(version)` to invalidate derived objects (answers,
    investigations, decision records) before the content disappears."""
    _purge_hooks.append(fn)


def maybe_purge(version_id) -> bool:
    """Purge the version when no unrevoked grant remains. Caller holds the
    document lock inside an organization scope."""
    if AccessGrant.objects.filter(version_id=version_id, revoked_at__isnull=True).exists():
        return False
    version = DocumentVersion.objects.select_for_update().filter(id=version_id).first()
    if version is None or version.content_state == DocumentVersion.CONTENT_PURGED:
        return False
    purge_version(version)
    return True


def purge_version(version: DocumentVersion) -> None:
    for hook in _purge_hooks:
        hook(version)
    DocumentReference.objects.filter(from_version=version).update(evidence_excerpt=None)
    delete_version_chunks(version)
    version.content_text = None
    version.structure = None
    version.content_state = DocumentVersion.CONTENT_PURGED
    version.save(update_fields=["content_text", "structure", "content_state"])
    document = Document.objects.select_for_update().get(id=version.document_id)
    if not DocumentVersion.objects.filter(
        document=document, content_state=DocumentVersion.CONTENT_PRESENT
    ).exists():
        document.status = Document.STATUS_TOMBSTONE
        document.tombstoned_at = timezone.now()
    document.generation += 1
    document.save(update_fields=["status", "tombstoned_at", "generation", "updated_at"])
    metrics.purge_completed_total.inc()
    log.info(
        "version purged", extra={"document_id": str(document.id), "version_id": str(version.id)}
    )
