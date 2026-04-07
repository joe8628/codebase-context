@CONVENTIONS.md
@AGENTS.md

# codebase-context

<!-- Replace codebase-context with your project name. -->

**Language/toolchain:** Python + ruff/mypy
**One-line description:** > A self-contained, locally-running context management tool for Claude Code agents.

---

## Conventions

Read `CONVENTIONS.md` before writing or reviewing any code. All coding decisions
must follow the rules defined there.

## Agent Registry

Read `AGENTS.md` for the full list of available agents, their roles, trigger
conditions, and expected outputs.

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

## Codebase Context

The MCP codebase-context tool is available. Use it to explore the codebase:
- `search_codebase` — semantic search over code symbols
- `get_symbol` — exact symbol lookup by name
- `get_repo_map` — compact file/class/function outline

### Navigation priority — follow this order every time

1. **`search_codebase` / `get_symbol`** — for targeted queries: finding a symbol, concept search, locating a utility. ~50–500 tokens per call.
2. **`get_repo_map`** — only when you need a full structural overview: new file placement, architecture questions, cross-cutting changes. ~8k tokens — call sparingly.
3. **`Grep` tool** — for content patterns in any file, including languages not in the index.
4. **`Glob` tool** — for finding files by name pattern (e.g. `**/*.sh`).
5. **`Read`** — only after you have located the right file via one of the above.

### Grep vs Glob — when to use each

| Tool | Use when | Example |
|---|---|---|
| `Glob` | You know the filename pattern | `**/*.sh`, `src/**/*.py` |
| `Grep` | You know what the code says | `pattern="class Indexer"`, `pattern="def substitute"` |

Never run `bash grep`, `bash find`, or `bash ls` to search the codebase — use the dedicated `Grep` and `Glob` tools instead. They are visible in the tool UI, respect permission settings, and return structured results.
