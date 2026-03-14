"""Wraps sentence-transformers with lazy loading and batching."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from codebase_context.config import EMBED_BATCH_SIZE, EMBED_MODEL

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    """
    Lazy-loads jinaai/jina-embeddings-v2-base-code on first call.
    Model is cached in ~/.cache/huggingface (standard HF cache).
    Thread-safe: uses a lock around model initialization.
    """

    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    def _get_model(self) -> "SentenceTransformer":
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(
                        "Loading embedding model %s (first use — may download ~550MB)...",
                        self.model_name,
                    )
                    print(
                        f"[codebase-context] Loading embedding model '{self.model_name}'...\n"
                        f"  First run: downloads ~550MB to ~/.cache/huggingface/\n"
                        f"  Subsequent runs use cached model.",
                        flush=True,
                    )
                    from sentence_transformers import SentenceTransformer
                    self._model = SentenceTransformer(
                        self.model_name,
                        trust_remote_code=True,
                    )
                    logger.info("Embedding model loaded.")
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embeds a list of texts in batches of EMBED_BATCH_SIZE.
        Returns list of float vectors.
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
            vecs = model.encode(batch, show_progress_bar=False)
            results.extend(vec.tolist() for vec in vecs)

        return results

    def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for single text."""
        return self.embed([text])[0]
