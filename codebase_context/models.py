"""Shared data models with no internal dependencies."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IndexMeta:
    """Persisted to INDEX_META_PATH as JSON. Tracks per-file mtimes."""
    last_full_index: str               # ISO timestamp
    file_mtimes:     dict[str, float]  # rel_path -> mtime at last index
    total_chunks:    int
    total_files:     int


@dataclass
class IndexStats:
    files_indexed:    int
    chunks_created:   int
    duration_seconds: float
