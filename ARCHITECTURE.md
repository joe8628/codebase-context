# Architecture

## Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Parsing | `tree-sitter` + `tree-sitter-python` / `tree-sitter-typescript` | AST symbol extraction |
| Embedding | `fastembed` + `jinaai/jina-embeddings-v2-base-code` | Local code embeddings via ONNX Runtime (768-dim, no torch/CUDA) |
| Vector store | `chromadb` (embedded, no server) | ANN search + metadata filtering |
| CLI | `click` | `ccindex` command-line interface |
| MCP server | `mcp` (stdio transport) | Tool exposure to Claude Code agents |
| File watching | `watchdog` | Real-time incremental reindexing |
| Gitignore | `pathspec` | `.gitignore`-aware file discovery |

All components run locally. No external services, no API keys beyond Claude itself.

---

## Module Dependency Graph

```
config.py          ← no deps; defines LANGUAGES, paths, constants
    │
utils.py           ← config
    │
parser.py          ← config              → tree-sitter grammars
    │
chunker.py         ← parser, config, utils
    │
embedder.py        ← config              → sentence-transformers (lazy load)
    │
store.py           ← chunker, config, utils  → chromadb
    │
repo_map.py        ← parser, config
    │
indexer.py         ← chunker, embedder, parser, repo_map, store, utils
    │
retriever.py       ← store, embedder, config
    │
watcher.py         ← indexer, config, utils  → watchdog
    │
cli.py             ← indexer, retriever, watcher, utils, config  → click
    │
mcp_server.py      ← retriever, config  → mcp
```

---

## Functional Diagram

### Indexing Pipeline (`ccindex init` / `ccindex update`)

```
Source files (.py / .ts / .tsx)
        │
        ▼
  discover_files()        gitignore + ALWAYS_IGNORE + LANGUAGES filter
        │
        ▼
  parser.parse_file()     tree-sitter AST → list[Symbol]
        │                 (name, type, signature, source, calls, parent)
        ▼
  chunker.build_chunks()  Symbol → Chunk
        │                 adds "# filepath / # type" context prefix
        │                 truncates at 512 tokens; full source in metadata
        ▼
  embedder.embed()        Chunk.text → float[768]  (batched, lazy model load)
        │
        ▼
  store.upsert()          (chunk, vector) → ChromaDB  (cosine space)
        │
        ▼
  repo_map.generate()     Symbol signatures → .codebase-context/repo_map.md
        │
        ▼
  save_index_meta()       file mtimes → .codebase-context/index_meta.json
```

### Retrieval Pipeline (MCP tool call / `ccindex search`)

```
Agent query: "rate limiting middleware"
        │
        ▼
  embedder.embed_one()    query → float[768]
        │
        ▼
  store.search()          ANN search, optional language/filepath filter
        │                 returns SearchResult(chunk_text, metadata, score)
        ▼
  Retriever.search()      deduplicate by filepath+symbol, rank by score
        │
        ▼
  MCP TextContent / CLI   JSON array or formatted markdown
```

### Real-time Watcher (`ccindex watch`)

```
File saved
    │
    ▼
watchdog event
    │
    ▼
2s debounce (batch rapid saves)
    │
    ├─ created/modified → store.delete_by_filepath()
    │                    → indexer.index_file()
    │
    └─ deleted          → indexer.remove_file()
    │
    ▼
repo_map.write_repo_map()
```

---

## Per-Project Isolation

Each project gets its own `.codebase-context/` directory:

```
my-project/
└── .codebase-context/
    ├── chroma/           ← ChromaDB vector index (gitignored)
    ├── repo_map.md       ← static context injected into every Claude session
    ├── index_meta.json   ← file mtimes for incremental reindex (gitignored)
    └── mcp.log           ← MCP server log (gitignored)
```

ChromaDB collection name = `slugify(abs_project_path)` — guarantees no cross-project collisions even if a single ChromaDB instance were shared.

---

## MCP Tools

| Tool | Input | Output |
|------|-------|--------|
| `search_codebase` | `query`, `top_k`, `language?`, `filepath_contains?` | JSON array of ranked symbols |
| `get_symbol` | `name` (exact, case-sensitive) | JSON array of all matches |
| `get_repo_map` | — | Full `repo_map.md` string |
