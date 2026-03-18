"""ChromaDB wrapper for vector storage and retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.errors import ChromaError

from codebase_context.chunker import Chunk
from codebase_context.config import CHROMA_DIR, DEFAULT_TOP_K
from codebase_context.utils import slugify

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    chunk_text: str
    metadata:   dict
    score:      float


class VectorStore:
    """
    Wraps a ChromaDB PersistentClient stored at CHROMA_DIR.
    Collection name: slugified project root path (absolute).
    """

    def __init__(self, project_root: str):
        chroma_path = str(Path(project_root) / CHROMA_DIR)
        Path(chroma_path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=chroma_path)
        self._collection_name = slugify(str(Path(project_root).resolve()))
        self._collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        return self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Upserts chunks by their deterministic ID."""
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[c.metadata for c in chunks],
        )

    def delete_by_filepath(self, filepath: str) -> None:
        """Removes all chunks from a given file."""
        try:
            results = self._collection.get(where={"filepath": filepath})
            if results["ids"]:
                self._collection.delete(ids=results["ids"])
        except ChromaError as e:
            logger.warning("Error deleting chunks for %s: %s", filepath, e)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = DEFAULT_TOP_K,
        where: dict | None = None,
    ) -> list[SearchResult]:
        """
        Nearest-neighbor search. Returns SearchResult sorted by score desc.
        ChromaDB cosine distance is converted to similarity: score = 1.0 - distance
        """
        count = self.count()
        if count == 0:
            return []

        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, count),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = self._collection.query(**kwargs)
        except ChromaError as e:
            logger.error("Search error: %s", e)
            return []

        search_results: list[SearchResult] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            score = 1.0 - dist
            search_results.append(SearchResult(chunk_text=doc, metadata=meta, score=score))

        return sorted(search_results, key=lambda r: r.score, reverse=True)

    def get_by_symbol_name(self, name: str) -> list[SearchResult]:
        """Exact metadata filter: {"symbol_name": name}."""
        try:
            results = self._collection.get(
                where={"symbol_name": name},
                include=["documents", "metadatas"],
            )
        except ChromaError as e:
            logger.warning("get_by_symbol_name error: %s", e)
            return []

        return [
            SearchResult(chunk_text=doc, metadata=meta, score=1.0)
            for doc, meta in zip(results["documents"], results["metadatas"])
        ]

    def count(self) -> int:
        """Total number of chunks indexed."""
        return self._collection.count()

    def clear(self) -> None:
        """Deletes and recreates the collection."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._get_or_create_collection()
        logger.info("Collection %s cleared.", self._collection_name)
