"""Per-thread SQLite connection manager for the memory layer."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_local = threading.local()


def get_connection(project_root: str, db_filename: str = "memory.db") -> sqlite3.Connection:
    """Return a per-thread SQLite connection for the given project root and db file.

    Each (project_root, db_filename) pair gets its own per-thread connection.
    WAL mode allows concurrent readers alongside a single writer.
    """
    key = f"conn\x00{project_root}\x00{db_filename}"
    if not hasattr(_local, key):
        path = Path(project_root) / ".codebase-context" / db_filename
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        setattr(_local, key, conn)
    return getattr(_local, key)
