"""
Nox configuration for Workshop Inventory Tracking tests.

Provides consistent test execution across development and CI environments.
"""

import nox

# Python version
DEFAULT_PYTHON = "3.13"

# Package locations
PACKAGE = "app"
TEST_PATHS = ["tests"]


@nox.session(python=DEFAULT_PYTHON)
def tests(session):
    """Run unit tests with pytest."""
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")
    
    # Run unit tests only (exclude e2e)
    session.run(
        "python", "-m", "pytest",
        "-v",
        "-m", "not e2e",
        "--tb=short",
        *session.posargs
    )


@nox.session(python=DEFAULT_PYTHON)
def e2e(session):
    """Run end-to-end tests with Playwright.
    
    Note: Requires Playwright browsers to be installed:
    playwright install --with-deps chromium
    """
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")
    
    # Install Playwright browsers (without --with-deps on Arch Linux due to sudo issues)
    session.run("python", "-m", "playwright", "install", "chromium")
    
    # Run E2E tests only
    session.run(
        "python", "-m", "pytest",
        "-v", 
        "-m", "e2e",
        "--tb=short",
        *session.posargs
    )


@nox.session(python=DEFAULT_PYTHON)
def coverage(session):
    """Generate test coverage report."""
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")
    
    # Run tests with coverage
    session.run(
        "python", "-m", "pytest",
        "-v",
        "-m", "not e2e",  # Unit tests only for coverage
        f"--cov={PACKAGE}",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml",
        "--cov-fail-under=45",
        *session.posargs
    )
    
    session.log("Coverage report generated in htmlcov/index.html")


@nox.session(python=DEFAULT_PYTHON)
def lint(session):
    """Run linting with flake8 (future enhancement)."""
    session.install("-r", "requirements-test.txt")
    session.install("flake8", "black", "isort")
    
    session.run("flake8", PACKAGE, *TEST_PATHS)
    session.run("black", "--check", "--diff", PACKAGE, *TEST_PATHS)
    session.run("isort", "--check-only", "--diff", PACKAGE, *TEST_PATHS)




# Default session when running 'nox' without arguments
nox.options.sessions = ["tests", "coverage"]