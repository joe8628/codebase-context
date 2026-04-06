# Concept: Layer 1 Code Map — On-Demand Access

**Status**: READY
**Complexity**: MODERATE
**Created**: 2026-04-06
**Updated**: 2026-04-06

## Summary

Currently, `repo_map.md` (the tree-sitter-generated structural outline of the codebase) is injected
into every Claude Code session wholesale via an `@.codebase-context/repo_map.md` reference in
`CLAUDE.md`. For this repo (~50 files, 426 symbols), that costs ~8k tokens per session regardless
of whether the agent ever needs structural context. The concept is to shift from "load upfront" to
"load on demand": remove the `@`-reference from `CLAUDE.md` and let agents call the existing
`get_repo_map` MCP tool only when they actually need the code map. The underlying storage model
(tree-sitter → repo_map.md on disk, served via `get_repo_map`) is unchanged.

---

## Accepted

- **Storage model unchanged**: tree-sitter parsing, repo_map.md on disk, `get_repo_map` MCP tool —
  all remain exactly as they are. Only the consumption pattern changes.
- **`get_repo_map` already exists**: the MCP tool surface requires no new implementation. The
  mechanism for on-demand access is already present.
- **Freshness model unchanged**: git hooks trigger `ccindex update` outside sessions; repo_map.md
  on disk stays fresh. Agents never call `ccindex update`.
- **Token cost direction is correct**: 8k tokens injected unconditionally is a real cost. For
  sessions that only do a targeted bugfix or a single file edit, the map is wasted context.
- **CLAUDE.md carries a lightweight navigation hint**: the `@`-reference is removed; a short
  instruction replaces it telling agents *when* to call `get_repo_map`. Agents do not self-discover
  purely from the tool description — the hint is the trigger signal.
- **Direction A — correct routing via hint, no new tools**: agents use `search_codebase` and
  `get_symbol` for targeted queries (cheap), and `get_repo_map` only for full structural overview.
  8k tokens are paid only when a full overview is genuinely warranted. No implementation changes
  required beyond the CLAUDE.md hint.
- **Partial access is already solved by existing tools**: `get_symbol` (~50–200 tokens) and
  `search_codebase` (~200–500 tokens) cover most structural queries without the full map.
- **Navigation priority order confirmed** — replaces the old "repo map first" rule:
  1. `search_codebase` / `get_symbol` — targeted queries (symbol location, concept search)
  2. `get_repo_map` — only for full structural overview (new file placement, architecture
     questions, cross-cutting changes)
  3. `Grep` / `Glob` — content/filename patterns not in the index
  4. `Read` — only after locating the right file via the above

---

## Blocked

*(none)*

---

## Discarded

- **Direction B — extend `get_repo_map` with partial access** (`filepath`/`summary` parameters):
  adds implementation complexity for gains already covered by `search_codebase` and `get_symbol`.
  Rejected in favour of correct routing via the CLAUDE.md hint.

---

## Sub-concepts

*(not required — MODERATE complexity)*

---

## Ready for Architecture

**Concept summary**: Remove the `@.codebase-context/repo_map.md` wholesale injection from
`CLAUDE.md` and replace it with a lightweight navigation hint. Agents use `search_codebase` and
`get_symbol` for targeted structural queries, and call `get_repo_map` only when a full codebase
overview is genuinely needed. The 8k token cost becomes opt-in rather than unconditional. No
changes to storage, tooling, or MCP server — only `CLAUDE.md` is modified.

**Key constraints**:
- Underlying storage model unchanged: tree-sitter → repo_map.md on disk → `get_repo_map` tool
- No new MCP tools, no new parameters on existing tools
- `CLAUDE.md` is the only file modified
- Freshness model unchanged: git hooks keep repo_map.md current; agents never call `ccindex update`

**Confirmed directions**:
- Navigation priority order: `search_codebase`/`get_symbol` first → `get_repo_map` for full
  overview → `Grep`/`Glob` for patterns → `Read` after locating the target file
- CLAUDE.md carries a lightweight hint specifying *when* each tool applies — agents do not
  self-discover purely from tool descriptions
- 8k tokens are paid only when the agent genuinely needs the full structural view

**Discarded alternatives**:
- Direction B (extend `get_repo_map` with `filepath`/`summary` parameters) — implementation
  complexity not justified; `search_codebase` and `get_symbol` already cover partial-access cases

**Blocked (deferred)**:
*(none)*

**Open questions for the architect**:
- What is the exact wording of the navigation hint in `CLAUDE.md`? It must be short enough to
  be lightweight (~50–80 tokens) but precise enough that agents don't default to `get_repo_map`
  on every task.
- Should the hint live inside the existing "Navigation priority" section (replacing the current
  rule) or as a new standalone note near the MCP tools documentation?

