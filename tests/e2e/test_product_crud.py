"""
E2E tests for creating, editing and viewing a product.

The Phase 2 checkpoint: a product can be created, edited and viewed, and carries
an internal code that a scan can later resolve.
"""

import pytest
from playwright.sync_api import expect


def create_product(page, base_url, description, **fields):
    """Fill in the add-product form and submit it"""
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)

    for field, value in fields.items():
        page.fill(f"#{field}", value)

    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.e2e
def test_create_product_and_view_it(page, live_server):
    """A product created through the form is immediately viewable"""
    create_product(
        page, live_server.url,
        "Blue widget, 10mm",
        manufacturer="Acme",
        specifications="10mm shaft, blue anodized",
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
