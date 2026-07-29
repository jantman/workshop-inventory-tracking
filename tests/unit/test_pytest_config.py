"""Tripwire tests asserting that ``pytest.ini`` is actually in force.

For the whole life of the file, ``pytest.ini`` opened with ``[tool:pytest]`` --
a ``setup.cfg`` section name. pytest reported ``configfile: pytest.ini`` in its
header while reading *nothing* from it, so ``testpaths``, ``addopts``,
``markers``, ``norecursedirs`` and ``minversion`` were all inert. Nothing in the
suite noticed, and the bug was eventually written into the project docs as
intended behaviour (DW-102 / DW-105).

These tests exist so that failure mode cannot recur silently: if the section
header is reverted, the file is renamed, or the configuration is migrated to a
``pyproject.toml``/``setup.cfg`` that pytest does not pick up, the suite goes
red instead of quietly losing five settings at once.

Note that these tests read the *effective* configuration, so overriding it on
the command line will fail them by design -- ``--override-ini="addopts=..."``
replaces the whole option string rather than editing it, and dropping
``--strict-markers``/``--strict-config`` from a replacement is indistinguishable
from the regression this file guards against. Repeat those flags in any
override (see the addopts bullet in ``_bmad-output/project-context.md``).
"""

import re
from collections import Counter

import pytest

# pytest's own default for the ``norecursedirs`` ini key, from
# ``_pytest.main.pytest_addoption``. Setting the key REPLACES this list rather
# than adding to it, so pytest.ini has to restate every entry verbatim. Frozen
# here so both directions of drift are caught: an entry dropped from the ini,
# and an entry *added* by a future pytest release that the ini has not picked
# up yet (see test_norecursedirs_keeps_the_builtin_exclusions).
PYTEST_DEFAULT_NORECURSEDIRS = {
    "*.egg",
    ".*",
    "_darcs",
    "build",
    "CVS",
    "dist",
    "node_modules",
    "venv",
    "{arch}",
}

# Project additions on top of the defaults above.
PROJECT_NORECURSEDIRS = {"*.egg-info", "__pycache__", "migrations"}

# Every marker pytest.ini declares. Of these, only ``e2e``, ``integration`` and
# ``screenshot`` are selected on with ``-m`` by a noxfile.py session; ``unit``
# and ``slow`` are declared and applied but no session selects on them.
PROJECT_MARKERS = {"unit", "integration", "e2e", "slow", "screenshot"}

# Matches a marker application in test source: the decorator form, plus the
# ``pytestmark = ...``, ``marks=...`` and ``add_marker(...)`` forms, none of
# which carry a leading ``@``. The backslashes keep this pattern from matching
# itself when the scan reads this very file -- and note that spelling out a
# marker reference in dotted form anywhere in this module would be picked up as
# a real use, so the comments here name the forms without illustrating them.
_MARKER_USE_RE = re.compile(r"pytest\.mark\.([A-Za-z_][A-Za-z0-9_]*)")


def _registered_marker_name_list(pytestconfig):
    """Marker names from the live ``markers`` ini value, in registry order.

    Entries look like ``name: description`` or ``name(arg): description``. At
    runtime this list also carries the markers that pytest core and the
    installed plugins register, which is exactly the set ``--strict-markers``
    validates against. Returned as a list rather than a set so that a
    double-registration stays visible instead of being deduplicated away.
    """
    return [
        line.split(":", 1)[0].split("(", 1)[0].strip()
        for line in pytestconfig.getini("markers")
    ]


def _registered_marker_names(pytestconfig):
    """The registered marker names as a set, for membership checks."""
    return set(_registered_marker_name_list(pytestconfig))


@pytest.mark.unit
def test_pytest_ini_is_the_active_configfile(pytestconfig):
    """The ini pytest loaded is *this repo's* pytest.ini, and it parsed."""
    assert pytestconfig.inipath is not None
    assert pytestconfig.inipath == pytestconfig.rootpath / "pytest.ini"


@pytest.mark.unit
def test_testpaths_is_read_from_the_ini(pytestconfig):
    """A non-empty ``testpaths`` proves the section header is ``[pytest]``.

    Under ``[tool:pytest]`` this returns the empty list.
    """
    assert pytestconfig.getini("testpaths") == ["tests"]


@pytest.mark.unit
def test_strict_markers_is_in_force(pytestconfig):
    """``addopts`` reached the option parser, so an unknown marker errors."""
    assert pytestconfig.getoption("strict_markers") is True


@pytest.mark.unit
def test_strict_config_is_in_force(pytestconfig):
    """A misspelled ini key errors instead of being silently ignored."""
    assert pytestconfig.getoption("strict_config") is True


@pytest.mark.unit
def test_project_markers_are_registered_exactly_once(pytestconfig):
    """pytest.ini is the *single* registry for the project's own markers.

    Two things can go wrong here and only one of them is loud. A *missing*
    entry breaks whichever session selects on it, because ``--strict-markers``
    turns it into a collection error -- and for ``screenshot`` that is only
    ``nox -s screenshots``/``screenshots_headless``, which no other session
    would surface. A *duplicate* entry is silent: restoring the
    ``addinivalue_line`` calls that used to live in ``tests/conftest.py``
    would re-register four of these names on top of the ini and nothing would
    complain. Counting occurrences catches both.
    """
    counts = Counter(_registered_marker_name_list(pytestconfig))
    assert {name: counts[name] for name in sorted(PROJECT_MARKERS)} == {
        name: 1 for name in sorted(PROJECT_MARKERS)
    }


@pytest.mark.unit
def test_every_marker_used_in_the_suite_is_registered(pytestconfig):
    """No test applies a marker that the registry does not know about.

    Unlike the fixed list above, this scans ``tests/`` for actual marker
    applications, so a *new* marker added to a test tomorrow without a matching
    ini entry is caught here rather than only in whichever session happens to
    collect that file. That was the DW-105 failure mode: ``screenshot`` was
    used 15 times and registered nowhere, and only the screenshot sessions
    would ever have noticed.

    The pattern deliberately does not require a leading ``@``: a marker can
    also be applied through a module-level ``pytestmark``, through ``marks=``
    on a parametrize case, or through ``add_marker()`` in a conftest -- and
    ``tests/integration/conftest.py`` uses the last of those today, so a
    decorator-only scan would have a hole that is already reachable.

    The scan is textual, so writing a nonexistent marker name in dotted form
    in prose under ``tests/`` will fail this test. Refer to it some other way.
    """
    tests_root = pytestconfig.rootpath / "tests"
    used = {}
    for path in sorted(tests_root.rglob("*.py")):
        for name in _MARKER_USE_RE.findall(path.read_text(encoding="utf-8")):
            used.setdefault(name, path.relative_to(pytestconfig.rootpath))

    assert used, "marker scan found nothing -- the scan itself is broken"
    registered = _registered_marker_names(pytestconfig)
    unregistered = {name: str(path) for name, path in used.items() if name not in registered}
    assert not unregistered, (
        "markers used in tests/ but not registered in pytest.ini: " f"{unregistered}"
    )


@pytest.mark.unit
def test_norecursedirs_keeps_the_builtin_exclusions(pytestconfig):
    """Setting ``norecursedirs`` REPLACES pytest's defaults rather than adding.

    Every default has to be restated in pytest.ini or it is silently lost.
    Losing the ``.*`` glob would expose ``.nox/`` -- whose session virtualenvs
    ship a few hundred third-party ``test_*.py`` files -- and the
    ``.claude/skills/**/scripts/tests/`` files to any run that recurses from
    the repo root (``pytest .``). ``testpaths = tests`` keeps every nox session
    away from the root today, so this setting is defence in depth rather than
    load-bearing; it does not filter a directory named directly on the command
    line (``pytest .nox`` still collects).

    The first assertion is the one that survives a pytest upgrade. A subset
    check against a frozen copy of the defaults only ever notices an entry
    being deleted from the ini; it cannot notice a new pytest release *adding*
    a built-in exclusion, which would leave pytest.ini quietly short of the
    list it claims to repeat verbatim. Comparing the frozen copy against the
    live default closes that direction.
    """
    # Private, but there is no public accessor for an ini key's default once
    # the ini has overridden it. If pytest moves it, this raises rather than
    # silently passing, which is the right failure for a tripwire.
    live_default = set(pytestconfig._parser._inidict["norecursedirs"][2])
    assert live_default == PYTEST_DEFAULT_NORECURSEDIRS, (
        "pytest's built-in norecursedirs default changed; add the new entries "
        "to pytest.ini's norecursedirs and to PYTEST_DEFAULT_NORECURSEDIRS"
    )

    norecursedirs = set(pytestconfig.getini("norecursedirs"))
    assert PYTEST_DEFAULT_NORECURSEDIRS <= norecursedirs
    assert PROJECT_NORECURSEDIRS <= norecursedirs
