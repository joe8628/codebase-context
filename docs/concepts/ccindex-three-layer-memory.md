# Concept: ccindex — Three-Layer Agent Memory

**Status**: READY
**Complexity**: COMPLEX
**Created**: 2026-04-06
**Updated**: 2026-04-06 (merged: Layer 1 on-demand model, Layer 3 consolidation + tool renames, ccindex migrate expanded)

## Summary

`codebase-context` (ccindex) is a locally-running agent context system organized in three
complementary layers, each providing a distinct kind of awareness to Claude Code agents. Layer 1
provides a structural map and semantic vector search over parsed code symbols (tree-sitter →
ChromaDB); `repo_map.md` is served on-demand via `get_repo_map` rather than injected at session
start. Layer 2 performs LSP binary presence detection — checking for and optionally installing
language server binaries — but exposes no MCP tools of its own; navigation tools are the
responsibility of first-party LSP MCP plugins. Layer 3 persists two kinds of agent memory:
cross-session narrative observations (memgram, standalone FTS5) and intra-session coordination state
(tasks, events, change manifests, SQLite FTS5). All 11 MCP tools are served from a single
`ccindex serve` process. Everything runs locally: no external services, no API keys, no Docker.

---

## Accepted

- **Three-layer structure** is the correct framing: code map / LSP navigation / agent memory.
- **Product description evolves with the product**: no fixed description is locked in at concept
  stage. The README and one-liner will be updated as each layer stabilises.
- **Layer 3 access modes are asymmetric by design**:
  - 3a (memgram): proactive load at session start — every session calls `narrative_context`
  - 3b (memory_store): reactive/on-demand — only loaded when continuing an in-flight task
- **All ccindex data is per-project, scoped to `.codebase-context/`**: no global or cross-project
  state. `memgram.db` moves from `.claude/` to `.codebase-context/` as part of MCP consolidation.
  Narrative memory is repo-scoped — agents get complete context over this repo, not over everything
  the user has touched across all projects.
- **Layer 1 scope**: tree-sitter parsing → Chunk embedding → ChromaDB vector store → repo_map.md.
  Tools: `search_codebase`, `get_symbol`, `get_repo_map`. Status: stable, well-tested.
- **Layer 2 scope** (revised): LSP binary presence detection only. `ccindex init` and
  `ccindex doctor` check for and optionally install missing language server binaries
  (pyright-langserver via npm, typescript-language-server via npm, clangd via apt/brew). No MCP
  tools are exposed. Navigation capabilities (find definition, find references, get signature,
  call hierarchy) are the exclusive responsibility of first-party LSP MCP plugins installed in
  the project. Layer 2 in ccindex does not duplicate that surface.
- **Layer 3 is intentionally split into two sub-layers** with different time horizons:
  - **3a — Narrative memory** (`memgram/`): Cross-session. Agents save handoff/decision/bugfix
    observations at session end; retrieve at session start. Simple `observations` table + FTS5.
    Standalone `ccindex mem-serve` process. Replaced an external Go binary (engram).
  - **3b — Coordination state** (`memory_store.py` + `db.py`): Intra-session. Tracks task
    lifecycle (pending/in_flight/done/failed), session events, and per-task change manifests.
    `events` FTS5 + `tasks` + `change_manifests` tables. Integrated into main `ccindex serve`.
- **graph.py was deliberately not built**: dependency traversal (find_callers, get_subgraph) was
  removed from scope because LSP provides it at higher semantic accuracy than tree-sitter string
  matching. This decision is documented in `docs/MEMORY_LAYER_SPEC.md`.
- **Per-project isolation**: all data in `.codebase-context/` — `chroma/` (Layer 1), `memory.db`
  (Layer 3b), and `memgram.db` (Layer 3a). No `.claude/` data files.
- **Zero new pip dependencies** for Layers 2 and 3: stdlib only (`subprocess`, `sqlite3`).
  Layer 1 carries the heavy deps (fastembed, chromadb, tree-sitter grammars).
- **Single `ccindex serve` entry confirmed**: all 11 tools (3 Layer 1 + 0 Layer 2 + 4 Layer 3b +
  4 Layer 3a memgram) will be consolidated into one `ccindex serve` process. One entry in
  `.claude/settings.json`. `ccindex mem-serve` becomes deprecated. Memgram's standalone
  portability is a future concern — if needed, a separate standalone version can be extracted
  later, but it is not a current requirement.
- **Layer 3 MCP tool names resolved** — all 8 Layer 3 tools renamed to semantic group prefixes:
  `narrative_save`, `narrative_context`, `narrative_search`, `narrative_session_end` (Layer 3a);
  `coord_store_event`, `coord_recall_events`, `coord_record_manifest`, `coord_get_manifest` (Layer 3b).
  Old `mem_*` and `store_memory`/`recall_memory` names are replaced everywhere.
- **`ccindex upgrade` owns settings and schema upgrades (permanent)**: removes the stale `memgram`
  MCP entry from `.claude/settings.json`; applies all schema changes for the current version. Safe
  to re-run. The ongoing upgrade path for every future release.
- **`ccindex migrate` expanded scope (bridge, eventually deprecated)**: handles the one-time
  migration for old file-based agent memory (HANDOFF.md/DECISIONS.md → memory store) AND
  moves `.claude/memgram.db` → `.codebase-context/memgram.db` with schema transformation
  (content-backed FTS + triggers → standalone FTS5, Unix INTEGER timestamps). Start fresh —
  existing narrative history is not preserved. `ccindex serve` refuses to start on old schema
  and directs the user to run `ccindex migrate`.
- **Index freshness model is solved**: `ccindex update` is a user-invoked command outside sessions.
  During agent sessions, git hooks trigger `ccindex update` automatically. Agents never call
  `ccindex update` explicitly mid-session. Layer 1 freshness is the hook's responsibility.

---

## Blocked

- [DEFERRED] **Two DB files within `.codebase-context/`**: after MCP consolidation, both
  `memgram.db` (narrative) and `memory.db` (coordination) will live in `.codebase-context/`.
  Whether to keep them as two separate SQLite files or merge them into a single `context.db`
  is an implementation-level decision deferred to the architect. Both options are valid;
  the schema, migration complexity, and WAL behaviour under concurrent MCP tool calls are
  the deciding factors. — *Deferred: no architectural blocker, implementation detail.*

- [DEFERRED] **payload-depot submodule is on an older version**: The embedded `codebase-context/`
  submodule in payload-depot only contains Layer 1 (no LSP, no memory). It does not reflect the
  current 3-layer architecture. Sync/update strategy is out of scope here but should be an open
  question for the architect. — *Deferred: out of scope for this concept.*

- [DEFERRED] **`ccindex serve` tool count is growing (11 tools)**: As layers accumulate, the single
  MCP server entry point becomes a broad namespace. No concrete problem yet, but an agent receiving
  11 tools in a session needs good tool descriptions to route correctly. Tool description quality
  has not been formally audited. — *Deferred: no functional gap, documentation concern.*

- [DEFERRED] **Layer 3b `store_memory`/`recall_memory` vs Layer 3a `mem_save`/`mem_search` are
  functionally similar to agents**: Both accept a text payload and return searchable results.
  The distinction (coordination events vs narrative observations) is clear in the spec, but agent
  confusion is a realistic failure mode if session protocol documentation is weak.
  — *Deferred: a documentation and session-prompt concern, not an architecture gap.*

- [DEFERRED] **Environments without first-party LSP MCP plugins lose reactive code navigation**:
  With Layer 2 tools removed, `find_references` and `get_call_hierarchy` have no equivalent in
  any remaining layer. Layer 1's `get_symbol` partially covers `find_definition`; `Grep` covers
  textual reference lookup but misses dynamic dispatch, interface implementations, and type-aware
  call chains. This gap only applies to projects where ccindex is the sole MCP server (no pyright
  MCP, no clangd MCP). In the target deployment (LSP plugins present), no gap exists.
  — *Deferred: acceptable trade-off given the decision rationale. Not a blocker.*

---

## Discarded

- **engram (Go binary)** — originally integrated as the session memory backend. Replaced by
  `memgram` (Python-native, zero extra install step). Engram's API was the inspiration for the
  `mem_save / mem_context / mem_search / mem_session_end` interface.
- **graph.py (tree-sitter edge extraction)** — planned `edges` table in `memory.db` for
  `find_callers`, `find_references`, `get_subgraph`. Removed because LSP provides semantically
  accurate dependency traversal that tree-sitter string matching cannot match. See
  `docs/MEMORY_LAYER_SPEC.md` § LSP Layer Decision.
- **Separate MCP servers per layer** — early design considered one server per layer (3 entries in
  `.claude/settings.json`). Consolidated to one `ccindex serve` for Layers 1+2+3b, keeping only
  memgram as a separate process because it was designed as a standalone MCP server from the start.
- **`ccindex mem-serve` as permanent separate entry** — confirmed consolidated into `ccindex serve`.
  `ccindex mem-serve` will be deprecated. Memgram standalone extraction deferred to a future version
  if the need arises.

---

## Sub-concepts

### Layer 1 — Code Map (tree-sitter + ChromaDB)
**Status**: READY
- parser.py → chunker.py → embedder.py → store.py → repo_map.py → indexer.py → retriever.py
- MCP tools: search_codebase, get_symbol, get_repo_map
- Static output: repo_map.md on disk, served on-demand via `get_repo_map`; `@`-reference removed
  from `CLAUDE.md` — agents call `get_repo_map` only when a full structural overview is needed
- Dynamic output: ANN semantic search (cosine, 768-dim Jina embeddings)
- Navigation priority: `search_codebase`/`get_symbol` (targeted) → `get_repo_map` (full overview)
  → `Grep`/`Glob` (content/filename patterns) → `Read` (after locating the right file)

### Layer 2 — LSP Binary Detection
**Status**: READY (scope narrowed — tools removed, binary detection retained)
- **Responsibility**: detect and optionally install LSP language server binaries
- **No MCP tools**: Layer 2 exposes nothing to agents. Navigation is the LSP plugin's job.
- **`ccindex init`**: checks for pyright-langserver (npm), typescript-language-server (npm),
  clangd (apt/brew); offers to install npm-managed binaries; prints manual instructions for clangd
- **`ccindex doctor`**: runs the same binary checks as a health audit
- **What was removed**: `find_definition`, `find_references`, `get_signature`,
  `get_call_hierarchy`, `warm_file` — all five MCP tools are gone
- **Why removed**: first-party LSP MCP plugins (pyright MCP, clangd MCP) expose the same tools
  at the platform level. Duplicating them in ccindex adds MCP namespace noise and token cost
  with no benefit when plugins are present.
- **Implementation note for architect**: the lsp/ package (router.py, handlers.py, client.py,
  filters.py, positions.py) was built to support the removed tools. Whether to keep it as dead
  code, remove it, or extract it is an implementation-level decision — the concept only requires
  that its tools are no longer wired into `ccindex serve`.

### Layer 3a — Narrative Memory (memgram)
**Status**: READY
- memgram/store.py (MemgramStore: standalone FTS5, db.py threading.local connection) → mcp_server.py
- MCP tools: narrative_save, narrative_context, narrative_search, narrative_session_end
- Folded into `ccindex serve` (consolidation); `ccindex mem-serve` deprecated
- Data file: `.codebase-context/memgram.db` (per-project)
- Cross-session: agents save at session end, load at session start via `narrative_context`
- Session protocol documented in `CLAUDE.md`; asymmetric from Layer 3b (proactive vs reactive)
- Type enum: VALID_OBSERVATION_TYPES = {handoff, decision, bugfix, architecture, discovery, session_end}

### Layer 3b — Coordination State (memory_store)
**Status**: READY
- db.py (threading.local WAL connection) → memory_store.py (events FTS5 + tasks + change_manifests)
- MCP tools: coord_store_event, coord_recall_events, coord_record_manifest, coord_get_manifest
- Integrated into main ccindex serve
- Data file: `.codebase-context/memory.db`
- Intra-session: task lifecycle tracking and change manifest handoff between dev/review agents
- **Access mode confirmed**: on-demand / task-continuation only. Agents load coordination state
  only when explicitly continuing an in-flight task. Not loaded at session start.
- Type enum: VALID_EVENT_TYPES = {task_started, task_completed, task_failed, agent_action, decision, error}
- Agent-to-tool contract is documented in `docs/MEMORY_LAYER_SPEC.md` — deferred to architect
  to surface in agent system prompts.

---

## Ready for Architecture

**Concept summary**: `codebase-context` (ccindex) is a locally-running, per-project agent context
system built in three layers served from a single `ccindex serve` MCP entry point. Layer 1 provides
a structural map (tree-sitter → repo_map.md, served on-demand via `get_repo_map`) and semantic
vector search (ChromaDB) via 3 MCP tools. Layer 2 performs LSP binary presence detection only — checking for
and optionally installing language server binaries during `ccindex init` and `ccindex doctor`;
it exposes no MCP tools and delegates all navigation capabilities to first-party LSP MCP plugins.
Layer 3 provides two complementary agent memory stores, both scoped to `.codebase-context/`: narrative
cross-session memory (memgram, proactively loaded at session start) and structured intra-session
coordination state (memory_store, loaded on-demand when continuing a task) via 8 MCP tools. All data
is per-project; no global or cross-project state exists. Total: 11 MCP tools.

**Key constraints**:
- All data lives in `.codebase-context/` — no global state, no `.claude/` data files
- Single `ccindex serve` MCP entry — 11 tools from one process (3 Layer 1 + 4 Layer 3b + 4 Layer 3a)
- Layer 2 exposes zero MCP tools — binary detection only, no navigation surface
- `ccindex mem-serve` must be deprecated; memgram folded into the main server
- All 8 Layer 3 MCP tool names changed — `CLAUDE.md` and all agent session protocols must
  reference the `narrative_*` and `coord_*` prefixed names; old `mem_*` and generic names removed
- `ccindex init` and `ccindex doctor` must be updated to register only `ccindex serve`
- `memgram.db` lives in `.codebase-context/`; `ccindex migrate` handles the one-time file move
  and schema transform for existing projects
- Zero new pip dependencies — consolidation uses only existing deps
- All existing tests must remain green throughout any consolidation work

**Confirmed directions**:
- Three-layer structure: code map / LSP navigation / agent memory
- Layer 3 asymmetric access: memgram proactively loaded at session start; memory_store
  loaded on-demand only when explicitly continuing an in-flight task
- Index freshness via hooks — agents never call `ccindex update` mid-session
- Navigation priority: `search_codebase`/`get_symbol` (targeted) → `get_repo_map` (full overview
  only) → `Grep`/`Glob` (patterns) → `Read`; repo_map 8k token cost is opt-in, not unconditional
- Layer 3 tool prefixes: `narrative_*` for cross-session observations, `coord_*` for intra-session
  coordination state — prefix is the structural signal agents use to route between sub-layers
- `ccindex upgrade` handles settings cleanup permanently; `ccindex migrate` is a one-time bridge
- Product description evolves with the product — no fixed description locked in at concept stage

**Discarded alternatives**:
- engram (Go binary) — replaced by Python-native memgram
- graph.py (tree-sitter edge extraction) — superseded by LSP semantic dependency traversal
- Separate MCP server per layer — consolidated to single `ccindex serve`
- Global/cross-project narrative memory — rejected; context must be repo-scoped and clean
- Layer 2 MCP navigation tools (find_definition, find_references, get_signature,
  get_call_hierarchy, warm_file) — duplicated what first-party LSP MCP plugins provide;
  removed to reduce namespace noise and token cost

**Blocked (deferred)**:
- payload-depot submodule sync to 3-layer version — out of scope for this concept
- Tool description quality audit (11 tools in one namespace) — documentation concern, not blocker
- Environments without any LSP MCP plugins lose `find_references` and `get_call_hierarchy` with
  no equivalent — accepted trade-off given the target deployment always includes LSP plugins

**Open questions for the architect**:
- ~~Should `memory.db` and `memgram.db` merge into a single `context.db`?~~ — RESOLVED: two
  separate files, one `ccindex serve` process, no schema unification.
- ~~What is the migration path for existing projects with `memgram.db` in `.claude/`?~~ —
  RESOLVED: `ccindex migrate` handles file move + schema transform (start fresh); `ccindex upgrade`
  removes the stale `memgram` MCP entry from `.claude/settings.json`.
- ~~Should `ccindex init` remove any existing `memgram` entry or only add if absent?~~ —
  RESOLVED: `ccindex upgrade` owns settings cleanup; `ccindex init` adds `ccindex serve` only
  if absent.
- How should the 11-tool namespace (`narrative_*` vs `coord_*`) be documented so agents can route
  correctly? Tool description quality across all 11 tools has not been formally audited.
- Should the `lsp/` package (router.py, handlers.py, client.py, filters.py, positions.py) be
  removed entirely, kept as dormant code, or kept because binary-detection logic depends on it?
  (The binary checks in `ccindex init` likely only need `shutil.which` — not the full LspClient.)
