"""E2E: the Outstanding Products page (feature 062, issue #200).

**Waiting note.** Receiving is a plain form POST that redirects back here, so
its waits are on the page it lands on: the flash and the rows, established with
`expect()`. Label printing is the shared dialog; its run is complete when the
Done button shows (rendered after the loop's last await), as in
test_order_bulk_actions.py. The rows are server-rendered and `#order-lines` is
established before any count or negative assertion.

Purchases are seeded straight into the database; the capture flow is not what
is under test.
"""

import re
from datetime import datetime

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.waits import wait_for_modal_shown, wait_for_select_populated

MODAL = "orderBulkLabelPrintingModal"
SELECT = "order-bulk-label-type"
PRINT_BTN = "#order-bulk-print-all-btn"
DONE_BTN = "#order-bulk-print-done-btn"
FLASH_OK = ".alert-success.alert-dismissible"
FLASH_ERROR = ".alert-danger.alert-dismissible"
ROWS = "#order-lines tbody tr.outstanding-line"


def seed(live_server):
    """Two orders from two vendors, a received line on one, and a loose purchase.

    Returns the service and a dict of purchases by name.
    """
    service = CatalogService(live_server.storage)

    def line(description, vendor, order, order_date, quantity, product=None):
        if product is None:
            product = service.create_product(description=description)
            service.set_quantity(product.id, 2)
        return service.record_purchase(
            product.id, vendor=vendor, vendor_item_id=description,
            order_date=order_date, quantity=quantity,
            supplier_order_reference=order,
        )

    washer = line("Washer", "McMaster-Carr", "7001OUT", datetime(2026, 9, 1), 10)
    nut = line("Nut", "McMaster-Carr", "7001OUT", datetime(2026, 9, 1), 25)
    bolt = line("Bolt", "Amazon", "111-0000000-0000062", datetime(2026, 9, 20), 5)
    gone = line("Already here", "Amazon", "111-0000000-0000062", datetime(2026, 9, 20), 1)
    loose = line("Loose", "Hardware Store", None, datetime(2026, 9, 25), 3)
    # A second outstanding purchase of the washer, on the other order.
    washer_again = line("Washer", "Amazon", "111-0000000-0000062",
                        datetime(2026, 9, 20), 4,
                        product=service.get_product(washer.product_id))
    service.receive_purchase(gone.id, received_date="2026-09-22")
    return service, {
        "washer": washer, "nut": nut, "bolt": bolt, "gone": gone,
        "loose": loose, "washer_again": washer_again,
    }


def open_page(page, live_server, rows):
    page.goto(f"{live_server.url}/products/outstanding")
    expect(page.locator(ROWS)).to_have_count(rows)


def checkbox(page, purchase):
    return page.locator(f'input.order-line-checkbox[value="{purchase.id}"]')


def row(page, purchase):
    return page.locator(f'tr.outstanding-line[data-purchase-id="{purchase.id}"]')


@pytest.mark.e2e
def test_lists_every_outstanding_line_across_orders(page, live_server):
    """US1: every order's outstanding lines and the loose one; no received line."""
    _, p = seed(live_server)

    open_page(page, live_server, 5)
    expect(page.locator("#outstanding-summary")).to_contain_text(
        "5 line(s) outstanding across 2 order(s).")
    expect(row(page, p["gone"])).to_have_count(0)

    # Oldest order first; the loose purchase last.
    expect(page.locator(ROWS).first).to_have_attribute(
        "data-purchase-id", str(p["washer"].id))
    expect(page.locator(ROWS).last).to_have_attribute(
        "data-purchase-id", str(p["loose"].id))
    expect(row(page, p["loose"]).locator(".no-order")).to_have_text("no order")

    row(page, p["bolt"]).locator("a.order-link").click()
    expect(page).to_have_url(re.compile(r"/products/orders/Amazon/111-0000000-0000062$"))


@pytest.mark.e2e
def test_receive_lines_from_two_orders_at_once(page, live_server):
    """US2: one line from each order received on the chosen date."""
    service, p = seed(live_server)

    open_page(page, live_server, 5)
    checkbox(page, p["washer"]).check()
    checkbox(page, p["bolt"]).check()
    page.locator("#bulk-received-date").fill("2026-10-03")
    page.locator("#order-receive-btn").click()

    expect(page.locator(FLASH_OK, has_text="Received 2 line(s).")).to_be_visible()
    expect(page.locator(ROWS)).to_have_count(3)
    expect(row(page, p["washer"])).to_have_count(0)
    expect(row(page, p["bolt"])).to_have_count(0)
    expect(row(page, p["nut"])).to_have_count(1)

    assert service.get_purchase(p["washer"].id).received_date == datetime(2026, 10, 3)
    assert service.get_purchase(p["bolt"].id).received_date == datetime(2026, 10, 3)
    assert service.get_product(p["washer"].product_id).quantity == 12


@pytest.mark.e2e
def test_a_refused_date_receives_nothing(page, live_server):
    """US2 edge case: too early for one ticked line, so none is received."""
    service, p = seed(live_server)

    open_page(page, live_server, 5)
    checkbox(page, p["washer"]).check()
    checkbox(page, p["bolt"]).check()
    # After the McMaster order, before the Amazon one.
    page.locator("#bulk-received-date").fill("2026-09-10")
    page.locator("#order-receive-btn").click()

    expect(page.locator(FLASH_ERROR, has_text="Nothing was received")).to_be_visible()
    expect(page.locator(ROWS)).to_have_count(5)
    assert service.get_purchase(p["washer"].id).received_date is None


@pytest.mark.e2e
def test_labels_print_once_per_product_across_orders(page, live_server):
    """US3: the washer is on both orders and is printed once."""
    _, p = seed(live_server)
    posts = []

    def record(request):
        match = re.search(r"/api/products/(\d+)/label$", request.url)
        if match and request.method == "POST":
            posts.append(match.group(1))

    page.on("request", record)

    open_page(page, live_server, 5)
    checkbox(page, p["washer"]).check()
    checkbox(page, p["washer_again"]).check()
    checkbox(page, p["bolt"]).check()
    page.locator("#order-print-labels-btn").click()
    wait_for_modal_shown(page, MODAL)
    wait_for_select_populated(page, SELECT)

    expect(page.locator("#order-bulk-label-items-list li")).to_have_count(2)

    page.locator(f"#{SELECT}").select_option("Sato 2x4")
    expect(page.locator(PRINT_BTN)).to_be_enabled()
    page.locator(PRINT_BTN).click()
    expect(page.locator(DONE_BTN)).to_be_visible()

    assert sorted(posts) == sorted([str(p["washer"].product_id), str(p["bolt"].product_id)])
    expect(page.locator("#order-bulk-print-status")).to_have_text(
        "Complete: 2 labels for 2 products, 0 failed")


@pytest.mark.e2e
def test_selection_arms_the_actions(page, live_server):
    """US4: nothing ticked, nothing to press; select-all ticks every row."""
    _, p = seed(live_server)

    open_page(page, live_server, 5)
    expect(page.locator("#order-print-labels-btn")).to_be_disabled()
    expect(page.locator("#order-receive-btn")).to_be_disabled()

    checkbox(page, p["nut"]).check()
    expect(page.locator("#order-selected-count")).to_have_text("1")
    expect(page.locator("#order-receive-btn")).to_be_enabled()
    expect(page.locator("#order-print-labels-btn")).to_be_enabled()

    page.locator("#order-select-all").check()
    expect(page.locator("input.order-line-checkbox:checked")).to_have_count(5)
    expect(page.locator("#order-selected-count")).to_have_text("5")


@pytest.mark.e2e
def test_reachable_from_the_products_menu(page, live_server):
    """US4: Products -> Outstanding Products."""
    page.goto(f"{live_server.url}/products")
    expect(page.locator("#products-nav")).to_be_visible()

    page.click("#products-nav")
    link = page.locator('a[href="/products/outstanding"]')
    expect(link).to_be_visible()
    link.click()

    expect(page.locator("#order-lines, #nothing-outstanding")).to_be_visible()
