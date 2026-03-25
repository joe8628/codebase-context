"""SQLite-backed memory store for agent session events, tasks, and change manifests."""
from __future__ import annotations

import time

from codebase_context.db import get_connection


_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS events USING fts5(
  agent,
  event_type,
  content,
  task_id UNINDEXED,
  created_at UNINDEXED,
  tokenize='porter unicode61'
);

CREATE TABLE IF NOT EXISTS tasks (
  id         TEXT    PRIMARY KEY,
  status     TEXT    NOT NULL,
  agent      TEXT    NOT NULL,
  payload    TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS change_manifests (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id       TEXT    NOT NULL,
  filepath      TEXT    NOT NULL,
  symbol_name   TEXT,
  change_type   TEXT    NOT NULL,
  old_signature TEXT,
  new_signature TEXT
);

CREATE INDEX IF NOT EXISTS idx_cm_task_id ON change_manifests(task_id);
"""


class MemoryStore:
    """Manages the per-project memory layer SQLite database."""

    def __init__(self, project_root: str) -> None:
        self._conn = get_connection(project_root)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- Events ---

    def store_event(
        self,
        agent: str,
        event_type: str,
        content: str,
        task_id: str | None = None,
    ) -> str:
        """Insert a session event. Returns the row ID as a string."""
        cur = self._conn.execute(
            "INSERT INTO events(agent, event_type, content, task_id, created_at) VALUES (?,?,?,?,?)",
            (agent, event_type, content, task_id or "", str(int(time.time()))),
        )
        self._conn.commit()
        return str(cur.lastrowid)

    def search_events(
        self,
        query: str,
        limit: int = 10,
        agent: str | None = None,
        event_type: str | None = None,
    ) -> list[dict]:
        """FTS5 full-text search over events. Post-filters by agent or event_type if given."""
        rows = self._conn.execute(
            "SELECT rowid, agent, event_type, content, task_id, created_at "
            "FROM events WHERE events MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()

        results = []
        for row in rows:
            if agent and row["agent"] != agent:
                continue
            if event_type and row["event_type"] != event_type:
                continue
            results.append({
                "id": str(row["rowid"]),
                "agent": row["agent"],
                "event_type": row["event_type"],
                "content": row["content"],
                "task_id": row["task_id"],
                "created_at": row["created_at"],
            })
        return results
