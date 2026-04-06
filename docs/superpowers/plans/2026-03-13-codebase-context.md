# codebase-context Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained, locally-running context management package (`codebase-context`) that gives Claude Code agents deep codebase awareness via a static repo map and dynamic semantic search over a local ChromaDB vector index.

**Architecture:** A Python package with a Tree-sitter parsing layer, sentence-transformers embeddings, and ChromaDB vector storage — all running locally. A Click CLI (`ccindex`) drives indexing; an MCP server exposes three tools to Claude Code agents over stdio.

**Tech Stack:** Python ≥3.11, tree-sitter ≥0.23, sentence-transformers ≥3.0, chromadb ≥0.5, click ≥8.1, watchdog ≥4.0, pathspec ≥0.12, tqdm ≥4.66, mcp ≥1.0, pytest

---

## Implementation Order

Modules are implemented in dependency order:
1. Packaging (`pyproject.toml`, `__init__.py`)
2. `config.py` — no deps
3. `utils.py` — deps: config
4. `parser.py` — deps: config
5. `chunker.py` — deps: parser, config
6. `embedder.py` — deps: config
7. `store.py` — deps: chunker, config
8. `repo_map.py` — deps: parser, config
9. `indexer.py` — deps: all above + utils
10. `retriever.py` — deps: store, embedder, config
11. `watcher.py` — deps: indexer
12. `cli.py` — deps: indexer, retriever, watcher, utils
13. `mcp_server.py` — deps: retriever, indexer
14. Tests fixtures + integration tests

---

## Chunk 1: Project Scaffolding

### Task 1: pyproject.toml and package skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `codebase_context/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Create pyproject.toml**

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

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]

[project.scripts]
ccindex = "codebase_context.cli:cli"

[tool.hatch.build.targets.wheel]
packages = ["codebase_context"]
```

- [ ] **Step 2: Create package skeleton**

```python
# codebase_context/__init__.py
"""codebase-context: Tree-sitter + RAG context management for Claude Code agents."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Create .gitignore**

```gitignore
__pycache__/
*.pyc
*.pyo
.venv/
venv/
dist/
build/
*.egg-info/
.pytest_cache/
.coverage
htmlcov/

# codebase-context generated files
.codebase-context/chroma/
.codebase-context/index_meta.json
.codebase-context/mcp.log
```

- [ ] **Step 4: Verify install works**

```bash
pip install -e ".[dev]"
python -c "import codebase_context; print(codebase_context.__version__)"
```
Expected: `0.1.0`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml codebase_context/__init__.py .gitignore
git commit -m "feat: initial package scaffold"
```

---

## Chunk 2: config.py

### Task 2: Language registry and global defaults

**Files:**
- Create: `codebase_context/config.py`

No test needed (pure config data — tested implicitly through other modules).

- [ ] **Step 1: Create config.py**

```python
# codebase_context/config.py
"""Central configuration: language registry and global defaults."""

import os

# ---------------------------------------------------------------------------
# Global defaults (override via environment variables)
# ---------------------------------------------------------------------------

EMBED_MODEL      = os.environ.get("CC_EMBED_MODEL", "jinaai/jina-embeddings-v2-base-code")
EMBED_BATCH_SIZE = int(os.environ.get("CC_EMBED_BATCH_SIZE", "32"))
CHROMA_DIR       = os.environ.get("CC_CHROMA_DIR", ".codebase-context/chroma")
REPO_MAP_PATH    = os.environ.get("CC_REPO_MAP_PATH", ".codebase-context/repo_map.md")
INDEX_META_PATH  = os.environ.get("CC_INDEX_META_PATH", ".codebase-context/index_meta.json")
MCP_LOG_PATH     = os.environ.get("CC_MCP_LOG_PATH", ".codebase-context/mcp.log")
DEFAULT_TOP_K    = int(os.environ.get("CC_DEFAULT_TOP_K", "10"))
MAX_CHUNK_TOKENS = int(os.environ.get("CC_MAX_CHUNK_TOKENS", "512"))

# ---------------------------------------------------------------------------
# Language registry
# ---------------------------------------------------------------------------

LANGUAGES: dict[str, dict] = {
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
        "tree_sitter_attr":   "language_typescript",
        "node_types":         [
            "function_declaration",
            "class_declaration",
            "method_definition",
            "arrow_function",
            "interface_declaration",
            "type_alias_declaration",
        ],
        "name_field":   "name",
        "comment_prefix": "//",
    },
    ".tsx": {
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
}

# ---------------------------------------------------------------------------
# Patterns always skipped during indexing (in addition to .gitignore)
# ---------------------------------------------------------------------------

ALWAYS_IGNORE: list[str] = [
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
    "*.min.js", "*.min.css", "*.lock", "*.map",
    ".codebase-context",
]
```

- [ ] **Step 2: Verify import**

```bash
python -c "from codebase_context.config import LANGUAGES, EMBED_MODEL; print(list(LANGUAGES.keys()))"
```
Expected: `['.py', '.ts', '.tsx']`

- [ ] **Step 3: Commit**

```bash
git add codebase_context/config.py
git commit -m "feat: add config module with language registry"
```

---

## Chunk 3: utils.py

### Task 3: Shared utilities

**Files:**
- Create: `codebase_context/utils.py`
- Create: `tests/__init__.py`
- Create: `tests/test_utils.py`

- [ ] **Step 1: Write failing tests first**

```python
# tests/test_utils.py
import os
import tempfile
import pytest
from codebase_context.utils import (
    count_tokens, slugify, load_gitignore, is_ignored, find_project_root
)


def test_count_tokens_basic():
    assert count_tokens("hello world") == pytest.approx(2 * 1.3, abs=1)


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_slugify_basic():
    result = slugify("/home/user/my-project")
    assert "-" not in result or result.replace("-", "").isalnum()
    assert "/" not in result
    assert " " not in result


def test_slugify_safe_for_chroma():
    # ChromaDB collection names: 3-63 chars, alphanumeric + hyphens
    result = slugify("/very/long/path/to/some/project/directory/that/is/deeply/nested")
    assert len(result) <= 63
    assert len(result) >= 3


def test_find_project_root_with_git(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    subdir = tmp_path / "src" / "api"
    subdir.mkdir(parents=True)
    result = find_project_root(str(subdir))
    assert result == str(tmp_path)


def test_find_project_root_no_git(tmp_path):
    result = find_project_root(str(tmp_path))
    assert result == str(tmp_path)


def test_load_gitignore_parses(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\nnode_modules/\n")
    spec = load_gitignore(str(tmp_path))
    assert spec is not None


def test_is_ignored_gitignore(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n")
    spec = load_gitignore(str(tmp_path))
    ignored_file = str(tmp_path / "foo.pyc")
    not_ignored = str(tmp_path / "foo.py")
    assert is_ignored(ignored_file, str(tmp_path), spec)
    assert not is_ignored(not_ignored, str(tmp_path), spec)


def test_is_ignored_always_ignore(tmp_path):
    spec = load_gitignore(str(tmp_path))
    node_modules_file = str(tmp_path / "node_modules" / "lodash" / "index.js")
    assert is_ignored(node_modules_file, str(tmp_path), spec)
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_utils.py -v
```
Expected: All FAIL (ImportError or similar)

- [ ] **Step 3: Create utils.py**

```python
# codebase_context/utils.py
"""Shared utilities: token counting, gitignore handling, path helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pathspec

from codebase_context.config import ALWAYS_IGNORE, INDEX_META_PATH


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Approximate token count: word count × 1.3 (fast heuristic)."""
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """
    Converts an arbitrary string (e.g. absolute path) to a safe ChromaDB
    collection name: alphanumeric + hyphens, 3–63 chars.
    """
    # Replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-zA-Z0-9]", "-", text)
    # Collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug).strip("-")
    # Ensure it fits in 63 chars (ChromaDB limit) using a hash suffix if needed
    if len(slug) > 63:
        hash_suffix = hashlib.sha256(text.encode()).hexdigest()[:8]
        slug = slug[:54] + "-" + hash_suffix
    # Ensure minimum 3 chars
    if len(slug) < 3:
        slug = slug + "xxx"
    return slug.lower()


# ---------------------------------------------------------------------------
# Gitignore / file filtering
# ---------------------------------------------------------------------------

def load_gitignore(project_root: str) -> pathspec.PathSpec:
    """Parses .gitignore and returns a pathspec matcher."""
    gitignore_path = Path(project_root) / ".gitignore"
    if gitignore_path.exists():
        lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def is_ignored(filepath: str, project_root: str, gitignore: pathspec.PathSpec) -> bool:
    """Returns True if this file should be skipped during indexing."""
    try:
        rel = os.path.relpath(filepath, project_root)
    except ValueError:
        return True

    # Check gitignore
    if gitignore.match_file(rel):
        return True

    # Check ALWAYS_IGNORE patterns against each path component
    parts = Path(rel).parts
    for pattern in ALWAYS_IGNORE:
        if "*" in pattern:
            # Glob-style: match against filename
            import fnmatch
            if fnmatch.fnmatch(Path(filepath).name, pattern):
                return True
        else:
            # Directory/prefix match: check any component
            if pattern in parts:
                return True

    return False


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------

def find_project_root(start_path: str = ".") -> str:
    """
    Walks up from start_path looking for a .git directory.
    Falls back to start_path if no .git found.
    """
    current = Path(start_path).resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return str(parent)
    return str(current)


# ---------------------------------------------------------------------------
# Index metadata persistence
# ---------------------------------------------------------------------------

def load_index_meta(project_root: str) -> "IndexMeta":  # type: ignore[name-defined]
    """Loads INDEX_META_PATH or returns an empty IndexMeta if not found."""
    # Import here to avoid circular import (IndexMeta is defined in indexer)
    from codebase_context.indexer import IndexMeta

    meta_path = Path(project_root) / INDEX_META_PATH
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return IndexMeta(**data)
    return IndexMeta(
        last_full_index="",
        file_mtimes={},
        total_chunks=0,
        total_files=0,
    )


def save_index_meta(project_root: str, meta: "IndexMeta") -> None:  # type: ignore[name-defined]
    """Persists IndexMeta to INDEX_META_PATH."""
    meta_path = Path(project_root) / INDEX_META_PATH
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "last_full_index": meta.last_full_index,
                "file_mtimes":     meta.file_mtimes,
                "total_chunks":    meta.total_chunks,
                "total_files":     meta.total_files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Result formatting
# ---------------------------------------------------------------------------

def format_results_for_agent(results: list) -> str:
    """
    Formats retrieval results as clean markdown for MCP tool responses.
    Groups by filepath. Shows signatures, line numbers, source.
    """
    if not results:
        return "_No results found._"

    from collections import defaultdict

    by_file: dict[str, list] = defaultdict(list)
    for r in results:
        by_file[r.filepath].append(r)

    lines: list[str] = []
    for filepath, file_results in sorted(by_file.items()):
        lines.append(f"## {filepath}")
        for r in file_results:
            header = f"### `{r.symbol_name}`"
            if r.parent_class:
                header += f" (in `{r.parent_class}`)"
            lines.append(header)
            lines.append(f"- **Type:** {r.symbol_type}")
            lines.append(f"- **Lines:** {r.start_line + 1}–{r.end_line + 1}")
            lines.append(f"- **Score:** {r.score:.3f}")
            lines.append(f"- **Signature:** `{r.signature}`")
            lines.append("")
            lines.append("```")
            lines.append(r.source)
            lines.append("```")
            lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Create tests/__init__.py**

```python
# tests/__init__.py
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_utils.py -v
```
Expected: All PASS (except load_index_meta / save_index_meta which need indexer — skip those for now if needed)

- [ ] **Step 6: Commit**

```bash
git add codebase_context/utils.py tests/__init__.py tests/test_utils.py
git commit -m "feat: add utils module with gitignore, path helpers, token counting"
```

---

## Chunk 4: parser.py

### Task 4: Tree-sitter abstraction layer

**Files:**
- Create: `codebase_context/parser.py`
- Create: `tests/test_parser.py`
- Create: `tests/fixtures/sample_py.py`
- Create: `tests/fixtures/sample_ts.ts`

- [ ] **Step 1: Create fixture files**

`tests/fixtures/sample_py.py`:
```python
"""Sample Python module for parser tests."""


class UserService:
    """Service for managing users."""

    def create(self, email: str, password: str) -> "User":
        """Create a new user."""
        return validate_email(email)

    def find_by_email(self, email: str) -> "Optional[User]":
        return None


def validate_email(email: str) -> str:
    """Validate an email address."""
    if "@" not in email:
        raise ValueError("Invalid email")
    return email


def validate_password(password: str) -> bool:
    return len(password) >= 8
```

`tests/fixtures/sample_ts.ts`:
```typescript
interface User {
  id: number;
  email: string;
}

type UserId = number;

class AuthService {
  login(email: string, password: string): Promise<User> {
    return Promise.resolve({ id: 1, email });
  }
}

function validateEmail(email: string): boolean {
  return email.includes("@");
}

const hashPassword = (password: string): string => {
  return password;
};
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_parser.py
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_python_class_and_methods():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    names = [s.name for s in symbols]
    assert "UserService" in names
    assert "create" in names
    assert "find_by_email" in names


def test_parse_python_module_functions():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    names = [s.name for s in symbols]
    assert "validate_email" in names
    assert "validate_password" in names


def test_parse_python_method_has_parent():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    method = next(s for s in symbols if s.name == "create")
    assert method.parent == "UserService"
    assert method.symbol_type in ("method", "function")


def test_parse_python_function_no_parent():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    fn = next(s for s in symbols if s.name == "validate_email")
    assert fn.parent is None


def test_parse_python_signature_format():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    fn = next(s for s in symbols if s.name == "validate_email")
    assert fn.signature.startswith("def validate_email")
    assert "email" in fn.signature


def test_parse_typescript_class():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_ts.ts"))
    names = [s.name for s in symbols]
    assert "AuthService" in names


def test_parse_typescript_interface():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_ts.ts"))
    names = [s.name for s in symbols]
    assert "User" in names


def test_parse_typescript_type_alias():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_ts.ts"))
    names = [s.name for s in symbols]
    assert "UserId" in names


def test_parse_typescript_arrow_function():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_ts.ts"))
    names = [s.name for s in symbols]
    assert "hashPassword" in names


def test_parse_syntax_error_returns_empty():
    from codebase_context.parser import parse_file
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def broken(:\n    pass\n")
        tmp = f.name
    try:
        # Should return [] or partial results, never raise
        result = parse_file(tmp)
        assert isinstance(result, list)
    finally:
        os.unlink(tmp)


def test_unsupported_extension_raises():
    from codebase_context.parser import parse_file, UnsupportedLanguageError
    with pytest.raises(UnsupportedLanguageError):
        parse_file("file.rb")
```

- [ ] **Step 3: Run failing tests**

```bash
pytest tests/test_parser.py -v
```
Expected: All FAIL (ImportError)

- [ ] **Step 4: Implement parser.py**

```python
# codebase_context/parser.py
"""Tree-sitter abstraction: parses source files into Symbol data structures."""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import tree_sitter
from tree_sitter import Language, Parser

from codebase_context.config import LANGUAGES

logger = logging.getLogger(__name__)


class UnsupportedLanguageError(ValueError):
    """Raised when a file extension is not in the LANGUAGES registry."""


@dataclass
class Symbol:
    name:       str
    symbol_type: str        # "function" | "class" | "method" | "interface" | "type"
    start_line: int         # 0-indexed
    end_line:   int         # 0-indexed, inclusive
    source:     str         # full source text of this symbol
    signature:  str         # compact one-line signature for repo map
    docstring:  str | None  # first comment/docstring if present
    calls:      list[str]   # names of functions/methods called within this symbol
    parent:     str | None  # class name if this is a method
    filepath:   str
    language:   str


@lru_cache(maxsize=None)
def _load_language(extension: str) -> tuple[Language, dict]:
    """Load and cache a tree-sitter Language object for the given extension."""
    if extension not in LANGUAGES:
        raise UnsupportedLanguageError(f"Unsupported file extension: {extension!r}")

    config = LANGUAGES[extension]
    module = importlib.import_module(config["tree_sitter_module"])

    if "tree_sitter_attr" in config:
        lang_obj = getattr(module, config["tree_sitter_attr"])
    else:
        lang_obj = module.language()

    # tree-sitter ≥0.22 uses Language(callable) directly
    if callable(lang_obj):
        language = Language(lang_obj())
    else:
        language = Language(lang_obj)

    return language, config


def get_parser(extension: str) -> Parser:
    """
    Returns a configured tree-sitter Parser for the given file extension.
    Raises UnsupportedLanguageError if extension not in LANGUAGES config.
    """
    language, _ = _load_language(extension)
    parser = Parser(language)
    return parser


def parse_file(filepath: str) -> list[Symbol]:
    """
    Parses a source file and returns all top-level symbols.
    Returns [] on parse error (logs warning, does not raise).
    """
    ext = Path(filepath).suffix
    if ext not in LANGUAGES:
        raise UnsupportedLanguageError(f"Unsupported file extension: {ext!r}")

    try:
        source_bytes = Path(filepath).read_bytes()
    except OSError as e:
        logger.warning("Could not read %s: %s", filepath, e)
        return []

    try:
        language, config = _load_language(ext)
        parser = Parser(language)
        tree = parser.parse(source_bytes)
    except Exception as e:
        logger.warning("Parse error for %s: %s", filepath, e)
        return []

    symbols: list[Symbol] = []
    lang_name = config["name"]
    node_types = config["node_types"]

    def _walk(node, parent_class: str | None = None) -> None:
        if node.type in node_types:
            name = _extract_name(node, source_bytes, config, ext)
            if not name:
                _walk_children(node, parent_class)
                return

            is_class = node.type in ("class_definition", "class_declaration")
            sym_type = _classify_node(node.type, parent_class, lang_name)

            sig = extract_signature(node, source_bytes, config, sym_type, name, parent_class)
            doc = _extract_docstring(node, source_bytes, config)
            calls = extract_calls(node, source_bytes)
            src = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

            sym = Symbol(
                name=name,
                symbol_type=sym_type,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                source=src,
                signature=sig,
                docstring=doc,
                calls=calls,
                parent=parent_class,
                filepath=filepath,
                language=lang_name,
            )
            symbols.append(sym)

            if is_class:
                # Recurse into class body to extract methods
                _walk_children(node, parent_class=name)
                return

        _walk_children(node, parent_class)

    def _walk_children(node, parent_class: str | None = None) -> None:
        for child in node.children:
            _walk(child, parent_class)

    _walk(tree.root_node)
    return symbols


def _extract_name(node, source_bytes: bytes, config: dict, ext: str) -> str | None:
    """Extract the symbol name from a node."""
    # For arrow functions: look up at variable_declarator parent
    if node.type == "arrow_function":
        return _get_arrow_function_name(node, source_bytes)

    name_node = node.child_by_field_name(config["name_field"])
    if name_node is None:
        return None
    return source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")


def _get_arrow_function_name(node, source_bytes: bytes) -> str | None:
    """
    For TypeScript arrow functions: extract variable name from parent
    variable_declarator node (e.g. `const foo = () => {}`).
    """
    parent = node.parent
    if parent is None:
        return None
    if parent.type == "variable_declarator":
        name_node = parent.child_by_field_name("name")
        if name_node:
            return source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
    return None


def _classify_node(node_type: str, parent_class: str | None, language: str) -> str:
    """Map tree-sitter node type to Symbol.symbol_type."""
    if node_type in ("class_definition", "class_declaration"):
        return "class"
    if node_type == "interface_declaration":
        return "interface"
    if node_type == "type_alias_declaration":
        return "type"
    if parent_class is not None:
        return "method"
    return "function"


def extract_signature(
    node,
    source_bytes: bytes,
    config: dict,
    sym_type: str,
    name: str,
    parent_class: str | None,
) -> str:
    """
    Produces a compact one-line signature string.
    Python:     def register(self, email: str, password: str) -> User
    TypeScript: function login(email: string, password: string): Promise<User>
    Class:      class UserService (N methods)
    """
    if sym_type == "class":
        # Count direct method children
        method_count = sum(
            1 for child in _iter_body(node)
            if child.type in ("function_definition", "method_definition")
        )
        return f"class {name} ({method_count} methods)"

    if sym_type in ("interface", "type"):
        first_line = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace").split("\n")[0]
        return first_line.rstrip("{").strip()

    # Function / method: extract first line up to body
    src = source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    first_line = src.split("\n")[0].rstrip("{ ").strip()
    # Remove leading `export `, `async ` for cleanliness
    first_line = first_line.lstrip("export ").strip()
    return first_line


def _iter_body(class_node):
    """Iterate children of the class body."""
    for child in class_node.children:
        if child.type in ("block", "class_body", "suite"):
            yield from child.children
        else:
            yield child


def _extract_docstring(node, source_bytes: bytes, config: dict) -> str | None:
    """Extract first docstring/comment from a symbol node."""
    prefix = config.get("comment_prefix", "#")
    for child in node.children:
        if child.type in ("block", "suite", "class_body"):
            for grandchild in child.children:
                if grandchild.type in ("expression_statement", "comment"):
                    text = source_bytes[grandchild.start_byte:grandchild.end_byte].decode("utf-8", errors="replace").strip()
                    if text.startswith(('"""', "'''", '"', "'")):
                        return text.strip("\"'").strip()
                    if text.startswith(prefix):
                        return text.lstrip(prefix).strip()
                    break
    return None


def extract_calls(node, source_bytes: bytes) -> list[str]:
    """
    Finds all call_expression / call nodes within a symbol's subtree.
    Returns unique function/method names called.
    """
    names: set[str] = set()

    def _walk(n) -> None:
        if n.type in ("call", "call_expression"):
            fn_node = n.child_by_field_name("function") or (n.children[0] if n.children else None)
            if fn_node:
                if fn_node.type == "identifier":
                    names.add(source_bytes[fn_node.start_byte:fn_node.end_byte].decode("utf-8", errors="replace"))
                elif fn_node.type in ("attribute", "member_expression"):
                    # e.g. self.validate_email → validate_email
                    attr = fn_node.children[-1]
                    if attr.type in ("identifier", "property_identifier"):
                        names.add(source_bytes[attr.start_byte:attr.end_byte].decode("utf-8", errors="replace"))
        for child in n.children:
            _walk(child)

    _walk(node)
    return sorted(names)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_parser.py -v
```
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add codebase_context/parser.py tests/test_parser.py tests/fixtures/
git commit -m "feat: add parser module with Tree-sitter symbol extraction"
```

---

## Chunk 5: chunker.py

### Task 5: Semantic code chunking

**Files:**
- Create: `codebase_context/chunker.py`
- Create: `tests/test_chunker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_chunker.py
import hashlib
from pathlib import Path
from codebase_context.parser import Symbol

FIXTURES = Path(__file__).parent / "fixtures"


def make_symbol(name="my_func", sym_type="function", start=0, end=5, source="def my_func(): pass"):
    return Symbol(
        name=name,
        symbol_type=sym_type,
        start_line=start,
        end_line=end,
        source=source,
        signature=f"def {name}()",
        docstring=None,
        calls=[],
        parent=None,
        filepath="src/utils.py",
        language="python",
    )


def test_chunk_has_context_prefix():
    from codebase_context.chunker import build_chunks
    sym = make_symbol()
    chunks = build_chunks([sym], "src/utils.py")
    assert len(chunks) == 1
    assert "# filepath: src/utils.py" in chunks[0].text
    assert "def my_func()" in chunks[0].text


def test_chunk_id_is_deterministic():
    from codebase_context.chunker import chunk_id
    id1 = chunk_id("src/utils.py", "my_func", 10)
    id2 = chunk_id("src/utils.py", "my_func", 10)
    assert id1 == id2


def test_chunk_id_differs_for_different_inputs():
    from codebase_context.chunker import chunk_id
    id1 = chunk_id("src/utils.py", "my_func", 10)
    id2 = chunk_id("src/utils.py", "other_func", 10)
    assert id1 != id2


def test_chunk_metadata_contains_required_fields():
    from codebase_context.chunker import build_chunks
    sym = make_symbol(name="create", sym_type="method", start=10, end=20)
    sym.parent = "UserService"
    chunks = build_chunks([sym], "src/api.py")
    meta = chunks[0].metadata
    assert meta["filepath"] == "src/api.py"
    assert meta["symbol_name"] == "create"
    assert meta["symbol_type"] == "method"
    assert meta["start_line"] == 10
    assert meta["end_line"] == 20
    assert meta["language"] == "python"
    assert meta["parent_class"] == "UserService"


def test_long_chunk_truncated():
    from codebase_context.chunker import build_chunks
    # Create a symbol with very long source to exceed MAX_CHUNK_TOKENS
    long_source = "\n".join([f"    x_{i} = {i}" for i in range(1000)])
    sym = make_symbol(source=f"def big():\n{long_source}")
    chunks = build_chunks([sym], "src/big.py")
    from codebase_context.config import MAX_CHUNK_TOKENS
    from codebase_context.utils import count_tokens
    assert count_tokens(chunks[0].text) <= MAX_CHUNK_TOKENS + 20  # small tolerance


def test_chunk_prefix_includes_parent_class():
    from codebase_context.chunker import build_chunks
    sym = make_symbol(name="save", sym_type="method")
    sym.parent = "UserService"
    chunks = build_chunks([sym], "src/service.py")
    assert "class: UserService" in chunks[0].text
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_chunker.py -v
```
Expected: All FAIL

- [ ] **Step 3: Implement chunker.py**

```python
# codebase_context/chunker.py
"""Converts parsed Symbols into indexable Chunks for the vector store."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from codebase_context.config import MAX_CHUNK_TOKENS
from codebase_context.parser import Symbol
from codebase_context.utils import count_tokens


@dataclass
class Chunk:
    id:       str    # deterministic: sha256(filepath + symbol_name + start_line)
    text:     str    # context-enriched text to embed
    metadata: dict   # stored in ChromaDB alongside the vector


def chunk_id(filepath: str, symbol_name: str, start_line: int) -> str:
    """
    Deterministic ID for a chunk. Same symbol at same location = same ID.
    Used to detect which chunks need updating on incremental reindex.
    """
    key = f"{filepath}::{symbol_name}::{start_line}"
    return hashlib.sha256(key.encode()).hexdigest()


def build_chunks(symbols: list[Symbol], filepath: str) -> list[Chunk]:
    """
    Converts symbols to chunks with context-enriched text.

    The text field includes a context prefix:
      # filepath: src/services/user_service.py
      # type: method | class: UserService
      def register(self, email: str, password: str) -> User:
          ...actual source...
    """
    chunks: list[Chunk] = []

    for sym in symbols:
        prefix_lines = [f"# filepath: {filepath}"]
        type_line = f"# type: {sym.symbol_type}"
        if sym.parent:
            type_line += f" | class: {sym.parent}"
        prefix_lines.append(type_line)

        full_text = "\n".join(prefix_lines) + "\n" + sym.source

        # Truncate at MAX_CHUNK_TOKENS, preserving full source in metadata
        text = _truncate_to_tokens(full_text, MAX_CHUNK_TOKENS)

        meta = {
            "filepath":     filepath,
            "symbol_name":  sym.name,
            "symbol_type":  sym.symbol_type,
            "start_line":   sym.start_line,
            "end_line":     sym.end_line,
            "language":     sym.language,
            "parent_class": sym.parent or "",
            "calls":        json.dumps(sym.calls),
            "docstring":    sym.docstring or "",
            # Preserve full source in metadata even if text is truncated
            "full_source":  sym.source,
            "signature":    sym.signature,
        }

        chunks.append(Chunk(
            id=chunk_id(filepath, sym.name, sym.start_line),
            text=text,
            metadata=meta,
        ))

    return chunks


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text at nearest logical line boundary to stay within max_tokens."""
    if count_tokens(text) <= max_tokens:
        return text

    lines = text.split("\n")
    result_lines: list[str] = []
    for line in lines:
        result_lines.append(line)
        if count_tokens("\n".join(result_lines)) > max_tokens:
            result_lines.pop()
            break
    return "\n".join(result_lines)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_chunker.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codebase_context/chunker.py tests/test_chunker.py
git commit -m "feat: add chunker module with context-enriched chunk building"
```

---

## Chunk 6: embedder.py

### Task 6: Sentence-transformers embedding wrapper

**Files:**
- Create: `codebase_context/embedder.py`

Note: No unit tests for embedder — it wraps a large ML model. Integration tests in `test_indexer.py` cover it end-to-end.

- [ ] **Step 1: Implement embedder.py**

```python
# codebase_context/embedder.py
"""Wraps sentence-transformers with lazy loading and batching."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from codebase_context.config import EMBED_BATCH_SIZE, EMBED_MODEL

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class Embedder:
    """
    Lazy-loads jinaai/jina-embeddings-v2-base-code on first call.
    Model is cached in ~/.cache/huggingface (standard HF cache).
    Thread-safe: uses a lock around model initialization.
    """

    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        self._lock = threading.Lock()

    def _get_model(self) -> "SentenceTransformer":
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(
                        "Loading embedding model %s (first use — may download ~550MB)...",
                        self.model_name,
                    )
                    print(
                        f"[codebase-context] Loading embedding model '{self.model_name}'...\n"
                        f"  First run: downloads ~550MB to ~/.cache/huggingface/\n"
                        f"  Subsequent runs use cached model.",
                        flush=True,
                    )
                    from sentence_transformers import SentenceTransformer
                    self._model = SentenceTransformer(
                        self.model_name,
                        trust_remote_code=True,
                    )
                    logger.info("Embedding model loaded.")
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embeds a list of texts in batches of EMBED_BATCH_SIZE.
        Returns list of float vectors (dimensionality: 768 for jina-v2-base-code).
        """
        model = self._get_model()
        results: list[list[float]] = []

        for batch_start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[batch_start : batch_start + EMBED_BATCH_SIZE]
            if len(texts) > 100:
                logger.info(
                    "Embedding batch %d/%d...",
                    batch_start // EMBED_BATCH_SIZE + 1,
                    (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE,
                )
            vecs = model.encode(batch, show_progress_bar=False)
            results.extend(vec.tolist() for vec in vecs)

        return results

    def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for single text."""
        return self.embed([text])[0]
```

- [ ] **Step 2: Verify import**

```bash
python -c "from codebase_context.embedder import Embedder; e = Embedder(); print('OK')"
```
Expected: `OK` (no model load yet — lazy)

- [ ] **Step 3: Commit**

```bash
git add codebase_context/embedder.py
git commit -m "feat: add embedder module with lazy sentence-transformers loading"
```

---

## Chunk 7: store.py

### Task 7: ChromaDB vector store wrapper

**Files:**
- Create: `codebase_context/store.py`

No isolated unit tests — tested via `test_indexer.py` and `test_retriever.py` integration tests.

- [ ] **Step 1: Implement store.py**

```python
# codebase_context/store.py
"""ChromaDB wrapper for vector storage and retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import chromadb

from codebase_context.chunker import Chunk
from codebase_context.config import CHROMA_DIR, DEFAULT_TOP_K
from codebase_context.utils import slugify

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    chunk_text: str
    metadata:   dict
    score:      float


class VectorStore:
    """
    Wraps a ChromaDB PersistentClient stored at CHROMA_DIR.
    Collection name: slugified project root path.
    """

    def __init__(self, project_root: str):
        chroma_path = str(Path(project_root) / CHROMA_DIR)
        Path(chroma_path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=chroma_path)
        self._collection_name = slugify(str(Path(project_root).resolve()))
        self._collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        return self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Upserts chunks by their deterministic ID."""
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeddings,
            metadatas=[c.metadata for c in chunks],
        )

    def delete_by_filepath(self, filepath: str) -> None:
        """Removes all chunks from a given file."""
        try:
            results = self._collection.get(where={"filepath": filepath})
            if results["ids"]:
                self._collection.delete(ids=results["ids"])
        except Exception as e:
            logger.warning("Error deleting chunks for %s: %s", filepath, e)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = DEFAULT_TOP_K,
        where: dict | None = None,
    ) -> list[SearchResult]:
        """
        Nearest-neighbor search.
        Returns SearchResult(chunk_text, metadata, score) sorted by score desc.
        """
        kwargs: dict = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, self.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = self._collection.query(**kwargs)
        except Exception as e:
            logger.error("Search error: %s", e)
            return []

        search_results: list[SearchResult] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance → similarity score
            score = 1.0 - dist
            search_results.append(SearchResult(chunk_text=doc, metadata=meta, score=score))

        return sorted(search_results, key=lambda r: r.score, reverse=True)

    def get_by_symbol_name(self, name: str) -> list[SearchResult]:
        """Exact metadata filter: {"symbol_name": name}."""
        try:
            results = self._collection.get(
                where={"symbol_name": name},
                include=["documents", "metadatas"],
            )
        except Exception as e:
            logger.warning("get_by_symbol_name error: %s", e)
            return []

        return [
            SearchResult(chunk_text=doc, metadata=meta, score=1.0)
            for doc, meta in zip(results["documents"], results["metadatas"])
        ]

    def count(self) -> int:
        """Total number of chunks indexed."""
        return self._collection.count()

    def clear(self) -> None:
        """Deletes and recreates the collection."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._get_or_create_collection()
        logger.info("Collection %s cleared.", self._collection_name)
```

- [ ] **Step 2: Verify import**

```bash
python -c "from codebase_context.store import VectorStore; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add codebase_context/store.py
git commit -m "feat: add ChromaDB vector store wrapper"
```

---

## Chunk 8: repo_map.py

### Task 8: Repo map generator

**Files:**
- Create: `codebase_context/repo_map.py`
- Create: `tests/test_repo_map.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_repo_map.py
import pytest
from codebase_context.parser import Symbol


def make_sym(name, sym_type, parent=None, sig="def foo()", filepath="src/utils.py", lang="python"):
    return Symbol(
        name=name, symbol_type=sym_type, start_line=0, end_line=5,
        source="def foo(): pass", signature=sig, docstring=None,
        calls=[], parent=parent, filepath=filepath, language=lang,
    )


def test_repo_map_includes_file_header():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/utils.py": [make_sym("validate_email", "function", sig="def validate_email(email: str) -> str")],
    }
    result = generate_repo_map(".", symbols_by_file)
    assert "## src/utils.py" in result


def test_repo_map_function_has_plus_prefix():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/utils.py": [make_sym("validate_email", "function", sig="def validate_email(email: str) -> str")],
    }
    result = generate_repo_map(".", symbols_by_file)
    assert "  + validate_email" in result


def test_repo_map_methods_indented_under_class():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/service.py": [
            make_sym("UserService", "class", sig="class UserService (2 methods)"),
            make_sym("create", "method", parent="UserService", sig="def create(self, email: str) -> User"),
            make_sym("delete", "method", parent="UserService", sig="def delete(self, id: int) -> bool"),
        ],
    }
    result = generate_repo_map(".", symbols_by_file)
    assert "  class UserService:" in result
    assert "    + create" in result
    assert "    + delete" in result


def test_repo_map_header_contains_stats():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/utils.py": [make_sym("foo", "function")],
        "src/other.py": [make_sym("bar", "function")],
    }
    result = generate_repo_map(".", symbols_by_file)
    assert "Files: 2" in result
    assert "Symbols: 2" in result


def test_repo_map_token_estimate_under_target():
    from codebase_context.repo_map import generate_repo_map, estimate_tokens
    # Simulate 500 files with 1 function each
    symbols_by_file = {
        f"src/module_{i}.py": [make_sym(f"func_{i}", "function", sig=f"def func_{i}()")]
        for i in range(500)
    }
    result = generate_repo_map(".", symbols_by_file)
    tokens = estimate_tokens(result)
    assert tokens < 8000, f"Repo map too large: {tokens} tokens"


def test_files_sorted_by_depth_then_alpha():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/api/auth.py": [make_sym("login", "function")],
        "src/utils.py": [make_sym("helper", "function")],
        "main.py": [make_sym("main", "function")],
    }
    result = generate_repo_map(".", symbols_by_file)
    # main.py (depth 0) should come before src/utils.py (depth 1)
    pos_main = result.index("main.py")
    pos_utils = result.index("src/utils.py")
    pos_auth = result.index("src/api/auth.py")
    assert pos_main < pos_utils
    assert pos_utils < pos_auth
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_repo_map.py -v
```
Expected: All FAIL

- [ ] **Step 3: Implement repo_map.py**

```python
# codebase_context/repo_map.py
"""Generates the compact repo map written to .codebase-context/repo_map.md."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from codebase_context.config import REPO_MAP_PATH
from codebase_context.parser import Symbol

logger = logging.getLogger(__name__)

_WARN_TOKENS = 8_000


def generate_repo_map(project_root: str, symbols_by_file: dict[str, list[Symbol]]) -> str:
    """Generates the full repo map string."""
    total_files = len(symbols_by_file)
    total_symbols = sum(len(syms) for syms in symbols_by_file.values())
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    lines: list[str] = [
        "# Repo Map",
        f"# Generated: {now}  |  Files: {total_files}  |  Symbols: {total_symbols}",
        "# Reference this in CLAUDE.md with: @.codebase-context/repo_map.md",
        "",
        "---",
        "",
    ]

    # Sort: by directory depth first, then alphabetically
    sorted_files = sorted(
        symbols_by_file.keys(),
        key=lambda p: (len(Path(p).parts), p),
    )

    for filepath in sorted_files:
        syms = symbols_by_file[filepath]
        if not syms:
            continue

        lines.append(f"## {filepath}")

        # Group methods under their parent class
        classes: dict[str, list[Symbol]] = {}
        standalone: list[Symbol] = []

        for sym in syms:
            if sym.symbol_type == "class":
                classes[sym.name] = []
            elif sym.symbol_type in ("method",) and sym.parent:
                classes.setdefault(sym.parent, []).append(sym)
            else:
                standalone.append(sym)

        # Emit classes first
        for class_name, methods in classes.items():
            lines.append(f"  class {class_name}:")
            for method in methods:
                lines.append(f"    + {method.name}{_params_from_sig(method.signature)}")

        # Emit standalone symbols
        for sym in standalone:
            if sym.symbol_type in ("interface", "type"):
                lines.append(f"  {sym.symbol_type} {sym.name}")
            else:
                lines.append(f"  + {sym.name}{_params_from_sig(sym.signature)}")

        lines.append("")

    result = "\n".join(lines)

    tokens = estimate_tokens(result)
    if tokens > _WARN_TOKENS:
        logger.warning(
            "Repo map is large (%d tokens). Consider excluding more files.", tokens
        )

    return result


def _params_from_sig(sig: str) -> str:
    """Extract the parameter/return portion from a signature for compact display."""
    # Return everything after the function name (params + return type)
    paren = sig.find("(")
    if paren >= 0:
        return sig[paren:]
    return ""


def write_repo_map(project_root: str, repo_map: str) -> None:
    """Writes to REPO_MAP_PATH, creating .codebase-context/ dir if needed."""
    path = Path(project_root) / REPO_MAP_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(repo_map, encoding="utf-8")
    logger.info("Repo map written to %s", path)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: len(text) / 4."""
    return len(text) // 4
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_repo_map.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codebase_context/repo_map.py tests/test_repo_map.py
git commit -m "feat: add repo_map module with compact symbol-map generation"
```

---

## Chunk 9: indexer.py

### Task 9: Full indexing pipeline orchestrator

**Files:**
- Create: `codebase_context/indexer.py`
- Create: `tests/test_indexer.py`
- Create: `tests/fixtures/sample_project/` (small fixture project)

- [ ] **Step 1: Create fixture project**

`tests/fixtures/sample_project/src/api/auth.py`:
```python
"""Auth API module."""
from typing import Optional


class AuthRouter:
    """Handles authentication routes."""

    def login(self, email: str, password: str) -> dict:
        """Log in a user."""
        return {"token": "abc"}

    def register(self, email: str, password: str) -> dict:
        """Register a new user."""
        return {"id": 1, "email": email}

    def refresh(self, token: str) -> dict:
        """Refresh an auth token."""
        return {"token": token}
```

`tests/fixtures/sample_project/src/utils/validation.py`:
```python
"""Validation utilities."""


def validate_email(email: str) -> str:
    """Validate an email address."""
    if "@" not in email:
        raise ValueError("Invalid email")
    return email.lower()


def validate_password(password: str) -> bool:
    """Validate password strength."""
    return len(password) >= 8
```

`tests/fixtures/sample_project/src/types/user.ts`:
```typescript
export interface User {
  id: number;
  email: string;
  createdAt: Date;
}

export type UserId = number;
```

`tests/fixtures/sample_project/src/services/auth.ts`:
```typescript
import { User, UserId } from "../types/user";

export class AuthService {
  async login(email: string, password: string): Promise<User> {
    return { id: 1, email, createdAt: new Date() };
  }

  async logout(userId: UserId): Promise<void> {
    return;
  }
}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_indexer.py
import os
import shutil
import tempfile
from pathlib import Path

import pytest

SAMPLE_PROJECT = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture
def tmp_project(tmp_path):
    """Copy sample project to a temp directory for isolation."""
    dest = tmp_path / "sample_project"
    shutil.copytree(SAMPLE_PROJECT, dest)
    # Initialize a fake git repo
    (dest / ".git").mkdir()
    return str(dest)


def test_discover_files_finds_py_and_ts(tmp_project):
    from codebase_context.indexer import discover_files
    files = discover_files(tmp_project)
    extensions = {Path(f).suffix for f in files}
    assert ".py" in extensions
    assert ".ts" in extensions


def test_discover_files_excludes_gitignore(tmp_project):
    from codebase_context.indexer import discover_files
    # Add a .gitignore that excludes validation.py
    gitignore = Path(tmp_project) / ".gitignore"
    gitignore.write_text("**/validation.py\n")
    files = discover_files(tmp_project)
    assert not any("validation.py" in f for f in files)


def test_full_index_creates_chunks(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    stats = indexer.full_index(show_progress=False)
    assert stats.files_indexed > 0
    assert stats.chunks_created > 0
    assert stats.duration_seconds >= 0


def test_full_index_writes_repo_map(tmp_project):
    from codebase_context.indexer import Indexer
    from codebase_context.config import REPO_MAP_PATH
    indexer = Indexer(tmp_project)
    indexer.full_index(show_progress=False)
    repo_map_path = Path(tmp_project) / REPO_MAP_PATH
    assert repo_map_path.exists()
    content = repo_map_path.read_text()
    assert "AuthRouter" in content or "auth" in content.lower()


def test_incremental_index_skips_unchanged(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    indexer.full_index(show_progress=False)

    # Re-index without changes
    stats = indexer.incremental_index(show_progress=False)
    assert stats.files_indexed == 0


def test_incremental_index_processes_changed_file(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    indexer.full_index(show_progress=False)

    # Modify a file
    auth_path = Path(tmp_project) / "src" / "api" / "auth.py"
    content = auth_path.read_text()
    auth_path.write_text(content + "\n\ndef new_function(): pass\n")

    # Small sleep to ensure mtime changes
    import time; time.sleep(0.01)

    stats = indexer.incremental_index(show_progress=False)
    assert stats.files_indexed >= 1


def test_index_file_returns_chunk_count(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    auth_path = str(Path(tmp_project) / "src" / "api" / "auth.py")
    count = indexer.index_file(auth_path)
    assert count > 0


def test_remove_file_clears_chunks(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    auth_path = str(Path(tmp_project) / "src" / "api" / "auth.py")
    indexer.index_file(auth_path)
    before = indexer.store.count()
    indexer.remove_file(auth_path)
    after = indexer.store.count()
    assert after < before
```

- [ ] **Step 3: Run failing tests**

```bash
pytest tests/test_indexer.py -v
```
Expected: All FAIL

- [ ] **Step 4: Implement indexer.py**

```python
# codebase_context/indexer.py
"""Full indexing pipeline orchestrator."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from codebase_context.chunker import build_chunks
from codebase_context.config import ALWAYS_IGNORE, LANGUAGES
from codebase_context.embedder import Embedder
from codebase_context.parser import parse_file
from codebase_context.repo_map import generate_repo_map, write_repo_map
from codebase_context.store import VectorStore
from codebase_context.utils import (
    find_project_root,
    is_ignored,
    load_gitignore,
    load_index_meta,
    save_index_meta,
)

logger = logging.getLogger(__name__)


@dataclass
class IndexMeta:
    """Persisted to INDEX_META_PATH as JSON. Tracks per-file mtimes for incremental indexing."""
    last_full_index: str               # ISO timestamp
    file_mtimes:     dict[str, float]  # filepath -> mtime at last index
    total_chunks:    int
    total_files:     int


@dataclass
class IndexStats:
    files_indexed:    int
    chunks_created:   int
    duration_seconds: float


class Indexer:
    def __init__(self, project_root: str):
        self.root     = project_root
        self.store    = VectorStore(project_root)
        self.embedder = Embedder()
        self.meta     = load_index_meta(project_root)

    def full_index(self, show_progress: bool = True) -> IndexStats:
        """Indexes the entire project from scratch."""
        start = time.time()
        self.store.clear()

        files = discover_files(self.root)
        if not files:
            logger.warning("No indexable files found in %s", self.root)
            return IndexStats(0, 0, time.time() - start)

        iter_files = files
        if show_progress:
            try:
                from tqdm import tqdm
                iter_files = tqdm(files, desc="Indexing", unit="file")
            except ImportError:
                pass

        symbols_by_file: dict[str, list] = {}
        total_chunks = 0

        for filepath in iter_files:
            symbols = parse_file(filepath)
            if not symbols:
                continue
            symbols_by_file[filepath] = symbols

            rel_path = os.path.relpath(filepath, self.root)
            chunks = build_chunks(symbols, rel_path)
            if not chunks:
                continue

            embeddings = self.embedder.embed([c.text for c in chunks])
            self.store.upsert(chunks, embeddings)
            total_chunks += len(chunks)

        # Generate and write repo map
        rel_symbols = {
            os.path.relpath(fp, self.root): syms
            for fp, syms in symbols_by_file.items()
        }
        repo_map = generate_repo_map(self.root, rel_symbols)
        write_repo_map(self.root, repo_map)

        # Save metadata
        self.meta = IndexMeta(
            last_full_index=datetime.now(tz=timezone.utc).isoformat(),
            file_mtimes={f: os.path.getmtime(f) for f in files},
            total_chunks=total_chunks,
            total_files=len(symbols_by_file),
        )
        save_index_meta(self.root, self.meta)

        duration = time.time() - start
        return IndexStats(
            files_indexed=len(symbols_by_file),
            chunks_created=total_chunks,
            duration_seconds=duration,
        )

    def incremental_index(self, show_progress: bool = True) -> IndexStats:
        """Only re-indexes files whose mtime has changed since last index."""
        start = time.time()
        files = discover_files(self.root)

        changed = [
            f for f in files
            if self.meta.file_mtimes.get(f, 0) != os.path.getmtime(f)
        ]

        if not changed:
            return IndexStats(0, 0, time.time() - start)

        iter_changed = changed
        if show_progress:
            try:
                from tqdm import tqdm
                iter_changed = tqdm(changed, desc="Updating", unit="file")
            except ImportError:
                pass

        total_chunks = 0
        for filepath in iter_changed:
            rel_path = os.path.relpath(filepath, self.root)
            self.store.delete_by_filepath(rel_path)
            chunks_created = self.index_file(filepath)
            total_chunks += chunks_created
            self.meta.file_mtimes[filepath] = os.path.getmtime(filepath)

        # Regenerate repo map with all current files
        self._regenerate_repo_map(files)

        self.meta.total_chunks = self.store.count()
        self.meta.total_files = len(files)
        save_index_meta(self.root, self.meta)

        return IndexStats(
            files_indexed=len(changed),
            chunks_created=total_chunks,
            duration_seconds=time.time() - start,
        )

    def index_file(self, filepath: str) -> int:
        """Index a single file. Returns number of chunks created."""
        symbols = parse_file(filepath)
        if not symbols:
            return 0

        rel_path = os.path.relpath(filepath, self.root)
        chunks = build_chunks(symbols, rel_path)
        if not chunks:
            return 0

        embeddings = self.embedder.embed([c.text for c in chunks])
        self.store.upsert(chunks, embeddings)
        return len(chunks)

    def remove_file(self, filepath: str) -> None:
        """Called when a file is deleted. Removes all its chunks."""
        rel_path = os.path.relpath(filepath, self.root)
        self.store.delete_by_filepath(rel_path)
        if filepath in self.meta.file_mtimes:
            del self.meta.file_mtimes[filepath]
        save_index_meta(self.root, self.meta)

    def _regenerate_repo_map(self, files: list[str]) -> None:
        """Rebuild repo map from all currently-indexed files."""
        symbols_by_file: dict[str, list] = {}
        for filepath in files:
            symbols = parse_file(filepath)
            if symbols:
                rel_path = os.path.relpath(filepath, self.root)
                symbols_by_file[rel_path] = symbols

        repo_map = generate_repo_map(self.root, symbols_by_file)
        write_repo_map(self.root, repo_map)


def discover_files(project_root: str) -> list[str]:
    """
    Returns all source files to index.
    Respects .gitignore, ALWAYS_IGNORE patterns, and LANGUAGES extensions.
    """
    gitignore = load_gitignore(project_root)
    supported_exts = set(LANGUAGES.keys())
    result: list[str] = []

    for dirpath, dirnames, filenames in os.walk(project_root):
        # Prune ignored directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not is_ignored(os.path.join(dirpath, d), project_root, gitignore)
        ]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            ext = Path(filepath).suffix
            if ext not in supported_exts:
                continue
            if is_ignored(filepath, project_root, gitignore):
                continue
            result.append(filepath)

    return sorted(result)
```

- [ ] **Step 5: Fix circular import in utils.py**

The `load_index_meta` / `save_index_meta` functions in `utils.py` import from `indexer.py`, and `indexer.py` imports from `utils.py`. Fix this by moving `IndexMeta` to a separate module or by using a local import. The simplest fix: remove the `IndexMeta` import from `utils.py` and instead access `IndexMeta` from `indexer` at call time (already done with local import in the utils.py implementation above).

Verify no circular import:
```bash
python -c "from codebase_context.indexer import Indexer; print('OK')"
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_indexer.py -v
```
Expected: All PASS (note: first run downloads embedding model ~550MB)

- [ ] **Step 7: Commit**

```bash
git add codebase_context/indexer.py tests/test_indexer.py tests/fixtures/sample_project/
git commit -m "feat: add indexer module with full and incremental indexing pipeline"
```

---

## Chunk 10: retriever.py

### Task 10: Query interface

**Files:**
- Create: `codebase_context/retriever.py`
- Create: `tests/test_retriever.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_retriever.py
import shutil
from pathlib import Path

import pytest

SAMPLE_PROJECT = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture(scope="module")
def indexed_project(tmp_path_factory):
    """Build a fully-indexed sample project once for all retriever tests."""
    tmp = tmp_path_factory.mktemp("retriever_project")
    dest = tmp / "sample_project"
    shutil.copytree(SAMPLE_PROJECT, dest)
    (dest / ".git").mkdir()

    from codebase_context.indexer import Indexer
    indexer = Indexer(str(dest))
    indexer.full_index(show_progress=False)
    return str(dest)


def test_search_returns_results(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.search("user authentication login")
    assert len(results) > 0


def test_search_results_have_required_fields(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.search("email validation")
    assert len(results) > 0
    r = results[0]
    assert r.filepath
    assert r.symbol_name
    assert r.symbol_type in ("function", "class", "method", "interface", "type")
    assert r.score >= 0.0


def test_search_language_filter(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.search("login", language="python")
    assert all(r.language == "python" for r in results)


def test_search_filepath_filter(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.search("auth", filepath_contains="auth")
    # All results should be from files containing "auth" in path
    assert all("auth" in r.filepath for r in results)


def test_get_symbol_exact_match(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.get_symbol("validate_email")
    assert len(results) > 0
    assert all(r.symbol_name == "validate_email" for r in results)


def test_get_symbol_returns_empty_for_unknown(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.get_symbol("nonexistent_function_xyz_abc")
    assert results == []


def test_get_repo_map_returns_content(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    result = retriever.get_repo_map(indexed_project)
    assert "Repo Map" in result or "not indexed" in result


def test_get_repo_map_not_indexed_message(tmp_path):
    from codebase_context.retriever import Retriever
    (tmp_path / ".git").mkdir()
    retriever = Retriever(str(tmp_path))
    result = retriever.get_repo_map(str(tmp_path))
    assert "not indexed" in result.lower() or "run" in result.lower()
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_retriever.py -v
```
Expected: All FAIL

- [ ] **Step 3: Implement retriever.py**

```python
# codebase_context/retriever.py
"""Clean query interface used by the MCP server and CLI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from codebase_context.config import DEFAULT_TOP_K, REPO_MAP_PATH
from codebase_context.embedder import Embedder
from codebase_context.store import SearchResult, VectorStore

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    filepath:     str
    symbol_name:  str
    symbol_type:  str
    source:       str
    signature:    str
    score:        float
    language:     str
    parent_class: str | None
    start_line:   int
    end_line:     int


def _search_result_to_retrieval(sr: SearchResult) -> RetrievalResult:
    meta = sr.metadata
    return RetrievalResult(
        filepath=meta.get("filepath", ""),
        symbol_name=meta.get("symbol_name", ""),
        symbol_type=meta.get("symbol_type", "function"),
        source=meta.get("full_source", sr.chunk_text),
        signature=meta.get("signature", ""),
        score=sr.score,
        language=meta.get("language", ""),
        parent_class=meta.get("parent_class") or None,
        start_line=int(meta.get("start_line", 0)),
        end_line=int(meta.get("end_line", 0)),
    )


class Retriever:
    def __init__(self, project_root: str):
        self.store    = VectorStore(project_root)
        self.embedder = Embedder()

    def search(
        self,
        query:             str,
        top_k:             int = DEFAULT_TOP_K,
        language:          str | None = None,
        filepath_contains: str | None = None,
    ) -> list[RetrievalResult]:
        """
        Embeds query, searches store, returns ranked results.
        Optional filters: language, filepath_contains.
        Results are deduplicated by filepath+symbol_name.
        """
        query_vec = self.embedder.embed_one(query)

        where: dict | None = None
        if language:
            where = {"language": language}

        raw = self.store.search(query_vec, top_k=top_k * 2, where=where)

        results = [_search_result_to_retrieval(r) for r in raw]

        # Apply filepath filter
        if filepath_contains:
            results = [r for r in results if filepath_contains in r.filepath]

        # Deduplicate by filepath+symbol_name (keep highest score)
        seen: set[str] = set()
        deduped: list[RetrievalResult] = []
        for r in results:
            key = f"{r.filepath}::{r.symbol_name}"
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        return deduped[:top_k]

    def get_symbol(self, name: str) -> list[RetrievalResult]:
        """Exact symbol name lookup. Case-sensitive."""
        raw = self.store.get_by_symbol_name(name)
        return [_search_result_to_retrieval(r) for r in raw]

    def get_repo_map(self, project_root: str) -> str:
        """Reads and returns current repo_map.md content."""
        path = Path(project_root) / REPO_MAP_PATH
        if path.exists():
            return path.read_text(encoding="utf-8")
        return (
            "Index not found. Run: ccindex init\n"
            "(This will parse your codebase and generate the repo map.)"
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_retriever.py -v
```
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add codebase_context/retriever.py tests/test_retriever.py
git commit -m "feat: add retriever module with semantic search and symbol lookup"
```

---

## Chunk 11: watcher.py

### Task 11: File system watcher and git hook installer

**Files:**
- Create: `codebase_context/watcher.py`

No unit tests for watcher (requires filesystem events; tested manually). Git hook installer is tested by `test_cli.py`.

- [ ] **Step 1: Implement watcher.py**

```python
# codebase_context/watcher.py
"""File system watcher for real-time incremental reindexing and git hook management."""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from codebase_context.config import LANGUAGES
from codebase_context.utils import find_project_root, is_ignored, load_gitignore

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = set(LANGUAGES.keys())
_DEBOUNCE_SECONDS = 2.0


class _CodebaseEventHandler(FileSystemEventHandler):
    """Watchdog event handler with debounce and filtering."""

    def __init__(self, indexer, project_root: str):
        self._indexer = indexer
        self._root = project_root
        self._gitignore = load_gitignore(project_root)
        self._pending: dict[str, str] = {}  # filepath -> event type
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def _should_handle(self, filepath: str) -> bool:
        ext = Path(filepath).suffix
        if ext not in _SUPPORTED_EXTENSIONS:
            return False
        if is_ignored(filepath, self._root, self._gitignore):
            return False
        return True

    def _schedule_flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(_DEBOUNCE_SECONDS, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()

        for filepath, event_type in pending.items():
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            if event_type == "deleted":
                self._indexer.remove_file(filepath)
                print(f"[{ts}] deleted  {filepath}")
            else:
                chunks = self._indexer.index_file(filepath)
                print(f"[{ts}] {event_type:<8} {filepath}  ({chunks} chunks)")

        if pending:
            # Regenerate repo map after batch
            from codebase_context.indexer import discover_files
            from codebase_context.repo_map import generate_repo_map, write_repo_map
            import os

            files = discover_files(self._root)
            symbols_by_file: dict[str, list] = {}
            for f in files:
                from codebase_context.parser import parse_file
                syms = parse_file(f)
                if syms:
                    symbols_by_file[os.path.relpath(f, self._root)] = syms
            repo_map = generate_repo_map(self._root, symbols_by_file)
            write_repo_map(self._root, repo_map)

    def on_created(self, event):
        if event.is_directory:
            return
        if self._should_handle(event.src_path):
            with self._lock:
                self._pending[event.src_path] = "created"
            self._schedule_flush()

    def on_modified(self, event):
        if event.is_directory:
            return
        if self._should_handle(event.src_path):
            with self._lock:
                self._pending[event.src_path] = "modified"
            self._schedule_flush()

    def on_deleted(self, event):
        if event.is_directory:
            return
        if self._should_handle(event.src_path):
            with self._lock:
                self._pending[event.src_path] = "deleted"
            self._schedule_flush()

    def on_moved(self, event):
        if event.is_directory:
            return
        # Remove old path
        if self._should_handle(event.src_path):
            with self._lock:
                self._pending[event.src_path] = "deleted"
        # Index new path
        if self._should_handle(event.dest_path):
            with self._lock:
                self._pending[event.dest_path] = "created"
        if event.src_path in self._pending or event.dest_path in self._pending:
            self._schedule_flush()


def watch(project_root: str) -> None:
    """
    Starts a watchdog FileSystemEventHandler on the project root.
    Runs until SIGINT/SIGTERM.
    """
    from codebase_context.indexer import Indexer

    indexer = Indexer(project_root)
    handler = _CodebaseEventHandler(indexer, project_root)
    observer = Observer()
    observer.schedule(handler, project_root, recursive=True)
    observer.start()

    print(f"[codebase-context] Watching {project_root}  (Ctrl+C to stop)")

    def _stop(signum, frame):
        observer.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    observer.join()
    print("[codebase-context] Watcher stopped.")


def install_git_hook(project_root: str) -> None:
    """
    Writes a post-commit hook to .git/hooks/post-commit.
    Appends if hook already exists. Makes it executable.
    """
    hook_dir = Path(project_root) / ".git" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / "post-commit"

    ccindex_line = "ccindex update\n"

    if hook_path.exists():
        content = hook_path.read_text(encoding="utf-8")
        if "ccindex update" in content:
            print(f"Git hook already contains ccindex line: {hook_path}")
            return
        # Append
        hook_path.write_text(content.rstrip("\n") + "\n" + ccindex_line, encoding="utf-8")
    else:
        hook_path.write_text(f"#!/bin/sh\n{ccindex_line}", encoding="utf-8")

    hook_path.chmod(0o755)
    print(f"Git hook installed: {hook_path}")


def uninstall_git_hook(project_root: str) -> None:
    """Removes the ccindex line from .git/hooks/post-commit."""
    hook_path = Path(project_root) / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        print("No post-commit hook found.")
        return

    content = hook_path.read_text(encoding="utf-8")
    new_lines = [l for l in content.splitlines() if "ccindex update" not in l]

    if not new_lines or new_lines == ["#!/bin/sh"]:
        hook_path.unlink()
        print(f"Git hook removed: {hook_path}")
    else:
        hook_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"ccindex line removed from: {hook_path}")
```

- [ ] **Step 2: Verify import**

```bash
python -c "from codebase_context.watcher import install_git_hook, watch; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add codebase_context/watcher.py
git commit -m "feat: add watcher module with debounced filesystem events and git hook management"
```

---

## Chunk 12: cli.py

### Task 12: Click CLI

**Files:**
- Create: `codebase_context/cli.py`

- [ ] **Step 1: Implement cli.py**

```python
# codebase_context/cli.py
"""Click CLI — entry point: ccindex."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from codebase_context.config import EMBED_MODEL
from codebase_context.utils import find_project_root


@click.group()
@click.option(
    "--root",
    default=None,
    metavar="PATH",
    help="Project root (default: nearest .git directory or cwd)",
)
@click.pass_context
def cli(ctx: click.Context, root: str | None) -> None:
    """codebase-context — Tree-sitter + RAG for Claude Code agents"""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root or find_project_root(os.getcwd())


# ---------------------------------------------------------------------------
# ccindex init
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Full index of current project."""
    from codebase_context.indexer import Indexer

    root = ctx.obj["root"]
    click.echo(f"Indexing {root}...")

    indexer = Indexer(root)
    stats = indexer.full_index(show_progress=True)

    click.echo(
        f"\n✓ Indexed {stats.files_indexed} files, "
        f"{stats.chunks_created} chunks in {stats.duration_seconds:.1f}s"
    )

    # Add .codebase-context/ to .gitignore
    _update_gitignore(root)

    # Prompt to add repo map to CLAUDE.md
    claude_md = Path(root) / "CLAUDE.md"
    ref_line = "@.codebase-context/repo_map.md"
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        has_ref = ref_line in content
    else:
        has_ref = False

    if not has_ref:
        if click.confirm("\nAdd repo map reference to CLAUDE.md?", default=True):
            if claude_md.exists():
                claude_md.write_text(
                    claude_md.read_text(encoding="utf-8").rstrip("\n")
                    + f"\n\n{ref_line}\n",
                    encoding="utf-8",
                )
            else:
                claude_md.write_text(f"{ref_line}\n", encoding="utf-8")
            click.echo(f"  Added {ref_line} to CLAUDE.md")

    # Prompt to install git hook
    if click.confirm("\nInstall git post-commit hook for auto-reindexing?", default=True):
        from codebase_context.watcher import install_git_hook
        install_git_hook(root)

    click.echo(
        "\nSetup complete! To use the MCP server, add to .claude/mcp.json:\n"
        '  {"mcpServers": {"codebase-context": {"command": "ccindex", "args": ["serve"]}}}'
    )


# ---------------------------------------------------------------------------
# ccindex update
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def update(ctx: click.Context) -> None:
    """Incremental index (changed files only)."""
    from codebase_context.indexer import Indexer

    root = ctx.obj["root"]
    indexer = Indexer(root)
    stats = indexer.incremental_index(show_progress=True)

    if stats.files_indexed == 0:
        click.echo("No changed files. Index is up to date.")
    else:
        click.echo(
            f"Updated {stats.files_indexed} files, "
            f"{stats.chunks_created} chunks in {stats.duration_seconds:.1f}s"
        )


# ---------------------------------------------------------------------------
# ccindex watch
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Real-time file watcher (Ctrl+C to stop)."""
    from codebase_context.watcher import watch as _watch
    _watch(ctx.obj["root"])


# ---------------------------------------------------------------------------
# ccindex search
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of results")
@click.option("--language", default=None, help="Filter: python or typescript")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    top_k: int,
    language: str | None,
    output_json: bool,
) -> None:
    """Semantic search from terminal."""
    from codebase_context.retriever import Retriever

    root = ctx.obj["root"]
    retriever = Retriever(root)
    results = retriever.search(query, top_k=top_k, language=language)

    if output_json:
        click.echo(json.dumps([
            {
                "filepath":     r.filepath,
                "symbol_name":  r.symbol_name,
                "symbol_type":  r.symbol_type,
                "signature":    r.signature,
                "score":        r.score,
                "start_line":   r.start_line,
                "end_line":     r.end_line,
                "parent_class": r.parent_class,
                "source":       r.source,
            }
            for r in results
        ], indent=2))
        return

    if not results:
        click.echo("No results found.")
        return

    for r in results:
        header = f"{r.filepath}:{r.start_line + 1}  [{r.symbol_type}]  score={r.score:.3f}"
        click.echo(click.style(header, bold=True))
        click.echo(f"  {r.signature}")
        click.echo("")


# ---------------------------------------------------------------------------
# ccindex map
# ---------------------------------------------------------------------------

@cli.command("map")
@click.pass_context
def map_cmd(ctx: click.Context) -> None:
    """Print repo map to stdout."""
    from codebase_context.retriever import Retriever

    root = ctx.obj["root"]
    retriever = Retriever(root)
    click.echo(retriever.get_repo_map(root))


# ---------------------------------------------------------------------------
# ccindex stats
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show index statistics."""
    import shutil
    from codebase_context.config import CHROMA_DIR, INDEX_META_PATH
    from codebase_context.utils import load_index_meta

    root = ctx.obj["root"]
    meta = load_index_meta(root)

    chroma_path = Path(root) / CHROMA_DIR
    size_mb = 0.0
    if chroma_path.exists():
        total = sum(f.stat().st_size for f in chroma_path.rglob("*") if f.is_file())
        size_mb = total / (1024 * 1024)

    click.echo(f"Files indexed:   {meta.total_files}")
    click.echo(f"Total chunks:    {meta.total_chunks}")
    click.echo(f"Index size:      {size_mb:.1f} MB")
    click.echo(f"Last index:      {meta.last_full_index or 'never'}")
    click.echo(f"Embedding model: {EMBED_MODEL}")


# ---------------------------------------------------------------------------
# ccindex clear
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--confirm", is_flag=True, required=True, help="Required: confirm deletion")
@click.pass_context
def clear(ctx: click.Context, confirm: bool) -> None:
    """Delete index and repo map. Requires --confirm."""
    from codebase_context.config import REPO_MAP_PATH
    from codebase_context.store import VectorStore

    root = ctx.obj["root"]
    store = VectorStore(root)
    store.clear()

    repo_map = Path(root) / REPO_MAP_PATH
    if repo_map.exists():
        repo_map.unlink()

    click.echo("Index and repo map cleared.")


# ---------------------------------------------------------------------------
# ccindex install-hook / uninstall-hook
# ---------------------------------------------------------------------------

@cli.command("install-hook")
@click.pass_context
def install_hook(ctx: click.Context) -> None:
    """Install git post-commit hook."""
    from codebase_context.watcher import install_git_hook
    install_git_hook(ctx.obj["root"])


@cli.command("uninstall-hook")
@click.pass_context
def uninstall_hook(ctx: click.Context) -> None:
    """Remove git post-commit hook."""
    from codebase_context.watcher import uninstall_git_hook
    uninstall_git_hook(ctx.obj["root"])


# ---------------------------------------------------------------------------
# ccindex serve
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Start MCP server (used by Claude Code)."""
    from codebase_context.mcp_server import run_server
    run_server()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _update_gitignore(project_root: str) -> None:
    """Appends codebase-context entries to .gitignore if not already present."""
    gitignore_path = Path(project_root) / ".gitignore"

    additions = [
        "# codebase-context",
        ".codebase-context/chroma/",
        ".codebase-context/index_meta.json",
        ".codebase-context/mcp.log",
        "# optionally commit repo_map.md for team visibility:",
        "# .codebase-context/repo_map.md",
    ]

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
    else:
        content = ""

    if ".codebase-context/chroma/" in content:
        return  # Already present

    new_content = content.rstrip("\n") + "\n\n" + "\n".join(additions) + "\n"
    gitignore_path.write_text(new_content, encoding="utf-8")
    click.echo("  Updated .gitignore with .codebase-context/ entries")
```

- [ ] **Step 2: Verify CLI entry point**

```bash
ccindex --help
```
Expected: Shows all commands (init, update, watch, search, map, stats, clear, install-hook, uninstall-hook, serve)

- [ ] **Step 3: Commit**

```bash
git add codebase_context/cli.py
git commit -m "feat: add ccindex CLI with all commands"
```

---

## Chunk 13: mcp_server.py

### Task 13: MCP server

**Files:**
- Create: `codebase_context/mcp_server.py`

- [ ] **Step 1: Implement mcp_server.py**

```python
# codebase_context/mcp_server.py
"""MCP server exposing search_codebase, get_symbol, and get_repo_map tools."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from codebase_context.config import DEFAULT_TOP_K, MCP_LOG_PATH

# ---------------------------------------------------------------------------
# Logging: all output goes to MCP_LOG_PATH, never to stderr/stdout
# (stderr would corrupt the stdio MCP protocol)
# ---------------------------------------------------------------------------

def _setup_logging(project_root: str) -> None:
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

    # Load embedder once at startup
    retriever = Retriever(project_root)
    # Eagerly load the embedding model so first tool call is fast
    try:
        retriever.embedder._get_model()
    except Exception as e:
        logger.warning("Could not pre-load embedding model: %s", e)

    server = Server("codebase-context")

    # -----------------------------------------------------------------------
    # Tool: search_codebase
    # -----------------------------------------------------------------------

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

    import asyncio
    asyncio.run(_run_server(server))


async def _run_server(server) -> None:
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def _handle_search(retriever, arguments: dict):
    from mcp import types
    from codebase_context.config import DEFAULT_TOP_K

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
```

- [ ] **Step 2: Verify import**

```bash
python -c "from codebase_context.mcp_server import run_server; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add codebase_context/mcp_server.py
git commit -m "feat: add MCP server with search_codebase, get_symbol, get_repo_map tools"
```

---

## Chunk 14: Final verification and README

### Task 14: End-to-end smoke test and documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: All tests PASS

- [ ] **Step 2: Smoke test CLI**

```bash
cd /tmp && mkdir cc-smoke-test && cd cc-smoke-test && git init
ccindex init --root .
```
Expected: Completes without error, creates `.codebase-context/`

- [ ] **Step 3: Update README.md**

```markdown
# codebase-context

> A self-contained, locally-running context management tool for Claude Code agents.
> Provides every agent session with a live repo map and on-demand semantic code retrieval
> via an MCP server — no external APIs, no Docker, no shared infrastructure.

## Install

```bash
pip install git+https://github.com/joe8628/codebase-context
```

## Quick Start

```bash
cd my-project
ccindex init
```

This will:
- Parse all `.py`, `.ts`, `.tsx` files
- Build a vector index in `.codebase-context/chroma/`
- Generate `.codebase-context/repo_map.md`
- Add `.codebase-context/` entries to `.gitignore`
- Prompt to add `@.codebase-context/repo_map.md` to `CLAUDE.md`
- Prompt to install a git post-commit hook

## MCP Server Setup

Add to `.claude/mcp.json` (or `~/.claude/mcp.json` for global use):

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

## Available Tools (MCP)

| Tool | Description |
|------|-------------|
| `search_codebase` | Semantic search over your codebase |
| `get_symbol` | Exact symbol name lookup |
| `get_repo_map` | Get fresh repo map mid-session |

## CLI Reference

```
ccindex init            Full index of current project
ccindex update          Incremental index (changed files only)
ccindex watch           Real-time file watcher
ccindex search <query>  Semantic search from terminal
ccindex map             Print repo map to stdout
ccindex stats           Show index statistics
ccindex clear           Delete index and repo map (--confirm required)
ccindex install-hook    Install git post-commit hook
ccindex uninstall-hook  Remove git post-commit hook
ccindex serve           Start MCP server
```

## First Run Note

The first `ccindex init` downloads the embedding model (~550MB) from HuggingFace.
Subsequent runs use the cached model from `~/.cache/huggingface/`.

## Adding Languages

See `CODEBASE_CONTEXT.md` for instructions on adding Go, Rust, or other Tree-sitter grammars.
```

- [ ] **Step 4: Final commit**

```bash
git add README.md
git commit -m "docs: update README with installation and usage instructions"
```

---

## Summary

**Modules to create (in order):**

| # | File | Key responsibility |
|---|------|--------------------|
| 1 | `pyproject.toml` | Packaging, entry points |
| 2 | `codebase_context/__init__.py` | Package version |
| 3 | `codebase_context/config.py` | Language registry, global defaults |
| 4 | `codebase_context/utils.py` | Token counting, gitignore, path helpers |
| 5 | `codebase_context/parser.py` | Tree-sitter symbol extraction |
| 6 | `codebase_context/chunker.py` | Context-enriched chunk building |
| 7 | `codebase_context/embedder.py` | Lazy sentence-transformers wrapper |
| 8 | `codebase_context/store.py` | ChromaDB vector store |
| 9 | `codebase_context/repo_map.py` | Compact markdown repo map |
| 10 | `codebase_context/indexer.py` | Full + incremental indexing pipeline |
| 11 | `codebase_context/retriever.py` | Semantic search + symbol lookup |
| 12 | `codebase_context/watcher.py` | Filesystem watcher + git hooks |
| 13 | `codebase_context/cli.py` | `ccindex` CLI with all commands |
| 14 | `codebase_context/mcp_server.py` | MCP stdio server with 3 tools |
