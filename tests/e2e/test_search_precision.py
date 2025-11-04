"""
E2E Tests for Search Precision Filter

Tests to verify that the Precision field filter works correctly on the search form.
This test should initially FAIL due to a bug where the precision filter is not working.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_by_precision_true_workflow(page, live_server):
    """Test searching for precision items only"""
    # Add test data with mixed precision values
    test_items = [
        {
            "ja_id": "JA020001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Precision item",
            "precision": True
        },
        {
            "ja_id": "JA020002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Non-precision item",
            "precision": False
        },
        {
            "ja_id": "JA020003",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "400",
            "width": "200",
            "thickness": "2",
            "location": "Storage C",
            "notes": "Another precision item",
            "precision": True
        },
        {
            "ja_id": "JA020004",
            "item_type": "Bar",
            "shape": "Square",
            "material": "Brass",
            "length": "200",
            "width": "8",
            "location": "Storage D",
            "notes": "Another non-precision item",
            "precision": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Verify search form is visible
    search_page.assert_search_form_visible()

    # Search for precision items only
    search_page.search_by_precision("true")

    # Verify results - should find only 2 precision items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA020001")
    search_page.assert_result_contains_item("JA020003")


@pytest.mark.e2e
def test_search_by_precision_false_workflow(page, live_server):
    """Test searching for non-precision items only"""
    # Add test data with mixed precision values
    test_items = [
        {
            "ja_id": "JA021001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Precision item",
            "precision": True
        },
        {
            "ja_id": "JA021002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Non-precision item",
            "precision": False
        },
        {
            "ja_id": "JA021003",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "400",
            "width": "200",
            "thickness": "2",
            "location": "Storage C",
            "notes": "Another non-precision item",
            "precision": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for non-precision items only
    search_page.search_by_precision("false")

    # Verify results - should find only 2 non-precision items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA021002")
    search_page.assert_result_contains_item("JA021003")


@pytest.mark.e2e
def test_search_by_precision_all_items_workflow(page, live_server):
    """Test searching for all items (no precision filter)"""
    # Add test data with mixed precision values
    test_items = [
        {
            "ja_id": "JA022001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Precision item",
            "precision": True
        },
        {
            "ja_id": "JA022002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Non-precision item",
            "precision": False
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search with no precision filter (empty value = all items)
    search_page.search_by_precision("")

    # Verify results - should find all items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA022001")
    search_page.assert_result_contains_item("JA022002")
