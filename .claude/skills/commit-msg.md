---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# commit-msg

## Purpose

Generate a conventional commit message from the staged diff, eliminating manual commit message decisions.

## Trigger

- User asks for a commit message
- End of a code-writer or any implementation session before committing
- Invoked explicitly: "use commit-msg skill"

## Language Support

Language-agnostic. Operates on the git diff, not source code.

## Process

1. Run `git diff --staged` to read the full staged diff.
2. If there are no staged changes, print a warning and stop:
   ```
   [commit-msg] No staged changes found. Stage your changes first: git add <files>
   ```
3. Identify the nature of the changes:
   - New functionality added → `feat`
   - Bug fixed → `fix`
   - Documentation only → `docs`
   - Refactoring with no behaviour change → `refactor`
   - Test additions or fixes → `test`
   - Build, tooling, or config changes → `chore`
   - Performance improvement → `perf`
4. Identify the scope if obvious (e.g. a module name, component, or subsystem).
5. Write a short description: imperative mood, lowercase, no trailing period, under 72 characters total including type and scope.
6. If the change is complex (multiple concerns, non-obvious rationale), write a body: one blank line after the subject, then wrapped paragraphs explaining *why*, not *what*.
7. Print the commit message to stdout.

## Output Format

Simple change:
```
feat(auth): add JWT token validation
```

Complex change:
```
fix(session): prevent token expiry race condition

Sessions were being invalidated mid-request when the expiry check ran
concurrently with a refresh. Added a lock around the check-and-refresh
sequence to ensure atomicity.
```

## Error Handling

- No staged changes: print warning, stop — do not generate a message for an empty diff
- Diff is too large to reason about as a single unit: warn that the change should be split into smaller commits, then generate the best possible message for the combined diff
- Change spans multiple unrelated concerns: flag it and suggest splitting before generating the message
