import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database connection string for SQLAlchemy - use directly from .env file
    SQLALCHEMY_DATABASE_URI = os.environ.get('SQLALCHEMY_DATABASE_URI')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_timeout': 20,
        'pool_recycle': -1,
        'pool_pre_ping': True,
    }
    
    # Google Sheets API Configuration (for migration and export functionality)
    GOOGLE_CREDENTIALS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE') or os.path.join(basedir, 'credentials', 'credentials.json')
    GOOGLE_TOKEN_FILE = os.environ.get('GOOGLE_TOKEN_FILE') or os.path.join(basedir, 'credentials', 'token.json')
    GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')
    
    # Application Configuration
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 'yes']
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')


class TestConfig(Config):
    """Test configuration using MariaDB test database"""
    TESTING = True
    
    # Test database configuration
    DB_HOST = os.environ.get('TEST_DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('TEST_DB_PORT', 3307))  # Different port for test container
    DB_USER = os.environ.get('TEST_DB_USER', 'inventory_test_user')
    DB_PASSWORD = os.environ.get('TEST_DB_PASSWORD', 'test_password')
    DB_NAME = os.environ.get('TEST_DB_NAME', 'workshop_inventory_test')
    
    # Override database URI for testing
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    
    # Test-specific engine options
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'pool_timeout': 10,
        'pool_recycle': -1,
        'pool_pre_ping': True,
    }
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False
    
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
        if not Config.SQLALCHEMY_DATABASE_URI:
            errors.append("SQLALCHEMY_DATABASE_URI environment variable is required")
        
        # Google Sheets configuration (for migration and export functionality)
        if Config.GOOGLE_SHEET_ID and not os.path.exists(Config.GOOGLE_CREDENTIALS_FILE):
            errors.append(f"Google credentials file not found: {Config.GOOGLE_CREDENTIALS_FILE}")
        
        return errors