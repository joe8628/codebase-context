"""Wraps fastembed with lazy loading and batching."""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from codebase_context.config import EMBED_BATCH_SIZE, EMBED_MODEL

if TYPE_CHECKING:
    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_one(self, text: str) -> list[float]: ...


class Embedder:
    """
    Lazy-loads jinaai/jina-embeddings-v2-base-code via fastembed on first call.
    Uses ONNX Runtime — no torch, no CUDA packages required.
    Model is cached in ~/.cache/fastembed/ (~200MB, ONNX format).
    Thread-safe: uses a lock around model initialization.
    """

    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name
        self._model: TextEmbedding | None = None
        self._lock = threading.Lock()

    def _get_model(self) -> "TextEmbedding":
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(
                        "Loading embedding model %s (first use — may download ~200MB)...",
                        self.model_name,
                    )
                    from fastembed import TextEmbedding
                    cache_dir = os.path.expanduser("~/.cache/fastembed")
                    self._model = TextEmbedding(self.model_name, cache_dir=cache_dir)
                    logger.info("Embedding model loaded.")
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embeds a list of texts in batches of EMBED_BATCH_SIZE.
        Returns list of float vectors (768-dim for jina-v2-base-code).
        Logs progress for batches > 100 items.
        """
        model = self._get_model()
        results: list[list[float]] = []

        for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[batch_start : batch_start + EMBED_BATCH_SIZE]
            if len(texts) > 100:
                logger.info(
                    "Embedding batch %d/%d...",
                    batch_start // EMBED_BATCH_SIZE + 1,
                    (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE,
                )
            results.extend(vec.tolist() for vec in model.embed(batch))

        return results

    def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for single text."""
        return self.embed([text])[0]
