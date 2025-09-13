"""
Storage Factory

Creates appropriate storage backend instances based on configuration.
Supports both Google Sheets (legacy) and MariaDB (new) backends.
"""

import os
import logging
from typing import Optional

from .storage import Storage
from .mariadb_storage import MariaDBStorage
from config import Config


logger = logging.getLogger(__name__)


class StorageFactory:
    """Factory for creating storage backend instances"""
    
    @staticmethod
    def create_storage(backend_type: Optional[str] = None, **kwargs) -> Storage:
        """
        Create a storage backend instance.
        
        Args:
            backend_type: Type of backend ('mariadb' or 'auto')
            **kwargs: Additional arguments for backend initialization
            
        Returns:
            Storage instance
        """
        if backend_type is None:
            backend_type = os.environ.get('STORAGE_BACKEND', 'auto')
        
        if backend_type == 'mariadb':
            return StorageFactory._create_mariadb_storage(**kwargs)
        elif backend_type == 'auto':
            # Auto-detect based on available configuration
            return StorageFactory._auto_detect_storage(**kwargs)
        else:
            raise ValueError(f"Unknown storage backend type: {backend_type}")
    
    @staticmethod
    def _create_mariadb_storage(**kwargs) -> MariaDBStorage:
        """Create MariaDB storage instance"""
        database_url = kwargs.get('database_url')
        return MariaDBStorage(database_url=database_url)
    
    
    @staticmethod
    def _auto_detect_storage(**kwargs) -> Storage:
        """
        Auto-detect storage backend based on available configuration.
        Always returns MariaDB storage as it's the only supported backend.
        """
        # Check for database configuration
        db_url = os.environ.get('SQLALCHEMY_DATABASE_URI')
        db_password = os.environ.get('DB_PASSWORD')
        
        if db_url or db_password:
            logger.info("Auto-detected MariaDB storage backend")
        else:
            logger.warning("No database configuration detected, defaulting to MariaDB")
        
        return StorageFactory._create_mariadb_storage(**kwargs)


def get_storage_backend() -> Storage:
    """
    Get the default storage backend instance.
    
    This is the main entry point for getting a storage backend in the application.
    """
    return StorageFactory.create_storage()


def get_test_storage_backend() -> Storage:
    """
    Get storage backend configured for testing.
    """
    if os.environ.get('USE_TEST_MARIADB') == '1':
        # Use MariaDB test configuration
        from config import TestConfig
        return MariaDBStorage(database_url=TestConfig.SQLALCHEMY_DATABASE_URI)
    else:
        # Use in-memory SQLite for unit tests
        return MariaDBStorage(database_url='sqlite:///:memory:')