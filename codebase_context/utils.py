"""Shared utilities: token counting, gitignore handling, path helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pathspec

from codebase_context.config import ALWAYS_IGNORE, INDEX_META_PATH


def count_tokens(text: str) -> int:
    """Approximate token count: word count × 1.3 (fast heuristic)."""
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


def slugify(text: str) -> str:
    """
    Converts an arbitrary string (e.g. absolute path) to a safe ChromaDB
    collection name: alphanumeric + hyphens, 3–63 chars.
    """
    slug = re.sub(r"[^a-zA-Z0-9]", "-", text)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if len(slug) > 63:
        hash_suffix = hashlib.sha256(text.encode()).hexdigest()[:8]
        slug = slug[:54] + "-" + hash_suffix
    if len(slug) < 3:
        slug = slug + "xxx"
    return slug.lower()


def load_gitignore(project_root: str) -> pathspec.PathSpec:
    """Parses .gitignore and returns a pathspec matcher."""
    gitignore_path = Path(project_root) / ".gitignore"
    if gitignore_path.exists():
        lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def is_ignored(filepath: str, project_root: str, gitignore: pathspec.PathSpec) -> bool:
    """Returns True if this file should be skipped during indexing."""
    try:
        rel = os.path.relpath(filepath, project_root)
    except ValueError:
        return True

    if gitignore.match_file(rel):
        return True

    parts = Path(rel).parts
    for pattern in ALWAYS_IGNORE:
        if "*" in pattern:
            import fnmatch
            if fnmatch.fnmatch(Path(filepath).name, pattern):
                return True
        else:
            if pattern in parts:
                return True

    return False


def find_project_root(start_path: str = ".") -> str:
    """
    Walks up from start_path looking for a .git directory.
    Falls back to start_path if no .git found.
    """
    current = Path(start_path).resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return str(parent)
    return str(current)


def load_index_meta(project_root: str):
    """Loads INDEX_META_PATH or returns an empty IndexMeta if not found."""
    from codebase_context.indexer import IndexMeta  # local import to avoid circular dep

    meta_path = Path(project_root) / INDEX_META_PATH
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return IndexMeta(**data)
    return IndexMeta(
        last_full_index="",
        file_mtimes={},
        total_chunks=0,
        total_files=0,
    )


def save_index_meta(project_root: str, meta) -> None:
    """Persists IndexMeta to INDEX_META_PATH."""
    meta_path = Path(project_root) / INDEX_META_PATH
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "last_full_index": meta.last_full_index,
                "file_mtimes":     meta.file_mtimes,
                "total_chunks":    meta.total_chunks,
                "total_files":     meta.total_files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def format_results_for_agent(results: list) -> str:
    """
    Formats retrieval results as clean markdown for MCP tool responses.
    Groups by filepath.
    """
    if not results:
        return "_No results found._"

    from collections import defaultdict
    by_file: dict[str, list] = defaultdict(list)
    for r in results:
        by_file[r.filepath].append(r)

    lines: list[str] = []
    for filepath, file_results in sorted(by_file.items()):
        lines.append(f"## {filepath}")
        for r in file_results:
            header = f"### `{r.symbol_name}`"
            if r.parent_class:
                header += f" (in `{r.parent_class}`)"
            lines.append(header)
            lines.append(f"- **Type:** {r.symbol_type}")
            lines.append(f"- **Lines:** {r.start_line + 1}–{r.end_line + 1}")
            lines.append(f"- **Score:** {r.score:.3f}")
            lines.append(f"- **Signature:** `{r.signature}`")
            lines.append("")
            lines.append("```")
            lines.append(r.source)
            lines.append("```")
            lines.append("")
    return "\n".join(lines)
