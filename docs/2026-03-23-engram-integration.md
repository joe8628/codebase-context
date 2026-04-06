# Plan: Replace HANDOFF.md / DECISIONS.md with Engram

**Date:** 2026-03-23
**Status:** Ready to implement

---

## Context

Agents currently append to `HANDOFF.md` and `DECISIONS.md` after each session. These files grow unboundedly, consume context window, and defeat the purpose of ccindex — agents pick them up as passive context instead of querying the semantic index. The goal is to eliminate all human-readable session/decision files from the repo and replace them with engram: a production-ready, MCP-native memory system backed by SQLite+FTS5.

Rather than building a custom Python implementation, we use engram as-is and integrate it into `ccindex init`.

**No markdown files remain in the repo for session context. Agents must query engram via MCP tools.**

---

## Why Engram, Not a Custom Solution

Engram (https://github.com/Gentleman-Programming/engram) already solves every requirement:
- Single `observations` table with `type`, `title`, `content`, `topic_key`, deduplication
- `mem_save(title, content, type)` with What/Why/Where/Learned structure
- `mem_search` / `mem_context` for agent retrieval
- `mem_session_start` / `mem_session_end` for grouping
- MIT license, Go binary (~30MB), zero Python dependencies

Building it in Python would be reinventing it.

---

## Type Convention (Handoff vs Decisions)

Engram's `type` field distinguishes memory kinds. We use:

| Type | Replaces | Meaning |
|---|---|---|
| `handoff` | HANDOFF.md block | What was completed this session, what's next |
| `decision` | DECISIONS.md block | Non-trivial architectural or design choice |
| `bugfix` | — | Root cause + fix summary |
| `architecture` | — | Structural design choices |
| `discovery` | — | Unexpected findings |

Agents filter by type when querying: `mem_search(query="auth", type="decision")`.

---

## What We Build

**Nothing new in Python for memory storage.** No `session_history/` module, no `parser.py`, `store.py`, `schema.sql`, or standalone MCP script.

Three targeted changes only:

---

## Change 1 — `codebase_context/cli.py`

Add `_setup_engram(project_root: str)` alongside the existing `_setup_mcp_server()`.

```python
_ENGRAM_KEY = "engram"

def _setup_engram(project_root: str) -> None:
    """Register engram memory MCP in .claude/settings.json if engram is on PATH."""
```

Logic:
1. Check `shutil.which("engram")`.
   - Not found → print install instructions and return (no error, graceful skip):
     ```
     engram not found. Install with: brew install gentleman-programming/tap/engram
     Or download from: https://github.com/Gentleman-Programming/engram/releases
     Skipping engram MCP registration.
     ```
2. Read `.claude/settings.json` (same pattern as `_setup_mcp_server`).
3. If `"engram"` key already present in `mcpServers` → skip with "engram already configured".
4. Prompt: `"Register engram memory MCP for this project? [Y/n]"`.
5. On accept: write entry:
   ```json
   {
     "command": "engram",
     "args": ["mcp"],
     "env": {
       "ENGRAM_DATA_DIR": "<abs_path_to_project_root/.claude/>"
     }
   }
   ```
6. On decline: skip silently.

Wire `_setup_engram(project_root)` into the `init` command, after `_setup_mcp_server()`.

**Per-project isolation:** `ENGRAM_DATA_DIR` set to the project's `.claude/` directory scopes the DB to the project (DB lives at `.claude/engram.db`). Without this, engram defaults to `~/.engram/` — global, shared across all projects.

---

## Change 2 — `_update_gitignore()` in `cli.py`

Add `engram.db` to gitignore entries:

```python
# add alongside existing .codebase-context/ entry:
".claude/engram.db",
```

---

## Change 3 — `CLAUDE.md` Session Protocol

Replace the HANDOFF.md/DECISIONS.md ritual entirely.

**New Session Protocol section:**

```markdown
## Session Protocol

**At the start of every session:**
1. Run `git pull`.
2. Call `mem_context` (engram MCP) to load prior memories for this project.
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
> Query past decisions with: mem_search(query="<topic>", type="decision")
```

Also update `AGENTS.md`: each agent's **Writes:** line must replace all `HANDOFF.md`/`DECISIONS.md` references with `mem_save` / `mem_session_end`.

---

## Files to Remove

- `HANDOFF.md` — replaced by engram `type: handoff` observations
- `DECISIONS.md` — replaced by engram `type: decision` observations

Remove after first successful `ccindex init` with engram registered and existing content optionally migrated (see below).

---

## Migration — `ccindex migrate-history`

Add a `migrate-history` subcommand to the CLI that reads `HANDOFF.md` and `DECISIONS.md`, parses them into blocks, and calls `engram save` for each.

**Same command pattern for both files — only `--type` differs:**
```bash
# HANDOFF.md blocks  → --type handoff
# DECISIONS.md blocks → --type decision
```

### Implementation (`codebase_context/cli.py`)

```python
def _migrate_history(project_root: str) -> None:
    """Parse HANDOFF.md and DECISIONS.md and insert each block into engram."""
```

Logic:
1. Check `shutil.which("engram")` — exit with error if not found.
2. For each source file and its type:
   - `HANDOFF.md` → type `handoff`, split on `^### Agent:`, extract title from `### Agent: X` line
   - `DECISIONS.md` → type `decision`, split on `^### `, extract title from `### X` line
3. Skip blocks where title contains `<` (template placeholders).
4. For each real block: call `subprocess.run(["engram", "save", title, content, "--type", type])`.
5. Print count: `Migrated N handoff blocks, M decision blocks.`

**Usage:**
```bash
ccindex migrate-history          # reads from project root
ccindex migrate-history --dry-run  # prints what would be saved, no writes
```

After successful migration, the command prints:
```
Migrated 3 handoff blocks, 2 decision blocks.
You can now delete HANDOFF.md and DECISIONS.md.
```

---

## Files to Modify

| File | Change |
|---|---|
| `codebase_context/cli.py` | Add `_setup_engram()`, `_migrate_history()`; call `_setup_engram` from `init`; add `migrate-history` subcommand; add `engram.db` to gitignore step |
| `CLAUDE.md` | Replace Session Protocol section; remove HANDOFF.md/DECISIONS.md references |
| `AGENTS.md` | Update each agent's Writes: field |

## Files to Create

None.

## Files to Delete

| File | When |
|---|---|
| `HANDOFF.md` | After engram is registered and content migrated |
| `DECISIONS.md` | Same — only if it exists and has content |

## Files NOT to Build

- `codebase_context/session_history/` — not needed
- `session-history-mcp.py` — not needed
- Any custom parser, store, schema, or mcp_tools module

---

## Tests

Add to `tests/test_cli.py` alongside existing `TestSetupMcpServer`:

```
class TestSetupEngram:
    test_skips_when_engram_not_on_path          # shutil.which returns None → no entry written
    test_prints_install_hint_when_not_found     # message contains brew/release URL
    test_registers_entry_when_accepted          # entry present in settings.json
    test_sets_engram_data_dir_to_claude_dir     # ENGRAM_DATA_DIR == project/.claude/
    test_skips_if_entry_already_present         # idempotent
    test_skips_when_user_declines               # no entry written on 'n'

class TestMigrateHistory:
    test_migrate_handoff_calls_engram_save      # subprocess called with --type handoff per block
    test_migrate_decisions_calls_engram_save    # subprocess called with --type decision per block
    test_skips_template_blocks                  # blocks with '<' in title are skipped
    test_dry_run_prints_without_calling_engram  # --dry-run: no subprocess calls, output shown
    test_errors_when_engram_not_on_path         # exits with message if engram missing
    test_missing_file_skipped_gracefully        # no DECISIONS.md → skips that file, continues
```

Mock `shutil.which` and use the existing `tmp_project` fixture pattern.

---

## Verification

1. `pytest tests/test_cli.py` — all tests pass (existing + new)
2. `ccindex init` in temp dir with engram mocked on PATH → `.claude/settings.json` has `engram` entry with `ENGRAM_DATA_DIR` set to `<tmp>/.claude/`
3. `ccindex init` without engram on PATH → graceful skip, install hint printed, no crash
4. `ccindex init` twice → idempotent, no duplicate entry
5. Manual smoke test: register engram, call `mem_save` from Claude Code, confirm DB at `.claude/engram.db`
