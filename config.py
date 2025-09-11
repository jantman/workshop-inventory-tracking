import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database Configuration
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_USER = os.environ.get('DB_USER', 'inventory_user')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'workshop_inventory')
    
    # Database connection string for SQLAlchemy
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_timeout': 20,
        'pool_recycle': -1,
        'pool_pre_ping': True,
    }
    
    # Google Sheets API Configuration (legacy, for export functionality)
    GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE') or os.path.join(basedir, 'credentials', 'credentials.json')
    GOOGLE_TOKEN_FILE = os.environ.get('GOOGLE_TOKEN_FILE') or os.path.join(basedir, 'credentials', 'token.json')
    GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    
    # Application Configuration
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 'yes']
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    
    @staticmethod
    def validate_config():
        """Validate that required configuration is present"""
        errors = []
        
        # Database configuration validation
        if not Config.DB_PASSWORD:
            errors.append("DB_PASSWORD environment variable is required")
        
        # Google Sheets configuration (for export functionality only)
        if Config.GOOGLE_SHEET_ID and not os.path.exists(Config.GOOGLE_CREDENTIALS_FILE):
            errors.append(f"Google credentials file not found: {Config.GOOGLE_CREDENTIALS_FILE}")
        
        return errors