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

from tests.e2e.waits import (
    wait_for_modal_hidden,
    wait_for_modal_shown,
    wait_for_select_populated,
)

MODAL = "listBulkLabelPrintingModal"
SELECT = "list-bulk-label-type"


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

    # The handler calls window.alert(). Register the dialog handler before the
    # click: click() cannot return until the dialog is dismissed, so by the time
    # it does we know the alert fired -- which is what makes the negative
    # assertion below meaningful instead of racing an unreacted page.
    messages = []

    def handle_dialog(dialog):
        messages.append(dialog.message)
        dialog.accept()

    page.on("dialog", handle_dialog)

    # Try to open Print Labels without selecting items
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()

    assert messages, "Expected an alert when printing labels with nothing selected"
    assert "select at least one item" in messages[0].lower()

    # Modal should not open (the alert showed instead)
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

    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

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

    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

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

    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

    # Select label type and print
    page.locator('#list-bulk-label-type').select_option('Sato 2x4')
    page.locator('#list-bulk-print-all-btn').click()

    # Verify progress section is visible
    progress_div = page.locator('#list-bulk-print-progress')
    expect(progress_div).to_be_visible()

    # Verify completion status
    status_span = page.locator('#list-bulk-print-status')
    expect(status_span).to_contain_text('Complete')
    # The summary reports labels and items at every count, not just above 1.
    expect(status_span).to_have_text('Complete: 2 labels for 2 items, 0 failed')

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
    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-print-all-btn').click()

    # Verify progress bar is visible and updating
    progress_bar = page.locator('#list-bulk-print-progress-bar')
    expect(progress_bar).to_be_visible()

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
    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

    page.locator('#list-bulk-label-type').select_option('Sato 4x6')

    # Close modal
    page.locator('#list-bulk-print-cancel').click()
    wait_for_modal_hidden(page, MODAL)

    # Reopen modal
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()
    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

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

    # Open Print Labels modal
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()

    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

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
    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

    # Mock API to return error
    page.route("**/api/labels/print", lambda route: route.fulfill(
        status=500,
        content_type="application/json",
        body=json.dumps({"success": False, "error": "Printer offline"})
    ))

    # Select label type and print
    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-print-all-btn').click()

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
        wait_for_modal_shown(page, MODAL)
        wait_for_select_populated(page, SELECT)

        # Select label type and print
        page.locator('#list-bulk-label-type').select_option(label_type)
        page.locator('#list-bulk-print-all-btn').click()

        # Verify completion
        status_span = page.locator('#list-bulk-print-status')
        expect(status_span).to_contain_text('Complete')

        # Close modal via Done button
        page.locator('#list-bulk-print-done-btn').click()
        wait_for_modal_hidden(page, MODAL)


def _capture_print_payloads(page):
    """Collect the decoded bodies of every POST to /api/labels/print."""
    payloads = []

    def handle_request(request):
        if "/api/labels/print" in request.url and request.method == "POST":
            payloads.append(json.loads(request.post_data))

    page.on("request", handle_request)
    return payloads


def _seed_and_select(page, live_server, ja_ids):
    """Seed items directly and tick their checkboxes on the inventory list."""
    live_server.add_test_data([
        {
            "ja_id": ja_id,
            "item_type": "Bar",
            "shape": "Round",
            "material": "Aluminum",
            "width": "1",
            "length": "12",
            "location": "Test Storage A",
            "active": True,
        }
        for ja_id in ja_ids
    ])

    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()

    for ja_id in ja_ids:
        page.locator(f'input.item-checkbox[data-ja-id="{ja_id}"]').check()


def _open_bulk_print_modal(page):
    """Open the list page's bulk print dialog and wait for it to finish loading."""
    page.locator('button:has-text("Options")').click()
    page.locator('#bulk-print-labels-btn').click()
    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)


@pytest.mark.e2e
def test_bulk_label_count_defaults_to_one(page, live_server):
    """Story 2 scenario 1: the label count shows 1 when the dialog opens"""
    _seed_and_select(page, live_server, ["JA700001", "JA700002"])
    _open_bulk_print_modal(page)

    count_input = page.locator('#list-bulk-label-count')
    expect(count_input).to_be_visible()
    expect(count_input).to_have_value('1')

    # "Labels per item", not "Quantity" -- the Add form's quantity is a
    # different number and the two must not read alike.
    expect(page.locator("label[for='list-bulk-label-count']")).to_have_text(
        'Labels per item'
    )


@pytest.mark.e2e
def test_bulk_label_count_default_sends_one_per_item(page, live_server):
    """Story 2 scenario 2: three items at the default produce three labels"""
    ja_ids = ["JA710001", "JA710002", "JA710003"]
    payloads = _capture_print_payloads(page)

    _seed_and_select(page, live_server, ja_ids)
    _open_bulk_print_modal(page)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-print-all-btn').click()

    # The completion line is rendered after every request has settled, so it is
    # a complete signal for the whole run.
    status_span = page.locator('#list-bulk-print-status')
    expect(status_span).to_have_text('Complete: 3 labels for 3 items, 0 failed')

    assert payloads == [
        {"ja_id": ja_id, "label_type": "Sato 1x2", "label_count": 1}
        for ja_id in ja_ids
    ]


@pytest.mark.e2e
def test_bulk_label_count_of_two_sends_two_per_item(page, live_server):
    """Story 2 scenarios 3, 4 and the summary: three items at 2 produce six labels"""
    ja_ids = ["JA720001", "JA720002", "JA720003"]
    payloads = _capture_print_payloads(page)

    _seed_and_select(page, live_server, ja_ids)
    _open_bulk_print_modal(page)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-label-count').fill('2')
    page.locator('#list-bulk-print-all-btn').click()

    status_span = page.locator('#list-bulk-print-status')
    expect(status_span).to_have_text('Complete: 6 labels for 3 items, 0 failed')

    # One request per item carrying the count -- not two requests per item.
    # That is also what keeps an item's copies consecutive: they are one job.
    assert payloads == [
        {"ja_id": ja_id, "label_type": "Sato 1x2", "label_count": 2}
        for ja_id in ja_ids
    ]


@pytest.mark.e2e
def test_bulk_label_count_progress_line_names_the_count(page, live_server):
    """The progress line gains a count suffix only above 1"""
    payloads = _capture_print_payloads(page)

    _seed_and_select(page, live_server, ["JA730001"])
    _open_bulk_print_modal(page)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-label-count').fill('4')
    page.locator('#list-bulk-print-all-btn').click()

    status_span = page.locator('#list-bulk-print-status')
    # Singular "item" -- one selected item, four labels for it.
    expect(status_span).to_have_text('Complete: 4 labels for 1 item, 0 failed')

    assert payloads == [
        {"ja_id": "JA730001", "label_type": "Sato 1x2", "label_count": 4}
    ]


@pytest.mark.e2e
@pytest.mark.parametrize("bad_count", ["0", "100", "2.5", "-1", ""])
def test_bulk_label_count_refused_prints_nothing(page, live_server, bad_count):
    """Story 2 scenario 6: an invalid count prints nothing and says why"""
    payloads = _capture_print_payloads(page)

    _seed_and_select(page, live_server, ["JA740001", "JA740002"])
    _open_bulk_print_modal(page)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-label-count').fill(bad_count)
    page.locator('#list-bulk-print-all-btn').click()

    # The error region is written synchronously before the loop would have
    # started, so its visibility establishes that the handler ran and returned.
    # Only then does "no request was sent" mean anything.
    errors_div = page.locator('#list-bulk-print-errors')
    expect(errors_div).to_be_visible()
    expect(errors_div).to_contain_text(
        'Label count must be a whole number between 1 and 99'
    )

    assert payloads == []

    # The dialog stays open with the label type still selected, and the run
    # never started -- the progress section is still hidden.
    expect(page.locator(f'#{MODAL}')).to_be_visible()
    expect(page.locator('#list-bulk-label-type')).to_have_value('Sato 1x2')
    expect(page.locator('#list-bulk-print-progress')).not_to_be_visible()


@pytest.mark.e2e
def test_bulk_label_count_resets_on_reopen(page, live_server):
    """Story 2 scenario 7: reopening the dialog resets the count to 1"""
    _seed_and_select(page, live_server, ["JA750001", "JA750002"])
    _open_bulk_print_modal(page)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-label-count').fill('5')
    page.locator('#list-bulk-print-all-btn').click()

    status_span = page.locator('#list-bulk-print-status')
    expect(status_span).to_have_text('Complete: 10 labels for 2 items, 0 failed')

    page.locator('#list-bulk-print-done-btn').click()
    wait_for_modal_hidden(page, MODAL)

    _open_bulk_print_modal(page)

    expect(page.locator('#list-bulk-label-count')).to_have_value('1')


@pytest.mark.e2e
def test_bulk_corrected_count_clears_the_earlier_warning(page, live_server):
    """A refused count's warning must not survive the corrected retry.

    The modal reset only runs when the dialog opens and closes, so without an
    explicit clear at the start of a run the warning stays on screen -- sitting
    directly above a successful completion line, which reads as a failure.
    """
    _seed_and_select(page, live_server, ["JA760001", "JA760002"])
    _open_bulk_print_modal(page)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-label-count').fill('0')
    page.locator('#list-bulk-print-all-btn').click()

    errors_div = page.locator('#list-bulk-print-errors')
    expect(errors_div).to_be_visible()

    # Correct the count and print for real.
    page.locator('#list-bulk-label-count').fill('2')
    page.locator('#list-bulk-print-all-btn').click()

    status_span = page.locator('#list-bulk-print-status')
    expect(status_span).to_have_text('Complete: 4 labels for 2 items, 0 failed')

    # Established by the completion assertion above, so this is a real negative.
    expect(errors_div).not_to_be_visible()


@pytest.mark.e2e
def test_bulk_summary_uses_singular_nouns_for_one(page, live_server):
    """One item at a count of 1 reads "1 label for 1 item", not "1 labels ... 1 items" """
    _seed_and_select(page, live_server, ["JA770001"])
    _open_bulk_print_modal(page)

    page.locator('#list-bulk-label-type').select_option('Sato 1x2')
    page.locator('#list-bulk-print-all-btn').click()

    status_span = page.locator('#list-bulk-print-status')
    expect(status_span).to_have_text('Complete: 1 label for 1 item, 0 failed')
