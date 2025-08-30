import logging
import logging.handlers
import os
from datetime import datetime

def setup_logging(app):
    """Configure logging for the application"""
    
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configure root logger
    log_level = getattr(logging, app.config.get('LOG_LEVEL', 'INFO').upper())
    
    # File handler for application logs
    file_handler = logging.handlers.RotatingFileHandler(
        'logs/workshop_inventory.log',
        maxBytes=10240000,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(log_level)
    
    # Console handler for development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(levelname)s: %(message)s'
    ))
    console_handler.setLevel(log_level)
    
    # Configure Flask app logger
    app.logger.handlers.clear()  # Clear default handlers
    app.logger.addHandler(file_handler)
    
    if app.debug:
        app.logger.addHandler(console_handler)
    
    app.logger.setLevel(log_level)
    
    # Log startup information
    app.logger.info(f'Workshop Inventory Tracking started - Debug: {app.debug}')
    
    # Configure werkzeug logger to reduce noise in development
    if app.debug:
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    return app.logger