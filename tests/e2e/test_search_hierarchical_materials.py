"""
E2E Tests for Hierarchical Material Search

Tests to verify that hierarchical material searching works correctly - searching
for a parent material returns items with child and grandchild materials.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage


@pytest.mark.e2e
def test_search_l1_material_returns_l2_and_l3_items(page, live_server):
    """Test that searching for L1 category returns items with L2 and L3 materials"""
    # Add taxonomy data
    taxonomy_data = [
        # L1: Aluminum
        {"name": "Aluminum", "level": 1, "parent": None, "active": True},
        # L2: Children of Aluminum
        {"name": "6000 Series Aluminum", "level": 2, "parent": "Aluminum", "active": True},
        {"name": "7000 Series Aluminum", "level": 2, "parent": "Aluminum", "active": True},
        # L3: Grandchildren
        {"name": "6061-T6", "level": 3, "parent": "6000 Series Aluminum", "active": True},
        {"name": "6063-T5", "level": 3, "parent": "6000 Series Aluminum", "active": True},
    ]
    live_server.add_material_taxonomy(taxonomy_data)

    # Add inventory items at different levels
    test_items = [
        {
            "ja_id": "JA080001",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Aluminum",  # L1
            "length": "300",
            "width": "200",
            "thickness": "10",
            "location": "Storage A"
        },
        {
            "ja_id": "JA080002",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "6000 Series Aluminum",  # L2
            "length": "250",
            "width": "150",
            "thickness": "8",
            "location": "Storage B"
        },
        {
            "ja_id": "JA080003",
            "item_type": "Bar",
            "shape": "Round",
            "material": "6061-T6",  # L3
            "length": "400",
            "width": "25",
            "location": "Storage C"
        },
        {
            "ja_id": "JA080004",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Steel",  # Different material entirely
            "length": "350",
            "width": "20",
            "location": "Storage D"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for "Aluminum" (L1 material)
    search_page.search_by_material("Aluminum")

    # Should find all 3 aluminum items (L1, L2, and L3)
    search_page.assert_results_found(3)
    search_page.assert_result_contains_item("JA080001")  # L1
    search_page.assert_result_contains_item("JA080002")  # L2
    search_page.assert_result_contains_item("JA080003")  # L3
    # Should NOT find the steel item
    search_page.assert_result_not_contains_item("JA080004")


@pytest.mark.e2e
def test_search_l2_material_returns_l3_items(page, live_server):
    """Test that searching for L2 family returns items with L3 materials"""
    # Add taxonomy data
    taxonomy_data = [
        {"name": "Aluminum", "level": 1, "parent": None, "active": True},
        {"name": "6000 Series Aluminum", "level": 2, "parent": "Aluminum", "active": True},
        {"name": "7000 Series Aluminum", "level": 2, "parent": "Aluminum", "active": True},
        {"name": "6061-T6", "level": 3, "parent": "6000 Series Aluminum", "active": True},
        {"name": "7075-T6", "level": 3, "parent": "7000 Series Aluminum", "active": True},
    ]
    live_server.add_material_taxonomy(taxonomy_data)

    # Add inventory items
    test_items = [
        {
            "ja_id": "JA081001",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "6000 Series Aluminum",  # L2
            "length": "300",
            "width": "200",
            "thickness": "10",
            "location": "Storage A"
        },
        {
            "ja_id": "JA081002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "6061-T6",  # L3 child
            "length": "400",
            "width": "25",
            "location": "Storage B"
        },
        {
            "ja_id": "JA081003",
            "item_type": "Bar",
            "shape": "Round",
            "material": "7075-T6",  # L3 but different parent
            "length": "350",
            "width": "20",
            "location": "Storage C"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for "6000 Series Aluminum" (L2 material)
    search_page.search_by_material("6000 Series Aluminum")

    # Should find the L2 item and its L3 child
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA081001")  # L2
    search_page.assert_result_contains_item("JA081002")  # L3 child
    # Should NOT find the L3 item with different parent
    search_page.assert_result_not_contains_item("JA081003")


@pytest.mark.e2e
def test_search_l3_material_returns_only_that_material(page, live_server):
    """Test that searching for L3 material returns only items with that exact material"""
    # Add taxonomy data
    taxonomy_data = [
        {"name": "Aluminum", "level": 1, "parent": None, "active": True},
        {"name": "6000 Series Aluminum", "level": 2, "parent": "Aluminum", "active": True},
        {"name": "6061-T6", "level": 3, "parent": "6000 Series Aluminum", "active": True},
        {"name": "6063-T5", "level": 3, "parent": "6000 Series Aluminum", "active": True},
    ]
    live_server.add_material_taxonomy(taxonomy_data)

    # Add inventory items
    test_items = [
        {
            "ja_id": "JA082001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "6061-T6",  # L3
            "length": "400",
            "width": "25",
            "location": "Storage A"
        },
        {
            "ja_id": "JA082002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "6063-T5",  # Different L3
            "length": "350",
            "width": "20",
            "location": "Storage B"
        },
        {
            "ja_id": "JA082003",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "6000 Series Aluminum",  # L2 parent
            "length": "300",
            "width": "200",
            "thickness": "10",
            "location": "Storage C"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for "6061-T6" (L3 material - leaf node)
    search_page.search_by_material("6061-T6")

    # Should find only the exact match (L3 materials don't have children)
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA082001")


@pytest.mark.e2e
def test_search_material_with_no_children(page, live_server):
    """Test searching for a material that has no children in the hierarchy"""
    # Add taxonomy data with materials that have no children
    taxonomy_data = [
        {"name": "Brass", "level": 1, "parent": None, "active": True},
        {"name": "Copper", "level": 1, "parent": None, "active": True},
    ]
    live_server.add_material_taxonomy(taxonomy_data)

    # Add inventory items
    test_items = [
        {
            "ja_id": "JA083001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Brass",  # L1 with no children
            "length": "400",
            "width": "25",
            "location": "Storage A"
        },
        {
            "ja_id": "JA083002",
            "item_type": "Plate",
            "shape": "Rectangular",
            "material": "Copper",  # Different L1
            "length": "300",
            "width": "200",
            "thickness": "10",
            "location": "Storage B"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for "Brass" (has no children)
    search_page.search_by_material("Brass")

    # Should find only the Brass item (no descendants to include)
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA083001")


@pytest.mark.e2e
def test_search_only_returns_active_materials(page, live_server):
    """Test that hierarchical search only includes active materials"""
    # Add taxonomy data with both active and inactive materials
    taxonomy_data = [
        {"name": "Steel", "level": 1, "parent": None, "active": True},
        {"name": "Carbon Steel", "level": 2, "parent": "Steel", "active": True},
        {"name": "1018 Steel", "level": 3, "parent": "Carbon Steel", "active": True},
        {"name": "Deprecated Steel Type", "level": 3, "parent": "Carbon Steel", "active": False},  # Inactive
    ]
    live_server.add_material_taxonomy(taxonomy_data)

    # Add inventory items
    test_items = [
        {
            "ja_id": "JA084001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "1018 Steel",  # Active L3
            "length": "400",
            "width": "25",
            "location": "Storage A"
        },
        {
            "ja_id": "JA084002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Deprecated Steel Type",  # Inactive L3
            "length": "350",
            "width": "20",
            "location": "Storage B"
        }
    ]
    live_server.add_test_data(test_items)

    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()

    # Search for "Steel" (L1 material)
    search_page.search_by_material("Steel")

    # Should find only items with active materials in the hierarchy
    # Note: The item with "Deprecated Steel Type" should still be found
    # because the item exists, but the inactive material won't be included
    # in the descendant lookup
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA084001")
