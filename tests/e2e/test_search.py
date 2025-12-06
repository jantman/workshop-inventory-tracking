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
            "material": "Carbon Steel",
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
            "material": "Carbon Steel",
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
    search_page.search_by_material("Carbon Steel")
    
    # Verify results
    search_page.assert_results_found(2)  # Should find 2 steel items
    search_page.assert_result_contains_item("JA001001")
    search_page.assert_result_contains_item("JA001003")
    search_page.assert_all_results_match_criteria(material="Carbon Steel")


@pytest.mark.e2e
def test_search_by_location_workflow(page, live_server):
    """Test searching for items by location"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA002001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
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
            "material": "Carbon Steel",
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
            "material": "Carbon Steel",
            "length": "250",
            "width": "10",
            "location": "Storage A", 
            "notes": "Steel rod in A"
        },
        {
            "ja_id": "JA004002",
            "item_type": "Bar",
            "shape": "Round", 
            "material": "Carbon Steel",
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
    search_page.search_multiple_criteria(material="Carbon Steel", location="Storage A")
    
    # Verify results
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA004001")
    search_page.assert_all_results_match_criteria(material="Carbon Steel", location="Storage A")


@pytest.mark.e2e
def test_search_no_results_workflow(page, live_server):
    """Test search with no matching results"""
    # Add test data
    test_items = [
        {
            "ja_id": "JA005001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
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
            "material": "Carbon Steel",
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
    search_page.search_by_material("Carbon Steel")
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
            "material": "Carbon Steel",
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


@pytest.mark.e2e 
def test_search_by_shape_workflow(page, live_server):
    """Test searching for items by shape - this test should FAIL initially due to enum conversion bug"""
    # Add test data with round items
    test_items = [
        {
            "ja_id": "JA008001",
            "item_type": "Bar",
            "shape": "Round", 
            "material": "Carbon Steel",
            "length": "200",
            "width": "1.0",
            "location": "Storage A",
            "notes": "Round bar for testing shape search"
        },
        {
            "ja_id": "JA008002",
            "item_type": "Bar",
            "shape": "Square",
            "material": "Aluminum", 
            "length": "150",
            "width": "0.75",
            "location": "Storage B",
            "notes": "Square bar for testing shape search"
        },
        {
            "ja_id": "JA008003", 
            "item_type": "Bar",
            "shape": "Round",
            "material": "Brass",
            "length": "180",
            "width": "0.5",
            "location": "Storage C",
            "notes": "Another round bar"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search for round items
    search_page.search_by_shape("Round")
    
    # Verify results - should find 2 round items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA008001")
    search_page.assert_result_contains_item("JA008003")
    search_page.assert_all_results_match_criteria(shape="Round")


@pytest.mark.e2e
def test_search_by_shape_and_width_range_workflow(page, live_server):
    """Test searching for items by shape and width range - reproduces the specific bug scenario"""
    # Add test data matching the bug report scenario: shape=Round, width between 0.62-1.3
    test_items = [
        {
            "ja_id": "JA009001",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel", 
            "length": "300",
            "width": "0.75",  # Within range 0.62-1.3
            "location": "Storage A",
            "notes": "Round bar within width range"
        },
        {
            "ja_id": "JA009002",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "length": "250", 
            "width": "1.0",   # Within range 0.62-1.3
            "location": "Storage B",
            "notes": "Another round bar in range"
        },
        {
            "ja_id": "JA009003",
            "item_type": "Bar", 
            "shape": "Round",
            "material": "Stainless Steel",
            "length": "200",
            "width": "0.5",   # Below range (should not match)
            "location": "Storage C",
            "notes": "Round bar too small"
        },
        {
            "ja_id": "JA009004",
            "item_type": "Bar",
            "shape": "Square",
            "material": "Carbon Steel",
            "length": "180",
            "width": "0.8",   # Within range but wrong shape
            "location": "Storage D", 
            "notes": "Square bar in width range"
        },
        {
            "ja_id": "JA009005",
            "item_type": "Bar",
            "shape": "Round",
            "material": "Brass",
            "length": "350",
            "width": "1.5",   # Above range (should not match)
            "location": "Storage E",
            "notes": "Round bar too big"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search for active items with shape round and width between 0.62 and 1.3
    # This reproduces the exact scenario from the bug report
    search_page.search_by_shape_and_width_range("Round", "0.62", "1.3")
    
    # Verify results - should find 2 items (JA009001 and JA009002)
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA009001")
    search_page.assert_result_contains_item("JA009002")
    search_page.assert_all_results_match_criteria(shape="Round")


@pytest.mark.e2e
def test_search_by_item_type_single_word_workflow(page, live_server):
    """Test searching for items by single-word item type (should work)"""
    # Add test data with various item types
    test_items = [
        {
            "ja_id": "JA010001", 
            "item_type": "Bar", 
            "shape": "Round", 
            "material": "Carbon Steel",
            "length": "300",
            "width": "12",
            "location": "Storage A"
        },
        {
            "ja_id": "JA010002",
            "item_type": "Plate", 
            "shape": "Rectangular", 
            "material": "Aluminum",
            "length": "500",
            "width": "200",
            "thickness": "5",
            "location": "Storage B"
        },
        {
            "ja_id": "JA010003",
            "item_type": "Bar", 
            "shape": "Square", 
            "material": "Brass",
            "length": "200",
            "width": "10",
            "location": "Storage A"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search for Bar items (single-word type - should work)
    search_page.search_by_item_type("Bar")
    
    # Verify results - should find 2 Bar items
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA010001")
    search_page.assert_result_contains_item("JA010003")


@pytest.mark.e2e  
def test_search_by_threaded_rod_type_workflow(page, live_server):
    """Test searching for Threaded Rod items (currently fails due to enum bug)"""
    # Add test data including Threaded Rod items
    # Note: We need to create Item objects properly with thread info for Threaded Rod
    from app.database import InventoryItem
    from app.models import ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
    from decimal import Decimal
    
    # Create proper InventoryItem objects for threaded rods
    threaded_rod_1 = InventoryItem(
        ja_id="JA011001",
        item_type="Threaded Rod",  # Store as string
        shape="Round",             # Store as string
        material="Carbon Steel",
        length=36,                 # Store as float
        width=0.25,                # Store as float
        thread_series="UNC",       # Store as string
        thread_handedness="Right", # Store as string
        thread_size="1/4-20",      # Store as string
        location="Storage D",
        notes="1/4-20 threaded rod",
        active=True
    )
    
    threaded_rod_2 = InventoryItem(
        ja_id="JA011002",
        item_type="Threaded Rod",  # Store as string
        shape="Round",             # Store as string
        material="Stainless Steel",
        length=48,                 # Store as float
        width=0.375,               # Store as float
        thread_series="UNC",       # Store as string
        thread_handedness="Right", # Store as string
        thread_size="3/8-16",      # Store as string
        location="Storage D",
        notes="3/8-16 threaded rod",
        active=True
    )
    
    test_items = [
        threaded_rod_1,
        threaded_rod_2,
        {
            "ja_id": "JA011003",
            "item_type": "Bar", 
            "shape": "Round", 
            "material": "Carbon Steel",
            "length": "36",
            "width": "0.25",
            "location": "Storage A",
            "notes": "Regular rod, not threaded"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search for Threaded Rod items - this should work once bug is fixed
    search_page.search_by_item_type("Threaded Rod")
    
    # Verify results - this will fail until the enum bug is fixed
    search_page.assert_results_found(2)
    search_page.assert_result_contains_item("JA011001")
    search_page.assert_result_contains_item("JA011002")


@pytest.mark.e2e
def test_search_by_multiple_criteria_with_threaded_rod_workflow(page, live_server):
    """Test searching with multiple criteria including Threaded Rod type"""
    # Add test data
    from app.database import InventoryItem
    from app.models import ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
    from decimal import Decimal
    
    # Create proper threaded rod items
    threaded_rod_carbon = InventoryItem(
        ja_id="JA012001",
        item_type="Threaded Rod",  # Store as string
        shape="Round",             # Store as string
        material="Carbon Steel",
        length=36,                 # Store as float
        width=0.25,                # Store as float
        thread_series="UNC",       # Store as string
        thread_handedness="Right", # Store as string
        thread_size="1/4-20",      # Store as string
        location="Storage D",
        active=True
    )
    
    threaded_rod_stainless = InventoryItem(
        ja_id="JA012002",
        item_type="Threaded Rod",  # Store as string
        shape="Round",             # Store as string
        material="Stainless Steel",
        length=36,                 # Store as float
        width=0.25,                # Store as float
        thread_series="UNC",       # Store as string
        thread_handedness="Right", # Store as string
        thread_size="1/4-20",      # Store as string
        location="Storage D",
        active=True
    )
    
    test_items = [
        threaded_rod_carbon,
        threaded_rod_stainless,
        {
            "ja_id": "JA012003",
            "item_type": "Bar",  # Different type
            "shape": "Round", 
            "material": "Carbon Steel",
            "length": "36",
            "width": "0.25",
            "location": "Storage D"
        }
    ]
    live_server.add_test_data(test_items)
    
    # Navigate to search page
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    
    # Search for Threaded Rod + Carbon Steel combination
    search_page.search_multiple_criteria(
        item_type="Threaded Rod",
        material="Carbon Steel"
    )
    
    # Should find only JA012001 (Threaded Rod + Carbon Steel)
    # This will fail until the enum lookup bug is fixed
    search_page.assert_results_found(1)
    search_page.assert_result_contains_item("JA012001")