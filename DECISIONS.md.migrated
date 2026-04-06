# Decisions — 2026-03-19

<!-- DECISIONS.md is committed to git — it accumulates across sessions. -->
<!-- One entry per meaningful implementation decision. -->
<!-- Do not record trivial choices. Record choices that a reviewer would ask about. -->

---

## Decision Log

### MCP config target: .claude/settings.json (not mcp.json)
- **Decision:** Write the `mcpServers` entry into `.claude/settings.json`, merging with any existing content.
- **Alternatives considered:** Creating a separate `.claude/mcp.json`; appending raw JSON instructions in a `click.echo`.
- **Rationale:** Claude Code resolves MCP servers from `.claude/settings.json`. A separate `mcp.json` is not read. The old echo pointed at the wrong file entirely.
- **Affected files:** `codebase_context/cli.py`, `tests/test_cli.py`
- **Date:** 2026-03-19

### Skip-before-prompt pattern for idempotent prompts
- **Decision:** Check whether the `codebase-context` MCP entry already exists *before* showing the `click.confirm` prompt, and return early if so (no prompt shown on re-runs).
- **Alternatives considered:** Always show the prompt and skip writing if already present.
- **Rationale:** Avoids annoying the user on `ccindex init` re-runs (e.g. after pulling a new version). Consistent with how `_update_gitignore` silently returns when entries are already present.
- **Affected files:** `codebase_context/cli.py`
- **Date:** 2026-03-19
