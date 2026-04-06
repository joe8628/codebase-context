@.codebase-context/repo_map.md
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
2. Call `mem_context` (memgram MCP) to load prior memories for this project.
3. Read `CONVENTIONS.md`.

**During every session:**
- After each significant finding, bugfix, or decision: call `mem_save`:
  - `title`: verb + what (e.g. "Fixed N+1 query in UserList")
  - `type`: `handoff` | `decision` | `bugfix` | `architecture` | `discovery`
  - `content`: freeform with ## What / ## Why / ## Where / ## Learned sections

**After every completed feature or fix:**
1. Call `mem_save` summarising what was completed (`type: handoff`).
2. Call `mem_session_end` with a one-line summary.
3. Commit and push code only: `git add <changed files> && git commit && git push`

> Do not write to HANDOFF.md or DECISIONS.md — they are removed.
> Query past decisions with: `mem_search(query="<topic>", type="decision")`

## Codebase Context

The MCP codebase-context tool is available. Use it to explore the codebase:
- `search_codebase` — semantic search over code symbols
- `get_symbol` — exact symbol lookup by name
- `get_repo_map` — compact file/class/function outline

### Navigation priority — follow this order every time

1. **Repo map first** (`@.codebase-context/repo_map.md` is loaded at session start). Check it before searching anything — it gives a full file/symbol outline at zero cost.
2. **MCP semantic search** (`search_codebase`, `get_symbol`) — for unfamiliar code or concept-level queries. Only covers languages indexed by ccindex (Python, TypeScript, C, C++).
3. **`Grep` tool** — for content search in any language, including files not in the index. Use `Grep` (not `bash grep`) for pattern matching across the codebase.
4. **`Glob` tool** — for finding files by name pattern (e.g. `**/*.sh`, `tests/test_*`). Use `Glob` (not `bash find` or `bash ls`) when you know the filename shape but not the path.
5. **`Read`** — only after you have located the right file via one of the above. Do not speculatively read files you haven't targeted.

### Grep vs Glob — when to use each

| Tool | Use when | Example |
|---|---|---|
| `Glob` | You know the filename pattern | `**/*.sh`, `src/**/*.py` |
| `Grep` | You know what the code says | `pattern="class Indexer"`, `pattern="def substitute"` |

Never run `bash grep`, `bash find`, or `bash ls` to search the codebase — use the dedicated `Grep` and `Glob` tools instead. They are visible in the tool UI, respect permission settings, and return structured results.
