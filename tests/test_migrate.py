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
    (tmp_path / "DECISIONS.md.migrated").write_text("old", encoding="utf-8")

    with pytest.raises(AlreadyMigratedError):
        run_migration(str(tmp_path))


def test_run_migration_does_not_raise_if_only_one_archive_exists(tmp_path):
    (tmp_path / "DECISIONS.md.migrated").write_text("old", encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    # Only decisions archive exists — handoff can still be migrated (returns zeros if no source)
    handoff_count, decision_count = run_migration(str(tmp_path))
    assert handoff_count == 0
    assert decision_count == 0


def test_run_migration_returns_zeros_when_nothing_to_migrate(tmp_path):
    handoff_count, decision_count = run_migration(str(tmp_path))
    assert handoff_count == 0
    assert decision_count == 0
    assert not (tmp_path / "HANDOFF.md.migrated").exists()
    assert not (tmp_path / "DECISIONS.md.migrated").exists()


def test_run_migration_handles_missing_decisions_file(tmp_path):
    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    handoff_count, decision_count = run_migration(str(tmp_path))

    assert handoff_count == 1
    assert decision_count == 0
    assert (tmp_path / "HANDOFF.md.migrated").exists()


def test_run_migration_handles_missing_handoff_file(tmp_path):
    (tmp_path / "DECISIONS.md").write_text(_DECISIONS_TEXT, encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    handoff_count, decision_count = run_migration(str(tmp_path))

    assert handoff_count == 0
    assert decision_count == 2
    assert (tmp_path / "DECISIONS.md.migrated").exists()


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
    (tmp_path / "DECISIONS.md.migrated").write_text("old", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, ["--root", str(tmp_path), "migrate"])

    assert result.exit_code == 1


def test_cli_migrate_nothing_to_migrate(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--root", str(tmp_path), "migrate"])

    assert result.exit_code == 0
    assert "Nothing to migrate" in result.output


def test_cli_migrate_prints_both_counts(tmp_path):
    (tmp_path / "HANDOFF.md").write_text(_HANDOFF_TEXT, encoding="utf-8")
    (tmp_path / "DECISIONS.md").write_text(_DECISIONS_TEXT, encoding="utf-8")
    (tmp_path / ".claude").mkdir()

    runner = CliRunner()
    result = runner.invoke(cli, ["--root", str(tmp_path), "migrate"])

    assert result.exit_code == 0
    assert "1 handoff" in result.output
    assert "2 decision" in result.output
