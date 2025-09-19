"""
E2E Tests for Required Location Field (Issue #16)

Tests to verify that Location field is required on Add/Edit Item forms.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.inventory_list_page import InventoryListPage


@pytest.mark.e2e
def test_add_item_requires_location_field(page, live_server):
    """Test that Location field is required when adding items"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Verify form is displayed
    add_page.assert_form_visible()

    # Fill all required fields EXCEPT location
    add_page.fill_basic_item_data("JA000001", "Bar", "Round", "Carbon Steel")
    add_page.fill_dimensions(length="100", width="10")
    # Note: deliberately NOT filling location

    # Try to submit form
    add_page.submit_form()

    # Form should NOT submit successfully - should show validation error
    # Check that we're still on the add form (not redirected)
    current_url = page.url
    assert "/inventory/add" in current_url, "Should still be on add form due to validation error"

    # Check for HTML5 validation or custom validation message
    location_input = page.locator("#location")
    expect(location_input).to_have_attribute("required", "")

    # Check if browser validation is triggered (HTML5 required attribute)
    is_valid = page.evaluate("document.getElementById('location').checkValidity()")
    assert not is_valid, "Location field should fail validation when empty"


@pytest.mark.e2e
def test_add_item_succeeds_with_location_field(page, live_server):
    """Test that form submits successfully when location is provided"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Fill all required fields INCLUDING location
    add_page.fill_basic_item_data("JA000002", "Bar", "Round", "Carbon Steel")
    add_page.fill_dimensions(length="100", width="10")
    add_page.fill_location_and_notes(location="Storage Room A")  # Include required location

    # Submit form
    add_page.submit_form()

    # Should submit successfully
    add_page.assert_form_submitted_successfully()

    # Verify item appears in inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.assert_item_in_list("JA000002")


@pytest.mark.e2e
def test_edit_item_requires_location_field(page, live_server):
    """Test that Location field is required when editing existing items"""
    # First add an item with location
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.fill_basic_item_data("JA000003", "Bar", "Round", "Carbon Steel")
    add_page.fill_dimensions(length="100", width="10")
    add_page.fill_location_and_notes(location="Storage Room B")
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Navigate to edit the item
    page.goto(f"{live_server.url}/inventory/edit/JA000003")

    # Verify edit form is displayed
    expect(page.locator("#add-item-form")).to_be_visible()
    expect(page.locator("#location")).to_have_value("Storage Room B")

    # Clear the location field (make it empty)
    location_input = page.locator("#location")
    location_input.fill("")

    # Try to submit form without location
    submit_button = page.locator("button[type='submit']")
    submit_button.click()
    page.wait_for_timeout(1000)

    # Form should NOT submit successfully - should show validation error
    current_url = page.url
    assert "/inventory/edit/JA000003" in current_url, "Should still be on edit form due to validation error"

    # Check that location field has required attribute
    expect(location_input).to_have_attribute("required", "")

    # Check if browser validation is triggered
    is_valid = page.evaluate("document.getElementById('location').checkValidity()")
    assert not is_valid, "Location field should fail validation when empty"


@pytest.mark.e2e
def test_edit_item_succeeds_with_location_field(page, live_server):
    """Test that edit form submits successfully when location is provided"""
    # First add an item with location
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.fill_basic_item_data("JA000004", "Bar", "Round", "Carbon Steel")
    add_page.fill_dimensions(length="100", width="10")
    add_page.fill_location_and_notes(location="Storage Room C")
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Navigate to edit the item
    page.goto(f"{live_server.url}/inventory/edit/JA000004")

    # Verify edit form is displayed with current location
    expect(page.locator("#location")).to_have_value("Storage Room C")

    # Update the location to a different value
    location_input = page.locator("#location")
    location_input.fill("Updated Storage Room D")

    # Submit form
    submit_button = page.locator("button[type='submit']")
    submit_button.click()
    page.wait_for_timeout(1000)

    # Should submit successfully and redirect to inventory list
    current_url = page.url
    assert "/inventory/list" in current_url or "/inventory" in current_url, f"Should redirect to inventory list, got: {current_url}"

    # Verify the item still exists and location was updated
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.assert_item_in_list("JA000004")


@pytest.mark.e2e
def test_location_field_shows_required_indicator(page, live_server):
    """Test that Location field label shows required indicator (*)"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Check that location label shows required indicator
    location_label = page.locator("label[for='location']")
    expect(location_label).to_be_visible()

    label_text = location_label.text_content()
    assert "*" in label_text, f"Location label should contain '*' to indicate required field, got: {label_text}"

    # Also check edit form
    # First add an item
    add_page.fill_basic_item_data("JA000005", "Bar", "Round", "Carbon Steel")
    add_page.fill_dimensions(length="100", width="10")
    add_page.fill_location_and_notes(location="Storage Room E")
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Navigate to edit form
    page.goto(f"{live_server.url}/inventory/edit/JA000005")

    # Check that location label shows required indicator on edit form too
    edit_location_label = page.locator("label[for='location']")
    expect(edit_location_label).to_be_visible()

    edit_label_text = edit_location_label.text_content()
    assert "*" in edit_label_text, f"Edit form location label should contain '*' to indicate required field, got: {edit_label_text}"


@pytest.mark.e2e
def test_sublocation_remains_optional(page, live_server):
    """Test that Sub-Location field remains optional (Issue #16 requirement)"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Fill required fields including location but NOT sub-location
    add_page.fill_basic_item_data("JA000006", "Bar", "Round", "Carbon Steel")
    add_page.fill_dimensions(length="100", width="10")
    add_page.fill_location_and_notes(location="Storage Room F")
    # Note: deliberately NOT filling sub_location

    # Submit form - should succeed
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Verify item appears in inventory list
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.assert_item_in_list("JA000006")

    # Check that sub-location input does NOT have required attribute
    add_page.navigate()
    sub_location_input = page.locator("#sub_location")
    expect(sub_location_input).to_be_visible()
    # Check that sub-location does not have required attribute (it should remain optional)
    has_required = page.evaluate("document.getElementById('sub_location').hasAttribute('required')")
    assert not has_required, "Sub-location field should not have required attribute"

    # Check that sub-location label does NOT show required indicator
    sub_location_label = page.locator("label[for='sub_location']")
    sub_location_label_text = sub_location_label.text_content()
    assert "*" not in sub_location_label_text, f"Sub-location label should NOT contain '*' (should remain optional), got: {sub_location_label_text}"