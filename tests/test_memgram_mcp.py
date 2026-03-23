"""Unit tests for memgram MCP tool handlers."""
from __future__ import annotations

import json
import pytest
from codebase_context.memgram.store import MemgramStore
from codebase_context.memgram.mcp_server import (
    _handle_mem_save,
    _handle_mem_context,
    _handle_mem_search,
    _handle_mem_session_end,
)


@pytest.fixture()
def store(tmp_path):
    return MemgramStore(str(tmp_path / "memgram.db"))


@pytest.mark.asyncio
async def test_mem_save_returns_confirmation(store):
    result = await _handle_mem_save(store, {"title": "Fixed bug", "content": "details", "type": "bugfix"})
    assert len(result) == 1
    data = json.loads(result[0].text)
    assert data["saved"] is True
    assert isinstance(data["id"], int)


@pytest.mark.asyncio
async def test_mem_save_uses_default_type(store):
    result = await _handle_mem_save(store, {"title": "Completed feature", "content": "done"})
    data = json.loads(result[0].text)
    assert data["saved"] is True
    # verify the default type was stored
    memories = store.context()
    assert memories[0]["type"] == "handoff"


@pytest.mark.asyncio
async def test_mem_context_returns_formatted_text(store):
    store.save("Alpha memory", "some detail", "handoff")
    result = await _handle_mem_context(store, {})
    assert len(result) == 1
    text = result[0].text
    assert "Alpha memory" in text
    assert "handoff" in text


@pytest.mark.asyncio
async def test_mem_context_empty_message_on_no_memories(store):
    result = await _handle_mem_context(store, {})
    assert "No memories" in result[0].text


@pytest.mark.asyncio
async def test_mem_search_returns_matches(store):
    store.save("Login flow refactor", "changed OAuth", "decision")
    result = await _handle_mem_search(store, {"query": "OAuth"})
    text = result[0].text
    assert "Login flow refactor" in text


@pytest.mark.asyncio
async def test_mem_search_with_type_filter(store):
    store.save("Auth decision", "use JWT", "decision")
    store.save("Auth handoff", "completed", "handoff")
    result = await _handle_mem_search(store, {"query": "Auth", "type": "decision"})
    text = result[0].text
    assert "Auth decision" in text
    assert "Auth handoff" not in text


@pytest.mark.asyncio
async def test_mem_search_no_results_message(store):
    result = await _handle_mem_search(store, {"query": "xyzzy_nomatch"})
    assert "No results" in result[0].text


@pytest.mark.asyncio
async def test_mem_session_end_returns_confirmation(store):
    result = await _handle_mem_session_end(store, {"summary": "Session done"})
    data = json.loads(result[0].text)
    assert data["session_ended"] is True
    # verify it was stored
    memories = store.context()
    assert any(m["type"] == "session_end" for m in memories)
