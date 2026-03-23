"""SQLite-backed memory store with FTS5 full-text search."""

from __future__ import annotations

import sqlite3
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL,
    content    TEXT    NOT NULL DEFAULT '',
    type       TEXT    NOT NULL DEFAULT 'handoff',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS obs_fts USING fts5(
    title, content,
    content='observations',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
    INSERT INTO obs_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS obs_ad AFTER DELETE ON observations BEGIN
    INSERT INTO obs_fts(obs_fts, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;
"""


class MemgramStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(_SCHEMA)
        self._con.commit()

    def save(self, title: str, content: str, type: str = "handoff") -> int:
        """Insert an observation. Returns the new row id."""
        cur = self._con.execute(
            "INSERT INTO observations (title, content, type) VALUES (?, ?, ?)",
            (title, content, type),
        )
        self._con.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def context(self, limit: int = 10) -> list[dict]:
        """Return the *limit* most recent observations, newest first."""
        rows = self._con.execute(
            "SELECT id, title, content, type, created_at "
            "FROM observations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
