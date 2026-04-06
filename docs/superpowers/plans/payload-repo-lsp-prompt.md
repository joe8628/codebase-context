# Payload-Repo Update Prompt — LSP Tool Integration

Use this prompt in a Claude Code session opened inside `~/github-repos/payload-repo`.

---

## Prompt

```
Update two template files in this repo to reflect that `ccindex serve` now exposes
5 LSP code navigation tools alongside the existing 3 semantic search tools.
Do not modify any other files. Do not create any new files.

---

### File 1: targets/claude-code/settings.json.template

Add three binaries to the `tools.bash.allowedCommands` array:
  - "pyright-langserver"
  - "typescript-language-server"
  - "clangd"

Insert them after the existing "ccindex" entry. The final allowedCommands array
should be (in this order):

  "git", "python", "python3", "node", "npm", "npx", "tsc", "mypy", "ruff",
  "eslint", "clang", "clang++", "make", "cmake", "pip", "pip3", "pip-audit",
  "npm audit", "ccindex", "pyright-langserver", "typescript-language-server", "clangd"

No other changes to settings.json.template.

---

### File 2: targets/claude-code/CLAUDE.md.template

Append the following section at the very end of the file (after the last line of
existing content). Insert one blank line before the new section:

---

## Code Navigation (LSP)

LSP tools are available via the `codebase-context` MCP server.
Use them in this order before reading files:

1. `get_signature` — understand a symbol's type and docstring before reading its file
2. `get_call_hierarchy` — decide which related files are worth reading
3. `find_definition` — locate a symbol's definition across files
4. `find_references` — find all usages before making a change
5. `warm_file` — pre-warm the LSP server for a file after opening it

**Do not read entire files speculatively.** Prefer LSP tools for navigation.
`read_file` only after you know exactly which file and lines matter.

LSP tools gracefully degrade: if the required binary (pyright-langserver,
typescript-language-server, clangd) is not installed, the tool returns
`{"error": "server_unavailable"}` — handle this by falling back to
`search_codebase` or `get_symbol`.

---

After making both changes, run:
  git diff
and confirm the diff shows only the two expected additions before committing.
Commit with: git commit -m "feat: add LSP tool entries to claude-code templates"
```
