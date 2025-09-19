"""
E2E Tests for Thread Field Order (Issue #15)

Tests to verify that threading fields are in the correct order:
Thread Size, Thread Series, Handedness
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.pages.add_item_page import AddItemPage


@pytest.mark.e2e
def test_add_form_thread_field_order(page, live_server):
    """Test that threading fields are in correct order on Add Item form"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Verify form is displayed
    add_page.assert_form_visible()

    # Get all column elements in the threading row by looking for the Threading Information card
    threading_card = page.locator(".card").filter(has_text="Threading Information")
    expect(threading_card).to_be_visible()
    threading_columns = threading_card.locator(".row .col-md-4").all()

    # We expect exactly 3 columns for thread fields
    assert len(threading_columns) == 3, f"Expected 3 thread field columns, got {len(threading_columns)}"

    # Check the order of fields by looking at the labels
    first_column_label = threading_columns[0].locator("label").text_content()
    second_column_label = threading_columns[1].locator("label").text_content()
    third_column_label = threading_columns[2].locator("label").text_content()

    # Verify the correct order: Thread Size, Thread Series, Handedness
    assert "Thread Size" in first_column_label, f"First field should be Thread Size, got: {first_column_label}"
    assert "Thread Series" in second_column_label, f"Second field should be Thread Series, got: {second_column_label}"
    assert "Handedness" in third_column_label, f"Third field should be Handedness, got: {third_column_label}"

    # Also verify by checking the actual input/select element IDs
    first_field_id = threading_columns[0].locator("input, select").get_attribute("id")
    second_field_id = threading_columns[1].locator("input, select").get_attribute("id")
    third_field_id = threading_columns[2].locator("input, select").get_attribute("id")

    assert first_field_id == "thread_size", f"First field should be thread_size, got: {first_field_id}"
    assert second_field_id == "thread_series", f"Second field should be thread_series, got: {second_field_id}"
    assert third_field_id == "thread_handedness", f"Third field should be thread_handedness, got: {third_field_id}"


@pytest.mark.e2e
def test_edit_form_thread_field_order(page, live_server):
    """Test that threading fields are in correct order on Edit Item form"""
    # First add a threaded rod item to edit
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.fill_basic_item_data("JA000100", "Threaded Rod", "Round", "Carbon Steel")
    add_page.fill_dimensions(length="36")
    add_page.fill_thread_information(thread_series="UNC", thread_size="1/4-20", thread_handedness="RH")
    add_page.fill_location_and_notes(location="Storage A")
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Navigate to edit the item
    page.goto(f"{live_server.url}/inventory/edit/JA000100")

    # Verify edit form is displayed
    expect(page.locator("#add-item-form")).to_be_visible()

    # Threading section should be visible since this is a threaded rod
    threading_section = page.locator("#threading-section")
    expect(threading_section).to_be_visible()

    # Get all column elements in the threading row
    threading_columns = page.locator("#threading-section .row .col-md-4").all()

    # We expect exactly 3 columns for thread fields
    assert len(threading_columns) == 3, f"Expected 3 thread field columns, got {len(threading_columns)}"

    # Check the order of fields by looking at the labels
    first_column_label = threading_columns[0].locator("label").text_content()
    second_column_label = threading_columns[1].locator("label").text_content()
    third_column_label = threading_columns[2].locator("label").text_content()

    # Verify the correct order: Thread Size, Thread Series, Handedness
    assert "Thread Size" in first_column_label, f"First field should be Thread Size, got: {first_column_label}"
    assert "Thread Series" in second_column_label, f"Second field should be Thread Series, got: {second_column_label}"
    assert "Handedness" in third_column_label, f"Third field should be Handedness, got: {third_column_label}"

    # Also verify by checking the actual input/select element IDs
    first_field_id = threading_columns[0].locator("input, select").get_attribute("id")
    second_field_id = threading_columns[1].locator("input, select").get_attribute("id")
    third_field_id = threading_columns[2].locator("input, select").get_attribute("id")

    assert first_field_id == "thread_size", f"First field should be thread_size, got: {first_field_id}"
    assert second_field_id == "thread_series", f"Second field should be thread_series, got: {second_field_id}"
    assert third_field_id == "thread_handedness", f"Third field should be thread_handedness, got: {third_field_id}"

    # Verify that the fields are populated with the correct values
    expect(page.locator("#thread_size")).to_have_value("1/4-20")
    expect(page.locator("#thread_series")).to_have_value("UNC")
    expect(page.locator("#thread_handedness")).to_have_value("RH")


@pytest.mark.e2e
def test_thread_fields_work_correctly_after_reorder(page, live_server):
    """Test that thread functionality still works correctly after reordering fields"""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    # Fill basic item data for a threaded rod
    add_page.fill_basic_item_data("JA000101", "Threaded Rod", "Round", "Stainless Steel")
    add_page.fill_dimensions(length="48")
    add_page.fill_location_and_notes(location="Storage B")

    # Fill thread information in the new field order
    page.fill("#thread_size", "3/8-16")  # First field: Thread Size
    page.select_option("#thread_series", "UNC")  # Second field: Thread Series
    page.select_option("#thread_handedness", "LH")  # Third field: Handedness

    # Submit form
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Navigate to edit form to verify data was saved correctly
    page.goto(f"{live_server.url}/inventory/edit/JA000101")

    # Verify all threading information was saved in the correct fields
    expect(page.locator("#thread_size")).to_have_value("3/8-16")
    expect(page.locator("#thread_series")).to_have_value("UNC")
    expect(page.locator("#thread_handedness")).to_have_value("LH")


@pytest.mark.e2e
def test_thread_field_consistency_between_add_and_edit(page, live_server):
    """Test that Add and Edit forms have consistent thread field ordering"""
    add_page = AddItemPage(page, live_server.url)

    # Check Add form field order
    add_page.navigate()
    add_threading_card = page.locator(".card").filter(has_text="Threading Information")
    add_threading_columns = add_threading_card.locator(".row .col-md-4").all()
    add_field_ids = [col.locator("input, select").get_attribute("id") for col in add_threading_columns]

    # Create a test item to check Edit form
    add_page.fill_basic_item_data("JA000102", "Threaded Rod", "Round", "Aluminum")
    add_page.fill_dimensions(length="24")
    add_page.fill_location_and_notes(location="Storage C")
    add_page.submit_form()
    add_page.assert_form_submitted_successfully()

    # Check Edit form field order
    page.goto(f"{live_server.url}/inventory/edit/JA000102")
    edit_threading_columns = page.locator("#threading-section .row .col-md-4").all()
    edit_field_ids = [col.locator("input, select").get_attribute("id") for col in edit_threading_columns]

    # Verify both forms have the same field order
    assert add_field_ids == edit_field_ids, f"Add form field order {add_field_ids} doesn't match Edit form field order {edit_field_ids}"

    # Verify the expected order
    expected_order = ["thread_size", "thread_series", "thread_handedness"]
    assert add_field_ids == expected_order, f"Add form field order should be {expected_order}, got {add_field_ids}"
    assert edit_field_ids == expected_order, f"Edit form field order should be {expected_order}, got {edit_field_ids}"