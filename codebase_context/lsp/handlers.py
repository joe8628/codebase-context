from __future__ import annotations

from pathlib import Path
from typing import Any

from codebase_context.lsp.filters import is_project_file
from codebase_context.lsp.router import (
    LspRouter,
    ServerUnavailableError,
    UnsupportedExtensionError,
)

_LANG_TO_SERVER_NAME: dict[str, str] = {
    "python":     "pyright",
    "typescript": "ts-server",
    "c":          "clangd",
}


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
    return router.get_client(Path(file).suffix)


def _error_for(exc: Exception) -> dict:
    if isinstance(exc, UnsupportedExtensionError):
        return {"error": "unsupported_extension", "ext": exc.ext}
    if isinstance(exc, ServerUnavailableError):
        server_name = _LANG_TO_SERVER_NAME.get(exc.lang, exc.binary)
        return {"error": "server_unavailable", "server": server_name}
    return {"error": str(exc)}


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
