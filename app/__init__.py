from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from app.logging_config import setup_logging
from app.error_handlers import create_error_handlers
from app.version import __version__

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

    # Behind a TLS-terminating reverse proxy the app itself speaks plain HTTP,
    # so Werkzeug reports `request.scheme == 'http'` for a page the browser
    # loaded over https. That is not cosmetic: the capture bookmarklet bakes in
    # `url_for(..., _external=True)` addresses at render time, so it shipped
    # http:// addresses that a vendor's `upgrade-insecure-requests` then broke
    # (issue #89). Trusting one hop of X-Forwarded-Proto / -Host fixes the
    # scheme, the host and therefore those URLs. This is LAN-only with one
    # trusted user, so there is no header-spoofing concern -- but it does mean
    # the proxy has to actually set the headers, which the deployment guide
    # says.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Store the storage backend in app config for access by routes
    if storage_backend:
        app.config['STORAGE_BACKEND'] = storage_backend
    
    # Setup CSRF protection
    csrf.init_app(app)
    
    # Setup logging
    setup_logging(app)
    
    # Setup error handlers
    create_error_handlers(app)
    
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    from app.product import bp as product_bp
    app.register_blueprint(product_bp)

    # Make the version available to all templates
    @app.context_processor
    def inject_version():
        return {'app_version': __version__}

    return app