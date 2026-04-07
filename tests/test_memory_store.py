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


# --- Tasks ---

def test_create_and_get_task(store):
    store.create_task("task-1", "dev-agent", {"file": "auth.py"})
    task = store.get_task("task-1")
    assert task is not None
    assert task["id"] == "task-1"
    assert task["status"] == "pending"
    assert task["agent"] == "dev-agent"
    assert task["payload"] == {"file": "auth.py"}


def test_get_task_returns_none_for_unknown(store):
    assert store.get_task("nonexistent") is None


def test_update_task_status(store):
    store.create_task("task-2", "dev-agent", {})
    store.update_task_status("task-2", "in_flight")
    task = store.get_task("task-2")
    assert task["status"] == "in_flight"


def test_list_tasks_returns_all(store):
    store.create_task("t1", "planner", {})
    store.create_task("t2", "dev-agent", {})
    tasks = store.list_tasks()
    assert len(tasks) == 2


def test_list_tasks_filter_by_status(store):
    store.create_task("t3", "planner", {})
    store.create_task("t4", "dev-agent", {})
    store.update_task_status("t4", "done")
    pending = store.list_tasks(status="pending")
    assert len(pending) == 1
    assert pending[0]["id"] == "t3"


def test_task_has_required_fields(store):
    store.create_task("task-x", "reviewer", {"key": "val"})
    task = store.get_task("task-x")
    assert "id" in task
    assert "status" in task
    assert "agent" in task
    assert "payload" in task
    assert "created_at" in task
    assert "updated_at" in task


# --- Change manifests ---

def test_record_manifest_returns_count(store):
    changes = [
        {"filepath": "auth.py", "change_type": "modified", "symbol_name": "login"},
        {"filepath": "utils.py", "change_type": "added", "symbol_name": "hash_password"},
    ]
    count = store.record_manifest("task-cm-1", changes)
    assert count == 2


def test_get_manifest_returns_records(store):
    changes = [
        {
            "filepath": "auth.py",
            "change_type": "modified",
            "symbol_name": "login",
            "old_signature": "def login(email)",
            "new_signature": "def login(email, mfa)",
        },
    ]
    store.record_manifest("task-cm-2", changes)
    records = store.get_manifest("task-cm-2")
    assert len(records) == 1
    assert records[0]["filepath"] == "auth.py"
    assert records[0]["change_type"] == "modified"
    assert records[0]["symbol_name"] == "login"
    assert records[0]["old_signature"] == "def login(email)"
    assert records[0]["new_signature"] == "def login(email, mfa)"


def test_get_manifest_empty_for_unknown_task(store):
    assert store.get_manifest("nonexistent-task") == []


def test_get_manifest_scoped_to_task(store):
    store.record_manifest("task-a", [{"filepath": "a.py", "change_type": "added"}])
    store.record_manifest("task-b", [{"filepath": "b.py", "change_type": "modified"}])
    records = store.get_manifest("task-a")
    assert len(records) == 1
    assert records[0]["filepath"] == "a.py"


def test_manifest_record_has_required_fields(store):
    store.record_manifest("task-fields", [{"filepath": "model.py", "change_type": "deleted"}])
    record = store.get_manifest("task-fields")[0]
    assert "filepath" in record
    assert "symbol_name" in record
    assert "change_type" in record
    assert "old_signature" in record
    assert "new_signature" in record


def test_valid_event_types_constant_exists():
    from codebase_context.memory_store import VALID_EVENT_TYPES
    assert "task_started" in VALID_EVENT_TYPES
    assert "task_completed" in VALID_EVENT_TYPES
    assert "task_failed" in VALID_EVENT_TYPES
    assert "agent_action" in VALID_EVENT_TYPES
    assert "decision" in VALID_EVENT_TYPES
    assert "error" in VALID_EVENT_TYPES


def test_store_event_rejects_unknown_type(store):
    with pytest.raises(ValueError, match="Unknown event_type"):
        store.store_event("planner", "invalid_type", "some content")
