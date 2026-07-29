"""Tripwire tests keeping docstring examples inside the only tree that runs them.

``nox -s doctests`` executes ``pytest --doctest-modules`` against ``app/utils``
and nothing else, and the explicit path argument is the only thing that scopes
it (DW-45 / DW-66 gave the session that shape deliberately: running it tree-wide
would import the Flask/ORM layers this repo keeps out of the pure-utils seam).
The cost of that choice is silent: a ``>>>`` example written into a route,
service or model docstring reads exactly like the executed ones under
``app/utils/``, is never collected by any session, and can therefore disagree
with the code it documents forever without a single test going red. That is
DW-103, and it is the failure mode these tests freeze.

``test_no_doctest_examples_outside_the_doctested_package`` is the tripwire
proper: it scans the Python that could plausibly carry a published contract
docstring but is NOT covered by the session -- everything under ``app/`` outside
``app/utils/``, plus the repo-root modules -- and fails naming every offending
``path:line``. ``test_the_doctests_session_still_targets_app_utils`` is what
keeps that exclusion honest: if the session's path argument is widened,
retargeted or dropped, the first test's idea of "already covered" silently stops
matching reality, so the noxfile is read rather than assumed.

What the scan covers is ``app/`` outside ``app/utils/`` plus the repo-root
modules, and nothing else -- there is no exclusion list in ``_scanned_files``,
only that reach. Everything else in the repo is therefore unscanned by the same
mechanism, however different the reasons for leaving it out: ``tests/`` because
an example inside a test describes the test rather than a caller-facing
contract, and the assertions around it are the real record; ``migrations/``
because it is Alembic-generated boilerplate no caller reads for a contract;
``.claude/skills/**/scripts/`` -- the largest unscanned tree, a dozen modules
with their own test suites, already named in ``pytest.ini``'s ``norecursedirs``
comment -- along with ``_bmad/scripts/``, ``.bmad-loop/`` and any future
top-level package, because they simply were not in view when this was written.
A prompt in any of them stays unexecuted AND unreported. That is a boundary, not
an oversight, but it is also the thing to widen -- ``_scanned_files`` -- if such
a tree ever grows contract docstrings.

Note that ``tests/`` is not excluded to stop this module matching itself: the
pattern below matches a prompt only at the start of a line, and neither place
this file spells one -- the prose above, and the regex literal below -- begins a
line with it. Scanning ``tests/`` would be harmless; it is simply not useful.

The scan is textual and deliberately unaware of whether a match sits in a
docstring, a comment or an ordinary string: the point is that the sequence
should not appear at the start of a line in these files at all. If a legitimate
need for one ever arises, move the code under ``app/utils/`` where the session
will run it, or rewrite the illustration so it does not open with a prompt.
"""

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The package the doctests session runs, relative to the repo root. Everything
# under it is executed, so it is the one place an example is allowed to live --
# and the one directory this file's scan must skip.
DOCTESTED_PACKAGE = 'app/utils'

# The repo-root modules scanned alongside ``app/``. Globbed rather than frozen so
# a new top-level module is covered the day it lands, but pinned below as a
# lower bound so an empty glob (a moved entry point, a scan reading the wrong
# directory) fails loudly instead of passing vacuously.
EXPECTED_ROOT_MODULES = {'app.py', 'config.py', 'manage.py', 'noxfile.py',
                         'wsgi.py'}

# A doctest prompt: the three-character sequence as the first non-whitespace on
# a line, which is the only position doctest itself recognises. A prompt spelled
# anywhere else on a line -- in prose, in a comment, mid-string -- is not an
# example and is deliberately not matched.
_DOCTEST_PROMPT_RE = re.compile(r'^[ \t]*>>>')

# The flag that turns docstrings into tests. The session's `session.run` call is
# located by looking for it AMONG `.run(...)` calls only, so a `session.log`
# mentioning the flag cannot stand in for the real invocation.
DOCTEST_FLAG = '--doctest-modules'

# Words in that call that are the interpreter invocation, not the path under
# test. `noxfile.py` currently spells it `session.run("python", "-m", "pytest",
# ...)`, where `python` is matched here while `pytest` is already consumed as
# the value of `-m` (see VALUE_TAKING_FLAGS); the `pytest` entry is what covers
# the shorter `session.run("pytest", ...)` form.
RUN_INVOCATION_WORDS = {'python', 'pytest'}

# Options whose value is a SEPARATE argument rather than glued on with `=`, so
# that value must not be read as a path. `noxfile.py` already spells `-m` this
# way in its `tests`, `coverage` and `integration` sessions; without this set,
# adding `-m`, `"not slow"` to the doctests session would report `not slow` as a
# second path argument and blame the session's scope for an unrelated flag.
VALUE_TAKING_FLAGS = {'-m', '-k', '-p', '-o', '-c', '-r', '-n', '--tb',
                      '--override-ini', '--deselect', '--ignore', '--rootdir'}

# Options that REMOVE files from the run. Because their values are skipped like
# any other separate-word option value, `--ignore app/utils/sql_text.py` beside
# the path argument leaves the path reading as exactly `app/utils` -- the
# session narrowed from the inside while every widening check below stays green
# and this file still exempts the whole package. Asserted against separately.
NARROWING_FLAGS = {'--ignore', '--ignore-glob', '--deselect'}

# Returned by `_default_session_names` for an assignment it cannot read
# statically. Distinct from `None`, which means the option is never set at all.
SESSIONS_UNREADABLE = object()


def _scanned_files():
    """Every Python file that could carry an example no session would run.

    ``app/`` minus the doctested package, plus the repo-root modules. Sorted so
    a multi-file failure reports in a stable order.
    """
    doctested = REPO_ROOT / DOCTESTED_PACKAGE
    app_files = [
        path for path in (REPO_ROOT / 'app').rglob('*.py')
        if doctested not in path.parents
    ]
    return sorted(app_files + list(REPO_ROOT.glob('*.py')))


@pytest.mark.unit
def test_no_doctest_examples_outside_the_doctested_package():
    """An example outside ``app/utils/`` is documentation nothing executes.

    The failure message has to carry its own explanation, because the developer
    who trips this has just written something that looks correct and is: the
    example is fine, its *location* is what makes it unexecuted.
    """
    scanned = _scanned_files()
    names = {path.name for path in scanned if path.parent == REPO_ROOT}
    assert EXPECTED_ROOT_MODULES <= names, (
        f'the repo-root scan found {sorted(names)}, missing '
        f'{sorted(EXPECTED_ROOT_MODULES - names)}; the scan itself is broken '
        f'or an entry point moved'
    )
    # Counted directly rather than as `len(scanned) > len(EXPECTED_ROOT_MODULES)`:
    # that comparison holds the moment a sixth root module lands, even with the
    # app/ half returning nothing, which is exactly the state it exists to catch.
    assert any(path.parent != REPO_ROOT for path in scanned), (
        'the app/ scan found nothing -- the scan itself is broken'
    )

    offenders = []
    for path in scanned:
        lines = path.read_text(encoding='utf-8').splitlines()
        for lineno, line in enumerate(lines, start=1):
            if _DOCTEST_PROMPT_RE.match(line):
                offenders.append(f'{path.relative_to(REPO_ROOT)}:{lineno}')

    assert not offenders, (
        'doctest examples found outside ' + DOCTESTED_PACKAGE + '/: '
        + ', '.join(offenders)
        + '. Only ' + DOCTESTED_PACKAGE + '/ is executed, by the explicit path '
        'argument in the doctests session (nox -s doctests); an example '
        'anywhere else is never run and is free to disagree with the code it '
        'documents. Move the logic into a pure utility module under '
        + DOCTESTED_PACKAGE + '/ so the example becomes a test, or state the '
        'behavior without opening a line with a doctest prompt.'
    )


def _is_nox_session_decorator(node):
    """Whether a decorator node is nox's session decorator.

    Both spellings count -- bare ``@nox.session`` and called
    ``@nox.session(python=...)`` -- and so does a ``from nox import session``
    import. Any OTHER decorator does not: `@functools.cache` on a function
    named ``doctests`` does not make it a session `nox -s doctests` can run.
    """
    func = node.func if isinstance(node, ast.Call) else node
    if isinstance(func, ast.Attribute):
        return func.attr == 'session'
    return isinstance(func, ast.Name) and func.id == 'session'


def _find_doctests_session(tree):
    """The function node `nox -s doctests` would run, or ``None``.

    Resolved the way nox resolves it: a session decorator's ``name=`` keyword
    when it carries one, otherwise the function's own name. Both halves matter
    -- ``@nox.session(name='doctests')`` on a differently named function IS the
    session, and ``@nox.session(name='doctest_utils')`` on a function called
    ``doctests`` is NOT.

    A ``name=`` that is not a string literal (a variable, an f-string) is
    treated as "registered under a name this reader cannot resolve", which is
    NOT a fallback to the function's own name: on a function called ``doctests``
    that fallback would report the session as present while `nox -s doctests`
    found nothing under that name.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decorators = [d for d in node.decorator_list
                      if _is_nox_session_decorator(d)]
        if not decorators:
            continue
        given_names = [kw.value for d in decorators if isinstance(d, ast.Call)
                       for kw in d.keywords if kw.arg == 'name']
        declared = {value.value for value in given_names
                    if isinstance(value, ast.Constant)
                    and isinstance(value.value, str)}
        if 'doctests' in declared:
            return node
        if not given_names and node.name == 'doctests':
            return node
    return None


def _doctests_session_run_args(session):
    """The string arguments of the ``doctests`` session's pytest invocation.

    Located structurally rather than by scanning the function for constants:
    the strings that matter have to be arguments of the same ``.run(...)``
    call, not merely present somewhere in the body.
    """
    for call in ast.walk(session):
        if not isinstance(call, ast.Call):
            continue
        if not (isinstance(call.func, ast.Attribute) and call.func.attr == 'run'):
            continue
        args = [node.value for node in call.args
                if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        if DOCTEST_FLAG in args:
            return args
    return None


def _path_arguments(args):
    """The path operands of a pytest command line, flags and their values gone.

    A bare ``not arg.startswith('-')`` filter is not enough: the value of a
    separate-word option is itself non-flag text, so it would be counted as a
    path (see ``VALUE_TAKING_FLAGS``).
    """
    paths = []
    skip_next = False
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg.startswith('-'):
            skip_next = arg in VALUE_TAKING_FLAGS
            continue
        if arg in RUN_INVOCATION_WORDS:
            continue
        paths.append(arg)
    return paths


def _default_session_names(tree):
    """String entries of ``nox.options.sessions``, or ``None`` if never set.

    Matched on the whole ``nox.options.sessions`` target rather than on any
    attribute happening to be called ``sessions``, and read at MODULE TOP LEVEL
    in source order so a later statement wins the way execution would: a plain
    assignment replaces, an augmented one extends. ``None`` means the option is
    not set at all, which is not a failure -- nox then runs every session,
    doctests included.

    Anything else that touches the option yields ``SESSIONS_UNREADABLE`` rather
    than a guess, because every such form would otherwise read as green while a
    bare ``nox`` skipped doctests: a right-hand side that is not a literal list
    of strings (``[s for s in ALL if s != 'doctests']`` mentions the very string
    it removes), an in-place mutation (``nox.options.sessions.remove(...)``, an
    ``append``, a subscript assignment), or any mention nested inside a
    conditional or a function, where "last in source order" is not what runs.
    """
    def _is_target(node):
        if not (isinstance(node, ast.Attribute) and node.attr == 'sessions'):
            return False
        base = node.value
        # `nox.options.sessions`, and the `from nox import options` spelling.
        if isinstance(base, ast.Attribute):
            return base.attr == 'options'
        return isinstance(base, ast.Name) and base.id == 'options'

    def _literal_entries(value):
        """The strings of a literal list/tuple, or ``None`` if not one."""
        if not isinstance(value, (ast.List, ast.Tuple)):
            return None
        entries = []
        for element in value.elts:
            if not (isinstance(element, ast.Constant)
                    and isinstance(element.value, str)):
                return None
            entries.append(element.value)
        return entries

    names = None
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AugAssign):
            targets = [statement.target]
        else:
            targets = []
        if any(_is_target(target) for target in targets):
            entries = _literal_entries(statement.value)
            if entries is None:
                return SESSIONS_UNREADABLE
            extends = (isinstance(statement, ast.AugAssign)
                       and names is not None)
            names = names + entries if extends else entries
        elif any(_is_target(node) for node in ast.walk(statement)):
            return SESSIONS_UNREADABLE
    return names


@pytest.mark.unit
def test_the_doctests_session_still_targets_app_utils(pytestconfig):
    """The exclusion above is only true while the session keeps its scope.

    Read out of ``noxfile.py`` by parsing rather than importing: nox is a dev
    dependency of the *session* environments, and this test runs in the unit one.

    Five ways the premise can break, all checked here. The session can stop
    existing -- deleted, renamed, or left defined but no longer decorated as a
    nox session, so nothing invokes it. The flag can go, which stops docstrings
    being tests at all. The path can be RETARGETED or dropped, which stops
    ``app/utils`` being executed while this file still exempts it. Coverage can
    be WIDENED, in two ways that are the inverse failure -- the scan would then
    report files the session does in fact run -- either by a second path
    argument beside ``app/utils``, or by ``--doctest-modules`` migrating into
    the active pytest config's ``addopts``, where it would apply to every
    session over whatever paths that session names. ``noxfile.py``'s own
    docstring warns about the second; both are checked below. And coverage can
    be NARROWED from the inside, by a ``--ignore``/``--deselect`` that subtracts
    part of ``app/utils`` while leaving the path argument itself intact.

    Also checked, as the other half of "the session runs": that ``doctests`` is
    still in ``nox.options.sessions``, so a bare ``nox`` executes it. CI names
    the session explicitly (``.github/workflows/test.yml``), which is
    deliberately NOT asserted here -- a unit test reaching into a workflow file
    couples them harder than the premise is worth. Deleting that CI step is
    therefore a way to stop doctests running in CI that these tests will not
    catch.

    A residual gap is deliberate: ``*session.posargs`` is appended at runtime,
    so a path passed on the command line widens a single invocation without
    being visible to any static check. So is the constants-only reading of the
    ``run`` call -- hoisting the path into a module constant the way
    ``noxfile.py`` already does for ``PACKAGE`` would fail this test rather
    than fool it, and the failure message says how to respond.
    """
    noxfile = REPO_ROOT / 'noxfile.py'
    source = noxfile.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(noxfile))

    session = _find_doctests_session(tree)
    assert session is not None, (
        'noxfile.py no longer defines a function decorated as the nox session '
        '`doctests` (by its own name, or by a `name=` keyword on the session '
        f'decorator), so `nox -s doctests` runs nothing. {Path(__file__).name} '
        f'exempts {DOCTESTED_PACKAGE}/ from its scan on the premise that it does.'
    )

    args = _doctests_session_run_args(session)
    assert args is not None, (
        f'the doctests session in noxfile.py no longer runs {DOCTEST_FLAG}, so '
        f'no docstring anywhere is executed. {Path(__file__).name} exempts '
        f'{DOCTESTED_PACKAGE}/ from its scan on the premise that it is.'
    )

    paths = _path_arguments(args)
    assert paths == [DOCTESTED_PACKAGE], (
        f'the doctests session passes pytest the path arguments {paths}, not '
        f'exactly [{DOCTESTED_PACKAGE!r}]. {Path(__file__).name} excludes '
        f'{DOCTESTED_PACKAGE}/ from its scan because that session executes it: '
        f'dropping or retargeting the path leaves the exclusion covering '
        f'nothing, and widening it makes the scan report files that ARE now '
        f'executed. Either restore the argument or update this file to match '
        f"the session's real scope."
    )

    narrowing = [arg for arg in args if arg.split('=', 1)[0] in NARROWING_FLAGS]
    assert not narrowing, (
        f'the doctests session passes pytest {narrowing}, which subtracts files '
        f'from the run. The path argument still reads as {DOCTESTED_PACKAGE!r}, '
        f'so every widening check here stays green while part of '
        f'{DOCTESTED_PACKAGE}/ is no longer collected -- and '
        f'{Path(__file__).name} exempts the whole package from its scan on the '
        f'premise that all of it is. Narrow the session by moving the code out '
        f'of {DOCTESTED_PACKAGE}/, not by hiding it from the collector.'
    )

    # The widening case the session's own arguments cannot show: the flag moving
    # into `addopts`, where it would apply to every session over that session's
    # paths -- the leak `noxfile.py`'s docstring keeps it on the command line to
    # prevent. Read as the EFFECTIVE parsed value rather than as pytest.ini's
    # text: that file carries explanatory comments about its own options
    # (`--strict-config`, `norecursedirs`), so a comment recording that this
    # flag deliberately does NOT belong there must not turn this test red with a
    # message claiming the opposite. `test_pytest_config.py` pins pytest.ini as
    # the active configfile; nothing here modifies it.
    addopts = pytestconfig.getini('addopts')
    assert not any(DOCTEST_FLAG in option for option in addopts), (
        f'the active pytest config (pytest.ini) now puts {DOCTEST_FLAG} in '
        f'`addopts` ({addopts}), where it applies to EVERY session over '
        f'whatever paths that session names, so doctests are no longer confined '
        f'to {DOCTESTED_PACKAGE}/ and this file would report files that ARE '
        f'executed. Keep the flag on the doctests session\'s command line, or '
        f'update this file to match the real scope.'
    )

    # The second half of "the session runs": one nothing invokes executes
    # nothing. `None` means nox.options.sessions is unset, in which case a bare
    # `nox` runs every session -- doctests included -- so the premise holds.
    default_names = _default_session_names(tree)
    assert default_names is not SESSIONS_UNREADABLE, (
        'noxfile.py sets nox.options.sessions in a form this test cannot read '
        'statically -- a non-literal value, an in-place mutation, or a mention '
        'nested inside a conditional or a function -- so it can no longer tell '
        'whether a bare `nox` run includes doctests, and a list that excluded '
        'doctests would read as green. Restore a literal list assigned at '
        f'module level, or teach {Path(__file__).name} the new form.'
    )
    assert default_names is None or 'doctests' in default_names, (
        f'nox.options.sessions is {default_names}, which no longer includes '
        f'doctests, so a bare `nox` run executes no docstring example while '
        f'{Path(__file__).name} still exempts {DOCTESTED_PACKAGE}/ from its scan'
    )
