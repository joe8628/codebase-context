"""MCP server exposing mem_save, mem_context, mem_search, mem_session_end."""

from __future__ import annotations

import asyncio
import json
import logging
import os


logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 10


def _format_memories(memories: list[dict]) -> str:
    lines = []
    for m in memories:
        lines.append(f"### [{m['type']}] {m['title']}")
        lines.append(f"*{m['created_at']}*")
        lines.append(m["content"])
        lines.append("")
    return "\n".join(lines)


async def _handle_mem_save(store, arguments: dict):
    from mcp import types

    title = arguments["title"]
    content = arguments.get("content", "")
    mem_type = arguments.get("type", "handoff")
    id_ = store.save(title, content, mem_type)
    return [types.TextContent(type="text", text=json.dumps({"saved": True, "id": id_}))]


async def _handle_mem_context(store, arguments: dict):
    from mcp import types

    limit = int(arguments.get("limit", _DEFAULT_LIMIT))
    memories = store.context(limit=limit)
    if not memories:
        return [types.TextContent(type="text", text="No memories stored yet.")]
    return [types.TextContent(type="text", text=_format_memories(memories))]


async def _handle_mem_search(store, arguments: dict):
    from mcp import types

    query = arguments["query"]
    mem_type = arguments.get("type")
    limit = int(arguments.get("limit", _DEFAULT_LIMIT))
    memories = store.search(query, type=mem_type, limit=limit)
    if not memories:
        return [types.TextContent(type="text", text=f"No results for '{query}'.")]
    return [types.TextContent(type="text", text=_format_memories(memories))]


async def _handle_mem_session_end(store, arguments: dict):
    from mcp import types

    summary = arguments.get("summary", "")
    store.session_end(summary)
    return [types.TextContent(type="text", text=json.dumps({"session_ended": True}))]


def run_server() -> None:
    """Entry point called by `ccindex mem-serve`."""
    from mcp.server import Server
    from mcp import types

    from codebase_context.memgram.store import MemgramStore

    project_root = os.getcwd()
    store = MemgramStore(project_root)
    server = Server("memgram")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="mem_save",
                description=(
                    "Save a memory (finding, decision, bugfix, handoff) to the project store. "
                    "Call after significant findings, bugfixes, or decisions. "
                    "Structure content with ## What / ## Why / ## Where / ## Learned sections."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title":   {"type": "string", "description": "Short verb+what title (e.g. 'Fixed N+1 query in UserList')"},
                        "content": {"type": "string", "description": "Freeform detail with What/Why/Where/Learned sections"},
                        "type":    {
                            "type": "string",
                            "enum": ["handoff", "decision", "bugfix", "architecture", "discovery"],
                            "description": "Memory type. Default: handoff",
                            "default": "handoff",
                        },
                    },
                    "required": ["title", "content"],
                },
            ),
            types.Tool(
                name="mem_context",
                description=(
                    "Load recent memories for this project. Call at session start to "
                    "restore prior context. Returns the most recent stored observations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max memories to return. Default: 10", "default": 10},
                    },
                },
            ),
            types.Tool(
                name="mem_search",
                description=(
                    "Full-text search over stored memories. Use to find past decisions, "
                    "bugfixes, or handoffs relevant to your current task. "
                    "Optionally filter by type."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search terms"},
                        "type":  {
                            "type": "string",
                            "enum": ["handoff", "decision", "bugfix", "architecture", "discovery", "session_end"],
                            "description": "Optional type filter",
                        },
                        "limit": {"type": "integer", "description": "Max results. Default: 10", "default": 10},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="mem_session_end",
                description=(
                    "Record the end of a session with a one-line summary. "
                    "Call after completing a feature or fix, before stopping work."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "One-line session summary"},
                    },
                    "required": ["summary"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        logger.info("memgram tool: %s  args=%s", name, arguments)
        try:
            if name == "mem_save":
                return await _handle_mem_save(store, arguments)
            elif name == "mem_context":
                return await _handle_mem_context(store, arguments)
            elif name == "mem_search":
                return await _handle_mem_search(store, arguments)
            elif name == "mem_session_end":
                return await _handle_mem_session_end(store, arguments)
            else:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"Unknown tool: {name}"}),
                )]
        except Exception as e:
            logger.exception("Error handling memgram tool %s: %s", name, e)
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": str(e)}),
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
