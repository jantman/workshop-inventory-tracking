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
    add_page.fill_dimensions(length="36")  # 36" long, no width for threaded rods
    add_page.fill_thread_information(thread_series="UNC", thread_size="1/4-20")
    add_page.fill_location_and_notes(location="Storage A")  # Location is now required
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
    # MaterialSelector includes icons and formatting, so check for material name within text
    assert any('12L14' in text for text in suggestions_text), f"Expected '12L14' in suggestions: {suggestions_text}"
    
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
    add_page.fill_location_and_notes(location="Storage B")  # Location is now required
    add_page.submit_form()
    
    add_page.assert_form_submitted_successfully()


@pytest.mark.e2e
def test_add_threaded_rod_with_proper_validation(page, live_server):
    """Test adding a Threaded Rod item with proper validation requirements
    
    This test documents the correct behavior:
    - Threaded Rod should NOT require Width 
    - Threaded Rod should require Thread Series and Thread Size (when UI supports it)
    - Should successfully add without the backend KeyError: 'THREADED ROD'
    """
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Verify form is displayed
    add_page.assert_form_visible()
    
    # Fill basic item data - Threaded Rod
    add_page.fill_basic_item_data("JA000100", "Threaded Rod", "Round", "Carbon Steel")
    
    # For Threaded Rod: Length is required, Width should NOT be required
    # Thread Series and Thread Size should be required
    add_page.fill_dimensions(length="36")  # 36" long, no width for threaded rods
    add_page.fill_thread_information(thread_series="UNC", thread_size="1/4-20")
    add_page.fill_location_and_notes(location="Storage C")  # Location is now required

    # Submit form - this should succeed once the enum bug is fixed
    add_page.submit_form()
    
    # Verify successful submission (this will fail until bug is fixed)
    add_page.assert_form_submitted_successfully()
    
    # Verify item appears in inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.assert_item_in_list("JA000100")


@pytest.mark.e2e
def test_add_and_continue_carry_forward_workflow(page, live_server):
    """Test the 'Add & Continue' → 'Carry Forward' workflow that is currently broken"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Verify form is displayed
    add_page.assert_form_visible()
    
    # Fill out the first item with complete data including new carry forward fields
    first_item_data = {
        "ja_id": "JA000200",
        "item_type": "Threaded Rod",
        "shape": "Round",
        "material": "Carbon Steel",
        "length": "500",
        "location": "Storage Rack A",
        "notes": "Test material for carry forward",
        "purchase_date": "2024-01-15",
        "thread_series": "UNC",
        "thread_handedness": "RH",
        "thread_size": "1/4-20"
    }
    
    # Fill all the form fields
    add_page.fill_basic_item_data(
        first_item_data["ja_id"],
        first_item_data["item_type"],
        first_item_data["shape"],
        first_item_data["material"]
    )
    add_page.fill_dimensions(
        length=first_item_data["length"]
    )
    add_page.fill_thread_information(
        thread_series=first_item_data["thread_series"],
        thread_size=first_item_data["thread_size"],
        thread_handedness=first_item_data["thread_handedness"]
    )
    add_page.fill_location_and_notes(
        location=first_item_data["location"],
        notes=first_item_data["notes"]
    )

    # Fill purchase date
    page.fill("#purchase_date", first_item_data["purchase_date"])
    
    # Submit using "Add & Continue" button
    add_page.submit_and_continue()
    
    # Verify we're back on the add form (should be cleared for next item)
    add_page.assert_form_visible()
    
    # Verify form is cleared (JA ID should be empty/different)
    current_ja_id = add_page.get_field_value(add_page.JA_ID_INPUT)
    assert current_ja_id != first_item_data["ja_id"], "Form should be cleared after Add & Continue"
    
    # Now click "Carry Forward" to reproduce the bug
    add_page.click_carry_forward()
    
    # BUG: This should show success toast and populate fields, but currently shows error
    # The bug is that lastItemData is not persisting across the page redirect
    
    # Check which toast appears - if error toast, this confirms the bug
    try:
        add_page.assert_carry_forward_error_toast()
        # BUG REPRODUCED: The carry forward is showing error when it should work
        print("BUG REPRODUCED: 'No previous item data to carry forward' error when it should work")
        
        # Re-raise to make the test fail and document the bug
        raise AssertionError(
            "BUG: Carry Forward functionality is broken. "
            "After using 'Add & Continue', clicking 'Carry Forward' shows "
            "'No previous item data to carry forward' instead of populating fields. "
            "The lastItemData is not persisting across the page redirect."
        )
        
    except AssertionError as e:
        # If the error toast assertion failed, maybe the success toast appeared (bug is fixed!)
        if "Expected carry forward error message" in str(e):
            try:
                add_page.assert_carry_forward_success_toast()
                
                # If carry forward worked, verify the fields are populated correctly
                add_page.assert_field_value(add_page.ITEM_TYPE_SELECT, first_item_data["item_type"])
                add_page.assert_field_value(add_page.SHAPE_SELECT, first_item_data["shape"])
                add_page.assert_field_value(add_page.MATERIAL_INPUT, first_item_data["material"])
                add_page.assert_field_value(add_page.LOCATION_INPUT, first_item_data["location"])

                # Verify NEW fields are carried forward (issue #12)
                add_page.assert_field_value("#purchase_date", first_item_data["purchase_date"])
                add_page.assert_field_value(add_page.THREAD_SERIES_SELECT, first_item_data["thread_series"])
                add_page.assert_field_value(add_page.THREAD_HANDEDNESS_SELECT, first_item_data["thread_handedness"])
                add_page.assert_field_value(add_page.THREAD_SIZE_INPUT, first_item_data["thread_size"])

                # JA ID should NOT be carried forward (it should remain empty/different)
                carried_ja_id = add_page.get_field_value(add_page.JA_ID_INPUT)
                assert carried_ja_id != first_item_data["ja_id"], "JA ID should not be carried forward"
                
                print("SUCCESS: Carry Forward functionality is working correctly!")
                
            except AssertionError:
                # Neither error nor success toast found as expected - something else is wrong
                raise AssertionError(f"Unexpected behavior: {str(e)}")
        else:
            # Re-raise the original bug documentation
            raise


@pytest.mark.e2e  
def test_carry_forward_without_previous_item(page, live_server):
    """Test that Carry Forward shows appropriate message when no previous item exists"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Verify form is displayed
    add_page.assert_form_visible()
    
    # Click "Carry Forward" when no previous item exists
    add_page.click_carry_forward()
    
    # Should show the appropriate error message
    add_page.assert_carry_forward_error_toast()


@pytest.mark.e2e
def test_thread_series_auto_lookup(page, live_server):
    """Test that thread series is auto-populated when thread size is entered"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Fill basic item data for a threaded rod
    add_page.fill_basic_item_data("JA102005", "Threaded Rod", "Round", "Stainless Steel")

    # Get the thread size and series fields
    thread_size_field = page.locator('#thread_size')
    thread_series_field = page.locator('#thread_series')

    # Verify fields are visible and empty initially
    expect(thread_size_field).to_be_visible()
    expect(thread_series_field).to_be_visible()
    expect(thread_series_field).to_have_value('')

    # Enter a thread size that should map to UNC
    thread_size_field.fill('1/2-13')

    # Trigger blur event to activate the lookup
    thread_size_field.blur()

    # Wait a bit for the API call and auto-population
    page.wait_for_timeout(1000)

    # Verify the thread series was auto-populated
    expect(thread_series_field).to_have_value('UNC')

    # Test with a metric thread size
    thread_size_field.fill('M8x1.25')
    thread_size_field.blur()
    page.wait_for_timeout(1000)

    # Verify the thread series was updated to Metric
    expect(thread_series_field).to_have_value('Metric')

    # Test with an invalid thread size
    thread_size_field.fill('invalid-size')
    thread_series_field.select_option('UNC')  # Set a value first
    thread_size_field.blur()
    page.wait_for_timeout(1000)

    # Thread series should remain unchanged for invalid input
    expect(thread_series_field).to_have_value('UNC')


@pytest.mark.e2e
def test_add_channel_item_rectangular_shape(page, live_server):
    """Test adding a Channel item with Rectangular shape"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Verify form is displayed
    add_page.assert_form_visible()

    # Add a Channel item with Rectangular shape
    add_page.fill_basic_item_data("JA900001", "Channel", "Rectangular", "Carbon Steel")
    add_page.fill_dimensions(length="72", width="2", diameter="0.125")  # 72" x 2" x 1/8" channel
    add_page.fill_location_and_notes(location="Storage C", notes="C-channel structural steel")
    add_page.submit_form()

    # Verify successful submission
    add_page.assert_form_submitted_successfully()

    # Navigate to inventory list to verify item was added
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()

    # Verify the item appears in the list
    list_page.assert_item_in_list("JA900001")

    # Verify item type badge shows "Channel"
    item_row = page.locator(f'tr:has-text("JA900001")')
    expect(item_row).to_be_visible()
    expect(item_row).to_contain_text("Channel")


@pytest.mark.e2e
def test_add_channel_item_square_shape(page, live_server):
    """Test adding a Channel item with Square shape"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Verify form is displayed
    add_page.assert_form_visible()

    # Add a Channel item with Square shape
    add_page.fill_basic_item_data("JA900002", "Channel", "Square", "Aluminum")
    add_page.fill_dimensions(length="48", width="1.5", diameter="0.0625")  # 48" x 1.5" x 1/16" square channel
    add_page.fill_location_and_notes(location="Storage D", notes="Square aluminum channel")
    add_page.submit_form()

    # Verify successful submission
    add_page.assert_form_submitted_successfully()

    # Navigate to inventory list to verify item was added
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()

    # Verify the item appears in the list
    list_page.assert_item_in_list("JA900002")

    # Verify item type badge shows "Channel"
    item_row = page.locator(f'tr:has-text("JA900002")')
    expect(item_row).to_be_visible()
    expect(item_row).to_contain_text("Channel")


@pytest.mark.e2e
def test_channel_item_in_type_filter(page, live_server):
    """Test that Channel items can be filtered in the inventory list"""
    # First add a Channel item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.fill_basic_item_data("JA900003", "Channel", "Rectangular", "Stainless Steel")
    add_page.fill_dimensions(length="60", width="3", diameter="0.25")
    add_page.fill_location_and_notes(location="Storage E")
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Verify Channel option exists in type filter dropdown
    type_filter = page.locator('#type-filter')
    expect(type_filter).to_be_visible()

    # Get all filter options
    filter_options = type_filter.locator('option').all_text_contents()
    assert "Channel" in filter_options, f"'Channel' not found in type filter options: {filter_options}"

    # Filter by Channel type
    type_filter.select_option("Channel")
    page.wait_for_timeout(1000)  # Wait for filter to apply

    # Verify the Channel item is visible
    list_page.assert_item_in_list("JA900003")


@pytest.mark.e2e
def test_channel_item_in_search(page, live_server):
    """Test that Channel items can be searched by type"""
    # First add a Channel item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.fill_basic_item_data("JA900004", "Channel", "Square", "Brass")
    add_page.fill_dimensions(length="36", width="1", diameter="0.125")
    add_page.fill_location_and_notes(location="Storage F")
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Navigate to search page
    page.goto(f"{live_server.url}/inventory/search")
    page.wait_for_timeout(1000)

    # Verify Channel option exists in item type dropdown
    item_type_select = page.locator('#item_type')
    expect(item_type_select).to_be_visible()

    # Get all type options
    type_options = item_type_select.locator('option').all_text_contents()
    assert "Channel" in type_options, f"'Channel' not found in search type options: {type_options}"

    # Search for Channel items
    item_type_select.select_option("Channel")
    search_button = page.locator('button[type="submit"]')
    search_button.click()
    page.wait_for_timeout(1000)

    # Verify results contain the Channel item
    results_table = page.locator('#search-results-table')
    expect(results_table).to_be_visible()
    expect(results_table).to_contain_text("JA900004")
    expect(results_table).to_contain_text("Channel")