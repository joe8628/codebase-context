"""Tests for the 4 new memory layer MCP tool handlers."""
from __future__ import annotations

import inspect
import json

import codebase_context.mcp_server as mcp_server_mod


MEMORY_TOOL_NAMES = [
    "store_memory",
    "recall_memory",
    "record_change_manifest",
    "get_change_manifest",
]


def test_memory_tool_names_present_in_source():
    src = inspect.getsource(mcp_server_mod)
    for name in MEMORY_TOOL_NAMES:
        assert f'"{name}"' in src, f'Tool name "{name}" not found in mcp_server source'


async def test_handle_store_memory_returns_id(tmp_path):
    from codebase_context.memory_store import MemoryStore
    store = MemoryStore(str(tmp_path))
    result = await mcp_server_mod._handle_store_memory(
        store,
        {"agent": "planner", "event_type": "decision", "content": "Use JWT"},
    )
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert "id" in payload


async def test_handle_recall_memory_returns_events(tmp_path):
    from codebase_context.memory_store import MemoryStore
    store = MemoryStore(str(tmp_path))
    store.store_event("planner", "decision", "Use JWT for authentication")
    result = await mcp_server_mod._handle_recall_memory(
        store,
        {"query": "JWT"},
    )
    assert len(result) == 1
    events = json.loads(result[0].text)
    assert isinstance(events, list)
    assert len(events) == 1
    assert "JWT" in events[0]["content"]


async def test_handle_record_change_manifest_returns_count(tmp_path):
    from codebase_context.memory_store import MemoryStore
    store = MemoryStore(str(tmp_path))
    changes = [
        {"filepath": "auth.py", "change_type": "modified"},
        {"filepath": "utils.py", "change_type": "added"},
    ]
    result = await mcp_server_mod._handle_record_change_manifest(
        store,
        {"task_id": "task-1", "changes": changes},
    )
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert payload["count"] == 2


async def test_handle_get_change_manifest_returns_records(tmp_path):
    from codebase_context.memory_store import MemoryStore
    store = MemoryStore(str(tmp_path))
    store.record_manifest("task-2", [{"filepath": "auth.py", "change_type": "modified"}])
    result = await mcp_server_mod._handle_get_change_manifest(
        store,
        {"task_id": "task-2"},
    )
    assert len(result) == 1
    records = json.loads(result[0].text)
    assert isinstance(records, list)
    assert records[0]["filepath"] == "auth.py"
