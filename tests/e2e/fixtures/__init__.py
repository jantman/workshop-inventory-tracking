"""
Test Fixtures for Screenshot Generation

This package contains realistic test data and helper utilities for
generating documentation screenshots.
"""

from .screenshot_data import (
    get_inventory_items,
    get_items_with_photos,
    get_history_items,
    get_search_examples,
    get_batch_operation_examples,
    get_locations,
    get_vendors,
    get_materials,
    SCREENSHOT_INVENTORY_DATA,
    SCREENSHOT_PHOTO_ITEMS,
)

__all__ = [
    'get_inventory_items',
    'get_items_with_photos',
    'get_history_items',
    'get_search_examples',
    'get_batch_operation_examples',
    'get_locations',
    'get_vendors',
    'get_materials',
    'SCREENSHOT_INVENTORY_DATA',
    'SCREENSHOT_PHOTO_ITEMS',
]
