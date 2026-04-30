"""Tests for codebase_context.config constants."""
from __future__ import annotations


def test_memgram_embed_model_constant_exists():
    from codebase_context.config import MEMGRAM_EMBED_MODEL
    assert MEMGRAM_EMBED_MODEL == "jinaai/jina-embeddings-v2-base-code"
