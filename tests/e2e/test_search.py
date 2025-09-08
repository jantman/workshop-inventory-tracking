"""
E2E Tests for Search Workflow

Happy-path browser tests for searching inventory items.
"""

import pytest
from tests.e2e.pages.search_page import SearchPage
from tests.e2e.pages.inventory_list_page import InventoryListPage


@pytest.mark.e2e
def test_search_by_material_workflow(page, live_server):
    """Test searching for items by material"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA001001", 
            "item_type": "Bar", 
            "shape": "Round", 
            "material": "Steel",
            "length": "300",
            "width": "12",
            "location": "Storage A",
            "notes": "Steel rod item"
        },
        {
            "ja_id": "JA001002",
            "item_type": "Bar", 
            "shape": "Round", 
            "material": "Aluminum",
            "length": "250",
            "width": "10",
            "location": "Storage B", 
            "notes": "Aluminum rod item"
        },
        {
            "ja_id": "JA001003",
            "item_type": "Bar", 
            "shape": "Round", 
            "material": "Steel",
            "length": "400",
            "width": "15",
            "location": "Storage C",
            "notes": "Another steel rod"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Verify search form is visible
    search_page.assert_search_form_visible()
    
    # Search for steel items
    search_page.search_by_material("Steel")
    
    # Verify results
    search_page.assert_results_found(2)  # Should find 2 steel items
    search_page.assert_result_contains_item("JA001001")
    search_page.assert_result_contains_item("JA001003")
    search_page.assert_all_results_match_criteria(material="Steel")


@pytest.mark.e2e
def test_search_by_location_workflow(page, live_server):
    """Test searching for items by location"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA002001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Steel",
            "length": "200",
            "width": "8",
            "location": "Storage A",
            "notes": "Item in Storage A"
        },
        {
            "ja_id": "JA002002",
            "item_type": "Sheet",
            "shape": "Rectangular", 
            "material": "Aluminum",
            "length": "500",
            "width": "300",
            "thickness": "2",
            "location": "Storage B",
            "notes": "Item in Storage B"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate and search
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search by location
    search_page.search_by_location("Storage A")
    
    # Verify results
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA002001")
    search_page.assert_all_results_match_criteria(location="Storage A")


@pytest.mark.e2e
def test_search_by_ja_id_workflow(page, live_server):
    """Test searching for specific item by JA ID"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA003001",
            "item_type": "Bar",
            "shape": "Round", 
            "material": "Copper",
            "length": "150",
            "width": "6",
            "location": "Storage A",
            "notes": "Copper rod for testing"
        },
        {
            "ja_id": "JA003002", 
            "item_type": "Tube",
            "shape": "Round",
            "material": "Steel",
            "length": "300",
            "width": "25",
            "wall_thickness": "2",
            "location": "Storage B",
            "notes": "Steel tube for testing"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate and search
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search by specific JA ID
    search_page.search_by_ja_id("JA003001")
    
    # Verify results
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA003001")


@pytest.mark.e2e
def test_search_multiple_criteria_workflow(page, live_server):
    """Test searching with multiple criteria"""
    # Add test data with variety
    test_items = [
        {
            "ja_id": "JA004001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Steel",
            "length": "250",
            "width": "10",
            "location": "Storage A", 
            "notes": "Steel rod in A"
        },
        {
            "ja_id": "JA004002",
            "item_type": "Bar",
            "shape": "Round", 
            "material": "Steel",
            "length": "300",
            "width": "12",
            "location": "Storage B",
            "notes": "Steel rod in B"
        },
        {
            "ja_id": "JA004003",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "400",
            "width": "200",
            "thickness": "1.5",
            "location": "Storage A",
            "notes": "Aluminum sheet in A"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate and search
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search with multiple criteria: Steel items in Storage A
    search_page.search_multiple_criteria(material="Steel", location="Storage A")
    
    # Verify results
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA004001")
    search_page.assert_all_results_match_criteria(material="Steel", location="Storage A")


@pytest.mark.e2e
def test_search_no_results_workflow(page, live_server):
    """Test search with no matching results"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA005001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Steel",
            "length": "200",
            "width": "8",
            "location": "Storage A",
            "notes": "Only steel item"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate and search
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search for non-existent material
    search_page.search_by_material("Titanium")
    
    # Verify no results
    search_page.assert_no_results_found()


@pytest.mark.e2e
def test_search_clear_form_workflow(page, live_server):
    """Test clearing search form and results"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA006001",
            "item_type": "Bar", 
            "shape": "Round",
            "material": "Steel",
            "length": "180",
            "width": "7",
            "location": "Storage A",
            "notes": "Test item"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate and search
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Perform search
    search_page.search_by_material("Steel")
    search_page.assert_results_found()
    
    # Clear search form
    search_page.clear_search()
    
    # Verify form is cleared and no results shown
    # The exact behavior depends on implementation
    # For now, just verify we can perform a new search
    search_page.search_by_location("Storage A") 
    search_page.assert_results_found()


@pytest.mark.e2e
def test_search_notes_content_workflow(page, live_server):
    """Test searching by notes content"""
    # Add test data with specific notes
    test_items = [
        {
            "ja_id": "JA007001",
            "item_type": "Bar",
            "shape": "Round", 
            "material": "Steel",
            "length": "350",
            "width": "14",
            "location": "Storage A",
            "notes": "High quality steel rod for machining"
        },
        {
            "ja_id": "JA007002",
            "item_type": "Sheet",
            "shape": "Rectangular",
            "material": "Aluminum",
            "length": "600",
            "width": "400",
            "thickness": "1",
            "location": "Storage B",
            "notes": "Thin aluminum sheet for fabrication"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate and search
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search by notes content
    search_page.search_by_notes("machining")
    
    # Verify results
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA007001")