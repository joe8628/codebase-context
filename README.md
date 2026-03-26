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

# Make sure ~/.local/bin is on your PATH (add to ~/.bashrc or ~/.zshrc):
export PATH="$HOME/.local/bin:$PATH"
```

**pipx (same idea, pip-compatible):**
```bash
pipx install git+https://github.com/joe8628/codebase-context

# Make sure ~/.local/bin is on your PATH (add to ~/.bashrc or ~/.zshrc):
export PATH="$HOME/.local/bin:$PATH"
```

**Manual virtualenv:**
```bash
python3 -m venv ~/.venvs/codebase-context
~/.venvs/codebase-context/bin/pip install git+https://github.com/joe8628/codebase-context
# Add to PATH (put in ~/.bashrc or ~/.zshrc):
export PATH="$HOME/.venvs/codebase-context/bin:$PATH"
```

> **Docker / fresh containers:** PATH is not automatically updated after install. Always
> add the export line above to your `~/.bashrc`, run `source ~/.bashrc`, or prepend the
> full binary path (e.g. `~/.local/bin/ccindex`) until the session is reloaded.

### Installing in an isolated environment (GitHub access only, no PyPI)

If your environment can reach GitHub but not PyPI, build a self-contained wheel bundle
on a machine with full internet access, then copy it across:

```bash
# --- On a machine WITH full internet access ---
git clone https://github.com/joe8628/codebase-context
cd codebase-context

# Download the package + all dependencies as wheel files
pip download . -d ./dist/wheels/

# Bundle the wheels directory and transfer it (scp, rsync, Docker COPY, etc.)
tar czf ccindex-bundle.tar.gz dist/wheels/
```

```bash
# --- On the isolated machine ---
tar xzf ccindex-bundle.tar.gz

# Install everything offline (no network required)
pip install --no-index --find-links dist/wheels/ codebase-context

# Or with uv:
uv pip install --no-index --find-links dist/wheels/ codebase-context
```

> **Embedding model:** The Jina model (~200MB) is downloaded at first use from
> HuggingFace. In a fully offline environment, pre-seed the cache by copying
> `~/.cache/fastembed/` from the bundle machine, or set `FASTEMBED_CACHE_PATH`
> to point at a local copy.

## Upgrading

```bash
ccindex upgrade
```

This detects your install method (uv, pipx, or pip) and upgrades to the latest
version from GitHub automatically.

## Quick Start

```bash
cd my-project
ccindex init
```

This will:
- Parse all `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.c`, `.h`, `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` files with Tree-sitter
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

`ccindex init` adds the MCP server entry automatically. If you need to add it
manually, add it to `.claude/settings.json` (per-project) or
`~/.claude/settings.json` (global):

```json
{
  "mcpServers": {
    "codebase-context": {
      "command": "ccindex",
      "args": ["serve"],
      "type": "stdio"
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
ccindex upgrade         Upgrade codebase-context to latest version from GitHub
ccindex watch           Real-time file watcher
ccindex search <query>  Semantic search from terminal
  --top-k N             Number of results (default: 5)
  --language LANG       Filter by language (python/typescript/javascript/c/cpp)
  --json                Output raw JSON
ccindex map             Print repo map to stdout
ccindex stats           Show index statistics
ccindex clear           Delete index and repo map (--confirm required)
ccindex doctor          Check binaries and MCP setup
ccindex install-hook    Install git post-commit hook
ccindex uninstall-hook  Remove git post-commit hook
ccindex serve           Start MCP server (used by Claude Code)
ccindex mem-serve       Start memgram memory MCP server (used by Claude Code)
ccindex migrate         Migrate HANDOFF.md / DECISIONS.md into memgram
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
| `.js`, `.jsx` | JavaScript | functions, classes, methods |
| `.c`, `.h` | C         | functions, structs |
| `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` | C++ | functions, classes, structs, methods |

## Per-Teammate Setup

The `.claude/mcp.json` and updated `CLAUDE.md` are committed to the repo.
Each teammate just needs to:

```bash
# Pick whichever method suits them (see Install section above)
uv tool install git+https://github.com/joe8628/codebase-context
export PATH="$HOME/.local/bin:$PATH"   # if not already on PATH

ccindex init   # builds their local index (~30s for typical codebases)
```
