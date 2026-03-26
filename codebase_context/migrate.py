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
