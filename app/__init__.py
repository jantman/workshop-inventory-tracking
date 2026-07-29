from flask import Flask
from flask_wtf.csrf import CSRFProtect
# Plain module-scope import, restored: `config.py` is a leaf that imports
# nothing from this package (`ConfigurationError` is defined there and adopted
# by `app/exceptions.py`, not the other way round), so there is no cycle to work
# around here. tests/unit/test_request_limits.py pins both import directions
# from a cold interpreter.
from config import Config
from app.logging_config import setup_logging
from app.error_handlers import create_error_handlers
from app.request_limits import init_request_limits
from app.secret_key_guard import validate_secret_key

csrf = CSRFProtect()

def create_app(config_class=Config, storage_backend=None):
    """
    Create Flask application factory with optional storage backend injection.

    Args:
        config_class: Configuration class to use (defaults to Config)
        storage_backend: Optional storage backend instance for testing
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Store the storage backend in app config for access by routes
    if storage_backend:
        app.config['STORAGE_BACKEND'] = storage_backend

    # The next four calls are ORDERED, and the order is load-bearing:
    #
    #   setup_logging       calls app.logger.handlers.clear() (and empties the
    #                       root logger too), so any log record emitted before it
    #                       bypasses the structured JSON pipeline operators are
    #                       told to aggregate.
    #   validate_secret_key refuses to boot a non-debug app whose SECRET_KEY is
    #                       one this repository publishes (or is missing), and
    #                       logs at ERROR when a debug/testing app lands on one.
    #                       It must run AFTER setup_logging or that ERROR record
    #                       never reaches the JSON pipeline. Its position ahead
    #                       of the other two is preference, not requirement --
    #                       a raise anywhere in this factory aborts the boot
    #                       just as completely -- but it is the cheapest and
    #                       most fundamental check, so nothing else is installed
    #                       on a key already known to be forgeable.
    #   init_request_limits validates the body limits (and may emit exactly that
    #                       kind of startup warning), then installs the WSGI
    #                       body cap and its before_request hook.
    #   csrf.init_app       registers CSRFProtect's own before_request hook,
    #                       which parses the form. Registering the body limit
    #                       first keeps an oversize body rejected as a clean 413
    #                       rather than surfacing as a confusing CSRF failure.
    #
    # See app/request_limits.py's and app/secret_key_guard.py's module
    # docstrings.
    setup_logging(app)
    validate_secret_key(app.config, app.logger)
    init_request_limits(app)
    csrf.init_app(app)

    # Setup error handlers
    create_error_handlers(app)

    # The app-scoped storage (app/db.py) lives for the life of the process, so
    # its scoped_session registry does too -- unlike the old per-request storage
    # object, which was simply discarded. Drop the calling thread's session at
    # the end of each app context so a worker thread doesn't hold one open
    # forever. Injected test backends are left alone: their lifetime belongs to
    # the fixture that created them.
    @app.teardown_appcontext
    def _remove_app_scoped_session(exception=None):
        from app.db import STORAGE_EXTENSION_KEY
        storage = app.extensions.get(STORAGE_EXTENSION_KEY)
        # Read the registry once: a concurrent close()/reconnect nulls
        # `storage.Session`, so checking and using it as two reads can hand this
        # hook a None.
        registry = getattr(storage, 'Session', None) if storage is not None else None
        if registry is None:
            return
        try:
            registry.remove()
        except Exception:
            # Session.remove() closes connections and can raise (a dropped
            # pooled connection resurfaces as OperationalError). This runs from
            # AppContext.pop() in Flask's `finally`, after the response has
            # already gone out, so an exception here escapes past the error
            # handlers as an unhandled traceback on an otherwise-successful
            # request. Failing to release a session is not worth that.
            app.logger.warning('Failed to remove app-scoped session', exc_info=True)

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    return app
