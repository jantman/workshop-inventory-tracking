from flask import Flask
from flask_wtf.csrf import CSRFProtect
from config import Config
from app.logging_config import setup_logging
from app.error_handlers import create_error_handlers

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
    
    # Setup CSRF protection
    csrf.init_app(app)
    
    # Setup logging
    setup_logging(app)
    
    # Setup error handlers
    create_error_handlers(app)
    
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    return app