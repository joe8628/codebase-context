# ccindex Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate `ccindex mem-serve` (memgram) into the single `ccindex serve` process, rename all Layer 3 MCP tools to semantic prefixes (`narrative_*` / `coord_*`), remove 5 LSP MCP tools, switch repo map to on-demand access, and fix all Layer 3 bugs (thread safety, FTS5 divergence, timestamp inconsistency, unenforced types).

**Architecture:** `MemgramStore` is rewritten to use standalone FTS5 (same pattern as `MemoryStore.events`) and adopts `db.py` threading.local connections. Both stores live in `.codebase-context/` (two separate DB files). The main `mcp_server.py` grows to host all 11 MCP tools: 3 Layer 1, 4 narrative (`narrative_*`), 4 coordination (`coord_*`). LSP tools are removed from the MCP surface. `ccindex upgrade` removes the stale `memgram` settings entry; `ccindex migrate` moves the old `memgram.db` file.

**Tech Stack:** Python 3.11+, SQLite FTS5, `threading.local`, Click CLI, mcp library

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `codebase_context/db.py` | Add `db_filename` param; update threading.local key |
| Modify | `codebase_context/memgram/store.py` | Standalone FTS5, db.py, type validation, Unix timestamps |
| Modify | `codebase_context/memory_store.py` | Add `VALID_EVENT_TYPES`; validate `event_type` in `store_event` |
| Modify | `codebase_context/mcp_server.py` | Add 4 narrative tools; rename 4 coord tools; remove 5 LSP tools; old-schema detection |
| Modify | `codebase_context/migrate.py` | Use new `MemgramStore(project_root)` API; add memgram.db file move |
| Modify | `codebase_context/cli.py` | `upgrade` removes stale memgram entry; `init` drops `@`-ref prompt; session protocol uses `narrative_*` names |
| Modify | `CLAUDE.md` | Remove `@.codebase-context/repo_map.md`; add navigation hint; update session protocol tool names |
| Modify | `tests/test_db.py` | Test `db_filename` parameter |
| Modify | `tests/test_memgram_store.py` | Update fixture to `MemgramStore(project_root)`; add type-validation and timestamp tests |
| Modify | `tests/test_mcp_memory_tools.py` | Rename tool assertions to `coord_*`; add `narrative_*` tests |
| Replace | `tests/test_mcp_lsp_tools.py` | Assert LSP tools ABSENT from `mcp_server` source |
| Modify | `tests/test_migrate.py` | Add memgram.db archiving test |
| Modify | `tests/test_cli.py` | Add `TestUpgradeSettingsCleanup`; update `TestSetupMemgram` to verify memgram NOT registered in init |

---

## Task 1: Extend `db.py` with `db_filename` parameter

**Files:**
- Modify: `codebase_context/db.py`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_db.py`:

```python
def test_db_filename_creates_named_db_file(tmp_path):
    from codebase_context.db import get_connection
    get_connection(str(tmp_path), db_filename="memgram.db")
    assert (tmp_path / ".codebase-context" / "memgram.db").exists()

def test_different_filenames_return_different_connections(tmp_path):
    from codebase_context.db import get_connection
    conn1 = get_connection(str(tmp_path), db_filename="memory.db")
    conn2 = get_connection(str(tmp_path), db_filename="memgram.db")
    assert conn1 is not conn2

def test_same_filename_same_thread_returns_cached_connection(tmp_path):
    from codebase_context.db import get_connection
    conn1 = get_connection(str(tmp_path), db_filename="memgram.db")
    conn2 = get_connection(str(tmp_path), db_filename="memgram.db")
    assert conn1 is conn2

def test_default_filename_is_memory_db(tmp_path):
    from codebase_context.db import get_connection
    get_connection(str(tmp_path))
    assert (tmp_path / ".codebase-context" / "memory.db").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db.py -k "db_filename or named_db or different_filenames or cached_connection or default_filename" -v
```

Expected: FAIL — `get_connection() got unexpected keyword argument 'db_filename'`

- [ ] **Step 3: Rewrite `codebase_context/db.py`**

```python
"""Per-thread SQLite connection manager for the memory layer."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_local = threading.local()


def get_connection(project_root: str, db_filename: str = "memory.db") -> sqlite3.Connection:
    """Return a per-thread SQLite connection for the given project root and db file.

    Each (project_root, db_filename) pair gets its own per-thread connection.
    WAL mode allows concurrent readers alongside a single writer.
    """
    key = f"conn_{project_root}_{db_filename}"
    if not hasattr(_local, key):
        path = Path(project_root) / ".codebase-context" / db_filename
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        setattr(_local, key, conn)
    return getattr(_local, key)
```

- [ ] **Step 4: Run the full db test suite**

```bash
pytest tests/test_db.py -v
```

Expected: All PASS

- [ ] **Step 5: Verify existing tests still pass**

```bash
pytest tests/ -x -q
```

Expected: All PASS (the default `db_filename="memory.db"` keeps backward compat)

- [ ] **Step 6: Commit**

```bash
git add codebase_context/db.py tests/test_db.py
git commit -m "feat: extend db.get_connection with db_filename parameter"
```

---

## Task 2: Rewrite `MemgramStore` (standalone FTS5 + db.py + type validation + Unix timestamps)

**Files:**
- Modify: `codebase_context/memgram/store.py`
- Modify: `tests/test_memgram_store.py`

- [ ] **Step 1: Write failing tests**

Replace the entire `tests/test_memgram_store.py` with:

```python
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


def test_valid_observation_types_contains_expected(store):
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
```

- [ ] **Step 2: Run to verify failures**

```bash
pytest tests/test_memgram_store.py -v
```

Expected: Multiple FAILs — `MemgramStore` still takes `db_path`, no `VALID_OBSERVATION_TYPES`, etc.

- [ ] **Step 3: Rewrite `codebase_context/memgram/store.py`**

```python
"""SQLite-backed narrative memory store with standalone FTS5."""
from __future__ import annotations

import time

VALID_OBSERVATION_TYPES = {
    "handoff", "decision", "bugfix", "architecture", "discovery", "session_end"
}

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS observations USING fts5(
    title,
    content,
    type     UNINDEXED,
    created_at UNINDEXED
);
"""


class MemgramStore:
    def __init__(self, project_root: str) -> None:
        from codebase_context.db import get_connection
        self._project_root = project_root
        conn = get_connection(project_root, db_filename="memgram.db")
        conn.executescript(_SCHEMA)
        conn.commit()

    def _conn(self):
        from codebase_context.db import get_connection
        return get_connection(self._project_root, db_filename="memgram.db")

    def save(self, title: str, content: str, type: str = "handoff") -> int:
        """Insert an observation. Returns the rowid."""
        if type not in VALID_OBSERVATION_TYPES:
            raise ValueError(
                f"Unknown type {type!r}. Valid: {sorted(VALID_OBSERVATION_TYPES)}"
            )
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO observations (title, content, type, created_at) VALUES (?, ?, ?, ?)",
            (title, content, type, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def context(self, limit: int = 10) -> list[dict]:
        """Return the *limit* most recent observations, newest first."""
        rows = self._conn().execute(
            "SELECT rowid AS id, title, content, type, created_at "
            "FROM observations ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, type: str | None = None, limit: int = 10) -> list[dict]:
        """Full-text search over title and content. Optionally filter by type."""
        conn = self._conn()
        if type is not None:
            rows = conn.execute(
                "SELECT rowid AS id, title, content, type, created_at "
                "FROM observations WHERE observations MATCH ? AND type = ? "
                "ORDER BY rank LIMIT ?",
                (query, type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT rowid AS id, title, content, type, created_at "
                "FROM observations WHERE observations MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def session_end(self, summary: str) -> None:
        """Record a session-end observation with the given summary."""
        self.save("Session ended", summary, "session_end")
```

- [ ] **Step 4: Run the memgram store tests**

```bash
pytest tests/test_memgram_store.py -v
```

Expected: All PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -x -q
```

Expected: All PASS (except `test_migrate.py` which still passes `.claude/memgram.db` — that's fixed in Task 5)

- [ ] **Step 6: Commit**

```bash
git add codebase_context/memgram/store.py tests/test_memgram_store.py
git commit -m "feat: rewrite MemgramStore — standalone FTS5, db.py threading, type validation, Unix timestamps"
```

---

## Task 3: Add `VALID_EVENT_TYPES` and type validation to `MemoryStore`

**Files:**
- Modify: `codebase_context/memory_store.py`
- Modify: `tests/test_memory_store.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_memory_store.py`:

```python
from codebase_context.memory_store import VALID_EVENT_TYPES

def test_valid_event_types_constant_exists():
    assert "task_started" in VALID_EVENT_TYPES
    assert "task_completed" in VALID_EVENT_TYPES
    assert "task_failed" in VALID_EVENT_TYPES
    assert "agent_action" in VALID_EVENT_TYPES
    assert "decision" in VALID_EVENT_TYPES
    assert "error" in VALID_EVENT_TYPES

def test_store_event_rejects_unknown_type(store):
    with pytest.raises(ValueError, match="Unknown event_type"):
        store.store_event("planner", "invalid_type", "some content")
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_memory_store.py -k "valid_event or rejects_unknown" -v
```

Expected: FAIL — `cannot import name 'VALID_EVENT_TYPES'` and `store_event` does not raise

- [ ] **Step 3: Add constant and validation to `codebase_context/memory_store.py`**

Add after the `from __future__ import annotations` block:

```python
VALID_EVENT_TYPES = {
    "task_started", "task_completed", "task_failed",
    "agent_action", "decision", "error"
}
```

Update `store_event` (lines ~53–68) to validate `event_type`:

```python
def store_event(
    self,
    agent: str,
    event_type: str,
    content: str,
    task_id: str | None = None,
) -> str:
    """Insert a session event. Returns the row ID as a string."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Unknown event_type {event_type!r}. Valid: {sorted(VALID_EVENT_TYPES)}"
        )
    self._conn.execute(
        "INSERT INTO events (agent, event_type, content, task_id, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent, event_type, content, task_id or "", str(int(time.time()))),
    )
    self._conn.commit()
    row = self._conn.execute("SELECT last_insert_rowid()").fetchone()
    return str(row[0])
```

> **Note:** Read lines 53–80 of `memory_store.py` before editing to confirm the exact current `store_event` body. The replacement above preserves the `task_id or ""` FTS5 NULL workaround.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_memory_store.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codebase_context/memory_store.py tests/test_memory_store.py
git commit -m "feat: add VALID_EVENT_TYPES constant and type validation to MemoryStore"
```

---

## Task 4: Rewrite `mcp_server.py` — narrative tools, coord rename, LSP removal, schema check

**Files:**
- Modify: `codebase_context/mcp_server.py`
- Replace: `tests/test_mcp_lsp_tools.py`
- Modify: `tests/test_mcp_memory_tools.py`

- [ ] **Step 1: Write failing tests — LSP tools absent**

Replace the entire `tests/test_mcp_lsp_tools.py` with:

```python
"""Verify LSP tools are NOT registered in mcp_server (Layer 2 scope narrowed)."""
import inspect
import codebase_context.mcp_server as mcp_server_mod

LSP_TOOL_NAMES = [
    "find_definition",
    "find_references",
    "get_signature",
    "get_call_hierarchy",
    "warm_file",
]


def test_lsp_tools_absent_from_source():
    src = inspect.getsource(mcp_server_mod)
    for name in LSP_TOOL_NAMES:
        assert f'"name": "{name}"' not in src or f'name="{name}"' not in src, \
            f'LSP tool "{name}" still registered in mcp_server — should be removed'


def test_lsp_router_not_imported_in_run_server():
    """LspRouter should not be instantiated — no more LSP tools."""
    src = inspect.getsource(mcp_server_mod)
    assert "LspRouter(project_root)" not in src
```

- [ ] **Step 2: Write failing tests — narrative and coord tools present**

Replace `tests/test_mcp_memory_tools.py` with:

```python
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
```

- [ ] **Step 3: Run to verify failures**

```bash
pytest tests/test_mcp_lsp_tools.py tests/test_mcp_memory_tools.py -v
```

Expected: Multiple FAILs — LSP tools still present, old names still in source, narrative handlers don't exist yet

- [ ] **Step 4: Rewrite `codebase_context/mcp_server.py`**

Replace the entire file with the following. Key changes from the current version:
- `MemgramStore` instantiated in `run_server()` alongside `MemoryStore`
- `LspRouter` instantiation and import removed
- Old-schema detection added at start of `run_server()`
- `list_tools()` returns 11 tools: 3 Layer 1 + 4 narrative + 4 coord (LSP tools gone)
- `call_tool()` dispatches `narrative_*` and `coord_*` names (old names gone)
- New handlers: `_handle_narrative_save`, `_handle_narrative_context`, `_handle_narrative_search`, `_handle_narrative_session_end`
- Renamed handlers: `_handle_coord_store_event`, `_handle_coord_recall_events`, `_handle_coord_record_manifest`, `_handle_coord_get_manifest`
- `_format_memories()` added (moved from `memgram/mcp_server.py`)

```python
"""MCP server exposing search_codebase, get_symbol, get_repo_map,
narrative_* (Layer 3a), and coord_* (Layer 3b) tools."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

from codebase_context.config import DEFAULT_TOP_K, MCP_LOG_PATH


def _setup_logging(project_root: str) -> None:
    """Log to file only — never stderr (would corrupt the stdio MCP protocol)."""
    log_path = Path(project_root) / MCP_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


logger = logging.getLogger(__name__)


def _check_old_memgram_schema(project_root: str) -> None:
    """Refuse to start if memgram.db has the old content-backed FTS schema."""
    db_path = Path(project_root) / ".codebase-context" / "memgram.db"
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name='obs_ai'"
        ).fetchone()[0]
    finally:
        conn.close()
    if count > 0:
        print(
            "ERROR: memgram.db has an old schema incompatible with this version.\n"
            "Run:   ccindex migrate",
            file=sys.stderr,
        )
        sys.exit(1)


def run_server() -> None:
    """Entry point called by `ccindex serve`."""
    project_root = os.getcwd()
    _setup_logging(project_root)
    logger.info("MCP server starting. project_root=%s", project_root)

    _check_old_memgram_schema(project_root)

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types

    from codebase_context.embedder import Embedder
    from codebase_context.retriever import Retriever
    from codebase_context.memory_store import MemoryStore
    from codebase_context.memgram.store import MemgramStore

    embedder = Embedder()
    retriever = Retriever(project_root, embedder=embedder)
    memory_store = MemoryStore(project_root)
    narrative_store = MemgramStore(project_root)

    server = Server("codebase-context")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            # --- Layer 1: Code Map ---
            types.Tool(
                name="search_codebase",
                description=(
                    "Search the codebase using natural language. Returns the most "
                    "semantically relevant functions, classes, and methods. "
                    "Use for finding implementations, locating utilities, or understanding a subsystem."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "top_k": {"type": "integer", "description": "Number of results. Default: 10. Max: 25.", "default": DEFAULT_TOP_K},
                        "language": {"type": "string", "description": 'Filter to "python" or "typescript"'},
                        "filepath_contains": {"type": "string", "description": "Fuzzy filter on filepath"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="get_symbol",
                description=(
                    "Fetch a specific symbol (function, class, method) by exact name. "
                    "Use to retrieve a known symbol's full implementation or verify it exists."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Exact symbol name (case-sensitive)"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="get_repo_map",
                description=(
                    "Returns the full repo map — all files, classes, and function signatures. "
                    "Use only when you need a complete structural overview: new file placement, "
                    "architecture questions, or cross-cutting changes. ~8k tokens — call sparingly."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            # --- Layer 3a: Narrative Memory (cross-session) ---
            types.Tool(
                name="narrative_save",
                description=(
                    "Save a cross-session observation (finding, decision, bugfix, handoff). "
                    "Call after significant findings, bugfixes, or decisions. "
                    "Structure content with ## What / ## Why / ## Where / ## Learned sections."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title":   {"type": "string", "description": "Short verb+what title (e.g. 'Fixed N+1 query in UserList')"},
                        "content": {"type": "string", "description": "Freeform detail with What/Why/Where/Learned sections"},
                        "type": {
                            "type": "string",
                            "enum": ["handoff", "decision", "bugfix", "architecture", "discovery"],
                            "description": "Observation type. Default: handoff",
                            "default": "handoff",
                        },
                    },
                    "required": ["title", "content"],
                },
            ),
            types.Tool(
                name="narrative_context",
                description=(
                    "Load recent cross-session observations for this project. "
                    "Call at session start to restore prior context."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max observations to return. Default: 10", "default": 10},
                    },
                },
            ),
            types.Tool(
                name="narrative_search",
                description=(
                    "Full-text search over cross-session observations. "
                    "Use to find past decisions, bugfixes, or handoffs relevant to the current task."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search terms"},
                        "type": {
                            "type": "string",
                            "enum": ["handoff", "decision", "bugfix", "architecture", "discovery", "session_end"],
                            "description": "Optional type filter",
                        },
                        "limit": {"type": "integer", "description": "Max results. Default: 10", "default": 10},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="narrative_session_end",
                description=(
                    "Record the end of a session with a one-line summary. "
                    "Call after completing a feature or fix, before stopping work."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "One-line session summary"},
                    },
                    "required": ["summary"],
                },
            ),
            # --- Layer 3b: Coordination State (intra-session) ---
            types.Tool(
                name="coord_store_event",
                description=(
                    "Log an intra-session coordination event. "
                    "Call after decisions, task transitions, or agent actions. "
                    "Use only when explicitly continuing an in-flight task — not at session start."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent":      {"type": "string", "description": "Agent name (e.g. planner, dev-agent)"},
                        "event_type": {
                            "type": "string",
                            "enum": ["task_started", "task_completed", "task_failed", "agent_action", "decision", "error"],
                            "description": "Event type",
                        },
                        "content":    {"type": "string", "description": "Event content — freeform text"},
                        "task_id":    {"type": "string", "description": "Optional task ID to associate this event with"},
                    },
                    "required": ["agent", "event_type", "content"],
                },
            ),
            types.Tool(
                name="coord_recall_events",
                description=(
                    "Full-text search over intra-session coordination events. "
                    "Use to retrieve past task decisions or agent actions for the current task."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query":      {"type": "string",  "description": "Full-text search query"},
                        "limit":      {"type": "integer", "description": "Max results. Default: 10.", "default": 10},
                        "agent":      {"type": "string",  "description": "Filter by agent name"},
                        "event_type": {"type": "string",  "description": "Filter by event type"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="coord_record_manifest",
                description=(
                    "Record files and symbols a Dev Agent touched at task completion. "
                    "Call at the end of each task with the full list of changes."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task ID"},
                        "changes": {
                            "type": "array",
                            "description": "List of change records",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "filepath":      {"type": "string"},
                                    "change_type":   {"type": "string", "enum": ["added", "modified", "deleted"]},
                                    "symbol_name":   {"type": "string"},
                                    "old_signature": {"type": "string"},
                                    "new_signature": {"type": "string"},
                                },
                                "required": ["filepath", "change_type"],
                            },
                        },
                    },
                    "required": ["task_id", "changes"],
                },
            ),
            types.Tool(
                name="coord_get_manifest",
                description=(
                    "Retrieve the change manifest for a task. "
                    "Use as a Review Agent to see which files and symbols were modified."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task ID to retrieve manifest for"},
                    },
                    "required": ["task_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        logger.info("Tool call: %s  args=%s", name, arguments)
        try:
            if name == "search_codebase":
                return await _handle_search(retriever, arguments)
            elif name == "get_symbol":
                return await _handle_get_symbol(retriever, arguments)
            elif name == "get_repo_map":
                return await _handle_get_repo_map(retriever, project_root)
            elif name == "narrative_save":
                return await _handle_narrative_save(narrative_store, arguments)
            elif name == "narrative_context":
                return await _handle_narrative_context(narrative_store, arguments)
            elif name == "narrative_search":
                return await _handle_narrative_search(narrative_store, arguments)
            elif name == "narrative_session_end":
                return await _handle_narrative_session_end(narrative_store, arguments)
            elif name == "coord_store_event":
                return await _handle_coord_store_event(memory_store, arguments)
            elif name == "coord_recall_events":
                return await _handle_coord_recall_events(memory_store, arguments)
            elif name == "coord_record_manifest":
                return await _handle_coord_record_manifest(memory_store, arguments)
            elif name == "coord_get_manifest":
                return await _handle_coord_get_manifest(memory_store, arguments)
            else:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}),
                )]
        except Exception as e:
            logger.exception("Error handling tool %s: %s", name, e)
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": str(e), "results": []}),
            )]

    asyncio.run(_run_server(server))


async def _run_server(server) -> None:
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


# --- Layer 1 handlers ---

async def _handle_search(retriever, arguments: dict):
    from mcp import types
    query = arguments["query"]
    top_k = min(int(arguments.get("top_k", DEFAULT_TOP_K)), 25)
    language = arguments.get("language")
    filepath_contains = arguments.get("filepath_contains")
    if retriever.store.count() == 0:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": "Index not found. Run: ccindex init", "results": []}),
        )]
    results = retriever.search(query, top_k=top_k, language=language, filepath_contains=filepath_contains)
    payload = [
        {
            "filepath": r.filepath, "symbol_name": r.symbol_name, "symbol_type": r.symbol_type,
            "signature": r.signature, "source": r.source, "score": r.score,
            "start_line": r.start_line, "end_line": r.end_line, "parent_class": r.parent_class,
        }
        for r in results
    ]
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


async def _handle_get_symbol(retriever, arguments: dict):
    from mcp import types
    name = arguments["name"]
    if retriever.store.count() == 0:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": "Index not found. Run: ccindex init", "results": []}),
        )]
    results = retriever.get_symbol(name)
    payload = [
        {
            "filepath": r.filepath, "symbol_name": r.symbol_name, "symbol_type": r.symbol_type,
            "signature": r.signature, "source": r.source, "score": r.score,
            "start_line": r.start_line, "end_line": r.end_line, "parent_class": r.parent_class,
        }
        for r in results
    ]
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


async def _handle_get_repo_map(retriever, project_root: str):
    from mcp import types
    content = retriever.get_repo_map(project_root)
    return [types.TextContent(type="text", text=content)]


# --- Layer 3a: Narrative handlers ---

def _format_memories(memories: list[dict]) -> str:
    lines = []
    for m in memories:
        ts = datetime.datetime.fromtimestamp(int(m["created_at"])).strftime("%Y-%m-%d %H:%M")
        lines.append(f"### [{m['type']}] {m['title']}")
        lines.append(f"*{ts}*")
        lines.append(m["content"])
        lines.append("")
    return "\n".join(lines)


async def _handle_narrative_save(narrative_store, arguments: dict):
    from mcp import types
    id_ = narrative_store.save(
        arguments["title"],
        arguments.get("content", ""),
        arguments.get("type", "handoff"),
    )
    return [types.TextContent(type="text", text=json.dumps({"saved": True, "id": id_}))]


async def _handle_narrative_context(narrative_store, arguments: dict):
    from mcp import types
    memories = narrative_store.context(limit=int(arguments.get("limit", 10)))
    if not memories:
        return [types.TextContent(type="text", text="No memories stored yet.")]
    return [types.TextContent(type="text", text=_format_memories(memories))]


async def _handle_narrative_search(narrative_store, arguments: dict):
    from mcp import types
    memories = narrative_store.search(
        arguments["query"],
        type=arguments.get("type"),
        limit=int(arguments.get("limit", 10)),
    )
    if not memories:
        return [types.TextContent(type="text", text=f"No results for '{arguments['query']}'.")]
    return [types.TextContent(type="text", text=_format_memories(memories))]


async def _handle_narrative_session_end(narrative_store, arguments: dict):
    from mcp import types
    narrative_store.session_end(arguments.get("summary", ""))
    return [types.TextContent(type="text", text=json.dumps({"session_ended": True}))]


# --- Layer 3b: Coordination handlers ---

async def _handle_coord_store_event(memory_store, arguments: dict):
    from mcp import types
    event_id = memory_store.store_event(
        agent=arguments["agent"],
        event_type=arguments["event_type"],
        content=arguments["content"],
        task_id=arguments.get("task_id"),
    )
    return [types.TextContent(type="text", text=json.dumps({"id": event_id}))]


async def _handle_coord_recall_events(memory_store, arguments: dict):
    from mcp import types
    results = memory_store.search_events(
        query=arguments["query"],
        limit=int(arguments.get("limit", 10)),
        agent=arguments.get("agent"),
        event_type=arguments.get("event_type"),
    )
    return [types.TextContent(type="text", text=json.dumps(results, indent=2))]


async def _handle_coord_record_manifest(memory_store, arguments: dict):
    from mcp import types
    count = memory_store.record_manifest(
        task_id=arguments["task_id"],
        changes=arguments["changes"],
    )
    return [types.TextContent(type="text", text=json.dumps({"count": count}))]


async def _handle_coord_get_manifest(memory_store, arguments: dict):
    from mcp import types
    records = memory_store.get_manifest(task_id=arguments["task_id"])
    return [types.TextContent(type="text", text=json.dumps(records, indent=2))]
```

- [ ] **Step 5: Run the tool tests**

```bash
pytest tests/test_mcp_lsp_tools.py tests/test_mcp_memory_tools.py -v
```

Expected: All PASS

- [ ] **Step 6: Run the full test suite**

```bash
pytest tests/ -x -q
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add codebase_context/mcp_server.py tests/test_mcp_lsp_tools.py tests/test_mcp_memory_tools.py
git commit -m "feat: merge narrative tools into ccindex serve; rename coord tools; remove LSP tools"
```

---

## Task 5: Extend `migrate.py` — new MemgramStore API + memgram.db file archiving

**Files:**
- Modify: `codebase_context/migrate.py`
- Modify: `tests/test_migrate.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_migrate.py`:

```python
def test_run_migration_archives_old_memgram_db(tmp_path):
    """If .claude/memgram.db exists, it is renamed to .migrated."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    old_db = claude_dir / "memgram.db"
    old_db.write_bytes(b"fake db content")

    run_migration(str(tmp_path))

    assert not old_db.exists()
    assert (claude_dir / "memgram.db.migrated").exists()


def test_run_migration_writes_to_codebase_context_memgram_db(tmp_path):
    """HANDOFF.md records go to .codebase-context/memgram.db after migration."""
    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    run_migration(str(tmp_path))
    assert (tmp_path / ".codebase-context" / "memgram.db").exists()


def test_run_migration_no_error_when_no_old_memgram_db(tmp_path):
    """Migration succeeds even if .claude/memgram.db does not exist."""
    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    handoff_count, _ = run_migration(str(tmp_path))
    assert handoff_count == 1
```

- [ ] **Step 2: Run to verify failures**

```bash
pytest tests/test_migrate.py -k "archives_old_memgram or codebase_context_memgram or no_error_when_no" -v
```

Expected: FAIL — `run_migration` still uses old `MemgramStore(db_path)` API, no file archiving logic

- [ ] **Step 3: Update `codebase_context/migrate.py`**

Replace the entire file:

```python
"""Migration helpers: parse HANDOFF.md / DECISIONS.md → MemgramStore;
archive old memgram.db from .claude/ to .codebase-context/."""

from __future__ import annotations

import re
from pathlib import Path

from codebase_context.memgram.store import MemgramStore


class AlreadyMigratedError(Exception):
    """Raised when .migrated archive files already exist in the project root."""


def parse_handoff_blocks(text: str) -> list[dict]:
    """Split HANDOFF.md text into one record per agent block.

    Skips the template block (agent name contains angle-bracket placeholders).
    Returns list of {"title": str, "content": str, "type": "handoff"}.
    """
    blocks = []
    parts = re.split(r"(?=^### Agent:)", text, flags=re.MULTILINE)
    for part in parts:
        part = part.strip()
        if not part.startswith("### Agent:"):
            continue
        first_line = part.splitlines()[0]
        agent_name = first_line.removeprefix("### Agent:").strip()
        if "<" in agent_name and ">" in agent_name:
            continue  # template placeholder — skip
        task_match = re.search(r"\*\*Task:\*\*\s*(.+)", part)
        task = task_match.group(1).strip() if task_match else ""
        title = f"Agent: {agent_name}" + (f" — {task}" if task else "")
        blocks.append({"title": title, "content": part, "type": "handoff"})
    return blocks


def parse_decision_blocks(text: str) -> list[dict]:
    """Split DECISIONS.md text into one record per decision entry.

    Only processes content under the '## Decision Log' heading.
    Returns list of {"title": str, "content": str, "type": "decision"}.
    """
    blocks = []
    log_match = re.search(r"^## Decision Log\s*\n", text, flags=re.MULTILINE)
    if not log_match:
        return blocks
    log_text = text[log_match.end():]
    parts = re.split(r"(?=^### )", log_text, flags=re.MULTILINE)
    for part in parts:
        part = part.strip()
        if not part.startswith("### "):
            continue
        first_line = part.splitlines()[0]
        title = first_line.removeprefix("### ").strip()
        if not title or ("<" in title and ">" in title):
            continue
        blocks.append({"title": title, "content": part, "type": "decision"})
    return blocks


def run_migration(project_root: str) -> tuple[int, int]:
    """Migrate HANDOFF.md, DECISIONS.md, and old memgram.db into the new layout.

    - Archives .claude/memgram.db → .claude/memgram.db.migrated (start fresh).
    - Inserts HANDOFF.md and DECISIONS.md blocks into the new MemgramStore
      (which writes to .codebase-context/memgram.db).
    - Renames HANDOFF.md → HANDOFF.md.migrated and DECISIONS.md → DECISIONS.md.migrated.
    - Raises AlreadyMigratedError if *.migrated archive files already exist.
    - Returns (handoff_count, decision_count).
    """
    root = Path(project_root)
    handoff_path = root / "HANDOFF.md"
    decisions_path = root / "DECISIONS.md"
    archived_handoff = root / "HANDOFF.md.migrated"
    archived_decisions = root / "DECISIONS.md.migrated"

    if archived_handoff.exists() and archived_decisions.exists():
        raise AlreadyMigratedError(
            "Migration has already been run — archive files (*.migrated) already exist."
        )

    # Archive old memgram.db (start fresh — no data preservation)
    old_memgram = root / ".claude" / "memgram.db"
    archived_memgram = root / ".claude" / "memgram.db.migrated"
    if old_memgram.exists() and not archived_memgram.exists():
        old_memgram.rename(archived_memgram)

    if not handoff_path.exists() and not decisions_path.exists():
        return (0, 0)

    # MemgramStore now takes project_root; writes to .codebase-context/memgram.db
    store = MemgramStore(project_root)

    handoff_blocks: list[dict] = []
    decision_blocks: list[dict] = []

    if handoff_path.exists():
        handoff_blocks = parse_handoff_blocks(handoff_path.read_text(encoding="utf-8"))

    if decisions_path.exists():
        decision_blocks = parse_decision_blocks(decisions_path.read_text(encoding="utf-8"))

    for block in handoff_blocks:
        store.save(block["title"], block["content"], block["type"])

    for block in decision_blocks:
        store.save(block["title"], block["content"], block["type"])

    if handoff_path.exists():
        handoff_path.rename(archived_handoff)

    if decisions_path.exists():
        decisions_path.rename(archived_decisions)

    return (len(handoff_blocks), len(decision_blocks))
```

- [ ] **Step 4: Run migrate tests**

```bash
pytest tests/test_migrate.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codebase_context/migrate.py tests/test_migrate.py
git commit -m "feat: extend migrate — new MemgramStore API, archive old memgram.db"
```

---

## Task 6: Update `cli.py` — upgrade settings cleanup, init @-ref removal, protocol update

**Files:**
- Modify: `codebase_context/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add a new test class to `tests/test_cli.py`:

```python
class TestUpgradeSettingsCleanup:
    def test_upgrade_removes_stale_memgram_entry(self, tmp_project):
        """After upgrade, the stale 'memgram' MCP entry is removed from settings.json."""
        from codebase_context.cli import _remove_stale_mcp_entries
        settings_path = Path(tmp_project) / ".claude" / "settings.json"
        settings_path.parent.mkdir(exist_ok=True)
        settings_path.write_text(json.dumps({
            "mcpServers": {
                "codebase-context": {"command": "ccindex", "args": ["serve"]},
                "memgram": {"command": "ccindex", "args": ["mem-serve"]},
            }
        }), encoding="utf-8")

        _remove_stale_mcp_entries(tmp_project)

        data = json.loads(settings_path.read_text())
        assert "memgram" not in data["mcpServers"]
        assert "codebase-context" in data["mcpServers"]

    def test_upgrade_no_op_when_no_memgram_entry(self, tmp_project):
        """No error when memgram entry is already absent."""
        from codebase_context.cli import _remove_stale_mcp_entries
        settings_path = Path(tmp_project) / ".claude" / "settings.json"
        settings_path.parent.mkdir(exist_ok=True)
        settings_path.write_text(json.dumps({
            "mcpServers": {"codebase-context": {"command": "ccindex", "args": ["serve"]}}
        }), encoding="utf-8")

        _remove_stale_mcp_entries(tmp_project)  # Should not raise

        data = json.loads(settings_path.read_text())
        assert "codebase-context" in data["mcpServers"]

    def test_upgrade_no_op_when_no_settings_file(self, tmp_project):
        """No error when .claude/settings.json does not exist."""
        from codebase_context.cli import _remove_stale_mcp_entries
        _remove_stale_mcp_entries(tmp_project)  # Should not raise
```

Also add a test to `TestSetupMemgram` to ensure `init` no longer sets up a separate memgram server:

```python
    def test_init_does_not_register_separate_memgram_server(self, tmp_project):
        """After init, settings.json should NOT have a 'memgram' MCP entry."""
        from codebase_context.cli import _setup_mcp_server
        _setup_mcp_server(tmp_project)
        settings_path = Path(tmp_project) / ".claude" / "settings.json"
        if settings_path.exists():
            data = json.loads(settings_path.read_text())
            assert "memgram" not in data.get("mcpServers", {})
```

Also verify the session protocol sentinel uses the new name:

```python
def test_write_session_protocol_uses_narrative_context_sentinel(tmp_project):
    from codebase_context.cli import _write_session_protocol
    claude_md = Path(tmp_project) / "CLAUDE.md"
    _write_session_protocol(tmp_project)
    text = claude_md.read_text()
    assert "narrative_context" in text
    assert "mem_context" not in text
```

- [ ] **Step 2: Run to verify failures**

```bash
pytest tests/test_cli.py -k "upgrade or stale or narrative_context_sentinel" -v
```

Expected: FAIL — `_remove_stale_mcp_entries` doesn't exist, sentinel still `mem_context`

- [ ] **Step 3: Update `codebase_context/cli.py`**

Make these changes:

**3a.** Add `_remove_stale_mcp_entries` function after `_setup_mcp_server`:

```python
def _remove_stale_mcp_entries(project_root: str) -> None:
    """Remove the stale 'memgram' MCP entry from .claude/settings.json if present."""
    settings_path = Path(project_root) / ".claude" / "settings.json"
    if not settings_path.exists():
        return
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    servers = data.get("mcpServers", {})
    if _MEMGRAM_KEY in servers:
        del servers[_MEMGRAM_KEY]
        data["mcpServers"] = servers
        settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        click.echo(f"  Removed stale '{_MEMGRAM_KEY}' MCP entry from .claude/settings.json")
```

**3b.** Update `_MEMGRAM_PROTOCOL_SENTINEL` and `_MEMGRAM_SESSION_PROTOCOL`:

```python
_MEMGRAM_PROTOCOL_SENTINEL = "narrative_context"
_MEMGRAM_SESSION_PROTOCOL = """
## Session Protocol

**At the start of every session:**
1. Run `git pull`.
2. Call `narrative_context` (ccindex MCP) to load prior memories for this project.
3. Read `CONVENTIONS.md`.

**During every session:**
- After each significant finding, bugfix, or decision: call `narrative_save`:
  - `title`: verb + what (e.g. "Fixed N+1 query in UserList")
  - `type`: `handoff` | `decision` | `bugfix` | `architecture` | `discovery`
  - `content`: freeform with ## What / ## Why / ## Where / ## Learned sections

**After every completed feature or fix:**
1. Call `narrative_save` summarising what was completed (`type: handoff`).
2. Call `narrative_session_end` with a one-line summary.
3. Commit and push code only: `git add <changed files> && git commit && git push`

> Do not write to HANDOFF.md or DECISIONS.md — they are removed.
> Query past decisions with: `narrative_search(query="<topic>", type="decision")`
"""
```

**3c.** Update `upgrade` command to call `_remove_stale_mcp_entries`. Change the decorator and signature to accept context:

```python
@cli.command()
@click.pass_context
@click.option("--debug", is_flag=True, help="Print install-method detection details.")
def upgrade(ctx: click.Context, debug: bool) -> None:
    """Upgrade codebase-context to the latest version; clean up project settings."""
    # ... existing binary upgrade logic unchanged ...
    
    # After upgrade, clean up stale settings
    _remove_stale_mcp_entries(ctx.obj["root"])
```

**3d.** Remove the `@.codebase-context/repo_map.md` prompt from `init`. In the `init` command body, delete these lines (roughly lines 61–78):

```python
# Remove entirely — the @-reference block:
    claude_md = Path(root) / "CLAUDE.md"
    ref_line = "@.codebase-context/repo_map.md"
    if claude_md.exists():
        has_ref = ref_line in claude_md.read_text(encoding="utf-8")
    else:
        has_ref = False

    if not has_ref:
        if click.confirm("\nAdd repo map reference to CLAUDE.md?", default=True):
            if claude_md.exists():
                claude_md.write_text(
                    claude_md.read_text(encoding="utf-8").rstrip("\n")
                    + f"\n\n{ref_line}\n",
                    encoding="utf-8",
                )
            else:
                claude_md.write_text(f"{ref_line}\n", encoding="utf-8")
            click.echo(f"  Added {ref_line} to CLAUDE.md")
```

**3e.** Remove `_setup_memgram` call from `doctor` command. Change the `doctor` body to:

```python
@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check binaries and MCP setup."""
    _setup_external_deps()
    _setup_mcp_server(ctx.obj["root"])
```

**3f.** Add deprecation warning to `mem_serve` command:

```python
@cli.command("mem-serve")
def mem_serve() -> None:
    """[DEPRECATED] memgram is now part of ccindex serve. Use ccindex serve instead."""
    click.echo(
        "Warning: ccindex mem-serve is deprecated. "
        "Memgram tools are now served by ccindex serve.\n"
        "Run: ccindex upgrade  to clean up your project settings.",
        err=True,
    )
    from codebase_context.memgram.mcp_server import run_server
    run_server()
```

**3g.** Update `_update_gitignore` — change `.claude/memgram.db` to `.codebase-context/memgram.db`:

```python
    additions = [
        "# codebase-context",
        ".codebase-context/chroma/",
        ".codebase-context/index_meta.json",
        ".codebase-context/mcp.log",
        ".codebase-context/memgram.db",
        ".codebase-context/memory.db",
        "# optionally commit repo_map.md for team visibility:",
        "# .codebase-context/repo_map.md",
    ]
```

- [ ] **Step 4: Run CLI tests**

```bash
pytest tests/test_cli.py -v
```

Expected: All PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -x -q
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add codebase_context/cli.py tests/test_cli.py
git commit -m "feat: upgrade cleans up stale memgram settings; init drops @-ref prompt; protocol uses narrative_* names"
```

---

## Task 7: Update `CLAUDE.md` — navigation hint and session protocol

**Files:**
- Modify: `CLAUDE.md`

> **Note:** `CLAUDE.md` is a live project config — read it fully before editing. The changes below describe the intent; apply them to match the current structure.

- [ ] **Step 1: Remove the `@.codebase-context/repo_map.md` reference**

In `CLAUDE.md`, find and remove the line:
```
@.codebase-context/repo_map.md
```

This line is in the `## Codebase Context` section header area. Remove it and the `@` reference that loads the file unconditionally.

- [ ] **Step 2: Update the navigation priority section**

Replace the existing "Navigation priority" block with:

```markdown
### Navigation priority — follow this order every time

1. **`search_codebase` / `get_symbol`** — for targeted queries: finding a symbol, concept search, locating a utility. ~50–500 tokens per call.
2. **`get_repo_map`** — only when you need a full structural overview: new file placement, architecture questions, cross-cutting changes. ~8k tokens — call sparingly.
3. **`Grep` tool** — for content patterns in any file, including languages not in the index.
4. **`Glob` tool** — for finding files by name pattern (e.g. `**/*.sh`).
5. **`Read`** — only after you have located the right file via one of the above.
```

- [ ] **Step 3: Update session protocol tool names**

In the `## Session Protocol` section, replace all occurrences of old tool names:

| Old | New |
|---|---|
| `mem_context` | `narrative_context` |
| `mem_save` | `narrative_save` |
| `mem_session_end` | `narrative_session_end` |
| `mem_search` | `narrative_search` |
| `store_memory` | `coord_store_event` |
| `recall_memory` | `coord_recall_events` |
| `memgram MCP` | `ccindex MCP` |

The updated session protocol block should read:

```markdown
## Session Protocol

**At the start of every session:**
1. Run `git pull`.
2. Call `narrative_context` (ccindex MCP) to load prior memories for this project.
3. Read `CONVENTIONS.md`.

**During every session:**
- After each significant finding, bugfix, or decision: call `narrative_save`:
  - `title`: verb + what (e.g. "Fixed N+1 query in UserList")
  - `type`: `handoff` | `decision` | `bugfix` | `architecture` | `discovery`
  - `content`: freeform with ## What / ## Why / ## Where / ## Learned sections

**After every completed feature or fix:**
1. Call `narrative_save` summarising what was completed (`type: handoff`).
2. Call `narrative_session_end` with a one-line summary.
3. Commit and push code only: `git add <changed files> && git commit && git push`

> Do not write to HANDOFF.md or DECISIONS.md — they are removed.
> Query past decisions with: `narrative_search(query="<topic>", type="decision")`
```

- [ ] **Step 4: Verify the file reads correctly**

```bash
grep -n "mem_context\|mem_save\|mem_session_end\|@.codebase-context/repo_map" CLAUDE.md
```

Expected: No output (old names removed)

```bash
grep -n "narrative_context\|narrative_save\|get_repo_map" CLAUDE.md
```

Expected: Lines showing the new names are present

- [ ] **Step 5: Run the full test suite one final time**

```bash
pytest tests/ -x -q
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md — on-demand repo map, narrative_* tool names in session protocol"
```

---

## Self-Review

### Spec coverage

| Requirement | Task |
|---|---|
| `db.py` `db_filename` parameter with encoded threading.local key | Task 1 |
| `MemgramStore` standalone FTS5 (no base table, no triggers) | Task 2 |
| `MemgramStore` adopts `db.py` threading.local connections | Task 2 |
| `VALID_OBSERVATION_TYPES` enforced with ValueError | Task 2 |
| All timestamps Unix INTEGER | Task 2 |
| `VALID_EVENT_TYPES` + validation in `MemoryStore.store_event` | Task 3 |
| 4 `narrative_*` tools in `ccindex serve` | Task 4 |
| 4 `coord_*` tools (renamed from old names) | Task 4 |
| 5 LSP tools removed from MCP surface | Task 4 |
| Old-schema detection + refuse-to-start in `run_server` | Task 4 |
| `migrate.py` uses new `MemgramStore(project_root)` API | Task 5 |
| `migrate.py` archives `.claude/memgram.db` | Task 5 |
| `ccindex upgrade` removes stale `memgram` settings entry | Task 6 |
| `ccindex init` stops injecting `@.codebase-context/repo_map.md` | Task 6 |
| Session protocol uses `narrative_*` tool names | Task 6 |
| `ccindex mem-serve` prints deprecation warning | Task 6 |
| `.gitignore` updated for new DB locations | Task 6 |
| `CLAUDE.md` navigation hint (on-demand `get_repo_map`) | Task 7 |
| `CLAUDE.md` session protocol uses `narrative_*` names | Task 7 |

### Placeholder scan

No TBDs, TODOs, or vague steps — all steps include actual code or exact commands.

### Type consistency

- `MemgramStore.save()` returns `int` (rowid) — used as `int` in `_handle_narrative_save` ✓
- `MemgramStore.context()` returns `list[dict]` with `created_at: int` — `_format_memories` reads `int(m["created_at"])` ✓
- `get_connection(project_root, db_filename)` — called in `MemgramStore.__init__` and `_conn()` with `db_filename="memgram.db"` ✓
- `_handle_coord_store_event` calls `memory_store.store_event(agent, event_type, content, task_id)` — matches `MemoryStore.store_event` signature ✓

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-06-ccindex-consolidation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints

**Which approach?**
