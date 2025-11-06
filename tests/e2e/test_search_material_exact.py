"""
E2E Tests for Search Material Exact Match Filter

Tests to verify that the Material Exact Match filter works correctly on the search form.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_material_contains_workflow(page, live_server):
    """Test searching for materials with contains matching (default)"""
    # Add test data with similar material names
    test_items = [
        {
            "ja_id": "JA070001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "4140 Pre-Hard",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Specific steel grade"
        },
        {
            "ja_id": "JA070002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "4140",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Generic 4140"
        },
        {
            "ja_id": "JA070003",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "400",
            "width": "15",
            "location": "Storage C",
            "notes": "Different material"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Verify search form is visible
    search_page.assert_search_form_visible()

    # Search for material containing "4140" (default is contains match)
    search_page.search_by_material_with_match_type("4140", exact=False)

    # Verify results - should find both items containing "4140"
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA070001")
    search_page.assert_result_contains_item("JA070002")


@pytest.mark.e2e
def test_search_material_exact_match_workflow(page, live_server):
    """Test searching for materials with exact matching"""
    # Add test data with similar material names
    test_items = [
        {
            "ja_id": "JA071001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "4140 Pre-Hard",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Specific steel grade"
        },
        {
            "ja_id": "JA071002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "4140",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Generic 4140"
        },
        {
            "ja_id": "JA071003",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "400",
            "width": "15",
            "location": "Storage C",
            "notes": "Different material"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for exact material "4140" (exact match enabled)
    search_page.search_by_material_with_match_type("4140", exact=True)

    # Verify results - should find only the exact match
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA071002")


@pytest.mark.e2e
def test_search_material_exact_no_results_workflow(page, live_server):
    """Test exact match returns no results when partial match exists"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA072001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "304/304L Stainless",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Stainless steel"
        },
        {
            "ja_id": "JA072002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "250",
            "width": "10",
            "location": "Storage B",
            "notes": "Carbon steel"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for exact material "304" (which doesn't exist as exact match)
    search_page.search_by_material_with_match_type("304", exact=True)

    # Verify no results - exact match doesn't exist
    search_page.assert_no_results_found()
