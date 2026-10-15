"""Chunk and embedding persistence for one document revision."""

from __future__ import annotations

from django.contrib.postgres.search import SearchVector

from .embedding.factory import get_embedder
from .models import Chunk, Embedding


def version_has_chunks(version) -> bool:
    return Chunk.objects.filter(version=version, is_active=True).exists()


def embed_texts(texts: list[str]):
    if not texts:
        return []
    return get_embedder().embed_batch(texts)


def publish_chunks(version, drafts, vectors) -> int:
    """Insert chunks and embeddings for `version`. Unique (version, position)
    makes a replay a no-op. Caller holds the document lock."""
    org_id = version.organization_id
    Chunk.objects.bulk_create(
        [
            Chunk(
                organization_id=org_id,
                document_id=version.document_id,
                version=version,
                position=d.position,
                text=d.text,
                heading_path=d.heading_path,
                locator=d.locator,
                content_hash=d.content_hash,
            )
            for d in drafts
        ],
        ignore_conflicts=True,
    )
    Chunk.objects.filter(version=version, search_vector__isnull=True).update(
        search_vector=SearchVector("text", config="english")
    )
    by_position = {c.position: c for c in Chunk.objects.filter(version=version)}
    Embedding.objects.bulk_create(
        [
            Embedding(
                organization_id=org_id,
                chunk=by_position[d.position],
                model_id=v.model_id,
                model_version=v.model_version,
                vec=v.vector,
            )
            for d, v in zip(drafts, vectors, strict=True)
            if d.position in by_position
        ],
        ignore_conflicts=True,
    )
    return len(by_position)


def delete_version_chunks(version) -> int:
    deleted, _ = Chunk.objects.filter(version=version).delete()
    return deleted
