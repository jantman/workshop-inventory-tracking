"""
E2E Infrastructure Validation Tests

Tests to validate E2E test infrastructure without requiring browser dependencies.
"""

import pytest
import requests
from tests.e2e.test_server import TestServer


@pytest.mark.e2e
def test_test_server_starts_and_stops():
    """Test that the test server can start and stop properly"""
    server = TestServer()
    
    # Start server
    server.start()
    
    # Verify server is running
    response = requests.get(f"{server.url}/health")
    assert response.status_code == 200
    
    # Stop server
    server.stop()


@pytest.mark.e2e
def test_test_server_context_manager():
    """Test test server as context manager"""
    with TestServer() as server:
        # Verify server is running
        response = requests.get(f"{server.url}/health")
        assert response.status_code == 200
        
        # Verify we can add test data
        test_data = [{
            "ja_id": "TEST001",
            "item_type": "Rod", 
            "shape": "Round",
            "material": "Steel",
            "location": "Test Location"
        }]
        server.add_test_data(test_data)
        
        # Verify data was added by checking storage
        result = server.storage.read_all('Inventory')
        assert result.success
        assert len(result.data) == 1


@pytest.mark.e2e
def test_test_server_with_live_server_fixture(live_server):
    """Test using the live_server fixture"""
    # Verify server is accessible
    response = requests.get(f"{live_server.url}/health")
    assert response.status_code == 200
    
    # Test adding data through fixture
    test_data = [{
        "ja_id": "FIXTURE001",
        "item_type": "Tube",
        "shape": "Round", 
        "material": "Aluminum",
        "location": "Fixture Test"
    }]
    live_server.add_test_data(test_data)
    
    # Verify data exists
    result = live_server.storage.read_all('Inventory')
    assert result.success
    assert len(result.data) == 1
    assert result.data[0][0] == "FIXTURE001"


@pytest.mark.e2e
def test_inventory_routes_accessible(live_server):
    """Test that key inventory routes are accessible"""
    base_url = live_server.url
    
    # Test main routes
    routes_to_test = [
        "/",
        "/inventory",
        "/inventory/add",
        "/inventory/search"
    ]
    
    for route in routes_to_test:
        response = requests.get(f"{base_url}{route}")
        # Should get 200 OK or redirect (3xx), not 404 or 500
        assert response.status_code < 400, f"Route {route} returned {response.status_code}"