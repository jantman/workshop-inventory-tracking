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

    # The next three calls are ORDERED, and the order is load-bearing:
    #
    #   setup_logging       calls app.logger.handlers.clear() (and empties the
    #                       root logger too), so any log record emitted before it
    #                       bypasses the structured JSON pipeline operators are
    #                       told to aggregate.
    #   init_request_limits validates the body limits (and may emit exactly that
    #                       kind of startup warning), then installs the WSGI
    #                       body cap and its before_request hook.
    #   csrf.init_app       registers CSRFProtect's own before_request hook,
    #                       which parses the form. Registering the body limit
    #                       first keeps an oversize body rejected as a clean 413
    #                       rather than surfacing as a confusing CSRF failure.
    #
    # See app/request_limits.py's module docstring.
    setup_logging(app)
    init_request_limits(app)
    csrf.init_app(app)

    # Setup error handlers
    create_error_handlers(app)

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    return app
