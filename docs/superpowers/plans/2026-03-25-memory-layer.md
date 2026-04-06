# Memory Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a SQLite-backed memory layer to the ccindex MCP server — exposing 4 new tools (`store_memory`, `recall_memory`, `record_change_manifest`, `get_change_manifest`) that let Payload Depot agents persist session events and change manifests.

**Architecture:** A new `db.py` module provides per-thread SQLite connections (WAL mode, `threading.local`). A new `memory_store.py` wraps those connections with a `MemoryStore` class covering three tables: a standalone FTS5 virtual table for events, a `tasks` table for task state, and a `change_manifests` table keyed by `task_id`. The four new MCP tools are thin async handlers wired into the existing `mcp_server.py` dispatch.

**Tech Stack:** Python 3.11+, `sqlite3` (stdlib — no new dependencies), FTS5 (bundled with Python's sqlite3), pytest with `asyncio_mode = "auto"`.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `codebase_context/db.py` | Per-thread connection manager; WAL mode; DB path resolution |
| Create | `codebase_context/memory_store.py` | Schema migration; CRUD for events (FTS5), tasks, change_manifests |
| Modify | `codebase_context/mcp_server.py` | Add 4 new tool definitions and 4 async handler functions |
| Create | `tests/test_db.py` | Unit tests for db.py |
| Create | `tests/test_memory_store.py` | Unit tests for all MemoryStore methods |
| Create | `tests/test_mcp_memory_tools.py` | Integration tests for the 4 new MCP handler functions |

**Files left untouched:** everything else — `parser.py`, `chunker.py`, `store.py`, `retriever.py`, `indexer.py`, `watcher.py`, `cli.py`, `utils.py`, `config.py`, `models.py`, `repo_map.py`, `embedder.py`, all existing tests.

---

## Task 0: Baseline — Confirm Existing Tests Are Green

**Files:** none

- [ ] **Step 1: Run full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass. If any fail, **stop here** and fix them before writing a single line of new code. The spec requires all existing tests to stay green throughout.

---

## Task 1: `db.py` — SQLite Connection Manager

**Files:**
- Create: `codebase_context/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:

```python
"""Unit tests for the db connection manager."""
from __future__ import annotations

import sqlite3
import threading

from codebase_context.db import get_connection


def test_returns_sqlite_connection(tmp_path):
    conn = get_connection(str(tmp_path))
    assert isinstance(conn, sqlite3.Connection)


def test_same_project_root_returns_same_connection(tmp_path):
    conn1 = get_connection(str(tmp_path))
    conn2 = get_connection(str(tmp_path))
    assert conn1 is conn2


def test_db_file_created_at_expected_path(tmp_path):
    get_connection(str(tmp_path))
    assert (tmp_path / ".codebase-context" / "memory.db").exists()


def test_wal_mode_enabled(tmp_path):
    conn = get_connection(str(tmp_path))
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_different_threads_get_different_connections(tmp_path):
    results: list = []

    def grab() -> None:
        results.append(get_connection(str(tmp_path)))

    t = threading.Thread(target=grab)
    t.start()
    t.join()

    main_conn = get_connection(str(tmp_path))
    assert results[0] is not main_conn
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'codebase_context.db'`

- [ ] **Step 3: Implement `codebase_context/db.py`**

```python
"""Per-thread SQLite connection manager for the memory layer."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

DB_PATH = ".codebase-context/memory.db"
_local = threading.local()


def get_connection(project_root: str) -> sqlite3.Connection:
    """Return a per-thread SQLite connection for the given project root.

    Uses threading.local() so each thread gets its own connection — the correct
    pattern for sqlite3 under concurrent MCP tool calls. WAL mode allows concurrent
    readers alongside a single writer.
    """
    key = f"conn_{project_root}"
    if not hasattr(_local, key):
        path = Path(project_root) / DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        setattr(_local, key, conn)
    return getattr(_local, key)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_db.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add codebase_context/db.py tests/test_db.py
git commit -m "feat: add db.py — per-thread SQLite connection manager with WAL mode"
```

---

## Task 2: `memory_store.py` — Schema and Events

**Files:**
- Create: `codebase_context/memory_store.py`
- Create: `tests/test_memory_store.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_memory_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_memory_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'codebase_context.memory_store'`

- [ ] **Step 3: Implement `codebase_context/memory_store.py` with schema and events**

```python
"""SQLite-backed memory store for agent session events, tasks, and change manifests."""
from __future__ import annotations

import json
import time

from codebase_context.db import get_connection


_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS events USING fts5(
  agent,
  event_type,
  content,
  task_id UNINDEXED,
  created_at UNINDEXED,
  tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS tasks (
  id         TEXT    PRIMARY KEY,
  status     TEXT    NOT NULL,
  agent      TEXT    NOT NULL,
  payload    TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS change_manifests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id       TEXT    NOT NULL,
  filepath      TEXT    NOT NULL,
  symbol_name   TEXT,
  change_type   TEXT    NOT NULL,
  old_signature TEXT,
  new_signature TEXT
);

CREATE INDEX IF NOT EXISTS idx_cm_task_id ON change_manifests(task_id);
"""


class MemoryStore:
    """Manages the per-project memory layer SQLite database."""

    def __init__(self, project_root: str) -> None:
        self._conn = get_connection(project_root)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- Events ---

    def store_event(
        self,
        agent: str,
        event_type: str,
        content: str,
        task_id: str | None = None,
    ) -> str:
        """Insert a session event. Returns the row ID as a string."""
        cur = self._conn.execute(
            "INSERT INTO events(agent, event_type, content, task_id, created_at) VALUES (?,?,?,?,?)",
            (agent, event_type, content, task_id or "", str(int(time.time()))),
        )
        self._conn.commit()
        return str(cur.lastrowid)

    def search_events(
        self,
        query: str,
        limit: int = 10,
        agent: str | None = None,
        event_type: str | None = None,
    ) -> list[dict]:
        """FTS5 full-text search over events. Post-filters by agent or event_type if given."""
        rows = self._conn.execute(
            "SELECT rowid, agent, event_type, content, task_id, created_at "
            "FROM events WHERE events MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()

        results = []
        for row in rows:
            if agent and row["agent"] != agent:
                continue
            if event_type and row["event_type"] != event_type:
                continue
            results.append({
                "id": str(row["rowid"]),
                "agent": row["agent"],
                "event_type": row["event_type"],
                "content": row["content"],
                "task_id": row["task_id"],
                "created_at": row["created_at"],
            })
        return results
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_memory_store.py -v
```

Expected: 9 tests pass (schema + events tests only; tasks and manifests tests don't exist yet).

- [ ] **Step 5: Commit**

```bash
git add codebase_context/memory_store.py tests/test_memory_store.py
git commit -m "feat: add memory_store.py — schema migration and FTS5 events CRUD"
```

---

## Task 3: `memory_store.py` — Tasks CRUD

**Files:**
- Modify: `codebase_context/memory_store.py` (add 4 methods)
- Modify: `tests/test_memory_store.py` (append task tests)

- [ ] **Step 1: Append failing task tests to `tests/test_memory_store.py`**

Add at the bottom of `tests/test_memory_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm new ones fail**

```bash
pytest tests/test_memory_store.py -v -k "task"
```

Expected: `AttributeError: 'MemoryStore' object has no attribute 'create_task'`

- [ ] **Step 3: Add task methods to `MemoryStore` in `codebase_context/memory_store.py`**

Append these methods inside the `MemoryStore` class, after `search_events`:

```python
    # --- Tasks ---

    def create_task(self, task_id: str, agent: str, payload: dict) -> None:
        """Create a new task with status 'pending'."""
        now = int(time.time())
        self._conn.execute(
            "INSERT INTO tasks(id, status, agent, payload, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (task_id, "pending", agent, json.dumps(payload), now, now),
        )
        self._conn.commit()

    def update_task_status(self, task_id: str, status: str) -> None:
        """Update the status of an existing task."""
        self._conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (status, int(time.time()), task_id),
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> dict | None:
        """Fetch a single task by ID. Returns None if not found."""
        row = self._conn.execute(
            "SELECT id, status, agent, payload, created_at, updated_at FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "status": row["status"],
            "agent": row["agent"],
            "payload": json.loads(row["payload"]) if row["payload"] else {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_tasks(self, status: str | None = None) -> list[dict]:
        """List all tasks, optionally filtered by status."""
        if status:
            rows = self._conn.execute(
                "SELECT id, status, agent, payload, created_at, updated_at FROM tasks WHERE status=?",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, status, agent, payload, created_at, updated_at FROM tasks"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "status": row["status"],
                "agent": row["agent"],
                "payload": json.loads(row["payload"]) if row["payload"] else {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_memory_store.py -v
```

Expected: all tests pass (9 schema+events + 6 task tests = 15 passing).

- [ ] **Step 5: Commit**

```bash
git add codebase_context/memory_store.py tests/test_memory_store.py
git commit -m "feat: add MemoryStore task CRUD — create, get, update_status, list"
```

---

## Task 4: `memory_store.py` — Change Manifests

**Files:**
- Modify: `codebase_context/memory_store.py` (add 2 methods)
- Modify: `tests/test_memory_store.py` (append manifest tests)

- [ ] **Step 1: Append failing manifest tests to `tests/test_memory_store.py`**

Add at the bottom of `tests/test_memory_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm new ones fail**

```bash
pytest tests/test_memory_store.py -v -k "manifest"
```

Expected: `AttributeError: 'MemoryStore' object has no attribute 'record_manifest'`

- [ ] **Step 3: Add manifest methods to `MemoryStore` in `codebase_context/memory_store.py`**

Append these methods inside the `MemoryStore` class, after `list_tasks`:

```python
    # --- Change manifests ---

    def record_manifest(self, task_id: str, changes: list[dict]) -> int:
        """Insert change records for a task. Returns the number of records inserted."""
        self._conn.executemany(
            "INSERT INTO change_manifests"
            "(task_id, filepath, symbol_name, change_type, old_signature, new_signature)"
            " VALUES (?,?,?,?,?,?)",
            [
                (
                    task_id,
                    c["filepath"],
                    c.get("symbol_name"),
                    c["change_type"],
                    c.get("old_signature"),
                    c.get("new_signature"),
                )
                for c in changes
            ],
        )
        self._conn.commit()
        return len(changes)

    def get_manifest(self, task_id: str) -> list[dict]:
        """Fetch all change records for a task."""
        rows = self._conn.execute(
            "SELECT filepath, symbol_name, change_type, old_signature, new_signature "
            "FROM change_manifests WHERE task_id=?",
            (task_id,),
        ).fetchall()
        return [
            {
                "filepath": row["filepath"],
                "symbol_name": row["symbol_name"],
                "change_type": row["change_type"],
                "old_signature": row["old_signature"],
                "new_signature": row["new_signature"],
            }
            for row in rows
        ]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_memory_store.py -v
```

Expected: all 20 tests pass (9 events + 6 tasks + 5 manifests = 20).

- [ ] **Step 5: Commit**

```bash
git add codebase_context/memory_store.py tests/test_memory_store.py
git commit -m "feat: add MemoryStore change manifest CRUD — record and retrieve by task_id"
```

---

## Task 5: `mcp_server.py` — `store_memory` and `recall_memory` Tools

**Files:**
- Create: `tests/test_mcp_memory_tools.py`
- Modify: `codebase_context/mcp_server.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_memory_tools.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_mcp_memory_tools.py -v
```

Expected: `test_memory_tool_names_present_in_source` fails with `AssertionError: Tool name "store_memory" not found`; the two async tests fail with `AttributeError: module has no attribute '_handle_store_memory'`.

- [ ] **Step 3: Add `store_memory` and `recall_memory` to `mcp_server.py`**

**3a.** In `run_server()`, add `MemoryStore` instantiation after the `Retriever` is created (after line `retriever = Retriever(...)`):

```python
    from codebase_context.memory_store import MemoryStore
    memory_store = MemoryStore(project_root)
```

**3b.** In `list_tools()`, append these two tools to the returned list (before the closing `]`):

```python
            types.Tool(
                name="store_memory",
                description=(
                    "Log an agent event to the session memory store. "
                    "Call this after decisions, discoveries, bugfixes, or task handoffs "
                    "to persist context for other agents and future sessions."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent":      {"type": "string", "description": "Agent name (e.g. planner, dev-agent)"},
                        "event_type": {"type": "string", "description": "Event type (e.g. decision, handoff, bugfix)"},
                        "content":    {"type": "string", "description": "Event content — freeform text"},
                        "task_id":    {"type": "string", "description": "Optional task ID to associate this event with"},
                    },
                    "required": ["agent", "event_type", "content"],
                },
            ),
            types.Tool(
                name="recall_memory",
                description=(
                    "Full-text search over session memory. "
                    "Use this to retrieve past decisions, discoveries, or handoffs relevant to the current task."
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
```

**3c.** In the `call_tool()` closure, add two new branches in the `elif` chain before the `else` that returns "Unknown tool":

```python
            elif name == "store_memory":
                return await _handle_store_memory(memory_store, arguments)
            elif name == "recall_memory":
                return await _handle_recall_memory(memory_store, arguments)
```

**3d.** Add two new module-level handler functions at the bottom of `mcp_server.py`:

```python
async def _handle_store_memory(memory_store, arguments: dict):
    from mcp import types

    event_id = memory_store.store_event(
        agent=arguments["agent"],
        event_type=arguments["event_type"],
        content=arguments["content"],
        task_id=arguments.get("task_id"),
    )
    return [types.TextContent(type="text", text=json.dumps({"id": event_id}))]


async def _handle_recall_memory(memory_store, arguments: dict):
    from mcp import types

    results = memory_store.search_events(
        query=arguments["query"],
        limit=int(arguments.get("limit", 10)),
        agent=arguments.get("agent"),
        event_type=arguments.get("event_type"),
    )
    return [types.TextContent(type="text", text=json.dumps(results, indent=2))]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_mcp_memory_tools.py -v
```

Expected: 3 tests pass (`test_memory_tool_names_present_in_source` still checks for all 4 names — it will still fail until Task 6. Skip it for now and focus on the 2 async tests):

```bash
pytest tests/test_mcp_memory_tools.py -v -k "store or recall"
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add codebase_context/mcp_server.py tests/test_mcp_memory_tools.py
git commit -m "feat: add store_memory and recall_memory MCP tools"
```

---

## Task 6: `mcp_server.py` — `record_change_manifest` and `get_change_manifest` Tools

**Files:**
- Modify: `tests/test_mcp_memory_tools.py` (append 2 async tests)
- Modify: `codebase_context/mcp_server.py`

- [ ] **Step 1: Append failing tests to `tests/test_mcp_memory_tools.py`**

Add at the bottom of `tests/test_mcp_memory_tools.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm new ones fail**

```bash
pytest tests/test_mcp_memory_tools.py -v -k "manifest"
```

Expected: `AttributeError: module has no attribute '_handle_record_change_manifest'`

- [ ] **Step 3: Add `record_change_manifest` and `get_change_manifest` to `mcp_server.py`**

**3a.** In `list_tools()`, append these two tools to the returned list (before the closing `]`):

```python
            types.Tool(
                name="record_change_manifest",
                description=(
                    "Record the files and symbols a Dev Agent touched at task.done. "
                    "Call this at the end of each task with the full list of changes."
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
                name="get_change_manifest",
                description=(
                    "Retrieve the change manifest for a task. "
                    "Use this as a Review Agent to see which files and symbols were modified."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task ID to retrieve manifest for"},
                    },
                    "required": ["task_id"],
                },
            ),
```

**3b.** In the `call_tool()` closure, add two more branches before the `else`:

```python
            elif name == "record_change_manifest":
                return await _handle_record_change_manifest(memory_store, arguments)
            elif name == "get_change_manifest":
                return await _handle_get_change_manifest(memory_store, arguments)
```

**3c.** Add two more module-level handler functions at the bottom of `mcp_server.py`:

```python
async def _handle_record_change_manifest(memory_store, arguments: dict):
    from mcp import types

    count = memory_store.record_manifest(
        task_id=arguments["task_id"],
        changes=arguments["changes"],
    )
    return [types.TextContent(type="text", text=json.dumps({"count": count}))]


async def _handle_get_change_manifest(memory_store, arguments: dict):
    from mcp import types

    records = memory_store.get_manifest(task_id=arguments["task_id"])
    return [types.TextContent(type="text", text=json.dumps(records, indent=2))]
```

- [ ] **Step 4: Run all memory tool tests to confirm they pass**

```bash
pytest tests/test_mcp_memory_tools.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add codebase_context/mcp_server.py tests/test_mcp_memory_tools.py
git commit -m "feat: add record_change_manifest and get_change_manifest MCP tools"
```

---

## Task 7: Full Regression

**Files:** none

- [ ] **Step 1: Run the complete test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass — the new tests plus every pre-existing test. Zero failures, zero errors.

- [ ] **Step 2: If any pre-existing test fails**

Stop. Read the error. Do not delete or modify existing tests. Find what the new code broke and fix it in the new code only (`db.py`, `memory_store.py`, or the new sections of `mcp_server.py`).

- [ ] **Step 3: Final commit (if any fixes were needed in step 2)**

```bash
git add <changed files>
git commit -m "fix: resolve regression in memory layer — <short description>"
```

---

## Spec Coverage Checklist

| Spec requirement | Task that covers it |
|---|---|
| `db.py` with `threading.local()` and WAL mode | Task 1 |
| `memory_store.py` with FTS5 events table | Task 2 |
| `memory_store.py` tasks table | Task 3 |
| `memory_store.py` change_manifests table with index | Task 4 |
| `store_memory` MCP tool | Task 5 |
| `recall_memory` MCP tool with agent/event_type filters | Task 5 |
| `record_change_manifest` MCP tool | Task 6 |
| `get_change_manifest` MCP tool | Task 6 |
| DB at `.codebase-context/memory.db` per project | Task 1 (path in `db.py`) |
| No new dependencies (sqlite3 is stdlib) | Verified — no `pyproject.toml` changes needed |
| All existing tests remain green | Task 0 (baseline) + Task 7 (regression) |
| `memory_store.py` receives connection from `db.py` (no direct `sqlite3.connect`) | Task 2 implementation |

All spec requirements are covered.
