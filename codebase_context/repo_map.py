"""Generates the compact repo map written to .codebase-context/repo_map.md."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from codebase_context.config import REPO_MAP_PATH
from codebase_context.parser import Symbol

logger = logging.getLogger(__name__)

_WARN_TOKENS = 8_000


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

    for filepath in sorted_files:
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

    result = "\n".join(lines)

    tokens = estimate_tokens(result)
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


def estimate_tokens(text: str) -> int:
    """Rough token estimate: len(text) / 4."""
    return len(text) // 4
