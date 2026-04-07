"""Verify LSP tools are NOT registered in mcp_server (Layer 2 scope narrowed)."""
import inspect
import codebase_context.mcp_server as mcp_server_mod

LSP_TOOL_NAMES = [
    "find_definition",
    "find_references",
    "get_signature",
    "get_call_hierarchy",
    "warm_file",
]


def test_lsp_tools_absent_from_list_tools():
    src = inspect.getsource(mcp_server_mod)
    for name in LSP_TOOL_NAMES:
        assert f'name="{name}"' not in src, \
            f'LSP tool "{name}" still registered in mcp_server — should be removed'


def test_lsp_router_not_instantiated_in_run_server():
    src = inspect.getsource(mcp_server_mod)
    assert "LspRouter(project_root)" not in src
