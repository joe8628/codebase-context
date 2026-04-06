---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# linting

## Purpose

Run and interpret linting for the detected language, report violations with file and line references, and suggest fixes for common patterns.

## Trigger

- Explicit user request: "lint", "run linter", "check style"
- Invoked by code-reviewer before producing a verdict
- Invoked automatically by the pre-commit hook
- Invoked by code-writer after completing an implementation

## Language Support

- **Python:** `ruff check .`
- **TypeScript/JavaScript:** `eslint .`
- **C/C++:** `clang-tidy` (if available)

## Process

1. Detect language from project root markers:
   - `pyproject.toml` or `setup.py` → Python
   - `package.json` → TypeScript/JavaScript
   - `CMakeLists.txt` or `Makefile` → C/C++
2. Check whether the linter is installed. If not, print the install command and stop.
3. Run the linter for the detected language.
4. Parse output and group violations by severity (error, warning, info).
5. For each violation, report: file path, line number, rule ID, and description.
6. For common violation patterns, suggest the fix inline:
   - Unused imports → "Remove the import or use the symbol"
   - Line too long → "Split the line or shorten the expression"
   - Missing whitespace → "Add whitespace per style rules"
   - Unused variable → "Remove the variable or prefix with `_` if intentionally unused"
7. Print a summary: total violations by severity, overall verdict (clean / needs fixes).

## Output Format

```
[linting] Python — ruff check .

  src/auth.py:14:1  E401  Multiple imports on one line
  src/auth.py:32:80 E501  Line too long (92 > 79 characters)
  tests/test_auth.py:8:5  F401  'os' imported but unused

3 violations (0 errors, 3 warnings)
Verdict: needs fixes
```

Clean output:
```
[linting] Python — ruff check .

0 violations
Verdict: clean
```

## Error Handling

- Linter not installed:
  - Python: `pip install ruff`
  - TypeScript: `npm install --save-dev eslint`
  - C/C++: install via system package manager (e.g. `apt install clang-tidy`)
- Config file missing (e.g. no `.eslintrc`): warn that linting may use defaults, proceed anyway
- Linter crashes or returns an unexpected error: print the raw output and suggest running the linter manually to diagnose
