# tests/test_lsp_client.py
import json
import pytest
from unittest.mock import MagicMock, patch

from codebase_context.lsp.client import LspClient


def _frame(req_id: int, result: object) -> bytes:
    """Build a valid LSP Content-Length framed response."""
    body = json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


class _FakeStdout:
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
        client.open_file("/project/main.py", "x = 2", "python")

    assert len(sent) == n_after_first


def test_request_timeout_raises():
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

    all_sent = b"".join(sent)
    bodies = []
    buf = all_sent
    while b"Content-Length:" in buf:
        length_line = buf.split(b"Content-Length: ")[1].split(b"\r\n")[0]
        length = int(length_line)
        _, rest = buf.split(b"\r\n\r\n", 1)
        bodies.append(json.loads(rest[:length]))
        buf = rest[length:]

    save_msg = next(m for m in bodies if m.get("method") == "textDocument/didSave")
    assert "id" not in save_msg
