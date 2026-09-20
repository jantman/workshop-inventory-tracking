"""Application version, and where the running code came from.

The release number lives in ``pyproject.toml`` and is read from there so there
is a single source of truth. The application is not installed as a package, so
``importlib.metadata`` is not an option.

``RELEASE_VERSION`` is that number, bare. ``__version__`` is what the footer and
``/health`` report, which is the release number plus whatever can be determined
about *which build* is running:

    2.0.0                    a release, or a provenance that cannot be determined
    2.0.0-6d15bde            built by CI from commit 6d15bde, or a working copy there
    2.0.0-6d15bde-dirty      a working copy with edits to tracked files

A built image carries no history -- ``.dockerignore`` excludes ``.git/`` and the
runtime stage installs no ``git`` -- so a container is told its commit at build
time through ``APP_BUILD_SHA``. A working copy has no such stamp and is asked
directly. Determining this must never fail: every unanswerable question degrades
to the bare release number.
"""

import os
import subprocess
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

with _PYPROJECT.open("rb") as f:
    RELEASE_VERSION: str = tomllib.load(f)["project"]["version"]


def _git(*args: str) -> str | None:
    """Run ``git <args>`` in the repository root; stdout, or None if unanswerable.

    None covers every way of not getting an answer -- git absent, not a working
    copy, a non-zero exit, a hang -- because the caller treats them identically.
    This must never raise: it runs at import, and an exception here would take
    out the application rather than a version string.

    The timeout is the reason a hang is on that list. Without it a git process
    that never returns would block startup indefinitely.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _version_suffix(release_version: str) -> str:
    """Describe the working copy: "", "-dirty", "-<sha>", or "-<sha>-dirty"."""
    commit = _git("rev-parse", "--short=7", "HEAD")
    if not commit:
        # No commit means no working copy to describe. Nothing else it might
        # say -- including whether it is dirty -- is knowable either.
        return ""

    # --untracked-files=no is load-bearing. A working copy in ordinary use always
    # has untracked files (test-debug-output/, .pytest_cache/, a scratch script),
    # and plain --porcelain reports them, so without this every developer run
    # would say -dirty and the marker would stop meaning anything.
    dirty = "-dirty" if _git("status", "--porcelain", "--untracked-files=no") else ""

    # The release workflow tags v<version>; accept the bare spelling too.
    tags = (_git("tag", "--points-at", "HEAD") or "").split()
    if release_version in tags or f"v{release_version}" in tags:
        return dirty

    return f"-{commit}{dirty}"


def _compute_version(release_version: str) -> str:
    """Return the version to report: the release number plus its provenance."""
    # A built image is told its commit at build time, and that answer wins: a
    # container started inside a working copy must report what it was built
    # from, not whatever happens to be on the disk around it.
    build_sha = os.environ.get("APP_BUILD_SHA", "").strip()
    if build_sha:
        return f"{release_version}-{build_sha[:7]}"

    return f"{release_version}{_version_suffix(release_version)}"


__version__: str = _compute_version(RELEASE_VERSION)
