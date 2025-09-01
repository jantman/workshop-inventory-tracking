"""
Test Configuration

Configuration class specifically for testing scenarios.
"""

import os
import tempfile
from config import Config


class TestConfig(Config):
    """Configuration for testing"""
    
    # Override settings for testing
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False  # Disable CSRF for easier testing
    
    # Use different secret key for testing
    SECRET_KEY = 'test-secret-key-not-for-production'
    
    # Disable Google Sheets requirements for testing
    GOOGLE_SHEET_ID = 'test-sheet-id'
    
    # Use temporary files for credentials (will be mocked anyway)
    GOOGLE_CREDENTIALS_FILE = os.path.join(tempfile.gettempdir(), 'test_credentials.json')
    GOOGLE_TOKEN_FILE = os.path.join(tempfile.gettempdir(), 'test_token.json')
    
    # Disable logging to files during tests
    LOG_LEVEL = 'WARNING'
    
    @staticmethod
    def validate_config():
        """Override validation for testing - don't require real Google credentials"""
        return []  # No validation errors for testing