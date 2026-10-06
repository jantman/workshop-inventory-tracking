"""
E2E tests for the pack fields on Record a Purchase (feature 058, issue #191).

The arithmetic itself is `pack-unit-price.js`, which `test_order_capture.py`
already drives table-by-table on the capture page. What is new here is that the
same script runs on this form and that what it derives is what gets recorded.
"""

import pytest
from playwright.sync_api import expect


def open_purchase_form(page, live_server):
    products = live_server.add_test_products([{'description': 'Widget screws, M3 x 8'}])
    page.goto(f"{live_server.url}/products/{products[0].id}/purchases/new")
    page.fill("#vendor", "Acme")
    return page


@pytest.mark.e2e
def test_a_pack_works_out_the_quantity_and_unit_price(page, live_server):
    """US1 scenarios 1 and 2: no calculator, and the pack is what gets recorded"""
    open_purchase_form(page, live_server)
    page.fill("#packs", "2")
    page.fill("#pack_price", "13.23")
    page.fill("#pack_size", "100")

    expect(page.locator("#quantity")).to_have_value("200")
    expect(page.locator("#unit_price")).to_have_value("0.13")
    expect(page.locator("#unit-price-inexact")).to_contain_text("Rounded to the cent")

    page.click("#save-purchase-btn")

    cells = page.locator("#purchase-history .purchase-row td")
    expect(cells.nth(2)).to_have_text("200")
    expect(cells.nth(3)).to_have_text("$0.13")


@pytest.mark.e2e
def test_a_typed_quantity_is_recorded_over_the_derived_one(page, live_server):
    """US1 scenario 3: the derived value is a default, not a decision"""
    open_purchase_form(page, live_server)
    page.fill("#pack_price", "13.23")
    page.fill("#pack_size", "100")
    expect(page.locator("#quantity")).to_have_value("100")

    page.fill("#quantity", "96")
    page.click("#save-purchase-btn")

    cells = page.locator("#purchase-history .purchase-row td")
    expect(cells.nth(2)).to_have_text("96")
    expect(cells.nth(3)).to_have_text("$0.13")
