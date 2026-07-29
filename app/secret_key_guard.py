"""Boot-time guard on `SECRET_KEY`.

`config.Config` resolves `SECRET_KEY` from the environment and falls back to
`config.DEV_SECRET_KEY_FALLBACK` when nothing is set. That fallback is committed
to this repository, so it is public: an app running on it signs every Flask
session cookie and every CSRF token with a key anyone can read, and both are
therefore forgeable. Nothing about a boot on the fallback looks different from a
boot on a real key -- which is the whole problem this module exists to fix.

The check is against `config.PUBLISHED_SECRET_KEYS`, not against the fallback
alone, because the fallback is not the only signing key this repository
publishes: `.env.example` and `docs/deployment-guide.md` each hand out a
placeholder, and the deployment guide's is offered as the content of a
PRODUCTION `.env`. A guard that recognised only the fallback would say nothing
about the value an operator following the documentation is most likely to be
running. An unset, blank or unusable key is refused on the same terms: those are
strictly worse than a public one, and failing closed on them costs nothing that
a real deployment wants. `SECRET_KEY_FALLBACKS` is held to the same standard:
Flask still VALIDATES cookies and tokens against every key in that list, so a
published value parked there is forgeable even when `SECRET_KEY` itself is
private.

**Why the debug/testing branch only logs.** Refusing to boot there would break
the test suites that build apps from `config.TestConfig` (which inherits the
fallback) and any developer running with `FLASK_DEBUG` on -- `flask run` gets
that from `.flaskenv`, and `app.py` sets it for the same reason. The argument is
NOT that a debug app is unreachable by an attacker; `flask run --host=0.0.0.0`
is one flag away from the committed `.flaskenv` defaults, and
`tests/e2e/test_server.py` boots a real listening server from a `TESTING` config.
It is that a debug app has already accepted a strictly larger exposure than a
forgeable cookie -- the Werkzeug debugger is remote code execution -- so
refusing to boot on the key would buy nothing there while breaking every
development and test workflow in the repository. The developer keeps a working
default and gets a loud ERROR record; the deployment gets a hard stop.

That asymmetry is only as good as the flags, and this repository commits
`.flaskenv` with `FLASK_DEBUG=1`: anyone running `flask run` from a checkout
gets the log branch, not the refusal. Such a deployment is running the debugger
in production and has a much larger problem than its signing key, but the guard
is genuinely silent about it -- see the deferred-work ledger.

Note what that does NOT promise: a plain non-debug boot on a fresh checkout --
`python -c "import wsgi"`, gunicorn, anything that does not declare
`FLASK_DEBUG` -- refuses to start until a key is set. That is the intended
outcome, not an accident, and it is why `app.py` declares its debug intent in
the environment before importing the factory.

**Ordering constraint.** `validate_secret_key` must be called *after*
`setup_logging(app)`, whose `app.logger.handlers.clear()` would otherwise
discard the ERROR record before it reaches the structured JSON pipeline. It is
placed first in the block that follows because it is the cheapest and most
fundamental of the startup checks; that position, unlike the dependency on
`setup_logging`, is a preference rather than a requirement -- a raise anywhere
in `create_app` aborts the boot just as completely. See the comment in
`app/__init__.py`.
"""

from collections.abc import Mapping
from typing import Any, Optional

from config import PUBLISHED_SECRET_KEYS

from app.exceptions import ConfigurationError

# Membership is tested casefolded. A placeholder retyped or autocapitalised as
# `Your-Secret-Key-Here` is character-for-character as public as the lowercase
# spelling, and no random key is one casefold away from a published one, so this
# only ever moves values in the refuse direction. Derived from
# PUBLISHED_SECRET_KEYS rather than written out, for the same reason the guard
# holds no copy of the literals at all.
#
# Stripped as well as casefolded, so that the two sides of the comparison are
# normalised identically -- `_diagnose` strips the candidate. Entries are added
# to PUBLISHED_SECRET_KEYS and never removed, so an entry that arrived with a
# stray leading or trailing space would otherwise match nothing, permanently and
# silently.
_PUBLISHED_CASEFOLDED = frozenset(
    published.strip().casefold() for published in PUBLISHED_SECRET_KEYS)

# One remedy sentence, shared by every diagnosis below so they cannot drift into
# telling an operator different things about the same variable.
_REMEDY = (
    "Set the SECRET_KEY environment variable (or the SECRET_KEY entry in .env) "
    "to a private random value, e.g. the output of "
    "`python -c \"import secrets; print(secrets.token_hex(32))\"`."
)

# None of these interpolate the resolved value. This text goes to logs and into
# a traceback, and a diagnostic that echoes a key is a way to leak one -- while
# a published placeholder needs no echoing, since it is in the repository.
#
# `_PUBLISHED` names all three ways of arriving at a published value on purpose.
# `config.py` resolves `os.environ.get('SECRET_KEY') or DEV_SECRET_KEY_FALLBACK`,
# so an UNSET and an EMPTY variable both land on the fallback and reach this
# message -- and `SECRET_KEY=` (blank) is exactly what `docs/deployment-guide.md`
# now tells an operator to write before generating a key. Saying only "set to a
# placeholder" would send that operator looking through their `.env` for a
# placeholder they never wrote.
_PUBLISHED = (
    "SECRET_KEY is unset, empty, or set to a placeholder committed to this "
    "repository, so the key in use is one anyone can read. Flask session "
    "cookies and CSRF tokens signed with it can be forged by anyone. " + _REMEDY
)
_MISSING = (
    "SECRET_KEY is not set at all, so nothing can sign a Flask session cookie "
    "or a CSRF token. " + _REMEDY
)
# Reached only for a value that is non-empty but all whitespace: an empty string
# is falsy, so `config.py`'s `or` sends it to the fallback and `_PUBLISHED`
# before this can apply. A config class that hard-codes `SECRET_KEY = ''`
# bypasses that resolution and lands here, which is why the wording covers both
# rather than asserting the value is non-empty.
_BLANK = (
    "SECRET_KEY is set to an empty or whitespace-only value, which is as "
    "guessable as no key at all. " + _REMEDY
)
_UNUSABLE = (
    "SECRET_KEY is of type {type_name}, which is neither text nor bytes and "
    "cannot sign anything. " + _REMEDY
)
# Flask 3.1 accepts `SECRET_KEY_FALLBACKS`: additional keys that no longer SIGN
# anything but are still ACCEPTED when validating an existing session cookie or
# CSRF token, so that a key rotation does not log everyone out. A published key
# left in that list is forgeable on exactly the same terms as a published
# `SECRET_KEY` -- the app honours anything signed with it -- and the rotation
# procedure Flask documents is precisely the one that leaves the old value
# behind. Nothing in this repository sets the key today; the guard asks the same
# question of every entry so that it never has to be remembered later.
_FALLBACKS = (
    "SECRET_KEY_FALLBACKS contains a key that is published in this repository, "
    "empty, or otherwise unusable. Flask validates session cookies and CSRF "
    "tokens against every entry in that list, so such a value is forgeable "
    "even though SECRET_KEY itself is private. Remove it from "
    "SECRET_KEY_FALLBACKS."
)


def _diagnose(key: Any) -> Optional[str]:
    """The problem with `key`, or `None` if there is nothing wrong with it.

    Bytes are compared as text where they decode, because a placeholder written
    into a config class as `b'...'` is exactly as public as the same characters
    written as `'...'`. Bytes that do NOT decode are left alone: that is what
    `secrets.token_bytes(32)` produces, and it is a perfectly good key.

    Surrounding whitespace is stripped, and the comparison is casefolded, before
    membership is tested. A key with a trailing space -- the commonest
    hand-edited `.env` artifact there is, and one `config.py`'s `_bytes_from_env`
    already strips for the same reason -- or one retyped with a capital is
    byte-different from the published value and just as public.

    Note what is NOT checked: length, entropy, or any other measure of key
    quality. `SECRET_KEY=x` passes. This guard answers one question -- "is the
    app running on a key this repository handed out?" -- and a quality floor is
    a separate policy with separate failure modes; see the deferred-work ledger.
    """
    if isinstance(key, (bytes, bytearray)):
        try:
            key = bytes(key).decode('utf-8')
        except UnicodeDecodeError:
            return None

    if key is None:
        return _MISSING
    if not isinstance(key, str):
        return _UNUSABLE.format(type_name=type(key).__name__)

    key = key.strip()
    if not key:
        return _BLANK
    if key.casefold() in _PUBLISHED_CASEFOLDED:
        return _PUBLISHED
    return None


def _fallbacks_are_unsafe(fallbacks: Any) -> bool:
    """Whether `SECRET_KEY_FALLBACKS` carries a key that must not be honoured.

    A `str`/`bytes` value is wrapped rather than iterated: Flask expects a
    sequence here, but someone writing a single key by mistake must be told
    about that key, not about four hundred one-character ones. Anything that is
    not iterable at all is refused -- Flask would fail on it later anyway, and
    the fail-closed direction is the one that costs nothing.
    """
    if fallbacks is None:
        return False
    if isinstance(fallbacks, (str, bytes, bytearray)):
        fallbacks = [fallbacks]
    try:
        entries = list(fallbacks)
    except TypeError:
        return True
    return any(_diagnose(entry) is not None for entry in entries)


def _is_on(flag: Any) -> bool:
    """Whether a `DEBUG`/`TESTING` flag is genuinely switched on.

    Only the boolean `True` counts, and the strictness is deliberate: a bare
    truthiness test reads the string `'False'` -- precisely what an unguarded
    `os.environ.get('FLASK_DEBUG')` yields -- as ON, and that failure is in the
    fail-OPEN direction for a security control, silently downgrading a
    production refusal to a log line. Anything else is treated as off, so an
    unrecognised value refuses to boot rather than waving itself through.
    `app/request_limits.py` rejects a `bool` masquerading as an `int` for the
    mirror-image reason.
    """
    return flag is True


def validate_secret_key(config: Mapping[str, Any],
                        logger: Any) -> None:
    """Check the resolved `SECRET_KEY` at startup.

    Logs at CRITICAL and then raises `ConfigurationError` -- aborting the boot --
    when a config that is neither `DEBUG` nor `TESTING` resolved `SECRET_KEY` to
    a value this repository publishes, or to no usable value at all, or left
    such a value in `SECRET_KEY_FALLBACKS`. On a debug or testing config the
    same condition is logged at ERROR and the boot continues; see the module
    docstring for why the two branches differ. Any other value returns silently.

    `config` is `app.config` (a mapping) and `logger` is `app.logger`, matching
    `app.request_limits.validate_limits`.
    """
    problem = _diagnose(config.get('SECRET_KEY'))
    if problem is None and _fallbacks_are_unsafe(
            config.get('SECRET_KEY_FALLBACKS')):
        problem = _FALLBACKS
    if problem is None:
        return

    # Read from `app.config` rather than from the class: Flask defaults
    # `TESTING` to False and `config.Config` never sets it, so a production boot
    # evaluates as non-debug here without either flag being written anywhere.
    if _is_on(config.get('DEBUG')) or _is_on(config.get('TESTING')):
        logger.error(problem)
        return

    # Logged CRITICAL *and* raised. The raise is what stops the boot, but it
    # surfaces only as a traceback on stderr -- unstructured, and invisible to
    # the JSON pipeline this call was deliberately ordered behind
    # `setup_logging` in order to reach. Without this line the branch that
    # matters most is the one branch an operator aggregating logs cannot see.
    #
    # The SAME text is logged and raised, prefix included. Logging the bare
    # `problem` would put a record on the stream byte-identical to the one the
    # debug branch emits above, distinguishable only by its level: the reader
    # who most needs to know that a process just died would have to infer it
    # from a field rather than read it in the message.
    refusal = f'Refusing to start: {problem}'
    logger.critical(refusal)
    raise ConfigurationError(refusal, config_key='SECRET_KEY')
