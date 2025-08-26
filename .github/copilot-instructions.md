# AI Copilot Instructions for workshop-inventory-tracking

## Core Rules
- **NEVER suppress warnings/errors without human approval** - Fix root cause, not symptoms
- **Always use proper type annotations** on all new code
- **Always close resources explicitly** - Use context managers or try/finally
- **Environment must be activated once per terminal session** - Run `eval $(poetry env activate)` at the start of each new terminal session
- **Do not** run the same command multiple times in a row; if this will be needed, then use a temporary file to store the output and analyze it later, such as `cmd > file.txt 2>&1; analyze file.txt; rm -f file.txt`. Be sure to clean up the temporary file after analysis.
- **Always** include the `-f` option when removing files, such as `rm -f file.txt`.
- **Always** run the `format` nox session before running the `lint` session, such as `poetry run nox -s format; poetry run nox -s lint`.
- When working on a problem, **always** ask for human confirmation before making code changes. We value complete understanding and consensus over speed.

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
