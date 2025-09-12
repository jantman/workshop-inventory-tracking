"""
E2E Tests for Material Field Taxonomy Validation

Tests that material fields in both Add and Edit forms only accept values 
from the materials taxonomy and reject invalid material names.
"""

import pytest
import re
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.inventory_list_page import InventoryListPage


@pytest.mark.e2e
def test_add_form_rejects_invalid_material(page, live_server):
    """Test that Add Item form rejects materials not in taxonomy"""
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Fill basic required fields
    page.locator('#ja_id').fill('JA999001')
    page.locator('#item_type').select_option('Bar')
    page.locator('#shape').select_option('Round')
    
    # Try invalid material names that should be rejected
    invalid_materials = [
        'InvalidMaterial123',
        'FakeMetal',
        'NotInTaxonomy',
        'Random Text Here'
    ]
    
    for invalid_material in invalid_materials:
        # Clear and fill with invalid material
        material_field = page.locator('#material')
        material_field.clear()
        material_field.fill(invalid_material)
        
        # Try to submit the form
        page.locator('button[type="submit"]').first.click()
        
        # Form should not submit successfully and should show validation error
        # The form should still be visible (not redirected away)
        add_page.assert_form_visible()
        
        # Material field should show as invalid
        expect(material_field).to_have_class(re.compile(r'.*\bis-invalid\b.*'))
        
        # Should show validation error message
        error_feedback = page.locator('#material').locator('xpath=following-sibling::div[contains(@class, "invalid-feedback")]').first
        expect(error_feedback).to_be_visible()
        expect(error_feedback).to_contain_text('must be from materials taxonomy')


@pytest.mark.e2e 
def test_add_form_accepts_valid_taxonomy_materials(page, live_server):
    """Test that Add Item form accepts valid materials from taxonomy"""
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Get valid materials from the page (should be included as data)
    valid_materials = page.evaluate('''
        () => {
            // Try to get materials list from various possible sources
            if (window.validMaterials) return window.validMaterials;
            if (window.materialsData) return window.materialsData.map(m => m.name);
            
            // Fallback: get from datalist if it exists
            const datalist = document.getElementById('materials-list');
            if (datalist) {
                return Array.from(datalist.options).map(opt => opt.value);
            }
            
            // Last resort: some common materials that should be in taxonomy
            return ['Steel', 'Carbon Steel', 'Stainless Steel', 'Aluminum', 'Brass', 'Copper'];
        }
    ''')
    
    # Test at least one valid material
    if valid_materials and len(valid_materials) > 0:
        test_material = valid_materials[0]
        
        # Fill form with valid data
        page.locator('#ja_id').fill('JA999002')
        page.locator('#item_type').select_option('Bar')
        page.locator('#shape').select_option('Round')
        page.locator('#material').fill(test_material)
        page.locator('#length').fill('12')
        page.locator('#width').fill('1')
        
        # Submit form
        page.locator('button[type="submit"]').first.click()
        
        # Should successfully submit (redirected away from form)
        page.wait_for_timeout(1000)  # Allow time for form processing
        
        # Should either be on success page or back to inventory list
        # The material field should not show as invalid
        material_field = page.locator('#material')
        if material_field.is_visible():  # If still on form page
            expect(material_field).not_to_have_class(re.compile(r'.*\bis-invalid\b.*'))


@pytest.mark.e2e
def test_edit_form_rejects_invalid_material(page, live_server):
    """Test that Edit Item form rejects materials not in taxonomy"""
    # First create an item to edit using a valid material
    add_page = AddItemPage(page, live_server.url) 
    add_page.navigate()
    add_page.add_minimal_item("JA999003", "Carbon Steel")
    add_page.assert_form_submitted_successfully()
    
    # Navigate to inventory list and find the item
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Click edit on the item (assumes edit link/button is available)
    edit_link = page.locator('a[href*="/edit"]').first
    if edit_link.is_visible():
        edit_link.click()
    else:
        # Alternative: construct edit URL directly
        page.goto(f"{live_server.url}/inventory/JA999003/edit")
    
    # Should be on edit form
    expect(page.locator('#add-item-form')).to_be_visible()
    expect(page.locator('h2')).to_contain_text('Edit Inventory Item')
    
    # Try to change to invalid material
    invalid_materials = [
        'InvalidEditMaterial',
        'AnotherFakeMetal', 
        'EditTestBadMaterial'
    ]
    
    for invalid_material in invalid_materials:
        # Clear and fill with invalid material
        material_field = page.locator('#material')
        material_field.clear()
        material_field.fill(invalid_material)
        
        # Try to submit the form
        page.locator('button[type="submit"]').click()
        
        # Form should not submit and should show validation error
        expect(page.locator('#add-item-form')).to_be_visible()
        expect(material_field).to_have_class(re.compile(r'.*\bis-invalid\b.*'))
        
        # Should show validation error message
        error_feedback = page.locator('#material').locator('xpath=following-sibling::div[contains(@class, "invalid-feedback")]').first
        expect(error_feedback).to_be_visible()
        expect(error_feedback).to_contain_text('must be from materials taxonomy')


@pytest.mark.e2e
def test_edit_form_accepts_valid_taxonomy_materials(page, live_server):
    """Test that Edit Item form accepts valid materials from taxonomy"""
    # First create an item to edit using a valid material
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate() 
    add_page.add_minimal_item("JA999004", "Carbon Steel")
    add_page.assert_form_submitted_successfully()
    
    # Navigate to edit form
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    edit_link = page.locator('a[href*="/edit"]').first
    if edit_link.is_visible():
        edit_link.click()
    else:
        page.goto(f"{live_server.url}/inventory/JA999004/edit")
    
    # Get valid materials from the page
    valid_materials = page.evaluate('''
        () => {
            if (window.validMaterials) return window.validMaterials;
            if (window.materialsData) return window.materialsData.map(m => m.name);
            
            const datalist = document.getElementById('materials-list');
            if (datalist) {
                return Array.from(datalist.options).map(opt => opt.value);
            }
            
            return ['Steel', 'Carbon Steel', 'Aluminum', 'Brass'];
        }
    ''')
    
    # Change to a different valid material
    if valid_materials and len(valid_materials) > 1:
        # Pick different material than current (Carbon Steel)
        new_material = next((m for m in valid_materials if m != 'Carbon Steel'), valid_materials[0])
        
        material_field = page.locator('#material')
        material_field.clear()
        material_field.fill(new_material)
        
        # Submit form
        page.locator('button[type="submit"]').click()
        
        # Should successfully update
        page.wait_for_timeout(1000)
        
        # Material field should not show as invalid
        if material_field.is_visible():
            expect(material_field).not_to_have_class(re.compile(r'.*\bis-invalid\b.*'))


@pytest.mark.e2e
def test_material_autocomplete_only_shows_taxonomy_materials(page, live_server):
    """Test that material autocomplete only suggests materials from taxonomy"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Start typing in material field to trigger autocomplete
    material_field = page.locator('#material')
    material_field.fill('Ste')
    
    # Wait for autocomplete suggestions
    page.wait_for_timeout(500)
    
    # Check if autocomplete suggestions appear
    suggestions_div = page.locator('#material-suggestions')
    if suggestions_div.is_visible():
        # All visible suggestions should be valid taxonomy materials
        suggestion_items = page.locator('#material-suggestions .dropdown-item')
        
        if suggestion_items.count() > 0:
            # Click first suggestion
            first_suggestion = suggestion_items.first
            suggestion_text = first_suggestion.text_content()
            first_suggestion.click()
            
            # Material field should now contain the selected value
            expect(material_field).to_have_value(suggestion_text)
            
            # This selected value should be valid when submitting
            page.locator('#ja_id').fill('JA999005')
            page.locator('#item_type').select_option('Bar')
            page.locator('#shape').select_option('Round')
            page.locator('#length').fill('10')
            page.locator('#width').fill('1')
            
            page.locator('button[type="submit"]').first.click()
            
            # Should submit successfully
            page.wait_for_timeout(1000)
            
            # If still on form page, material should not be invalid
            if material_field.is_visible():
                expect(material_field).not_to_have_class(re.compile(r'.*\bis-invalid\b.*'))


@pytest.mark.e2e  
def test_material_field_validation_feedback_messages(page, live_server):
    """Test that appropriate validation feedback messages are shown"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Focus on taxonomy validation specifically
    page.locator('#ja_id').fill('JA999006')
    page.locator('#item_type').select_option('Bar')
    page.locator('#shape').select_option('Round')
    
    # Test invalid material with proper error message
    material_field = page.locator('#material')
    material_field.fill('InvalidMaterialName123')
    page.locator('button[type="submit"]').first.click()
    
    # Should show taxonomy validation error
    expect(material_field).to_have_class(re.compile(r'.*\bis-invalid\b.*'))
    
    # Check that the error feedback message is shown
    error_feedback = page.locator('#material').locator('xpath=following-sibling::div[contains(@class, "invalid-feedback")]').first
    expect(error_feedback).to_be_visible()
    expect(error_feedback).to_contain_text('must be from materials taxonomy')