---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# env-setup

## Purpose

Document and scaffold the local development environment: generate `.env.example`, list required system dependencies, and write setup steps. Update automatically when new dependencies are added.

## Trigger

- `rig install` has just run on a new project
- A new dependency has been added to the project
- User asks to "update env-setup" or "document the dev environment"
- Invoked by code-writer when adding a dependency that requires environment configuration

## Language Support

- **Python:** reads `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`
- **TypeScript:** reads `package.json`, `package-lock.json`
- **C/C++:** reads `CMakeLists.txt`, `conanfile.txt`, `vcpkg.json`

## Process

1. Read the project's dependency manifest for the detected language.
2. Read any existing `.env.example` — preserve existing entries, only add new ones.
3. Identify all environment variables referenced in source files:
   - Python: `os.environ`, `os.getenv`, `dotenv`
   - TypeScript: `process.env`
   - C/C++: `getenv()`
4. For each environment variable found, add an entry to `.env.example`:
   - If the variable is a secret (key, token, password, secret in the name): set value to `your-<name>-here`
   - If the variable is a non-secret config value: set a safe default if one is evident from the code
5. Identify required system dependencies (tools that must be installed separately):
   - Python: check for `subprocess` calls, system tool imports, or build extensions
   - TypeScript: check for native addons, CLI tools called via `child_process`
   - C/C++: check `find_package()` calls in `CMakeLists.txt`
6. Write or update `docs/env-setup.md` with the format below.
7. Print a confirmation with the number of environment variables documented.

## Output Format

`.env.example`:
```
# Database
DATABASE_URL=postgresql://localhost:5432/mydb

# Auth
JWT_SECRET=your-jwt-secret-here
JWT_EXPIRY_SECONDS=3600

# External APIs
STRIPE_API_KEY=your-stripe-api-key-here
```

`docs/env-setup.md`:
```markdown
# Environment Setup

## System Requirements

- <runtime> <minimum version>
- <tool> — <what it's used for>

## Installation

```bash
<language-specific install command>
```

## Environment Variables

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `JWT_SECRET` | Yes | Secret key for signing JWTs |
| `JWT_EXPIRY_SECONDS` | No | Token lifetime in seconds (default: 3600) |

## Running Locally

```bash
<exact command to start the development server or run the application>
```

## Running Tests

```bash
<exact test command>
```
```

## Error Handling

- No dependency manifest found: warn and generate a minimal `.env.example` and `docs/env-setup.md` with placeholder sections
- Environment variable found in code but purpose is unclear: add it to `.env.example` with a `# TODO: document this variable` comment
- `.env` file exists (not `.env.example`): warn that `.env` should be in `.gitignore` and should not be committed; check `.gitignore` and add it if missing
