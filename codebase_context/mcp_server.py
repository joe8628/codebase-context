"""MCP server exposing search_codebase, get_symbol, get_repo_map,
narrative_* (Layer 3a), and coord_* (Layer 3b) tools."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import sqlite3
import sys
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


def _check_old_memgram_schema(project_root: str) -> None:
    """Refuse to start if memgram.db has the old content-backed FTS schema."""
    db_path = Path(project_root) / ".codebase-context" / "memgram.db"
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name='obs_ai'"
        ).fetchone()[0]
    finally:
        conn.close()
    if count > 0:
        print(
            "ERROR: memgram.db has an old schema incompatible with this version.\n"
            "Run:   ccindex migrate",
            file=sys.stderr,
        )
        sys.exit(1)


def run_server() -> None:
    """Entry point called by `ccindex serve`."""
    project_root = os.getcwd()
    _setup_logging(project_root)
    logger.info("MCP server starting. project_root=%s", project_root)

    _check_old_memgram_schema(project_root)

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types

    from codebase_context.embedder import Embedder
    from codebase_context.retriever import Retriever
    from codebase_context.memory_store import MemoryStore
    from codebase_context.memgram.store import MemgramStore

    embedder = Embedder()
    retriever = Retriever(project_root, embedder=embedder)
    memory_store = MemoryStore(project_root)
    narrative_store = MemgramStore(project_root)

    server = Server("codebase-context")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            # --- Layer 1: Code Map ---
            types.Tool(
                name="search_codebase",
                description=(
                    "Search the codebase using natural language. Returns the most "
                    "semantically relevant functions, classes, and methods. "
                    "Use for finding implementations, locating utilities, or understanding a subsystem."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "top_k": {"type": "integer", "description": "Number of results. Default: 10. Max: 25.", "default": DEFAULT_TOP_K},
                        "language": {"type": "string", "description": 'Filter to "python" or "typescript"'},
                        "filepath_contains": {"type": "string", "description": "Fuzzy filter on filepath"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="get_symbol",
                description=(
                    "Fetch a specific symbol (function, class, method) by exact name. "
                    "Use to retrieve a known symbol's full implementation or verify it exists."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Exact symbol name (case-sensitive)"},
                    },
                    "required": ["name"],
                },
            ),
            types.Tool(
                name="get_repo_map",
                description=(
                    "Returns the full repo map — all files, classes, and function signatures. "
                    "Use only when you need a complete structural overview: new file placement, "
                    "architecture questions, or cross-cutting changes. ~8k tokens — call sparingly."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            # --- Layer 3a: Narrative Memory (cross-session) ---
            types.Tool(
                name="narrative_save",
                description=(
                    "Save a cross-session observation (finding, decision, bugfix, handoff). "
                    "Call after significant findings, bugfixes, or decisions. "
                    "Structure content with ## What / ## Why / ## Where / ## Learned sections."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "title":   {"type": "string", "description": "Short verb+what title (e.g. 'Fixed N+1 query in UserList')"},
                        "content": {"type": "string", "description": "Freeform detail with What/Why/Where/Learned sections"},
                        "type": {
                            "type": "string",
                            "enum": ["handoff", "decision", "bugfix", "architecture", "discovery"],
                            "description": "Observation type. Default: handoff",
                            "default": "handoff",
                        },
                    },
                    "required": ["title", "content"],
                },
            ),
            types.Tool(
                name="narrative_context",
                description=(
                    "Load recent cross-session observations for this project. "
                    "Call at session start to restore prior context."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max observations to return. Default: 10", "default": 10},
                    },
                },
            ),
            types.Tool(
                name="narrative_search",
                description=(
                    "Full-text search over cross-session observations. "
                    "Use to find past decisions, bugfixes, or handoffs relevant to the current task."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search terms"},
                        "type": {
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
                name="narrative_session_end",
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
            # --- Layer 3b: Coordination State (intra-session) ---
            types.Tool(
                name="coord_store_event",
                description=(
                    "Log an intra-session coordination event. "
                    "Call after decisions, task transitions, or agent actions. "
                    "Use only when explicitly continuing an in-flight task — not at session start."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent":      {"type": "string", "description": "Agent name (e.g. planner, dev-agent)"},
                        "event_type": {
                            "type": "string",
                            "enum": ["task_started", "task_completed", "task_failed", "agent_action", "decision", "error"],
                            "description": "Event type",
                        },
                        "content":    {"type": "string", "description": "Event content — freeform text"},
                        "task_id":    {"type": "string", "description": "Optional task ID to associate this event with"},
                    },
                    "required": ["agent", "event_type", "content"],
                },
            ),
            types.Tool(
                name="coord_recall_events",
                description=(
                    "Full-text search over intra-session coordination events. "
                    "Use to retrieve past task decisions or agent actions for the current task."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query":      {"type": "string",  "description": "Full-text search query"},
                        "limit":      {"type": "integer", "description": "Max results. Default: 10.", "default": 10},
                        "agent":      {"type": "string",  "description": "Filter by agent name"},
                        "event_type": {"type": "string",  "description": "Filter by event type"},
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="coord_record_manifest",
                description=(
                    "Record files and symbols a Dev Agent touched at task completion. "
                    "Call at the end of each task with the full list of changes."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task ID"},
                        "changes": {
                            "type": "array",
                            "description": "List of change records",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "filepath":      {"type": "string"},
                                    "change_type":   {"type": "string", "enum": ["added", "modified", "deleted"]},
                                    "symbol_name":   {"type": "string"},
                                    "old_signature": {"type": "string"},
                                    "new_signature": {"type": "string"},
                                },
                                "required": ["filepath", "change_type"],
                            },
                        },
                    },
                    "required": ["task_id", "changes"],
                },
            ),
            types.Tool(
                name="coord_get_manifest",
                description=(
                    "Retrieve the change manifest for a task. "
                    "Use as a Review Agent to see which files and symbols were modified."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task ID to retrieve manifest for"},
                    },
                    "required": ["task_id"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        logger.info("Tool call: %s  args=%s", name, arguments)
        try:
            if name == "search_codebase":
                return await _handle_search(retriever, arguments)
            elif name == "get_symbol":
                return await _handle_get_symbol(retriever, arguments)
            elif name == "get_repo_map":
                return await _handle_get_repo_map(retriever, project_root)
            elif name == "narrative_save":
                return await _handle_narrative_save(narrative_store, arguments)
            elif name == "narrative_context":
                return await _handle_narrative_context(narrative_store, arguments)
            elif name == "narrative_search":
                return await _handle_narrative_search(narrative_store, arguments)
            elif name == "narrative_session_end":
                return await _handle_narrative_session_end(narrative_store, arguments)
            elif name == "coord_store_event":
                return await _handle_coord_store_event(memory_store, arguments)
            elif name == "coord_recall_events":
                return await _handle_coord_recall_events(memory_store, arguments)
            elif name == "coord_record_manifest":
                return await _handle_coord_record_manifest(memory_store, arguments)
            elif name == "coord_get_manifest":
                return await _handle_coord_get_manifest(memory_store, arguments)
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


# --- Layer 1 handlers ---

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
        query, top_k=top_k, language=language, filepath_contains=filepath_contains
    )
    payload = [
        {
            "filepath": r.filepath, "symbol_name": r.symbol_name, "symbol_type": r.symbol_type,
            "signature": r.signature, "source": r.source, "score": r.score,
            "start_line": r.start_line, "end_line": r.end_line, "parent_class": r.parent_class,
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
            "filepath": r.filepath, "symbol_name": r.symbol_name, "symbol_type": r.symbol_type,
            "signature": r.signature, "source": r.source, "score": r.score,
            "start_line": r.start_line, "end_line": r.end_line, "parent_class": r.parent_class,
        }
        for r in results
    ]
    return [types.TextContent(type="text", text=json.dumps(payload, indent=2))]


async def _handle_get_repo_map(retriever, project_root: str):
    from mcp import types
    content = retriever.get_repo_map(project_root)
    return [types.TextContent(type="text", text=content)]


# --- Layer 3a: Narrative handlers ---

def _format_memories(memories: list[dict]) -> str:
    lines = []
    for m in memories:
        ts = datetime.datetime.fromtimestamp(int(m["created_at"])).strftime("%Y-%m-%d %H:%M")
        lines.append(f"### [{m['type']}] {m['title']}")
        lines.append(f"*{ts}*")
        lines.append(m["content"])
        lines.append("")
    return "\n".join(lines)


async def _handle_narrative_save(narrative_store, arguments: dict):
    from mcp import types
    id_ = narrative_store.save(
        arguments["title"],
        arguments.get("content", ""),
        arguments.get("type", "handoff"),
    )
    return [types.TextContent(type="text", text=json.dumps({"saved": True, "id": id_}))]


async def _handle_narrative_context(narrative_store, arguments: dict):
    from mcp import types
    memories = narrative_store.context(limit=int(arguments.get("limit", 10)))
    if not memories:
        return [types.TextContent(type="text", text="No memories stored yet.")]
    return [types.TextContent(type="text", text=_format_memories(memories))]


async def _handle_narrative_search(narrative_store, arguments: dict):
    from mcp import types
    memories = narrative_store.search(
        arguments["query"],
        type=arguments.get("type"),
        limit=int(arguments.get("limit", 10)),
    )
    if not memories:
        return [types.TextContent(type="text", text=f"No results for '{arguments['query']}'.")]
    return [types.TextContent(type="text", text=_format_memories(memories))]


async def _handle_narrative_session_end(narrative_store, arguments: dict):
    from mcp import types
    narrative_store.session_end(arguments.get("summary", ""))
    return [types.TextContent(type="text", text=json.dumps({"session_ended": True}))]


# --- Layer 3b: Coordination handlers ---

async def _handle_coord_store_event(memory_store, arguments: dict):
    from mcp import types
    event_id = memory_store.store_event(
        agent=arguments["agent"],
        event_type=arguments["event_type"],
        content=arguments["content"],
        task_id=arguments.get("task_id"),
    )
    return [types.TextContent(type="text", text=json.dumps({"id": event_id}))]


async def _handle_coord_recall_events(memory_store, arguments: dict):
    from mcp import types
    results = memory_store.search_events(
        query=arguments["query"],
        limit=int(arguments.get("limit", 10)),
        agent=arguments.get("agent"),
        event_type=arguments.get("event_type"),
    )
    return [types.TextContent(type="text", text=json.dumps(results, indent=2))]


async def _handle_coord_record_manifest(memory_store, arguments: dict):
    from mcp import types
    count = memory_store.record_manifest(
        task_id=arguments["task_id"],
        changes=arguments["changes"],
    )
    return [types.TextContent(type="text", text=json.dumps({"count": count}))]


async def _handle_coord_get_manifest(memory_store, arguments: dict):
    from mcp import types
    records = memory_store.get_manifest(task_id=arguments["task_id"])
    return [types.TextContent(type="text", text=json.dumps(records, indent=2))]
