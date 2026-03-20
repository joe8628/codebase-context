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
    assert result["server"] == "pyright"  # short name, not binary name


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
    client.request.side_effect = [
        [call_item],
        [{"from": caller, "fromRanges": [{"start": {"line": 30, "character": 0}}]}],
        [],
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
