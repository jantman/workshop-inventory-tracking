"""
E2E tests for creating, editing and viewing a product.

The Phase 2 checkpoint: a product can be created, edited and viewed, and carries
an internal code that a scan can later resolve.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.specification_rows import set_specifications


def create_product(page, base_url, description, specifications=None, **fields):
    """Fill in the add-product form and submit it"""
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)

    for field, value in fields.items():
        page.fill(f"#{field}", value)

    if specifications:
        set_specifications(page, specifications)

    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.e2e
def test_create_product_and_view_it(page, live_server):
    """A product created through the form is immediately viewable"""
    create_product(
        page, live_server.url,
        "Blue widget, 10mm",
        manufacturer="Acme",
        specifications=[("Shaft", "10mm"), ("Finish", "blue anodized")],
        location="Bin 4",
        category_path="Hardware/Widgets",
    )

    expect(page.locator("#product-description")).to_have_text("Blue widget, 10mm")
    expect(page.locator("#product-manufacturer")).to_have_text("Acme")
    expect(page.locator("#product-specifications")).to_contain_text("blue anodized")
    expect(page.locator("#product-location")).to_have_text("Bin 4")
    expect(page.locator("#product-category")).to_have_text("hardware/widgets")


@pytest.mark.e2e
def test_new_product_carries_an_internal_code(page, live_server):
    """FR-015: scannable from the moment it exists, before any label is printed"""
    create_product(page, live_server.url, "Blue widget")

    code = page.locator("#internal-code")
    expect(code).to_be_visible()
    assert code.inner_text().strip().startswith("WIT")


@pytest.mark.e2e
def test_a_product_is_reachable_by_its_printed_code(page, live_server):
    """009 SC-007: the label's code is the whole address, no lookup step first"""
    product = live_server.add_test_products([{
        'description': 'Toroidal transformer',
    }])[0]

    page.goto(f"{live_server.url}/products/{product.internal_code}")

    expect(page.locator("#product-description")).to_have_text("Toroidal transformer")
    # 009 FR-017: the record number stays canonical, and says so in the address.
    expect(page).to_have_url(f"{live_server.url}/products/{product.id}")


@pytest.mark.e2e
def test_edit_a_product(page, live_server):
    """Edits are saved and shown"""
    create_product(page, live_server.url, "Blue widget", location="Bin 4")

    page.click("text=Edit")
    page.wait_for_load_state("domcontentloaded")

    page.fill("#description", "Blue widget, revised")
    page.fill("#location", "Bin 9")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#product-description")).to_have_text("Blue widget, revised")
    expect(page.locator("#product-location")).to_have_text("Bin 9")


@pytest.mark.e2e
def test_product_appears_in_the_catalogue_list(page, live_server):
    """The list page is reachable from the nav and shows what was created"""
    create_product(page, live_server.url, "Findable widget")

    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table")).to_contain_text("Findable widget")


@pytest.mark.e2e
def test_a_product_with_no_description_is_rejected(page, live_server):
    """Bad data breaks the inventory, so it does not get in"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", "")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    # Still on the form, not on a detail page.
    expect(page.locator("#description")).to_be_visible()


@pytest.mark.e2e
def test_an_identifier_entered_at_creation_is_attached(page, live_server):
    """FR-007: a product's other coded names are recorded alongside it"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", "Barcoded widget")
    page.select_option("#identifier_type", "GTIN")
    page.fill("#identifier_value", "012345678905")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

    # Stored in its normalized 14-digit form (FR-009).
    expect(page.locator("#identifier-list")).to_contain_text("00012345678905")


@pytest.mark.e2e
def test_a_product_records_a_location_and_a_sub_location(page, live_server):
    """FR-020/FR-021: both save and both show, matching metal stock"""
    create_product(
        page, live_server.url,
        "Binned widget",
        location="Drawer 3",
        sub_location="Bin 7",
    )

    expect(page.locator("#product-location")).to_have_text("Drawer 3")
    expect(page.locator("#product-sub-location")).to_have_text("Bin 7")


@pytest.mark.e2e
def test_a_product_without_a_sub_location_is_not_an_error(page, live_server):
    """FR-023: no sub-location recorded is an ordinary state"""
    create_product(page, live_server.url, "Unbinned widget", location="Drawer 3")

    expect(page.locator("#product-location")).to_have_text("Drawer 3")
    expect(page.locator("#product-sub-location")).to_have_text("Not recorded")


@pytest.mark.e2e
def test_a_sub_location_survives_an_edit(page, live_server):
    create_product(
        page, live_server.url, "Binned widget",
        location="Drawer 3", sub_location="Bin 7",
    )

    page.click("text=Edit")
    expect(page.locator("#sub_location")).to_have_value("Bin 7")
    page.fill("#sub_location", "Bin 9")
    page.click("#save-product-btn")

    expect(page.locator("#product-sub-location")).to_have_text("Bin 9")


@pytest.mark.e2e
def test_a_sub_location_is_suggested_scoped_by_the_location(page, live_server):
    """FR-022: already recorded under that location, so offered under it"""
    live_server.add_test_products([
        {'description': 'first widget', 'location': 'Drawer 3', 'sub_location': 'Bin 7'},
        {'description': 'other widget', 'location': 'Drawer 9', 'sub_location': 'Bin 99'},
    ])

    page.goto(f"{live_server.url}/products/new")
    expect(page.locator("#sub_location")).to_be_visible()

    page.fill("#location", "Drawer 3")
    page.locator("#sub_location").click()

    dropdown = page.locator("#sub_location-suggestions")
    # render() appends only after the fetch resolves, so the rendered item is
    # the whole wait (CLAUDE.md pattern C).
    expect(dropdown.locator(".dropdown-item", has_text="Bin 7")).to_have_count(1)
    expect(dropdown).not_to_contain_text("Bin 99")
