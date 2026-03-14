# codebase_context/config.py
"""Central configuration: language registry and global defaults."""

import os

# Global defaults (override via environment variables)
EMBED_MODEL      = os.environ.get("CC_EMBED_MODEL", "jinaai/jina-embeddings-v2-base-code")
EMBED_BATCH_SIZE = int(os.environ.get("CC_EMBED_BATCH_SIZE", "32"))
CHROMA_DIR       = os.environ.get("CC_CHROMA_DIR", ".codebase-context/chroma")
REPO_MAP_PATH    = os.environ.get("CC_REPO_MAP_PATH", ".codebase-context/repo_map.md")
INDEX_META_PATH  = os.environ.get("CC_INDEX_META_PATH", ".codebase-context/index_meta.json")
MCP_LOG_PATH     = os.environ.get("CC_MCP_LOG_PATH", ".codebase-context/mcp.log")
DEFAULT_TOP_K    = int(os.environ.get("CC_DEFAULT_TOP_K", "10"))
MAX_CHUNK_TOKENS = int(os.environ.get("CC_MAX_CHUNK_TOKENS", "512"))

# Language registry
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

# Patterns always skipped during indexing (in addition to .gitignore)
ALWAYS_IGNORE: list[str] = [
    "node_modules", "__pycache__", ".git", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "coverage",
    "*.min.js", "*.min.css", "*.lock", "*.map",
    ".codebase-context",
]
