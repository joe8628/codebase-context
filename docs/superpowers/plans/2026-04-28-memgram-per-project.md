# Memgram Per-Project Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make memgram (Layer 3) store data in `.codebase-context/memgram.db` per project, matching Layers 1 and 2.
**Stack:** Python, SQLite, Click, MCP

---

### Task 1: Remove `_db_path()` and wire `os.getcwd()` in `mcp_server.py`
Files: modify `codebase_context/memgram/mcp_server.py`, modify `tests/test_memgram_mcp.py`

- [ ] **Test** — update fixture in `tests/test_memgram_mcp.py` (pre-existing bug: fixture passes a file path, not a project root):
  ```py
  # change line 17 from:
  #   MemgramStore(str(tmp_path / "memgram.db"))
  # to:
  def store(tmp_path):
      return MemgramStore(str(tmp_path))
  ```
  Add assertion that `_db_path` no longer exists in the module:
  ```py
  def test_db_path_removed():
      import codebase_context.memgram.mcp_server as m
      assert not hasattr(m, "_db_path")
  ```
  Run `pytest tests/test_memgram_mcp.py` → FAIL (fixture still broken, `_db_path` still present)

- [ ] **Implement** — edit `codebase_context/memgram/mcp_server.py`:
  - Delete the `_db_path()` function (lines 17–20) and its `Path` import if no longer used
  - In `run_server()`, replace `store = MemgramStore(_db_path())` with:
  ```py
  project_root = os.getcwd()
  store = MemgramStore(project_root)
  ```
  Run `pytest tests/test_memgram_mcp.py` → PASS

- [ ] **Commit** — `refactor: resolve memgram db path from os.getcwd() per-project`

---

### Task 2: Remove `MEMGRAM_DATA_DIR` env injection from `cli.py` and update its test
Files: modify `codebase_context/cli.py`, modify `tests/test_cli.py`

- [ ] **Test** — update `tests/test_cli.py:170–181`. Rename and invert the assertion:
  ```py
  def test_memgram_mcp_entry_has_no_env(self, tmp_project):
      # run init, accept memgram prompt
      settings = tmp_project / ".claude" / "settings.json"
      data = json.loads(settings.read_text())
      entry = data["mcpServers"]["memgram"]
      assert "env" not in entry
  ```
  Run `pytest tests/test_cli.py` → FAIL (`env` key still present)

- [ ] **Implement** — edit `codebase_context/cli.py` around line 651:
  ```py
  # Remove these two lines:
  #   memgram_data_dir = str(Path(project_root) / ".claude")
  #   "env": {"MEMGRAM_DATA_DIR": memgram_data_dir},
  data.setdefault("mcpServers", {})[_MEMGRAM_KEY] = {
      "command": "ccindex",
      "args": ["mem-serve"],
  }
  ```
  Run `pytest tests/test_cli.py` → PASS

- [ ] **Commit** — `refactor: remove MEMGRAM_DATA_DIR env injection — mem-serve uses os.getcwd()`

---

### Task 3: Verify full test suite and confirm isolation
Files: read-only verification

- [ ] **Run all affected tests:**
  ```
  pytest tests/test_memgram_store.py tests/test_memgram_mcp.py tests/test_cli.py -v
  ```
  → All pass

- [ ] **Step 4 — Manual smoke check:**
  ```bash
  cd /tmp/project-a && mkdir -p . && ccindex mem-serve &
  # In a second terminal:
  cd /tmp/project-b && mkdir -p . && ccindex mem-serve &
  # Verify:
  ls /tmp/project-a/.codebase-context/memgram.db   # exists
  ls /tmp/project-b/.codebase-context/memgram.db   # exists, separate file
  ls ~/.memgram/                                     # does NOT exist (or is stale/old)
  ```

- [ ] **Commit** — `test: verify memgram per-project isolation`

---

## Scope Summary

| File | Change | Lines affected |
|---|---|---|
| `codebase_context/memgram/mcp_server.py` | Remove `_db_path()`, add `os.getcwd()` | ~4 deleted, ~2 added |
| `codebase_context/cli.py` | Remove `memgram_data_dir` var and `env` key | ~2 deleted |
| `tests/test_cli.py` | Update assertion: `env` key must NOT exist | ~3 changed |
| `tests/test_memgram_mcp.py` | Fix fixture path bug + add `_db_path` removal test | ~3 changed, ~3 added |

**Behavior before:** `ccindex mem-serve` stores all projects' memories in `~/.memgram/memgram.db` (or `$MEMGRAM_DATA_DIR`). All projects share one database.

**Behavior after:** `ccindex mem-serve` (run from a project directory) stores memories in `<project_root>/.codebase-context/memgram.db`. Each project is fully isolated.

---

## Spec Coverage

| Requirement | Task |
|---|---|
| `mem-serve` resolves `project_root = os.getcwd()` | Task 1 |
| `MemgramStore` instantiated with project root, not global path | Task 1 |
| Data lands at `.codebase-context/memgram.db` per project | Task 1 |
| `MEMGRAM_DATA_DIR` env var removed | Task 2 |
| All existing tests pass unchanged | Task 3 |
| Two project dirs produce two isolated databases | Task 3 (Step 4) |
