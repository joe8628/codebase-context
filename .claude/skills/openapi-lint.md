---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# openapi-lint

## Purpose

Validate and lint OpenAPI (3.x) or AsyncAPI specs, report violations, and optionally generate route stubs from the spec.

## Trigger

- An OpenAPI or AsyncAPI spec file exists and has been modified
- User asks to "validate the API spec" or "lint the OpenAPI"
- Invoked by docs-writer or code-reviewer when API documentation is in scope
- Before generating client SDKs or server stubs from a spec

## Language Support

Language-agnostic. Operates on YAML or JSON spec files.

**Tool used:** `npx @redocly/cli lint` (requires Node.js). Falls back to structural validation via spec parsing if Redocly is unavailable.

## Process

1. Locate the spec file: look for `openapi.yaml`, `openapi.json`, `asyncapi.yaml`, `asyncapi.json`, or any file referenced in `package.json` scripts as an API spec.
2. Check whether `npx @redocly/cli` is available.
3. If available: run `npx @redocly/cli lint <spec-file>` and parse the output.
4. If not available: perform structural validation manually:
   - Confirm required top-level fields (`openapi`/`asyncapi`, `info`, `paths`/`channels`)
   - Check all `$ref` references resolve to defined components
   - Check all path operations have at least one response defined
   - Check all request bodies have a `content` field with at least one media type
5. Report violations grouped by severity: error, warning, info.
6. For each violation: file path, line number (if available), rule name, description, and suggested fix.
7. If `--generate-stubs` is requested: for each path and method in the spec, generate a minimal route stub in the detected server language and print to stdout.
8. Print a summary and verdict.

## Output Format

```
[openapi-lint] Validating openapi.yaml

  paths./users.get: missing operationId  [operation-operationId]
  paths./users/{id}.delete: response 404 not defined  [operation-4xx-response]
  components.schemas.User: property 'email' missing format  [info]

3 issues (0 errors, 2 warnings, 1 info)
Verdict: needs fixes
```

Clean:
```
[openapi-lint] Validating openapi.yaml

No issues found.
Verdict: clean
```

## Error Handling

- No spec file found: print a list of locations checked and stop
- Spec file is not valid YAML or JSON: report the parse error with line number and stop
- `npx` not available: fall back to manual structural validation and note that full rule coverage requires Node.js
- `$ref` cycle detected: report the cycle path and stop — circular references are always an error
