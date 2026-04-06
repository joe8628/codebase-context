---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# readme-gen

## Purpose

Generate a README skeleton from the project tree and entry points. Use when no README exists or when the existing one needs a full structural rebuild.

## Trigger

- No `README.md` exists in the project root
- User asks to "generate a README" or "rebuild the README"
- Invoked by docs-writer when the README structure is too outdated to update incrementally

## Language Support

Language-agnostic. Inspects the project tree and detects language-specific conventions for install/run commands.

## Process

1. Use `get_repo_map` to understand the full project structure.
2. Identify the project entry point:
   - Python: `main.py`, `__main__.py`, or the `[project.scripts]` entry in `pyproject.toml`
   - TypeScript: `main` field in `package.json` or `src/index.ts`
   - C/C++: primary target in `CMakeLists.txt` or `Makefile`
3. Detect the install and run commands for the identified language and toolchain.
4. Read any existing `README.md` — preserve any sections that contain accurate, specific content.
5. Generate the README with the sections below. Fill in every section from evidence in the codebase — do not use placeholder text in sections you can answer from reading the code.
6. Write the result to `README.md`.

## Output Format

```markdown
# <Project Name>

<One-sentence description of what the project does.>

## Requirements

<System dependencies, runtime version, and any prerequisites.>

## Installation

```bash
<exact install command>
```

## Usage

```bash
<exact run command with a realistic example>
```

## Project Structure

<Brief description of the top-level directories and what they contain.>

## Development

<How to run tests, linting, and type-checking.>

## Contributing

<How to contribute — branch naming, commit format, PR process.>

## License

<License name and file reference.>
```

## Error Handling

- Project entry point not identifiable: generate the skeleton with a `<!-- TODO -->` marker in the Usage section and note what to fill in
- Existing README has custom sections not in the template: preserve them below the generated sections
- `get_repo_map` returns no results (empty project): generate a minimal skeleton with all sections marked `<!-- TODO -->`
