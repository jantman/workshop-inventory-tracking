"""
Basic unit tests to validate testing infrastructure.

Simple tests to ensure our testing framework is working correctly.
"""

import pytest
from app.test_storage import InMemoryStorage
from app.storage import StorageResult


class TestBasicInfrastructure:
    """Basic tests to validate testing infrastructure"""
    
    @pytest.mark.unit 
    def test_basic_pytest(self):
        """Test that pytest is working"""
        assert True
        assert 1 + 1 == 2
    
    @pytest.mark.unit
    def test_test_storage_basic(self):
        """Test that InMemoryStorage basic functionality works"""
        storage = InMemoryStorage()
        result = storage.connect()
        
        assert result.success
        assert storage.connection is not None
        
        storage.close()
    
    @pytest.mark.unit
    def test_storage_create_and_read(self):
        """Test basic storage operations"""
        storage = InMemoryStorage()
        storage.connect()
        
        # Create sheet
        result = storage.create_sheet('TestSheet', ['Name', 'Value'])
        assert result.success
        
        # Write data
        result = storage.write_row('TestSheet', ['Test', '123'])
        assert result.success
        
        # Read data
        result = storage.read_all('TestSheet')
        assert result.success
        assert len(result.data) == 2  # Headers + 1 data row
        assert result.data[0] == ['Name', 'Value']  # Headers
        assert result.data[1] == ['Test', '123']  # Data row
        
        storage.close()
    
    @pytest.mark.unit
    def test_flask_app_creation(self, app):
        """Test that Flask app can be created with test configuration"""
        assert app is not None
        assert app.config['TESTING'] is True
    
    @pytest.mark.unit
    def test_flask_client(self, client):
        """Test that Flask test client works"""
        response = client.get('/health')
        assert response.status_code == 200