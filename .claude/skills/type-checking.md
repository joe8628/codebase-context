---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# type-checking

## Purpose

Run the type checker for the detected language, interpret the output, and suggest fixes for type errors.

## Trigger

- Explicit user request: "type check", "run mypy", "run tsc"
- Invoked by code-reviewer before producing a verdict
- Invoked automatically by the pre-commit hook
- Invoked by code-writer after completing an implementation

## Language Support

- **Python:** `mypy .`
- **TypeScript:** `tsc --noEmit`
- **C/C++:** compiler warnings via `make` or `cmake --build`

## Process

1. Detect language from project root markers:
   - `pyproject.toml` or `setup.py` → Python
   - `package.json` + `tsconfig.json` → TypeScript
   - `CMakeLists.txt` or `Makefile` → C/C++
2. Check whether the type checker is installed. If not, print the install command and stop.
3. Run the type checker for the detected language.
4. Parse output and list each error with: file path, line number, error code, and description.
5. For each error, suggest a resolution:
   - Missing type annotation → "Add return type or parameter type annotation"
   - Incompatible types → "Cast explicitly or fix the type mismatch at the source"
   - Unknown attribute → "Check the class definition or use `hasattr` guard"
   - `any` type in TypeScript → "Replace with a specific type or union"
6. Print a summary: total errors, overall verdict (clean / has errors).

## Output Format

```
[type-checking] Python — mypy .

  src/models.py:45:12  error  Argument 1 to "process" has incompatible type "str"; expected "int"  [arg-type]
  src/utils.py:12:5   error  Function is missing a return type annotation  [no-untyped-def]

2 errors
Verdict: has errors
```

Clean output:
```
[type-checking] Python — mypy .

Success: no issues found
Verdict: clean
```

## Error Handling

- Type checker not installed:
  - Python: `pip install mypy`
  - TypeScript: `npm install --save-dev typescript`
  - C/C++: ensure compiler is available (`gcc`, `clang`, `g++`, or `clang++`)
- Config file missing (e.g. no `mypy.ini` or `tsconfig.json`): warn and proceed with defaults
- Type checker exits with an internal error (not a type error): print raw output and suggest running the checker manually
- Extremely large number of errors: report the first 20 with a count of remaining — fix the first errors first, as they often cascade
