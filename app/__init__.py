from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config
from app.logging_config import setup_logging
from app.error_handlers import create_error_handlers
from app.version import __version__

csrf = CSRFProtect()


def _drop_malformed_forwarded_port(wsgi_app):
    """Ignore X-Forwarded-Port unless it is a plain decimal number.

    ProxyFix appends whatever it is handed to the host, and
    `werkzeug.sansio.utils.get_host` returns the *empty string* for a host
    containing characters a host cannot contain. So one malformed header
    turns every address the app builds into `https:///...` and refuses every
    secure form -- with no error, no log line, and a site whose every link is
    malformed.

    This is not input hardening; the single trusted hop needs none. It is
    there because without it trusting the port at all would be worse than not
    trusting it: before issue #114 the same header was simply ignored, and
    falling back to the arriving host restores exactly that. `isascii` because
    `isdigit` alone accepts non-ASCII digits, which are not valid in a host.

    Digits are not sufficient on their own. `get_host` checks characters, not
    range, so `:99999999` survives into request.host -- and Flask-WTF's
    referrer check compares `urlparse(...).port`, which *raises* `Port out of
    range 0-65535` rather than returning False. That turns every secure write
    into an unhandled 500: reads healthy, writes failing, which is the shape of
    the bug this guard exists alongside. Hence the bound.

    Bounded and no further. A port that is wrong but real -- 9090 when the
    proxy is on 15603 -- is left alone to produce a visibly wrong address and a
    readable 400, the same as a wrong hostname would.
    """
    def middleware(environ, start_response):
        port = environ.get('HTTP_X_FORWARDED_PORT')
        if port is not None and not (
            port.isascii() and port.isdigit() and int(port) <= 65535
        ):
            del environ['HTTP_X_FORWARDED_PORT']
        return wsgi_app(environ, start_response)

    return middleware


def _build_digikey_client(config):
    """Build the DigiKey client from config, or None when it is not configured.

    Absent credentials are not an error. The catalog worked without DigiKey
    before feature 024 and still does; only the DigiKey screens change, and they
    say why (024 FR-036, FR-037).

    The import is local because ``app/services/digikey.py`` pulls in ``requests``
    and this factory is imported by ``manage.py`` and the migration environment,
    neither of which has any use for an HTTP client.
    """
    if not config.get('DIGIKEY_CLIENT_ID') or not config.get('DIGIKEY_CLIENT_SECRET'):
        return None

    from app.services.digikey import DigiKeyClient

    return DigiKeyClient(
        client_id=config['DIGIKEY_CLIENT_ID'],
        client_secret=config['DIGIKEY_CLIENT_SECRET'],
        # May be empty. The client raises ConfigurationError naming this
        # setting on first use, which is a better message than refusing to
        # build here and reporting the whole integration as absent.
        account_id=config.get('DIGIKEY_ACCOUNT_ID') or '',
        base_url=config.get('DIGIKEY_API_BASE') or 'https://api.digikey.com',
    )


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
    #
    # The port is trusted for the same reason and was learned the harder way
    # (issue #114). x_host=1 believes an X-Forwarded-Host that carries no port,
    # overwriting an HTTP_HOST that did, so on a non-default port the app ends
    # up believing it lives where the browser never was. The bookmarklet was
    # the visible symptom -- addresses on 443, where nothing listens. The
    # disabling one was that every CSRF-protected form over https was refused
    # with "The referrer does not match the host", because that check compares
    # the referrer against request.host. Reads were unaffected, which is why
    # the deployment looked healthy until someone tried to save something.
    #
    # The guard wraps ProxyFix rather than the other way round: it has to
    # clear the header before ProxyFix reads it.
    app.wsgi_app = _drop_malformed_forwarded_port(
        ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    )

    # Store the storage backend in app config for access by routes
    if storage_backend:
        app.config['STORAGE_BACKEND'] = storage_backend

    # DigiKey client, in the same shape as the storage backend above so that a
    # test can inject a fake by setting app.config['DIGIKEY_CLIENT'].
    #
    # None means "not configured", and that is an ordinary state: the DigiKey
    # screens say so and every other part of the application is unaffected
    # (024 FR-036, FR-037). Building it here rather than per request keeps one
    # cached access token for the process instead of one per page view.
    app.config['DIGIKEY_CLIENT'] = _build_digikey_client(app.config)


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