# codebase-context

> A self-contained, locally-running context management tool for Claude Code agents.
> Provides every agent session with a live repo map and on-demand semantic code retrieval
> via an MCP server — no external APIs, no Docker, no shared infrastructure.

## Install

Modern Linux distros (Ubuntu 23.04+, Debian 12+) protect the system Python.
Use one of these methods:

**Recommended — uv (fastest, handles everything automatically):**
```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install codebase-context into an isolated environment, ccindex goes on PATH
uv tool install git+https://github.com/joe8628/codebase-context
```

**pipx (same idea, pip-compatible):**
```bash
pipx install git+https://github.com/joe8628/codebase-context
```

**Manual virtualenv:**
```bash
python3 -m venv ~/.venvs/codebase-context
~/.venvs/codebase-context/bin/pip install git+https://github.com/joe8628/codebase-context
# Add to PATH (put in ~/.bashrc or ~/.zshrc):
export PATH="$HOME/.venvs/codebase-context/bin:$PATH"
```

## Quick Start

```bash
cd my-project
ccindex init
```

This will:
- Parse all `.py`, `.ts`, `.tsx` files with Tree-sitter
- Build a local vector index in `.codebase-context/chroma/`
- Generate `.codebase-context/repo_map.md`
- Add `.codebase-context/` entries to `.gitignore`
- Prompt to add `@.codebase-context/repo_map.md` to `CLAUDE.md`
- Prompt to install a git post-commit hook for auto-reindexing

> **First run note:** Downloads the Jina embedding model (~200MB ONNX) to `~/.cache/fastembed/`.
> No GPU or CUDA packages required. Subsequent runs use the cached model.

## CLAUDE.md Setup

Add one line to your project's `CLAUDE.md`:

```markdown
@.codebase-context/repo_map.md
```

Every Claude Code session will then start with the full repo map in context.

## MCP Server Setup

Add to `.claude/mcp.json` (per-project) or `~/.claude/mcp.json` (global):

```json
{
  "mcpServers": {
    "codebase-context": {
      "command": "ccindex",
      "args": ["serve"]
    }
  }
}
```

## MCP Tools Available to Agents

| Tool | Description |
|------|-------------|
| `search_codebase` | Semantic search — find functions, classes, methods by natural language |
| `get_symbol` | Exact lookup by symbol name (case-sensitive) |
| `get_repo_map` | Get fresh repo map mid-session |

## CLI Reference

```
ccindex init            Full index of current project
ccindex update          Incremental index (changed files only)
ccindex watch           Real-time file watcher
ccindex search <query>  Semantic search from terminal
  --top-k N             Number of results (default: 5)
  --language LANG       Filter by language (python/typescript)
  --json                Output raw JSON
ccindex map             Print repo map to stdout
ccindex stats           Show index statistics
ccindex clear           Delete index and repo map (--confirm required)
ccindex install-hook    Install git post-commit hook
ccindex uninstall-hook  Remove git post-commit hook
ccindex serve           Start MCP server (used by Claude Code)
```

## Adding New Languages

1. Install the tree-sitter grammar: `pip install tree-sitter-go`
2. Add an entry to `LANGUAGES` in `codebase_context/config.py`
3. Run `ccindex update`

No other code changes required. See `CODEBASE_CONTEXT.md` for the full spec.

## Supported Languages

| Extension | Language   | Symbols Extracted |
|-----------|------------|-------------------|
| `.py`     | Python     | functions, classes, methods |
| `.ts`     | TypeScript | functions, classes, methods, interfaces, type aliases |
| `.tsx`    | TSX        | functions, classes, methods, React components |

## Per-Teammate Setup

The `.claude/mcp.json` and updated `CLAUDE.md` are committed to the repo.
Each teammate just needs to:

```bash
pip install git+https://github.com/joe8628/codebase-context
ccindex init   # builds their local index (~30s for typical codebases)
```
