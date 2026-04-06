---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# dependency-audit

## Purpose

Audit project dependencies for known vulnerabilities and summarise findings by severity.

## Trigger

- Before any release or merge to main
- After adding a new dependency
- Invoked by security-auditor as part of its process
- Explicit user request: "audit dependencies", "check for vulnerabilities"

## Language Support

- **Python:** `pip-audit`
- **TypeScript/JavaScript:** `npm audit`
- **C/C++:** No automated tool — follow the manual CVE check guidance in the Process section

## Process

1. Detect language from project root markers.
2. Check whether the audit tool is installed. If not, print the install command and stop.
3. Run the audit tool:
   - Python: `pip-audit`
   - TypeScript: `npm audit --json`
   - C/C++: proceed to manual guidance (step 6)
4. Parse output and group findings by severity: **critical**, **high**, **moderate**, **low**.
5. For each finding, report:
   - Package name and version
   - CVE ID (if available)
   - Severity
   - Description of the vulnerability
   - Fix: upgrade path or patch version
6. C/C++ manual guidance: list all direct dependencies from `CMakeLists.txt` or `conanfile.txt`. For each, search the [NVD CVE database](https://nvd.nist.gov/) for the package name and version. Report any findings manually.
7. Print a summary table and an overall verdict.

## Output Format

```
[dependency-audit] Python — pip-audit

  Package       Version  Severity  CVE              Description
  requests      2.27.1   HIGH      CVE-2023-32681   Proxy auth header leak
  urllib3       1.26.5   MODERATE  CVE-2023-43804   Cookie header forwarding

2 vulnerabilities (1 high, 1 moderate, 0 critical)
Verdict: action required — fix high severity findings before release
```

Clean output:
```
[dependency-audit] Python — pip-audit

No known vulnerabilities found.
Verdict: clean
```

## Error Handling

- Audit tool not installed:
  - Python: `pip install pip-audit`
  - TypeScript: `npm audit` is built into npm — ensure npm is installed
- Audit tool returns no dependency manifest: warn that no lockfile or requirements file was found; the audit may be incomplete
- Network unavailable: warn that the vulnerability database could not be reached and results may be stale
- Critical severity finding: always flag with `ACTION REQUIRED` regardless of context — do not soften the verdict
