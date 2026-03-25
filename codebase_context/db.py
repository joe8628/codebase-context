"""Per-thread SQLite connection manager for the memory layer."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

DB_PATH = ".codebase-context/memory.db"
_local = threading.local()


def get_connection(project_root: str) -> sqlite3.Connection:
    """Return a per-thread SQLite connection for the given project root.

    Uses threading.local() so each thread gets its own connection — the correct
    pattern for sqlite3 under concurrent MCP tool calls. WAL mode allows concurrent
    readers alongside a single writer.
    """
    key = f"conn_{project_root}"
    if not hasattr(_local, key):
        path = Path(project_root) / DB_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        setattr(_local, key, conn)
    return getattr(_local, key)
