"""Wraps fastembed with lazy loading and batching."""

from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path
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
    Model is cached in ~/.cache/fastembed/ (~640MB, ONNX format).
    Thread-safe: uses a lock around model initialization.

    Airgapped / offline use: set CC_MODELS_DIR to a directory containing the
    model folder (e.g. ``CC_MODELS_DIR=/workspace/models``).  The subfolder
    name should be the model basename (``jina-embeddings-v2-base-code``) or
    the full slug (``jinaai-jina-embeddings-v2-base-code``).  On the first
    call, HF_HUB_OFFLINE is set so fastembed skips the download and fails fast
    with a NoSuchFile error containing the exact snapshot path needed; the
    local files are then copied there and the load is retried.
    """

    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name
        self._model: TextEmbedding | None = None
        self._lock = threading.Lock()

    def _seed_from_local(self, error_message: str, models_dir: str) -> bool:
        """Copy local model to the snapshot path extracted from *error_message*.

        fastembed raises an onnxruntime NoSuchFile whose message contains::

            Load model from /full/path/to/onnx/model.onnx failed

        The snapshot directory is two levels above that path (``onnx/model.onnx``).
        Local folder name accepted: model basename or full org-model slug.
        Returns True when files were copied successfully, False otherwise.
        """
        import re

        match = re.search(r"Load model from ([^ ]+) failed", error_message)
        if not match:
            return False

        onnx_path = Path(match.group(1))
        snapshot_dir = onnx_path.parent.parent  # strip onnx/model.onnx

        model_basename = self.model_name.split("/")[-1]
        local_path = Path(models_dir) / model_basename
        if not local_path.exists():
            local_path = Path(models_dir) / self.model_name.replace("/", "-")
        if not local_path.exists():
            logger.warning(
                "CC_MODELS_DIR=%s set but model folder not found (tried %s)",
                models_dir,
                local_path,
            )
            return False

        logger.info("Copying local model from %s to %s ...", local_path, snapshot_dir)
        snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(local_path), str(snapshot_dir))
        logger.info("Local model seeded to fastembed cache.")
        return True

    def _get_model(self) -> "TextEmbedding":
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(
                        "Loading embedding model %s (first use — may download ~640MB)...",
                        self.model_name,
                    )
                    from fastembed import TextEmbedding

                    cache_dir = os.path.expanduser("~/.cache/fastembed")
                    models_dir = os.environ.get("CC_MODELS_DIR", "")

                    if models_dir:
                        # Skip the slow download attempt; fastembed will fail
                        # fast with NoSuchFile so we can seed from CC_MODELS_DIR.
                        os.environ.setdefault("HF_HUB_OFFLINE", "1")

                    try:
                        self._model = TextEmbedding(self.model_name, cache_dir=cache_dir)
                    except Exception as exc:
                        if models_dir and self._seed_from_local(str(exc), models_dir):
                            logger.info("Retrying after seeding local model...")
                            self._model = TextEmbedding(self.model_name, cache_dir=cache_dir)
                        else:
                            raise

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
