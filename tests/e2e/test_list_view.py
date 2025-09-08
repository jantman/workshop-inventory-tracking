"""
E2E Tests for List View Workflow

Happy-path browser tests for inventory list functionality.
"""

import pytest
from tests.e2e.pages.inventory_list_page import InventoryListPage


@pytest.mark.e2e
def test_empty_inventory_list_workflow(page, live_server):
    """Test viewing empty inventory list"""
    # Navigate to inventory list (no items added)
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Verify empty list is displayed properly
    list_page.assert_no_items_displayed()


@pytest.mark.e2e
def test_basic_inventory_list_workflow(page, live_server):
    """Test viewing inventory list with items"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA101001",
            "item_type": "Rod",
            "shape": "Round",
            "material": "Steel", 
            "length": "500",
            "width": "12",
            "location": "Storage A",
            "notes": "Steel rod item"
        },
        {
            "ja_id": "JA101002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "1000",
            "width": "500", 
            "thickness": "3",
            "location": "Storage B",
            "notes": "Aluminum sheet"
        },
        {
            "ja_id": "JA101003", 
            "item_type": "Tube",
            "shape": "Round",
            "material": "Copper",
            "length": "300",
            "width": "25",
            "wall_thickness": "2",
            "location": "Storage C", 
            "notes": "Copper tube"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Verify all items are displayed
    list_page.assert_items_displayed(3)
    list_page.assert_item_in_list("JA101001")
    list_page.assert_item_in_list("JA101002")
    list_page.assert_item_in_list("JA101003")


@pytest.mark.e2e
def test_list_search_functionality(page, live_server):
    """Test search functionality within the list view"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA102001",
            "item_type": "Rod", 
            "shape": "Round",
            "material": "Steel",
            "location": "Storage A",
            "notes": "Steel rod for testing"
        },
        {
            "ja_id": "JA102002",
            "item_type": "Rod",
            "shape": "Round", 
            "material": "Aluminum",
            "location": "Storage B",
            "notes": "Aluminum rod for testing"
        },
        {
            "ja_id": "JA102003",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Steel",
            "location": "Storage C",
            "notes": "Steel sheet for testing"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Verify all items initially displayed
    list_page.assert_items_displayed(3)
    
    # Search for steel items
    list_page.search_items("Steel")
    
    # Verify search results
    search_results = list_page.assert_search_results_contain("Steel")
    assert len(search_results) >= 1, "Should find at least one steel item"


@pytest.mark.e2e
def test_list_material_filter(page, live_server):
    """Test material filtering in list view"""
    # Add test data with different materials
    test_items = [
        {
            "ja_id": "JA103001",
            "item_type": "Rod",
            "shape": "Round",
            "material": "Steel",
            "location": "Storage A", 
            "notes": "Steel item"
        },
        {
            "ja_id": "JA103002",
            "item_type": "Rod",
            "shape": "Round",
            "material": "Aluminum", 
            "location": "Storage B",
            "notes": "Aluminum item"
        },
        {
            "ja_id": "JA103003",
            "item_type": "Rod", 
            "shape": "Round",
            "material": "Steel",
            "location": "Storage C",
            "notes": "Another steel item"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Apply material filter
    list_page.filter_by_material("Steel")
    
    # Verify filtered results
    items = list_page.get_inventory_items()
    steel_items = [item for item in items if "Steel" in item.get("material", "")]
    assert len(steel_items) >= 1, "Should find steel items after filtering"


@pytest.mark.e2e
def test_list_location_filter(page, live_server):
    """Test location filtering in list view"""
    # Add test data with different locations
    test_items = [
        {
            "ja_id": "JA104001",
            "item_type": "Rod",
            "shape": "Round",
            "material": "Steel",
            "location": "Storage A",
            "notes": "Item in A"
        },
        {
            "ja_id": "JA104002", 
            "item_type": "Rod",
            "shape": "Round",
            "material": "Steel",
            "location": "Storage B",
            "notes": "Item in B"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Apply location filter
    list_page.filter_by_location("Storage A")
    
    # Verify filtered results
    items = list_page.get_inventory_items()
    storage_a_items = [item for item in items if "Storage A" in item.get("location", "")]
    assert len(storage_a_items) >= 1, "Should find items in Storage A after filtering"


@pytest.mark.e2e
def test_navigation_to_add_item(page, live_server):
    """Test navigation from list view to add item form"""
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Click add item button
    list_page.click_add_item()
    
    # Verify we navigated to add item page (URL should change)
    list_page.assert_url_contains("/inventory/add")


@pytest.mark.e2e
def test_list_view_with_many_items(page, live_server):
    """Test list view performance with multiple items"""
    # Add many test items
    test_items = []
    for i in range(1, 21):  # Add 20 items
        test_items.append({
            "ja_id": f"JA105{i:03d}",
            "item_type": "Rod",
            "shape": "Round", 
            "material": f"Material{i % 5}",  # 5 different materials
            "location": f"Storage {chr(65 + (i % 3))}",  # Storage A, B, C
            "notes": f"Test item number {i}"
        })
    
    live_server.add_test_data(test_items)
    
    # Navigate to list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Verify all items are displayed (or proper pagination if implemented)
    items = list_page.get_inventory_items()
    assert len(items) >= 10, "Should display multiple items"
    
    # Test search with many items
    list_page.search_items("JA105001")
    
    # Should find specific item
    list_page.assert_item_in_list("JA105001")


@pytest.mark.e2e
def test_list_view_item_details(page, live_server):
    """Test that item details are properly displayed in list"""
    # Add test item with specific details
    test_items = [
        {
            "ja_id": "JA106001",
            "item_type": "Rod",
            "shape": "Round",
            "material": "Stainless Steel", 
            "length_mm": "1000",
            "diameter_mm": "25",
            "location": "Main Storage Area",
            "notes": "High grade stainless steel rod"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Get item details
    items = list_page.get_inventory_items()
    
    # Find our test item
    test_item = next((item for item in items if item["ja_id"] == "JA106001"), None)
    assert test_item is not None, "Test item should be in the list"
    
    # Verify key details are displayed
    assert "Stainless Steel" in test_item["material"], "Material should be displayed"
    assert "Main Storage Area" in test_item["location"], "Location should be displayed"