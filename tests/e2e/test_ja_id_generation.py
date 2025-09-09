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
def test_generate_ja_id_button_functionality(page, live_server):
    """Test that the Generate JA ID button still works correctly"""
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Find the generate JA ID button
    generate_button = page.locator('#generate-ja-id-btn')
    expect(generate_button).to_be_visible()
    expect(generate_button).to_have_attribute('title', 'Generate next JA ID')
    
    # JA ID field should already be auto-populated
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).not_to_have_value('')
    
    # Clear the field to test manual generation
    ja_id_field.fill('')
    
    # Click the generate button
    generate_button.click()
    
    # Wait for the API call to complete and check that JA ID was generated
    expect(ja_id_field).not_to_have_value('')
    
    # Verify the generated ID follows the correct format (JA######)
    generated_id = ja_id_field.input_value()
    assert generated_id.startswith('JA'), f"Generated ID should start with 'JA', got: {generated_id}"
    assert len(generated_id) == 8, f"Generated ID should be 8 characters long, got: {len(generated_id)}"
    assert generated_id[2:].isdigit(), f"Generated ID should have 6 digits after 'JA', got: {generated_id}"
    
    # The first generation should work and produce JA000001 (since no items exist yet)
    assert generated_id == "JA000001", f"First generated ID should be JA000001, got: {generated_id}"


@pytest.mark.e2e
def test_generate_ja_id_with_existing_items(page, live_server):
    """Test JA ID generation when items already exist"""
    # First add an item manually with a specific JA ID
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Add a test item with JA ID JA000050
    test_item = {
        "ja_id": "JA000050",
        "item_type": "Bar", 
        "shape": "Round",
        "material": "Test Steel",
        "length": "10",
        "width": "1"
    }
    
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], 
                                 test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.submit_form()
    
    # Navigate back to add another item
    add_page.navigate()
    
    # Now test that generate JA ID produces JA000051 or higher
    generate_button = page.locator('#generate-ja-id-btn')
    generate_button.click()
    
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).not_to_have_value('')
    
    generated_id = ja_id_field.input_value()
    generated_number = int(generated_id[2:])
    
    # Should be at least 51 (next after our manually added 50)
    assert generated_number >= 51, f"Generated ID should be >= 51, got: {generated_number}"


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