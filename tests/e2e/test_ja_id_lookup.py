"""
E2E Tests for JA ID Lookup functionality
"""

import pytest
import re
from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.inventory_list_page import InventoryListPage
from playwright.sync_api import expect


@pytest.mark.e2e
def test_ja_id_lookup_with_existing_item(page, live_server):
    """Test JA ID lookup with an existing item navigates to edit page"""
    # First add a test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA200001",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Carbon Steel",
        "length": "12",
        "width": "1",
        "location": "Workshop"
    }
    
    # Add the test item
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], 
                                 test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.fill_location_and_notes(location=test_item["location"], notes="Test item for JA lookup")
    add_page.submit_form()
    
    # Navigate to any page to see the navbar
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Find the JA ID lookup input
    lookup_input = page.locator('#ja-id-lookup')
    expect(lookup_input).to_be_visible()
    
    # Enter the JA ID and press Enter
    lookup_input.fill("JA200001")
    lookup_input.press('Enter')
    
    # Should navigate to edit page
    expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA200001')
    
    # Verify we're on the edit page by checking the form is populated
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).to_have_value('JA200001')


@pytest.mark.e2e
def test_ja_id_lookup_with_nonexistent_item(page, live_server):
    """Test JA ID lookup with nonexistent item shows error"""
    # Navigate to inventory list to see the navbar
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Find the JA ID lookup input
    lookup_input = page.locator('#ja-id-lookup')
    expect(lookup_input).to_be_visible()
    
    # Enter a nonexistent JA ID and press Enter
    lookup_input.fill("JA999999")
    lookup_input.press('Enter')
    
    # Should redirect to inventory list with error message
    expect(page).to_have_url(f'{live_server.url}/inventory')
    
    # Verify error message appears (be specific to avoid multiple matches)
    error_alert = page.locator('.alert-danger.alert-dismissible')
    expect(error_alert).to_contain_text('Item JA999999 not found')


@pytest.mark.e2e 
def test_ja_id_lookup_input_formatting(page, live_server):
    """Test JA ID lookup input auto-formatting"""
    # Navigate to inventory list to see the navbar
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Find the JA ID lookup input
    lookup_input = page.locator('#ja-id-lookup')
    expect(lookup_input).to_be_visible()
    
    # Test auto-formatting: enter just numbers
    lookup_input.fill("123456")
    expect(lookup_input).to_have_value("JA123456")
    
    # Clear and test with full JA ID
    lookup_input.fill("JA654321")
    expect(lookup_input).to_have_value("JA654321")


@pytest.mark.e2e
def test_ja_id_lookup_invalid_format_validation(page, live_server):
    """Test JA ID lookup validation for invalid formats"""
    # Navigate to inventory list to see the navbar
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Find the JA ID lookup input
    lookup_input = page.locator('#ja-id-lookup')
    expect(lookup_input).to_be_visible()
    
    # Enter invalid format and press Enter
    lookup_input.fill("invalid")
    lookup_input.press('Enter')
    
    # Should show validation error (input becomes invalid)
    expect(lookup_input).to_have_class(re.compile(r'.*is-invalid.*'))
    
    # Should not navigate away from current page
    expect(page).to_have_url(f'{live_server.url}/inventory')
    
    # Wait for error to clear automatically
    page.wait_for_timeout(2500)
    expect(lookup_input).not_to_have_class(re.compile(r'.*is-invalid.*'))