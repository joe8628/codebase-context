"""Tests for Embedder._seed_from_local (airgapped model seeding)."""

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


def _no_such_file_error(snapshot_dir: Path) -> str:
    """Build the onnxruntime NoSuchFile message format fastembed emits."""
    onnx = snapshot_dir / "onnx" / "model.onnx"
    return f"[ONNXRuntimeError] : 3 : NO_SUCHFILE : Load model from {onnx} failed: File doesn't exist"


# ---------------------------------------------------------------------------
# _seed_from_local
# ---------------------------------------------------------------------------

def test_copies_model_to_snapshot_path(tmp_path):
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jina-embeddings-v2-base-code")

    snapshot_dir = (
        tmp_path / "cache"
        / "models--jinaai--jina-embeddings-v2-base-code"
        / "snapshots" / "abc123deadbeef"
    )
    error_msg = _no_such_file_error(snapshot_dir)

    embedder = Embedder()
    result = embedder._seed_from_local(error_msg, str(local_models))

    assert result is True
    assert (snapshot_dir / "config.json").exists()
    assert (snapshot_dir / "onnx" / "model.onnx").exists()


def test_returns_false_when_error_message_has_no_path(tmp_path):
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jina-embeddings-v2-base-code")

    embedder = Embedder()
    result = embedder._seed_from_local("some unrelated error", str(local_models))

    assert result is False


def test_returns_false_when_local_model_folder_missing(tmp_path):
    local_models = tmp_path / "models"
    local_models.mkdir()  # exists but empty

    snapshot_dir = tmp_path / "cache" / "snapshots" / "abc"
    error_msg = _no_such_file_error(snapshot_dir)

    embedder = Embedder()
    result = embedder._seed_from_local(error_msg, str(local_models))

    assert result is False
    assert not snapshot_dir.exists()


def test_accepts_full_slug_folder_name(tmp_path):
    """Also works when local folder uses jinaai-jina-embeddings-v2-base-code."""
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jinaai-jina-embeddings-v2-base-code")

    snapshot_dir = tmp_path / "cache" / "snapshots" / "abc"
    error_msg = _no_such_file_error(snapshot_dir)

    embedder = Embedder()
    result = embedder._seed_from_local(error_msg, str(local_models))

    assert result is True
    assert (snapshot_dir / "config.json").exists()


def test_creates_intermediate_snapshot_dirs(tmp_path):
    """snapshot_dir parent (snapshots/) may not exist yet."""
    local_models = tmp_path / "models"
    _make_local_model(local_models, "jina-embeddings-v2-base-code")

    deep_snapshot = tmp_path / "a" / "b" / "c" / "snapshots" / "hash1"
    error_msg = _no_such_file_error(deep_snapshot)

    embedder = Embedder()
    embedder._seed_from_local(error_msg, str(local_models))

    assert (deep_snapshot / "config.json").exists()
