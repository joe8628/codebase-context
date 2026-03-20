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
