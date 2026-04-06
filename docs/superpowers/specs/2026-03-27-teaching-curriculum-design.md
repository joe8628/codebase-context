# Teaching Curriculum Design — codebase-context

**Date:** 2026-03-27
**Status:** Approved
**Output file:** `docs/teaching/CURRICULUM.md`

---

## Objective

Produce a single curriculum document that guides a teacher through delivering a complete lecture series on the `codebase-context` repo. The document must be self-contained and continuable — any future Claude Code session must be able to read it and add content coherently.

## Audience

Mixed: developers new to this specific repo, and developers who may also be new to Claude Code and the MCP ecosystem.

## Delivery Format

Lecture + code snippets. No hands-on labs. Visual aids noted as placeholders for future production.

---

## Curriculum Structure: Option B — Inside-Out

Sessions build on each other in dependency order, starting from the core data model and working outward to user-facing surfaces and subsystems.

| # | Session Title | Depends On |
|---|---|---|
| 1 | What Is codebase-context and Why It Exists | — |
| 2 | Core Data Model: Symbol and Chunk | 1 |
| 3 | The Parser | 2 |
| 4 | The Chunker | 2, 3 |
| 5 | The Embedder | 4 |
| 6 | The Vector Store | 5 |
| 7 | The Retriever | 6 |
| 8 | The MCP Server | 7 |
| 9 | The CLI and File Watcher | 3–8 |
| 10 | The LSP Integration | 8 |
| 11 | The Memgram Memory Layer | 8 |
| 12 | The Repo Map | 2–8 |

---

## Output File Spec: `docs/teaching/CURRICULUM.md`

### Header block (YAML front matter)
```yaml
---
objective: >
  A lecture-series guide for teaching the architecture and implementation of
  codebase-context. Covers every major component in dependency order, from
  core data model to user-facing CLI and subsystems.
audience: >
  Developers new to this repo; some may also be new to Claude Code and MCP.
format: Lecture + code snippets. Visual aid placeholders inline.
continuation_instructions: >
  This file is incrementally filled in across multiple Claude Code sessions.
  Each session covers one topic from the session outline below.
  When adding content: (1) read this header, (2) read the session stub you
  are filling in, (3) use the repo map and code-explorer agent to verify
  all code references before writing them, (4) do not modify stubs for
  sessions you are not currently filling in.
status: draft
last_updated: YYYY-MM-DD
---
```

### Per-session stub format
Each of the 12 sessions follows this structure:

```markdown
## Session N — [Title]

**Learning objectives:**
- ...
- ...
- ...

**Key concepts:** [comma-separated list]

**Primary source files:** [file paths]

<!-- AID: [diagram | code-walkthrough | sequence-diagram] — [description] -->

### Content

> _Stub — to be filled in._
```

---

## Diagram Strategy

Inline Mermaid diagrams used where flow or relationships need visualization. Notes for richer visual aids are left as HTML comments:

```
<!-- AID: sequence-diagram — Show the full indexing pipeline from CLI call to vector upsert -->
<!-- AID: diagram — Component map of MCP server tools and their handlers -->
```

These are deferred to a later production pass.

---

## Constraints

- One output file only: `docs/teaching/CURRICULUM.md`
- Do not create the `docs/teaching/` directory without confirming it does not exist
- Session body content is filled in interactively, not all at once
- All code references must be verified against the actual repo before being written into sessions
