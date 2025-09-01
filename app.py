from flask import Flask
from config import Config
import logging
import os

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
    
    # Configure logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = logging.FileHandler('logs/workshop_inventory.log')
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('Workshop Inventory startup')
    
    # Register blueprints
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=5000)