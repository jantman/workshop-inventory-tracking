from flask import Flask
from config import Config
import logging
import os
from app.logging_config import JSONFormatter

def create_app(config_class=Config, storage_backend=None):
    """
    Create Flask application factory with optional storage backend injection.
    
    Args:
        config_class: Configuration class to use (defaults to Config)
        storage_backend: Optional storage backend instance for testing
    """
    app = Flask(__name__, template_folder='app/templates', static_folder='app/static')
    app.config.from_object(config_class)
    
    # Store the storage backend in app config for access by routes
    if storage_backend:
        app.config['STORAGE_BACKEND'] = storage_backend
    else:
        # Create storage backend using factory
        from app.storage_factory import get_storage_backend, get_test_storage_backend
        
        if app.config.get('TESTING'):
            app.config['STORAGE_BACKEND'] = get_test_storage_backend()
        else:
            app.config['STORAGE_BACKEND'] = get_storage_backend()
    
    # Configure logging
    if app.debug:
        app.logger.setLevel(logging.DEBUG)

    # Register blueprints
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=5000)
