# codebase-context

> A self-contained, locally-running context management tool for Claude Code agents.
> Provides every agent session with on-demand semantic code retrieval and cross-session
> narrative memory via a single MCP server — no external APIs, no Docker, no shared infrastructure.

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

This detects your install method (uv, pipx, or pip), upgrades to the latest version
from GitHub, and removes any stale MCP entries (e.g. the old `memgram` server) from
`.claude/settings.json` automatically.

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
- Prompt to install a git post-commit hook for auto-reindexing
- Register the MCP server in `.claude/settings.json`
- Append the session protocol to `CLAUDE.md`

> **First run note:** Downloads the Jina embedding model (~200MB ONNX) to `~/.cache/fastembed/`.
> No GPU or CUDA packages required. Subsequent runs use the cached model.

## MCP Server Setup

`ccindex init` registers the MCP server automatically. To add it manually, edit
`.claude/settings.json` (per-project) or `~/.claude/settings.json` (global):

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

A single `ccindex serve` process now hosts all 11 MCP tools — code search, repo map,
narrative memory, and agent coordination.

## MCP Tools Available to Agents

### Code Search (Layer 1)

| Tool | Description |
|------|-------------|
| `search_codebase` | Semantic search — find functions, classes, methods by natural language |
| `get_symbol` | Exact lookup by symbol name (case-sensitive) |
| `get_repo_map` | Full repo map — all files, classes, function signatures (~8k tokens, call sparingly) |

### Narrative Memory (Layer 3a) — cross-session

| Tool | Description |
|------|-------------|
| `narrative_save` | Save a cross-session observation (finding, decision, bugfix, handoff) |
| `narrative_context` | Load the most recent memories at session start |
| `narrative_search` | Full-text search over saved memories, optionally filtered by type |
| `narrative_session_end` | Record a session-end summary |

### Agent Coordination (Layer 3b) — same-session

| Tool | Description |
|------|-------------|
| `coord_store_event` | Record an agent event (task_started, decision, error, …) |
| `coord_recall_events` | Search events by content, agent, or type |
| `coord_record_manifest` | Record which files a task changed |
| `coord_get_manifest` | Retrieve the change manifest for a task |

## Session Protocol

Add this to your project's `CLAUDE.md` (or let `ccindex init` do it automatically):

```markdown
## Session Protocol

**At the start of every session:**
1. Run `git pull`.
2. Call `narrative_context` (ccindex MCP) to load prior memories for this project.
3. Read `CONVENTIONS.md`.

**During every session:**
- After each significant finding, bugfix, or decision: call `narrative_save`.

**After every completed feature or fix:**
1. Call `narrative_save` summarising what was completed (`type: handoff`).
2. Call `narrative_session_end` with a one-line summary.
```

## Agent Navigation Guide

Agents should use this order when exploring the codebase:

1. **`search_codebase` / `get_symbol`** — for targeted queries: finding a symbol, concept search, locating a utility. ~50–500 tokens per call.
2. **`get_repo_map`** — only when you need a full structural overview: new file placement, architecture questions, cross-cutting changes. ~8k tokens — call sparingly.
3. **`Grep` tool** — for content patterns in any file, including languages not in the index.
4. **`Glob` tool** — for finding files by name pattern (e.g. `**/*.sh`).
5. **`Read`** — only after you have located the right file via one of the above.

## CLI Reference

```
ccindex init            Full index of current project
ccindex update          Incremental index (changed files only)
ccindex upgrade         Upgrade to latest version; clean up stale MCP settings
ccindex version         Show installed version and check for updates
ccindex watch           Real-time file watcher
ccindex search <query>  Semantic search from terminal
  --top-k N             Number of results (default: 5)
  --language LANG       Filter by language (python/typescript/javascript/c/cpp)
  --json                Output raw JSON
ccindex map             Print repo map to stdout
ccindex stats           Show index statistics
ccindex clear           Delete index and repo map (--confirm required)
ccindex doctor          Check binaries and re-register MCP server if missing
ccindex install-hook    Install git post-commit hook
ccindex uninstall-hook  Remove git post-commit hook
ccindex serve           Start MCP server (code search + narrative memory + coordination)
ccindex migrate         Migrate HANDOFF.md / DECISIONS.md into narrative memory store
ccindex release         Bump version, tag, push, create GitHub Release
```

> **`ccindex mem-serve` is deprecated.** Narrative memory tools are now served by
> `ccindex serve`. Run `ccindex upgrade` to clean up your project settings.

## Adding New Languages

1. Install the tree-sitter grammar: `pip install tree-sitter-go`
2. Add an entry to `LANGUAGES` in `codebase_context/config.py`
3. Run `ccindex update`

No other code changes required.

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

`.claude/settings.json` and `CLAUDE.md` are committed to the repo.
Each teammate just needs to:

```bash
# Pick whichever method suits them (see Install section above)
uv tool install git+https://github.com/joe8628/codebase-context
export PATH="$HOME/.local/bin:$PATH"   # if not already on PATH

ccindex init   # builds their local index (~30s for typical codebases)
```
