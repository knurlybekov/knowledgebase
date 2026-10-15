"""Hybrid retrieval over visible document revisions: vector leg (same embedder
only) and keyword leg, fused with reciprocal rank fusion."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field

from django.contrib.postgres.search import SearchQuery, SearchRank
from pgvector.django import CosineDistance

from infra.api import metrics, with_org

from .embedding.factory import get_embedder
from .models import Chunk, Embedding, RetrievalLog

RRF_K = 60
PER_LEG = 50
EXCERPT_CHARS = 500


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    version_id: str
    version_label: str
    title: str
    source_type: str
    source_url: str
    heading_path: list[str]
    locator: dict
    excerpt: str
    text: str
    score: float
    legs: list[str] = field(default_factory=list)

    @property
    def evidence_id(self) -> str:
        start = self.locator.get("start_char", 0)
        end = self.locator.get("end_char", 0)
        return f"chunk:{self.chunk_id}@{self.version_label}[{start}:{end}]"


_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]{1,}")
_STOP = {
    "the",
    "and",
    "for",
    "our",
    "with",
    "that",
    "this",
    "from",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "how",
    "did",
    "does",
    "do",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "many",
    "much",
    "each",
    "about",
    "into",
    "over",
    "last",
    "before",
    "after",
    "between",
    "there",
    "their",
    "they",
    "them",
    "its",
    "any",
    "all",
    "can",
    "could",
    "would",
    "should",
    "will",
    "been",
    "being",
    "you",
    "your",
    "we",
    "us",
}


def _or_query(query: str):
    terms = [w for w in _WORD.findall(query) if w.lower() not in _STOP]
    if not terms:
        return None
    tsquery = None
    for term in terms[:24]:
        part = SearchQuery(term, config="english", search_type="plain")
        tsquery = part if tsquery is None else (tsquery | part)
    return tsquery


def _visible_chunks(principal, source_types):
    from knowledge.api import visible_versions  # deferred: knowledge imports retrieval.api

    qs = Chunk.objects.filter(
        organization_id=principal.organization_id,
        is_active=True,
        version_id__in=visible_versions(principal).values("id"),
    )
    if source_types:
        qs = qs.filter(document__source_type__in=list(source_types))
    return qs


def search(
    principal, query: str, *, source_types=None, limit: int = 10, mode: str = "quick"
) -> list[SearchResult]:
    """Hybrid search inside the principal's organization scope (nestable)."""
    query = (query or "").strip()
    if not query:
        return []
    with with_org(principal.organization_id, principal.user_id):
        return _search(principal, query, source_types, limit, mode)


def _search(principal, query: str, source_types, limit: int, mode: str) -> list[SearchResult]:
    started = time.monotonic()
    base = _visible_chunks(principal, source_types)
    embedder = get_embedder()
    query_vector = embedder.embed(query).vector

    vector_ids = list(
        Embedding.objects.filter(
            organization_id=principal.organization_id,
            model_id=embedder.model_id,
            model_version=embedder.model_version,
            chunk__in=base,
        )
        .annotate(distance=CosineDistance("vec", query_vector))
        .order_by("distance", "chunk_id")
        .values_list("chunk_id", flat=True)[:PER_LEG]
    )
    # Keyword leg: OR of the query's content words, ranked by ts_rank (more
    # matching terms rank higher). A websearch AND would drop every natural
    # question that contains one word the document lacks. ts_rank returns a tiny
    # positive value for non-matching rows, so the match (@@) is the filter.
    tsquery = _or_query(query)
    keyword_ids = []
    if tsquery is not None:
        keyword_ids = list(
            base.filter(search_vector=tsquery)
            .annotate(rank=SearchRank("search_vector", tsquery))
            .order_by("-rank", "id")
            .values_list("id", flat=True)[:PER_LEG]
        )

    scores: dict = {}
    legs: dict = {}
    for leg, ids in (("vector", vector_ids), ("keyword", keyword_ids)):
        for rank, chunk_id in enumerate(ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank)
            legs.setdefault(chunk_id, []).append(leg)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], str(kv[0])))[: max(1, min(limit, 50))]
    top_ids = [cid for cid, _ in ranked]

    chunks = {
        c.id: c for c in Chunk.objects.filter(id__in=top_ids).select_related("document", "version")
    }
    # Defensive recheck: every returned chunk must still be a visible chunk.
    allowed = set(base.filter(id__in=top_ids).values_list("id", flat=True))
    denied = [cid for cid in top_ids if cid not in allowed]
    if denied:
        metrics.access_denied_total.labels(path="retrieval.search").inc(len(denied))

    results = []
    for chunk_id, score in ranked:
        chunk = chunks.get(chunk_id)
        if chunk is None or chunk_id not in allowed:
            continue
        results.append(
            SearchResult(
                chunk_id=str(chunk.id),
                document_id=str(chunk.document_id),
                version_id=str(chunk.version_id),
                version_label=chunk.version.version_label,
                title=chunk.document.title,
                source_type=chunk.document.source_type,
                source_url=chunk.document.source_url,
                heading_path=list(chunk.heading_path),
                locator=dict(chunk.locator),
                excerpt=chunk.text[:EXCERPT_CHARS],
                text=chunk.text,
                score=score,
                legs=legs.get(chunk_id, []),
            )
        )
    RetrievalLog.objects.create(
        organization_id=principal.organization_id,
        user=principal.user,
        query_hash=hashlib.sha256(query.encode("utf-8")).hexdigest(),
        mode=mode,
        candidate_chunk_ids=[str(c) for c in top_ids],
        latency_ms=int((time.monotonic() - started) * 1000),
        denied_count=len(denied),
    )
    return results


def chunks_for(principal, chunk_ids) -> list[Chunk]:
    """Visible chunks among `chunk_ids`, in the given order."""
    with with_org(principal.organization_id, principal.user_id):
        qs = (
            _visible_chunks(principal, None)
            .filter(id__in=list(chunk_ids))
            .select_related("document", "version")
        )
        by_id = {str(c.id): c for c in qs}
        return [by_id[str(c)] for c in chunk_ids if str(c) in by_id]
