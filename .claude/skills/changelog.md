---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# changelog

## Purpose

Generate CHANGELOG entries from git log or the current task list, following the Keep a Changelog format.

## Trigger

- Before a release or version bump
- User asks to "update the CHANGELOG" or "generate release notes"
- Invoked by the planner or docs-writer at the end of a feature cycle

## Language Support

Language-agnostic. Operates on git history and markdown.

## Process

1. Read the existing `CHANGELOG.md` to find the last recorded version and date.
2. Run `git log --oneline <last-tag>..HEAD` to get all commits since the last release. If no tags exist, use the full history.
3. Categorise each commit by its conventional commit type:
   - `feat:` → Added
   - `fix:` → Fixed
   - `docs:` → Changed (documentation)
   - `refactor:` → Changed
   - `perf:` → Changed (performance)
   - `chore:`, `test:`, `build:` → omit from changelog unless significant
   - Breaking change (commit contains `BREAKING CHANGE:`) → add to a **Breaking Changes** section at the top of the entry
4. Deduplicate and consolidate related commits into a single changelog line where appropriate.
5. Write the new `[Unreleased]` block at the top of `CHANGELOG.md` (above any existing `[Unreleased]` block — replace it if it exists).
6. If a version number is provided, replace `[Unreleased]` with `[<version>] — YYYY-MM-DD`.
7. Print a confirmation with the number of entries added.

## Output Format

```markdown
## [Unreleased]

### Breaking Changes
- Remove `--no-context-manager` flag — replaced by `--no-codebase-index`

### Added
- `rig install --no-codebase-index` flag to skip ccindex init
- `issue-logger` agent for persistent issue tracking across sessions
- `test-writer` agent for TDD specification and test coverage auditing

### Fixed
- Pre-commit hook now exits 0 when linting tool is missing rather than blocking commit

### Changed
- `HANDOFF.md` and `DECISIONS.md` are now committed to git for cross-session persistence
- Session start protocol requires `git pull` before reading `HANDOFF.md`
```

## Error Handling

- No `CHANGELOG.md` exists: create it with the standard header and the new `[Unreleased]` block
- No git history (freshly initialised repo): write an `[Unreleased]` block with a note that history is not yet available
- Commit messages do not follow conventional commits format: categorise best-effort and flag that conventional commits would improve future changelog generation
- Version number provided but no tag exists: write the versioned entry and remind the user to create the git tag: `git tag v<version>`
