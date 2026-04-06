# Concept: Layer 3 Merge Audit — memgram + memory_store into a Single Unified Layer

**Status**: READY
**Complexity**: COMPLEX
**Created**: 2026-04-06
**Updated**: 2026-04-06 (all 9 open questions resolved — READY)

## Accepted

- **Server consolidation only — two DB files, one process.** The merge is `ccindex serve` holding
  two store instances (`MemgramStore` + `MemoryStore`) pointed at two separate DB files
  (`memgram.db` + `memory.db`) both in `.codebase-context/`. No schema unification. No data
  migration beyond moving `memgram.db` from `.claude/` to `.codebase-context/`. The two schemas
  remain independent and evolve separately. This resolves **OQ1** and **MG1**.

- **`MemgramStore` adopts `db.py` (Option A).** `MemgramStore` is fully committed to living
  inside `codebase_context` — no standalone portability requirement. `db.py` is extended with a
  `db_filename` parameter (`"memory.db"` default, `"memgram.db"` for memgram). `MemgramStore`
  replaces `sqlite3.connect(check_same_thread=False)` with `get_connection(project_root,
  db_filename="memgram.db")`. One connection manager, one WAL strategy, one place to change
  threading behaviour. This resolves **OQ2** and **G1**.

- **All 8 Layer 3 MCP tools renamed to semantic groups.** Two prefixes, one per sub-layer:

  | Old name | New name | Sub-layer |
  |---|---|---|
  | `mem_save` | `narrative_save` | 3a — narrative |
  | `mem_context` | `narrative_context` | 3a — narrative |
  | `mem_search` | `narrative_search` | 3a — narrative |
  | `mem_session_end` | `narrative_session_end` | 3a — narrative |
  | `store_memory` | `coord_store_event` | 3b — coordination |
  | `recall_memory` | `coord_recall_events` | 3b — coordination |
  | `record_change_manifest` | `coord_record_manifest` | 3b — coordination |
  | `get_change_manifest` | `coord_get_manifest` | 3b — coordination |

  `CLAUDE.md` session protocol updated to reference new tool names. All existing agent
  system prompts and session protocol docs updated accordingly. This resolves **OQ7**
  and **MG3**.

- **Type fields enforced at the application layer, two separate enums.** Both stores
  raise `ValueError` on unknown type values. Enums are defined as module-level constants:

  ```python
  # memgram/store.py
  VALID_OBSERVATION_TYPES = {
      "handoff", "decision", "bugfix", "architecture", "discovery", "session_end"
  }

  # memory_store.py
  VALID_EVENT_TYPES = {
      "task_started", "task_completed", "task_failed",
      "agent_action", "decision", "error"
  }
  ```

  The two namespaces are kept separate — narrative types and coordination types serve
  different concerns and agents writing to one store have no reason to know the other's
  vocabulary. This resolves **OQ9** and **G5**.

- **`ccindex upgrade` owns settings and schema upgrades (permanent).** `ccindex upgrade`
  upgrades the binary AND removes the stale `memgram` MCP entry from `.claude/settings.json`,
  ensuring only `codebase-context: ccindex serve` is present. Applies all schema changes for
  the current version. Safe to re-run. This is the ongoing upgrade path for every future
  release. `ccindex migrate` is NOT responsible for settings. This resolves **OQ6** and
  the settings half of **MG4**.

- **`ccindex migrate` is a bridge command (eventually deprecated).** Handles the one-time
  old-to-new data migration: moves `.claude/memgram.db` → `.codebase-context/memgram.db`
  and transforms the old schema (content-backed FTS + base table + triggers → standalone
  FTS5, Unix INTEGER timestamps). Start fresh — existing narrative history is not preserved.
  `ccindex serve` refuses to start on the old schema and directs the user to run
  `ccindex migrate`. Once every user is past this version, `ccindex migrate` is deprecated
  and removed. This resolves **OQ5** and the data half of **MG4**.

- **`memgram.db` migration is explicit and start-fresh.** Existing narrative history is not
  preserved on upgrade. `ccindex migrate` is the single explicit command that moves
  `.claude/memgram.db` → `.codebase-context/memgram.db` and applies the new schema (standalone
  FTS5, Unix INTEGER timestamps). `ccindex serve` detects the old schema on startup and refuses
  to start with a clear message directing the user to run `ccindex migrate`. No silent or
  automatic migration. This resolves **OQ5** and **MG4**.

- **All timestamps use Unix INTEGER.** All `created_at` / `updated_at` columns across both
  stores use `INTEGER` (Unix seconds) set by Python `int(time.time())`. The ISO string
  `DEFAULT (datetime('now'))` in `observations` is removed — FTS5 standalone tables cannot
  use computed defaults, so Python must supply it regardless (no extra migration cost).
  Human-readable display via `datetime(created_at, 'unixepoch')` in SQL when needed.
  This resolves **OQ4** and **G3**.

- **`MemgramStore` simplified to standalone FTS5.** The content-backed FTS + base table +
  2 triggers are replaced by a single standalone FTS5 virtual table (same pattern as
  `MemoryStore.events`). `type` and `created_at` become `UNINDEXED` columns. `context()`
  uses `ORDER BY rowid DESC` (insertion order, equivalent to `ORDER BY id DESC` on the old
  base table). `save()` inserts directly into the FTS table — no trigger chain. `UPDATE` on
  observations is not possible with standalone FTS, but narrative memory is append-only by
  design so no functionality is lost. Both schemas now use the same FTS5 pattern.
  This resolves **OQ3** and **G2**.

---

## Current State

### MemgramStore — Layer 3a (Narrative Memory)

**File:** `codebase_context/memgram/store.py`
**DB:** `.claude/memgram.db` (moving to `.codebase-context/memgram.db`)
**Server:** `ccindex mem-serve` (standalone, to be deprecated)

**Responsibility:** Cross-session narrative memory. Agents save handoff / decision / bugfix /
architecture / discovery observations at session end and load them proactively at session start.

**Schema:**
- `observations` table — base table: `id INTEGER PK`, `title TEXT`, `content TEXT`, `type TEXT`, `created_at TEXT`
- `obs_fts` — content-backed FTS5 virtual table (`content='observations'`, synced via two triggers)
- FTS indexes: `title`, `content`; the base table is the authoritative store

**Query surface:**
- `save(title, content, type)` → int
- `context(limit)` → list[dict] — N most recent observations, ordered by insertion id DESC
- `search(query, type, limit)` → list[dict] — FTS5 MATCH with optional type filter
- `session_end(summary)` → None — shorthand for `save("Session ended", summary, "session_end")`

**Connection model:** `sqlite3.connect(db_path, check_same_thread=False)` — single shared connection,
no per-thread isolation.

**MCP tools exposed:** `mem_save`, `mem_context`, `mem_search`, `mem_session_end`

---

### MemoryStore — Layer 3b (Coordination State)

**File:** `codebase_context/memory_store.py`
**DB:** `.codebase-context/memory.db`
**Server:** `ccindex serve` (main process)

**Responsibility:** Intra-session coordination. Tracks task lifecycle, logs agent events, records
per-task change manifests at `task.done` for the Review Agent.

**Schema:**
- `events` — standalone FTS5 virtual table (direct, no base table): `agent`, `event_type`,
  `content`, `task_id UNINDEXED`, `created_at UNINDEXED`
- `tasks` — standard table: `id TEXT PK`, `status TEXT`, `agent TEXT`, `payload TEXT (JSON)`,
  `created_at INTEGER`, `updated_at INTEGER`
- `change_manifests` — standard table: `id INTEGER PK AUTOINCREMENT`, `task_id TEXT`,
  `filepath TEXT`, `symbol_name TEXT`, `change_type TEXT`, `old_signature TEXT`, `new_signature TEXT`
- Index: `idx_cm_task_id ON change_manifests(task_id)`

**Query surface:**
- `store_event(agent, event_type, content, task_id)` → str
- `search_events(query, limit, agent, event_type)` → list[dict]
- `create_task(task_id, agent, payload)` → None
- `update_task_status(task_id, status)` → None
- `get_task(task_id)` → dict | None
- `list_tasks(status)` → list[dict]
- `record_manifest(task_id, changes)` → int
- `get_manifest(task_id)` → list[dict]

**Connection model:** `db.py` — `threading.local()` per-thread connections, WAL mode enabled.

**MCP tools exposed:** `store_memory`, `recall_memory`, `record_change_manifest`, `get_change_manifest`

---

## Merge Rationale

The concept log `ccindex-three-layer-memory.md` confirms the following as accepted:

1. **Single `ccindex serve` process** — all 11 MCP tools (3 Layer 1 + 4 Layer 3b + 4 Layer 3a)
   served from one entry point, one line in `.claude/settings.json`.
2. **`ccindex mem-serve` deprecated** — memgram's standalone server is folded into the main server.
3. **All data in `.codebase-context/`** — both DB files move there; `.claude/memgram.db` is relocated.
4. **Zero new pip dependencies** — consolidation uses only existing deps.

The merge is motivated by operational simplicity: one MCP server registration, one data directory,
unified connection management. It is not motivated by schema unification — whether the two DB files
merge into one `context.db` remains explicitly deferred.

---

## Conceptual Gaps

Gaps in the existing Layer 3 design, independent of the merge decision.

### G1 — MemgramStore connection model is thread-unsafe

`MemgramStore` uses `sqlite3.connect(db_path, check_same_thread=False)`. This disables SQLite's
thread-check warning but does not provide per-thread safety — a single connection is shared across
all threads with no locking. Under concurrent MCP tool calls from multiple threads (which the
MCP server does dispatch), this is a data-corruption risk.

`MemoryStore` solved this correctly with `threading.local()` in `db.py`. `MemgramStore` has not
adopted the same pattern. The spec does not acknowledge this discrepancy.

### G2 — FTS5 architecture is divergent

The two stores use incompatible FTS5 patterns:

| | MemgramStore | MemoryStore |
|---|---|---|
| Pattern | Content-backed (`content='observations'`) | Standalone (direct) |
| Triggers | Two triggers (`obs_ai`, `obs_ad`) | None |
| Base table | `observations` (authoritative) | FTS table IS the store |
| NULL support | Not applicable (base table) | Worked around (NULL → `""`) |

Content-backed FTS allows querying the base table independently of FTS. Standalone FTS is simpler
but all data lives in the virtual table, which has quirks (e.g., NULL not supported in UNINDEXED
columns). Neither pattern is wrong, but having both in the same codebase adds maintenance overhead
and makes any future schema consolidation more complex.

### G3 — Timestamp types are inconsistent

- `MemgramStore.observations.created_at` — `TEXT DEFAULT (datetime('now'))` — ISO 8601 string,
  generated by SQLite at insert time
- `MemoryStore.events.created_at` — stored as `str(int(time.time()))` — Unix timestamp as a TEXT
  string in FTS5
- `MemoryStore.tasks.created_at / updated_at` — `INTEGER` — Unix timestamp

Three different timestamp representations across two stores in the same layer.

### G4 — `mem_context` has no recency weighting or age filter

`context(limit)` returns the N most recent observations by insertion order. In a mature project
with months of session history, old handoffs surface with equal weight alongside recent ones. There
is no decay function, age cutoff, or relevance filter. The only control is `limit`. This is a
design gap in the narrative memory model — useful context and stale context are indistinguishable.

### G5 — `observations.type` is an unenforced open string

`CLAUDE.md` lists valid types: `handoff | decision | bugfix | architecture | discovery`. The code
hardcodes `"session_end"` in `session_end()`. No enum, no validation, and no constraint exists at
the DB or application layer. Any string is silently accepted. The same absence applies to
`events.event_type` in `memory_store`.

### G6 — FTS5 NULL workaround is a leaky abstraction

In `MemoryStore.store_event()`, `task_id or ""` converts `None` to an empty string because FTS5
standalone tables cannot store NULL in any column. Querying "events with no task" requires
`WHERE task_id = ""`, which is not documented and will surprise any future developer or agent
querying the store directly.

### G7 — No schema migration mechanism exists in either store

Both stores use `CREATE TABLE IF NOT EXISTS` — idempotent on first run but silent on upgrades.
Adding a column to `observations` or `events` requires a manual `ALTER TABLE` on every existing
database. No version table, no migration runner, and no migration tests exist. This gap is latent
but will become a blocker as the schema evolves.

---

## Merge-Specific Gaps

Gaps that appear specifically because the two stores are being consolidated.

### MG1 — The deferred DB-file question is a prerequisite, not a detail

The concept log defers "single vs dual DB file" to the architect as an "implementation detail."
It is not. The choice determines everything downstream:

- **Two files, one server:** each store keeps its own schema, WAL, and connection pool. No schema
  migration. No FTS architecture unification required. The merge is purely operational (one process).
- **One file (`context.db`):** one WAL, one connection pool. All schema differences (FTS pattern,
  timestamp types, type enum) must be resolved before migration. Existing `memgram.db` and
  `memory.db` files must be migrated with data preserved. This is a significant implementation.

The concept is incomplete without acknowledging that "merge" means one of these two things. The
architect cannot make the DB decision in isolation — it determines the scope of the entire effort.

### MG2 — Connection management is incompatible if DB files are unified

If both stores share one DB file, they cannot use two different connection strategies simultaneously:

- `MemgramStore` holds `self._con` (one shared connection, `check_same_thread=False`)
- `MemoryStore` uses `db.get_connection(project_root)` (`threading.local()`, WAL mode)

One strategy must be chosen and the other discarded. `MemgramStore` must adopt `db.py`, or `db.py`
must be extended to support multiple named DB paths. If DB files remain separate, `MemgramStore`
still needs to adopt thread-safe connections (see G1) but the two strategies don't conflict.

### MG3 — 8 MCP tools with parallel-but-differently-named operations in one namespace

After consolidation, agents receive these tool pairs in one namespace:

| Narrative (3a) | Coordination (3b) | Operation |
|---|---|---|
| `mem_save` | `store_memory` | write a text payload |
| `mem_search` | `recall_memory` | FTS search over stored text |
| `mem_context` | *(none)* | load recent context |
| `mem_session_end` | *(none)* | terminal write |
| *(none)* | `record_change_manifest` | write structured change records |
| *(none)* | `get_change_manifest` | read structured change records |

The naming conventions are inconsistent (`mem_*` prefix vs `*_memory` suffix). The functional
overlap between `mem_save`/`store_memory` and `mem_search`/`recall_memory` is high. An agent
choosing between them must rely entirely on tool description quality — there is no structural
signal in the API. The concept log flags this as DEFERRED but understates the risk: agent
tool-call errors here corrupt the memory layer silently (data written to the wrong store).

### MG4 — `ccindex mem-serve` deprecation path is undefined

The concept says `ccindex mem-serve` is deprecated. Three concrete migration concerns are unspecified:

1. **Settings migration:** Projects with `"memgram": {"command": "ccindex", "args": ["mem-serve"]}`
   in `.claude/settings.json` will break silently after deprecation. `ccindex init` and
   `ccindex doctor` must detect and remove stale entries — this logic does not exist.
2. **Data migration:** `memgram.db` moves from `.claude/memgram.db` to
   `.codebase-context/memgram.db`. No migration step is defined. Projects with existing narrative
   memory will lose it silently if the old path is abandoned without a copy/move.
3. **Graceful deprecation signal:** There is no plan for a `ccindex mem-serve` deprecation
   warning during a transition period before removal.

### MG5 — No enforced boundary prevents agents from writing to the wrong store

`observations` (memgram) and `events` (memory_store) both accept free-text from agents. Nothing
in the schema, server routing, or validation prevents an agent from saving a narrative handoff to
`store_memory` or a structured task event to `mem_save`. The boundary is a convention documented
in `CLAUDE.md` — not a constraint. Under a single server, both tool sets are always visible,
and a misrouted write is silent and unrecoverable.

### MG6 — No unified session-start query after consolidation

Currently, a session start requires:
1. Call `mem_context` → recent narrative observations
2. (If resuming a task) Call `recall_memory` with a known task_id → coordination events

After consolidation, both tools live in one server, but the session protocol still requires the
agent to know which to call and in what order. There is no `get_session_context` or equivalent
unified entry point. The asymmetric access model (proactive narrative, reactive coordination) is
correct in principle but is not expressed as a single composable call. The agent's session-start
protocol document (`CLAUDE.md`) must be precise enough to substitute for this missing abstraction.

### MG7 — Two temporal models are not reconciled

`MemgramStore` organises memory around **sessions** — bounded by `session_end()`. `MemoryStore`
organises memory around **tasks** — bounded by task status (`pending → done`). These do not align:

- A session can contain multiple tasks
- A task can span multiple sessions (in-flight across context resets)
- `session_end` is a memgram concept; `memory_store` has no session concept at all

After merge, an agent asking "what happened in the last session?" and "what is the state of
task X?" are answered by different stores with different temporal semantics. No bridge between
these two time horizons is defined.

---

## Open Questions

Decisions that MUST be made before implementation can begin.

1. ~~**DB consolidation scope**~~ — **RESOLVED.** Server consolidation only. Two DB files,
   one `ccindex serve` process. No schema unification. See **Accepted** above.

2. ~~**`MemgramStore` thread safety**~~ — **RESOLVED.** `MemgramStore` adopts `db.py` (Option A).
   `db.py` extended with `db_filename` parameter. See **Accepted** above.

3. ~~**FTS5 architecture standardisation**~~ — **RESOLVED.** `MemgramStore` simplified to
   standalone FTS5. Both schemas now use the same pattern. See **Accepted** above.

4. ~~**Timestamp unification**~~ — **RESOLVED.** All `created_at` / `updated_at` columns use
   Unix INTEGER set by Python `int(time.time())`. The ISO string default in `observations` is
   dropped — FTS5 standalone tables cannot use computed defaults anyway (OQ3 resolution makes
   this a zero-cost change). See **Accepted** below.

5. ~~**`memgram.db` data migration**~~ — **RESOLVED.** Start fresh — existing narrative history
   is not preserved on upgrade. `ccindex migrate` handles the file move (`.claude/memgram.db`
   → `.codebase-context/memgram.db`) and schema transformation as an explicit user action.
   `ccindex serve` detects the old schema on startup and refuses to start, printing:
   `"Run ccindex migrate to update memgram.db to the new schema."` No silent migration,
   no auto-migration. This resolves **OQ5** and **MG4** (file move and schema change).
   See **Accepted** below.

6. ~~**`ccindex mem-serve` settings migration**~~ — **RESOLVED.** Two commands with distinct
   responsibilities: `ccindex upgrade` (permanent) removes the stale `memgram` MCP entry from
   `.claude/settings.json` and applies all schema/settings changes for the current version —
   safe to re-run, the ongoing upgrade path for every future release. `ccindex migrate`
   (bridge, eventually deprecated) is the one-time command that moves `.claude/memgram.db` →
   `.codebase-context/memgram.db` and transforms the old schema. `ccindex serve` refuses to
   start on old schema and directs the user to run `ccindex migrate` first. See **Accepted**
   below.

7. ~~**MCP tool naming**~~ — **RESOLVED.** All 8 Layer 3 tools renamed to semantic groups with
   a shared prefix per sub-layer. `narrative_*` for cross-session narrative memory (memgram),
   `coord_*` for intra-session coordination state (memory_store). Existing `mem_*` and
   `store_memory`/`recall_memory` names are replaced. `CLAUDE.md` session protocol updated
   to use new names. See **Accepted** below.

8. ~~**Unified session-start tool**~~ — **RESOLVED.** No new tool. Two separate calls remain:
   `narrative_context` at session start (always), `coord_recall_events` only when explicitly
   resuming a known in-flight task. `CLAUDE.md` session protocol made precise about the
   sequence. This resolves **OQ8** and **MG6**.

9. ~~**`type` / `event_type` enum**~~ — **RESOLVED.** Enforced at the application layer
   (`ValueError` on unknown type). Two separate enums, one per store. See **Accepted** below.

---

## Ready for Architecture

**Concept summary**: Layer 3 consolidation merges `ccindex mem-serve` (memgram) into the main
`ccindex serve` process as a server-only operation — two DB files (`memgram.db` + `memory.db`)
in `.codebase-context/`, one MCP entry, one process. No schema unification. `MemgramStore` is
simplified to standalone FTS5 (dropping the content-backed pattern and its triggers) and adopts
`db.py` for thread-safe connections. All timestamps unified to Unix INTEGER. All 8 Layer 3 MCP
tools renamed to semantic groups: `narrative_*` for cross-session observations, `coord_*` for
intra-session coordination state. Type fields enforced at the application layer via module-level
enums. Upgrade path: `ccindex upgrade` handles settings and schema changes permanently;
`ccindex migrate` is a one-time bridge for old `memgram.db` data (start fresh, eventually
deprecated). `ccindex serve` refuses to start on old schema.

**Key constraints**:
- Server consolidation only — two DB files, one `ccindex serve` process, no schema unification
- `MemgramStore` adopts `db.py` (`db_filename="memgram.db"`) — no more `check_same_thread=False`
- `MemgramStore` schema: standalone FTS5 only, no base `observations` table, no triggers
- All `created_at` / `updated_at` columns: `INTEGER` Unix seconds set by Python `int(time.time())`
- All 8 Layer 3 tool names changed — `CLAUDE.md` and all agent session protocols must be updated
- `ccindex serve` detects old schema on startup and refuses to start with a migration message
- `ccindex migrate` is a bridge command — start fresh, no data preservation, eventually removed
- `ccindex upgrade` is the permanent ongoing upgrade path for settings + schema changes
- `VALID_OBSERVATION_TYPES` and `VALID_EVENT_TYPES` enforced in their respective store modules

**Confirmed directions**:
- `narrative_*` prefix for memgram tools (save, context, search, session_end)
- `coord_*` prefix for memory_store tools (store_event, recall_events, record_manifest, get_manifest)
- Two separate type enums — narrative and coordination vocabularies are independent
- No unified session-start tool — protocol doc is the right place to express the two-call sequence
- `ccindex upgrade` absorbs settings cleanup; `ccindex migrate` handles old data bridge only

**Discarded alternatives**:
- Single `context.db` (schema unification) — write contention, migration complexity, schema
  coupling; two files with independent WALs is the stronger design
- Content-backed FTS for `MemgramStore` — three schema objects (base table + FTS + triggers)
  replaced by one standalone FTS table; UPDATE not used so nothing lost
- `check_same_thread=False` shared connection in `MemgramStore` — thread-unsafe under concurrent
  MCP calls; replaced by `db.py` threading.local pattern
- `mem_*` / `store_memory` / `recall_memory` naming — replaced by semantic group prefixes
- Unified session-start MCP tool — blurs `narrative_`/`coord_` separation; protocol doc sufficient
- Unified type enum across both stores — different vocabularies for different concerns

**Blocked (deferred)**:
- Tool description quality audit (11 tools in one namespace) — no functional gap, documentation
  concern; deferred post-consolidation
- Environments without first-party LSP MCP plugins lose `find_references` / `get_call_hierarchy`
  — accepted trade-off; target deployment always includes LSP plugins
- `payload-depot` submodule sync to 3-layer architecture — out of scope for this concept

**Open questions for the architect**:
- `db.py` interface change: add `db_filename: str = "memory.db"` parameter — confirm the
  signature and whether the key in `threading.local` should encode both `project_root` and
  `db_filename` to prevent cross-store connection reuse
- `ccindex serve` old-schema detection: what is the minimum signal to distinguish old from new
  `memgram.db`? (Presence of `observations` base table vs standalone FTS table is the reliable
  check — confirm detection logic)
- `ccindex upgrade` project-scope detection: when run outside a project root, print a reminder
  to run again from each project directory — confirm the detection heuristic (`.codebase-context/`
  presence or `.git` presence)
- `ccindex migrate` deprecation timeline: at what version or date should the command be removed?
  Define the condition (e.g. two major versions after the consolidation release)
- `CLAUDE.md` session protocol rewrite: `mem_context` → `narrative_context`,
  `mem_save` → `narrative_save`, `mem_search` → `narrative_search`,
  `mem_session_end` → `narrative_session_end` — confirm all references updated before ship
