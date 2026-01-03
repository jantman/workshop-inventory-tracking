"""
E2E Tests for Hierarchical Material Search

Tests to verify that hierarchical material search works correctly on the search form.
Note: The old "exact match" functionality has been replaced with hierarchical search.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_material_hierarchical_workflow(page, live_server):
    """Test searching for materials with hierarchical matching"""
    # Add taxonomy with hierarchical materials
    taxonomy_data = [
        {"name": "Steel", "level": 1, "parent": None, "active": True},
        {"name": "4140 Series", "level": 2, "parent": "Steel", "active": True},
        {"name": "4140", "level": 3, "parent": "4140 Series", "active": True},
        {"name": "4140 Pre-Hard", "level": 3, "parent": "4140 Series", "active": True},
    ]
    live_server.add_material_taxonomy(taxonomy_data)

    # Add test data with materials at different levels
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
            "material": "4140 Series",
            "length": "350",
            "width": "11",
            "location": "Storage C",
            "notes": "Family level"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Verify search form is visible
    search_page.assert_search_form_visible()

    # Search for "4140 Series" - should find all items in that family
    search_page.search_by_material("4140 Series")

    # Verify results - should find all three items (L2 + its L3 children)
    search_page.assert_results_found(3)
    search_page.assert_result_contains_item("JA070001")
    search_page.assert_result_contains_item("JA070002")
    search_page.assert_result_contains_item("JA070003")
