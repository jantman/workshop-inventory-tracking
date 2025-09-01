"""
Pytest configuration and shared fixtures.

This file contains fixtures that are available to all test modules.
"""

import pytest
import tempfile
import os
from flask import Flask
from app import create_app
from app.test_storage import TestStorage
from app.models import Item, ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
from tests.test_config import TestConfig
from decimal import Decimal


@pytest.fixture
def test_storage():
    """Create a fresh TestStorage instance for each test"""
    storage = TestStorage()
    storage.connect()
    
    # Create basic inventory sheet structure matching Google Sheets format
    headers = [
        'JA_ID', 'Item_Type', 'Shape', 'Material', 'Length_mm', 'Width_mm', 
        'Height_mm', 'Diameter_mm', 'Thread_Series', 'Thread_Handedness', 
        'Thread_Length_mm', 'Location', 'Notes', 'Parent_JA_ID', 'Active'
    ]
    storage.create_sheet('Inventory', headers)
    
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
        'ja_id': 'TEST001',
        'item_type': ItemType.ROD,
        'shape': ItemShape.ROUND,
        'material': 'Steel',
        'dimensions': Dimensions(
            length_mm=Decimal('1000'),
            diameter_mm=Decimal('25')
        ),
        'location': 'Test Location',
        'notes': 'Test item',
        'active': True
    }


@pytest.fixture
def sample_threaded_item_data():
    """Sample threaded item data for testing"""
    return {
        'ja_id': 'TEST002', 
        'item_type': ItemType.THREADED_ROD,
        'shape': ItemShape.ROUND,
        'material': 'Stainless Steel',
        'dimensions': Dimensions(
            length_mm=Decimal('500'),
            diameter_mm=Decimal('12')
        ),
        'thread': Thread(
            series=ThreadSeries.METRIC_COARSE,
            handedness=ThreadHandedness.RIGHT_HAND,
            length_mm=Decimal('500')
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
    # Add sample items to storage
    item1 = Item(**sample_item_data)
    item2 = Item(**sample_threaded_item_data)
    
    # Convert to storage format (list of values)
    row1 = [
        item1.ja_id, item1.item_type.value, item1.shape.value, item1.material,
        str(item1.dimensions.length_mm) if item1.dimensions.length_mm else '',
        str(item1.dimensions.width_mm) if item1.dimensions.width_mm else '',
        str(item1.dimensions.height_mm) if item1.dimensions.height_mm else '',
        str(item1.dimensions.diameter_mm) if item1.dimensions.diameter_mm else '',
        '', '', '',  # Thread fields
        item1.location, item1.notes, item1.parent_ja_id or '', str(item1.active)
    ]
    
    row2 = [
        item2.ja_id, item2.item_type.value, item2.shape.value, item2.material,
        str(item2.dimensions.length_mm) if item2.dimensions.length_mm else '',
        str(item2.dimensions.width_mm) if item2.dimensions.width_mm else '',
        str(item2.dimensions.height_mm) if item2.dimensions.height_mm else '',
        str(item2.dimensions.diameter_mm) if item2.dimensions.diameter_mm else '',
        item2.thread.series.value if item2.thread else '',
        item2.thread.handedness.value if item2.thread else '',
        str(item2.thread.length_mm) if item2.thread and item2.thread.length_mm else '',
        item2.location, item2.notes, item2.parent_ja_id or '', str(item2.active)
    ]
    
    test_storage.write_rows('Inventory', [row1, row2])
    
    return test_storage


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