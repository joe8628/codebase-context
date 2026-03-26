"""Wraps fastembed with lazy loading and batching."""

from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from codebase_context.config import EMBED_BATCH_SIZE, EMBED_MODEL
from codebase_context.utils import find_project_root

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
    the full slug (``jinaai-jina-embeddings-v2-base-code``).  The files are
    copied into the HF hub cache structure before fastembed is initialised;
    HF_HUB_OFFLINE=1 is then set so no download is attempted.
    """

    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name
        self._model: TextEmbedding | None = None
        self._lock = threading.Lock()

    def _seed_local_to_hf_cache(self, cache_dir: str, models_dir: str) -> bool:
        """Proactively copy local model files into the HF hub cache structure.

        Creates::

            {cache_dir}/models--{org}--{model}/
                refs/main          ← contains "local"
                snapshots/local/   ← copy of the local model folder

        huggingface_hub (with ``HF_HUB_OFFLINE=1``) reads ``refs/main`` to
        resolve the snapshot path; finding the files there, fastembed loads
        the model without any network access.

        Is a no-op if ``refs/main`` already exists (model already seeded or
        previously downloaded).  Accepts a local folder named either after the
        model basename (``jina-embeddings-v2-base-code``) or the full slug
        (``jinaai-jina-embeddings-v2-base-code``).

        Returns True when the cache is ready, False when the local folder is
        not found.
        """
        # HF hub cache dir name: models--{org}--{model}  (/ → --)
        model_dir = Path(cache_dir) / ("models--" + self.model_name.replace("/", "--"))
        refs_main = model_dir / "refs" / "main"

        if refs_main.exists():
            # Verify the snapshot the ref points to is actually complete.
            # A partial download leaves refs/main in place but no onnx file.
            current_hash = refs_main.read_text().strip()
            onnx_file = model_dir / "snapshots" / current_hash / "onnx" / "model.onnx"
            if onnx_file.exists():
                return True  # Fully cached — nothing to do

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

        revision = "local"
        snapshot_dir = model_dir / "snapshots" / revision

        logger.info("Seeding fastembed cache from local model at %s ...", local_path)
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(local_path), str(snapshot_dir), dirs_exist_ok=True)
        refs_main.parent.mkdir(parents=True, exist_ok=True)
        refs_main.write_text(revision)
        logger.info("Local model seeded to fastembed cache at %s.", snapshot_dir)
        return True

    def _resolve_models_dir(self) -> str:
        """Return the models directory to use for local seeding.

        Resolution order:
        1. ``CC_MODELS_DIR`` environment variable (explicit override).
        2. ``models/`` folder inside the project root (auto-detected via
           the nearest ``.git`` directory from the current working directory).
        3. Empty string — no local seeding, fastembed will attempt a download.
        """
        models_dir = os.environ.get("CC_MODELS_DIR", "")
        if models_dir:
            return models_dir
        try:
            project_root = find_project_root()
            candidate = Path(project_root) / "models"
            if candidate.is_dir():
                return str(candidate)
        except Exception as exc:
            logger.debug("Could not auto-detect project root for models/ lookup: %s", exc)
        return ""

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
                    models_dir = self._resolve_models_dir()

                    if models_dir and self._seed_local_to_hf_cache(cache_dir, models_dir):
                        # Cache is ready; prevent any download attempt.
                        os.environ.setdefault("HF_HUB_OFFLINE", "1")

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
