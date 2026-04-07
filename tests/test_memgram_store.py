"""Unit tests for MemgramStore."""
from __future__ import annotations

import time
import pytest
from codebase_context.memgram.store import MemgramStore, VALID_OBSERVATION_TYPES


@pytest.fixture()
def store(tmp_path):
    return MemgramStore(str(tmp_path))


def test_save_returns_id(store):
    id_ = store.save("Fixed login bug", "Root cause was X", "bugfix")
    assert isinstance(id_, int)
    assert id_ >= 1


def test_save_increments_id(store):
    id1 = store.save("First", "content A", "handoff")
    id2 = store.save("Second", "content B", "decision")
    assert id2 > id1


def test_save_rejects_unknown_type(store):
    with pytest.raises(ValueError, match="Unknown type"):
        store.save("Title", "Content", "invalid_type")


def test_valid_observation_types_contains_expected():
    assert "handoff" in VALID_OBSERVATION_TYPES
    assert "decision" in VALID_OBSERVATION_TYPES
    assert "bugfix" in VALID_OBSERVATION_TYPES
    assert "architecture" in VALID_OBSERVATION_TYPES
    assert "discovery" in VALID_OBSERVATION_TYPES
    assert "session_end" in VALID_OBSERVATION_TYPES


def test_created_at_is_unix_integer(store):
    before = int(time.time())
    store.save("Test", "Content", "handoff")
    after = int(time.time())
    result = store.context()[0]
    assert isinstance(result["created_at"], int)
    assert before <= result["created_at"] <= after


def test_db_file_in_codebase_context_dir(tmp_path):
    MemgramStore(str(tmp_path))
    assert (tmp_path / ".codebase-context" / "memgram.db").exists()


def test_context_empty_on_fresh_db(store):
    assert store.context() == []


def test_context_returns_saved_memories(store):
    store.save("Alpha", "detail A", "handoff")
    store.save("Beta", "detail B", "decision")
    results = store.context()
    assert len(results) == 2
    assert results[0]["title"] == "Beta"
    assert results[1]["title"] == "Alpha"


def test_context_respects_limit(store):
    for i in range(15):
        store.save(f"Memory {i}", "content", "handoff")
    assert len(store.context(limit=5)) == 5


def test_context_result_has_required_fields(store):
    store.save("Test title", "Test content", "discovery")
    result = store.context()[0]
    for field in ("id", "title", "content", "type", "created_at"):
        assert field in result


def test_search_finds_by_title(store):
    store.save("Authentication refactor", "changed login flow", "decision")
    store.save("Unrelated memory", "something else", "handoff")
    results = store.search("Authentication")
    assert len(results) == 1
    assert results[0]["title"] == "Authentication refactor"
    assert "id" in results[0]


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
    assert store.search("xyzzy_no_match") == []


def test_session_end_saves_observation(store):
    store.session_end("Completed login feature")
    results = store.context()
    assert len(results) == 1
    assert results[0]["type"] == "session_end"
    assert "Completed login feature" in results[0]["content"]
