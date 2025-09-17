# AI Copilot Instructions for workshop-inventory-tracking

## Core Rules

- **NEVER suppress warnings/errors without human approval** - Fix root cause, not symptoms
- **Always use proper type annotations** on all new code
- **Always close resources explicitly** - Use context managers or try/finally
- **Environment must be activated once per terminal session** - Run `eval $(poetry env activate)` at the start of each new terminal session
- **Do not** run the same command multiple times in a row; if this will be needed, then use a temporary file to store the output and analyze it later, such as `cmd > file.txt 2>&1; analyze file.txt; rm -f file.txt`. Be sure to clean up the temporary file after analysis.
- **Always** include the `-f` option when removing files, such as `rm -f file.txt`.

## Rules for Implementing Features and Fixing Bugs / Issues

If you have been assigned an issue to complete or a feature to implement, you MUST ALWAYS follow these rules:

* When beginning work on a new problem/issue, you must identify any areas that you are unclear on or confused about, and you must ask for clarification from a human developer before proceeding.
* Tests may not be skipped, ignored, deleted, disabled, or circumvented without explicit human developer approval.
* You MUST add ttests to cover any new functionality you implement; these should be the minimum necessary to demonstrate the feature works as intended and to cover expected failure modes. Frontend/UI changes MUST be covered by e2e browser tests.
* ALL tests MUST pass for work to be considered ready for review; if you cannot get tests to pass, you MUST ask for help from a human developer, but you must attempt to get all tests to pass before asking for help or asking for a review.
* If you get confused, you must ask for help from a human developer; you must not make assumptions or guesses about what to do next.
* Correctness, quality, and maintainability are more important than speed; you must take the time to do things right, even if it takes longer. You must strive to maintain a clean code base with little to no duplication, clear and consistent style, and good organization.
* Features that are non-trivial in size (i.e. more than a few simple changes) should be broken down into multiple commit-sized chunks, each with a clear purpose and scope and each testable. You must not attempt to implement a large feature in a single step.
* All changes must include updates to relevant documentation (i.e. `README.md` and `docs/*.md`).
* If you become confused or unclear on how to proceed, have to make a significant decision not explicitly included in the implementation plan, or find yourself making changes and then undoing them without a clear and certain path forward, you must stop and ask for human guidance.

## Technology Stack

- Python 3.13, Flask, SQLAlchemy, Alembic
- `nox` and `pytest` for testing

## Resource Management
### Database/SQLAlchemy
- Close sessions: `db.session.close()`, Dispose engines: `db.engine.dispose()`
- Use NullPool for tests, always close SQLite connections explicitly
- Use try/finally blocks for cleanup

### Testing
- Fix ResourceWarnings at source, don't suppress with `warnings.filterwarnings()`
- Don't use `gc.collect()` to mask resource problems
- Test fixtures must cleanup resources they create

## Warning/Error Suppression Policy
**Requires explicit human approval before using:**
- `warnings.filterwarnings()`, `# type: ignore`, `# noqa`, `# pragma: no cover`
- Any pytest skip/ignore markers

**Approval process:**
1. Explain why can't fix at source
2. Document third-party library limitation
3. Prove functionality works despite warning/error
4. Propose minimal suppression scope

## Command Examples
```bash
# FIRST: Activate environment (once per terminal session)
eval $(poetry env activate)

# Then run commands normally (no poetry run prefix needed)
nox -s test

# Linting
nox -s lint

# Analysis pattern
nox -s lint > lint.txt 2>&1
# analyze lint.txt
rm -f lint.txt

# Good resource management
with create_connection() as conn:
    # use conn
    pass  # auto-closed

# Test fixture cleanup
@pytest.fixture
def resource():
    data = create_resource()
    yield data
    cleanup_resource(data)
```
