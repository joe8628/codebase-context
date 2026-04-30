"""SQLite-backed narrative memory store with standalone FTS5."""
from __future__ import annotations

import math
import struct
import time

VALID_OBSERVATION_TYPES = {
    "handoff", "decision", "bugfix", "architecture", "discovery", "session_end"
}

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return dot / mag if mag else 0.0


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
        """Full-text search over title and content. Optionally filter by type.

        When an embedder is present, merges BM25 and cosine rankings via RRF.
        """
        restricted_query = "{title content} : " + query
        conn = self._conn()
        base_sql = (
            "SELECT rowid AS id, title, content, type, created_at "
            "FROM observations WHERE observations MATCH ?"
        )
        params: list = [restricted_query]
        if type is not None:
            base_sql += " AND type = ?"
            params.append(type)
        fts_rows = conn.execute(base_sql + " ORDER BY rank LIMIT ?", params + [limit]).fetchall()

        if self._embedder is None:
            return [dict(r) for r in fts_rows]

        q_vec = self._embedder.embed_one(query)
        vec_rows = conn.execute("SELECT rowid, embedding FROM observations_vec").fetchall()

        scored: dict[int, float] = {}
        for rank, row in enumerate(fts_rows):
            scored[row["id"]] = scored.get(row["id"], 0.0) + 1.0 / (60 + rank)

        dim = len(q_vec)
        sem_scored = []
        for rowid, blob in vec_rows:
            vec = list(struct.unpack(f"{dim}f", blob))
            sem_scored.append((rowid, _cosine_similarity(q_vec, vec)))
        sem_scored.sort(key=lambda x: x[1], reverse=True)
        for rank, (rowid, _) in enumerate(sem_scored):
            scored[rowid] = scored.get(rowid, 0.0) + 1.0 / (60 + rank)

        top_ids = sorted(scored, key=scored.__getitem__, reverse=True)[:limit]
        if not top_ids:
            return []

        placeholders = ",".join("?" * len(top_ids))
        all_rows = conn.execute(
            f"SELECT rowid AS id, title, content, type, created_at "
            f"FROM observations WHERE rowid IN ({placeholders})",
            top_ids,
        ).fetchall()
        id_order = {id_: i for i, id_ in enumerate(top_ids)}
        return [dict(r) for r in sorted(all_rows, key=lambda r: id_order[r["id"]])]

    def session_end(self, summary: str) -> None:
        """Record a session-end observation with the given summary."""
        self.save("Session ended", summary, "session_end")
