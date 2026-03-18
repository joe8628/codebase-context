"""Converts parsed Symbols into indexable Chunks for the vector store."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from codebase_context.config import MAX_CHUNK_TOKENS
from codebase_context.parser import Symbol
from codebase_context.utils import count_tokens


@dataclass
class Chunk:
    id:       str    # deterministic: sha256(filepath + symbol_name + start_line)
    text:     str    # context-enriched text to embed
    metadata: dict   # stored in ChromaDB alongside the vector


def chunk_id(filepath: str, symbol_name: str, start_line: int) -> str:
    """
    Deterministic ID. Same symbol at same location = same ID.
    sha256 of "filepath::symbol_name::start_line"
    """
    key = f"{filepath}::{symbol_name}::{start_line}"
    return hashlib.sha256(key.encode()).hexdigest()


def build_chunks(symbols: list[Symbol], filepath: str) -> list[Chunk]:
    """
    Converts symbols to chunks with context-enriched text prefix:

      # filepath: src/services/user_service.py
      # type: method | class: UserService
      def register(self, email: str, password: str) -> User:
          ...actual source...

    Chunks exceeding MAX_CHUNK_TOKENS are truncated at nearest line boundary.
    Full source is preserved in metadata regardless of truncation.
    """
    chunks: list[Chunk] = []

    for sym in symbols:
        prefix_lines = [f"# filepath: {filepath}"]
        type_line = f"# type: {sym.symbol_type}"
        if sym.parent:
            type_line += f" | class: {sym.parent}"
        prefix_lines.append(type_line)

        full_text = "\n".join(prefix_lines) + "\n" + sym.source
        text = _truncate_to_tokens(full_text, MAX_CHUNK_TOKENS)

        meta = {
            "filepath":     filepath,
            "symbol_name":  sym.name,
            "symbol_type":  sym.symbol_type,
            "start_line":   sym.start_line,
            "end_line":     sym.end_line,
            "language":     sym.language,
            "parent_class": sym.parent or "",
            "calls":        json.dumps(sym.calls),
            "docstring":    sym.docstring or "",
            "full_source":  sym.source,
            "signature":    sym.signature,
        }

        chunks.append(Chunk(
            id=chunk_id(filepath, sym.name, sym.start_line),
            text=text,
            metadata=meta,
        ))

    return chunks


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text at nearest logical line boundary to stay within max_tokens."""
    if count_tokens(text) <= max_tokens:
        return text

    budget = max_tokens * 4  # chars per token approximation
    char_count = 0
    result_lines: list[str] = []
    for line in text.split("\n"):
        char_count += len(line) + 1  # +1 for the newline
        if char_count > budget:
            break
        result_lines.append(line)
    return "\n".join(result_lines)
