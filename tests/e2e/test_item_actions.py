"""
E2E Tests for Item Actions - View and Edit

Tests for the view (modal) and edit functionality of inventory items.
"""

import pytest
from tests.e2e.pages.inventory_list_page import InventoryListPage
from tests.e2e.pages.add_item_page import AddItemPage
from playwright.sync_api import expect


@pytest.mark.e2e
def test_view_item_modal_workflow(page, live_server):
    """Test viewing item details in modal"""
    # First add a test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    test_item = {
        "ja_id": "JA102001",
        "item_type": "Bar",
        "shape": "Round",
        "material": "Stainless Steel",
        "length": "12.5",
        "width": "0.5",
        "location": "Workshop A",
        "sub_location": "Shelf 1",
        "purchase_price": "15.99",
        "vendor": "McMaster-Carr",
        "notes": "High quality stainless rod"
    }

    # Fill the form with test data
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])

    # Fill additional fields
    page.fill("#sub_location", test_item["sub_location"])
    page.fill("#purchase_price", test_item["purchase_price"])
    page.fill("#vendor", test_item["vendor"])
    
    # Test precision checkbox - check it for this test item
    precision_checkbox = page.locator('#precision')
    expect(precision_checkbox).to_be_visible()
    expect(precision_checkbox).not_to_be_checked()  # Initially unchecked
    precision_checkbox.check()
    expect(precision_checkbox).to_be_checked()  # Verify it got checked
    
    add_page.submit_form()
    
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Wait for items to load
    list_page.wait_for_items_loaded()
    
    # Find the view button for our item
    view_button = page.locator(f'button[onclick*="showItemDetails(\'JA102001\')"]')
    expect(view_button).to_be_visible()
    
    # Click the view button
    view_button.click()
    
    # Wait for modal to appear
    modal = page.locator('#item-details-modal')
    expect(modal).to_be_visible()
    
    # Wait for modal content to be loaded (it should contain the JA ID)
    modal_body = page.locator('#item-details-modal .modal-body')
    expect(modal_body).to_contain_text('JA102001')  # Wait for content to be loaded
    
    # Verify modal title
    modal_title = page.locator('#item-details-modal-label')
    expect(modal_title).to_contain_text('Item Details')
    
    # Verify key item details are displayed in modal
    expect(modal_body).to_contain_text('Bar')
    expect(modal_body).to_contain_text('Round')
    expect(modal_body).to_contain_text('Stainless Steel')
    expect(modal_body).to_contain_text('12.5"')
    expect(modal_body).to_contain_text('0.5"')
    expect(modal_body).to_contain_text('Workshop A')
    expect(modal_body).to_contain_text('Shelf 1')
    expect(modal_body).to_contain_text('$15.99')
    expect(modal_body).to_contain_text('McMaster-Carr')
    expect(modal_body).to_contain_text('High quality stainless rod')
    
    # Verify precision field shows 'Yes' (since we checked the checkbox)
    expect(modal_body).to_contain_text('Precision')
    expect(modal_body).to_contain_text('Yes')
    
    # Verify edit button in modal footer
    edit_link = page.locator('#edit-item-link')
    expect(edit_link).to_be_visible()
    expect(edit_link).to_have_attribute('href', '/inventory/edit/JA102001')
    
    # Close modal
    close_button = page.locator('#item-details-modal .btn-close')
    close_button.click()
    
    # Verify modal is closed
    expect(modal).not_to_be_visible()


@pytest.mark.e2e
def test_edit_item_workflow(page, live_server):
    """Test editing an existing item"""
    # First add a test item to edit
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    original_item = {
        "ja_id": "JA102002", 
        "item_type": "Plate",
        "shape": "Rectangular",
        "material": "Aluminum",
        "length": "10",
        "width": "5", 
        "thickness": "0.25",
        "location": "Storage B",
        "notes": "Original aluminum plate"
    }
    
    # Fill and submit the original item
    add_page.fill_basic_item_data(original_item["ja_id"], original_item["item_type"], 
                                 original_item["shape"], original_item["material"])
    add_page.fill_dimensions(length=original_item["length"], width=original_item["width"])
    page.fill("#thickness", original_item["thickness"])
    add_page.fill_location_and_notes(location=original_item["location"], notes=original_item["notes"])
    add_page.submit_form()
    
    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Wait for items to load  
    list_page.wait_for_items_loaded()
    
    # Find and click the edit button for our item
    edit_link = page.locator(f'a[href="/inventory/edit/JA102002"]')
    expect(edit_link).to_be_visible()
    edit_link.click()
    
    # Verify we're on the edit page
    expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA102002')
    
    # Verify page title and heading
    expect(page).to_have_title('Edit JA102002 - Workshop Inventory')
    heading = page.locator('h2')
    expect(heading).to_contain_text('Edit Inventory Item: JA102002')
    
    # Verify form is pre-populated with existing data
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).to_have_value('JA102002')
    
    item_type_field = page.locator('#item_type') 
    expect(item_type_field).to_have_value('Plate')
    
    shape_field = page.locator('#shape')
    expect(shape_field).to_have_value('Rectangular')
    
    material_field = page.locator('#material')
    expect(material_field).to_have_value('Aluminum')
    
    length_field = page.locator('#length')
    expect(length_field).to_have_value('10')
    
    width_field = page.locator('#width')
    expect(width_field).to_have_value('5')
    
    thickness_field = page.locator('#thickness') 
    expect(thickness_field).to_have_value('0.25')
    
    location_field = page.locator('#location')
    expect(location_field).to_have_value('Storage B')
    
    notes_field = page.locator('#notes')
    expect(notes_field).to_have_value('Original aluminum plate')
    
    # Check initial precision checkbox state (should be unchecked as default)
    precision_checkbox = page.locator('#precision')
    expect(precision_checkbox).to_be_visible()
    expect(precision_checkbox).not_to_be_checked()
    
    # Make some changes to the item
    material_field.fill('6000 Series')
    width_field.fill('6')
    location_field.fill('Workshop C')
    notes_field.fill('Updated aluminum plate - now 6000 series alloy')
    
    # Check the precision checkbox as part of the edit
    precision_checkbox.check()
    expect(precision_checkbox).to_be_checked()
    
    # Submit the changes
    submit_button = page.locator('button[type="submit"]')
    submit_button.click()
    
    # Verify redirect to inventory list
    expect(page).to_have_url(f'{live_server.url}/inventory')
    
    # Verify success message
    success_alert = page.locator('.alert-success')
    expect(success_alert).to_contain_text('Item updated successfully!')
    
    # Verify the changes are reflected in the list
    list_page.wait_for_items_loaded()
    
    # Check that the updated item appears in the list with new values
    items = list_page.get_inventory_items()
    updated_item = None
    for item in items:
        if item['ja_id'] == 'JA102002':
            updated_item = item
            break
    
    assert updated_item is not None, "Updated item not found in list"
    assert '6000 Series' in updated_item['material']
    
    # Verify changes by viewing the item details
    view_button = page.locator(f'button[onclick*="showItemDetails(\'JA102002\')"]')
    view_button.click()
    
    # Wait for modal content to be loaded
    modal_body = page.locator('#item-details-modal .modal-body')
    expect(modal_body).to_contain_text('JA102002')  # Wait for content to load
    expect(modal_body).to_contain_text('6000 Series')
    expect(modal_body).to_contain_text('6"')  # updated width
    expect(modal_body).to_contain_text('Workshop C')
    expect(modal_body).to_contain_text('Updated aluminum plate - now 6000 series alloy')
    
    # Verify precision field shows 'Yes' after editing
    expect(modal_body).to_contain_text('Precision')
    expect(modal_body).to_contain_text('Yes')


@pytest.mark.e2e
def test_edit_nonexistent_item_workflow(page, live_server):
    """Test editing a nonexistent item shows error"""
    # Try to navigate directly to edit a nonexistent item
    page.goto(f'{live_server.url}/inventory/edit/JA999999')
    
    # Should redirect to inventory list with error message
    expect(page).to_have_url(f'{live_server.url}/inventory')
    
    # Verify error message (be specific to avoid multiple matches)
    error_alert = page.locator('.alert-danger.alert-dismissible')
    expect(error_alert).to_contain_text('Item JA999999 not found')


@pytest.mark.e2e
def test_edit_form_loads_without_validation_errors(page, live_server):
    """Test that edit form loads cleanly without premature validation errors"""
    # First add a test item to edit
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    test_item = {
        "ja_id": "JA102003", 
        "item_type": "Bar",
        "shape": "Round",
        "material": "Carbon Steel",
        "length": "12",
        "width": "1", 
        "location": "Workshop",
        "notes": "Test item for validation check"
    }
    
    # Fill and submit the test item
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], 
                                 test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"], width=test_item["width"])
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])
    add_page.submit_form()
    
    # Navigate to edit the item
    page.goto(f'{live_server.url}/inventory/edit/JA102003')
    
    # Wait for page to fully load
    page.wait_for_load_state('domcontentloaded')
    page.wait_for_timeout(500)  # Small delay for JavaScript to initialize
    
    # Verify no validation error classes are present on page load
    invalid_fields = page.locator('.is-invalid')
    expect(invalid_fields).to_have_count(0)
    
    # Verify no visible invalid-feedback messages
    visible_errors = page.locator('.invalid-feedback:visible')
    expect(visible_errors).to_have_count(0)
    
    # Verify form fields are properly populated (no red borders due to empty required fields)
    ja_id_field = page.locator('#ja_id')
    expect(ja_id_field).to_have_value('JA102003')
    expect(ja_id_field).not_to_have_class('is-invalid')
    
    item_type_field = page.locator('#item_type')
    expect(item_type_field).to_have_value('Bar')
    expect(item_type_field).not_to_have_class('is-invalid')
    
    shape_field = page.locator('#shape')
    expect(shape_field).to_have_value('Round')
    expect(shape_field).not_to_have_class('is-invalid')
    
    material_field = page.locator('#material')
    expect(material_field).to_have_value('Carbon Steel')
    expect(material_field).not_to_have_class('is-invalid')
    
    length_field = page.locator('#length')
    expect(length_field).to_have_value('12')  # normalized precision
    expect(length_field).not_to_have_class('is-invalid')
    
    width_field = page.locator('#width')
    expect(width_field).to_have_value('1')  # normalized precision
    expect(width_field).not_to_have_class('is-invalid')


@pytest.mark.e2e 
def test_view_nonexistent_item_workflow(page, live_server):
    """Test viewing a nonexistent item shows error in modal"""
    # Navigate to inventory list first
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Manually call showItemDetails with nonexistent ID
    page.evaluate('showItemDetails("JA999999")')
    
    # Wait for modal to appear
    modal = page.locator('#item-details-modal')
    expect(modal).to_be_visible()
    
    # Verify error message in modal
    error_alert = page.locator('#item-details-modal .alert-danger')
    expect(error_alert).to_contain_text('Item JA999999 not found')


@pytest.mark.e2e
def test_view_threaded_item_modal_workflow(page, live_server):
    """Test viewing threaded item details in modal - validates issue #14"""
    # First add a threaded test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    test_item = {
        "ja_id": "JA102004",
        "item_type": "Threaded Rod",
        "shape": "Round",
        "material": "Stainless Steel",
        "length": "12.5",
        "location": "Workshop A",
        "sub_location": "Shelf 1",
        "purchase_price": "15.99",
        "vendor": "McMaster-Carr",
        "notes": "High quality stainless threaded rod",
        "thread_series": "UNC",
        "thread_handedness": "RH",
        "thread_size": "1/2-13"
    }

    # Fill the form with test data
    add_page.fill_basic_item_data(test_item["ja_id"], test_item["item_type"], test_item["shape"], test_item["material"])
    add_page.fill_dimensions(length=test_item["length"])
    add_page.fill_thread_information(
        thread_series=test_item["thread_series"],
        thread_size=test_item["thread_size"],
        thread_handedness=test_item["thread_handedness"]
    )
    add_page.fill_location_and_notes(location=test_item["location"], notes=test_item["notes"])

    # Fill additional fields
    page.fill("#sub_location", test_item["sub_location"])
    page.fill("#purchase_price", test_item["purchase_price"])
    page.fill("#vendor", test_item["vendor"])

    add_page.submit_form()

    # Navigate to inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()

    # Wait for items to load
    list_page.wait_for_items_loaded()

    # Find the view button for our threaded item
    view_button = page.locator(f'button[onclick*="showItemDetails(\'JA102004\')"]')
    expect(view_button).to_be_visible()

    # Click the view button
    view_button.click()

    # Wait for modal to appear
    modal = page.locator('#item-details-modal')
    expect(modal).to_be_visible()

    # Verify modal title
    modal_title = page.locator('#item-details-modal-label')
    expect(modal_title).to_contain_text('JA102004 Details')

    # Verify basic item details are displayed in modal
    modal_body = page.locator('#item-details-modal .modal-body')
    expect(modal_body).to_contain_text('JA102004')
    expect(modal_body).to_contain_text('Threaded Rod')
    expect(modal_body).to_contain_text('Round')
    expect(modal_body).to_contain_text('Stainless Steel')
    expect(modal_body).to_contain_text('12.5"')
    expect(modal_body).to_contain_text('Workshop A')
    expect(modal_body).to_contain_text('Shelf 1')
    expect(modal_body).to_contain_text('$15.99')
    expect(modal_body).to_contain_text('McMaster-Carr')
    expect(modal_body).to_contain_text('High quality stainless threaded rod')

    # Verify thread information is displayed in modal (issue #14)
    expect(modal_body).to_contain_text('Threading')  # Thread section header
    expect(modal_body).to_contain_text('Size:')      # Thread size label
    expect(modal_body).to_contain_text('1/2-13')     # Thread size value
    expect(modal_body).to_contain_text('Series:')    # Thread series label
    expect(modal_body).to_contain_text('UNC')        # Thread series value
    expect(modal_body).to_contain_text('Handedness:') # Thread handedness label
    expect(modal_body).to_contain_text('RH')         # Thread handedness value