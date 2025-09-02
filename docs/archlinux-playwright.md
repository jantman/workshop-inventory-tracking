# Arch Linux Playwright E2E Testing Issues

## Current Status

The E2E testing framework has been successfully implemented with:
- ✅ Playwright E2E testing infrastructure
- ✅ Page Object Model classes for maintainable tests
- ✅ Happy-path E2E tests for critical workflows (add item, search, list view)
- ✅ Test server management and data setup
- ✅ Fixture scope fixes for Playwright compatibility

## The Problem

Running `nox -s e2e` fails on Arch Linux because:
- Playwright's `playwright install --with-deps chromium` command tries to install system dependencies
- This requires sudo privileges, which nox sessions don't have by default
- The command fails with permission errors during system package installation

## Error Details

The nox e2e session currently runs:
```python
session.run("python", "-m", "playwright", "install", "--with-deps", "chromium")
```

The `--with-deps` flag attempts to install system dependencies like:
- libatk-bridge2.0-0
- libdrm2
- libgtk-3-0
- And other chromium browser dependencies

These require root access on Arch Linux.

## Solutions to Try

### Option 1: Manual System Dependency Installation (Recommended)
Install Playwright's system dependencies once on the Arch system:

```bash
# Install Playwright system dependencies manually (requires sudo)
sudo playwright install-deps chromium

# Then nox can install just the browser binaries without sudo
nox -s e2e
```

### Option 2: Docker-based E2E Testing
Create a containerized testing environment:

```dockerfile
# Dockerfile.e2e
FROM python:3.13-slim
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements*.txt ./
RUN pip install -r requirements-test.txt
RUN playwright install --with-deps chromium
CMD ["python", "-m", "pytest", "-v", "-m", "e2e"]
```

Then run with:
```bash
docker build -f Dockerfile.e2e -t workshop-e2e .
docker run -v $(pwd):/app workshop-e2e
```

### Option 3: Arch-Specific Package Installation
Use Arch's package manager for browser dependencies:

```bash
# Install chromium via pacman
sudo pacman -S chromium
```

Then configure Playwright to use system chromium (requires environment variable or config changes).

### Option 4: Modified nox Session (Skip System Dependencies)
Update the e2e session to skip system dependencies:

```python
@nox.session(python=DEFAULT_PYTHON)
def e2e(session):
    """Run end-to-end tests with Playwright."""
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")
    
    # Install only browser binaries (no system deps)
    session.run("python", "-m", "playwright", "install", "chromium")
    
    # Run E2E tests
    session.run("python", "-m", "pytest", "-v", "-m", "e2e", "--tb=short", *session.posargs)
```

This may require pre-installing system dependencies manually.

## Files Involved

- `noxfile.py` - Contains the e2e session configuration
- `tests/conftest.py` - E2E test fixtures (scope issues already fixed)
- `tests/e2e/test_server.py` - Test server management
- `tests/e2e/pages/` - Page Object Model classes
- `tests/e2e/test_*.py` - E2E test implementations

## Testing Progress

Current testing milestone completion:
- ✅ **Milestone 1**: Unit Testing Foundation & Storage Abstraction
- ✅ **Milestone 2**: E2E Testing Infrastructure & Happy-Path Tests
- 🚧 **Issue**: E2E tests can't run due to Playwright system dependency installation on Arch Linux

## Next Steps

1. **Try Option 1 first** - Install system dependencies manually with `sudo playwright install-deps chromium`
2. **Test the fix** by running `nox -s e2e` 
3. **If Option 1 fails**, try Option 4 (modify nox session) or Option 2 (Docker)
4. **Document the working solution** in this file for future reference
5. **Continue with any remaining testing work** or move to deployment preparation

## Commands to Test When Resuming

```bash
# Test unit tests (should work)
nox -s tests

# Test coverage (should work) 
nox -s coverage

# Test E2E (currently failing)
nox -s e2e

# Manual E2E test (after fixing dependencies)
python -m pytest -v -m e2e
```