"""Public surface of the knowledge app."""

from .authz import (
    freshness_cutoff,
    membership_active,
    valid_grants,
    versions_visible,
    visible_documents,
    visible_versions,
)
from .chunking import chunk_document
from .models import AccessGrant, Document, DocumentReference, DocumentVersion
from .parsing import parse
from .pipeline import (
    DRIFT,
    NOOP,
    OBSOLETE,
    PUBLISHED,
    REFRESHED,
    REVOKED,
    STALE,
    UNSUPPORTED,
    apply_change,
    expire_stale_grants,
    revoke_link_drive_grants,
    revoke_link_grants,
    revoke_scope_grants,
    sweep_not_seen,
)
from .purge import maybe_purge, purge_version, register_publish_hook, register_purge_hook
from .types import (
    ChangeEvent,
    ChunkDraft,
    DownloadResult,
    ParsedDocument,
    RevisionDrift,
    Section,
    SourceDocument,
    UnsupportedFormat,
)


def visible_version(principal, version_id):
    return visible_versions(principal).select_related("document").filter(id=version_id).first()


def visible_document(principal, document_id):
    return visible_documents(principal).filter(id=document_id).first()


__all__ = [
    "DRIFT",
    "NOOP",
    "OBSOLETE",
    "PUBLISHED",
    "REFRESHED",
    "REVOKED",
    "STALE",
    "UNSUPPORTED",
    "AccessGrant",
    "ChangeEvent",
    "ChunkDraft",
    "Document",
    "DocumentReference",
    "DocumentVersion",
    "DownloadResult",
    "ParsedDocument",
    "RevisionDrift",
    "Section",
    "SourceDocument",
    "UnsupportedFormat",
    "apply_change",
    "chunk_document",
    "expire_stale_grants",
    "freshness_cutoff",
    "maybe_purge",
    "membership_active",
    "parse",
    "purge_version",
    "register_publish_hook",
    "register_purge_hook",
    "revoke_link_drive_grants",
    "revoke_link_grants",
    "revoke_scope_grants",
    "sweep_not_seen",
    "valid_grants",
    "versions_visible",
    "visible_document",
    "visible_documents",
    "visible_version",
    "visible_versions",
]
