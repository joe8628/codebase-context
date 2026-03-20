"""
Verify the 5 LSP tools are registered in mcp_server and dispatch correctly.
"""
import inspect
import json
import pytest
from unittest.mock import MagicMock

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


async def test_handle_lsp_tool_returns_text_content():
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
