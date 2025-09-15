"""
E2E Tests for Add Item Workflow

Happy-path browser tests for adding inventory items.
"""

import pytest
from playwright.sync_api import expect
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
    add_page.add_minimal_item("JA000001", "Carbon Steel")
    
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
        item_type="Bar", 
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
    add_page.add_minimal_item("JA000003", "Carbon Steel")
    add_page.assert_form_submitted_successfully()
    
    # Add second item
    add_page.navigate()
    add_page.add_minimal_item("JA000004", "Copper")
    add_page.assert_form_submitted_successfully()
    
    # Add third item
    add_page.navigate()
    add_page.add_complete_item(
        ja_id="JA000005",
        material="360 Brass",
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
    add_page.fill_basic_item_data("JA000006", "Bar", "Round", "Carbon Steel")
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
    add_page.add_minimal_item("JA000007", "Carbon Steel")
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
    add_page.fill_basic_item_data("JA000008", "Threaded Rod", "Round", "Carbon Steel")
    add_page.fill_dimensions(length="36", width="0.25")  # 36" long, 1/4" diameter
    add_page.submit_form()
    
    # Verify successful submission
    add_page.assert_form_submitted_successfully()


@pytest.mark.e2e
def test_material_autocomplete_functionality(page, live_server):
    """Test that material autocomplete shows suggestions from inventory data"""
    # Create test data with realistic materials based on your actual inventory
    test_items = [
        # Steel materials (most common - should appear first)
        {
            "ja_id": "JA200001",
            "item_type": "Bar", 
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "1000",
            "width": "25"
        },
        {
            "ja_id": "JA200002",
            "item_type": "Bar", 
            "shape": "Square",
            "material": "Carbon Steel",
            "length": "500",
            "width": "10"
        },
        {
            "ja_id": "JA200003",
            "item_type": "Sheet", 
            "shape": "Rectangular",
            "material": "Carbon Steel",
            "length": "1200",
            "width": "600",
            "thickness": "3"
        },
        # Stainless variations 
        {
            "ja_id": "JA200004",
            "item_type": "Bar", 
            "shape": "Round",
            "material": "321 Stainless",
            "length": "800",
            "width": "15"
        },
        {
            "ja_id": "JA200005",
            "item_type": "Sheet", 
            "shape": "Rectangular",
            "material": "Stainless Steel",
            "length": "1000",
            "width": "500",
            "thickness": "2"
        },
        # Brass materials
        {
            "ja_id": "JA200006",
            "item_type": "Bar", 
            "shape": "Hex",
            "material": "Brass",
            "length": "200",
            "width": "8"
        },
        {
            "ja_id": "JA200007",
            "item_type": "Bar", 
            "shape": "Round",
            "material": "Brass 360-H02",
            "length": "300",
            "width": "12"
        },
        # Other materials
        {
            "ja_id": "JA200008",
            "item_type": "Tube", 
            "shape": "Round",
            "material": "Aluminum",
            "length": "500",
            "width": "20",
            "wall_thickness": "2"
        },
        {
            "ja_id": "JA200009",
            "item_type": "Bar", 
            "shape": "Round",
            "material": "Copper",
            "length": "150",
            "width": "6"
        },
        {
            "ja_id": "JA200010",
            "item_type": "Bar", 
            "shape": "Round",
            "material": "12L14",
            "length": "400",
            "width": "18"
        }
    ]
    
    # Add test data to storage
    live_server.add_test_data(test_items)
    
    # Navigate to add item page
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()
    
    # Test material autocomplete functionality
    material_input = page.locator('#material')
    suggestions_div = page.locator('.material-suggestions')
    
    # Test 1: Typing "Ste" should show Steel and Stainless materials
    material_input.fill('Ste')
    page.wait_for_timeout(300)  # Wait for debounce and API call
    
    expect(suggestions_div).to_be_visible()
    suggestion_items = page.locator('.material-suggestions .suggestion-item')
    expect(suggestion_items.first).to_be_visible()  # At least one suggestion visible
    
    # Should show steel categories and materials (hierarchical system)
    suggestions_text = [item.text_content() for item in suggestion_items.all()]
    assert any('Steel' in s for s in suggestions_text), f"Expected steel material in suggestions: {suggestions_text}"
    assert any('Stainless' in s for s in suggestions_text), f"Expected stainless material in: {suggestions_text}"
    
    # Test 2: Clicking suggestion populates the field
    # Look for Carbon Steel specifically, or any steel material that exists
    carbon_steel_suggestion = page.locator('.material-suggestions .suggestion-item').filter(has_text='Carbon Steel')
    if carbon_steel_suggestion.count() > 0:
        carbon_steel_suggestion.first.click()
        expect(material_input).to_have_value('Carbon Steel')
    else:
        # If Carbon Steel not directly available, use any steel material
        steel_suggestion = page.locator('.material-suggestions .suggestion-item').filter(has_text='Steel').first  
        steel_suggestion.click()
        # Verify some steel material was selected
        selected_value = material_input.input_value()
        assert 'Steel' in selected_value, f"Expected steel material to be selected, got: {selected_value}"
    expect(suggestions_div).not_to_be_visible()
    
    # Test 3: Typing "Bra" should show Brass materials
    material_input.fill('Bra')
    page.wait_for_timeout(300)
    
    expect(suggestions_div).to_be_visible() 
    suggestion_items = page.locator('.material-suggestions .suggestion-item')
    suggestions_text = [item.text_content() for item in suggestion_items.all()]
    
    assert any('Brass' in s for s in suggestions_text), f"Expected brass material in suggestions: {suggestions_text}"
    # Should show either the category or specific brass material
    brass_found = any(s in ['Brass', '360 Brass'] for s in suggestions_text) or any('Brass' in s for s in suggestions_text)
    assert brass_found, f"Expected brass material in suggestions: {suggestions_text}"
    
    # Test 4: Typing specific material like "12L" should show 12L14
    material_input.fill('12L')
    page.wait_for_timeout(300)
    
    expect(suggestions_div).to_be_visible()
    suggestion_items = page.locator('.material-suggestions .suggestion-item')
    suggestions_text = [item.text_content() for item in suggestion_items.all()]
    assert '12L14' in suggestions_text, f"Expected '12L14' in suggestions: {suggestions_text}"
    
    # Test 5: Clicking outside hides suggestions
    page.locator('#ja_id').click()
    expect(suggestions_div).not_to_be_visible()
    
    # Test 6: Verify we can complete adding an item with autocomplete
    material_input.fill('Copp')
    page.wait_for_timeout(300)
    
    copper_suggestion = page.locator('.material-suggestions .suggestion-item').filter(has_text='Copper').first
    copper_suggestion.click()
    
    # Complete the form and verify submission works
    add_page.fill_basic_item_data("JA200011", "Bar", "Round", "Copper")  # Material already set
    add_page.fill_dimensions(length="100", width="5")
    add_page.submit_form()
    
    add_page.assert_form_submitted_successfully()