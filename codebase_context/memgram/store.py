"""SQLite-backed narrative memory store with standalone FTS5."""
from __future__ import annotations

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
"""


class MemgramStore:
    def __init__(self, project_root: str) -> None:
        from codebase_context.db import get_connection
        self._project_root = project_root
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
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

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
