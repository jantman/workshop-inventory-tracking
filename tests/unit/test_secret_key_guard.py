"""The boot-time `SECRET_KEY` guard (`app/secret_key_guard.py`).

`config.Config` falls back to a key that is committed to this repository, and
`.env.example` and the deployment guide each publish a placeholder, so an app
that boots on any of them signs every session cookie and CSRF token with a
public value. These tests pin both halves of the fix: a non-debug app REFUSES to
start on such a key, and a debug/testing app boots but says so at ERROR.

Every scenario is driven through `create_app(...)` rather than by calling
`validate_secret_key` directly, because part of what is being asserted is
*where* the guard sits in the factory: after `setup_logging`, or its ERROR
record never reaches the structured JSON pipeline.

`caplog` is deliberately unused for the log assertions: `setup_logging` removes
every handler from the root logger, pytest's capturing handler included, so
records emitted during `create_app` are invisible to it. The `capsys` +
JSON-line pattern below is the same one `tests/unit/test_request_limits.py`
uses, and it doubles as proof that the record went through the configured
handlers -- the JSON envelope is only produced by the formatter `setup_logging`
installs.

`importlib.reload(config)` is avoided on purpose: the repo's own `.env` may
define `SECRET_KEY`, and a reload picks the ambient environment up as-is, so
such a test passes or fails depending on whose checkout ran it. The scenarios
are built as config subclasses instead.

Cold-import SUBPROCESSES are likewise absent, and that one is worth naming
precisely, because the reason recorded in this story's spec does not hold:
`dotenv.load_dotenv` defaults to `override=False`, so a variable set in a
child's environment beats the repo's `.env` deterministically, and
`tests/unit/test_request_limits.py::TestColdInterpreterImports` already runs
subprocesses on exactly that basis. They are absent because the frozen intent
contract for this story forbids them, not because they would be flaky. The cost
is real and is recorded as deferred work: nothing here exercises the SHIPPED
`config.Config` through `wsgi.py`, so every scenario below proves the guard's
logic and none of them proves that a real deployment boot reaches it.
"""

import ast
import inspect
import json
import os
import re
from pathlib import Path

import pytest

import config as config_module
from app import create_app
from app.exceptions import ConfigurationError
from app.secret_key_guard import validate_secret_key
from config import DEV_SECRET_KEY_FALLBACK, PUBLISHED_SECRET_KEYS
from tests.test_config import TestConfig

REPO_ROOT = Path(__file__).resolve().parents[2]

# A stand-in for a key an operator actually set. Any value outside
# PUBLISHED_SECRET_KEYS will do; the guard compares for membership in that set
# and nothing else.
_REAL_KEY = 'a-private-key-that-is-not-in-the-repository'


def _json_errors_about_the_key(captured):
    """ERROR-or-worse messages ABOUT `SECRET_KEY`, emitted through the JSON
    pipeline that `setup_logging` installs, read off the captured streams.

    See the module docstring for why `caplog` cannot be used here. Two
    narrowings matter:

    - Only records naming SECRET_KEY are returned. Asserting on *every* startup
      ERROR would make an unrelated future check fail these tests with a message
      pointing at this guard.
    - The ONE emitted record produces SEVERAL lines, which is why callers below
      compare distinct messages rather than counting: `setup_logging` installs a
      JSON handler on `app.logger`, a plain-text one for ERROR, and a third JSON
      handler on the ROOT logger that `app.logger` propagates to. That fan-out
      predates this guard -- every startup warning already lands twice -- so it
      is not this module's to assert on.
    """
    messages = []
    for stream in (captured.out, captured.err):
        for line in stream.splitlines():
            if not line.startswith('{'):
                continue
            try:
                record = json.loads(line)
            except ValueError:       # pragma: no cover - not a log line
                continue
            if record.get('level') not in ('ERROR', 'CRITICAL'):
                continue
            message = record.get('message', '')
            if 'SECRET_KEY' in message:
                messages.append(message)
    return messages


def _without_comments(source):
    """`source` with whole-line comments removed.

    The ordering assertions below search this rather than the raw source: the
    explanatory comment blocks in `create_app` and in `app.py` name the very
    calls being ordered, so a comment edit could otherwise satisfy -- or break
    -- an assertion about the code.
    """
    return '\n'.join(line for line in source.splitlines()
                     if not line.lstrip().startswith('#'))


def _factory_statements():
    """`create_app`'s source, comments stripped."""
    return _without_comments(inspect.getsource(create_app))


def _app_py_statements():
    """`app.py`'s source, comments stripped."""
    return _without_comments((REPO_ROOT / 'app.py').read_text())


def _app_py_main_guard():
    """`app.py`'s `if __name__ == '__main__':` node, or `None`.

    Matched on the `__name__` test, not on "the first module-level `if`": the
    assertions below use this node to decide what counts as module scope, so a
    loose match would let a future `if os.environ.get(...)` at module level be
    mistaken for the guard and excluded from exactly the check it needs.
    """
    tree = ast.parse((REPO_ROOT / 'app.py').read_text())
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        if any(isinstance(sub, ast.Name) and sub.id == '__name__'
               for sub in ast.walk(node.test)):
            return tree, node
    return tree, None


class _Recorder:
    """The minimum of `app.logger` that the guard uses.

    `critical` is recorded separately from `error` because the two mark
    different branches: ERROR is the debug/testing downgrade, CRITICAL
    accompanies the refusal that stops the boot.
    """

    def __init__(self):
        self.errors = []
        self.criticals = []

    def error(self, message, *args):
        self.errors.append(message % args if args else message)

    def critical(self, message, *args):
        self.criticals.append(message % args if args else message)


class _FallbackKeyProductionConfig(TestConfig):
    """A deployment whose operator never set `SECRET_KEY`.

    `TESTING`/`DEBUG` are turned back off explicitly: `tests.test_config`
    switches both on, and they are exactly what the guard branches on.
    """
    TESTING = False
    DEBUG = False
    SECRET_KEY = DEV_SECRET_KEY_FALLBACK


class _RealKeyProductionConfig(_FallbackKeyProductionConfig):
    SECRET_KEY = _REAL_KEY


class _FallbackKeyDebugConfig(_FallbackKeyProductionConfig):
    DEBUG = True


class _FallbackKeyTestingConfig(_FallbackKeyProductionConfig):
    TESTING = True


class _RealKeyDebugConfig(_FallbackKeyProductionConfig):
    DEBUG = True
    SECRET_KEY = _REAL_KEY


@pytest.mark.unit
class TestANonDebugAppRefusesToBootOnAPublishedKey:

    def test_create_app_raises_configuration_error_naming_secret_key(
            self, test_storage):
        """The point of the whole feature: the process does not start. A
        deployment that silently came up on a public signing key is
        indistinguishable, from the outside, from a correctly configured one."""
        with pytest.raises(ConfigurationError) as excinfo:
            create_app(_FallbackKeyProductionConfig,
                       storage_backend=test_storage)

        assert 'SECRET_KEY' in str(excinfo.value)
        assert excinfo.value.config_key == 'SECRET_KEY'

    def test_the_refusal_says_the_key_is_published_and_how_to_set_one(
            self, test_storage):
        """An operator reading only this line has to be able to act on it."""
        with pytest.raises(ConfigurationError) as excinfo:
            create_app(_FallbackKeyProductionConfig,
                       storage_backend=test_storage)

        message = str(excinfo.value).lower()
        assert 'repository' in message
        assert 'environment variable' in message or '.env' in message

    def test_the_refusal_never_echoes_the_resolved_key_value(self, test_storage):
        """This text lands in logs and in a traceback. Echoing the value would
        make the guard's own diagnostic a way to leak a key -- and there is
        nothing to gain by quoting a value that is already in the repository."""
        with pytest.raises(ConfigurationError) as excinfo:
            create_app(_FallbackKeyProductionConfig,
                       storage_backend=test_storage)

        assert DEV_SECRET_KEY_FALLBACK not in str(excinfo.value)

    def test_the_refusal_is_also_logged_through_the_configured_pipeline(
            self, test_storage, capsys):
        """The raise stops the boot, but on its own it surfaces only as a
        traceback on stderr -- unstructured, and absent from the JSON stream an
        operator aggregates. The branch that matters most would be the one
        branch invisible to monitoring. This is why the call sits after
        `setup_logging`: that ordering buys nothing for a bare raise."""
        capsys.readouterr()
        with pytest.raises(ConfigurationError):
            create_app(_FallbackKeyProductionConfig,
                       storage_backend=test_storage)

        messages = _json_errors_about_the_key(capsys.readouterr())
        assert messages, 'the refusal emitted no structured log record'
        assert 'repository' in messages[0].lower()
        assert DEV_SECRET_KEY_FALLBACK not in ' '.join(messages)

    def test_the_logged_refusal_says_the_process_is_not_starting(
            self, test_storage, capsys):
        """Otherwise the record is byte-identical to the one the debug branch
        emits, and the reader who most needs to know a process just died has to
        infer it from the level field instead of reading it."""
        capsys.readouterr()
        with pytest.raises(ConfigurationError):
            create_app(_FallbackKeyProductionConfig,
                       storage_backend=test_storage)

        messages = _json_errors_about_the_key(capsys.readouterr())
        assert all('refusing to start' in message.lower()
                   for message in messages), messages

    def test_the_refusal_logs_at_critical_not_error(self):
        """Severity carries the difference between the two branches: a debug app
        that booted anyway (ERROR) and a deployment that did not start
        (CRITICAL). Collapsing them would make the alert-worthy case
        indistinguishable from the routine development one."""
        recorder = _Recorder()
        with pytest.raises(ConfigurationError):
            validate_secret_key({'SECRET_KEY': DEV_SECRET_KEY_FALLBACK},
                                recorder)

        assert len(recorder.criticals) == 1
        assert recorder.errors == []

    def test_a_non_debug_app_with_a_real_key_boots_and_says_nothing(
            self, test_storage, capsys):
        capsys.readouterr()          # discard anything logged before this point
        app = create_app(_RealKeyProductionConfig, storage_backend=test_storage)

        assert app.config['SECRET_KEY'] == _REAL_KEY
        assert _json_errors_about_the_key(capsys.readouterr()) == []


@pytest.mark.unit
class TestADebugOrTestingAppLogsInsteadOfRefusing:
    """`FLASK_DEBUG=1 flask run` must keep working, and the suites that build
    apps from `config.TestConfig` (which inherits the fallback) must keep
    running -- neither is reachable by an attacker. See the guard's docstring.
    """

    @pytest.mark.parametrize('config_class', [_FallbackKeyDebugConfig,
                                              _FallbackKeyTestingConfig])
    def test_the_app_boots_and_logs_a_single_diagnosis_naming_secret_key(
            self, test_storage, capsys, config_class):
        """A SINGLE DIAGNOSIS -- not a single line, and not a claim about how
        many times the guard was called. `setup_logging`'s handler fan-out
        repeats every record (see `_json_errors_about_the_key`), so identical
        emissions cannot be counted here; de-duplicating is the only stable
        assertion this level supports. Exactly-once IS pinned, one layer down,
        by `test_either_flag_alone_is_enough_to_downgrade_to_a_log`, which
        counts calls on a recorder instead of lines on a stream."""
        capsys.readouterr()
        app = create_app(config_class, storage_backend=test_storage)

        assert app is not None
        errors = _json_errors_about_the_key(capsys.readouterr())
        assert len(set(errors)) == 1, errors
        assert 'repository' in errors[0].lower()

    def test_the_logged_error_never_echoes_the_resolved_key_value(
            self, test_storage, capsys):
        capsys.readouterr()
        create_app(_FallbackKeyDebugConfig, storage_backend=test_storage)

        for message in _json_errors_about_the_key(capsys.readouterr()):
            assert DEV_SECRET_KEY_FALLBACK not in message

    def test_a_debug_app_with_a_real_key_says_nothing(self, test_storage,
                                                      capsys):
        """The ERROR is a diagnosis of one specific condition, not a nag at
        every development boot: a developer who has set a key must not be
        trained to filter the channel that carries it."""
        capsys.readouterr()
        create_app(_RealKeyDebugConfig, storage_backend=test_storage)

        assert _json_errors_about_the_key(capsys.readouterr()) == []

    def test_the_shipped_test_config_can_only_ever_take_the_log_branch(self):
        """`config.TestConfig` (used by the e2e and integration suites) does not
        set `SECRET_KEY`, so on a machine with no `SECRET_KEY` in the
        environment it inherits the fallback. It must keep BOOTING there, which
        is what `TESTING = True` guarantees.

        The assertion is on the flag, not on the resolved key: this repo's
        `.env` may itself define `SECRET_KEY` (it does on a configured
        developer machine), which would make an assertion about the value pass
        or fail depending on whose checkout ran it. The flag is what decides
        the branch, and it is environment-independent.
        """
        assert config_module.TestConfig.TESTING is True
        assert 'SECRET_KEY' not in vars(config_module.TestConfig)


@pytest.mark.unit
class TestEveryPublishedKeyIsRecognized:
    """The fallback is not the only signing key this repository hands out, and
    a guard that knows only the fallback is silent about the value an operator
    following the documentation is most likely to be running."""

    @pytest.mark.parametrize('published', sorted(PUBLISHED_SECRET_KEYS))
    def test_each_published_key_refuses_a_non_debug_boot(self, published):
        with pytest.raises(ConfigurationError) as excinfo:
            validate_secret_key({'SECRET_KEY': published}, _Recorder())

        assert excinfo.value.config_key == 'SECRET_KEY'

    @pytest.mark.parametrize('published', sorted(PUBLISHED_SECRET_KEYS))
    def test_a_retyped_or_autocapitalized_placeholder_is_still_recognized(
            self, published):
        """`Your-Secret-Key-Here` is character-for-character as public as the
        lowercase spelling. An operator who retypes a placeholder instead of
        pasting it -- or whose editor capitalises it -- is in exactly the
        situation this guard exists for, and no random key is one casefold away
        from a published one, so the widening only ever refuses more."""
        with pytest.raises(ConfigurationError):
            validate_secret_key({'SECRET_KEY': published.title()}, _Recorder())

    def test_the_placeholder_env_example_ships_is_in_the_set(self):
        """Pins the set to the file, so editing one without the other is a test
        failure rather than a guard that quietly stops recognising the value
        every new developer copies."""
        shipped = re.search(r'^SECRET_KEY=(.*)$',
                            (REPO_ROOT / '.env.example').read_text(),
                            re.MULTILINE)

        assert shipped is not None
        assert shipped.group(1).strip() in PUBLISHED_SECRET_KEYS

    def test_the_deployment_guide_no_longer_prints_a_usable_placeholder(self):
        """The guide used to offer a placeholder as the content of a PRODUCTION
        `.env`. That value stays in PUBLISHED_SECRET_KEYS forever -- every
        `.env` already created from the old text still contains it -- but the
        guide must not hand out a new one."""
        guide = (REPO_ROOT / 'docs' / 'deployment-guide.md').read_text()

        for published in PUBLISHED_SECRET_KEYS:
            assert f'SECRET_KEY={published}' not in guide

    def test_entries_are_never_removed_from_the_set(self):
        """A shrinking set silently un-protects deployments already running the
        removed value."""
        assert PUBLISHED_SECRET_KEYS >= frozenset({
            DEV_SECRET_KEY_FALLBACK,
            'your-secret-key-here',
            'your-secret-key-here-change-this',
        })


@pytest.mark.unit
class TestTheFallbackLiteralHasExactlyOneHome:
    """A guard that compares against its own copy of the string is a guard that
    stops firing the day someone edits `config.py`."""

    def test_the_literal_appears_exactly_once_in_config_py(self):
        source = (REPO_ROOT / 'config.py').read_text()

        assert source.count(DEV_SECRET_KEY_FALLBACK) == 1, (
            'the development fallback key must appear in config.py exactly '
            'once, as the definition of DEV_SECRET_KEY_FALLBACK')

    def test_the_guard_module_carries_no_copy_of_any_published_key(self):
        """The whole module, not just the function body: a copy pasted into a
        module-level constant would be just as stale, and just as invisible."""
        source = (REPO_ROOT / 'app' / 'secret_key_guard.py').read_text()

        for published in PUBLISHED_SECRET_KEYS:
            assert published not in source
        assert 'PUBLISHED_SECRET_KEYS' in source

    def test_config_resolves_the_constant_when_the_environment_is_unset(self):
        """Pins the two halves together without reloading `config` (the repo's
        own `.env` may set `SECRET_KEY`, which would make a reload-based test
        machine-dependent): either the environment supplied a key, or the
        resolved value IS the constant."""
        if os.environ.get('SECRET_KEY'):
            assert config_module.Config.SECRET_KEY == os.environ['SECRET_KEY']
        else:
            assert config_module.Config.SECRET_KEY == DEV_SECRET_KEY_FALLBACK


@pytest.mark.unit
class TestTheGuardSitsInTheRightPlaceInTheFactory:

    def test_the_call_is_after_setup_logging(self):
        """Prose in a comment does not keep the call where it has to be. Before
        `setup_logging`, whose `handlers.clear()` empties the root logger too,
        the ERROR bypasses the JSON pipeline operators aggregate."""
        statements = _factory_statements()

        assert statements.index('setup_logging(') < \
            statements.index('validate_secret_key(')

    def test_the_call_is_before_the_rest_of_the_startup_checks(self):
        """Not a correctness requirement -- a raise anywhere in the factory
        aborts the boot -- but the cheapest check belongs first, so nothing is
        installed on a key already known to be forgeable."""
        statements = _factory_statements()

        assert statements.index('validate_secret_key(') < \
            statements.index('csrf.init_app(')

    def test_the_factory_passes_app_config_and_app_logger(self):
        """Matching `validate_limits(app.config, app.logger)`: reading
        `app.config` is what makes Flask's own `TESTING` default apply.
        Whitespace-tolerant, so a line wrap is not a test failure."""
        assert re.search(r'validate_secret_key\(\s*app\.config\s*,\s*app\.logger\s*\)',
                         _factory_statements())


@pytest.mark.unit
class TestTheDevEntrypointDeclaresItsDebugIntent:
    """`app.py` runs `app.run(debug=True)`, but that happens after
    `create_app()` has read the config -- so the app it builds is configured as
    a NON-debug app unless FLASK_DEBUG says otherwise, and the guard would
    refuse to start it on a fresh checkout."""

    def test_flask_debug_is_defaulted_before_the_factory_is_imported(self):
        statements = _app_py_statements()

        default_at = statements.index("os.environ['FLASK_DEBUG']")
        import_at = statements.index('from app import create_app')
        assert default_at < import_at, (
            'config.py reads FLASK_DEBUG while `class Config` executes, i.e. '
            'during the import of the factory -- defaulting it afterwards is '
            'too late')

    def test_the_env_file_is_loaded_before_the_default_is_applied(self):
        """Order decides who wins. `load_dotenv` defaults to `override=False`,
        so anything written into `os.environ` before `.env` is read beats the
        operator's own `FLASK_DEBUG` when `config.py` loads the same file --
        silently, and in the fail-OPEN direction, since DEBUG=True is what
        downgrades the refusal to a log line."""
        statements = _app_py_statements()

        assert statements.index('load_dotenv(') < \
            statements.index("os.environ['FLASK_DEBUG']")

    def test_the_default_yields_to_an_explicitly_set_value(self):
        """`FLASK_DEBUG=0` -- in the shell or in the `.env` loaded just above
        -- must still produce a non-debug app. A BLANK value must not count as
        set: `FLASK_DEBUG=` satisfies "already present" while `config.py`
        parses it as OFF, which would leave `python app.py` refusing to boot
        for the very reason this block exists to prevent."""
        _, main_guard = _app_py_main_guard()
        writes = [node for node in ast.walk(main_guard)
                  if isinstance(node, ast.Assign)
                  and 'FLASK_DEBUG' in ast.dump(node.targets[0])]

        assert len(writes) == 1, 'expected exactly one FLASK_DEBUG assignment'
        condition = next(node for node in ast.walk(main_guard)
                         if isinstance(node, ast.If) and writes[0] in node.body)
        condition_source = ast.dump(condition.test)
        assert 'FLASK_DEBUG' in condition_source, (
            'the assignment is unconditional, so an explicit FLASK_DEBUG=0 '
            'would be overridden')
        assert 'strip' in condition_source, (
            'a blank FLASK_DEBUG must be treated as unset, not as a decision')

    def test_the_default_is_confined_to_running_the_script(self):
        """It mutates the environment of the whole PROCESS, and DEBUG=True is
        precisely what downgrades the refusal to a log line. At module scope,
        anything that loads this file -- by path, by a future `FLASK_APP`
        pointing at it -- would disarm the guard for every `create_app()` in
        that interpreter as a side effect of an import."""
        tree, main_guard = _app_py_main_guard()

        assert main_guard is not None, (
            'app.py has no `if __name__ == "__main__":` block')
        outside_the_guard = ast.dump(ast.Module(
            body=[node for node in tree.body if node is not main_guard],
            type_ignores=[]))
        assert 'FLASK_DEBUG' not in outside_the_guard
        assert 'FLASK_DEBUG' in ast.dump(main_guard)


@pytest.mark.unit
class TestValidateSecretKeyOnItsOwn:
    """The guard is a leaf function, so its branches are checkable without
    building an app -- including states no config class in the tree produces."""

    @pytest.mark.parametrize('key', [None, '', '   ', '\t\n'])
    def test_an_unset_or_blank_key_refuses_a_non_debug_boot(self, key):
        """Strictly worse than the published fallback, and reachable by two
        different routes. A WHITESPACE-ONLY value is truthy, so `config.py`'s
        `or` never reaches the fallback and the app really does sign cookies
        with spaces. `None` and `''` are falsy and would be resolved to the
        fallback by `config.py`; they reach the guard from a config class that
        hard-codes them, and are refused here on their own terms."""
        with pytest.raises(ConfigurationError) as excinfo:
            validate_secret_key({'SECRET_KEY': key}, _Recorder())

        assert excinfo.value.config_key == 'SECRET_KEY'

    def test_a_missing_key_entry_is_treated_as_unset(self):
        with pytest.raises(ConfigurationError):
            validate_secret_key({}, _Recorder())

    def test_a_key_of_the_wrong_type_names_the_type_and_not_the_value(self):
        with pytest.raises(ConfigurationError) as excinfo:
            validate_secret_key({'SECRET_KEY': 12345}, _Recorder())

        assert 'int' in str(excinfo.value)
        assert '12345' not in str(excinfo.value)

    def test_surrounding_whitespace_does_not_hide_a_published_key(self):
        """The commonest hand-edited `.env` artifact there is. The value is
        byte-different from the published one and exactly as public."""
        with pytest.raises(ConfigurationError):
            validate_secret_key({'SECRET_KEY': f' {DEV_SECRET_KEY_FALLBACK} '},
                                _Recorder())

    def test_a_published_key_written_as_bytes_is_still_recognized(self):
        """Flask accepts a bytes key, and the same characters are no less
        public for being spelled `b'...'`."""
        with pytest.raises(ConfigurationError):
            validate_secret_key(
                {'SECRET_KEY': DEV_SECRET_KEY_FALLBACK.encode()}, _Recorder())

    def test_undecodable_random_bytes_are_a_perfectly_good_key(self):
        """What `secrets.token_bytes(32)` produces. Refusing it would push
        operators towards the text keys this guard is trying to move them off."""
        recorder = _Recorder()
        validate_secret_key({'SECRET_KEY': b'\xff\xfe\x00\x80' * 8}, recorder)

        assert recorder.errors == []

    def test_a_real_key_returns_silently_whatever_the_flags_say(self):
        recorder = _Recorder()
        for flags in ({}, {'DEBUG': True}, {'TESTING': True},
                      {'DEBUG': False, 'TESTING': False}):
            validate_secret_key({'SECRET_KEY': _REAL_KEY, **flags}, recorder)

        assert recorder.errors == []

    def test_absent_debug_and_testing_flags_count_as_non_debug(self):
        """Flask defaults `TESTING` to False and `config.Config` never sets it,
        so the production path is the one where NEITHER flag is written
        anywhere. A guard that required them to be present would never fire."""
        with pytest.raises(ConfigurationError) as excinfo:
            validate_secret_key({'SECRET_KEY': DEV_SECRET_KEY_FALLBACK},
                                _Recorder())

        assert excinfo.value.config_key == 'SECRET_KEY'

    @pytest.mark.parametrize('flags', [{'DEBUG': True},
                                       {'TESTING': True},
                                       {'DEBUG': True, 'TESTING': True}])
    def test_either_flag_alone_is_enough_to_downgrade_to_a_log(self, flags):
        recorder = _Recorder()
        validate_secret_key({'SECRET_KEY': DEV_SECRET_KEY_FALLBACK, **flags},
                            recorder)

        assert len(recorder.errors) == 1
        assert 'SECRET_KEY' in recorder.errors[0]

    @pytest.mark.parametrize('flags', [{'DEBUG': 'False'},
                                       {'TESTING': 'False'},
                                       {'DEBUG': 'no'},
                                       {'DEBUG': 1},
                                       {'TESTING': 'yes'}])
    def test_a_non_boolean_flag_does_not_downgrade_the_refusal(self, flags):
        """`'False'` is TRUTHY. A bare truthiness test here would read the
        commonest unguarded `os.environ.get('FLASK_DEBUG')` result as "debug
        mode on" and silently turn a production refusal into a log line -- a
        fail-OPEN failure in a security control."""
        with pytest.raises(ConfigurationError):
            validate_secret_key({'SECRET_KEY': DEV_SECRET_KEY_FALLBACK,
                                 **flags}, _Recorder())

    @pytest.mark.parametrize('fallbacks', [
        [DEV_SECRET_KEY_FALLBACK],
        [_REAL_KEY, DEV_SECRET_KEY_FALLBACK],
        (DEV_SECRET_KEY_FALLBACK.title(),),
        [''],
        DEV_SECRET_KEY_FALLBACK,             # a bare string, not a sequence
        DEV_SECRET_KEY_FALLBACK.encode(),
    ])
    def test_a_published_key_left_in_the_fallback_list_is_refused(self,
                                                                 fallbacks):
        """Flask 3.1 still VALIDATES session cookies and CSRF tokens against
        every entry in `SECRET_KEY_FALLBACKS`, so a published key parked there
        is forgeable even though `SECRET_KEY` itself is private -- and leaving
        the old value behind is exactly what the rotation procedure Flask
        documents produces."""
        with pytest.raises(ConfigurationError) as excinfo:
            validate_secret_key({'SECRET_KEY': _REAL_KEY,
                                 'SECRET_KEY_FALLBACKS': fallbacks},
                                _Recorder())

        assert 'SECRET_KEY_FALLBACKS' in str(excinfo.value)
        assert excinfo.value.config_key == 'SECRET_KEY'

    @pytest.mark.parametrize('fallbacks', [None, [], (), [_REAL_KEY]])
    def test_an_absent_or_private_fallback_list_returns_silently(self,
                                                                 fallbacks):
        """The overwhelmingly common case is no rotation at all: `Flask`
        defaults the key to `None`, and a guard that complained about that
        would fire on every boot in the tree."""
        recorder = _Recorder()
        validate_secret_key({'SECRET_KEY': _REAL_KEY,
                             'SECRET_KEY_FALLBACKS': fallbacks}, recorder)

        assert recorder.errors == []
        assert recorder.criticals == []

    def test_a_fallback_list_that_is_not_iterable_is_refused(self):
        """Flask would fail on it later anyway; failing closed here costs
        nothing and names the key."""
        with pytest.raises(ConfigurationError):
            validate_secret_key({'SECRET_KEY': _REAL_KEY,
                                 'SECRET_KEY_FALLBACKS': 12345}, _Recorder())

    def test_the_secret_key_itself_is_diagnosed_before_the_fallback_list(self):
        """Both wrong is the likeliest way to get here, and the operator needs
        the primary key named first -- fixing the list alone would leave the
        app signing NEW cookies with a public value."""
        with pytest.raises(ConfigurationError) as excinfo:
            validate_secret_key(
                {'SECRET_KEY': DEV_SECRET_KEY_FALLBACK,
                 'SECRET_KEY_FALLBACKS': [DEV_SECRET_KEY_FALLBACK]},
                _Recorder())

        assert 'SECRET_KEY_FALLBACKS' not in str(excinfo.value)

    def test_a_debug_app_only_logs_about_the_fallback_list(self):
        """Same asymmetry as every other diagnosis: a developer mid-rotation
        keeps a working app and gets told."""
        recorder = _Recorder()
        validate_secret_key({'SECRET_KEY': _REAL_KEY,
                             'SECRET_KEY_FALLBACKS': [DEV_SECRET_KEY_FALLBACK],
                             'DEBUG': True}, recorder)

        assert len(recorder.errors) == 1
        assert 'SECRET_KEY_FALLBACKS' in recorder.errors[0]
        assert recorder.criticals == []

    def test_the_raised_error_is_catchable_as_the_leaf_configuration_error(self):
        """`app.exceptions.ConfigurationError` subclasses the one in
        `config.py`, so an entry point that catches configuration failures with
        `except config.ConfigurationError` catches this one too."""
        with pytest.raises(config_module.ConfigurationError):
            validate_secret_key({'SECRET_KEY': DEV_SECRET_KEY_FALLBACK},
                                _Recorder())

