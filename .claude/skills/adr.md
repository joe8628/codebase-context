---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# adr

## Purpose

Scaffold and maintain Architecture Decision Records (ADRs) in `docs/decisions/`. Each ADR captures a significant architectural choice, the context that led to it, the alternatives considered, and the consequences.

## Trigger

- A significant architectural decision has been made during a session
- User asks to "record this decision" or "write an ADR"
- Architect or code-writer agent identifies a choice worth preserving long-term
- Distinct from `DECISIONS.md` (implementation micro-decisions) — use ADRs for choices that affect the system's structure over time

## Language Support

Language-agnostic. Operates on markdown files only.

## Process

1. Create `docs/decisions/` if it does not exist.
2. Determine the next ADR number by listing existing files in `docs/decisions/` and incrementing.
3. Write the ADR file at `docs/decisions/NNNN-<short-title>.md` using the format below.
4. If an existing ADR is being superseded by this decision, update the old ADR's **Status** field to `Superseded by NNNN`.
5. Print a confirmation: `[adr] Written: docs/decisions/NNNN-<title>.md`

## Output Format

```markdown
# NNNN — <Decision title>

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Deprecated | Superseded by NNNN

## Context

<What situation, constraint, or requirement forced this decision? What was the problem being solved?>

## Decision

<What was decided. State it clearly and directly.>

## Alternatives Considered

- **<Alternative 1>:** <Why it was considered and why it was rejected.>
- **<Alternative 2>:** <Why it was considered and why it was rejected.>

## Consequences

**Positive:**
- <What gets better as a result of this decision>

**Negative:**
- <What gets harder or more constrained as a result>

**Risks:**
- <Any assumption that, if wrong, would make this decision a mistake>
```

## Error Handling

- `docs/decisions/` does not exist: create it before writing
- ADR number collision (two agents writing simultaneously): check the directory again before writing and use the next available number
- Decision is too vague to write a meaningful ADR: prompt the user or agent for the missing context (what problem was being solved, what alternatives were considered)
