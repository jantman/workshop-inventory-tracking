"""
E2E Tests for Search Thickness Range Filter

Tests to verify that the Thickness range filter works correctly on the search form.
This test should initially FAIL due to a bug where the thickness filter is not working.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_by_thickness_min_workflow(page, live_server):
    """Test searching for items with minimum thickness"""
    # Add test data with different thickness values
    test_items = [
        {
            "ja_id": "JA030001",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "300",
            "width": "200",
            "thickness": "0.125",  # 1/8 inch
            "location": "Storage A",
            "notes": "Thin sheet"
        },
        {
            "ja_id": "JA030002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "400",
            "width": "300",
            "thickness": "0.25",  # 1/4 inch
            "location": "Storage B",
            "notes": "Medium sheet"
        },
        {
            "ja_id": "JA030003",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "200",
            "width": "150",
            "thickness": "0.5",  # 1/2 inch
            "location": "Storage C",
            "notes": "Thick plate"
        },
        {
            "ja_id": "JA030004",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Stainless Steel",
            "length": "250",
            "width": "175",
            "thickness": "1.0",  # 1 inch
            "location": "Storage D",
            "notes": "Very thick plate"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Verify search form is visible
    search_page.assert_search_form_visible()

    # Search for items with thickness >= 0.25
    search_page.search_by_thickness_range(thickness_min="0.25")

    # Verify results - should find only 3 items (0.25, 0.5, 1.0) excluding the 0.125 item
    search_page.assert_results_found(3)
    search_page.assert_result_contains_item("JA030002")
    search_page.assert_result_contains_item("JA030003")
    search_page.assert_result_contains_item("JA030004")


@pytest.mark.e2e
def test_search_by_thickness_max_workflow(page, live_server):
    """Test searching for items with maximum thickness"""
    # Add test data with different thickness values
    test_items = [
        {
            "ja_id": "JA031001",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "300",
            "width": "200",
            "thickness": "0.125",  # 1/8 inch
            "location": "Storage A",
            "notes": "Thin sheet"
        },
        {
            "ja_id": "JA031002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "400",
            "width": "300",
            "thickness": "0.25",  # 1/4 inch
            "location": "Storage B",
            "notes": "Medium sheet"
        },
        {
            "ja_id": "JA031003",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "200",
            "width": "150",
            "thickness": "0.5",  # 1/2 inch
            "location": "Storage C",
            "notes": "Thick plate"
        },
        {
            "ja_id": "JA031004",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Stainless Steel",
            "length": "250",
            "width": "175",
            "thickness": "1.0",  # 1 inch
            "location": "Storage D",
            "notes": "Very thick plate"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for items with thickness <= 0.25
    search_page.search_by_thickness_range(thickness_max="0.25")

    # Verify results - should find only 2 items (0.125, 0.25) excluding thicker items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA031001")
    search_page.assert_result_contains_item("JA031002")


@pytest.mark.e2e
def test_search_by_thickness_range_workflow(page, live_server):
    """Test searching for items within a thickness range"""
    # Add test data with different thickness values
    test_items = [
        {
            "ja_id": "JA032001",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "300",
            "width": "200",
            "thickness": "0.125",  # 1/8 inch - below range
            "location": "Storage A",
            "notes": "Thin sheet"
        },
        {
            "ja_id": "JA032002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "400",
            "width": "300",
            "thickness": "0.25",  # 1/4 inch - in range
            "location": "Storage B",
            "notes": "Medium sheet"
        },
        {
            "ja_id": "JA032003",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "200",
            "width": "150",
            "thickness": "0.5",  # 1/2 inch - in range
            "location": "Storage C",
            "notes": "Thick plate"
        },
        {
            "ja_id": "JA032004",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Stainless Steel",
            "length": "250",
            "width": "175",
            "thickness": "1.0",  # 1 inch - above range
            "location": "Storage D",
            "notes": "Very thick plate"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for items with thickness between 0.25 and 0.5 (inclusive)
    search_page.search_by_thickness_range(thickness_min="0.25", thickness_max="0.5")

    # Verify results - should find only 2 items (0.25 and 0.5)
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA032002")
    search_page.assert_result_contains_item("JA032003")
