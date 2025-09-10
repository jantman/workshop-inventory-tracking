"""
E2E Tests for JA ID Auto-Generation

Tests for the automatic JA ID generation functionality.
"""

import pytest
from tests.e2e.pages.add_item_page import AddItemPage
from playwright.sync_api import expect


@pytest.mark.e2e  
def test_ja_id_auto_population_on_page_load(page, live_server):
    """Test that JA ID is automatically populated when add page loads"""
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # JA ID field should be auto-populated (not empty)
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).not_to_have_value('')
    
    # Verify the auto-populated ID follows the correct format (JA######)
    auto_populated_id = ja_id_field.input_value()
    assert auto_populated_id.startswith('JA'), f"Auto-populated ID should start with 'JA', got: {auto_populated_id}"
    assert len(auto_populated_id) == 8, f"Auto-populated ID should be 8 characters long, got: {len(auto_populated_id)}"
    assert auto_populated_id[2:].isdigit(), f"Auto-populated ID should have 6 digits after 'JA', got: {auto_populated_id}"
    
    # With no existing items, should be JA000001
    assert auto_populated_id == "JA000001", f"First auto-populated ID should be JA000001, got: {auto_populated_id}"


@pytest.mark.e2e  
def test_ja_id_field_validation_after_auto_population(page, live_server):
    """Test that validation errors are cleared after auto-population"""
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # JA ID field should be auto-populated and valid
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).not_to_have_value('')
    
    # Check that no validation errors are visible
    invalid_feedback = page.locator('#ja_id + .input-group + .invalid-feedback')
    expect(invalid_feedback).not_to_be_visible()
    
    # Verify the field is not marked as invalid
    expect(ja_id_field).not_to_have_class('is-invalid')
    
    # The auto-populated value should be valid
    auto_populated_id = ja_id_field.input_value()
    assert auto_populated_id == "JA000001", f"Auto-populated ID should be JA000001, got: {auto_populated_id}"


@pytest.mark.e2e  
def test_generate_ja_id_button_removed_from_add_form(page, live_server):
    """Test that the generate JA ID button has been removed from add form"""
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # The generate JA ID button should not exist
    generate_button = page.locator('#generate-ja-id-btn')
    expect(generate_button).not_to_be_attached()
    
    # But the scan barcode button should still be there
    scan_button = page.locator('#scan-ja-id-btn')
    expect(scan_button).to_be_visible()
    expect(scan_button).to_have_attribute('title', 'Scan barcode')


@pytest.mark.e2e
def test_ja_id_auto_population_with_existing_items(page, live_server):
    """Test JA ID auto-population when items already exist"""
    # First add an item manually with a specific JA ID
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Clear the auto-populated ID and enter our test ID
    ja_id_field = page.locator('#ja_id')
    ja_id_field.fill("JA000050")
    
    # Add a test item with JA ID JA000050
    test_item = {
        "item_type": "Bar", 
        "shape": "Round",
        "material": "Test Steel",
        "length": "10",
        "width": "1"
    }
    
    # Fill the form but skip JA ID since we already set it
    page.select_option("#item_type", test_item["item_type"])
    page.select_option("#shape", test_item["shape"])
    page.fill("#material", test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.submit_form()
    
    # Wait for success flash message or redirect
    try:
        # Look for success message
        success_message = page.locator('.alert-success')
        expect(success_message).to_be_visible(timeout=5000)
    except:
        # If no success message, wait for URL change
        page.wait_for_timeout(2000)
    
    # Additional wait to ensure Google Sheets persistence
    page.wait_for_timeout(3000)
    
    # Navigate back to add another item
    add_page.navigate()
    
    # Now test that auto-population produces JA000051 or higher
    expect(ja_id_field).not_to_have_value('')
    
    auto_populated_id = ja_id_field.input_value()
    generated_number = int(auto_populated_id[2:])
    
    # Should be at least 51 (next after our manually added 50)
    assert generated_number >= 51, f"Auto-populated ID should be >= 51, got: {generated_number}"


@pytest.mark.e2e
def test_api_next_ja_id_endpoint(page, live_server):
    """Test the API endpoint directly"""
    # Navigate to any page to establish session
    page.goto(live_server.url)
    
    # Call the API endpoint directly
    response = page.request.get(f'{live_server.url}/api/inventory/next-ja-id')
    
    # Verify response
    assert response.ok, f"API request failed with status: {response.status}"
    
    data = response.json()
    assert data['success'] is True, f"API returned success=False: {data}"
    assert 'next_ja_id' in data, f"API response missing next_ja_id: {data}"
    
    next_id = data['next_ja_id']
    assert next_id.startswith('JA'), f"Generated ID should start with 'JA', got: {next_id}"
    assert len(next_id) == 8, f"Generated ID should be 8 characters long, got: {len(next_id)}"
    assert next_id[2:].isdigit(), f"Generated ID should have 6 digits after 'JA', got: {next_id}"