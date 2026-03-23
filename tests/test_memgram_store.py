"""Unit tests for MemgramStore."""
from __future__ import annotations

import pytest
from codebase_context.memgram.store import MemgramStore


@pytest.fixture()
def store(tmp_path):
    return MemgramStore(str(tmp_path / "memgram.db"))


def test_save_returns_id(store):
    id_ = store.save("Fixed login bug", "Root cause was X", "bugfix")
    assert isinstance(id_, int)
    assert id_ >= 1


def test_save_increments_id(store):
    id1 = store.save("First", "content A", "handoff")
    id2 = store.save("Second", "content B", "decision")
    assert id2 > id1


def test_context_empty_on_fresh_db(store):
    results = store.context()
    assert results == []


def test_context_returns_saved_memories(store):
    store.save("Alpha", "detail A", "handoff")
    store.save("Beta", "detail B", "decision")
    results = store.context()
    assert len(results) == 2
    # Most recent first
    assert results[0]["title"] == "Beta"
    assert results[1]["title"] == "Alpha"


def test_context_respects_limit(store):
    for i in range(15):
        store.save(f"Memory {i}", "content", "handoff")
    results = store.context(limit=5)
    assert len(results) == 5


def test_context_result_has_required_fields(store):
    store.save("Test title", "Test content", "discovery")
    result = store.context()[0]
    assert "id" in result
    assert "title" in result
    assert "content" in result
    assert "type" in result
    assert "created_at" in result
