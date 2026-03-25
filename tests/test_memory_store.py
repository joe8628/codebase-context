"""Unit tests for MemoryStore — schema, events, tasks, and change manifests."""
from __future__ import annotations

import pytest

from codebase_context.memory_store import MemoryStore


@pytest.fixture()
def store(tmp_path):
    return MemoryStore(str(tmp_path))


# --- Schema ---

def test_store_can_be_instantiated(tmp_path):
    store = MemoryStore(str(tmp_path))
    assert store is not None


# --- Events ---

def test_store_event_returns_string_id(store):
    id_ = store.store_event("planner", "decision", "Use JWT for auth")
    assert isinstance(id_, str)
    assert id_ != ""


def test_store_event_ids_are_unique(store):
    id1 = store.store_event("planner", "decision", "content A")
    id2 = store.store_event("dev-agent", "handoff", "content B")
    assert id1 != id2


def test_search_events_finds_by_content(store):
    store.store_event("planner", "decision", "Use JWT for authentication")
    results = store.search_events("JWT")
    assert len(results) == 1
    assert "JWT" in results[0]["content"]


def test_search_events_returns_required_fields(store):
    store.store_event("planner", "decision", "Deploy pipeline updated")
    result = store.search_events("pipeline")[0]
    assert "id" in result
    assert "agent" in result
    assert "event_type" in result
    assert "content" in result
    assert "task_id" in result
    assert "created_at" in result


def test_search_events_filter_by_agent(store):
    store.store_event("planner", "decision", "planning notes")
    store.store_event("dev-agent", "handoff", "planning notes")
    results = store.search_events("planning", agent="planner")
    assert len(results) == 1
    assert results[0]["agent"] == "planner"


def test_search_events_filter_by_event_type(store):
    store.store_event("planner", "decision", "planning notes")
    store.store_event("planner", "handoff", "planning notes")
    results = store.search_events("planning", event_type="decision")
    assert len(results) == 1
    assert results[0]["event_type"] == "decision"


def test_search_events_empty_when_no_match(store):
    store.store_event("planner", "decision", "unrelated content")
    results = store.search_events("xyzzy_no_match_at_all")
    assert results == []


def test_search_events_respects_limit(store):
    for i in range(5):
        store.store_event("planner", "decision", f"event {i} about authentication")
    results = store.search_events("authentication", limit=3)
    assert len(results) <= 3
