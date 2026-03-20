from __future__ import annotations

from pathlib import Path

_EXCLUDED_SEGMENTS = frozenset({"node_modules", ".venv", "venv", "env", "__pycache__"})


def is_project_file(path: str, project_root: str) -> bool:
    """Return True if path is inside project_root and not in an excluded directory."""
    try:
        rel = Path(path).resolve().relative_to(Path(project_root).resolve())
    except ValueError:
        return False
    return not any(part in _EXCLUDED_SEGMENTS for part in rel.parts)
