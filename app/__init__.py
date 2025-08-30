from flask import Flask
from config import Config
from app.logging_config import setup_logging

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Setup logging
    setup_logging(app)
    
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    return app