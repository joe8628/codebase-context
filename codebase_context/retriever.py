"""Clean query interface used by the MCP server and CLI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from codebase_context.config import DEFAULT_TOP_K, REPO_MAP_PATH
from codebase_context.embedder import Embedder
from codebase_context.store import SearchResult, VectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    filepath:     str
    symbol_name:  str
    symbol_type:  str
    source:       str
    signature:    str
    score:        float
    language:     str
    parent_class: str | None
    start_line:   int
    end_line:     int


def _search_result_to_retrieval(sr: SearchResult) -> RetrievalResult:
    meta = sr.metadata
    return RetrievalResult(
        filepath=meta.get("filepath", ""),
        symbol_name=meta.get("symbol_name", ""),
        symbol_type=meta.get("symbol_type", "function"),
        source=meta.get("full_source", sr.chunk_text),
        signature=meta.get("signature", ""),
        score=sr.score,
        language=meta.get("language", ""),
        parent_class=meta.get("parent_class") or None,
        start_line=int(meta.get("start_line", 0)),
        end_line=int(meta.get("end_line", 0)),
    )


class Retriever:
    def __init__(self, project_root: str):
        self.store    = VectorStore(project_root)
        self.embedder = Embedder()

    def search(
        self,
        query:             str,
        top_k:             int = DEFAULT_TOP_K,
        language:          str | None = None,
        filepath_contains: str | None = None,
    ) -> list[RetrievalResult]:
        """
        Embeds query, searches store, returns ranked results.
        Optional filters: language, filepath_contains.
        Results are deduplicated by filepath+symbol_name.
        """
        query_vec = self.embedder.embed_one(query)

        where: dict | None = None
        if language:
            where = {"language": language}

        raw = self.store.search(query_vec, top_k=top_k * 2, where=where)
        results = [_search_result_to_retrieval(r) for r in raw]

        # Apply filepath filter
        if filepath_contains:
            results = [r for r in results if filepath_contains in r.filepath]

        # Deduplicate by filepath+symbol_name (keep highest score)
        seen: set[str] = set()
        deduped: list[RetrievalResult] = []
        for r in results:
            key = f"{r.filepath}::{r.symbol_name}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        return deduped[:top_k]

    def get_symbol(self, name: str) -> list[RetrievalResult]:
        """Exact symbol name lookup. Case-sensitive."""
        raw = self.store.get_by_symbol_name(name)
        return [_search_result_to_retrieval(r) for r in raw]

    def get_repo_map(self, project_root: str) -> str:
        """Reads and returns current repo_map.md content."""
        path = Path(project_root) / REPO_MAP_PATH
        if path.exists():
            return path.read_text(encoding="utf-8")
        return (
            "Index not found. Run: ccindex init\n"
            "(This will parse your codebase and generate the repo map.)"
        )
