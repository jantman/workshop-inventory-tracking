"""
E2E Tests for Bulk Label Printing from Inventory List

Tests the bulk label printing feature from the inventory list view,
including item selection, modal interactions, batch printing, progress
tracking, and error handling.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.inventory_list_page import InventoryListPage
import json


@pytest.mark.e2e
def test_bulk_label_printing_button_visibility(page, live_server):
    """Test that Print Labels button is visible in Options dropdown"""
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Open Options dropdown
    options_btn = page.locator('button:has-text("Options")')
    expect(options_btn).to_be_visible()
    options_btn.click()

    # Verify Print Labels option is present
    print_labels_btn = page.locator('#bulk-print-labels-btn')
    expect(print_labels_btn).to_be_visible()
    expect(print_labels_btn).to_contain_text('Print Labels')


@pytest.mark.e2e
def test_bulk_label_printing_select_and_open_modal(page, live_server):
    """Test selecting items and opening bulk label printing modal"""
    # Create test items
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA100001", "Aluminum")

    add_page.navigate()
    add_page.add_minimal_item("JA100002", "Steel")

    add_page.navigate()
    add_page.add_minimal_item("JA100003", "Brass")

    # Navigate to list and wait for items
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Select the first two items
    first_checkbox = page.locator('input.item-checkbox[data-ja-id="JA100001"]')
    second_checkbox = page.locator('input.item-checkbox[data-ja-id="JA100002"]')

    expect(first_checkbox).to_be_visible()
    expect(second_checkbox).to_be_visible()

    first_checkbox.check()
    second_checkbox.check()

    # Open Options dropdown and click Print Labels
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()

    # Verify modal opens
    modal = page.locator('#listBulkLabelPrintingModal')
    expect(modal).to_be_visible(timeout=5000)

    # Verify modal title
    modal_title = page.locator('#listBulkLabelPrintingModalLabel')
    expect(modal_title).to_contain_text('Print Labels')

    # Verify summary shows correct count
    summary = page.locator('#list-bulk-print-summary')
    expect(summary).to_contain_text('2 item(s)')

    # Verify selected items are listed
    items_list = page.locator('#list-bulk-label-items-list')
    expect(items_list).to_contain_text('JA100001')
    expect(items_list).to_contain_text('JA100002')


@pytest.mark.e2e
def test_bulk_label_printing_no_items_selected(page, live_server):
    """Test that clicking Print Labels with no items shows alert"""
    # Create a test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA200001", "Aluminum")

    # Navigate to list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Set up dialog handler
    page.on("dialog", lambda dialog: dialog.accept())

    # Try to open Print Labels without selecting items
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()

    # Modal should not open (alert should show instead)
    page.wait_for_timeout(1000)
    modal = page.locator('#listBulkLabelPrintingModal')
    expect(modal).not_to_be_visible()


@pytest.mark.e2e
def test_bulk_label_printing_label_types_loaded(page, live_server):
    """Test that label types are loaded from API"""
    # Create test items
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA300001", "Aluminum")

    # Navigate to list and select item
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    page.locator('input.item-checkbox[data-ja-id="JA300001"]').check()

    # Monitor API requests
    api_requests = []

    def handle_request(request):
        if "/api/labels/types" in request.url:
            api_requests.append(request)

    page.on("request", handle_request)

    # Open modal
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()

    # Wait for modal and API call
    page.wait_for_timeout(2000)

    # Verify API was called
    assert len(api_requests) > 0, "Label types API should have been called"

    # Verify label type dropdown is populated
    label_select = page.locator('#list-bulk-label-type')
    expect(label_select).to_be_visible()

    # Verify expected label types are present
    expected_types = ['Sato 1x2', 'Sato 1x2 Flag', 'Sato 2x4', 'Sato 2x4 Flag', 'Sato 4x6', 'Sato 4x6 Flag']
    for label_type in expected_types:
        option = label_select.locator(f"option[value='{label_type}']")
        expect(option).to_have_count(1)


@pytest.mark.e2e
def test_bulk_label_printing_button_enabled_on_label_type_selection(page, live_server):
    """Test that Print All button is enabled when label type is selected"""
    # Create test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA400001", "Aluminum")

    # Navigate to list and select item
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    page.locator('input.item-checkbox[data-ja-id="JA400001"]').check()

    # Open modal
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()

    # Wait for modal to load
    page.wait_for_timeout(2000)

    # Verify Print All button is initially disabled
    print_all_btn = page.locator('#list-bulk-print-all-btn')
    expect(print_all_btn).to_be_disabled()

    # Select a label type
    label_select = page.locator('#list-bulk-label-type')
    label_select.select_option('Sato 1x2')

    # Verify Print All button is now enabled
    expect(print_all_btn).to_be_enabled()


@pytest.mark.e2e
def test_bulk_label_printing_successful_batch_print(page, live_server):
    """Test successful bulk label printing for multiple items"""
    # Create test items
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA500001", "Aluminum")

    add_page.navigate()
    add_page.add_minimal_item("JA500002", "Steel")

    # Navigate to list and select items
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    page.locator('input.item-checkbox[data-ja-id="JA500001"]').check()
    page.locator('input.item-checkbox[data-ja-id="JA500002"]').check()

    # Open modal
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()

    # Wait for modal to load
    page.wait_for_timeout(2000)

    # Select label type and print
    page.locator('#list-bulk-label-type').select_option('Sato 2x4')
    page.locator('#list-bulk-print-all-btn').click()

    # Wait for printing to complete
    page.wait_for_timeout(3000)

    # Verify progress section is visible
    progress_div = page.locator('#list-bulk-print-progress')
    expect(progress_div).to_be_visible()

    # Verify completion status
    status_span = page.locator('#list-bulk-print-status')
    expect(status_span).to_contain_text('Complete')
    expect(status_span).to_contain_text('2 printed')

    # Verify Done button is visible
    done_btn = page.locator('#list-bulk-print-done-btn')
    expect(done_btn).to_be_visible()


@pytest.mark.e2e
def test_bulk_label_printing_progress_tracking(page, live_server):
    """Test that progress is tracked during bulk printing"""
    # Create multiple test items
    add_page = AddItemPage(page, live_server.url)
    for i in range(3):
        add_page.navigate()
        add_page.add_minimal_item(f"JA60000{i+1}", "Aluminum")

    # Navigate to list and select all items
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    for i in range(3):
        page.locator(f'input.item-checkbox[data-ja-id="JA60000{i+1}"]').check()

    # Open modal and start printing
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()
    page.wait_for_timeout(2000)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-print-all-btn').click()

    # Wait a bit for printing to start
    page.wait_for_timeout(500)

    # Verify progress bar is visible and updating
    progress_bar = page.locator('#list-bulk-print-progress-bar')
    expect(progress_bar).to_be_visible()

    # Wait for completion
    page.wait_for_timeout(3000)

    # Verify final progress
    expect(progress_bar).to_have_text('100%')


@pytest.mark.e2e
def test_bulk_label_printing_modal_close_and_reset(page, live_server):
    """Test that modal resets when closed"""
    # Create test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA700001", "Aluminum")

    # Navigate to list and select item
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    page.locator('input.item-checkbox[data-ja-id="JA700001"]').check()

    # Open modal and select label type
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()
    page.wait_for_timeout(2000)

    page.locator('#list-bulk-label-type').select_option('Sato 4x6')

    # Close modal
    page.locator('#list-bulk-print-cancel').click()
    page.wait_for_timeout(500)

    # Reopen modal
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()
    page.wait_for_timeout(2000)

    # Verify label type is reset
    label_select = page.locator('#list-bulk-label-type')
    selected_value = label_select.input_value()
    assert selected_value == "", "Label type should be reset when modal reopens"

    # Verify Print All button is disabled
    print_all_btn = page.locator('#list-bulk-print-all-btn')
    expect(print_all_btn).to_be_disabled()


@pytest.mark.e2e
def test_bulk_label_printing_select_all_functionality(page, live_server):
    """Test using Select All option with bulk label printing"""
    # Create multiple test items
    add_page = AddItemPage(page, live_server.url)
    for i in range(3):
        add_page.navigate()
        add_page.add_minimal_item(f"JA80000{i+1}", "Aluminum")

    # Navigate to list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    # Use Select All from Options dropdown
    page.locator('button:has-text("Options")').click()
    page.locator('#select-all-btn').click()

    # Verify items are selected
    page.wait_for_timeout(500)

    # Open Print Labels modal
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()

    # Wait for modal
    page.wait_for_timeout(2000)

    # Verify all items are listed
    items_list = page.locator('#list-bulk-label-items-list')
    expect(items_list).to_contain_text('JA800001')
    expect(items_list).to_contain_text('JA800002')
    expect(items_list).to_contain_text('JA800003')

    # Verify summary shows correct count
    summary = page.locator('#list-bulk-print-summary')
    expect(summary).to_contain_text('3 item(s)')


@pytest.mark.e2e
def test_bulk_label_printing_api_error_handling(page, live_server):
    """Test error handling when print API fails"""
    # Create test items
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA900001", "Aluminum")

    # Navigate to list and select item
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    page.locator('input.item-checkbox[data-ja-id="JA900001"]').check()

    # Open modal
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()
    page.wait_for_timeout(2000)

    # Mock API to return error
    page.route("**/api/labels/print", lambda route: route.fulfill(
        status=500,
        content_type="application/json",
        body=json.dumps({"success": False, "error": "Printer offline"})
    ))

    # Select label type and print
    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-print-all-btn').click()

    # Wait for error handling
    page.wait_for_timeout(2000)

    # Verify error is displayed
    errors_div = page.locator('#list-bulk-print-errors')
    expect(errors_div).to_be_visible()
    expect(errors_div).to_contain_text('failed to print')

    # Verify completion status shows failure
    status_span = page.locator('#list-bulk-print-status')
    expect(status_span).to_contain_text('1 failed')


@pytest.mark.e2e
def test_bulk_label_printing_different_label_types(page, live_server):
    """Test bulk printing with different label types"""
    # Create test item
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.add_minimal_item("JA110001", "Aluminum")

    # Navigate to list and select item
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    page.locator('input.item-checkbox[data-ja-id="JA110001"]').check()

    label_types_to_test = ["Sato 1x2", "Sato 1x2 Flag", "Sato 2x4 Flag", "Sato 4x6"]

    for label_type in label_types_to_test:
        # Open modal
        page.locator('button:has-text("Options")').click()
        page.locator('#bulk-print-labels-btn').click()
        page.wait_for_timeout(2000)

        # Select label type and print
        page.locator('#list-bulk-label-type').select_option(label_type)
        page.locator('#list-bulk-print-all-btn').click()

        # Wait for completion
        page.wait_for_timeout(2000)

        # Verify completion
        status_span = page.locator('#list-bulk-print-status')
        expect(status_span).to_contain_text('Complete')

        # Close modal via Done button
        page.locator('#list-bulk-print-done-btn').click()
        page.wait_for_timeout(500)
