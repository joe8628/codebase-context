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


def test_search_finds_by_title(store):
    store.save("Authentication refactor", "changed login flow", "decision")
    store.save("Unrelated memory", "something else", "handoff")
    results = store.search("Authentication")
    assert len(results) == 1
    assert results[0]["title"] == "Authentication refactor"


def test_search_finds_by_content(store):
    store.save("Deploy notes", "updated the redis cache layer", "handoff")
    results = store.search("redis")
    assert len(results) == 1
    assert "redis" in results[0]["content"]


def test_search_with_type_filter(store):
    store.save("Auth decision", "use JWT", "decision")
    store.save("Auth handoff", "completed login", "handoff")
    results = store.search("Auth", type="decision")
    assert len(results) == 1
    assert results[0]["type"] == "decision"


def test_search_empty_when_no_match(store):
    store.save("Something", "unrelated", "handoff")
    results = store.search("xyzzy_no_match")
    assert results == []


def test_session_end_saves_observation(store):
    store.session_end("Completed login feature")
    results = store.context()
    assert len(results) == 1
    assert results[0]["type"] == "session_end"
    assert "Completed login feature" in results[0]["content"]
