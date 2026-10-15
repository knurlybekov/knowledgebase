"""Embedder protocol. A concrete embedder declares model_id, model_version and
dim. Retrieval never mixes vectors across (model_id, model_version)."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class EmbeddingVector:
    model_id: str
    model_version: str
    dim: int
    vector: list[float]


@runtime_checkable
class Embedder(Protocol):
    model_id: str
    model_version: str
    dim: int

    def embed(self, text: str) -> EmbeddingVector: ...

    def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingVector]: ...
