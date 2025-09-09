"""
Pytest configuration and shared fixtures.

This file contains fixtures that are available to all test modules.
"""

import pytest
import tempfile
import os
from flask import Flask
from app import create_app
from app.test_storage import InMemoryStorage
from app.models import Item, ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
from tests.test_config import TestConfig
from decimal import Decimal

# E2E Testing imports
from tests.e2e.test_server import get_test_server
from tests.e2e.debug_utils import E2EDebugCapture, create_debug_summary


@pytest.fixture
def test_storage():
    """Create a fresh InMemoryStorage instance for each test"""
    storage = InMemoryStorage()
    storage.connect()
    
    # Create basic inventory sheet structure matching InventoryService format
    from app.inventory_service import InventoryService
    headers = InventoryService.SHEET_HEADERS
    storage.create_sheet('Metal', headers)
    
    yield storage
    
    # Cleanup
    storage.close()


@pytest.fixture
def app(test_storage):
    """Create Flask application with test storage backend"""
    app = create_app(TestConfig, storage_backend=test_storage)
    
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    """Create Flask test client"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create Flask CLI runner"""
    return app.test_cli_runner()


# Test Data Factories

@pytest.fixture
def sample_item_data():
    """Sample item data for testing"""
    return {
        'ja_id': 'JA000001',
        'item_type': ItemType.BAR,
        'shape': ItemShape.ROUND,
        'material': 'Steel',
        'dimensions': Dimensions(
            length=Decimal('1000'),
            width=Decimal('25')
        ),
        'location': 'Test Location',
        'notes': 'Test item',
        'active': True
    }


@pytest.fixture
def sample_threaded_item_data():
    """Sample threaded item data for testing"""
    return {
        'ja_id': 'JA000002', 
        'item_type': ItemType.THREADED_ROD,
        'shape': ItemShape.ROUND,
        'material': 'Stainless Steel',
        'dimensions': Dimensions(
            length=Decimal('500'),
            width=Decimal('12')
        ),
        'thread': Thread(
            series=ThreadSeries.METRIC,
            handedness=ThreadHandedness.RIGHT,
            size="M12x1.75"
        ),
        'location': 'Storage Rack A',
        'notes': 'M12x1.75 threaded rod',
        'active': True
    }


@pytest.fixture
def sample_item(sample_item_data):
    """Create a sample Item object"""
    return Item(**sample_item_data)


@pytest.fixture
def sample_threaded_item(sample_threaded_item_data):
    """Create a sample threaded Item object"""
    return Item(**sample_threaded_item_data)


@pytest.fixture
def populated_storage(test_storage, sample_item_data, sample_threaded_item_data):
    """Create storage with sample data pre-populated"""
    # Add sample items using InventoryService for proper formatting
    from app.inventory_service import InventoryService
    
    service = InventoryService(test_storage)
    item1 = Item(**sample_item_data)
    item2 = Item(**sample_threaded_item_data)
    
    service.add_item(item1)
    service.add_item(item2)
    
    return test_storage


# E2E Testing Fixtures

@pytest.fixture(scope="session")
def e2e_server():
    """Session-scoped test server for E2E tests"""
    server = get_test_server()
    server.start()
    
    yield server
    
    server.stop()


@pytest.fixture
def live_server(e2e_server):
    """Live server fixture that clears data between tests"""
    e2e_server.clear_test_data()
    yield e2e_server


@pytest.fixture
def browser_context_args(browser_context_args):
    """Configure browser context for tests"""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Configure browser launch args"""
    return {
        **browser_type_launch_args,
        "headless": True,  # Change to False to see browser during development
    }


# Markers for test categorization
pytest_plugins = []


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
    config.addinivalue_line(
        "markers", "e2e: marks tests as end-to-end tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )


# Global storage for debug capture (keyed by node id)
_debug_captures = {}

@pytest.fixture
def page(page, request):
    """Enhanced page fixture with debug capture for E2E tests"""
    # Only set up debug capture for E2E tests
    if any(mark.name == "e2e" for mark in request.node.iter_markers()):
        # Set up debug capture
        test_name = request.node.name
        debug_capture = E2EDebugCapture(test_name)
        debug_capture.setup_page_monitoring(page)
        
        # Store debug capture globally (keyed by node id)
        _debug_captures[request.node.nodeid] = {
            'debug_capture': debug_capture,
            'page': page
        }
    
    yield page
    
    # Clean up debug capture after test
    if request.node.nodeid in _debug_captures:
        del _debug_captures[request.node.nodeid]


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Hook to capture test results for debug capture"""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
    
    # Capture debug info on test failure
    if rep.when == "call" and rep.failed and any(mark.name == "e2e" for mark in item.iter_markers()):
        print(f"\n🔍 Test failed, capturing debug information...")
        
        # Get debug capture from global storage
        try:
            node_id = item.nodeid
            if node_id in _debug_captures:
                capture_info = _debug_captures[node_id]
                debug_capture = capture_info['debug_capture']
                page = capture_info['page']
                
                debug_dir = debug_capture.capture_failure_state(page, f"Test failed: {str(rep.longrepr)}")
                if debug_dir:
                    print(f"📁 Debug information saved to: {debug_dir}")
                    # Create summary
                    create_debug_summary(debug_capture.test_dir)
                else:
                    print(f"⚠️ Debug capture failed - no directory created")
            else:
                print(f"⚠️ Debug capture not available - test not found in global storage")
        except Exception as e:
            print(f"⚠️ Error during debug capture: {e}")
            import traceback
            traceback.print_exc()