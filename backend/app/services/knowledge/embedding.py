from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np

from app.core.config import Settings
from app.services.knowledge.errors import EmbeddingError
from app.services.knowledge.types import EmbeddingBatch


class EmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch: ...


class OpenAIEmbeddingProvider:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if (
            settings.openai_api_key is None
            or not settings.openai_api_key.get_secret_value().strip()
        ):
            raise EmbeddingError("Konfigurasi embedding belum tersedia.")
        self.settings = settings
        owns_client = client is None
        if client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:
                raise EmbeddingError("OpenAI SDK belum tersedia.") from exc
            client = AsyncOpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=settings.embedding_timeout_seconds,
                max_retries=0,
            )
        self.client = client
        self._owns_client = owns_client

    async def close(self) -> None:
        if self._owns_client:
            await self.client.close()

    async def _request(self, texts: Sequence[str]):
        last_error: Exception | None = None
        for attempt in range(1, self.settings.embedding_max_attempts + 1):
            try:
                return await self.client.embeddings.create(
                    model=self.settings.openai_embedding_model,
                    input=list(texts),
                )
            except Exception as exc:
                last_error = exc
                status = getattr(exc, "status_code", None)
                retryable_names = {
                    "APIConnectionError",
                    "APITimeoutError",
                    "InternalServerError",
                    "RateLimitError",
                }
                retryable = (
                    status in {408, 429, 500, 502, 503, 504}
                    or exc.__class__.__name__ in retryable_names
                )
                if not retryable or attempt >= self.settings.embedding_max_attempts:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 4))
        raise EmbeddingError() from last_error

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        if not texts:
            raise EmbeddingError("Tidak ada teks untuk embedding.")
        all_vectors: list[tuple[float, ...]] = []
        request_ids: list[str] = []
        total_input_tokens = 0
        dimension: int | None = None
        for start in range(0, len(texts), self.settings.embedding_batch_size):
            batch = texts[start : start + self.settings.embedding_batch_size]
            response = await self._request(batch)
            ordered = sorted(response.data, key=lambda item: item.index)
            if len(ordered) != len(batch) or [item.index for item in ordered] != list(
                range(len(batch))
            ):
                raise EmbeddingError("Respons embedding tidak lengkap.")
            for item in ordered:
                vector = tuple(float(value) for value in item.embedding)
                if not vector or any(not math.isfinite(value) for value in vector):
                    raise EmbeddingError("Vektor embedding tidak valid.")
                if dimension is None:
                    dimension = len(vector)
                if len(vector) != dimension:
                    raise EmbeddingError("Dimensi embedding tidak konsisten.")
                norm = float(np.linalg.norm(np.asarray(vector, dtype=np.float32)))
                if norm == 0.0 or not math.isfinite(norm):
                    raise EmbeddingError("Vektor embedding tidak valid.")
                all_vectors.append(vector)
            request_id = getattr(response, "_request_id", None) or getattr(
                response, "request_id", None
            )
            if request_id:
                request_ids.append(str(request_id))
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", None) or getattr(
                usage, "total_tokens", None
            )
            if input_tokens is not None:
                total_input_tokens += int(input_tokens)
        if len(all_vectors) != len(texts) or dimension is None:
            raise EmbeddingError("Respons embedding tidak lengkap.")
        return EmbeddingBatch(
            vectors=tuple(all_vectors),
            model=self.settings.openai_embedding_model,
            vector_dimension=dimension,
            request_ids=tuple(request_ids),
            input_tokens=total_input_tokens or None,
        )


def normalized_matrix(batch: EmbeddingBatch) -> np.ndarray:
    matrix = np.asarray(batch.vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise EmbeddingError("Matriks embedding tidak valid.")
    if not np.all(np.isfinite(matrix)):
        raise EmbeddingError("Matriks embedding tidak valid.")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0) or not np.all(np.isfinite(norms)):
        raise EmbeddingError("Matriks embedding tidak valid.")
    return matrix / norms
