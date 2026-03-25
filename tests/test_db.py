"""Unit tests for the db connection manager."""
from __future__ import annotations

import sqlite3
import threading

from codebase_context.db import get_connection


def test_returns_sqlite_connection(tmp_path):
    conn = get_connection(str(tmp_path))
    assert isinstance(conn, sqlite3.Connection)


def test_same_project_root_returns_same_connection(tmp_path):
    conn1 = get_connection(str(tmp_path))
    conn2 = get_connection(str(tmp_path))
    assert conn1 is conn2


def test_db_file_created_at_expected_path(tmp_path):
    get_connection(str(tmp_path))
    assert (tmp_path / ".codebase-context" / "memory.db").exists()


def test_wal_mode_enabled(tmp_path):
    conn = get_connection(str(tmp_path))
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"


def test_different_threads_get_different_connections(tmp_path):
    results: list = []

    def grab() -> None:
        results.append(get_connection(str(tmp_path)))

    t = threading.Thread(target=grab)
    t.start()
    t.join()

    main_conn = get_connection(str(tmp_path))
    assert results[0] is not main_conn
