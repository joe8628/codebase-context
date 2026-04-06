# codebase-context

> A self-contained, locally-running context management tool for Claude Code agents.  
> Provides every agent session with a live repo map and on-demand semantic code retrieval
> via an MCP server — no external APIs, no Docker, no shared infrastructure.

---

## Table of Contents

1. [Overview](#overview)
2. [Design Principles](#design-principles)
3. [Repository Structure](#repository-structure)
4. [Module Specifications](#module-specifications)
5. [Packaging & Installation](#packaging--installation)
6. [CLI Reference](#cli-reference)
7. [MCP Server Specification](#mcp-server-specification)
8. [Claude Code Integration](#claude-code-integration)
9. [Language Configuration](#language-configuration)
10. [Data Flow & Architecture](#data-flow--architecture)
11. [Dependencies](#dependencies)
12. [Testing Requirements](#testing-requirements)
13. [Per-Project Usage](#per-project-usage)

---

## Overview

`codebase-context` is an installable Python package (published to GitHub, installable via pip)
that gives Claude Code agents deep, accurate awareness of any codebase.

It works at two levels:

**Static (always-on):** A compact repo map — every file's classes, functions, and
signatures — is generated with Tree-sitter and written to
`.codebase-context/repo_map.md`. This file is referenced in `CLAUDE.md` so every
agent session starts with full structural awareness.

**Dynamic (on-demand):** An MCP server exposes three tools to Claude Code agents.
The agent calls these tools mid-session to retrieve specific code chunks via semantic
search over a local ChromaDB vector index.

Everything runs locally. Embeddings use `jinaai/jina-embeddings-v2-base-code` via
`sentence-transformers`. No API keys required beyond what the user already has for
Claude itself.

---

## Design Principles

1. **Zero external services.** ChromaDB runs embedded (no server process). Embeddings
   run on-device via sentence-transformers. The only network calls are to pip during
   install.

2. **Per-project isolation.** Each codebase gets its own `.codebase-context/` directory
   containing its index and repo map. Nothing is shared between projects.

3. **Installable once, usable everywhere.** The tool is installed globally (or in a
   shared virtualenv). New projects just run `ccindex init`.

4. **Language extensibility.** Languages are registered in `config.py`. Adding support
   for a new language requires one config entry and installing the corresponding
   `tree-sitter-<lang>` package. No other code changes needed.

5. **Incremental reindexing.** Only files changed since the last index run are
   re-processed. Full reindexes are fast for typical codebases (<30s for 500 files).

6. **Gitignore-aware.** The indexer respects `.gitignore`. Generated files
   (the index, the repo map) are local and should not be committed (except optionally
   `repo_map.md` for team visibility).

---

## Repository Structure

```
codebase-context/
│
├── pyproject.toml                  ← packaging, entry points, dependencies
├── README.md                       ← user-facing docs
├── .gitignore
│
└── codebase_context/
    ├── __init__.py
    ├── config.py                   ← language registry and global settings
    ├── parser.py                   ← Tree-sitter abstraction layer
    ├── chunker.py                  ← semantic code chunking
    ├── embedder.py                 ← sentence-transformers embedding wrapper
    ├── store.py                    ← ChromaDB wrapper
    ├── repo_map.py                 ← repo map generator
    ├── indexer.py                  ← full indexing pipeline orchestrator
    ├── retriever.py                ← query interface
    ├── watcher.py                  ← file watcher + git hook installer
    ├── cli.py                      ← Click CLI (`ccindex` command)
    ├── mcp_server.py               ← MCP server (stdio transport)
    └── utils.py                    ← shared helpers (token counting, gitignore, etc.)
```

---

## Module Specifications

---

### `config.py`

Central configuration. Defines the language registry and global defaults.

```python
# All paths and defaults configurable via environment variables or
# a .codebase-context.toml file in the project root.

# Global defaults
EMBED_MODEL      = "jinaai/jina-embeddings-v2-base-code"
EMBED_BATCH_SIZE = 32
CHROMA_DIR       = ".codebase-context/chroma"
REPO_MAP_PATH    = ".codebase-context/repo_map.md"
INDEX_META_PATH  = ".codebase-context/index_meta.json"
MCP_LOG_PATH     = ".codebase-context/mcp.log"
DEFAULT_TOP_K    = 10
MAX_CHUNK_TOKENS = 512

# Language registry
# Each entry maps a file extension to:
#   - tree_sitter_module: the importable tree-sitter language package
#   - node_types: which AST node types to extract as chunks
#   - name_field: the AST field name that holds the symbol name

LANGUAGES = {
    ".py": {
        "name":               "python",
        "tree_sitter_module": "tree_sitter_python",
        "node_types":         ["function_definition", "class_definition"],
        "method_types":       ["function_definition"],
        "name_field":         "name",
        "comment_prefix":     "#",
    },
    ".ts": {
        "name":               "typescript",
        "tree_sitter_module": "tree_sitter_typescript",
        "tree_sitter_attr":   "language_typescript",  # some packages expose sub-attrs
        "node_types":         [
            "function_declaration",
            "class_declaration",
            "method_definition",
            "arrow_function",      # named via variable_declarator parent
            "interface_declaration",
            "type_alias_declaration",
        ],
        "name_field":   "name",
        "comment_prefix": "//",
    },
    ".tsx": {
        # inherits typescript config, additionally indexes React components
        "name":               "tsx",
        "tree_sitter_module": "tree_sitter_typescript",
        "tree_sitter_attr":   "language_tsx",
        "node_types":         [
            "function_declaration",
            "class_declaration",
            "method_definition",
            "arrow_function",
        ],
        "name_field":   "name",
        "comment_prefix": "//",
    },
    # To add Go support later:
    # ".go": {
    #     "name": "go",
    #     "tree_sitter_module": "tree_sitter_go",
    #     "node_types": ["function_declaration", "method_declaration", "type_declaration"],
    #     "name_field": "name",
    #     "comment_prefix": "//",
    # },
}

# File patterns to always skip (in addition to .gitignore)
ALWAYS_IGNORE = [
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
    "*.min.js", "*.min.css", "*.lock", "*.map",
    ".codebase-context",
]
```

---

### `parser.py`

Tree-sitter abstraction. Handles parsing source code into structured symbol data.
Must handle parse errors gracefully (partial/broken files during agent writes).

**Key data structures:**

```python
@dataclass
class Symbol:
    name:       str
    type:       str          # "function" | "class" | "method" | "interface" | "type"
    start_line: int          # 0-indexed
    end_line:   int          # 0-indexed, inclusive
    source:     str          # full source text of this symbol
    signature:  str          # compact one-line signature for repo map
    docstring:  str | None   # first comment/docstring if present
    calls:      list[str]    # names of functions/methods called within this symbol
    parent:     str | None   # class name if this is a method
    filepath:   str
    language:   str
```

**Key functions:**

```python
def get_parser(extension: str) -> Parser:
    """
    Returns a configured tree-sitter Parser for the given file extension.
    Caches parsers after first construction.
    Raises UnsupportedLanguageError if extension not in LANGUAGES config.
    """

def parse_file(filepath: str) -> list[Symbol]:
    """
    Parses a source file and returns all top-level symbols.
    Returns [] on parse error (logs warning, does not raise).
    Uses the extension to select the right parser from LANGUAGES config.
    For classes: returns the class Symbol AND each method as a child Symbol
    with parent set to the class name.
    For TypeScript arrow functions assigned to variables:
    extracts the variable name from the parent variable_declarator node.
    """

def extract_signature(node, source_bytes: bytes, language_config: dict) -> str:
    """
    Produces a compact one-line signature string.
    Python:     def register(self, email: str, password: str) -> User
    TypeScript: function login(email: string, password: string): Promise<User>
    Class:      class UserService (with method count)
    """

def extract_calls(node, source_bytes: bytes) -> list[str]:
    """
    Finds all call_expression / call nodes within a symbol's subtree.
    Returns unique function/method names called.
    Used to build dependency relationships.
    """
```

---

### `chunker.py`

Converts parsed symbols into indexable chunks. Each chunk is a self-contained
unit that will be stored in the vector DB.

**Key data structures:**

```python
@dataclass
class Chunk:
    id:       str          # deterministic: sha256(filepath + symbol_name + start_line)
    text:     str          # the text to embed (decorated with context prefix)
    metadata: dict         # stored in ChromaDB alongside the vector
    # metadata keys:
    #   filepath, symbol_name, symbol_type, start_line, end_line,
    #   language, parent_class, calls (json-serialized list), docstring
```

**Key functions:**

```python
def build_chunks(symbols: list[Symbol], filepath: str) -> list[Chunk]:
    """
    Converts symbols to chunks.
    
    The `text` field is NOT the raw source — it is a context-enriched version:
    
      # filepath: src/services/user_service.py
      # type: method | class: UserService
      def register(self, email: str, password: str) -> User:
          ...actual source...
    
    This prefix dramatically improves embedding quality by giving the model
    explicit file and structural context.
    
    Chunks exceeding MAX_CHUNK_TOKENS (512) are truncated at the nearest
    logical line boundary. The full source is preserved in metadata regardless.
    """

def chunk_id(filepath: str, symbol_name: str, start_line: int) -> str:
    """
    Deterministic ID for a chunk. Same symbol at same location = same ID.
    Used to detect which chunks need updating on incremental reindex.
    """
```

---

### `embedder.py`

Wraps `sentence-transformers` with the Jina code embedding model.
Handles batching, caching, and lazy model loading (model loads on first use,
not on import).

```python
class Embedder:
    """
    Lazy-loads jinaai/jina-embeddings-v2-base-code on first call.
    Model is cached in ~/.cache/huggingface (standard HF cache).
    Thread-safe: uses a lock around model initialization.
    """
    
    def __init__(self, model_name: str = EMBED_MODEL):
        ...
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embeds a list of texts in batches of EMBED_BATCH_SIZE.
        Returns list of float vectors (dimensionality: 768 for jina-v2-base-code).
        Logs progress for batches > 100 items.
        """
    
    def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for single text."""
```

---

### `store.py`

ChromaDB wrapper. The collection is named after the project (derived from the
absolute path of the project root, slugified).

```python
class VectorStore:
    """
    Wraps a ChromaDB PersistentClient stored at CHROMA_DIR.
    Collection name: slugified project root path.
    """
    
    def __init__(self, project_root: str):
        ...
    
    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """
        Upserts chunks by their deterministic ID.
        Existing chunks with the same ID are overwritten.
        """
    
    def delete_by_filepath(self, filepath: str) -> None:
        """
        Removes all chunks from a given file.
        Called before re-indexing a modified file.
        """
    
    def search(
        self,
        query_embedding: list[float],
        top_k:           int = DEFAULT_TOP_K,
        where:           dict | None = None,
    ) -> list[SearchResult]:
        """
        Nearest-neighbor search.
        `where` supports ChromaDB metadata filter syntax:
          {"language": "python"}
          {"filepath": {"$contains": "auth"}}
        Returns SearchResult(chunk_text, metadata, score) sorted by score desc.
        """
    
    def get_by_symbol_name(self, name: str) -> list[SearchResult]:
        """
        Exact metadata filter: {"symbol_name": name}.
        Used by the get_symbol MCP tool.
        """
    
    def count(self) -> int:
        """Total number of chunks indexed."""
    
    def clear(self) -> None:
        """Deletes and recreates the collection. Used by ccindex clear."""
```

---

### `repo_map.py`

Generates the compact repo map written to `.codebase-context/repo_map.md`.
This is the static context injected into every Claude Code session.

**Format spec:**

```
# Repo Map
# Generated: 2026-03-13T09:14:22  |  Files: 47  |  Symbols: 312
# Reference this in CLAUDE.md with: @.codebase-context/repo_map.md

---

## src/api/auth.py
  class AuthRouter:
    + login(self, email: str, password: str) -> TokenResponse
    + register(self, email: str, password: str) -> User
    + refresh(self, token: str) -> TokenResponse

## src/services/user_service.py
  class UserService:
    + create(self, email: str, password: str) -> User
    + find_by_email(self, email: str) -> Optional[User]
    + delete(self, user_id: int) -> bool

## src/utils/validation.py
  + validate_email(email: str) -> str
  + validate_password(password: str) -> bool

## src/models/user.py
  class User:
    fields: id, email, password_hash, created_at, updated_at
```

**Rules:**
- Files with no extractable symbols are omitted from the map
- Methods are indented under their class with `+` prefix
- Module-level functions use `+` at file level
- Classes with no methods show their field names if detectable
- TypeScript interfaces and type aliases are included
- The header shows generation timestamp, file count, symbol count
- Files are sorted: by directory depth first, then alphabetically
- Total token budget target: under 4,000 tokens for a 500-file codebase

```python
def generate_repo_map(project_root: str, symbols_by_file: dict[str, list[Symbol]]) -> str:
    """Generates the full repo map string."""

def write_repo_map(project_root: str, repo_map: str) -> None:
    """Writes to REPO_MAP_PATH, creating .codebase-context/ dir if needed."""

def estimate_tokens(text: str) -> int:
    """Rough token estimate: len(text) / 4. Used to warn if map exceeds 8k tokens."""
```

---

### `indexer.py`

Orchestrates the full indexing pipeline. This is the main entry point called
by the CLI and watcher.

```python
@dataclass
class IndexMeta:
    """
    Persisted to INDEX_META_PATH as JSON.
    Tracks per-file modification times for incremental indexing.
    """
    last_full_index:  str               # ISO timestamp
    file_mtimes:      dict[str, float]  # filepath -> mtime at last index
    total_chunks:     int
    total_files:      int

class Indexer:
    def __init__(self, project_root: str):
        self.root     = project_root
        self.store    = VectorStore(project_root)
        self.embedder = Embedder()
        self.meta     = load_index_meta(project_root)
    
    def full_index(self, show_progress: bool = True) -> IndexStats:
        """
        Indexes the entire project from scratch.
        Steps:
          1. Discover all source files (respecting .gitignore + ALWAYS_IGNORE)
          2. Parse each file with parser.parse_file()
          3. Build chunks with chunker.build_chunks()
          4. Embed all chunks in batches with embedder.embed()
          5. Upsert all chunks to store
          6. Generate repo map and write to disk
          7. Save index meta (mtimes, counts)
        Shows a progress bar if show_progress=True (using tqdm).
        Returns IndexStats(files_indexed, chunks_created, duration_seconds).
        """
    
    def incremental_index(self, show_progress: bool = True) -> IndexStats:
        """
        Only re-indexes files whose mtime has changed since last index.
        For each changed file:
          1. store.delete_by_filepath(filepath)
          2. Re-parse, re-chunk, re-embed, re-upsert
        Regenerates repo map regardless (cheap operation).
        Updates index meta.
        Returns IndexStats with only changed file counts.
        """
    
    def index_file(self, filepath: str) -> int:
        """
        Index a single file. Returns number of chunks created.
        Used by watcher for real-time updates.
        """
    
    def remove_file(self, filepath: str) -> None:
        """
        Called when a file is deleted.
        Removes all its chunks from the store.
        """

def discover_files(project_root: str) -> list[str]:
    """
    Returns all source files to index.
    Respects:
      - .gitignore (via pathspec library)
      - ALWAYS_IGNORE patterns from config
      - Only includes extensions present in LANGUAGES config
    """
```

---

### `retriever.py`

Clean query interface used by the MCP server and CLI.

```python
@dataclass
class RetrievalResult:
    filepath:    str
    symbol_name: str
    symbol_type: str
    source:      str
    signature:   str
    score:       float
    language:    str
    parent_class: str | None
    start_line:  int
    end_line:    int

class Retriever:
    def __init__(self, project_root: str):
        self.store    = VectorStore(project_root)
        self.embedder = Embedder()
    
    def search(
        self,
        query:    str,
        top_k:    int = DEFAULT_TOP_K,
        language: str | None = None,
        filepath_contains: str | None = None,
    ) -> list[RetrievalResult]:
        """
        Embeds query, searches store, returns ranked results.
        Optional filters:
          language: restrict to "python" or "typescript"
          filepath_contains: fuzzy filepath filter (e.g. "auth", "services/user")
        Results are deduplicated by filepath+symbol_name.
        """
    
    def get_symbol(self, name: str) -> list[RetrievalResult]:
        """
        Exact symbol name lookup. Case-sensitive.
        Returns all matches (a name may exist in multiple files).
        """
    
    def get_repo_map(self, project_root: str) -> str:
        """
        Reads and returns current repo_map.md content.
        Returns a 'not indexed yet' message if file doesn't exist.
        """
```

---

### `watcher.py`

File system watcher for real-time incremental reindexing and git hook management.

```python
def watch(project_root: str) -> None:
    """
    Starts a watchdog FileSystemEventHandler on the project root.
    On file create/modify: calls indexer.index_file(filepath)
    On file delete:        calls indexer.remove_file(filepath)
    On file move:          removes old path, indexes new path
    Debounces rapid changes (e.g. editor save storms): 2 second debounce window.
    Filters events by LANGUAGES extensions and ALWAYS_IGNORE patterns.
    Regenerates repo map after each batch of changes.
    Runs until SIGINT/SIGTERM.
    Logs activity to stdout (timestamp, event type, filepath, chunks affected).
    """

def install_git_hook(project_root: str) -> None:
    """
    Writes a post-commit hook to .git/hooks/post-commit:
    
      #!/bin/sh
      ccindex update
    
    Makes it executable.
    If a post-commit hook already exists, appends the ccindex line
    rather than overwriting.
    Prints confirmation with hook path.
    """

def uninstall_git_hook(project_root: str) -> None:
    """
    Removes the ccindex line from .git/hooks/post-commit.
    If that was the only line, removes the hook file entirely.
    """
```

---

### `mcp_server.py`

MCP server using stdio transport (Claude Code spawns it as a subprocess).
Uses the `mcp` Python SDK (`pip install mcp`).

**Server name:** `codebase-context`

**Tools exposed:**

#### Tool 1: `search_codebase`

```
Name:        search_codebase
Description: Search the codebase using natural language. Returns the most
             semantically relevant functions, classes, and methods.
             Use this when you need to find how something is implemented,
             locate existing utilities, or understand a subsystem.

Parameters:
  query              (string, required)  Natural language search query
  top_k              (integer, optional) Number of results. Default: 10. Max: 25.
  language           (string, optional)  Filter to "python" or "typescript"
  filepath_contains  (string, optional)  Fuzzy filter on filepath

Returns: JSON array of results, each containing:
  - filepath
  - symbol_name
  - symbol_type   ("function" | "class" | "method" | "interface" | "type")
  - signature     (compact one-line)
  - source        (full source of the symbol)
  - score         (0.0 - 1.0 similarity)
  - start_line
  - end_line
  - parent_class  (if method)
```

#### Tool 2: `get_symbol`

```
Name:        get_symbol
Description: Fetch a specific symbol (function, class, method) by exact name.
             Use this to retrieve a known symbol's full implementation.
             Useful for verifying a symbol exists before referencing it,
             or reading an implementation before modifying it.

Parameters:
  name  (string, required)  Exact symbol name (case-sensitive)

Returns: JSON array of all matches (same schema as search_codebase results).
         Empty array if not found.
```

#### Tool 3: `get_repo_map`

```
Name:        get_repo_map
Description: Returns the current repo map — a compact summary of all files,
             classes, and function signatures in the codebase.
             Use this when you need a fresh overview mid-session or when
             the repo map in your context may be outdated after recent changes.

Parameters: none

Returns: string (the full repo_map.md content)
```

**Server implementation notes:**
- Resolves `project_root` from the working directory at server startup (`os.getcwd()`)
- Logs all tool calls and errors to MCP_LOG_PATH
- Returns structured errors (never crashes) if index doesn't exist yet:
  `{"error": "Index not found. Run: ccindex init"}`
- Embedder is loaded once at server startup, not per-request

---

### `cli.py`

Click-based CLI. Entry point is `ccindex`.

```
ccindex init        Full index of current directory. Writes repo map.
                    Creates .codebase-context/ if not present.
                    Adds .codebase-context/ to .gitignore if not present.
                    Prints: files indexed, chunks created, duration.
                    Prompts to install git hook (y/n).

ccindex update      Incremental index (only changed files since last run).
                    Run manually or via git post-commit hook.

ccindex watch       Starts file watcher for real-time reindexing.
                    Runs until Ctrl+C.

ccindex search      Interactive semantic search from the terminal.
  <query>           e.g. ccindex search "email validation"
  --top-k N         Number of results (default: 5)
  --language LANG   Filter by language
  --json            Output raw JSON

ccindex map         Print current repo map to stdout.

ccindex stats       Show index statistics:
                    - Total files indexed
                    - Total chunks
                    - Index size on disk
                    - Last index timestamp
                    - Embedding model in use

ccindex clear       Delete the index and repo map. Requires --confirm flag.

ccindex install-hook    Install git post-commit hook.
ccindex uninstall-hook  Remove git post-commit hook.

ccindex serve       Start the MCP server (used by Claude Code MCP config).
                    This command is what .claude/mcp.json points to.
```

---

### `utils.py`

Shared utilities.

```python
def count_tokens(text: str) -> int:
    """Approximate token count: len(text.split()) * 1.3 (fast heuristic)."""

def slugify(text: str) -> str:
    """Converts arbitrary string to safe collection name."""

def load_gitignore(project_root: str) -> pathspec.PathSpec:
    """Parses .gitignore and returns a pathspec matcher."""

def is_ignored(filepath: str, project_root: str, gitignore: pathspec.PathSpec) -> bool:
    """Returns True if file should be skipped during indexing."""

def find_project_root(start_path: str = ".") -> str:
    """
    Walks up from start_path looking for .git directory.
    Falls back to start_path if no .git found.
    """

def format_results_for_agent(results: list[RetrievalResult]) -> str:
    """
    Formats retrieval results as clean markdown for MCP tool responses.
    Groups by filepath. Shows signatures, line numbers, source.
    """

def load_index_meta(project_root: str) -> IndexMeta:
    """Loads INDEX_META_PATH or returns empty IndexMeta if not found."""

def save_index_meta(project_root: str, meta: IndexMeta) -> None:
    """Persists IndexMeta to INDEX_META_PATH."""
```

---

## Packaging & Installation

### `pyproject.toml`

```toml
[build-system]
requires      = ["hatchling"]
build-backend = "hatchling.build"

[project]
name        = "codebase-context"
version     = "0.1.0"
description = "Tree-sitter + RAG context management for Claude Code agents"
readme      = "README.md"
requires-python = ">=3.11"

dependencies = [
    "click>=8.1",
    "chromadb>=0.5",
    "sentence-transformers>=3.0",
    "tree-sitter>=0.23",
    "tree-sitter-python>=0.23",
    "tree-sitter-typescript>=0.23",
    "watchdog>=4.0",
    "pathspec>=0.12",
    "tqdm>=4.66",
    "mcp>=1.0",
]

[project.scripts]
ccindex = "codebase_context.cli:cli"

[tool.hatch.build.targets.wheel]
packages = ["codebase_context"]
```

### Installation

**From GitHub (recommended):**
```bash
pip install git+https://github.com/yourusername/codebase-context
```

**For development:**
```bash
git clone https://github.com/yourusername/codebase-context
cd codebase-context
pip install -e ".[dev]"
```

**With uv (faster):**
```bash
uv pip install git+https://github.com/yourusername/codebase-context
```

---

## CLI Reference

```
$ ccindex --help

Usage: ccindex [OPTIONS] COMMAND [ARGS]...

  codebase-context — Tree-sitter + RAG for Claude Code agents

Options:
  --root PATH  Project root (default: nearest .git directory or cwd)
  --help       Show this message and exit.

Commands:
  init            Full index of current project
  update          Incremental index (changed files only)
  watch           Real-time file watcher
  search          Semantic search from terminal
  map             Print repo map to stdout
  stats           Show index statistics
  clear           Delete index and repo map
  install-hook    Install git post-commit hook
  uninstall-hook  Remove git post-commit hook
  serve           Start MCP server (used by Claude Code)
```

---

## MCP Server Specification

### Transport

Stdio (standard input/output). Claude Code spawns the server as a subprocess
and communicates over stdin/stdout. Errors and logs go to MCP_LOG_PATH (not stderr,
to avoid corrupting the stdio MCP protocol).

### Configuration in Claude Code

**Option A — Global** (`~/.claude/mcp.json`, applies to all projects):
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

**Option B — Per-project** (`.claude/mcp.json`, committed to repo):
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

Both options work. The server resolves `project_root` from `os.getcwd()` at startup,
which Claude Code sets to the workspace root.

### Error Handling

All tools return valid JSON even on error. Error responses:

```json
{
  "error": "Index not found. Run: ccindex init",
  "results": []
}
```

Never raise unhandled exceptions (would crash the MCP server and break the agent session).

---

## Claude Code Integration

### CLAUDE.md Setup

After running `ccindex init`, the user adds one line to their project's `CLAUDE.md`:

```markdown
# Project Context

@.codebase-context/repo_map.md

<!-- rest of CLAUDE.md instructions -->
```

`ccindex init` prints this instruction and optionally appends it automatically
(prompt the user: "Add repo map reference to CLAUDE.md? [y/N]").

### What the Agent Sees at Session Start

Every Claude Code session automatically begins with the full repo map inlined
into context. Example:

```
# Repo Map
# Generated: 2026-03-13T09:14:22  |  Files: 47  |  Symbols: 312

---

## src/api/auth.py
  class AuthRouter:
    + login(self, email: str, password: str) -> TokenResponse
    + register(self, email: str, password: str) -> User
    + refresh(self, token: str) -> TokenResponse

## src/services/user_service.py
  class UserService:
    + create(self, email: str, password: str) -> User
    + find_by_email(self, email: str) -> Optional[User]
    ...
```

### What the Agent Can Do During a Session

```
# Find relevant code for a task
search_codebase("rate limiting middleware")

# Verify a symbol exists before referencing it
get_symbol("validate_email")

# Get a fresh overview if context is stale
get_repo_map()
```

### .gitignore Additions

`ccindex init` appends to `.gitignore` if not already present:

```gitignore
# codebase-context
.codebase-context/chroma/
.codebase-context/index_meta.json
.codebase-context/mcp.log
# optionally commit repo_map.md for team visibility:
# .codebase-context/repo_map.md
```

---

## Language Configuration

### Adding a New Language

1. Install the tree-sitter grammar:
   ```bash
   pip install tree-sitter-go
   ```

2. Add an entry to `LANGUAGES` in `config.py`:
   ```python
   ".go": {
       "name":               "go",
       "tree_sitter_module": "tree_sitter_go",
       "node_types":         ["function_declaration", "method_declaration", "type_declaration"],
       "name_field":         "name",
       "comment_prefix":     "//",
   }
   ```

3. Run `ccindex update` to index the new file types.

No other code changes required.

### Currently Supported

| Extension | Language   | Symbols Extracted |
|-----------|------------|-------------------|
| `.py`     | Python     | functions, classes, methods |
| `.ts`     | TypeScript | functions, classes, methods, interfaces, type aliases |
| `.tsx`    | TSX        | functions, classes, methods, React components |

---

## Data Flow & Architecture

### Indexing Pipeline

```
Source Files (.py, .ts, .tsx)
       │
       ▼
  utils.discover_files()          ← gitignore-aware file discovery
       │
       ▼
  parser.parse_file()             ← Tree-sitter → list[Symbol]
       │
       ▼
  chunker.build_chunks()          ← Symbol → Chunk (with context prefix)
       │
       ▼
  embedder.embed()                ← Chunk.text → vector[768]
       │
       ▼
  store.upsert()                  ← (chunk, vector) → ChromaDB
       │
       ▼
  repo_map.generate_repo_map()    ← Symbol signatures → .md file
       │
       ▼
  utils.save_index_meta()         ← file mtimes → JSON
```

### Retrieval Pipeline

```
Agent query: "rate limiting middleware"
       │
       ▼
  embedder.embed_one(query)       ← query → vector[768]
       │
       ▼
  store.search(vector, top_k=10)  ← nearest-neighbor search in ChromaDB
       │
       ▼
  utils.format_results_for_agent()  ← SearchResult[] → markdown string
       │
       ▼
  MCP tool response               ← returned to Claude Code agent
```

### File Change Flow (Watcher)

```
File saved by agent or developer
       │
       ▼
  watchdog event                  ← filesystem event
       │
       ▼
  2s debounce                     ← batch rapid saves
       │
       ▼
  store.delete_by_filepath()      ← remove old chunks
       │
       ▼
  indexer.index_file()            ← parse → chunk → embed → upsert
       │
       ▼
  repo_map.write_repo_map()       ← regenerate repo map
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `click` | >=8.1 | CLI framework |
| `chromadb` | >=0.5 | Embedded vector database |
| `sentence-transformers` | >=3.0 | Local embeddings |
| `tree-sitter` | >=0.23 | Code parsing core |
| `tree-sitter-python` | >=0.23 | Python grammar |
| `tree-sitter-typescript` | >=0.23 | TypeScript + TSX grammar |
| `watchdog` | >=4.0 | Filesystem events |
| `pathspec` | >=0.12 | .gitignore parsing |
| `tqdm` | >=4.66 | Progress bars |
| `mcp` | >=1.0 | MCP server SDK |

**Embedding model** (downloaded on first use, ~550MB):
`jinaai/jina-embeddings-v2-base-code` via HuggingFace Hub  
Dimensionality: 768 | Context window: 8192 tokens | License: Apache 2.0

**Note on first run:** The first `ccindex init` will download the embedding model
from HuggingFace (~550MB). Subsequent runs use the cached model from
`~/.cache/huggingface/`. Print a clear message to the user when this download
begins so they are not confused by the delay.

---

## Testing Requirements

Tests live in `tests/` and use `pytest`.

### Required test coverage

**`tests/test_parser.py`**
- Parse a Python file with classes, methods, and module-level functions
- Parse a TypeScript file with interfaces and arrow functions
- Handle a file with syntax errors (should return [] not raise)
- Verify signature extraction format for each language

**`tests/test_chunker.py`**
- Verify context prefix is added to chunk text
- Verify chunk ID is deterministic
- Verify long chunks are truncated at MAX_CHUNK_TOKENS

**`tests/test_repo_map.py`**
- Verify map format (indentation, `+` prefix, class grouping)
- Verify token estimate stays under target for typical codebase size

**`tests/test_indexer.py`**
- Full index on a small fixture project (5 files)
- Incremental index only processes changed files
- Adding and removing a file updates the index correctly

**`tests/test_retriever.py`**
- search() returns relevant results for a known query
- get_symbol() finds a symbol by exact name
- get_symbol() returns [] for unknown names
- Language filter works correctly

**`tests/fixtures/`**
- `sample_project/` — small Python + TypeScript project for integration tests
  - `src/api/auth.py` — class with methods, type annotations
  - `src/utils/validation.py` — module-level functions
  - `src/types/user.ts` — TypeScript interface + type alias
  - `src/services/auth.ts` — TypeScript class with methods

---

## Per-Project Usage

### First Time Setup (any new project)

```bash
# 1. Install the tool (once per machine)
pip install git+https://github.com/yourusername/codebase-context

# 2. Navigate to your project
cd my-project

# 3. Initialize the index
ccindex init
# → Downloads embedding model on first run (~550MB, one time only)
# → Parses all .py, .ts, .tsx files
# → Builds vector index in .codebase-context/chroma/
# → Generates .codebase-context/repo_map.md
# → Adds .codebase-context/ to .gitignore
# → Prompts to add @.codebase-context/repo_map.md to CLAUDE.md
# → Prompts to install git post-commit hook

# 4. Add to CLAUDE.md (if not done automatically)
echo "@.codebase-context/repo_map.md" >> CLAUDE.md

# 5. Add MCP config (for Claude Code tool access)
mkdir -p .claude
cat > .claude/mcp.json << 'EOF'
{
  "mcpServers": {
    "codebase-context": {
      "command": "ccindex",
      "args": ["serve"]
    }
  }
}
EOF

# Done. Open Claude Code — agents now have full context.
```

### Day-to-Day

The git hook handles reindexing automatically on each commit.
For real-time reindexing during active development, run in a separate terminal:

```bash
ccindex watch
```

### Teammate Onboarding

```bash
git clone <repo>
cd <repo>
pip install git+https://github.com/yourusername/codebase-context
ccindex init      # builds a fresh local index for their machine
```

The `.claude/mcp.json` and updated `CLAUDE.md` are already committed.
They just need to run `ccindex init` to build their local index.
