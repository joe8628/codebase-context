"""Tests for all Layer 3 MCP tool handlers in mcp_server."""
from __future__ import annotations

import inspect
import json
import pytest

import codebase_context.mcp_server as mcp_server_mod

NARRATIVE_TOOL_NAMES = [
    "narrative_save",
    "narrative_context",
    "narrative_search",
    "narrative_session_end",
]

COORD_TOOL_NAMES = [
    "coord_store_event",
    "coord_recall_events",
    "coord_record_manifest",
    "coord_get_manifest",
]

OLD_TOOL_NAMES = [
    "store_memory",
    "recall_memory",
    "record_change_manifest",
    "get_change_manifest",
    "mem_save",
    "mem_context",
    "mem_search",
    "mem_session_end",
]


def test_narrative_tool_names_in_source():
    src = inspect.getsource(mcp_server_mod)
    for name in NARRATIVE_TOOL_NAMES:
        assert f'"{name}"' in src, f'Narrative tool "{name}" not found in mcp_server source'


def test_coord_tool_names_in_source():
    src = inspect.getsource(mcp_server_mod)
    for name in COORD_TOOL_NAMES:
        assert f'"{name}"' in src, f'Coord tool "{name}" not found in mcp_server source'


def test_old_tool_names_absent_from_source():
    src = inspect.getsource(mcp_server_mod)
    for name in OLD_TOOL_NAMES:
        assert f'name="{name}"' not in src, \
            f'Old tool name "{name}" still registered — should be renamed'


async def test_handle_narrative_save_returns_id(tmp_path):
    from codebase_context.memgram.store import MemgramStore
    store = MemgramStore(str(tmp_path))
    result = await mcp_server_mod._handle_narrative_save(
        store, {"title": "Fixed auth bug", "content": "Root cause was X", "type": "bugfix"}
    )
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert payload["saved"] is True
    assert isinstance(payload["id"], int)


async def test_handle_narrative_context_returns_formatted(tmp_path):
    from codebase_context.memgram.store import MemgramStore
    store = MemgramStore(str(tmp_path))
    store.save("Session note", "We refactored auth", "handoff")
    result = await mcp_server_mod._handle_narrative_context(store, {})
    assert len(result) == 1
    assert "Session note" in result[0].text


async def test_handle_narrative_context_empty(tmp_path):
    from codebase_context.memgram.store import MemgramStore
    store = MemgramStore(str(tmp_path))
    result = await mcp_server_mod._handle_narrative_context(store, {})
    assert "No memories" in result[0].text


async def test_handle_narrative_search_returns_results(tmp_path):
    from codebase_context.memgram.store import MemgramStore
    store = MemgramStore(str(tmp_path))
    store.save("Auth fix", "Fixed JWT handling", "bugfix")
    result = await mcp_server_mod._handle_narrative_search(store, {"query": "JWT"})
    assert "Auth fix" in result[0].text


async def test_handle_narrative_session_end_returns_success(tmp_path):
    from codebase_context.memgram.store import MemgramStore
    store = MemgramStore(str(tmp_path))
    result = await mcp_server_mod._handle_narrative_session_end(
        store, {"summary": "Completed auth refactor"}
    )
    payload = json.loads(result[0].text)
    assert payload["session_ended"] is True


async def test_handle_coord_store_event_returns_id(tmp_path):
    from codebase_context.memory_store import MemoryStore
    store = MemoryStore(str(tmp_path))
    result = await mcp_server_mod._handle_coord_store_event(
        store,
        {"agent": "planner", "event_type": "decision", "content": "Use JWT"},
    )
    payload = json.loads(result[0].text)
    assert "id" in payload


async def test_handle_coord_recall_events_returns_list(tmp_path):
    from codebase_context.memory_store import MemoryStore
    store = MemoryStore(str(tmp_path))
    store.store_event("planner", "decision", "Use JWT for authentication")
    result = await mcp_server_mod._handle_coord_recall_events(store, {"query": "JWT"})
    events = json.loads(result[0].text)
    assert isinstance(events, list)
    assert "JWT" in events[0]["content"]


async def test_handle_coord_record_manifest_returns_count(tmp_path):
    from codebase_context.memory_store import MemoryStore
    store = MemoryStore(str(tmp_path))
    changes = [
        {"filepath": "auth.py", "change_type": "modified"},
        {"filepath": "utils.py", "change_type": "added"},
    ]
    result = await mcp_server_mod._handle_coord_record_manifest(
        store, {"task_id": "task-1", "changes": changes}
    )
    assert json.loads(result[0].text)["count"] == 2


async def test_handle_coord_get_manifest_returns_records(tmp_path):
    from codebase_context.memory_store import MemoryStore
    store = MemoryStore(str(tmp_path))
    store.record_manifest("task-2", [{"filepath": "auth.py", "change_type": "modified"}])
    result = await mcp_server_mod._handle_coord_get_manifest(store, {"task_id": "task-2"})
    records = json.loads(result[0].text)
    assert records[0]["filepath"] == "auth.py"
