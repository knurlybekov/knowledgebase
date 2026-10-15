"""Chunks, embeddings and the retrieval log. One chunk set per document revision."""

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils import timezone
from pgvector.django import HalfVectorField, HnswIndex

EMBEDDING_DIMENSIONS = 1536  # halfvec column width; a change needs a new migration and a reindex


class Chunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    document = models.ForeignKey(
        "knowledge.Document", on_delete=models.PROTECT, related_name="chunks"
    )
    version = models.ForeignKey(
        "knowledge.DocumentVersion", on_delete=models.CASCADE, related_name="chunks"
    )
    position = models.IntegerField()
    text = models.TextField()
    heading_path = models.JSONField(default=list)
    locator = models.JSONField(default=dict)
    content_hash = models.CharField(max_length=64)
    search_vector = SearchVectorField(null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["version", "position"], name="uniq_chunk_position")
        ]
        indexes = [
            GinIndex(fields=["search_vector"], name="chunk_search_gin_idx"),
            models.Index(fields=["organization", "document"]),
        ]


class Embedding(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    chunk = models.ForeignKey(Chunk, on_delete=models.CASCADE, related_name="embeddings")
    model_id = models.CharField(max_length=64, db_index=True)
    model_version = models.CharField(max_length=64, db_index=True)
    vec = HalfVectorField(dimensions=EMBEDDING_DIMENSIONS)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["chunk", "model_id", "model_version"], name="uniq_embedding_per_model"
            )
        ]
        indexes = [
            HnswIndex(
                name="embedding_vec_hnsw_idx",
                fields=["vec"],
                m=16,
                ef_construction=64,
                opclasses=["halfvec_cosine_ops"],
            )
        ]


class RetrievalLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="+"
    )
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+", null=True)
    query_hash = models.CharField(max_length=64)
    mode = models.CharField(max_length=16)
    candidate_chunk_ids = models.JSONField(default=list)
    latency_ms = models.IntegerField(default=0)
    denied_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
