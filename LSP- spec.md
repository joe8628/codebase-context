# LSP MCP Server — Specification

## Overview

An MCP (Model Context Protocol) server that wraps Language Server Protocol (LSP)
clients for Python, TypeScript/React, and C/C++, exposing semantic code intelligence
as discrete tools for Claude Code. Designed to work alongside an existing tree-sitter
repo outline to minimize tokens used in agentic coding sessions.

---

## Goals

- Expose LSP semantic queries as MCP tools callable by Claude Code
- Support Python (pyright), TypeScript/TSX (typescript-language-server), and C/C++ (clangd)
- Manage LSP subprocess lifecycle transparently (start, warmup, keep-alive)
- Return minimal, structured responses — not raw LSP JSON
- Be runnable as a stdio MCP server with zero configuration beyond project root

---

## Non-goals

- Not a full LSP client or editor integration
- Not responsible for running tree-sitter (assumed to be handled upstream)
- Not a persistent daemon — lifecycle tied to the MCP session

---

## Architecture

```
Claude Code
    │  MCP (stdio JSON-RPC)
    ▼
lsp_mcp_server.py
    ├── LspClient (pyright)       ← manages subprocess + JSON-RPC over stdio
    ├── LspClient (ts-server)
    └── LspClient (clangd)
```

Each `LspClient` instance:
- Spawns the LSP binary as a subprocess
- Handles `Content-Length` framing over stdio
- Manages request IDs and response matching via threading
- Tracks open files to avoid redundant `didOpen` notifications

---

## Language Server Binaries

| Language | Binary | Install |
|----------|--------|---------|
| Python | `pyright-langserver --stdio` | `npm i -g pyright` |
| TypeScript / TSX | `typescript-language-server --stdio` | `npm i -g typescript typescript-language-server` |
| C / C++ | `clangd` | `brew install llvm` / `apt install clangd` |

File extension → server routing:

| Extension | Server |
|-----------|--------|
| `.py` | pyright |
| `.ts` | ts-server |
| `.tsx` | ts-server |
| `.js` | ts-server |
| `.jsx` | ts-server |
| `.c` | clangd |
| `.cpp` | clangd |
| `.h` | clangd |

---

## MCP Tools

### `find_definition`

Resolve where a symbol at a given position is defined.

**Input**
```json
{
  "file": "/abs/path/to/file.py",
  "line": 42,
  "character": 15
}
```

**Output**
```json
{
  "file": "/abs/path/to/other_file.py",
  "line": 88,
  "preview": "def charge_card(amount: Decimal, token: str) -> ChargeResult:"
}
```

Returns `null` if no definition found (e.g. stdlib symbol).

---

### `find_references`

Find all usages of a symbol across the project.

**Input**
```json
{
  "file": "/abs/path/to/file.py",
  "line": 42,
  "character": 15,
  "include_declaration": false
}
```

**Output**
```json
{
  "count": 4,
  "references": [
    { "file": "/abs/path/main.py",    "line": 10, "preview": "result = charge_card(amt, tok)" },
    { "file": "/abs/path/billing.py", "line": 55, "preview": "charge_card(order.total, card)" }
  ]
}
```

Capped at 20 results. Excludes stdlib and `node_modules` / `.venv` paths.

---

### `get_signature`

Get the type signature and docstring for a symbol.

**Input**
```json
{
  "file": "/abs/path/to/file.py",
  "line": 42,
  "character": 15
}
```

**Output**
```json
{
  "signature": "def charge_card(amount: Decimal, token: str) -> ChargeResult",
  "docstring": "Charges the given amount to the card identified by token.\nRaises PaymentError on failure."
}
```

---

### `get_call_hierarchy`

Get what a function calls (outgoing) and what calls it (incoming).

**Input**
```json
{
  "file": "/abs/path/to/file.py",
  "line": 42,
  "character": 15,
  "direction": "both"
}
```

`direction`: `"incoming"` | `"outgoing"` | `"both"`

**Output**
```json
{
  "symbol": "process_payment",
  "incoming": [
    { "symbol": "handle_checkout", "file": "/abs/path/checkout.py", "line": 30 }
  ],
  "outgoing": [
    { "symbol": "validate_user",   "file": "/abs/path/auth.py",     "line": 14 },
    { "symbol": "charge_card",     "file": "/abs/path/billing.py",  "line": 88 },
    { "symbol": "emit_event",      "file": "/abs/path/events.py",   "line": 22 }
  ]
}
```

---

### `warm_file`

Pre-warms the LSP server for a given file so subsequent queries are fast.
Called automatically on first query for a file; exposed as a tool for explicit
pre-warming (e.g. from a Claude Code hook on `read_file`).

**Input**
```json
{ "file": "/abs/path/to/file.py" }
```

**Output**
```json
{ "status": "ready", "server": "pyright" }
```

---

## Position Utilities

Internal module `positions.py`:

```python
def offset_to_position(source: str, offset: int) -> dict:
    """Convert byte offset to {line, character} LSP position."""

def position_to_offset(source: str, line: int, character: int) -> int:
    """Convert {line, character} LSP position to byte offset."""
```

These must handle multi-byte Unicode characters correctly (LSP uses UTF-16 code units
for `character`; pyright and clangd both follow the spec strictly).

---

## LspClient — internal interface

```python
class LspClient:
    def __init__(self, cmd: list[str], root_uri: str): ...
    def open_file(self, path: str, source: str, language_id: str): ...
    def request(self, method: str, params: dict, timeout: float = 5.0) -> any: ...
    def notify(self, method: str, params: dict): ...
    def shutdown(self): ...
```

Initialization sequence on construction:
1. Spawn subprocess
2. Send `initialize` request with capability declarations
3. Send `initialized` notification
4. Start background reader thread

File tracking: maintain a `set[str]` of opened URIs. Skip `didOpen` if already open.

---

## Error handling

| Situation | Behavior |
|-----------|----------|
| Binary not found | Return `{"error": "server_unavailable", "server": "pyright"}` |
| Request timeout | Return `{"error": "timeout"}` after 5s |
| No LSP for extension | Return `{"error": "unsupported_extension", "ext": ".rb"}` |
| Result is empty/null | Return `null` (not an error) |
| stdlib / external path | Omit from results silently |

Never raise exceptions to the MCP caller — always return structured error dicts.

---

## Filtering

Exclude from all results:
- Paths containing `node_modules`
- Paths containing `.venv`, `venv`, `env`
- Paths containing `__pycache__`
- Paths outside `PROJECT_ROOT`

---

## Configuration

Resolved in this order:
1. Environment variable `PROJECT_ROOT` — required
2. Optional `LSP_MCP_CONFIG` path to a JSON config file for custom binary paths

```json
{
  "project_root": "/abs/path/to/project",
  "servers": {
    "python": { "cmd": ["pyright-langserver", "--stdio"] },
    "typescript": { "cmd": ["typescript-language-server", "--stdio"] },
    "c": { "cmd": ["clangd", "--background-index"] }
  }
}
```

---

## Project structure

```
lsp-mcp/
├── server.py          # MCP server entrypoint — tool definitions and dispatch
├── lsp_client.py      # LspClient class — subprocess + JSON-RPC management
├── positions.py       # offset ↔ LSP position conversion utilities
├── tool_handlers.py   # one function per tool — LSP query + response shaping
├── filters.py         # path exclusion logic
├── requirements.txt   # mcp, anyio
└── README.md
```

---

## Registration in Claude Code

`.claude/mcp_servers.json` (project-level) or `~/.claude/mcp_servers.json` (global):

```json
{
  "mcpServers": {
    "lsp-tools": {
      "command": "python",
      "args": ["/abs/path/to/lsp-mcp/server.py"],
      "env": {
        "PROJECT_ROOT": "/abs/path/to/your/project"
      }
    }
  }
}
```

---

## CLAUDE.md snippet (for consuming projects)

```markdown
## Code navigation

LSP tools are available via the `lsp-tools` MCP server.
Use them in this order before reading files:

1. `get_signature` — understand a symbol's type before reading its file
2. `get_call_hierarchy` — decide which related files are worth reading
3. `find_definition` — locate a symbol across files
4. `find_references` — find all usages before making a change
5. `read_file` — only after you know exactly which file and lines matter

Do not read entire files speculatively. Prefer LSP tools for navigation.
```

---

## Dependencies

```
mcp>=1.0.0
anyio>=4.0.0
```

No other runtime dependencies. LSP binaries are external prerequisites.

---

## Out of scope for v1

- Semantic / LSP-based chunking for RAG
- Workspace-wide symbol search (`workspace/symbol`)
- Rename / code action tools
- Diagnostics / lint error forwarding
- File watching / `didChange` notifications
