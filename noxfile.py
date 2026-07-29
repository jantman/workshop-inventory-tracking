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
    
    # Log installed packages for build record
    session.log("Installed packages:")
    session.run("pip", "freeze")
    
    # Run unit tests only (exclude e2e and integration)
    session.run(
        "python", "-m", "pytest",
        "-v",
        "--blockage",
        "-m", "not e2e and not integration",
        "--tb=short",
        *session.posargs
    )


@nox.session(python=DEFAULT_PYTHON)
def doctests(session):
    """Run the docstring examples in the pure utility modules (AD-4).

    The explicit ``app/utils`` path argument is load-bearing: it is the only
    thing confining ``--doctest-modules`` to the pure-utils package, and it is
    what overrides the ini's ``testpaths = tests``. Remove it and pytest falls
    back to ``testpaths``, running the whole unit/e2e suite under
    ``--doctest-modules`` and collecting no doctests from ``app/`` at all --
    a green session that tested nothing it exists for. New modules added under
    ``app/utils`` are picked up automatically.

    pytest.ini is live (it declares ``[pytest]``), so its ``addopts`` apply
    here too; ``--doctest-modules`` is deliberately kept on the command line
    rather than in ``addopts`` because it must not leak into the other
    sessions.

    Note these modules are pure in the AD-4 sense (no Flask/DB logic), but the
    collector imports them package-qualified as ``app.utils.X``, which executes
    ``app/__init__.py`` and therefore ``config.py``/``.env``. An import-time
    failure there fails this session too.
    """
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")

    # Log installed packages for build record
    session.log("Installed packages:")
    session.run("pip", "freeze")

    # Run doctests from the pure utils package only
    session.run(
        "python", "-m", "pytest",
        "-v",
        "--doctest-modules",
        "--blockage",
        "app/utils",
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
    
    # Log installed packages for build record
    session.log("Installed packages:")
    session.run("pip", "freeze")
    
    # Install Playwright browsers
    # Use --with-deps in CI environments, but not locally on Arch Linux to avoid sudo issues
    import os
    if os.environ.get('CI') == 'true':
        session.run("python", "-m", "playwright", "install", "--with-deps", "chromium")
    else:
        session.run("python", "-m", "playwright", "install", "chromium")
    
    # Run E2E tests only with retry logic
    session.run(
        "python", "-m", "pytest",
        "-v", 
        "--durations=20",
        "-m", "e2e",
        "--tb=short",
        "--reruns=3",          # Retry failed tests up to 3 times
        "--reruns-delay=2",    # Wait 2 seconds between retries
        *session.posargs
    )


@nox.session(python=DEFAULT_PYTHON)
def integration(session):
    """Run integration tests against a real MariaDB database.

    Locally the session-scoped ``mariadb_testcontainer`` fixture starts a
    ``mariadb:11.8`` container and exports ``SQLALCHEMY_DATABASE_URI``; under
    ``CI=true`` that fixture yields None and the ``TEST_DB_*``-derived
    ``TestConfig`` URL points at the workflow's service container. Either way
    Docker (or a reachable MariaDB) is a hard requirement of this session --
    these tests exist precisely because SQLite cannot stand in for the backend.

    Deliberately NO ``--blockage``: unlike ``tests``, this session must open a
    real TCP socket to the database, and pytest-blockage would sever it.
    """
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")

    # Log installed packages for build record
    session.log("Installed packages:")
    session.run("pip", "freeze")

    # Integration tests only, scoped BOTH ways. The explicit path is what keeps
    # the run from importing every module in tests/e2e/ just to deselect it --
    # an import-time error anywhere in that tree would otherwise fail this
    # session for a reason having nothing to do with MariaDB. pytest.ini's
    # ``testpaths = tests`` is live but far too broad for that, and the
    # explicit path overrides it. The marker stays as the second net, and
    # tests/integration/conftest.py applies it structurally so no test can drop
    # out of the selection.
    session.run(
        "python", "-m", "pytest",
        "-v",
        "-m", "integration",
        "tests/integration",
        "--tb=short",
        *session.posargs
    )


@nox.session(python=DEFAULT_PYTHON)
def coverage(session):
    """Generate test coverage report."""
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")
    
    # Log installed packages for build record
    session.log("Installed packages:")
    session.run("pip", "freeze")
    
    # Run tests with coverage
    session.run(
        "python", "-m", "pytest",
        "-v",
        # Unit tests only for coverage. Integration is excluded alongside e2e:
        # it needs a live MariaDB and a real socket, which a coverage run has
        # no business requiring.
        "-m", "not e2e and not integration",
        f"--cov={PACKAGE}",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml",
        "--cov-fail-under=1",
        *session.posargs
    )
    
    session.log("Coverage report generated in htmlcov/index.html")


@nox.session(python=DEFAULT_PYTHON)
def lint(session):
    """Run linting with flake8 (future enhancement)."""
    session.install("-r", "requirements-test.txt")
    session.install("flake8", "black", "isort")

    # Log installed packages for build record
    session.log("Installed packages:")
    session.run("pip", "freeze")

    session.run("flake8", PACKAGE, *TEST_PATHS)
    session.run("black", "--check", "--diff", PACKAGE, *TEST_PATHS)
    session.run("isort", "--check-only", "--diff", PACKAGE, *TEST_PATHS)


@nox.session(python=DEFAULT_PYTHON)
def screenshots(session):
    """Generate all documentation screenshots (headed browser mode for development).

    This will open visible browser windows during screenshot generation.
    Use this for development and debugging.

    Example:
        nox -s screenshots
    """
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")

    # Install Playwright browsers
    session.run("python", "-m", "playwright", "install", "chromium")

    session.log("🖼️  Generating documentation screenshots...")

    # Run screenshot tests only
    session.run(
        "python", "-m", "pytest",
        "tests/e2e/test_screenshot_generation.py",
        "-m", "screenshot",
        "-v",
        *session.posargs
    )

    session.log("✅ Screenshot generation complete!")
    session.log("📁 Screenshots saved to: docs/images/screenshots/")


@nox.session(python=DEFAULT_PYTHON)
def screenshots_headless(session):
    """Generate screenshots in headless mode (CI/CD).

    This runs browsers in headless mode (no visible windows).
    Use this for CI/CD pipelines.

    Example:
        nox -s screenshots_headless
    """
    session.install("-r", "requirements.txt")
    session.install("-r", "requirements-test.txt")

    # Install Playwright browsers with deps for CI
    import os
    if os.environ.get('CI') == 'true':
        session.run("python", "-m", "playwright", "install", "--with-deps", "chromium")
    else:
        session.run("python", "-m", "playwright", "install", "chromium")

    session.log("🖼️  Generating documentation screenshots (headless mode)...")

    # Set headless mode via environment variable
    session.env["HEADLESS"] = "true"

    # Run screenshot tests only
    session.run(
        "python", "-m", "pytest",
        "tests/e2e/test_screenshot_generation.py",
        "-m", "screenshot",
        "-v",
        "--tb=short",
        *session.posargs
    )

    session.log("✅ Screenshot generation complete!")
    session.log("📁 Screenshots saved to: docs/images/screenshots/")


@nox.session(python=DEFAULT_PYTHON)
def screenshots_verify(session):
    """Verify screenshots against their manifest, config, and quality standards.

    Runs ``tests/e2e/screenshot_verifier.py``, which is unit tested in
    ``tests/unit/test_screenshot_infrastructure.py``.

    Checks:
    - docs/images/screenshots/metadata.json exists, is valid JSON, and every
      entry carries filename/capture_type/timestamp plus details with
      viewport_size and hide_selectors; no duplicate filenames
    - Manifest entries and on-disk PNGs agree in both directions (no orphan
      PNGs, no manifest entries whose file is missing). A PNG belonging to a
      `capture_status: conditional` capture is exempt from the orphan check,
      since it may survive a run whose guard did not fire
    - Every manifest entry is declared in tests/e2e/screenshot_config.yaml
    - Every `capture_status: required` capture appears in the manifest; no
      `capture_status: planned` capture does. Skipped `conditional` captures
      and outstanding `planned` ones are reported as informational notes
    - screenshot_config.yaml is structurally valid, every definition has a
      valid capture_status, and no two definitions share an output
    - At least one screenshot exists, all are under the 500KB size limit, and
      all are valid PNG images in RGB/RGBA color mode

    Example:
        nox -s screenshots_verify
    """
    session.install("Pillow", "PyYAML")

    session.log("🔍 Verifying screenshots...")

    session.run("python", "-m", "tests.e2e.screenshot_verifier")


# Default session when running 'nox' without arguments
nox.options.sessions = ["tests", "doctests", "coverage"]
