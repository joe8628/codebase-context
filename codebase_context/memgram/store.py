"""SQLite-backed narrative memory store with standalone FTS5."""
from __future__ import annotations

import struct
import time

VALID_OBSERVATION_TYPES = {
    "handoff", "decision", "bugfix", "architecture", "discovery", "session_end"
}

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS observations USING fts5(
    title,
    content,
    type     UNINDEXED,
    created_at UNINDEXED
);
CREATE TABLE IF NOT EXISTS observations_vec (
    rowid   INTEGER PRIMARY KEY,
    embedding BLOB NOT NULL
);
"""


class MemgramStore:
    def __init__(self, project_root: str, embedder=None) -> None:
        from codebase_context.db import get_connection
        self._project_root = project_root
        self._embedder = embedder
        conn = get_connection(project_root, db_filename="memgram.db")
        conn.executescript(_SCHEMA)
        conn.commit()

    def _conn(self):
        from codebase_context.db import get_connection
        return get_connection(self._project_root, db_filename="memgram.db")

    def save(self, title: str, content: str, type: str = "handoff") -> int:
        """Insert an observation. Returns the rowid."""
        if type not in VALID_OBSERVATION_TYPES:
            raise ValueError(
                f"Unknown type {type!r}. Valid: {sorted(VALID_OBSERVATION_TYPES)}"
            )
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO observations (title, content, type, created_at) VALUES (?, ?, ?, ?)",
            (title, content, type, int(time.time())),
        )
        rowid = cur.lastrowid
        if self._embedder is not None:
            vec = self._embedder.embed_one(title + " " + content)
            blob = struct.pack(f"{len(vec)}f", *vec)
            conn.execute(
                "INSERT INTO observations_vec (rowid, embedding) VALUES (?, ?)",
                (rowid, blob),
            )
        conn.commit()
        return rowid  # type: ignore[return-value]

    def context(self, limit: int = 10) -> list[dict]:
        """Return the *limit* most recent observations, newest first."""
        rows = self._conn().execute(
            "SELECT rowid AS id, title, content, type, created_at "
            "FROM observations ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, type: str | None = None, limit: int = 10) -> list[dict]:
        """Full-text search over title and content. Optionally filter by type."""
        restricted_query = "{title content} : " + query
        conn = self._conn()
        if type is not None:
            rows = conn.execute(
                "SELECT rowid AS id, title, content, type, created_at "
                "FROM observations WHERE observations MATCH ? AND type = ? "
                "ORDER BY rank LIMIT ?",
                (restricted_query, type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT rowid AS id, title, content, type, created_at "
                "FROM observations WHERE observations MATCH ? "
                "ORDER BY rank LIMIT ?",
                (restricted_query, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def session_end(self, summary: str) -> None:
        """Record a session-end observation with the given summary."""
        self.save("Session ended", summary, "session_end")
