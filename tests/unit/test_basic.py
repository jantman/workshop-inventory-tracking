"""
Basic unit tests to validate testing infrastructure.

Simple tests to ensure our testing framework is working correctly.
"""

import pytest
from app import __version__
from app.mariadb_storage import MariaDBStorage
from app.storage import StorageResult


class TestBasicInfrastructure:
    """Basic tests to validate testing infrastructure"""
    
    @pytest.mark.unit 
    def test_basic_pytest(self):
        """Test that pytest is working"""
        assert True
        assert 1 + 1 == 2
    
    @pytest.mark.unit
    def test_test_storage_basic(self, test_storage):
        """Test that MariaDB storage basic functionality works"""
        assert test_storage is not None
        # Connection is already established by the fixture
    
    @pytest.mark.unit
    def test_storage_read_materials(self, test_storage):
        """Test reading Materials taxonomy data"""
        # Read Materials sheet which should exist with taxonomy data
        result = test_storage.read_all('Materials')
        assert result.success
        assert len(result.data) > 0  # Should have headers plus taxonomy data
    
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

    @pytest.mark.unit
    def test_health_reports_version(self, client):
        """Health endpoint reports the version, so deployments are identifiable"""
        response = client.get('/health')
        assert response.json['version'] == __version__

    @pytest.mark.unit
    def test_version_is_semver(self):
        """Version from pyproject.toml is a SemVer MAJOR.MINOR.PATCH string"""
        major, minor, patch = __version__.split('.')
        assert all(part.isdigit() for part in (major, minor, patch))

    @pytest.mark.unit
    def test_templates_render_version(self, client):
        """Version is injected into templates and rendered in the footer"""
        response = client.get('/')
        assert response.status_code == 200
        assert f'v{__version__}' in response.get_data(as_text=True)
