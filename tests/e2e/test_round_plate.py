"""
Round Plate Dimension Tests

A round plate is a disc: how far across it is, and how thick. It requires a
diameter and a thickness, and no length (issue #85, FR-001).

Wait conditions here follow one rule: the requirement marks are applied
synchronously by dimension-requirements.js on the select's `change` event, so
the signal that the module has run for the current selection is a *positive*
one -- a field that is now required, or a label that now reads "Diameter".
"Length is not required" is also true of a form the module has never touched,
so it is only ever asserted after one of those.
"""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.pages.add_item_page import AddItemPage
from tests.e2e.pages.inventory_list_page import InventoryListPage


def _select_type_and_shape(page, add_page, item_type, shape):
    """Choose a Type and Shape and wait for the requirement marks to follow."""
    page.select_option(add_page.ITEM_TYPE_SELECT, item_type)
    page.select_option(add_page.SHAPE_SELECT, shape)
    # updateShapeOptions() clears the selection when the new Type cannot take
    # the old Shape, so confirm the pair actually took before reading marks.
    expect(page.locator(add_page.SHAPE_SELECT)).to_have_value(shape)


@pytest.mark.e2e
def test_round_plate_requires_diameter_and_thickness_not_length(page, live_server):
    """FR-001, FR-004: the form asks for the two measurements a disc has."""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()

    _select_type_and_shape(page, add_page, "Plate", "Round")

    width = page.locator(add_page.WIDTH_INPUT)
    thickness = page.locator(add_page.THICKNESS_INPUT)
    length = page.locator(add_page.LENGTH_INPUT)

    # Positive first: these cannot be true before the module has applied the
    # Plate/Round rule, so they establish that it has.
    expect(width).to_have_js_property("required", True)
    expect(thickness).to_have_js_property("required", True)
    expect(page.locator(add_page.WIDTH_LABEL)).to_have_text("Diameter")

    expect(length).to_have_js_property("required", False)


@pytest.mark.e2e
def test_add_round_plate_with_only_diameter_and_thickness(page, live_server):
    """The whole of issue #85: two measurements, no invented third."""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    add_page.fill_basic_item_data("JA085001", "Plate", "Round", "Aluminum")
    expect(page.locator(add_page.THICKNESS_INPUT)).to_have_js_property("required", True)
    add_page.fill_dimensions(width="6", thickness="0.25")
    add_page.fill_location_and_notes(location="Storage A")

    # submit_form() returns False when the browser refuses the submission; a
    # caller that ignores it carries on as though the item exists.
    assert add_page.submit_form() is True, "the form refused a valid round plate"
    add_page.assert_form_submitted_successfully()

    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    list_page.assert_item_in_list("JA085001")


@pytest.mark.e2e
def test_add_round_sheet_with_only_diameter_and_thickness(page, live_server):
    """A round sheet is the same disc with a different thickness."""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    add_page.fill_basic_item_data("JA085002", "Sheet", "Round", "Aluminum")
    expect(page.locator(add_page.THICKNESS_INPUT)).to_have_js_property("required", True)
    add_page.fill_dimensions(width="12", thickness="0.0625")
    add_page.fill_location_and_notes(location="Storage A")

    assert add_page.submit_form() is True, "the form refused a valid round sheet"
    add_page.assert_form_submitted_successfully()

    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    list_page.assert_item_in_list("JA085002")


@pytest.mark.e2e
def test_round_plate_with_a_length_is_still_accepted(page, live_server):
    """FR-002: length remains available, it has merely stopped being demanded."""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    add_page.fill_basic_item_data("JA085003", "Plate", "Round", "Aluminum")
    expect(page.locator(add_page.THICKNESS_INPUT)).to_have_js_property("required", True)
    add_page.fill_dimensions(length="3", width="6", thickness="0.25")
    add_page.fill_location_and_notes(location="Storage A")

    assert add_page.submit_form() is True
    add_page.assert_form_submitted_successfully()

    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    list_page.assert_item_in_list("JA085003")


@pytest.mark.e2e
def test_round_plate_without_thickness_is_refused(page, live_server):
    """FR-003: the thickness is marked required, and the mark is enforced."""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()

    add_page.fill_basic_item_data("JA085004", "Plate", "Round", "Aluminum")
    expect(page.locator(add_page.THICKNESS_INPUT)).to_have_js_property("required", True)
    add_page.fill_dimensions(width="6")
    add_page.fill_location_and_notes(location="Storage A")

    assert add_page.submit_form() is False, "a round plate with no thickness was accepted"

    # Nothing was recorded. The list is established before the absence is read:
    # a table that has not loaded is empty of everything.
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    expect(page.locator("#empty-state")).to_be_visible()


@pytest.mark.e2e
def test_changing_type_to_bar_demands_a_length_again(page, live_server):
    """Story 1, scenario 7: the form says so before the operator submits."""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()

    _select_type_and_shape(page, add_page, "Plate", "Round")
    length = page.locator(add_page.LENGTH_INPUT)
    expect(page.locator(add_page.THICKNESS_INPUT)).to_have_js_property("required", True)
    expect(length).to_have_js_property("required", False)

    page.select_option(add_page.ITEM_TYPE_SELECT, "Bar")
    expect(page.locator(add_page.SHAPE_SELECT)).to_have_value("Round")
    expect(length).to_have_js_property("required", True)
    # Bar/Round requires a length and a diameter, and no thickness.
    expect(page.locator(add_page.THICKNESS_INPUT)).to_have_js_property("required", False)


ROUND_PLATE = {
    "ja_id": "JA085010",
    "item_type": "Plate",
    "shape": "Round",
    "material": "Aluminum",
    "width": "6",
    "thickness": "0.25",
    "location": "Test Storage A",
    "active": True,
}

RECTANGULAR_PLATE = {
    "ja_id": "JA085011",
    "item_type": "Plate",
    "shape": "Rectangular",
    "material": "Aluminum",
    "length": "12",
    "width": "6",
    "thickness": "0.25",
    "location": "Test Storage A",
    "active": True,
}


def _open_edit_form(page, live_server, ja_id):
    """Open the Edit form and wait for the rules to have been applied to it."""
    page.goto(f"{live_server.url}/inventory/edit/{ja_id}")
    expect(page.locator("#add-item-form")).to_be_visible()
    # The module marks the thickness required for every plate, round or not,
    # and the Edit form's static HTML never did -- so this is a signal that
    # cannot be true before dimension-requirements.js has run.
    expect(page.locator("#thickness")).to_have_js_property("required", True)


@pytest.mark.e2e
def test_edit_form_marks_what_a_round_plate_requires(page, live_server):
    """FR-007: the marks and the enforcement are the same list."""
    live_server.add_test_data([ROUND_PLATE])
    _open_edit_form(page, live_server, "JA085010")

    expect(page.locator("#width")).to_have_js_property("required", True)
    expect(page.locator("#width-label")).to_have_text("Diameter")
    expect(page.locator("#length")).to_have_js_property("required", False)


@pytest.mark.e2e
def test_saving_a_round_plate_unchanged_demands_nothing(page, live_server):
    """SC-003: what the Add form recorded, the Edit form saves back."""
    live_server.add_test_data([ROUND_PLATE])
    add_page = AddItemPage(page, live_server.url)
    _open_edit_form(page, live_server, "JA085010")

    assert add_page.submit_and_wait("button[type='submit']") is True, \
        "the edit form refused an unchanged round plate"
    expect(page).not_to_have_url(f"{live_server.url}/inventory/edit/JA085010")

    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    list_page.assert_item_in_list("JA085010")


@pytest.mark.e2e
def test_clearing_the_thickness_of_a_round_plate_is_refused(page, live_server):
    """Story 2, scenario 3."""
    live_server.add_test_data([ROUND_PLATE])
    add_page = AddItemPage(page, live_server.url)
    _open_edit_form(page, live_server, "JA085010")

    page.locator("#thickness").fill("")

    assert add_page.submit_and_wait("button[type='submit']") is False, \
        "a round plate was saved with its thickness cleared"
    expect(page).to_have_url(f"{live_server.url}/inventory/edit/JA085010")
    assert page.evaluate("document.getElementById('thickness').checkValidity()") is False


@pytest.mark.e2e
def test_changing_a_rectangular_plate_to_round_keeps_its_length(page, live_server):
    """Story 2, scenario 6: a recorded length is not discarded for want of demand."""
    live_server.add_test_data([RECTANGULAR_PLATE])
    add_page = AddItemPage(page, live_server.url)
    _open_edit_form(page, live_server, "JA085011")

    # The stored Numeric renders with a varying number of trailing zeros
    # depending on how it reached the field, so match the measurement, not
    # its formatting.
    twelve_inches = re.compile(r"^12(\.0+)?$")
    expect(page.locator("#length")).to_have_value(twelve_inches)
    page.select_option("#shape", "Round")
    # Round drops the length requirement; the value stays in the field.
    expect(page.locator("#width-label")).to_have_text("Diameter")
    expect(page.locator("#length")).to_have_js_property("required", False)

    assert add_page.submit_and_wait("button[type='submit']") is True
    expect(page).not_to_have_url(f"{live_server.url}/inventory/edit/JA085011")

    page.goto(f"{live_server.url}/inventory/edit/JA085011")
    expect(page.locator("#shape")).to_have_value("Round")
    expect(page.locator("#length")).to_have_value(twelve_inches)


@pytest.mark.e2e
def test_rectangular_plate_still_demands_all_three(page, live_server):
    """FR-010: what changes is the round row, and only the round row."""
    add_page = AddItemPage(page, live_server.url)
    add_page.navigate()
    add_page.assert_form_visible()

    _select_type_and_shape(page, add_page, "Plate", "Rectangular")

    expect(page.locator(add_page.WIDTH_LABEL)).to_have_text("Width")
    expect(page.locator(add_page.LENGTH_INPUT)).to_have_js_property("required", True)
    expect(page.locator(add_page.WIDTH_INPUT)).to_have_js_property("required", True)
    expect(page.locator(add_page.THICKNESS_INPUT)).to_have_js_property("required", True)
