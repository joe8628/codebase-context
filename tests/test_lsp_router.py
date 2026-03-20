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
