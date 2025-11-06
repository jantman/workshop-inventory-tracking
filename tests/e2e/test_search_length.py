"""
E2E Tests for Search Length Range Filter

Tests to verify that the Length range filter works correctly on the search form.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_by_length_min_workflow(page, live_server):
    """Test searching for items with minimum length"""
    # Add test data with different length values
    test_items = [
        {
            "ja_id": "JA050001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "100",
            "width": "12",
            "location": "Storage A",
            "notes": "Short bar"
        },
        {
            "ja_id": "JA050002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "200",
            "width": "10",
            "location": "Storage B",
            "notes": "Medium bar"
        },
        {
            "ja_id": "JA050003",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Brass",
            "length": "300",
            "width": "8",
            "location": "Storage C",
            "notes": "Long bar"
        },
        {
            "ja_id": "JA050004",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Stainless Steel",
            "length": "400",
            "width": "15",
            "location": "Storage D",
            "notes": "Very long bar"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Verify search form is visible
    search_page.assert_search_form_visible()

    # Search for items with length >= 200
    search_page.search_by_length_range(length_min="200")

    # Verify results - should find only 3 items (200, 300, 400) excluding the 100 item
    search_page.assert_results_found(3)
    search_page.assert_result_contains_item("JA050002")
    search_page.assert_result_contains_item("JA050003")
    search_page.assert_result_contains_item("JA050004")


@pytest.mark.e2e
def test_search_by_length_max_workflow(page, live_server):
    """Test searching for items with maximum length"""
    # Add test data with different length values
    test_items = [
        {
            "ja_id": "JA051001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "100",
            "width": "12",
            "location": "Storage A",
            "notes": "Short bar"
        },
        {
            "ja_id": "JA051002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "200",
            "width": "10",
            "location": "Storage B",
            "notes": "Medium bar"
        },
        {
            "ja_id": "JA051003",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Brass",
            "length": "300",
            "width": "8",
            "location": "Storage C",
            "notes": "Long bar"
        },
        {
            "ja_id": "JA051004",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Stainless Steel",
            "length": "400",
            "width": "15",
            "location": "Storage D",
            "notes": "Very long bar"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for items with length <= 200
    search_page.search_by_length_range(length_max="200")

    # Verify results - should find only 2 items (100, 200) excluding longer items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA051001")
    search_page.assert_result_contains_item("JA051002")


@pytest.mark.e2e
def test_search_by_length_range_workflow(page, live_server):
    """Test searching for items within a length range"""
    # Add test data with different length values
    test_items = [
        {
            "ja_id": "JA052001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "100",
            "width": "12",
            "location": "Storage A",
            "notes": "Too short - below range"
        },
        {
            "ja_id": "JA052002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "200",
            "width": "10",
            "location": "Storage B",
            "notes": "In range - lower bound"
        },
        {
            "ja_id": "JA052003",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Brass",
            "length": "300",
            "width": "8",
            "location": "Storage C",
            "notes": "In range - upper bound"
        },
        {
            "ja_id": "JA052004",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Stainless Steel",
            "length": "400",
            "width": "15",
            "location": "Storage D",
            "notes": "Too long - above range"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for items with length between 200 and 300 (inclusive)
    search_page.search_by_length_range(length_min="200", length_max="300")

    # Verify results - should find only 2 items (200 and 300)
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA052002")
    search_page.assert_result_contains_item("JA052003")
