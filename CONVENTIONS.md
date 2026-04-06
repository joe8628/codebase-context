# Conventions

<!-- Fill in each section for your project. Remove sections that do not apply. -->
<!-- Agents read this file at session start. Keep it current. -->

---

## Naming Conventions

- **Files:** <kebab-case | snake_case | PascalCase — choose one>
- **Variables:** <camelCase | snake_case>
- **Functions:** <camelCase | snake_case>
- **Classes:** <PascalCase>
- **Constants:** <SCREAMING_SNAKE_CASE>

## File and Directory Structure

<!-- Describe where things live. E.g.: -->
<!-- - `src/` — application source -->
<!-- - `tests/` — test files mirror src/ structure -->
<!-- - `docs/` — documentation only, no code -->

## Error Handling

<!-- Describe your error handling pattern. E.g.: -->
<!-- - Always log before re-raising -->
<!-- - Never swallow exceptions silently -->
<!-- - Use typed errors/exceptions where supported -->

## Logging

<!-- Describe logging conventions. E.g.: -->
<!-- - Use structured logging (JSON) -->
<!-- - Log at INFO for business events, DEBUG for implementation details -->

## Preferred Libraries

| Purpose | Library | Notes |
|---|---|---|
| <purpose> | <library> | <when and how to use it> |

## Dependency Rules

- Never add a dependency without updating `env-setup`
- Never add a dependency without a documented reason in `DECISIONS.md`

## Never Do

- Never hardcode secrets or credentials — use environment variables
- Never use broad exception catches without logging the error
- Never commit commented-out code
- Never use `any` type (TypeScript) or equivalent type erasure
- Never push directly to `main` — use branches and PRs
- <add project-specific rules here>

## Branch Naming

`<type>/<short-description>`

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`

Example: `feat/add-auth`, `fix/null-pointer`

## Commit Message Format

Conventional Commits: `<type>: <short description>`

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`

Example: `feat: add user authentication`, `fix: handle null session token`
