"""E2E: bulk receive and bulk label printing on the order page (feature 060, #194).

**Waiting note.** Receiving is a plain form POST that redirects, so its waits
are on the page it lands on: the flash and the line badges, established with
`expect()`. Label printing is the shared dialog; its run is complete when the
Done button shows (rendered after the loop's last await), as in
test_bulk_label_printing_products.py. The rows are server-rendered and
`#order-lines` is established before any count or negative assertion.

Purchases are seeded straight into the database; the capture flow is not what
is under test.
"""

import re
from datetime import datetime

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.waits import wait_for_modal_shown, wait_for_select_populated

VENDOR = "McMaster-Carr"
ORDER = "7001BULK"
MODAL = "orderBulkLabelPrintingModal"
SELECT = "order-bulk-label-type"
PRINT_BTN = "#order-bulk-print-all-btn"
DONE_BTN = "#order-bulk-print-done-btn"
# The flash, not the order-progress box, which is also green once all is in.
FLASH = ".alert-success.alert-dismissible"


def seed(live_server, *lines):
    """One order of (description, quantity) lines; returns (service, purchases).

    A description repeated reuses its product, so two lines can name one.
    """
    service = CatalogService(live_server.storage)
    products = {}
    purchases = []
    for description, quantity in lines:
        if description not in products:
            products[description] = service.create_product(description=description)
            service.set_quantity(products[description].id, 2)
        purchases.append(service.record_purchase(
            products[description].id, vendor=VENDOR, vendor_item_id=description,
            order_date=datetime(2026, 9, 1), quantity=quantity,
            supplier_order_reference=ORDER,
        ))
    return service, purchases


def open_order(page, live_server, rows):
    page.goto(f"{live_server.url}/products/orders/{VENDOR}/{ORDER}")
    expect(page.locator("#order-lines tbody tr.order-line")).to_have_count(rows)


def tick(page, purchase):
    page.locator(f'input.order-line-checkbox[value="{purchase.id}"]').check()


def row(page, purchase):
    return page.locator(f'tr.order-line:has(input[value="{purchase.id}"])')


def state(page, purchase):
    """The line's state badge; a McMaster row also carries a details badge."""
    return row(page, purchase).locator(".badge", has_text=re.compile(r"^(received|outstanding)$"))


@pytest.mark.e2e
def test_receive_ticked_lines_on_a_date(page, live_server):
    """US1: two of three received on the chosen date, third still outstanding."""
    service, (washer, nut, bolt) = seed(
        live_server, ("Washer", 10), ("Nut", 25), ("Bolt", 5))

    open_order(page, live_server, 3)
    tick(page, washer)
    tick(page, nut)
    page.locator("#bulk-received-date").fill("2026-10-03")
    page.locator("#order-receive-btn").click()

    expect(page.locator(FLASH, has_text="Received 2 line(s).")).to_be_visible()
    expect(state(page, washer)).to_have_text("received")
    expect(row(page, washer)).to_contain_text("3 Oct 2026")
    expect(state(page, nut)).to_have_text("received")
    expect(state(page, bolt)).to_have_text("outstanding")
    expect(page.locator("#outstanding-count")).to_have_text("1 of 3 still outstanding.")

    assert service.get_product(washer.product_id).quantity == 12


@pytest.mark.e2e
def test_already_received_lines_are_reported_as_skipped(page, live_server):
    """US1 edge case: a received line ticked again is left alone."""
    service, (washer, nut) = seed(live_server, ("Washer", 10), ("Nut", 25))
    service.receive_purchase(washer.id)

    open_order(page, live_server, 2)
    page.locator("#order-select-all").check()
    page.locator("#order-receive-btn").click()

    expect(page.locator(FLASH)).to_contain_text(
        "Received 1 line(s). 1 already received, skipped.")
    expect(page.locator("#outstanding-count")).to_have_text("All 2 line(s) received.")


@pytest.mark.e2e
def test_labels_print_once_per_distinct_product(page, live_server):
    """US2: two lines naming one product print it once."""
    _, (first, again, other) = seed(
        live_server, ("Washer", 10), ("Washer", 5), ("Nut", 25))
    posts = []

    def record(request):
        match = re.search(r"/api/products/(\d+)/label$", request.url)
        if match and request.method == "POST":
            posts.append(match.group(1))

    page.on("request", record)

    open_order(page, live_server, 3)
    tick(page, first)
    tick(page, again)
    tick(page, other)
    page.locator("#order-print-labels-btn").click()
    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

    items = page.locator("#order-bulk-label-items-list li")
    expect(items).to_have_count(2)

    page.locator(f"#{SELECT}").select_option("Sato 2x4")
    expect(page.locator(PRINT_BTN)).to_be_enabled()
    page.locator(PRINT_BTN).click()
    expect(page.locator(DONE_BTN)).to_be_visible()

    assert sorted(posts) == sorted([str(first.product_id), str(other.product_id)])
    expect(page.locator("#order-bulk-print-status")).to_have_text(
        "Complete: 2 labels for 2 products, 0 failed")


@pytest.mark.e2e
def test_selection_arms_the_actions(page, live_server):
    """US3: nothing ticked, nothing to press; select-all ticks every line."""
    _, (washer, nut) = seed(live_server, ("Washer", 10), ("Nut", 25))

    open_order(page, live_server, 2)
    expect(page.locator("#order-print-labels-btn")).to_be_disabled()
    expect(page.locator("#order-receive-btn")).to_be_disabled()

    tick(page, washer)
    expect(page.locator("#order-selected-count")).to_have_text("1")
    expect(page.locator("#order-receive-btn")).to_be_enabled()
    expect(page.locator("#order-print-labels-btn")).to_be_enabled()
    assert page.locator("#order-select-all").evaluate("el => el.indeterminate")

    page.locator("#order-select-all").check()
    expect(page.locator("input.order-line-checkbox:checked")).to_have_count(2)
    expect(page.locator("#order-selected-count")).to_have_text("2")
