"""Full indexing pipeline orchestrator."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from codebase_context.chunker import build_chunks
from codebase_context.config import ALWAYS_IGNORE, LANGUAGES
from codebase_context.embedder import Embedder
from codebase_context.parser import parse_file
from codebase_context.repo_map import generate_repo_map, write_repo_map
from codebase_context.store import VectorStore
from codebase_context.utils import (
    find_project_root,
    is_ignored,
    load_gitignore,
    load_index_meta,
    save_index_meta,
)

logger = logging.getLogger(__name__)


@dataclass
class IndexMeta:
    """Persisted to INDEX_META_PATH as JSON. Tracks per-file mtimes."""
    last_full_index: str               # ISO timestamp
    file_mtimes:     dict[str, float]  # filepath -> mtime at last index
    total_chunks:    int
    total_files:     int


@dataclass
class IndexStats:
    files_indexed:    int
    chunks_created:   int
    duration_seconds: float


class Indexer:
    def __init__(self, project_root: str):
        self.root     = project_root
        self.store    = VectorStore(project_root)
        self.embedder = Embedder()
        self.meta     = load_index_meta(project_root)

    def full_index(self, show_progress: bool = True) -> IndexStats:
        """Indexes the entire project from scratch."""
        start = time.time()
        self.store.clear()

        files = discover_files(self.root)
        if not files:
            logger.warning("No indexable files found in %s", self.root)
            return IndexStats(0, 0, time.time() - start)

        iter_files = files
        if show_progress:
            try:
                from tqdm import tqdm
                iter_files = tqdm(files, desc="Indexing", unit="file")
            except ImportError:
                pass

        symbols_by_file: dict[str, list] = {}
        total_chunks = 0

        for filepath in iter_files:
            symbols = parse_file(filepath)
            if not symbols:
                continue
            symbols_by_file[filepath] = symbols

            rel_path = os.path.relpath(filepath, self.root)
            chunks = build_chunks(symbols, rel_path)
            if not chunks:
                continue

            embeddings = self.embedder.embed([c.text for c in chunks])
            self.store.upsert(chunks, embeddings)
            total_chunks += len(chunks)

        # Generate and write repo map
        rel_symbols = {
            os.path.relpath(fp, self.root): syms
            for fp, syms in symbols_by_file.items()
        }
        repo_map = generate_repo_map(self.root, rel_symbols)
        write_repo_map(self.root, repo_map)

        # Save metadata
        self.meta = IndexMeta(
            last_full_index=datetime.now(tz=timezone.utc).isoformat(),
            file_mtimes={f: os.path.getmtime(f) for f in files},
            total_chunks=total_chunks,
            total_files=len(symbols_by_file),
        )
        save_index_meta(self.root, self.meta)

        duration = time.time() - start
        return IndexStats(
            files_indexed=len(symbols_by_file),
            chunks_created=total_chunks,
            duration_seconds=duration,
        )

    def incremental_index(self, show_progress: bool = True) -> IndexStats:
        """Only re-indexes files whose mtime has changed since last index."""
        start = time.time()
        files = discover_files(self.root)

        changed = [
            f for f in files
            if self.meta.file_mtimes.get(f, 0) != os.path.getmtime(f)
        ]

        if not changed:
            return IndexStats(0, 0, time.time() - start)

        iter_changed = changed
        if show_progress:
            try:
                from tqdm import tqdm
                iter_changed = tqdm(changed, desc="Updating", unit="file")
            except ImportError:
                pass

        total_chunks = 0
        for filepath in iter_changed:
            rel_path = os.path.relpath(filepath, self.root)
            self.store.delete_by_filepath(rel_path)
            chunks_created = self.index_file(filepath)
            total_chunks += chunks_created
            self.meta.file_mtimes[filepath] = os.path.getmtime(filepath)

        # Regenerate repo map
        self._regenerate_repo_map(files)

        self.meta.total_chunks = self.store.count()
        self.meta.total_files = len(files)
        save_index_meta(self.root, self.meta)

        return IndexStats(
            files_indexed=len(changed),
            chunks_created=total_chunks,
            duration_seconds=time.time() - start,
        )

    def index_file(self, filepath: str) -> int:
        """Index a single file. Returns number of chunks created."""
        symbols = parse_file(filepath)
        if not symbols:
            return 0

        rel_path = os.path.relpath(filepath, self.root)
        chunks = build_chunks(symbols, rel_path)
        if not chunks:
            return 0

        embeddings = self.embedder.embed([c.text for c in chunks])
        self.store.upsert(chunks, embeddings)
        return len(chunks)

    def remove_file(self, filepath: str) -> None:
        """Called when a file is deleted."""
        rel_path = os.path.relpath(filepath, self.root)
        self.store.delete_by_filepath(rel_path)
        if filepath in self.meta.file_mtimes:
            del self.meta.file_mtimes[filepath]
        save_index_meta(self.root, self.meta)

    def _regenerate_repo_map(self, files: list[str]) -> None:
        """Rebuild repo map from all currently-indexed files."""
        symbols_by_file: dict[str, list] = {}
        for filepath in files:
            symbols = parse_file(filepath)
            if symbols:
                rel_path = os.path.relpath(filepath, self.root)
                symbols_by_file[rel_path] = symbols

        repo_map = generate_repo_map(self.root, symbols_by_file)
        write_repo_map(self.root, repo_map)


def discover_files(project_root: str) -> list[str]:
    """
    Returns all source files to index.
    Respects .gitignore, ALWAYS_IGNORE patterns, and LANGUAGES extensions.
    """
    gitignore = load_gitignore(project_root)
    supported_exts = set(LANGUAGES.keys())
    result: list[str] = []

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Prune ignored directories in-place (avoids walking into them)
        dirnames[:] = [
            d for d in dirnames
            if not is_ignored(os.path.join(dirpath, d), project_root, gitignore)
        ]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            ext = Path(filepath).suffix
            if ext not in supported_exts:
                continue
            if is_ignored(filepath, project_root, gitignore):
                continue
            result.append(filepath)

    return sorted(result)
