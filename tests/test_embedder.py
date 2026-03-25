"""Tests for Embedder._seed_local_to_hf_cache (airgapped model seeding)."""

from __future__ import annotations

from pathlib import Path

import pytest

from codebase_context.embedder import Embedder


def _make_local_model(base: Path, folder_name: str) -> Path:
    model_dir = base / folder_name
    (model_dir / "onnx").mkdir(parents=True)
    (model_dir / "config.json").write_text("{}")
    (model_dir / "tokenizer.json").write_text("{}")
    (model_dir / "onnx" / "model.onnx").write_bytes(b"fake-onnx")
    return model_dir


# ---------------------------------------------------------------------------
# _seed_local_to_hf_cache
# ---------------------------------------------------------------------------

def test_creates_hf_cache_structure(tmp_path):
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jina-embeddings-v2-base-code")

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    embedder = Embedder()
    result = embedder._seed_local_to_hf_cache(str(cache_dir), str(local_models))

    assert result is True
    model_dir = cache_dir / "models--jinaai--jina-embeddings-v2-base-code"
    assert (model_dir / "refs" / "main").read_text() == "local"
    assert (model_dir / "snapshots" / "local" / "config.json").exists()
    assert (model_dir / "snapshots" / "local" / "onnx" / "model.onnx").exists()


def test_no_op_when_snapshot_already_complete(tmp_path):
    """When refs/main points to a snapshot that has the onnx file, skip seeding."""
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jina-embeddings-v2-base-code")

    cache_dir = tmp_path / "cache"
    model_dir = cache_dir / "models--jinaai--jina-embeddings-v2-base-code"
    existing_hash = "516f4baf13dec4ddddda8631e019b5737c8bc250"
    snapshot = model_dir / "snapshots" / existing_hash
    (snapshot / "onnx").mkdir(parents=True)
    (snapshot / "onnx" / "model.onnx").write_bytes(b"real-onnx")
    refs_main = model_dir / "refs" / "main"
    refs_main.parent.mkdir(parents=True)
    refs_main.write_text(existing_hash)

    embedder = Embedder()
    result = embedder._seed_local_to_hf_cache(str(cache_dir), str(local_models))

    assert result is True
    assert refs_main.read_text() == existing_hash  # not overwritten


def test_reseeds_when_snapshot_is_incomplete(tmp_path):
    """refs/main exists but onnx file is missing (partial download) — should seed."""
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jina-embeddings-v2-base-code")

    cache_dir = tmp_path / "cache"
    model_dir = cache_dir / "models--jinaai--jina-embeddings-v2-base-code"
    stale_hash = "516f4baf13dec4ddddda8631e019b5737c8bc250"
    # Snapshot dir exists but no onnx file (partial download)
    (model_dir / "snapshots" / stale_hash).mkdir(parents=True)
    refs_main = model_dir / "refs" / "main"
    refs_main.parent.mkdir(parents=True)
    refs_main.write_text(stale_hash)

    embedder = Embedder()
    result = embedder._seed_local_to_hf_cache(str(cache_dir), str(local_models))

    assert result is True
    # refs/main now points to "local" and the onnx file is present
    assert refs_main.read_text() == "local"
    assert (model_dir / "snapshots" / "local" / "onnx" / "model.onnx").exists()


def test_returns_false_when_local_model_folder_missing(tmp_path):
    local_models = tmp_path / "models"
    local_models.mkdir()  # exists but empty

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    embedder = Embedder()
    result = embedder._seed_local_to_hf_cache(str(cache_dir), str(local_models))

    assert result is False
    assert not (cache_dir / "models--jinaai--jina-embeddings-v2-base-code").exists()


def test_accepts_full_slug_folder_name(tmp_path):
    """Also works when local folder uses jinaai-jina-embeddings-v2-base-code."""
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jinaai-jina-embeddings-v2-base-code")

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    embedder = Embedder()
    result = embedder._seed_local_to_hf_cache(str(cache_dir), str(local_models))

    assert result is True
    model_dir = cache_dir / "models--jinaai--jina-embeddings-v2-base-code"
    assert (model_dir / "snapshots" / "local" / "config.json").exists()


def test_idempotent_on_repeated_calls(tmp_path):
    """Calling twice does not raise even if snapshot dir already exists."""
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jina-embeddings-v2-base-code")

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    embedder = Embedder()
    embedder._seed_local_to_hf_cache(str(cache_dir), str(local_models))
    # Second call must not raise (refs/main already exists → early return)
    result = embedder._seed_local_to_hf_cache(str(cache_dir), str(local_models))
    assert result is True
