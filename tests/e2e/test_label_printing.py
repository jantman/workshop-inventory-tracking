"""
E2E Tests for Label Printing Functionality

Tests the label printing feature from Add Item and Edit Item views,
including modal interactions, test mode verification, and error handling.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.inventory_list_page import InventoryListPage
import json


@pytest.mark.e2e
def test_label_printing_modal_add_item_form(page, live_server):
    """Test label printing modal from Add Item form"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Clear any auto-populated JA ID first
    ja_id_input = page.locator("#ja_id")
    ja_id_input.fill("")
    
    # Verify print button is disabled when no JA ID
    print_btn = page.locator("#print-label-btn")
    expect(print_btn).to_be_disabled()
    
    # Enter valid JA ID
    ja_id_input.fill("JA123456")
    
    # Print button should now be enabled
    expect(print_btn).to_be_enabled()
    
    # Click print button to open modal
    print_btn.click()
    
    # Wait for modal to appear and fully load
    modal = page.locator("#label-printing-modal")
    expect(modal).to_be_visible()
    
    # Wait a bit for JavaScript to initialize the modal
    page.wait_for_timeout(1000)
    
    # Verify modal title includes JA ID
    modal_title = page.locator("#label-printing-modal-label")
    expect(modal_title).to_contain_text("Print Label for JA123456")
    
    # Verify label type dropdown is populated
    label_select = page.locator("#label-type-select")
    expect(label_select).to_be_visible()
    
    # Wait for options to load via API call
    page.wait_for_timeout(2000)
    
    # Verify options are loaded (should have more than just placeholder)
    option_count = label_select.locator("option").count()
    assert option_count > 1, "Label type dropdown should have options loaded"
    
    # Verify expected label types are present
    expected_types = ['Sato 1x2', 'Sato 1x2 Flag', 'Sato 2x4', 'Sato 2x4 Flag', 'Sato 4x6', 'Sato 4x6 Flag']
    for label_type in expected_types:
        option = label_select.locator(f"option[value='{label_type}']")
        expect(option).to_have_count(1)  # Option should exist
    
    # Select a label type
    label_select.select_option("Sato 1x2")
    
    # Click print button in modal
    modal_print_btn = page.locator("#modal-print-label-btn")
    modal_print_btn.click()
    
    # Wait for print request to complete
    page.wait_for_timeout(2000)
    
    # Verify success message appears (in test mode, should not actually print)
    success_alert = page.locator("#label-print-alerts .alert-success")
    expect(success_alert).to_be_visible()
    expect(success_alert).to_contain_text("Label printed successfully")
    
    # Modal should auto-close after success
    page.wait_for_timeout(2500)
    expect(modal).not_to_be_visible()


@pytest.mark.e2e
def test_label_type_persistence_add_item_form(page, live_server):
    """Test that label type selection persists on Add Item form"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Clear auto-populated JA ID and enter test JA ID
    page.locator("#ja_id").fill("")
    page.locator("#ja_id").fill("JA123456")
    page.locator("#print-label-btn").click()
    
    # Wait for modal to load
    page.wait_for_timeout(2000)
    
    # Select a label type
    page.locator("#label-type-select").select_option("Sato 2x4")
    
    # Close modal without printing
    page.locator("#label-printing-modal .btn-secondary").click()
    
    # Open modal again
    page.locator("#print-label-btn").click()
    
    # Verify the label type is still selected
    selected_value = page.locator("#label-type-select").input_value()
    assert selected_value == "Sato 2x4", "Label type selection should persist on Add Item form"
    
    # Close modal
    page.locator("#label-printing-modal .btn-close").click()


@pytest.mark.e2e
def test_label_printing_edit_item_form(page, live_server):
    """Test label printing from Edit Item form"""
    # First create an item to edit
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA654321", "Aluminum")
    
    # Navigate to inventory list and edit the item
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    
    # Wait for items to load
    list_page.wait_for_items_loaded()
    
    # Find and click the edit link for our item
    edit_link = page.locator(f'a[href="/inventory/edit/JA654321"]')
    expect(edit_link).to_be_visible()
    edit_link.click()
    
    # Should now be on edit page
    expect(page).to_have_url(f'{live_server.url}/inventory/edit/JA654321')
    
    # Verify print button is enabled (since JA ID already exists)
    print_btn = page.locator("#print-label-btn")
    expect(print_btn).to_be_enabled()
    
    # Click print button
    print_btn.click()

    # Wait for modal to be created and shown
    page.wait_for_timeout(3000)

    # Verify modal opens with correct JA ID
    modal = page.locator("#label-printing-modal")
    expect(modal).to_be_visible()
    expect(page.locator("#label-ja-id-display")).to_contain_text("JA654321")
    
    # Wait for modal to load
    page.wait_for_timeout(2000)
    
    # Select label type and print
    page.locator("#label-type-select").select_option("Sato 4x6 Flag")
    page.locator("#modal-print-label-btn").click()
    
    # Verify success
    page.wait_for_timeout(2000)
    success_alert = page.locator("#label-print-alerts .alert-success")
    expect(success_alert).to_be_visible()


@pytest.mark.e2e
def test_label_printing_invalid_ja_id_validation(page, live_server):
    """Test validation for invalid JA ID formats"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    invalid_ja_ids = ["", "JA123", "JA1234567", "AB123456", "ja123456", "JA12345A"]
    
    for invalid_ja_id in invalid_ja_ids:
        # Clear and fill with invalid JA ID
        ja_id_input = page.locator("#ja_id")
        ja_id_input.fill("")
        ja_id_input.fill(invalid_ja_id)
        
        # Print button should be disabled
        print_btn = page.locator("#print-label-btn")
        expect(print_btn).to_be_disabled()


@pytest.mark.e2e
def test_label_printing_modal_validation(page, live_server):
    """Test modal validation for required fields"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Clear auto-populated JA ID and enter valid JA ID
    page.locator("#ja_id").fill("")
    page.locator("#ja_id").fill("JA999999")
    page.locator("#print-label-btn").click()
    
    # Wait for modal to load
    page.wait_for_timeout(2000)
    
    # Try to print without selecting label type
    modal_print_btn = page.locator("#modal-print-label-btn")
    modal_print_btn.click()
    
    # Should show error message
    error_alert = page.locator("#label-print-alerts .alert-danger")
    expect(error_alert).to_be_visible()
    expect(error_alert).to_contain_text("Please select a label type")
    
    # Modal should remain open
    modal = page.locator("#label-printing-modal")
    expect(modal).to_be_visible()


@pytest.mark.e2e
def test_label_printing_test_mode_verification(page, live_server):
    """Test that printing is short-circuited in test mode"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Set up network request monitoring to verify API call
    api_requests = []
    
    def handle_request(request):
        if "/api/labels/print" in request.url:
            api_requests.append(request)
    
    page.on("request", handle_request)
    
    # Print a label
    page.locator("#ja_id").fill("")
    page.locator("#ja_id").fill("JA888888")
    page.locator("#print-label-btn").click()
    
    # Wait for modal to load
    page.wait_for_timeout(2000)
    
    page.locator("#label-type-select").select_option("Sato 1x2")
    page.locator("#modal-print-label-btn").click()
    
    # Wait for request to complete
    page.wait_for_timeout(2000)
    
    # Verify API was called
    assert len(api_requests) > 0, "Print API should have been called"
    
    # Verify success message (indicates test mode short-circuit worked)
    success_alert = page.locator("#label-print-alerts .alert-success")
    expect(success_alert).to_be_visible()
    expect(success_alert).to_contain_text("Label printed successfully")


@pytest.mark.e2e 
def test_label_printing_modal_close_behaviors(page, live_server):
    """Test different ways to close the modal"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Clear auto-populated JA ID and enter test JA ID
    page.locator("#ja_id").fill("")
    page.locator("#ja_id").fill("JA777777")
    
    # Test close button (X)
    page.locator("#print-label-btn").click()
    modal = page.locator("#label-printing-modal")
    expect(modal).to_be_visible()
    page.wait_for_timeout(1000)  # Wait for modal to fully load
    
    page.locator("#label-printing-modal .btn-close").click()
    page.wait_for_timeout(500)  # Wait for close animation
    expect(modal).not_to_be_visible()
    
    # Test cancel button
    page.locator("#print-label-btn").click()
    expect(modal).to_be_visible()
    page.wait_for_timeout(1000)  # Wait for modal to fully load
    
    page.locator("#label-printing-modal .btn-secondary").click()
    page.wait_for_timeout(500)  # Wait for close animation
    expect(modal).not_to_be_visible()
    
    # Test ESC key
    page.locator("#print-label-btn").click()
    expect(modal).to_be_visible()
    page.wait_for_timeout(1000)  # Wait for modal to fully load
    
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)  # Wait for close animation
    expect(modal).not_to_be_visible()


@pytest.mark.e2e
def test_label_printing_api_error_handling(page, live_server):
    """Test error handling when API requests fail"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Mock API to return error
    page.route("**/api/labels/print", lambda route: route.fulfill(
        status=500,
        content_type="application/json",
        body=json.dumps({"success": False, "error": "Printer offline"})
    ))
    
    # Try to print a label
    page.locator("#ja_id").fill("")
    page.locator("#ja_id").fill("JA555555")
    page.locator("#print-label-btn").click()
    
    # Wait for modal to load
    page.wait_for_timeout(2000)
    
    page.locator("#label-type-select").select_option("Sato 1x2")
    page.locator("#modal-print-label-btn").click()
    
    # Wait for error handling
    page.wait_for_timeout(2000)
    
    # Verify error message is displayed
    error_alert = page.locator("#label-print-alerts .alert-danger")
    expect(error_alert).to_be_visible()
    expect(error_alert).to_contain_text("Failed to print label")
    
    # Modal should remain open for user to retry
    modal = page.locator("#label-printing-modal")
    expect(modal).to_be_visible()


@pytest.mark.e2e
def test_label_types_api_loading(page, live_server):
    """Test that label types are loaded from API"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    # Monitor API requests
    api_requests = []
    
    def handle_request(request):
        if "/api/labels/types" in request.url:
            api_requests.append(request)
    
    page.on("request", handle_request)
    
    # Open modal which should trigger label types loading
    page.locator("#ja_id").fill("")
    page.locator("#ja_id").fill("JA333333")
    page.locator("#print-label-btn").click()
    
    # Wait for API call
    page.wait_for_timeout(1000)
    
    # Verify API was called
    assert len(api_requests) > 0, "Label types API should have been called"
    
    # Verify dropdown is populated
    label_select = page.locator("#label-type-select")
    option_count = label_select.locator("option").count()
    assert option_count > 1, "Label type dropdown should be populated from API"


@pytest.mark.e2e
def test_label_printing_different_label_types(page, live_server):
    """Test printing with different label types"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    
    page.locator("#ja_id").fill("")
    page.locator("#ja_id").fill("JA111111")
    
    label_types_to_test = ["Sato 1x2", "Sato 1x2 Flag", "Sato 2x4", "Sato 4x6 Flag"]
    
    for label_type in label_types_to_test:
        # Open modal
        page.locator("#print-label-btn").click()
        
        # Wait for modal to load
        page.wait_for_timeout(2000)
        
        # Select label type and print
        page.locator("#label-type-select").select_option(label_type)
        page.locator("#modal-print-label-btn").click()
        
        # Wait for completion
        page.wait_for_timeout(2000)
        
        # Verify success (modal should close)
        modal = page.locator("#label-printing-modal")
        expect(modal).not_to_be_visible()
        
        # Small delay between tests
        page.wait_for_timeout(500)