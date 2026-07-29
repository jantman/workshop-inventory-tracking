import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))


class ConfigurationError(Exception):
    """Raised when a configuration value is invalid or missing.

    Defined HERE, in a leaf module, and not in `app/exceptions.py`, for one
    concrete reason: `_bytes_from_env` below raises it while the `class Config`
    body is being executed, i.e. during `import config`. Importing anything from
    the `app` package to do that would execute `app/__init__.py`, which imports
    `config` — so a cold `import config` with a malformed env value would die
    with a confusing partial-import `ImportError` instead of the named error an
    operator needs. Keeping this module free of `app` imports is what lets
    `app/__init__.py` say plain `from config import Config` at module scope,
    with no lazy-import workaround in the factory. Both directions are pinned by
    the subprocess tests in tests/unit/test_request_limits.py.

    `app.exceptions.ConfigurationError` subclasses this one, so
    `except config.ConfigurationError` catches configuration failures from
    either side of that line while the app-side class keeps its place in the
    `WorkshopInventoryError` hierarchy that `app/error_handlers.py` dispatches
    on. The attribute surface is the same on both.
    """

    def __init__(self, message: str, config_key: str = None):
        super().__init__(message)
        self.message = message
        self.config_key = config_key


# The development stand-in for `SECRET_KEY`, used when the environment does not
# supply one. It is committed to this repository, so it is public: anything
# signed with it -- every Flask session cookie, every CSRF token -- is forgeable
# by anyone who can read this file. It is NAMED here, once, so that
# `app/secret_key_guard.py` can recognise it by identity instead of carrying a
# second copy of the string that could drift from this one. `config.py` stays a
# leaf module (see `ConfigurationError` above), so the guard imports this
# constant rather than the other way round.
DEV_SECRET_KEY_FALLBACK = 'dev-secret-key-change-in-production'

# Every `SECRET_KEY` value this repository has published AS DEPLOYMENT
# CONFIGURATION, not just the fallback: the placeholder `.env.example` ships,
# and the one `docs/deployment-guide.md` used to offer as the content of a
# PRODUCTION `.env`. All of them are readable by anyone who can read this
# repository, so all of them sign forgeable cookies and CSRF tokens, and
# `app/secret_key_guard.py` treats them identically. A guard that knew only the
# fallback would wave through the value the deployment documentation itself
# handed out -- the one an operator is most likely to actually be running.
#
# The qualifier is load-bearing, and this set is NOT "every string in the repo
# that could be a key". `tests/test_config.py` commits one too, and it is
# deliberately absent: it is reachable only from a `TESTING = True` config, i.e.
# only from the branch that logs rather than refuses, and adding it would make
# every unit-test app boot emit an ERROR about a key no deployment can resolve
# to. The membership test is "could a deployment end up running this?".
#
# ENTRIES ARE NEVER REMOVED, only added: the deployment guide no longer prints
# its placeholder, but every `.env` already created from the old text still
# contains it, and those are exactly the deployments this exists to catch.
PUBLISHED_SECRET_KEYS = frozenset({
    DEV_SECRET_KEY_FALLBACK,
    'your-secret-key-here',              # .env.example
    'your-secret-key-here-change-this',  # docs/deployment-guide.md, pre-2026-07
})


def _bytes_from_env(name, default):
    """Read a byte-count setting from the environment, or return `default`.

    Accepts ONLY plain ASCII digits. No sign (`+1024`), no `_` grouping
    (`1_048_576`), no non-ASCII digits — all of which `int()` would happily
    accept and none of which anyone writes on purpose in a `.env` file.
    Unset, or set to a blank/whitespace-only value, reads as unset and takes
    the default, matching the `os.environ.get(...) or default` idiom used
    elsewhere in this file (a stray blank line in `.env` must not become a hard
    failure).

    SURROUNDING WHITESPACE IS STRIPPED before any of that is decided.
    `MAX_REQUEST_BODY_BYTES=1024 ` with one trailing space is the commonest
    hand-edited `.env` artifact there is, and refusing to boot on it while
    treating an all-whitespace value as absent is incoherent — the same
    character is fatal in one position and ignored in the other.

    A malformed value raises `ConfigurationError` naming the variable rather
    than letting a bare `ValueError` escape from the `class Config` body: the
    one malformed input an operator actually produces is
    `MAX_REQUEST_BODY_BYTES=1MB`, and a traceback out of a class body at import
    time tells them nothing about which key is wrong. Note the `int()` call is
    guarded too — CPython caps integer-string conversion at 4300 digits, so an
    absurdly long all-digits value raises `ValueError` from `int()` itself.
    """
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    raw = raw.strip()

    if not (raw.isascii() and raw.isdigit()):
        raise ConfigurationError(
            f'{name} must be a whole number of bytes written as plain digits; '
            f'got {raw!r}',
            config_key=name)

    try:
        return int(raw)
    except ValueError:
        # `from None`: the underlying "Exceeds the limit (4300 digits) for
        # integer string conversion" is an implementation detail, and the
        # "During handling of the above exception, another exception occurred"
        # preamble buries the one line an operator needs to read.
        raise ConfigurationError(
            f'{name} is not a usable byte count: {len(raw)} digits is beyond '
            f"Python's integer-conversion limit",
            config_key=name) from None


class Config:
    # Resolution semantics are deliberately unchanged: unset, or set to a blank
    # value, falls back. What is new is that `app/secret_key_guard.py` refuses
    # to boot a non-debug app that lands on the fallback.
    SECRET_KEY = os.environ.get('SECRET_KEY') or DEV_SECRET_KEY_FALLBACK
    
    # Database connection string for SQLAlchemy - use directly from .env file
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_timeout': 20,
        'pool_recycle': -1,
        'pool_pre_ping': True,
    }
    
    # Google Sheets API Configuration (for migration and export functionality)
    GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE') or os.path.join(basedir, 'credentials', 'credentials.json')
    GOOGLE_TOKEN_FILE = os.environ.get('GOOGLE_TOKEN_FILE') or os.path.join(basedir, 'credentials', 'token.json')
    GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    
    # Application Configuration
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'yes']
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # Transport-level bound on the request body, enforced at the WSGI layer by
    # app/request_limits.py. Two limits, because the app has two populations of
    # request: JSON/form traffic, where 1 MiB is orders of magnitude above the
    # largest legitimate body, and the two file-upload endpoints, which need
    # room for a real photo or attachment.
    #
    # These names are DELIBERATE and must not be "tidied" onto Flask's own
    # body-limit config key: setting that key re-arms Werkzeug's TRUNCATING
    # limiter, which silently hands a view the first N bytes of a longer body
    # with a 200 instead of rejecting it. app/request_limits.py names the key
    # and carries the measurements; nothing else in the tree may mention it.
    #
    # This bound is ADDITIVE to the existing per-payload guards, not a
    # replacement for any of them: `MAX_SCAN_LENGTH` (app/utils/scan_input.py)
    # still bounds the scan `raw` field, `ATTACHMENT_MAX_SIZE`
    # (app/mariadb_catalog_service.py) still bounds an attachment, and
    # `PhotoService.MAX_FILE_SIZE` (app/photo_service.py) still bounds a
    # photo. Those produce the friendly, specific error for a merely-oversize
    # file; this one only stops a body the process should never have buffered
    # at all. Do not lower or remove them because this exists.
    #
    # Residual exposure, recorded rather than implied away: `main.upload_photo`
    # remains unauthenticated and `@csrf.exempt`, and reads its file fully into
    # memory — now formally sanctioned up to MAX_UPLOAD_BODY_BYTES per request.
    # Rate limiting is out of scope, so nothing here bounds uploads in
    # AGGREGATE; a caller can still make many such requests. Bound concurrent
    # exposure at the reverse proxy and the WSGI server.
    #
    # A second residual, stated the honest way round: the raised ceiling is
    # granted on the request's own `Content-Type`, which the CALLER writes. The
    # app requires `multipart/form-data` with a non-empty `boundary` parameter
    # before granting it (a bare mimetype would be one free word), but that is
    # still only a shape, not a proof. So the accurate statement of this bound
    # is "MAX_UPLOAD_BODY_BYTES applies to the two upload endpoints for anything
    # SHAPED LIKE a multipart body" — not "only for real uploads". Every other
    # route, and every non-multipart-shaped body to those two, gets
    # MAX_REQUEST_BODY_BYTES.
    MAX_REQUEST_BODY_BYTES = _bytes_from_env('MAX_REQUEST_BODY_BYTES', 1 * 1024 * 1024)
    # 24 MiB, not 20: a body carrying a file at PhotoService.MAX_FILE_SIZE
    # (20 MiB) is larger than 20 MiB on the wire once multipart boundaries and
    # part headers are counted, so a 20 MiB ceiling would 413 a legitimate
    # maximum-size photo before the service-layer check could explain why.
    MAX_UPLOAD_BODY_BYTES = _bytes_from_env('MAX_UPLOAD_BODY_BYTES', 24 * 1024 * 1024)

    # GS1 internal-identifier grammar (Story 2.4, FR12c, AD-16). The single
    # named pair the service passes into app/utils/gs1.py's encode/decode, so
    # one config change moves encoder and scan router together. app/utils/gs1.py
    # carries no literal defaults of its own.
    # `or` rather than a get() default: a key present but empty in .env would
    # otherwise override the default with '', which gs1.py rejects — turning a
    # stray blank line into a hard failure of every label and every scan.
    GS1_INTERNAL_AI = os.environ.get('GS1_INTERNAL_AI') or '96'
    GS1_INTERNAL_TOKEN = os.environ.get('GS1_INTERNAL_TOKEN') or 'WIT'

    # Ownership / return information for labels (Story 2.5, FR12d). Read through
    # CatalogService.ownership_label_text(); Epic 6 composites it into the
    # label's HUMAN-READABLE text region. It is never encoded: no code path
    # passes this value to gs1.encode, and no 43xx element string — the GS1
    # logistics AIs where such data would otherwise be carried — can be built at
    # all. Unset or blank means no ownership region, which is a valid
    # configuration rather than an error — hence `or ''` in the same idiom as
    # the GS1 pair above, so a key present but empty reads as unset. A
    # whitespace-only value is truthy and survives this line; the service strips
    # it, which is where blank-after-trimming is normalized.
    LABEL_OWNER_TEXT = os.environ.get('LABEL_OWNER_TEXT') or ''


class TestConfig(Config):
    """Test configuration using MariaDB test database"""
    TESTING = True
    
    # Test database configuration
    DB_HOST = os.environ.get('TEST_DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('TEST_DB_PORT', 3307))  # Different port for test container
    DB_USER = os.environ.get('TEST_DB_USER', 'inventory_test_user')
    DB_PASSWORD = os.environ.get('TEST_DB_PASSWORD', 'test_password')
    DB_NAME = os.environ.get('TEST_DB_NAME', 'workshop_inventory_test')
    
    # Override database URI for testing
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    
    # Test-specific engine options
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'pool_timeout': 10,
        'pool_recycle': -1,
        'pool_pre_ping': True,
    }
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False
    
    # Google Sheets API Configuration (legacy, for export functionality)
    GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE') or os.path.join(basedir, 'credentials', 'credentials.json')
    GOOGLE_TOKEN_FILE = os.environ.get('GOOGLE_TOKEN_FILE') or os.path.join(basedir, 'credentials', 'token.json')
    GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    
    # Application Configuration
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 'yes']
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    @staticmethod
    def validate_config():
        """Validate that required configuration is present"""
        errors = []
        
        # Database configuration validation
        if not Config.SQLALCHEMY_DATABASE_URI:
            errors.append("SQLALCHEMY_DATABASE_URI environment variable is required")
        
        # Google Sheets configuration (for migration and export functionality)
        if Config.GOOGLE_SHEET_ID and not os.path.exists(Config.GOOGLE_CREDENTIALS_FILE):
            errors.append(f"Google credentials file not found: {Config.GOOGLE_CREDENTIALS_FILE}")
        
        return errors