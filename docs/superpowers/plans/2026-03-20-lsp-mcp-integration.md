# LSP MCP Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LSP-backed code navigation tools (find_definition, find_references, get_signature, get_call_hierarchy, warm_file) to the existing `ccindex serve` MCP server as a new `codebase_context/lsp/` subpackage.

**Architecture:** A lazy `LspRouter` holds one `LspClient` per language (pyright, ts-server, clangd), creating each subprocess only on first use. Five handler functions translate MCP tool arguments into LSP JSON-RPC calls and shape responses. The five new tools are wired into the existing `mcp_server.py` alongside the three existing tools — one process, one MCP server entry in `.claude/settings.json`. The `ccindex init` command gains a binary-detection step that offers to `npm install -g` the two npm-based servers and prints manual instructions for clangd.

**Tech Stack:** Python stdlib only (subprocess, threading, queue, json, pathlib, shutil) — no new pip dependencies. External binaries: `pyright-langserver` (npm), `typescript-language-server` (npm), `clangd` (apt/brew).

---

## Scope

This plan covers the `codebase-context` repo only. Changes to `payload-repo` (template updates) are handled by a separate prompt document at `docs/superpowers/plans/payload-repo-lsp-prompt.md`.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `codebase_context/lsp/__init__.py` | Empty package marker |
| Create | `codebase_context/lsp/filters.py` | Path exclusion: outside root, node_modules, .venv, __pycache__ |
| Create | `codebase_context/lsp/positions.py` | offset ↔ LSP position conversion (UTF-16 aware) |
| Create | `codebase_context/lsp/client.py` | LspClient: subprocess lifecycle, Content-Length framing, request/notify |
| Create | `codebase_context/lsp/router.py` | Ext → language map, lazy LspClient cache, UnsupportedExtensionError, ServerUnavailableError |
| Create | `codebase_context/lsp/handlers.py` | One function per MCP tool; calls router and client; shapes response |
| Modify | `codebase_context/mcp_server.py` | Add 5 tools to list_tools(); add dispatch in call_tool(); init LspRouter at startup |
| Modify | `codebase_context/cli.py` | Add `_setup_lsp_binaries()` called at end of `init` command |
| Create | `tests/test_lsp_filters.py` | Unit tests for filters.py |
| Create | `tests/test_lsp_positions.py` | Unit tests for positions.py |
| Create | `tests/test_lsp_client.py` | Unit tests for LspClient with FakeProc subprocess mock |
| Create | `tests/test_lsp_router.py` | Unit tests for LspRouter routing, caching, error cases |
| Create | `tests/test_lsp_handlers.py` | Unit tests for all 5 handlers with mock router |
| Create | `tests/test_cli_lsp.py` | Unit tests for _setup_lsp_binaries() via CliRunner |

---

## Task 1: `filters.py` — Path exclusion logic

**Files:**
- Create: `codebase_context/lsp/__init__.py`
- Create: `codebase_context/lsp/filters.py`
- Create: `tests/test_lsp_filters.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lsp_filters.py
from codebase_context.lsp.filters import is_project_file


def test_file_inside_project_is_included(tmp_path):
    f = tmp_path / "src" / "main.py"
    assert is_project_file(str(f), str(tmp_path)) is True


def test_file_outside_project_is_excluded(tmp_path):
    other = tmp_path.parent / "other" / "file.py"
    assert is_project_file(str(other), str(tmp_path)) is False


def test_node_modules_excluded(tmp_path):
    f = tmp_path / "node_modules" / "pkg" / "index.js"
    assert is_project_file(str(f), str(tmp_path)) is False


def test_venv_excluded(tmp_path):
    f = tmp_path / ".venv" / "lib" / "site.py"
    assert is_project_file(str(f), str(tmp_path)) is False


def test_pycache_excluded(tmp_path):
    f = tmp_path / "src" / "__pycache__" / "mod.pyc"
    assert is_project_file(str(f), str(tmp_path)) is False


def test_nested_src_is_included(tmp_path):
    f = tmp_path / "src" / "api" / "auth.py"
    assert is_project_file(str(f), str(tmp_path)) is True


def test_venv_without_dot_excluded(tmp_path):
    f = tmp_path / "venv" / "bin" / "python"
    assert is_project_file(str(f), str(tmp_path)) is False
```

- [ ] **Step 2: Run tests — expect ImportError (module doesn't exist yet)**

```bash
pytest tests/test_lsp_filters.py -v
```
Expected: `ModuleNotFoundError: No module named 'codebase_context.lsp'`

- [ ] **Step 3: Create the package and implement filters**

```python
# codebase_context/lsp/__init__.py
# (empty)
```

```python
# codebase_context/lsp/filters.py
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
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_lsp_filters.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add codebase_context/lsp/__init__.py codebase_context/lsp/filters.py tests/test_lsp_filters.py
git commit -m "feat: add lsp subpackage with path filter"
```

---

## Task 2: `positions.py` — UTF-16 position conversion

LSP uses UTF-16 code units for character positions. Characters above U+FFFF (e.g. emoji) consume 2 code units. pyright and clangd both follow the spec strictly.

**Files:**
- Create: `codebase_context/lsp/positions.py`
- Create: `tests/test_lsp_positions.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lsp_positions.py
from codebase_context.lsp.positions import offset_to_position, position_to_offset


def test_offset_to_position_first_line():
    src = "hello world"
    assert offset_to_position(src, 5) == {"line": 0, "character": 5}


def test_offset_to_position_second_line():
    src = "line1\nline2"
    assert offset_to_position(src, 6) == {"line": 1, "character": 0}


def test_offset_to_position_end_of_first_line():
    src = "abc\ndef"
    assert offset_to_position(src, 3) == {"line": 0, "character": 3}


def test_position_to_offset_first_line():
    src = "hello world"
    assert position_to_offset(src, 0, 5) == 5


def test_position_to_offset_second_line():
    src = "line1\nline2"
    assert position_to_offset(src, 1, 0) == 6


def test_roundtrip(tmp_path):
    src = "foo\nbar\nbaz"
    for offset in [0, 1, 4, 5, 8]:
        pos = offset_to_position(src, offset)
        assert position_to_offset(src, pos["line"], pos["character"]) == offset


def test_multibyte_emoji_counts_as_two_utf16_units():
    # U+1F600 is above U+FFFF → 2 UTF-16 code units
    # string: "x" + emoji + "y"  (3 Python chars, 4 UTF-16 code units)
    src = "x\U0001F600y"
    pos = offset_to_position(src, 2)  # position of "y"
    assert pos == {"line": 0, "character": 3}  # x=1, emoji=2 → y at character 3


def test_position_past_end_of_line(tmp_path):
    src = "abc"
    # character beyond line end → clamp to end of line
    result = position_to_offset(src, 0, 100)
    assert result == 3
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
pytest tests/test_lsp_positions.py -v
```
Expected: `ModuleNotFoundError: No module named 'codebase_context.lsp.positions'`

- [ ] **Step 3: Implement positions.py**

```python
# codebase_context/lsp/positions.py
from __future__ import annotations


def _utf16_len(char: str) -> int:
    """Return UTF-16 code unit count for a single Python character."""
    return 2 if ord(char) > 0xFFFF else 1


def offset_to_position(source: str, offset: int) -> dict[str, int]:
    """Convert a byte offset into an LSP {line, character} position.

    LSP character counts are UTF-16 code units, not Python character counts.
    """
    before = source[:offset]
    lines = before.split("\n")
    line = len(lines) - 1
    last_line = lines[-1]
    character = sum(_utf16_len(c) for c in last_line)
    return {"line": line, "character": character}


def position_to_offset(source: str, line: int, character: int) -> int:
    """Convert an LSP {line, character} position to a source byte offset.

    character is measured in UTF-16 code units.
    """
    lines = source.split("\n")
    if line >= len(lines):
        return len(source)
    base = sum(len(lines[i]) + 1 for i in range(line))  # +1 for \n
    target_line = lines[line]
    cu = 0
    for i, c in enumerate(target_line):
        if cu >= character:
            return base + i
        cu += _utf16_len(c)
    return base + len(target_line)
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_lsp_positions.py -v
```
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add codebase_context/lsp/positions.py tests/test_lsp_positions.py
git commit -m "feat: add lsp position conversion utilities (UTF-16 aware)"
```

---

## Task 3: `client.py` — LspClient subprocess + JSON-RPC

The client owns the LSP subprocess lifecycle. A background reader thread pulls responses off stdout and routes them to per-request queues. The main thread sends requests and blocks on its queue with a timeout.

**Files:**
- Create: `codebase_context/lsp/client.py`
- Create: `tests/test_lsp_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lsp_client.py
import json
import pytest
from unittest.mock import MagicMock, patch

from codebase_context.lsp.client import LspClient


# ── Helpers ──────────────────────────────────────────────────────────────────

def _frame(req_id: int, result: object) -> bytes:
    """Build a valid LSP Content-Length framed response."""
    body = json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


class _FakeStdout:
    """Simulates a process stdout that returns pre-loaded bytes."""

    def __init__(self, data: bytes) -> None:
        self._buf = data

    def read(self, n: int) -> bytes:
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk


class _FakeProc:
    def __init__(self, responses: list[bytes]) -> None:
        self.stdout = _FakeStdout(b"".join(responses))
        self.stdin = MagicMock()
        self.stdin.write = lambda data: None
        self.stdin.flush = lambda: None

    def terminate(self) -> None: ...
    def wait(self, timeout=None) -> None: ...


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_request_returns_result():
    init_result = {"capabilities": {}, "serverInfo": {"name": "test"}}
    test_result = {"file": "foo.py", "line": 10}
    proc = _FakeProc([_frame(1, init_result), _frame(2, test_result)])

    with patch("subprocess.Popen", return_value=proc):
        client = LspClient(["fake-lsp"], "file:///project")
        result = client.request("textDocument/definition", {})

    assert result == test_result


def test_open_file_sends_did_open_notification():
    proc = _FakeProc([_frame(1, {"capabilities": {}})])
    sent: list[bytes] = []
    proc.stdin.write = lambda data: sent.append(data)

    with patch("subprocess.Popen", return_value=proc):
        client = LspClient(["fake-lsp"], "file:///project")
        client.open_file("/project/main.py", "x = 1", "python")

    all_sent = b"".join(sent)
    assert b"textDocument/didOpen" in all_sent
    assert b"main.py" in all_sent


def test_open_file_skips_duplicate():
    proc = _FakeProc([_frame(1, {"capabilities": {}})])
    sent: list[bytes] = []
    proc.stdin.write = lambda data: sent.append(data)

    with patch("subprocess.Popen", return_value=proc):
        client = LspClient(["fake-lsp"], "file:///project")
        client.open_file("/project/main.py", "x = 1", "python")
        n_after_first = len(sent)
        client.open_file("/project/main.py", "x = 2", "python")  # second call must be skipped

    assert len(sent) == n_after_first


def test_request_timeout_raises():
    # Only provide the initialize response; our request never gets a reply
    proc = _FakeProc([_frame(1, {"capabilities": {}})])

    with patch("subprocess.Popen", return_value=proc):
        client = LspClient(["fake-lsp"], "file:///project")
        with pytest.raises(TimeoutError):
            client.request("textDocument/definition", {}, timeout=0.05)


def test_notify_does_not_add_id():
    proc = _FakeProc([_frame(1, {"capabilities": {}})])
    sent: list[bytes] = []
    proc.stdin.write = lambda data: sent.append(data)

    with patch("subprocess.Popen", return_value=proc):
        client = LspClient(["fake-lsp"], "file:///project")
        client.notify("textDocument/didSave", {"textDocument": {"uri": "file:///x.py"}})

    # Find the didSave message (skip Content-Length header bytes)
    all_sent = b"".join(sent)
    # Extract JSON bodies from the framed messages
    bodies = []
    buf = all_sent
    while b"Content-Length:" in buf:
        _, rest = buf.split(b"\r\n\r\n", 1)
        length_line = buf.split(b"Content-Length: ")[1].split(b"\r\n")[0]
        length = int(length_line)
        bodies.append(json.loads(rest[:length]))
        buf = rest[length:]

    save_msg = next(m for m in bodies if m.get("method") == "textDocument/didSave")
    assert "id" not in save_msg
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
pytest tests/test_lsp_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'codebase_context.lsp.client'`

- [ ] **Step 3: Implement client.py**

```python
# codebase_context/lsp/client.py
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any


class LspClient:
    """Manages one LSP server subprocess.

    Spawns the binary, performs the initialize handshake, and exposes
    request() / notify() / open_file() for tool handlers to use.
    A background reader thread drains stdout and routes responses to
    per-request queues.
    """

    def __init__(self, cmd: list[str], root_uri: str) -> None:
        self._root_uri = root_uri
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._lock = threading.Lock()
        self._pending: dict[int, queue.Queue[Any]] = {}
        self._id_counter = 0
        self._running = True
        self._opened_uris: set[str] = set()

        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

        self._initialize()

    # ── Public API ────────────────────────────────────────────────────────────

    def open_file(self, path: str, source: str, language_id: str) -> None:
        """Send textDocument/didOpen unless already sent for this URI."""
        uri = f"file://{path}"
        if uri in self._opened_uris:
            return
        self._opened_uris.add(uri)
        self.notify("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": 1,
                "text": source,
            }
        })

    def open_file_lazy(self, path: str) -> None:
        """Open a file by reading it from disk. Infers language from extension."""
        _EXT_TO_LANG = {
            ".py": "python",
            ".ts": "typescript", ".tsx": "typescriptreact",
            ".js": "javascript", ".jsx": "javascriptreact",
            ".c": "c", ".cpp": "cpp", ".h": "c",
        }
        ext = Path(path).suffix
        lang = _EXT_TO_LANG.get(ext, "plaintext")
        try:
            source = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            source = ""
        self.open_file(path, source, lang)

    def request(self, method: str, params: dict, timeout: float = 5.0) -> Any:
        """Send a JSON-RPC request and block until the response arrives."""
        req_id = self._next_id()
        q: queue.Queue[Any] = queue.Queue(maxsize=1)
        self._pending[req_id] = q
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"LSP request '{method}' timed out after {timeout}s")
        finally:
            self._pending.pop(req_id, None)

    def notify(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def shutdown(self) -> None:
        """Gracefully shut down the LSP server and terminate the subprocess."""
        self._running = False
        try:
            self.request("shutdown", {}, timeout=2.0)
            self.notify("exit", {})
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=2.0)
        except Exception:
            pass

    # ── Internal ──────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        with self._lock:
            self._id_counter += 1
            return self._id_counter

    def _send(self, msg: dict) -> None:
        body = json.dumps(msg).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        assert self._proc.stdin is not None
        self._proc.stdin.write(header + body)
        self._proc.stdin.flush()

    def _reader(self) -> None:
        """Background thread: parse Content-Length frames and route to pending queues."""
        assert self._proc.stdout is not None
        while self._running:
            try:
                header = b""
                while not header.endswith(b"\r\n\r\n"):
                    ch = self._proc.stdout.read(1)
                    if not ch:
                        return
                    header += ch
                length = int(header.split(b"Content-Length: ")[1].split(b"\r\n")[0])
                body = self._proc.stdout.read(length)
                msg = json.loads(body)
                req_id = msg.get("id")
                if req_id is not None and req_id in self._pending:
                    self._pending[req_id].put(msg.get("result"))
            except Exception:
                if self._running:
                    continue
                return

    def _initialize(self) -> None:
        self.request("initialize", {
            "processId": os.getpid(),
            "rootUri": self._root_uri,
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                    "callHierarchy": {"dynamicRegistration": False},
                }
            },
            "workspaceFolders": [{"uri": self._root_uri, "name": "root"}],
        })
        self.notify("initialized", {})
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_lsp_client.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add codebase_context/lsp/client.py tests/test_lsp_client.py
git commit -m "feat: add LspClient with subprocess lifecycle and JSON-RPC framing"
```

---

## Task 4: `router.py` — Extension routing and lazy client cache

**Files:**
- Create: `codebase_context/lsp/router.py`
- Create: `tests/test_lsp_router.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lsp_router.py
import pytest
from unittest.mock import MagicMock, patch

from codebase_context.lsp.router import (
    LspRouter,
    UnsupportedExtensionError,
    ServerUnavailableError,
)


def test_unsupported_extension_raises():
    router = LspRouter("/project")
    with pytest.raises(UnsupportedExtensionError) as exc:
        router.get_client(".rb")
    assert exc.value.ext == ".rb"


def test_binary_not_found_raises():
    router = LspRouter("/project")
    with patch("shutil.which", return_value=None):
        with pytest.raises(ServerUnavailableError) as exc:
            router.get_client(".py")
    assert "pyright-langserver" in exc.value.binary


def test_get_client_creates_and_caches():
    mock_client = MagicMock()
    router = LspRouter("/project")
    with patch("shutil.which", return_value="/usr/bin/pyright-langserver"), \
         patch("codebase_context.lsp.router.LspClient", return_value=mock_client):
        c1 = router.get_client(".py")
        c2 = router.get_client(".py")
    assert c1 is c2


def test_ts_extensions_share_one_client():
    mock_client = MagicMock()
    router = LspRouter("/project")
    with patch("shutil.which", return_value="/usr/bin/ts-server"), \
         patch("codebase_context.lsp.router.LspClient", return_value=mock_client):
        c_ts  = router.get_client(".ts")
        c_tsx = router.get_client(".tsx")
        c_js  = router.get_client(".js")
        c_jsx = router.get_client(".jsx")
    assert c_ts is c_tsx is c_js is c_jsx


def test_server_name_for_known_extensions():
    router = LspRouter("/project")
    assert router.server_name_for_ext(".py")  == "pyright"
    assert router.server_name_for_ext(".ts")  == "ts-server"
    assert router.server_name_for_ext(".tsx") == "ts-server"
    assert router.server_name_for_ext(".cpp") == "clangd"
    assert router.server_name_for_ext(".h")   == "clangd"


def test_server_name_for_unknown_extension():
    router = LspRouter("/project")
    assert router.server_name_for_ext(".rb") == "unknown"


def test_shutdown_closes_all_clients():
    mock_py = MagicMock()
    mock_ts = MagicMock()
    router = LspRouter("/project")
    router._clients = {"python": mock_py, "typescript": mock_ts}
    router.shutdown()
    mock_py.shutdown.assert_called_once()
    mock_ts.shutdown.assert_called_once()
    assert router._clients == {}


def test_custom_cmds_override_defaults():
    mock_client = MagicMock()
    router = LspRouter("/project", cmds={"python": ["my-pyright", "--stdio"]})
    with patch("shutil.which", return_value="/usr/local/bin/my-pyright"), \
         patch("codebase_context.lsp.router.LspClient", return_value=mock_client) as MockClient:
        router.get_client(".py")
    MockClient.assert_called_once_with(["my-pyright", "--stdio"], "file:///project")
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
pytest tests/test_lsp_router.py -v
```
Expected: `ModuleNotFoundError: No module named 'codebase_context.lsp.router'`

- [ ] **Step 3: Implement router.py**

```python
# codebase_context/lsp/router.py
from __future__ import annotations

import shutil

from codebase_context.lsp.client import LspClient

_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "typescript", ".jsx": "typescript",
    ".c": "c", ".cpp": "c", ".h": "c",
}

_LANG_TO_SERVER_NAME: dict[str, str] = {
    "python":     "pyright",
    "typescript": "ts-server",
    "c":          "clangd",
}

_DEFAULT_CMDS: dict[str, list[str]] = {
    "python":     ["pyright-langserver", "--stdio"],
    "typescript": ["typescript-language-server", "--stdio"],
    "c":          ["clangd"],
}


class UnsupportedExtensionError(Exception):
    def __init__(self, ext: str) -> None:
        self.ext = ext
        super().__init__(f"No LSP server configured for extension '{ext}'")


class ServerUnavailableError(Exception):
    def __init__(self, lang: str, binary: str) -> None:
        self.lang = lang
        self.binary = binary
        super().__init__(f"LSP binary '{binary}' not found for language '{lang}'")


class LspRouter:
    """Maps file extensions to LspClient instances, creating them lazily."""

    def __init__(
        self,
        project_root: str,
        cmds: dict[str, list[str]] | None = None,
    ) -> None:
        self._project_root = project_root
        self._cmds = cmds or _DEFAULT_CMDS
        self._clients: dict[str, LspClient] = {}

    def get_client(self, ext: str) -> LspClient:
        """Return the LspClient for this file extension, starting it if needed."""
        lang = _EXT_TO_LANG.get(ext)
        if lang is None:
            raise UnsupportedExtensionError(ext)
        if lang not in self._clients:
            cmd = self._cmds.get(lang, [])
            if not cmd or not shutil.which(cmd[0]):
                binary = cmd[0] if cmd else "(none)"
                raise ServerUnavailableError(lang, binary)
            self._clients[lang] = LspClient(cmd, f"file://{self._project_root}")
        return self._clients[lang]

    def server_name_for_ext(self, ext: str) -> str:
        lang = _EXT_TO_LANG.get(ext, "unknown")
        return _LANG_TO_SERVER_NAME.get(lang, "unknown")

    def shutdown(self) -> None:
        for client in self._clients.values():
            client.shutdown()
        self._clients.clear()
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_lsp_router.py -v
```
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add codebase_context/lsp/router.py tests/test_lsp_router.py
git commit -m "feat: add LspRouter with lazy client cache and extension routing"
```

---

## Task 5: `handlers.py` — MCP tool handler functions

**Files:**
- Create: `codebase_context/lsp/handlers.py`
- Create: `tests/test_lsp_handlers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lsp_handlers.py
import pytest
from unittest.mock import MagicMock

from codebase_context.lsp.handlers import (
    handle_find_definition,
    handle_find_references,
    handle_get_signature,
    handle_get_call_hierarchy,
    handle_warm_file,
)
from codebase_context.lsp.router import UnsupportedExtensionError, ServerUnavailableError


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_router(client=None, *, raises=None):
    router = MagicMock()
    if raises:
        router.get_client.side_effect = raises
    else:
        router.get_client.return_value = client or MagicMock()
    router.server_name_for_ext.return_value = "pyright"
    return router


def _loc(path: str, line: int) -> dict:
    return {"uri": f"file://{path}", "range": {"start": {"line": line, "character": 0}}}


# ── find_definition ───────────────────────────────────────────────────────────

def test_find_definition_returns_location(tmp_path):
    target = tmp_path / "other.py"
    target.write_text("def charge_card(): pass\n")
    client = MagicMock()
    client.request.return_value = [_loc(str(target), 0)]
    result = handle_find_definition(
        _make_router(client),
        {"file": str(tmp_path / "main.py"), "line": 5, "character": 10},
        str(tmp_path),
    )
    assert result["file"] == str(target)
    assert result["line"] == 0
    assert result["preview"] == "def charge_card(): pass"


def test_find_definition_filters_stdlib(tmp_path):
    client = MagicMock()
    client.request.return_value = [_loc("/usr/lib/python3/site.py", 0)]
    result = handle_find_definition(
        _make_router(client),
        {"file": str(tmp_path / "x.py"), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result is None


def test_find_definition_null_result(tmp_path):
    client = MagicMock()
    client.request.return_value = None
    result = handle_find_definition(
        _make_router(client),
        {"file": str(tmp_path / "x.py"), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result is None


def test_find_definition_unsupported_extension(tmp_path):
    result = handle_find_definition(
        _make_router(raises=UnsupportedExtensionError(".rb")),
        {"file": str(tmp_path / "x.rb"), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result["error"] == "unsupported_extension"
    assert result["ext"] == ".rb"


def test_find_definition_server_unavailable(tmp_path):
    result = handle_find_definition(
        _make_router(raises=ServerUnavailableError("python", "pyright-langserver")),
        {"file": str(tmp_path / "x.py"), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result["error"] == "server_unavailable"


# ── find_references ───────────────────────────────────────────────────────────

def test_find_references_returns_capped_list(tmp_path):
    src = tmp_path / "a.py"
    src.write_text("\n" * 30)
    locs = [_loc(str(src), i) for i in range(25)]
    client = MagicMock()
    client.request.return_value = locs
    result = handle_find_references(
        _make_router(client),
        {"file": str(src), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result["count"] == 20
    assert len(result["references"]) == 20


def test_find_references_empty_result(tmp_path):
    client = MagicMock()
    client.request.return_value = None
    result = handle_find_references(
        _make_router(client),
        {"file": str(tmp_path / "x.py"), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result == {"count": 0, "references": []}


def test_find_references_excludes_outside_project(tmp_path):
    client = MagicMock()
    client.request.return_value = [_loc("/usr/lib/python3/site.py", 0)]
    result = handle_find_references(
        _make_router(client),
        {"file": str(tmp_path / "x.py"), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result == {"count": 0, "references": []}


# ── get_signature ─────────────────────────────────────────────────────────────

def test_get_signature_splits_signature_and_docstring(tmp_path):
    client = MagicMock()
    client.request.return_value = {
        "contents": {
            "kind": "markdown",
            "value": "def charge_card(amount: Decimal) -> ChargeResult\nCharges the card.",
        }
    }
    result = handle_get_signature(
        _make_router(client),
        {"file": str(tmp_path / "x.py"), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result["signature"] == "def charge_card(amount: Decimal) -> ChargeResult"
    assert result["docstring"] == "Charges the card."


def test_get_signature_null_result(tmp_path):
    client = MagicMock()
    client.request.return_value = None
    result = handle_get_signature(
        _make_router(client),
        {"file": str(tmp_path / "x.py"), "line": 0, "character": 0},
        str(tmp_path),
    )
    assert result is None


# ── get_call_hierarchy ────────────────────────────────────────────────────────

def test_get_call_hierarchy_null_prepare(tmp_path):
    client = MagicMock()
    client.request.return_value = None
    result = handle_get_call_hierarchy(
        _make_router(client),
        {"file": str(tmp_path / "x.py"), "line": 0, "character": 0, "direction": "both"},
        str(tmp_path),
    )
    assert result is None


def test_get_call_hierarchy_returns_symbol(tmp_path):
    call_item = {
        "name": "process_payment",
        "uri": f"file://{tmp_path}/pay.py",
        "range": {"start": {"line": 5, "character": 0}},
    }
    caller = {
        "name": "handle_checkout",
        "uri": f"file://{tmp_path}/checkout.py",
        "range": {"start": {"line": 30, "character": 0}},
    }
    client = MagicMock()
    # prepareCallHierarchy → [item]; incomingCalls → [{from: caller, fromRanges: [...]}]
    client.request.side_effect = [
        [call_item],  # prepareCallHierarchy
        [{"from": caller, "fromRanges": [{"start": {"line": 30, "character": 0}}]}],  # incomingCalls
        [],  # outgoingCalls
    ]
    (tmp_path / "pay.py").touch()
    (tmp_path / "checkout.py").touch()
    result = handle_get_call_hierarchy(
        _make_router(client),
        {"file": str(tmp_path / "pay.py"), "line": 5, "character": 0, "direction": "both"},
        str(tmp_path),
    )
    assert result["symbol"] == "process_payment"
    assert len(result["incoming"]) == 1
    assert result["incoming"][0]["symbol"] == "handle_checkout"


# ── warm_file ─────────────────────────────────────────────────────────────────

def test_warm_file_returns_ready(tmp_path):
    client = MagicMock()
    result = handle_warm_file(
        _make_router(client),
        {"file": str(tmp_path / "x.py")},
        str(tmp_path),
    )
    assert result == {"status": "ready", "server": "pyright"}
    client.open_file_lazy.assert_called_once_with(str(tmp_path / "x.py"))


def test_warm_file_server_unavailable(tmp_path):
    result = handle_warm_file(
        _make_router(raises=ServerUnavailableError("python", "pyright-langserver")),
        {"file": str(tmp_path / "x.py")},
        str(tmp_path),
    )
    assert result["error"] == "server_unavailable"
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
pytest tests/test_lsp_handlers.py -v
```
Expected: `ModuleNotFoundError: No module named 'codebase_context.lsp.handlers'`

- [ ] **Step 3: Implement handlers.py**

```python
# codebase_context/lsp/handlers.py
from __future__ import annotations

from pathlib import Path
from typing import Any

from codebase_context.lsp.filters import is_project_file
from codebase_context.lsp.router import (
    LspRouter,
    ServerUnavailableError,
    UnsupportedExtensionError,
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_line(path: str, line: int) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return lines[line].rstrip("\n").strip() if line < len(lines) else ""
    except OSError:
        return ""


def _uri_to_path(uri: str) -> str:
    return uri.removeprefix("file://")


def _loc_to_ref(loc: dict, project_root: str) -> dict | None:
    path = _uri_to_path(loc["uri"])
    if not is_project_file(path, project_root):
        return None
    line = loc["range"]["start"]["line"]
    return {"file": path, "line": line, "preview": _read_line(path, line)}


def _get_client(router: LspRouter, file: str):
    """Return the right LspClient or raise a typed error."""
    return router.get_client(Path(file).suffix)


_LANG_TO_SERVER_NAME: dict[str, str] = {
    "python":     "pyright",
    "typescript": "ts-server",
    "c":          "clangd",
}


def _error_for(exc: Exception) -> dict:
    if isinstance(exc, UnsupportedExtensionError):
        return {"error": "unsupported_extension", "ext": exc.ext}
    if isinstance(exc, ServerUnavailableError):
        # spec requires the short server name (e.g. "pyright"), not the binary name
        server_name = _LANG_TO_SERVER_NAME.get(exc.lang, exc.binary)
        return {"error": "server_unavailable", "server": server_name}
    return {"error": str(exc)}


# ── Tool handlers ─────────────────────────────────────────────────────────────

def handle_find_definition(
    router: LspRouter, arguments: dict, project_root: str
) -> Any:
    file = arguments["file"]
    try:
        client = _get_client(router, file)
    except (UnsupportedExtensionError, ServerUnavailableError) as e:
        return _error_for(e)

    client.open_file_lazy(file)
    result = client.request("textDocument/definition", {
        "textDocument": {"uri": f"file://{file}"},
        "position": {"line": arguments["line"], "character": arguments["character"]},
    })
    if not result:
        return None
    locs = result if isinstance(result, list) else [result]
    for loc in locs:
        ref = _loc_to_ref(loc, project_root)
        if ref:
            return ref
    return None


def handle_find_references(
    router: LspRouter, arguments: dict, project_root: str
) -> Any:
    file = arguments["file"]
    try:
        client = _get_client(router, file)
    except (UnsupportedExtensionError, ServerUnavailableError) as e:
        return _error_for(e)

    client.open_file_lazy(file)
    result = client.request("textDocument/references", {
        "textDocument": {"uri": f"file://{file}"},
        "position": {"line": arguments["line"], "character": arguments["character"]},
        "context": {"includeDeclaration": arguments.get("include_declaration", False)},
    })
    if not result:
        return {"count": 0, "references": []}
    refs = []
    for loc in result:
        ref = _loc_to_ref(loc, project_root)
        if ref:
            refs.append(ref)
            if len(refs) >= 20:
                break
    return {"count": len(refs), "references": refs}


def handle_get_signature(
    router: LspRouter, arguments: dict, project_root: str
) -> Any:
    file = arguments["file"]
    try:
        client = _get_client(router, file)
    except (UnsupportedExtensionError, ServerUnavailableError) as e:
        return _error_for(e)

    client.open_file_lazy(file)
    result = client.request("textDocument/hover", {
        "textDocument": {"uri": f"file://{file}"},
        "position": {"line": arguments["line"], "character": arguments["character"]},
    })
    if not result:
        return None

    contents = result.get("contents", "")
    if isinstance(contents, dict):
        text = contents.get("value", "")
    elif isinstance(contents, list):
        text = "\n".join(
            c.get("value", c) if isinstance(c, dict) else str(c) for c in contents
        )
    else:
        text = str(contents)

    parts = text.strip().split("\n", 1)
    signature = parts[0].strip()
    docstring = parts[1].strip() if len(parts) > 1 else None
    return {"signature": signature, "docstring": docstring}


def handle_get_call_hierarchy(
    router: LspRouter, arguments: dict, project_root: str
) -> Any:
    file = arguments["file"]
    direction = arguments.get("direction", "both")
    try:
        client = _get_client(router, file)
    except (UnsupportedExtensionError, ServerUnavailableError) as e:
        return _error_for(e)

    client.open_file_lazy(file)
    items = client.request("textDocument/prepareCallHierarchy", {
        "textDocument": {"uri": f"file://{file}"},
        "position": {"line": arguments["line"], "character": arguments["character"]},
    })
    if not items:
        return None

    item = items[0]

    def _call_site(entry: dict, key: str) -> dict | None:
        side = entry.get(key, {})
        path = _uri_to_path(side.get("uri", ""))
        if not is_project_file(path, project_root):
            return None
        # Both incomingCalls and outgoingCalls use "fromRanges" for call-site ranges
        ranges = entry.get("fromRanges") or []
        line = (
            ranges[0]["start"]["line"] if ranges
            else side.get("range", {}).get("start", {}).get("line", 0)
        )
        return {"symbol": side.get("name", ""), "file": path, "line": line}

    output: dict[str, Any] = {"symbol": item.get("name", "")}
    if direction in ("incoming", "both"):
        raw = client.request("callHierarchy/incomingCalls", {"item": item}) or []
        output["incoming"] = [s for e in raw if (s := _call_site(e, "from"))]
    if direction in ("outgoing", "both"):
        raw = client.request("callHierarchy/outgoingCalls", {"item": item}) or []
        output["outgoing"] = [s for e in raw if (s := _call_site(e, "to"))]
    return output


def handle_warm_file(
    router: LspRouter, arguments: dict, project_root: str
) -> Any:
    file = arguments["file"]
    ext = Path(file).suffix
    try:
        client = _get_client(router, file)
    except (UnsupportedExtensionError, ServerUnavailableError) as e:
        return _error_for(e)

    client.open_file_lazy(file)
    return {"status": "ready", "server": router.server_name_for_ext(ext)}
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
pytest tests/test_lsp_handlers.py -v
```
Expected: 15+ passed

- [ ] **Step 5: Run the full test suite — no regressions**

```bash
pytest -v
```
Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add codebase_context/lsp/handlers.py tests/test_lsp_handlers.py
git commit -m "feat: add LSP tool handler functions (find_definition, references, signature, call_hierarchy, warm_file)"
```

---

## Task 6: `mcp_server.py` — Wire in the 5 new tools

The 5 new tools are added to `list_tools()` and dispatched in `call_tool()`. An `LspRouter` is created at startup and shut down via `atexit`.

**Files:**
- Modify: `codebase_context/mcp_server.py`
- Create: `tests/test_mcp_lsp_tools.py`

- [ ] **Step 1: Add `pytest-asyncio` to pyproject.toml dev dependencies**

The async test in this task requires `pytest-asyncio`. Edit `pyproject.toml`:

```toml
# Change:
dev = ["pytest>=8.0", "pytest-cov>=5.0"]

# To:
dev = ["pytest>=8.0", "pytest-cov>=5.0", "pytest-asyncio>=0.23"]
```

Also add asyncio mode config so the marker works without extra decoration:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Then reinstall dev deps:

```bash
pip install -e ".[dev]"
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_mcp_lsp_tools.py
"""
Verify the 5 LSP tools are registered in mcp_server and dispatch correctly.
We test via the handler layer (already covered in test_lsp_handlers.py) and
verify the wiring in mcp_server via source-level assertions on list_tools.
"""
import inspect
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import codebase_context.mcp_server as mcp_server_mod


LSP_TOOL_NAMES = [
    "find_definition",
    "find_references",
    "get_signature",
    "get_call_hierarchy",
    "warm_file",
]


def test_all_lsp_tool_names_present_in_source():
    src = inspect.getsource(mcp_server_mod)
    for name in LSP_TOOL_NAMES:
        assert f'"{name}"' in src, f'Tool name "{name}" not found in mcp_server source'


def test_lsp_handler_imports_present_in_source():
    src = inspect.getsource(mcp_server_mod)
    assert "LspRouter" in src
    assert "handle_find_definition" in src


@pytest.mark.asyncio
async def test_handle_lsp_tool_returns_text_content():
    """_handle_lsp_tool must wrap handler output in TextContent."""
    from codebase_context.lsp.router import ServerUnavailableError

    router = MagicMock()
    router.get_client.side_effect = ServerUnavailableError("python", "pyright-langserver")

    result = await mcp_server_mod._handle_lsp_tool(
        "find_definition", router,
        {"file": "/tmp/x.py", "line": 0, "character": 0},
        "/tmp",
    )
    assert len(result) == 1
    payload = json.loads(result[0].text)
    assert payload["error"] == "server_unavailable"
```

- [ ] **Step 3: Run tests — expect failures (functions not wired yet)**

```bash
pytest tests/test_mcp_lsp_tools.py -v
```
Expected: `AssertionError` on missing tool names or `AttributeError` on `_handle_lsp_tool`

- [ ] **Step 4: Add the 5 tools to mcp_server.py**

In `run_server()`, after the `retriever = ...` line, add:

```python
    from codebase_context.lsp.router import LspRouter
    import atexit
    router = LspRouter(project_root)
    atexit.register(router.shutdown)
```

In `list_tools()`, append to the returned list:

```python
            types.Tool(
                name="find_definition",
                description=(
                    "Resolve where a symbol at a given position is defined. "
                    "Use before reading a file to locate the exact definition site. "
                    "Returns null for stdlib symbols."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file":      {"type": "string",  "description": "Absolute path to the file"},
                        "line":      {"type": "integer", "description": "Zero-based line number"},
                        "character": {"type": "integer", "description": "Zero-based UTF-16 character offset"},
                    },
                    "required": ["file", "line", "character"],
                },
            ),
            types.Tool(
                name="find_references",
                description=(
                    "Find all usages of a symbol across the project. "
                    "Capped at 20 results. Excludes stdlib, node_modules, and .venv paths."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file":                {"type": "string",  "description": "Absolute path to the file"},
                        "line":                {"type": "integer", "description": "Zero-based line number"},
                        "character":           {"type": "integer", "description": "Zero-based UTF-16 character offset"},
                        "include_declaration": {"type": "boolean", "description": "Include the definition site. Default: false", "default": False},
                    },
                    "required": ["file", "line", "character"],
                },
            ),
            types.Tool(
                name="get_signature",
                description=(
                    "Get the type signature and docstring for a symbol at a position. "
                    "Use this to understand a function's interface before reading its implementation."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file":      {"type": "string",  "description": "Absolute path to the file"},
                        "line":      {"type": "integer", "description": "Zero-based line number"},
                        "character": {"type": "integer", "description": "Zero-based UTF-16 character offset"},
                    },
                    "required": ["file", "line", "character"],
                },
            ),
            types.Tool(
                name="get_call_hierarchy",
                description=(
                    "Get what a function calls (outgoing) and what calls it (incoming). "
                    "Use to understand blast radius before modifying a function."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file":      {"type": "string", "description": "Absolute path to the file"},
                        "line":      {"type": "integer", "description": "Zero-based line number"},
                        "character": {"type": "integer", "description": "Zero-based UTF-16 character offset"},
                        "direction": {
                            "type": "string",
                            "enum": ["incoming", "outgoing", "both"],
                            "description": "Which direction to query. Default: both",
                            "default": "both",
                        },
                    },
                    "required": ["file", "line", "character"],
                },
            ),
            types.Tool(
                name="warm_file",
                description=(
                    "Pre-warm the LSP server for a file so subsequent queries are fast. "
                    "Call this after opening a file, before calling find_definition or find_references."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "description": "Absolute path to the file"},
                    },
                    "required": ["file"],
                },
            ),
```

In `call_tool()`, add new branches before the final `else`:

```python
            elif name in ("find_definition", "find_references", "get_signature",
                          "get_call_hierarchy", "warm_file"):
                return await _handle_lsp_tool(name, router, arguments, project_root)
```

Add the new helper function after `_handle_get_repo_map`:

```python
async def _handle_lsp_tool(
    tool_name: str, router, arguments: dict, project_root: str
) -> list:
    from mcp import types
    from codebase_context.lsp import handlers

    _DISPATCH = {
        "find_definition":    handlers.handle_find_definition,
        "find_references":    handlers.handle_find_references,
        "get_signature":      handlers.handle_get_signature,
        "get_call_hierarchy": handlers.handle_get_call_hierarchy,
        "warm_file":          handlers.handle_warm_file,
    }
    try:
        result = _DISPATCH[tool_name](router, arguments, project_root)
    except TimeoutError:
        result = {"error": "timeout"}
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
```

Note: `call_tool` is already defined as a nested function inside `run_server()` and closes over `retriever` and `project_root`. Assigning `router` inside `run_server()` before the decorator is applied means it will automatically be in scope — no restructuring needed.

- [ ] **Step 5: Run tests — expect all pass**

```bash
pytest tests/test_mcp_lsp_tools.py -v
```
Expected: 3 passed

- [ ] **Step 6: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml codebase_context/mcp_server.py tests/test_mcp_lsp_tools.py
git commit -m "feat: add 5 LSP tools to MCP server (find_definition, find_references, get_signature, get_call_hierarchy, warm_file)"
```

---

## Task 7: `cli.py` — LSP binary detection in `ccindex init`

**Files:**
- Modify: `codebase_context/cli.py`
- Create: `tests/test_cli_lsp.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_lsp.py
import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from codebase_context.cli import cli


def _mock_indexer():
    idx = MagicMock()
    idx.full_index.return_value = MagicMock(
        files_indexed=0, chunks_created=0, duration_seconds=0.1
    )
    return idx


def _init_project(runner, tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
    return tmp_path


def test_init_reports_missing_lsp_binaries(tmp_path):
    _init_project(None, tmp_path)
    runner = CliRunner()
    # Patch via the module that imports shutil, not the global shutil
    with patch("codebase_context.indexer.Indexer", return_value=_mock_indexer()), \
         patch("codebase_context.cli.shutil.which", return_value=None):
        result = runner.invoke(cli, ["--root", str(tmp_path), "init"], input="n\nn\nn\nn\n")
    assert "pyright-langserver" in result.output
    assert "typescript-language-server" in result.output
    assert "clangd" in result.output


def test_init_skips_lsp_prompt_when_all_binaries_present(tmp_path):
    _init_project(None, tmp_path)
    runner = CliRunner()
    with patch("codebase_context.indexer.Indexer", return_value=_mock_indexer()), \
         patch("codebase_context.cli.shutil.which", return_value="/usr/bin/something"):
        result = runner.invoke(cli, ["--root", str(tmp_path), "init"], input="n\nn\nn\n")
    assert "Install npm-based LSP" not in result.output


def test_init_npm_install_runs_on_confirm(tmp_path):
    _init_project(None, tmp_path)
    runner = CliRunner()
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    with patch("codebase_context.indexer.Indexer", return_value=_mock_indexer()), \
         patch("codebase_context.cli.shutil.which", return_value=None), \
         patch("codebase_context.cli.subprocess.run", mock_run):
        runner.invoke(cli, ["--root", str(tmp_path), "init"], input="n\nn\nn\ny\n")
    # subprocess.run should have been called for npm installs
    npm_calls = [c for c in mock_run.call_args_list if "npm" in str(c)]
    assert len(npm_calls) > 0


def test_init_shows_clangd_manual_instructions_when_missing(tmp_path):
    _init_project(None, tmp_path)
    runner = CliRunner()
    # Only clangd missing, npm ones present
    def fake_which(cmd):
        return None if cmd == "clangd" else "/usr/bin/" + cmd
    with patch("codebase_context.indexer.Indexer", return_value=_mock_indexer()), \
         patch("codebase_context.cli.shutil.which", fake_which):
        result = runner.invoke(cli, ["--root", str(tmp_path), "init"], input="n\nn\nn\n")
    assert "apt install clangd" in result.output or "brew install llvm" in result.output
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_cli_lsp.py -v
```
Expected: 4 failures (function not yet defined)

- [ ] **Step 3: Add `_setup_lsp_binaries()` to cli.py and call it from init**

Add near the top of `cli.py`, after existing imports:

```python
import shutil
import subprocess
```

Add the function before `_update_gitignore`:

```python
_LSP_BINARIES = [
    ("pyright-langserver",        "Python",        "npm install -g pyright"),
    ("typescript-language-server","TypeScript/JS",  "npm install -g typescript typescript-language-server"),
    ("clangd",                    "C/C++",          None),  # system package — manual install
]


def _setup_lsp_binaries() -> None:
    """Check for LSP binaries and offer to install the npm-based ones."""
    missing = [
        (binary, lang, cmd)
        for binary, lang, cmd in _LSP_BINARIES
        if not shutil.which(binary)
    ]
    if not missing:
        return

    click.echo("\nLSP code navigation tools require these binaries:")
    for binary, lang, install_cmd in missing:
        hint = install_cmd if install_cmd else "sudo apt install clangd  OR  brew install llvm"
        click.echo(f"  {binary} ({lang})  →  {hint}")

    npm_installable = [(b, l, c) for b, l, c in missing if c]
    if npm_installable and click.confirm("\nInstall npm-based LSP servers now?", default=True):
        for binary, _lang, install_cmd in npm_installable:
            click.echo(f"  Installing {binary}...")
            result = subprocess.run(
                install_cmd.split(), capture_output=True, text=True
            )
            if result.returncode == 0:
                click.echo(f"  ✓ {binary} installed")
            else:
                click.echo(f"  ✗ {binary} failed: {result.stderr.strip()}")

    clangd_missing = any(c is None for _, _, c in missing)
    if clangd_missing:
        click.echo("\n  To install clangd manually:")
        click.echo("    Ubuntu/Debian:  sudo apt install clangd")
        click.echo("    macOS:          brew install llvm")
```

In the `init` command, add one line at the end of the function body (after `_setup_mcp_server(root)`):

```python
    _setup_lsp_binaries()
```

- [ ] **Step 4: Run the new tests**

```bash
pytest tests/test_cli_lsp.py -v
```
Expected: 4 passed

- [ ] **Step 5: Run the full test suite — no regressions**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add codebase_context/cli.py tests/test_cli_lsp.py
git commit -m "feat: detect and offer to install LSP binaries during ccindex init"
```

---

## Final verification

- [ ] **Run the complete test suite one last time**

```bash
pytest -v --tb=short
```
Expected: all tests pass, no warnings about missing imports

- [ ] **Verify the new tools appear in the CLI help (smoke test)**

```bash
ccindex --help
```
Expected: existing commands still present, no import errors

- [ ] **Update HANDOFF.md and commit**

```bash
git add HANDOFF.md DECISIONS.md
git commit -m "handoff: code-writer completed LSP MCP integration"
git push
```
