"""
E2E Tests for Search Active/Inactive Status Filter

Tests to verify that the Active/Inactive status filter works correctly on the search form.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_active_only_workflow(page, live_server):
    """Test searching for active items only (default behavior)"""
    # Add test data with mixed active/inactive items
    test_items = [
        {
            "ja_id": "JA040001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Active item 1",
            "active": True
        },
        {
            "ja_id": "JA040002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Inactive item 1",
            "active": False
        },
        {
            "ja_id": "JA040003",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "400",
            "width": "200",
            "thickness": "2",
            "location": "Storage C",
            "notes": "Active item 2",
            "active": True
        },
        {
            "ja_id": "JA040004",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Brass",
            "length": "200",
            "width": "150",
            "thickness": "5",
            "location": "Storage D",
            "notes": "Inactive item 2",
            "active": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Verify search form is visible
    search_page.assert_search_form_visible()

    # Search for active items only (default filter is "Active Only")
    search_page.search_by_active_status("true")

    # Verify results - should find only 2 active items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA040001")
    search_page.assert_result_contains_item("JA040003")


@pytest.mark.e2e
def test_search_inactive_only_workflow(page, live_server):
    """Test searching for inactive items only"""
    # Add test data with mixed active/inactive items
    test_items = [
        {
            "ja_id": "JA041001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Active item",
            "active": True
        },
        {
            "ja_id": "JA041002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Inactive item 1",
            "active": False
        },
        {
            "ja_id": "JA041003",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Stainless Steel",
            "length": "400",
            "width": "200",
            "thickness": "2",
            "location": "Storage C",
            "notes": "Inactive item 2",
            "active": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for inactive items only
    search_page.search_by_active_status("false")

    # Verify results - should find only 2 inactive items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA041002")
    search_page.assert_result_contains_item("JA041003")


@pytest.mark.e2e
def test_search_all_items_regardless_of_status_workflow(page, live_server):
    """Test searching for all items regardless of active/inactive status"""
    # Add test data with mixed active/inactive items
    test_items = [
        {
            "ja_id": "JA042001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Active item",
            "active": True
        },
        {
            "ja_id": "JA042002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Inactive item",
            "active": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for all items (empty value = all items)
    search_page.search_by_active_status("")

    # Verify results - should find all 2 items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA042001")
    search_page.assert_result_contains_item("JA042002")
