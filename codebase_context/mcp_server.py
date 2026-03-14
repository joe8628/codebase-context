"""MCP server exposing search_codebase, get_symbol, and get_repo_map tools."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from codebase_context.config import DEFAULT_TOP_K, MCP_LOG_PATH


def _setup_logging(project_root: str) -> None:
    """Log to file only — never stderr (would corrupt the stdio MCP protocol)."""
    log_path = Path(project_root) / MCP_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


logger = logging.getLogger(__name__)


def run_server() -> None:
    """Entry point called by `ccindex serve`."""
    project_root = os.getcwd()
    _setup_logging(project_root)
    logger.info("MCP server starting. project_root=%s", project_root)

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types

    from codebase_context.retriever import Retriever

    retriever = Retriever(project_root)

    # Eagerly load embedding model at startup (so first tool call is fast)
    try:
        retriever.embedder._get_model()
        logger.info("Embedding model loaded at startup.")
    except Exception as e:
        logger.warning("Could not pre-load embedding model: %s", e)

    server = Server("codebase-context")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="search_codebase",
                description=(
                    "Search the codebase using natural language. Returns the most "
                    "semantically relevant functions, classes, and methods. "
                    "Use this when you need to find how something is implemented, "
                    "locate existing utilities, or understand a subsystem."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results. Default: 10. Max: 25.",
                            "default": DEFAULT_TOP_K,
                        },
                        "language": {
                            "type": "string",
                            "description": 'Filter to "python" or "typescript"',
                        },
                        "filepath_contains": {
                            "type": "string",
                            "description": "Fuzzy filter on filepath",
                        },
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="get_symbol",
                description=(
                    "Fetch a specific symbol (function, class, method) by exact name. "
                    "Use this to retrieve a known symbol's full implementation. "
                    "Useful for verifying a symbol exists before referencing it, "
                    "or reading an implementation before modifying it."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Exact symbol name (case-sensitive)",
                        },
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="get_repo_map",
                description=(
                    "Returns the current repo map — a compact summary of all files, "
                    "classes, and function signatures in the codebase. "
                    "Use this when you need a fresh overview mid-session or when "
                    "the repo map in your context may be outdated after recent changes."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> list[types.TextContent]:
        logger.info("Tool call: %s  args=%s", name, arguments)

        try:
            if name == "search_codebase":
                return await _handle_search(retriever, arguments)
            elif name == "get_symbol":
                return await _handle_get_symbol(retriever, arguments)
            elif name == "get_repo_map":
                return await _handle_get_repo_map(retriever, project_root)
            else:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}),
                )]
        except Exception as e:
            logger.exception("Error handling tool %s: %s", name, e)
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": str(e), "results": []}),
            )]

    asyncio.run(_run_server(server))


async def _run_server(server) -> None:
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def _handle_search(retriever, arguments: dict):
    from mcp import types

    query = arguments["query"]
    top_k = min(int(arguments.get("top_k", DEFAULT_TOP_K)), 25)
    language = arguments.get("language")
    filepath_contains = arguments.get("filepath_contains")

    if retriever.store.count() == 0:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": "Index not found. Run: ccindex init", "results": []}),
        )]

    results = retriever.search(
        query,
        top_k=top_k,
        language=language,
        filepath_contains=filepath_contains,
    )

    payload = [
        {
            "filepath":     r.filepath,
            "symbol_name":  r.symbol_name,
            "symbol_type":  r.symbol_type,
            "signature":    r.signature,
            "source":       r.source,
            "score":        r.score,
            "start_line":   r.start_line,
            "end_line":     r.end_line,
            "parent_class": r.parent_class,
        }
        for r in results
    ]
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


async def _handle_get_symbol(retriever, arguments: dict):
    from mcp import types

    name = arguments["name"]

    if retriever.store.count() == 0:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": "Index not found. Run: ccindex init", "results": []}),
        )]

    results = retriever.get_symbol(name)
    payload = [
        {
            "filepath":     r.filepath,
            "symbol_name":  r.symbol_name,
            "symbol_type":  r.symbol_type,
            "signature":    r.signature,
            "source":       r.source,
            "score":        r.score,
            "start_line":   r.start_line,
            "end_line":     r.end_line,
            "parent_class": r.parent_class,
        }
        for r in results
    ]
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


async def _handle_get_repo_map(retriever, project_root: str):
    from mcp import types
    content = retriever.get_repo_map(project_root)
    return [types.TextContent(type="text", text=content)]
