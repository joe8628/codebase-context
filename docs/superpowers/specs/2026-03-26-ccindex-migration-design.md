# Design: /ccindex-migration Slash Command

**Date:** 2026-03-26
**Status:** Approved

---

## Overview

A Claude Code slash command `/ccindex-migration` that migrates legacy `HANDOFF.md` and `DECISIONS.md` files into the memgram memory layer (`MemgramStore`). After successful import, both source files are archived (renamed with `.migrated` suffix). The command is user-level (`~/.claude/commands/`) so it works in any project where `ccindex` is installed.

---

## Architecture

Four deliverables:

```
~/.claude/commands/ccindex-migration.md   ← user-level slash command
codebase_context/migrate.py               ← parser + migration logic
codebase_context/cli.py                   ← new `migrate` subcommand (thin wrapper)
tests/test_migrate.py                     ← unit tests
```

---

## Components

### 1. Slash command — `~/.claude/commands/ccindex-migration.md`

A prompt-only file that instructs Claude to:
1. Find the project root (nearest `.git` dir or cwd)
2. Run `ccindex migrate` via Bash
3. Report the result to the user

The slash command contains no parsing logic — it is a thin, stable dispatcher.

### 2. Parser + migration logic — `codebase_context/migrate.py`

**`parse_handoff_blocks(text: str) -> list[dict]`**
Splits on `### Agent:` headers. Each block becomes:
```python
{"title": "Agent: <name> — <task>", "content": "<full block text>", "type": "handoff"}
```

**`parse_decision_blocks(text: str) -> list[dict]`**
Splits on `### <title>` headers (inside `## Decision Log`). Each block becomes:
```python
{"title": "<decision title>", "content": "<full block text>", "type": "decision"}
```

**`run_migration(project_root: str) -> tuple[int, int]`**
Orchestrates the full migration:
1. Resolve paths for `HANDOFF.md` and `DECISIONS.md`
2. Check for `.migrated` archives — raise `AlreadyMigratedError` if found
3. Parse both files (skip gracefully if a file is absent)
4. Insert each record into `MemgramStore` via `store.save(title, content, type)`
5. Rename source files to `<file>.migrated`
6. Return `(handoff_count, decision_count)`

**`AlreadyMigratedError`** — raised when archive files already exist, caught by the CLI to print a warning and exit non-zero.

### 3. CLI subcommand — `codebase_context/cli.py`

```
ccindex migrate [--root PATH]
```

- Calls `run_migration(root)`
- On success: prints `Migrated N handoff records and M decision records.`
- On `AlreadyMigratedError`: prints warning and exits with code 1
- Resolves `db_path` the same way `_setup_memgram` does: `<project_root>/.claude/memgram.db`

---

## Data Flow

```
HANDOFF.md ──► parse_handoff_blocks() ──► MemgramStore.save(type="handoff")
                                                         │
DECISIONS.md ─► parse_decision_blocks() ─► MemgramStore.save(type="decision")
                                                         │
Both files renamed to *.migrated ◄──────── on success ──┘
```

---

## Error Handling

| Condition | Behaviour |
|---|---|
| `.migrated` file already exists | `AlreadyMigratedError` → warn + exit 1 |
| Neither source file exists | Print "Nothing to migrate." and exit 0 |
| One file absent, one present | Migrate the present file only |
| Malformed block (no header text) | Skip the block, continue |
| `MemgramStore` DB path doesn't exist | `MemgramStore.__init__` creates it automatically |

---

## Testing

`tests/test_migrate.py` covers:

- `parse_handoff_blocks` extracts correct title, content, type per block
- `parse_handoff_blocks` ignores the template block (the one with `<agent name>` placeholder)
- `parse_decision_blocks` extracts correct title, content, type per block
- `run_migration` inserts records into a real (tmp) `MemgramStore`
- `run_migration` archives both files on success
- `run_migration` raises `AlreadyMigratedError` if `.migrated` files already exist
- `run_migration` handles missing files gracefully
- CLI `ccindex migrate` exits 0 on success and prints summary
- CLI `ccindex migrate` exits 1 and prints warning if already migrated

---

## Out of Scope

- Migrating worktree copies (`.worktrees/*/HANDOFF.md`) — only the project root files are migrated
- Deduplication within memgram — not needed; migration is a one-shot operation (guarded by the already-migrated check)
- Modifying `CLAUDE.md` references — left for the developer to clean up manually
