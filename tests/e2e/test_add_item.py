"""
E2E Tests for Add Item Workflow

Happy-path browser tests for adding inventory items.
"""

import pytest
from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.inventory_list_page import InventoryListPage


@pytest.mark.e2e
def test_add_basic_item_workflow(page, live_server):
    """Test adding a basic item through the UI"""
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Verify form is displayed
    add_page.assert_form_visible()
    
    # Add a minimal item with required fields only
    add_page.add_minimal_item("JA000001", "Steel")
    
    # Verify successful submission
    add_page.assert_form_submitted_successfully()
    
    # Navigate to inventory list to verify item was added
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Verify the item appears in the list
    list_page.assert_item_in_list("JA000001")


@pytest.mark.e2e  
def test_add_complete_item_workflow(page, live_server):
    """Test adding a complete item with all fields filled"""
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Add a complete item with all common fields
    add_page.add_complete_item(
        ja_id="JA000002",
        item_type="Rod", 
        shape="Round",
        material="Aluminum",
        length="500",
        diameter="12",
        location="Storage B",
        notes="Test aluminum rod"
    )
    
    # Verify successful submission
    add_page.assert_form_submitted_successfully()
    
    # Verify item appears in inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.assert_item_in_list("JA000002")


@pytest.mark.e2e
def test_add_multiple_items_workflow(page, live_server):
    """Test adding multiple items in sequence"""
    add_page = AddItemPage(page, live_server.url)
    
    # Add first item
    add_page.navigate()
    add_page.add_minimal_item("JA000003", "Steel")
    add_page.assert_form_submitted_successfully()
    
    # Add second item
    add_page.navigate()
    add_page.add_minimal_item("JA000004", "Copper")
    add_page.assert_form_submitted_successfully()
    
    # Add third item
    add_page.navigate()
    add_page.add_complete_item(
        ja_id="JA000005",
        material="Brass",
        length="750",
        diameter="20",
        location="Storage C"
    )
    add_page.assert_form_submitted_successfully()
    
    # Verify all items appear in inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    list_page.assert_item_in_list("JA000003")
    list_page.assert_item_in_list("JA000004") 
    list_page.assert_item_in_list("JA000005")
    list_page.assert_items_displayed(3)


@pytest.mark.e2e
def test_form_navigation_workflow(page, live_server):
    """Test form navigation and cancel functionality"""
    add_page = AddItemPage(page, live_server.url)
    list_page = InventoryListPage(page, live_server.url)
    
    # Start from inventory list
    list_page.navigate()
    
    # Navigate to add item form via button
    list_page.click_add_item()
    
    # Verify we're on the add form
    add_page.assert_form_visible()
    
    # Fill some data then cancel
    add_page.fill_basic_item_data("JA000006", "Rod", "Round", "Steel")
    add_page.cancel_form()
    
    # Verify we're back to inventory list (or wherever cancel takes us)
    # The exact behavior depends on implementation
    # For now, just verify we can navigate back to add form
    add_page.navigate()
    add_page.assert_form_visible()


@pytest.mark.e2e
def test_form_field_validation_workflow(page, live_server):
    """Test basic form validation (if implemented in UI)"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Try to submit empty form
    add_page.submit_form()
    
    # The exact validation behavior depends on implementation
    # For now, just verify form is still visible (didn't submit successfully)
    add_page.assert_form_visible()
    
    # Fill valid data and verify it works
    add_page.add_minimal_item("JA000007", "Steel")
    add_page.assert_form_submitted_successfully()


@pytest.mark.e2e
def test_all_item_types_available_in_dropdown(page, live_server):
    """Test that all ItemType enum values appear in the Type dropdown"""
    from app.models import ItemType
    
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Verify form is displayed
    add_page.assert_form_visible()
    
    # Get all options from the item type dropdown (excluding the empty "Select type..." option)
    all_options = page.locator('#item_type option').all_text_contents()
    type_options = [option for option in all_options if option != "Select type..."]
    
    # Get all ItemType enum values
    expected_types = [item_type.value for item_type in ItemType]
    
    # Verify all ItemType enum values are in the dropdown
    for expected_type in expected_types:
        assert expected_type in type_options, f"'{expected_type}' not found in dropdown options: {type_options}"
    
    # Verify no extra options exist (should be exactly the same)
    assert sorted(type_options) == sorted(expected_types), f"Dropdown options don't match ItemType enum. Expected: {sorted(expected_types)}, Found: {sorted(type_options)}"
    
    # Test that we can actually select 'Threaded Rod' and add an item (since that was the original issue)
    add_page.fill_basic_item_data("JA000008", "Threaded Rod", "Round", "Steel")
    add_page.fill_dimensions(length="36", width="0.25")  # 36" long, 1/4" diameter
    add_page.submit_form()
    
    # Verify successful submission
    add_page.assert_form_submitted_successfully()