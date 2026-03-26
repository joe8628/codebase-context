# ccindex-migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `ccindex migrate` CLI subcommand and a `/ccindex-migration` user-level Claude Code slash command that imports legacy `HANDOFF.md` and `DECISIONS.md` blocks into the memgram `MemgramStore`, then archives the source files.

**Architecture:** A new `codebase_context/migrate.py` module holds all parsing and orchestration logic. `cli.py` gains a thin `migrate` subcommand that calls it. A user-level slash command at `~/.claude/commands/ccindex-migration.md` dispatches to the CLI. All logic is covered by tests before implementation.

**Tech Stack:** Python 3.11+, Click, `codebase_context.memgram.store.MemgramStore`, `re`, `pathlib`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `codebase_context/migrate.py` | Create | `AlreadyMigratedError`, `parse_handoff_blocks`, `parse_decision_blocks`, `run_migration` |
| `codebase_context/cli.py` | Modify | Add `migrate` subcommand |
| `tests/test_migrate.py` | Create | Unit + integration tests for migrate module and CLI command |
| `~/.claude/commands/ccindex-migration.md` | Create | User-level slash command |

---

## Task 1: Write failing tests for the migrate module

**Files:**
- Create: `tests/test_migrate.py`

- [ ] **Step 1: Create `tests/test_migrate.py` with all tests**

```python
"""Tests for codebase_context.migrate."""

import pytest
from pathlib import Path
from click.testing import CliRunner

from codebase_context.migrate import (
    AlreadyMigratedError,
    parse_handoff_blocks,
    parse_decision_blocks,
    run_migration,
)
from codebase_context.cli import cli


_HANDOFF_TEXT = """\
# Handoff Log

---

## Block Template

### Agent: <agent name>
**Completed:** <timestamp>
**Task:** <what was asked>

---

### Agent: code-writer
**Completed:** 2026-03-19
**Task:** Fix init command

#### Output Files
- `codebase_context/cli.py` — updated

#### Assumptions Made
- None
"""

_DECISIONS_TEXT = """\
# Decisions

---

## Decision Log

### MCP config target
- **Decision:** Use .claude/settings.json
- **Rationale:** Claude Code reads from there
- **Date:** 2026-03-19

### Skip-before-prompt pattern
- **Decision:** Check before prompting
- **Rationale:** Avoids re-prompting on re-runs
- **Date:** 2026-03-19
"""


# --- parse_handoff_blocks ---

def test_parse_handoff_blocks_extracts_one_real_block():
    blocks = parse_handoff_blocks(_HANDOFF_TEXT)
    assert len(blocks) == 1


def test_parse_handoff_blocks_title_contains_agent_and_task():
    blocks = parse_handoff_blocks(_HANDOFF_TEXT)
    assert blocks[0]["title"] == "Agent: code-writer — Fix init command"


def test_parse_handoff_blocks_type_is_handoff():
    blocks = parse_handoff_blocks(_HANDOFF_TEXT)
    assert blocks[0]["type"] == "handoff"


def test_parse_handoff_blocks_skips_template():
    blocks = parse_handoff_blocks(_HANDOFF_TEXT)
    for b in blocks:
        assert "<" not in b["title"]


def test_parse_handoff_blocks_content_contains_block_text():
    blocks = parse_handoff_blocks(_HANDOFF_TEXT)
    assert "code-writer" in blocks[0]["content"]
    assert "Fix init command" in blocks[0]["content"]


def test_parse_handoff_blocks_empty_on_no_blocks():
    blocks = parse_handoff_blocks("# Handoff Log\n\nNo blocks here.")
    assert blocks == []


# --- parse_decision_blocks ---

def test_parse_decision_blocks_extracts_two_blocks():
    blocks = parse_decision_blocks(_DECISIONS_TEXT)
    assert len(blocks) == 2


def test_parse_decision_blocks_titles():
    blocks = parse_decision_blocks(_DECISIONS_TEXT)
    titles = [b["title"] for b in blocks]
    assert "MCP config target" in titles
    assert "Skip-before-prompt pattern" in titles


def test_parse_decision_blocks_type_is_decision():
    blocks = parse_decision_blocks(_DECISIONS_TEXT)
    for b in blocks:
        assert b["type"] == "decision"


def test_parse_decision_blocks_content_contains_rationale():
    blocks = parse_decision_blocks(_DECISIONS_TEXT)
    assert any("Claude Code reads from there" in b["content"] for b in blocks)


def test_parse_decision_blocks_returns_empty_when_no_decision_log():
    blocks = parse_decision_blocks("# Just a header\n\nNo decision log here.")
    assert blocks == []


# --- run_migration ---

def test_run_migration_returns_correct_counts(tmp_path):
    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    (tmp_path / "DECISIONS.md").write_text(_DECISIONS_TEXT, encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    handoff_count, decision_count = run_migration(str(tmp_path))

    assert handoff_count == 1
    assert decision_count == 2


def test_run_migration_archives_both_files(tmp_path):
    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    (tmp_path / "DECISIONS.md").write_text(_DECISIONS_TEXT, encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    run_migration(str(tmp_path))

    assert not (tmp_path / "HANDOFF.md").exists()
    assert not (tmp_path / "DECISIONS.md").exists()
    assert (tmp_path / "HANDOFF.md.migrated").exists()
    assert (tmp_path / "DECISIONS.md.migrated").exists()


def test_run_migration_raises_if_already_migrated(tmp_path):
    (tmp_path / "HANDOFF.md.migrated").write_text("old", encoding="utf-8")

    with pytest.raises(AlreadyMigratedError):
        run_migration(str(tmp_path))


def test_run_migration_returns_zeros_when_nothing_to_migrate(tmp_path):
    handoff_count, decision_count = run_migration(str(tmp_path))
    assert handoff_count == 0
    assert decision_count == 0


def test_run_migration_handles_missing_decisions_file(tmp_path):
    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    handoff_count, decision_count = run_migration(str(tmp_path))

    assert handoff_count == 1
    assert decision_count == 0
    assert (tmp_path / "HANDOFF.md.migrated").exists()


def test_run_migration_records_saved_to_store(tmp_path):
    from codebase_context.memgram.store import MemgramStore

    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    (tmp_path / "DECISIONS.md").write_text(_DECISIONS_TEXT, encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    run_migration(str(tmp_path))

    store = MemgramStore(str(tmp_path / ".claude" / "memgram.db"))
    records = store.context(limit=10)
    types = [r["type"] for r in records]
    assert "handoff" in types
    assert "decision" in types


# --- CLI subcommand ---

def test_cli_migrate_exits_0_and_prints_summary(tmp_path):
    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    runner = CliRunner()
    result = runner.invoke(cli, ["--root", str(tmp_path), "migrate"])

    assert result.exit_code == 0
    assert "Migrated" in result.output
    assert "1 handoff" in result.output


def test_cli_migrate_exits_1_when_already_migrated(tmp_path):
    (tmp_path / "HANDOFF.md.migrated").write_text("old", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["--root", str(tmp_path), "migrate"])

    assert result.exit_code == 1


def test_cli_migrate_nothing_to_migrate(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--root", str(tmp_path), "migrate"])

    assert result.exit_code == 0
    assert "Nothing to migrate" in result.output
```

- [ ] **Step 2: Run the tests to confirm they all fail**

```bash
cd /workspace && python -m pytest tests/test_migrate.py -v 2>&1 | head -40
```

Expected: `ImportError` or `ModuleNotFoundError` for `codebase_context.migrate` — confirms tests are wired correctly and the module doesn't exist yet.

---

## Task 2: Implement `codebase_context/migrate.py`

**Files:**
- Create: `codebase_context/migrate.py`

- [ ] **Step 1: Create `codebase_context/migrate.py`**

```python
"""Migration helpers: parse HANDOFF.md / DECISIONS.md → MemgramStore."""

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
    """Migrate HANDOFF.md and DECISIONS.md into MemgramStore.

    Inserts one record per block, then renames source files to *.migrated.
    Raises AlreadyMigratedError if archive files already exist.
    Returns (handoff_count, decision_count).
    """
    root = Path(project_root)
    handoff_path = root / "HANDOFF.md"
    decisions_path = root / "DECISIONS.md"
    archived_handoff = root / "HANDOFF.md.migrated"
    archived_decisions = root / "DECISIONS.md.migrated"

    if archived_handoff.exists() or archived_decisions.exists():
        raise AlreadyMigratedError(
            "Migration has already been run — archive files (*.migrated) already exist."
        )

    if not handoff_path.exists() and not decisions_path.exists():
        return (0, 0)

    db_path = str(root / ".claude" / "memgram.db")
    store = MemgramStore(db_path)

    handoff_count = 0
    decision_count = 0

    if handoff_path.exists():
        blocks = parse_handoff_blocks(handoff_path.read_text(encoding="utf-8"))
        for block in blocks:
            store.save(block["title"], block["content"], block["type"])
        handoff_count = len(blocks)
        handoff_path.rename(archived_handoff)

    if decisions_path.exists():
        blocks = parse_decision_blocks(decisions_path.read_text(encoding="utf-8"))
        for block in blocks:
            store.save(block["title"], block["content"], block["type"])
        decision_count = len(blocks)
        decisions_path.rename(archived_decisions)

    return (handoff_count, decision_count)
```

- [ ] **Step 2: Run the parser + run_migration tests**

```bash
cd /workspace && python -m pytest tests/test_migrate.py -v -k "not cli_migrate"
```

Expected: all non-CLI tests pass. The two CLI tests will still fail (no subcommand yet).

---

## Task 3: Add `migrate` subcommand to `cli.py`

**Files:**
- Modify: `codebase_context/cli.py`

- [ ] **Step 1: Add the `migrate` command after the `stats` command (~line 196)**

Find the block:
```python
@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
```

Add the following **after** the `stats` command's closing line:

```python
@cli.command()
@click.pass_context
def migrate(ctx: click.Context) -> None:
    """Migrate HANDOFF.md and DECISIONS.md into the memgram memory layer."""
    from codebase_context.migrate import AlreadyMigratedError, run_migration

    root = ctx.obj["root"]
    try:
        handoff_count, decision_count = run_migration(root)
    except AlreadyMigratedError as exc:
        click.echo(f"Warning: {exc}", err=True)
        raise SystemExit(1)

    if handoff_count == 0 and decision_count == 0:
        click.echo("Nothing to migrate.")
        return

    click.echo(
        f"Migrated {handoff_count} handoff records and {decision_count} decision records."
    )
```

- [ ] **Step 2: Run all migrate tests**

```bash
cd /workspace && python -m pytest tests/test_migrate.py -v
```

Expected: all 19 tests pass.

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
cd /workspace && python -m pytest tests/ -q
```

Expected: all existing tests still pass (total should be 178 + 19 = 197).

- [ ] **Step 4: Commit**

```bash
cd /workspace && git add codebase_context/migrate.py codebase_context/cli.py tests/test_migrate.py
git commit -m "feat: add ccindex migrate command to import HANDOFF.md and DECISIONS.md into memgram"
```

---

## Task 4: Create the user-level slash command

**Files:**
- Create: `~/.claude/commands/ccindex-migration.md`

- [ ] **Step 1: Create `~/.claude/commands/ccindex-migration.md`**

```bash
mkdir -p ~/.claude/commands
```

Then create the file with this content:

```markdown
Find the project root by locating the nearest parent directory that contains a `.git`
folder, starting from the current working directory. If no `.git` folder is found,
use the current working directory.

Run the following command using the Bash tool, substituting the resolved project root:

```
ccindex --root <project_root> migrate
```

Report the command's output to the user exactly as printed. If the command exits
with a non-zero status, also report the warning message from stderr.
```

- [ ] **Step 2: Verify the slash command file is in place**

```bash
cat ~/.claude/commands/ccindex-migration.md
```

Expected: the file contents print correctly.

- [ ] **Step 3: Verify `ccindex migrate --help` works**

```bash
ccindex migrate --help
```

Expected output:
```
Usage: ccindex migrate [OPTIONS]

  Migrate HANDOFF.md and DECISIONS.md into the memgram memory layer.

Options:
  --help  Show this message and exit.
```

- [ ] **Step 4: Smoke-test against the real project files**

```bash
cd /workspace && ccindex --root . migrate
```

Expected: prints `Migrated N handoff records and M decision records.` and `HANDOFF.md` / `DECISIONS.md` are renamed to `*.migrated`.

Running again immediately after:
```bash
ccindex --root . migrate
```
Expected: prints `Warning: Migration has already been run...` and exits 1.
