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
        # Buffer for responses that arrived before pending was registered
        self._response_cache: dict[int, Any] = {}
        self._cache_lock = threading.Lock()

        self._initialize()

        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()

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
        with self._cache_lock:
            # Check if response already arrived before we registered
            if req_id in self._response_cache:
                return self._response_cache.pop(req_id)
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
                if req_id is not None:
                    with self._cache_lock:
                        if req_id in self._pending:
                            self._pending[req_id].put(msg.get("result"))
                        else:
                            # Cache for late-registering request()
                            self._response_cache[req_id] = msg.get("result")
            except Exception:
                if self._running:
                    continue
                return

    def _read_one_response(self) -> dict:
        """Synchronously read one LSP response frame from stdout."""
        assert self._proc.stdout is not None
        header = b""
        while not header.endswith(b"\r\n\r\n"):
            ch = self._proc.stdout.read(1)
            if not ch:
                raise EOFError("LSP server closed stdout during initialize")
            header += ch
        length = int(header.split(b"Content-Length: ")[1].split(b"\r\n")[0])
        body = self._proc.stdout.read(length)
        return json.loads(body)

    def _initialize(self) -> None:
        req_id = self._next_id()
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
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
            },
        })
        self._read_one_response()
        self.notify("initialized", {})
