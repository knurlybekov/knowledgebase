"""`get_embedder()` reads settings.EMBEDDER and checks the dimension against
the halfvec column width."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ..models import EMBEDDING_DIMENSIONS
from .base import Embedder
from .mock import MockEmbedder
from .openai import OpenAIEmbedder


def get_embedder() -> Embedder:
    kind = settings.EMBEDDER
    dim = int(settings.EMBEDDING_DIM)
    if kind == "mock":
        embedder: Embedder = MockEmbedder(dim=dim)
    elif kind == "openai":
        embedder = OpenAIEmbedder(
            api_key=settings.OPENAI_API_KEY,
            model=settings.EMBEDDING_MODEL,
            model_version=settings.EMBEDDING_MODEL_VERSION,
            dim=dim,
        )
    else:
        raise ValueError(f"Unknown EMBEDDER={kind!r}. Use mock or openai.")
    if embedder.dim != EMBEDDING_DIMENSIONS:
        raise ImproperlyConfigured(
            f"EMBEDDING_DIM={embedder.dim} but the retrieval_embedding.vec column is "
            f"halfvec({EMBEDDING_DIMENSIONS}). Add a migration and reindex before changing it."
        )
    return embedder
