# Airgapped Models Auto-Detect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-detect a `models/` folder in the project root as a fallback embedding model source when `CC_MODELS_DIR` is not set, enabling airgapped Docker environments to work without any env var configuration.

**Architecture:** Extract a new `_resolve_models_dir()` method on `Embedder` that checks `CC_MODELS_DIR` first, then falls back to `<project_root>/models` (discovered via `find_project_root()`). Wire it into the existing `_get_model()` in place of the direct `os.environ.get("CC_MODELS_DIR")` call. No other files need changing.

**Tech Stack:** Python, fastembed, pytest, monkeypatch

---

## Files

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `codebase_context/embedder.py` | Add `_resolve_models_dir()`, update `_get_model()` |
| Create | `tests/test_embedder.py` | Unit tests for `_resolve_models_dir()` |

---

### Task 1: Write failing tests for `_resolve_models_dir`

**Files:**
- Create: `tests/test_embedder.py`

- [ ] **Step 1: Create the test file with three failing tests**

```python
# tests/test_embedder.py
"""Tests for Embedder._resolve_models_dir."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from codebase_context.embedder import Embedder


def test_resolve_models_dir_uses_env_var(monkeypatch):
    """CC_MODELS_DIR takes precedence over auto-detection."""
    monkeypatch.setenv("CC_MODELS_DIR", "/explicit/path")
    embedder = Embedder()
    assert embedder._resolve_models_dir() == "/explicit/path"


def test_resolve_models_dir_autodetects_project_models(tmp_path, monkeypatch):
    """Returns <project_root>/models when it exists and CC_MODELS_DIR is unset."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "models").mkdir()
    monkeypatch.delenv("CC_MODELS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    embedder = Embedder()
    assert embedder._resolve_models_dir() == str(tmp_path / "models")


def test_resolve_models_dir_returns_empty_when_no_models_folder(tmp_path, monkeypatch):
    """Returns empty string when CC_MODELS_DIR is unset and no models/ folder exists."""
    (tmp_path / ".git").mkdir()
    monkeypatch.delenv("CC_MODELS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    embedder = Embedder()
    assert embedder._resolve_models_dir() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /workspace && python -m pytest tests/test_embedder.py -v
```

Expected: `AttributeError: 'Embedder' object has no attribute '_resolve_models_dir'`

---

### Task 2: Implement `_resolve_models_dir` and wire into `_get_model`

**Files:**
- Modify: `codebase_context/embedder.py`

- [ ] **Step 1: Add the import for `find_project_root` at the top of `embedder.py`**

In `codebase_context/embedder.py`, after the existing imports (around line 12), add:

```python
from codebase_context.utils import find_project_root
```

So the import block reads:

```python
from codebase_context.config import EMBED_BATCH_SIZE, EMBED_MODEL
from codebase_context.utils import find_project_root
```

- [ ] **Step 2: Add `_resolve_models_dir` method to `Embedder`**

Insert this method directly before `_get_model` (currently at line 102):

```python
def _resolve_models_dir(self) -> str:
    """Return the models directory to use for local seeding.

    Resolution order:
    1. ``CC_MODELS_DIR`` environment variable (explicit override).
    2. ``models/`` folder inside the project root (auto-detected via
       the nearest ``.git`` directory from the current working directory).
    3. Empty string — no local seeding, fastembed will attempt a download.
    """
    models_dir = os.environ.get("CC_MODELS_DIR", "")
    if models_dir:
        return models_dir
    try:
        project_root = find_project_root()
        candidate = Path(project_root) / "models"
        if candidate.is_dir():
            return str(candidate)
    except Exception:
        pass
    return ""
```

- [ ] **Step 3: Replace the direct env-var read in `_get_model` with `_resolve_models_dir()`**

In `_get_model`, replace the two lines:

```python
                    cache_dir = os.path.expanduser("~/.cache/fastembed")
                    models_dir = os.environ.get("CC_MODELS_DIR", "")
```

with:

```python
                    cache_dir = os.path.expanduser("~/.cache/fastembed")
                    models_dir = self._resolve_models_dir()
```

The rest of `_get_model` is unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /workspace && python -m pytest tests/test_embedder.py -v
```

Expected output:
```
tests/test_embedder.py::test_resolve_models_dir_uses_env_var PASSED
tests/test_embedder.py::test_resolve_models_dir_autodetects_project_models PASSED
tests/test_embedder.py::test_resolve_models_dir_returns_empty_when_no_models_folder PASSED

3 passed
```

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
cd /workspace && python -m pytest --tb=short -q
```

Expected: all existing tests still pass; total failures = 0.

- [ ] **Step 6: Commit**

```bash
cd /workspace && git add codebase_context/embedder.py tests/test_embedder.py
git commit -m "feat: auto-detect models/ in project root as airgapped fallback"
```
