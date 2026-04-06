---
version: 1.0.0
updated: 2026-03-15
changelog:
  - 1.0.0: initial version
---

# tdd

## Purpose

Guide test-driven development: write a failing test first, implement the minimum code to make it pass, then refactor.

## Trigger

- Before implementing any feature or bugfix
- User asks to "use TDD" or "write tests first"
- Invoked by code-writer at the start of any implementation task

## Language Support

- **Python:** pytest (`pytest <test_file> -v`)
- **TypeScript:** jest or vitest (`npx jest <test_file>` or `npx vitest run <test_file>`)
- **C/C++:** Catch2 or Google Test (`./build/tests` or `ctest`)

## Process

1. Identify the unit of behaviour to implement. Write it as a one-sentence specification: "Given X, when Y, then Z."
2. Write the smallest possible failing test that captures that specification. The test must:
   - Test one behaviour only
   - Have a name that describes the expected behaviour (not the implementation)
   - Be runnable immediately (no missing imports, no unresolved dependencies)
3. Run the test. Confirm it fails with the expected failure message (not an import error or syntax error — a genuine assertion failure or "not implemented" error).
4. Write the minimum implementation code to make the test pass. Resist adding anything not required by the current test.
5. Run the test again. Confirm it passes.
6. Check whether existing tests still pass. If any broke, fix them before continuing.
7. Refactor if needed: improve names, remove duplication, simplify logic. Tests must still pass after refactoring.
8. Commit: stage the test file and implementation file together.
9. Repeat from step 1 for the next behaviour.

## Output Format

No file output. Inline guidance during the session. Each cycle produces:
- One new test (committed)
- Minimum implementation to pass it (committed)
- All prior tests still passing

## Error Handling

- Test runner not installed: print the install command for the detected language and stop
  - Python: `pip install pytest`
  - TypeScript: `npm install --save-dev jest` or `npm install --save-dev vitest`
  - C/C++: link to Catch2 or Google Test setup docs
- Test fails with an import error instead of an assertion failure: fix the import before treating it as a red test — an import error means the test is not yet runnable, not that it is failing correctly
- Implementation passes all tests on the first attempt without any change: the test was not actually failing — go back to step 3 and verify the red state
