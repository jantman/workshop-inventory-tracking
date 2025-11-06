"""
E2E Tests for Search Wall Thickness Range Filter

Tests to verify that the Wall Thickness range filter works correctly on the search form.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_by_wall_thickness_min_workflow(page, live_server):
    """Test searching for items with minimum wall thickness"""
    # Add test data with different wall thickness values (typically for tubes/pipes)
    test_items = [
        {
            "ja_id": "JA060001",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "25",
            "wall_thickness": "1.5",
            "location": "Storage A",
            "notes": "Thin wall tube"
        },
        {
            "ja_id": "JA060002",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Aluminum",
            "length": "400",
            "width": "30",
            "wall_thickness": "2.0",
            "location": "Storage B",
            "notes": "Medium wall tube"
        },
        {
            "ja_id": "JA060003",
            "item_type": "Tube",
            "shape": "Square",
            "material": "Stainless Steel",
            "length": "200",
            "width": "50",
            "wall_thickness": "3.0",
            "location": "Storage C",
            "notes": "Thick wall tube"
        },
        {
            "ja_id": "JA060004",
            "item_type": "Tube",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "250",
            "width": "40",
            "wall_thickness": "5.0",
            "location": "Storage D",
            "notes": "Very thick wall tube"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Verify search form is visible
    search_page.assert_search_form_visible()

    # Search for items with wall_thickness >= 2.0
    search_page.search_by_wall_thickness_range(wall_thickness_min="2.0")

    # Verify results - should find only 3 items (2.0, 3.0, 5.0) excluding the 1.5 item
    search_page.assert_results_found(3)
    search_page.assert_result_contains_item("JA060002")
    search_page.assert_result_contains_item("JA060003")
    search_page.assert_result_contains_item("JA060004")


@pytest.mark.e2e
def test_search_by_wall_thickness_max_workflow(page, live_server):
    """Test searching for items with maximum wall thickness"""
    # Add test data with different wall thickness values
    test_items = [
        {
            "ja_id": "JA061001",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "25",
            "wall_thickness": "1.5",
            "location": "Storage A",
            "notes": "Thin wall tube"
        },
        {
            "ja_id": "JA061002",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Aluminum",
            "length": "400",
            "width": "30",
            "wall_thickness": "2.0",
            "location": "Storage B",
            "notes": "Medium wall tube"
        },
        {
            "ja_id": "JA061003",
            "item_type": "Tube",
            "shape": "Square",
            "material": "Stainless Steel",
            "length": "200",
            "width": "50",
            "wall_thickness": "3.0",
            "location": "Storage C",
            "notes": "Thick wall tube"
        },
        {
            "ja_id": "JA061004",
            "item_type": "Tube",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "250",
            "width": "40",
            "wall_thickness": "5.0",
            "location": "Storage D",
            "notes": "Very thick wall tube"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for items with wall_thickness <= 2.0
    search_page.search_by_wall_thickness_range(wall_thickness_max="2.0")

    # Verify results - should find only 2 items (1.5, 2.0) excluding thicker items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA061001")
    search_page.assert_result_contains_item("JA061002")


@pytest.mark.e2e
def test_search_by_wall_thickness_range_workflow(page, live_server):
    """Test searching for items within a wall thickness range"""
    # Add test data with different wall thickness values
    test_items = [
        {
            "ja_id": "JA062001",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "25",
            "wall_thickness": "1.5",
            "location": "Storage A",
            "notes": "Too thin - below range"
        },
        {
            "ja_id": "JA062002",
            "item_type": "Tube",
            "shape": "Round",
            "material": "Aluminum",
            "length": "400",
            "width": "30",
            "wall_thickness": "2.0",
            "location": "Storage B",
            "notes": "In range - lower bound"
        },
        {
            "ja_id": "JA062003",
            "item_type": "Tube",
            "shape": "Square",
            "material": "Stainless Steel",
            "length": "200",
            "width": "50",
            "wall_thickness": "3.0",
            "location": "Storage C",
            "notes": "In range - upper bound"
        },
        {
            "ja_id": "JA062004",
            "item_type": "Tube",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "250",
            "width": "40",
            "wall_thickness": "5.0",
            "location": "Storage D",
            "notes": "Too thick - above range"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for items with wall_thickness between 2.0 and 3.0 (inclusive)
    search_page.search_by_wall_thickness_range(wall_thickness_min="2.0", wall_thickness_max="3.0")

    # Verify results - should find only 2 items (2.0 and 3.0)
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA062002")
    search_page.assert_result_contains_item("JA062003")
