"""Generates the compact repo map written to .codebase-context/repo_map.md."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from codebase_context.config import REPO_MAP_PATH
from codebase_context.parser import Symbol
from codebase_context.utils import count_tokens

logger = logging.getLogger(__name__)

_WARN_TOKENS  = 32_000
_MAX_TOKENS   = 32_000  # hard cap; files beyond this depth are omitted
_PRIORITY_DEPTH = 2     # files at depth <= this are always included


def generate_repo_map(project_root: str, symbols_by_file: dict[str, list[Symbol]]) -> str:
    """
    Generates the full repo map string.

    Format:
      # Repo Map
      # Generated: 2026-03-13T09:14:22  |  Files: 47  |  Symbols: 312
      # Reference this in CLAUDE.md with: @.codebase-context/repo_map.md

      ---

      ## src/api/auth.py
        class AuthRouter:
          + login(self, email: str, password: str) -> TokenResponse
          + register(self, email: str, password: str) -> User

      ## src/utils/validation.py
        + validate_email(email: str) -> str
    """
    total_files = len(symbols_by_file)
    total_symbols = sum(len(syms) for syms in symbols_by_file.values())
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    lines: list[str] = [
        "# Repo Map",
        f"# Generated: {now}  |  Files: {total_files}  |  Symbols: {total_symbols}",
        "# Reference this in CLAUDE.md with: @.codebase-context/repo_map.md",
        "",
        "---",
        "",
    ]

    # Sort: by directory depth first, then alphabetically
    sorted_files = sorted(
        symbols_by_file.keys(),
        key=lambda p: (len(Path(p).parts), p),
    )

    # Partition: priority files (shallow) always included; deep files added until budget
    priority = [f for f in sorted_files if len(Path(f).parts) <= _PRIORITY_DEPTH]
    deep     = [f for f in sorted_files if len(Path(f).parts) >  _PRIORITY_DEPTH]

    # Estimate tokens for the header already in `lines`
    budget_remaining = _MAX_TOKENS - count_tokens("\n".join(lines))

    # Build the file list to emit, greedily adding deep files within budget
    files_to_emit: list[str] = []
    for filepath in priority:
        files_to_emit.append(filepath)
    omitted = 0
    for filepath in deep:
        syms = symbols_by_file[filepath]
        estimated = count_tokens(filepath) + len(syms) * 6  # rough chars per symbol line
        if estimated <= budget_remaining:
            files_to_emit.append(filepath)
            budget_remaining -= estimated
        else:
            omitted += 1

    for filepath in files_to_emit:
        syms = symbols_by_file[filepath]
        if not syms:
            continue

        lines.append(f"## {filepath}")

        # Group: separate classes from their methods and standalone symbols
        classes: dict[str, list[Symbol]] = {}
        standalone: list[Symbol] = []

        for sym in syms:
            if sym.symbol_type == "class":
                if sym.name not in classes:
                    classes[sym.name] = []
            elif sym.symbol_type == "method" and sym.parent:
                classes.setdefault(sym.parent, []).append(sym)
            else:
                standalone.append(sym)

        # Emit classes
        for class_name, methods in classes.items():
            lines.append(f"  class {class_name}:")
            for method in methods:
                lines.append(f"    + {method.name}{_params_from_sig(method.signature)}")

        # Emit standalone (functions, interfaces, types)
        for sym in standalone:
            if sym.symbol_type in ("interface", "type"):
                lines.append(f"  {sym.symbol_type} {sym.name}")
            else:
                lines.append(f"  + {sym.name}{_params_from_sig(sym.signature)}")

        lines.append("")

    if omitted:
        lines.append(
            f"# [{omitted} file(s) omitted — over token budget. "
            "Run: ccindex map --full to see all.]"
        )

    result = "\n".join(lines)

    tokens = count_tokens(result)
    if tokens > _WARN_TOKENS:
        logger.warning(
            "Repo map is large (%d tokens). Consider excluding more files.", tokens
        )

    return result


def _params_from_sig(sig: str) -> str:
    """Extract the parameter/return portion from a signature."""
    paren = sig.find("(")
    if paren >= 0:
        return sig[paren:]
    return ""


def write_repo_map(project_root: str, repo_map: str) -> None:
    """Writes to REPO_MAP_PATH, creating .codebase-context/ dir if needed."""
    path = Path(project_root) / REPO_MAP_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(repo_map, encoding="utf-8")
    logger.info("Repo map written to %s", path)

