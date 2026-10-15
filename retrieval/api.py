"""Public surface of the retrieval app."""

from .embedding.base import Embedder, EmbeddingVector
from .embedding.factory import get_embedder
from .embedding.mock import MockEmbedder
from .models import Chunk, Embedding, RetrievalLog
from .search import RRF_K, SearchResult, chunks_for, search
from .store import delete_version_chunks, embed_texts, publish_chunks, version_has_chunks

__all__ = [
    "RRF_K",
    "Chunk",
    "Embedder",
    "Embedding",
    "EmbeddingVector",
    "MockEmbedder",
    "RetrievalLog",
    "SearchResult",
    "chunks_for",
    "delete_version_chunks",
    "embed_texts",
    "get_embedder",
    "publish_chunks",
    "search",
    "version_has_chunks",
]
