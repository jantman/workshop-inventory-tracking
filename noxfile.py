"""
Nox configuration for Workshop Inventory Tracking tests.

Provides consistent test execution across development and CI environments.
"""

import nox

# Python versions to test against
PYTHON_VERSIONS = ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13"]
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
    """Run end-to-end tests with Playwright."""
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")
    
    # Install Playwright browsers
    session.run("python", "-m", "playwright", "install", "--with-deps", "chromium")
    
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
        "--cov-fail-under=80",
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


@nox.session(python=PYTHON_VERSIONS)
def test_matrix(session):
    """Run tests across multiple Python versions."""
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")
    
    session.run(
        "python", "-m", "pytest",
        "-v",
        "-m", "not e2e",
        "--tb=short"
    )


# Default session when running 'nox' without arguments
nox.options.sessions = ["tests", "coverage"]