from flask import Flask
from flask_wtf.csrf import CSRFProtect
from config import Config
from app.logging_config import setup_logging

csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Setup CSRF protection
    csrf.init_app(app)
    
    # Setup logging
    setup_logging(app)
    
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)
    
    return app