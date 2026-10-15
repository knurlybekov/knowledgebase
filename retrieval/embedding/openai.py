"""OpenAI text embeddings. Fails at construction without an API key."""

from collections.abc import Sequence

from .base import EmbeddingVector


class OpenAIEmbedder:
    def __init__(self, *, api_key: str, model: str, model_version: str, dim: int) -> None:
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is empty; set it or use EMBEDDER=mock.")
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model_id = model
        self.model_version = model_version
        self.dim = dim

    def embed(self, text: str) -> EmbeddingVector:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> list[EmbeddingVector]:
        response = self._client.embeddings.create(
            model=self.model_id, input=list(texts), dimensions=self.dim
        )
        return [
            EmbeddingVector(self.model_id, self.model_version, self.dim, item.embedding)
            for item in response.data
        ]
