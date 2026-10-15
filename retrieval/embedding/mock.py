"""Deterministic offline embedder: sha256 of the text spread over `dim`
values. Same text, same vector; no semantic structure."""

import hashlib
from collections.abc import Sequence

from .base import EmbeddingVector


class MockEmbedder:
    def __init__(self, *, dim: int, model_version: str = "mock-1") -> None:
        self.model_id = "mock"
        self.model_version = model_version
        self.dim = dim

    def embed(self, text: str) -> EmbeddingVector:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingVector]:
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [(digest[i % len(digest)] - 128) / 128.0 for i in range(self.dim)]
            out.append(EmbeddingVector(self.model_id, self.model_version, self.dim, vector))
        return out
