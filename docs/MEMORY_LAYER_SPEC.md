# Memory Layer Spec — ccindex Extension

**Status:** Design complete — ready for implementation
**Repo:** `codebase-context` (ccindex)
**Last updated:** 2026-03-25

---

## Context

This document defines the changes needed to extend `ccindex` into the Memory Layer for
Payload Depot's event-driven agent architecture. The memory layer has three responsibilities:

1. **Session memory** — persist agent events, decisions, and task state (replaces `HANDOFF.md`)
2. **Dependency graph** — materialise call/import/inheritance edges for `scope-expansion`
3. **Change manifests** — record what each Dev Agent touched at `task.done` (feeds Review Agent)

The memory database lives **per project** at `.codebase-context/memory.db` — same directory
as the existing ChromaDB store and `index_meta.json`.

---

## What to Keep (no changes)

| Asset | Why |
|---|---|
| `parser.py` | Tree-sitter parsing is solid. Already extracts `Symbol.calls`. |
| `chunker.py` | Symbol → Chunk conversion is unchanged. |
| `embedder.py` | Embedding provider interface is unchanged. |
| `store.py` | ChromaDB vector store stays for semantic search. |
| `repo_map.py` | Repo map generation is unchanged. |
| `retriever.py` | Existing 3 retrieval methods stay as-is. |
| `watcher.py` | Real-time reindexing + git hook is unchanged. |
| `utils.py` | All utilities are unchanged. |
| `config.py` | Language registry and config are unchanged. |
| `models.py` | `IndexMeta`, `IndexStats`, `Symbol`, `Chunk` are unchanged. |
| `cli.py` | CLI entry point is unchanged. |
| All existing tests | Must stay green at baseline before any work begins. |
| All existing MCP tools | `search_codebase`, `get_symbol`, `get_repo_map` are unchanged. |

---

## What to Change

### `indexer.py` — no changes required

Dependency edge extraction has been moved to the LSP layer (see **LSP Layer Decision**
below). `indexer.py` needs no modifications for the memory layer.

---

### `mcp_server.py` — add 4 new tools

Add the following tools to the existing MCP server. Existing tools are untouched.

Dependency traversal tools (`find_callers`, `find_references`, `get_subgraph`) are **not
implemented here** — they are provided by LSP MCP plugins external to this repo (see
**LSP Layer Decision** below).

| Tool | Inputs | Output | Purpose |
|---|---|---|---|
| `store_memory` | `agent`, `event_type`, `content`, `task_id` (optional) | `{id}` | Log an agent event to FTS5 events table |
| `recall_memory` | `query`, `limit` (default 10), `agent` (filter), `event_type` (filter) | Array of events | FTS5 full-text search over session memory |
| `record_change_manifest` | `task_id`, `changes` (array of change objects) | `{count}` | Dev Agent writes touched files/symbols at task.done |
| `get_change_manifest` | `task_id` | Array of change records | Review Agent reads manifest to seed scope-expansion |

---

## What to Add (new modules)

Two new modules. `graph.py` is **not included** — see **LSP Layer Decision**.

### `db.py` — connection manager

`memory_store.py` receives its connection from `db.py` rather than calling
`sqlite3.connect` directly. This prevents `database is locked` errors under concurrent
MCP tool calls and keeps connection management in one place.

```python
# db.py
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
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        setattr(_local, key, conn)
    return getattr(_local, key)
```

> **Why `threading.local()` and not `lru_cache`?** `sqlite3.Connection` objects are
> not thread-safe. `threading.local()` gives each thread its own connection; WAL mode
> handles the read/write concurrency at the SQLite file level. `lru_cache` would return
> the same connection to all threads and is unsafe here.

---

### `memory_store.py`

Manages the SQLite database at `.codebase-context/memory.db`.

**Responsibilities:**
- Create and migrate the database schema on first use
- CRUD for events, tasks, and change_manifests tables
- FTS5 search over events

**Schema:**

```sql
-- Session events (FTS5 full-text search)
CREATE VIRTUAL TABLE IF NOT EXISTS events USING fts5(
  agent,
  event_type,
  content,
  task_id UNINDEXED,
  created_at UNINDEXED,
  tokenize='porter unicode61'
);

-- Task state (replaces HANDOFF.md task queue)
CREATE TABLE IF NOT EXISTS tasks (
  id        TEXT    PRIMARY KEY,
  status    TEXT    NOT NULL,   -- pending | in_flight | done | failed
  agent     TEXT    NOT NULL,
  payload   TEXT,               -- JSON blob
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

-- Change manifests from Dev Agent at task.done
CREATE TABLE IF NOT EXISTS change_manifests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id       TEXT    NOT NULL,
  filepath      TEXT    NOT NULL,
  symbol_name   TEXT,
  change_type   TEXT    NOT NULL,  -- added | modified | deleted
  old_signature TEXT,
  new_signature TEXT
);
CREATE INDEX IF NOT EXISTS idx_cm_task_id ON change_manifests(task_id);
```

**Public interface (methods):**

```python
class MemoryStore:
    def __init__(self, project_root: str): ...  # uses db.get_connection(project_root)

    # Events
    def store_event(self, agent: str, event_type: str, content: str, task_id: str | None) -> str: ...
    def search_events(self, query: str, limit: int, agent: str | None, event_type: str | None) -> list[dict]: ...

    # Tasks
    def create_task(self, task_id: str, agent: str, payload: dict) -> None: ...
    def update_task_status(self, task_id: str, status: str) -> None: ...
    def get_task(self, task_id: str) -> dict | None: ...
    def list_tasks(self, status: str | None = None) -> list[dict]: ...

    # Change manifests
    def record_manifest(self, task_id: str, changes: list[dict]) -> int: ...
    def get_manifest(self, task_id: str) -> list[dict]: ...
```

---

## What to Scrap

Nothing in ccindex needs to be removed. The additions are purely additive.

---

## New dependency

None. `sqlite3` is Python stdlib. No new packages required.

---

## Implementation order

1. Write `db.py` — connection manager + WAL mode + unit test (run tests ✓)
2. Write `memory_store.py` + schema migration + unit tests (run tests ✓)
3. Add 4 new tools to `mcp_server.py` (run tests ✓)
4. Run full test suite — all existing tests must remain green

---

## Integration contract with Payload Depot

Payload Depot agents consume the memory layer exclusively through the MCP tools.
No agent reads `memory.db` directly.

The contract is:

| Agent | Writes | Reads |
|---|---|---|
| Dev Agent | `store_memory`, `record_change_manifest` | — |
| Debugger | `store_memory` | `recall_memory` |
| Review Agent | `store_memory` | `get_change_manifest` |
| Planner | `store_memory` | `recall_memory` |
| Architect | `store_memory` | `recall_memory` |
| Phase Validator | — | `recall_memory`, `get_change_manifest` |

> **Note:** `find_callers`, `find_references`, and `get_subgraph` are provided by LSP MCP
> plugins, not by this server. Review Agent calls those tools directly from the LSP layer.
> See **LSP Layer Decision** below.

---

---

## LSP Layer Decision

**Dependency traversal (`find_callers`, `find_references`, `get_subgraph`) is not
implemented in ccindex.** This decision was made after reviewing the overlap between
the planned `graph.py` module and what LSP MCP plugins already provide.

### Why graph.py was removed

The original design planned a `graph.py` module that would:
- Extract `calls`, `imports`, `inherits` edges from tree-sitter ASTs
- Store them in an `edges` table in `memory.db`
- Serve `find_callers`, `find_references`, `get_subgraph` queries

LSP MCP plugins (pyright, typescript-language-server, clangd) provide equivalent
capabilities at higher quality:

| ccindex graph.py (planned) | LSP plugin equivalent |
|---|---|
| `find_callers(symbol_name)` | `callHierarchy/incomingCalls` |
| `find_references(filepath)` | `textDocument/references` |
| `get_subgraph(depth=N)` | recursive `callHierarchy/incomingCalls` |

Tree-sitter edge extraction is syntactic — it matches call names as strings without
type resolution. LSP analysis is semantic — the language server fully type-checks the
codebase and resolves references correctly across aliases, inheritance, and imports.
LSP is strictly more accurate for dependency traversal.

### What this means for ccindex

- `graph.py` is not built
- No `edges` table in `memory.db`
- `indexer.py` requires no changes
- The memory layer is focused exclusively on agent session state

### LSP plugin installation

LSP plugin detection and installation is handled externally, triggered after
`ccindex index` and `ccindex update` complete. ccindex itself has no
awareness of LSP plugins — it only needs to expose the indexed language set,
which is already derivable from `symbols_cache.json`.

The language → LSP server mapping lives outside this repo. ccindex's `LANGUAGES`
registry in `config.py` is the authoritative source of which languages are present
in a project.

---

## Claude Code session prompt

Use this prompt to start the implementation session in the ccindex repo:

---

```
You are implementing the Memory Layer extension for the ccindex (codebase-context) MCP server.

Read docs/MEMORY_LAYER_SPEC.md first — it defines exactly what to keep, change, add, and the
full SQLite schema, module interfaces, and implementation order.

Before writing any code:
1. Run the existing test suite and confirm it is green (baseline)
2. Read store.py and mcp_server.py to understand the existing patterns
3. Follow the implementation order in the spec exactly

Scope — what this implementation covers:
- db.py: connection manager (sqlite3, threading.local, WAL mode)
- memory_store.py: events (FTS5), tasks, change_manifests tables + full CRUD interface
- mcp_server.py: 4 new tools (store_memory, recall_memory, record_change_manifest, get_change_manifest)

Scope — what this implementation does NOT cover:
- graph.py: not built — dependency traversal (find_callers, find_references, get_subgraph)
  is provided by external LSP MCP plugins, not by this server
- indexer.py: no changes required
- Any LSP client code: out of scope for this repo entirely

Design constraints:
- The memory database lives at .codebase-context/memory.db (per project, same as ChromaDB)
- memory_store.py uses db.py for its connection — never call sqlite3.connect directly
- All existing MCP tools and tests must remain untouched and green throughout
- No new dependencies — sqlite3 is Python stdlib
- Use TDD: write failing tests before each module implementation
- Follow the existing code style (type hints, docstrings on public methods, dataclasses for return types)

The goal is a working MCP server that exposes 7 tools total (3 existing + 4 new) with
session memory writable and searchable by agents, and change manifests recordable and
retrievable by task ID.
```

---
