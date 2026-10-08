"""E2E: editing a purchase and an order (feature 061, issue #192).

**Waiting note.** Both screens are plain forms that POST and redirect; nothing
here fires a `fetch` or renders client-side. Every wait is an `expect()` on the
page a navigation lands on -- the flash, a row, a field's value. `#order-lines`
and `#purchase-history` are established before anything counts their rows.

Purchases are seeded straight into the database; capture is not under test.
"""

from datetime import datetime

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService

VENDOR = "Amazon"
ORDER = "111-9281973-9357866"
FLASH = ".alert-success.alert-dismissible"


def seed(live_server):
    """A product with a count of 5 and one received line of an order."""
    service = CatalogService(live_server.storage)
    product = service.create_product(description="ELECROW ESP32 E-Ink 4.2in")
    service.set_quantity(product.id, 5)
    purchase = service.record_purchase(
        product.id, vendor=VENDOR, vendor_item_id="B0G43FCHFX",
        order_date=datetime(2026, 7, 23), received_date=datetime(2026, 7, 25),
        quantity=1, unit_price="13.23", supplier_order_reference=ORDER,
    )
    return service, product, purchase


def open_order(page, live_server, order=ORDER, rows=1):
    page.goto(f"{live_server.url}/products/orders/{VENDOR}/{order}")
    expect(page.locator("#order-lines tbody tr.order-line")).to_have_count(rows)


@pytest.mark.e2e
def test_correct_a_purchase_from_the_product_page(page, live_server):
    """US1: the form is pre-filled, the save lands, the count does not move."""
    service, product, purchase = seed(live_server)

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#purchase-history .purchase-row")).to_have_count(1)
    page.locator(".edit-purchase-btn").click()

    expect(page.locator("#quantity")).to_have_value("1")
    expect(page.locator("#unit_price")).to_have_value("13.23")
    page.locator("#quantity").fill("100")
    page.locator("#unit_price").fill("0.13")
    page.locator("#pack_size").fill("100")
    page.locator("#pack_price").fill("13.23")
    page.locator("#save-purchase-edit-btn").click()

    expect(page.locator(FLASH)).to_contain_text("Purchase updated.")
    row = page.locator("#purchase-history .purchase-row")
    expect(row).to_contain_text("100")
    expect(row).to_contain_text("$0.13")
    stored = service.get_purchase(purchase.id)
    assert stored.pack_size == 100
    assert service.get_product(product.id).quantity == 5


@pytest.mark.e2e
def test_correct_a_line_from_the_order_page_and_land_back_on_it(page, live_server):
    """US1 scenario 3: still the same line of the same order."""
    _, _, purchase = seed(live_server)

    open_order(page, live_server)
    page.locator(".edit-purchase-btn").click()
    page.locator("#quantity").fill("3")
    page.locator("#save-purchase-edit-btn").click()

    expect(page.locator(FLASH)).to_contain_text("Purchase updated.")
    line = page.locator(f'tr.order-line:has(a[href*="/purchases/{purchase.id}/edit"])')
    expect(line).to_have_count(1)
    expect(line.locator("td.text-end").first).to_have_text("3")


@pytest.mark.e2e
def test_a_refused_save_keeps_what_was_typed(page, live_server):
    """FR-006"""
    service, _, purchase = seed(live_server)

    page.goto(f"{live_server.url}/purchases/{purchase.id}/edit")
    page.locator("#notes").fill("typed this")
    page.locator("#pack_size").fill("10")
    page.locator("#save-purchase-edit-btn").click()

    expect(page.locator(".alert-danger")).to_contain_text("pack")
    expect(page.locator("#notes")).to_have_value("typed this")
    assert service.get_purchase(purchase.id).notes is None


@pytest.mark.e2e
def test_reattach_a_hand_recorded_purchase_to_its_order(page, live_server):
    """US2: the case the issue names."""
    service, product, _ = seed(live_server)
    hand = service.record_purchase(product.id, vendor=VENDOR, quantity=2)

    page.goto(f"{live_server.url}/purchases/{hand.id}/edit")
    expect(page.locator("#receive-instead")).to_be_visible()
    page.locator("#supplier_order_reference").fill(ORDER)
    page.locator("#order_line_number").fill("2")
    page.locator("#save-purchase-edit-btn").click()
    expect(page.locator(FLASH)).to_contain_text("Purchase updated.")

    open_order(page, live_server, rows=2)
    expect(page.locator('tr.order-line[data-line="2"]')).to_have_count(1)


@pytest.mark.e2e
def test_edit_an_order_date_and_number(page, live_server):
    """US3: every line, one save, lands at the new address."""
    service, product, _ = seed(live_server)
    service.record_purchase(
        product.id, vendor=VENDOR, order_date=datetime(2026, 7, 23),
        quantity=2, supplier_order_reference=ORDER,
    )

    open_order(page, live_server, rows=2)
    page.locator("#edit-order-btn").click()
    expect(page.locator("#edit-order-line-count")).to_have_text("2")
    page.locator("#order_number").fill("RENAMED-1")
    page.locator("#order_date").fill("2026-07-22")
    page.locator("#save-order-edit-btn").click()

    expect(page.locator(FLASH)).to_contain_text("Updated 2 line(s) of the order.")
    expect(page.locator("#order-lines tbody tr.order-line")).to_have_count(2)
    assert page.url.endswith(f"/products/orders/{VENDOR}/RENAMED-1")
    lines = service.find_order_lines_for(VENDOR, "RENAMED-1")
    assert {p.order_date for p in lines} == {datetime(2026, 7, 22)}
