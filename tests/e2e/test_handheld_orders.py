"""E2E: handheld orders (feature 068, US7).

A captured order's lines are full-width selectable cards at 360x512, Receive
Selected stays in the fixed action bar, and exactly the selected lines are
received -- checked on the desktop order page (SC-005). The order list shows
only orders with outstanding lines, and the product screen's Order button
reaches them.

**Waiting note.** Selecting a card is a native checkbox change; the inline
script enables Receive Selected and counts the selection synchronously, so
``to_be_checked`` and the count badge are the signals. Receive Selected is a
plain form post that redirects back with a flash, so the flash is the signal
for the POST.

Author: Jason Antman, 2026.
"""

import re
from datetime import datetime
from urllib.parse import quote

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.handheld import (
    LONG_DESCRIPTION,
    LONG_VENDOR,
    ORDER_NUMBERS,
    assert_handheld_layout,
    assert_scan_entry_no_keyboard,
    scan_label,
)

SCAN = "#handheld-scan-input"
RECEIVE_SELECTED = "#handheld-order-receive-btn"
FLASH_OK = ".alert-success.alert-dismissible"

# A vendor name with a slash cannot be an order URL segment on the desktop
# either (the default route converter), so the long vendor drops it.
VENDOR = LONG_VENDOR.replace(" / ", " and ")
ORDER = ORDER_NUMBERS["Amazon"]


def seed_order(live_server, vendor: str = VENDOR, order: str = ORDER, lines: int = 3,
               order_date: datetime | None = None, product=None):
    service = CatalogService(live_server.storage)
    purchases = []
    for n in range(lines):
        line_product = product or service.create_product(
            description=f"{LONG_DESCRIPTION[:200]} #{n}"
        )
        purchases.append(service.record_purchase(
            line_product.id, vendor=vendor, vendor_item_id=f"PART-{n}",
            supplier_order_reference=order, quantity=n + 1, order_date=order_date,
        ))
    return service, purchases


def order_url(live_server, vendor: str = VENDOR, order: str = ORDER) -> str:
    return f"{live_server.url}/h/orders/{quote(vendor)}/{quote(order)}"


def desktop_outstanding_parts(page, live_server, vendor: str = VENDOR,
                              order: str = ORDER) -> list[str]:
    """SC-005: the outstanding lines, as the desktop order page reports them."""
    page.goto(f"{live_server.url}/products/orders/{quote(vendor)}/{quote(order)}")
    expect(page.locator("#order-lines")).to_be_visible()
    return page.locator('.order-line[data-outstanding="true"]').evaluate_all(
        "rows => rows.map(r => r.dataset.part)"
    )


@pytest.mark.e2e
def test_selected_cards_and_only_they_are_received(handheld_page, live_server):
    """US7 scenarios 1-2 (FR-023, FR-008, FR-006, FR-007)"""
    page = handheld_page
    _, purchases = seed_order(live_server)
    page.goto(order_url(live_server))
    cards = page.locator(".order-line")
    expect(cards).to_have_count(3)
    assert_scan_entry_no_keyboard(page, SCAN)
    assert_handheld_layout(page, SCAN, RECEIVE_SELECTED)
    expect(page.locator(RECEIVE_SELECTED)).to_be_disabled()

    # Tap the cards' text, not the checkboxes: the whole card is the target.
    for index in (0, 2):
        card = cards.nth(index)
        card.scroll_into_view_if_needed()
        box = card.bounding_box()
        assert box["width"] >= 300 and box["height"] >= 44, box
        card.locator(".small").first.click()
        expect(card.locator(".order-line-checkbox")).to_be_checked()
    expect(cards.nth(1).locator(".order-line-checkbox")).not_to_be_checked()
    expect(page.locator("#handheld-order-selected-count")).to_have_text("2")

    page.locator(RECEIVE_SELECTED).click()

    expect(page.locator(FLASH_OK)).to_contain_text("Received 2 line(s).")
    expect(page.locator(".order-line-checkbox")).to_have_count(1)
    assert desktop_outstanding_parts(page, live_server) == [purchases[1].vendor_item_id]


@pytest.mark.e2e
def test_received_lines_cannot_be_selected(handheld_page, live_server):
    """US7 scenario 3"""
    page = handheld_page
    service, purchases = seed_order(live_server)
    service.receive_purchase(purchases[0].id)
    page.goto(order_url(live_server))

    cards = page.locator(".order-line")
    expect(cards).to_have_count(3)
    received = page.locator('.order-line[data-outstanding="false"]')
    expect(received).to_have_count(1)
    expect(received).to_contain_text("received")
    expect(received.locator("input")).to_have_count(0)
    expect(page.locator(".order-line-checkbox")).to_have_count(2)


@pytest.mark.e2e
def test_the_order_list_shows_only_orders_with_outstanding_lines(handheld_page, live_server):
    """US7 scenario 4 (FR-023a)"""
    page = handheld_page
    seed_order(live_server, lines=2, order_date=datetime(2026, 9, 1))
    service, done = seed_order(live_server, vendor="DigiKey", order="77000001", lines=1)
    service.receive_purchase(done[0].id)

    page.goto(f"{live_server.url}/h/")
    page.locator("#landing-orders").click()

    expect(page).to_have_url(re.compile(r"/h/orders$"))
    rows = page.locator(".handheld-order-row")
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text(ORDER)
    expect(rows).to_contain_text(VENDOR)
    expect(rows.locator(".handheld-order-outstanding")).to_have_text("2 outstanding")
    assert_handheld_layout(page, SCAN, "#handheld-home-btn")

    rows.click()
    expect(page.locator("#handheld-order-number")).to_have_text(f"Order {ORDER}")
    expect(page.locator(".order-line-checkbox")).to_have_count(2)


@pytest.mark.e2e
def test_the_product_screen_order_button(handheld_page, live_server):
    """US7 scenario 5 (FR-023b): one order opens it; two offer the choice."""
    page = handheld_page
    service = CatalogService(live_server.storage)
    product = service.create_product(description="Widget on order")
    seed_order(live_server, lines=1, product=product)
    page.goto(f"{live_server.url}/h/product/{product.id}")
    expect(page.locator("#stock-card")).to_be_visible()

    page.locator("#handheld-order-btn").click()
    expect(page.locator("#handheld-order-number")).to_have_text(f"Order {ORDER}")

    seed_order(live_server, vendor="DigiKey", order="88412377", lines=1, product=product)
    page.goto(f"{live_server.url}/h/product/{product.id}")
    expect(page.locator("#stock-card")).to_be_visible()
    page.locator("#handheld-order-btn").click()
    choices = page.locator(".handheld-order-link")
    expect(choices).to_have_count(2)
    expect(choices.last).to_be_in_viewport()

    choices.filter(has_text="88412377").click()
    expect(page.locator("#handheld-order-number")).to_have_text("Order 88412377")
    expect(page.locator("#handheld-order-vendor")).to_have_text("DigiKey")


@pytest.mark.e2e
def test_a_multi_line_label_opens_the_order_with_the_line_highlighted(handheld_page, live_server):
    """US7 scan entry (FR-022): highlighted, nothing selected."""
    page = handheld_page
    service = CatalogService(live_server.storage)
    product = service.create_product(description="AC/DC converter 5V 10W")
    order = ORDER_NUMBERS["DigiKey"]
    for _ in range(2):
        service.record_purchase(product.id, vendor="DigiKey", vendor_item_id="1866-3032-ND",
                                supplier_order_reference=order, quantity=5)
    service.record_purchase(product.id, vendor="DigiKey", vendor_item_id="1866-3027-ND",
                            supplier_order_reference=order, quantity=5)
    rs, gs, eot = "\x1e", "\x1d", "\x04"
    label = (
        "[)>" + rs + "06" + gs + "P1866-3032-ND" + gs + "1PIRM-10-5" + gs
        + f"1K{order}" + gs + "10K130599231" + gs + "Q5" + gs + "4LCN" + rs + eot
    )
    page.goto(f"{live_server.url}/h/")
    assert_scan_entry_no_keyboard(page, SCAN)

    scan_label(page, label)

    expect(page).to_have_url(re.compile(rf"/h/orders/DigiKey/{order}\?highlight=1866-3032-ND$"))
    expect(page.locator(".order-line")).to_have_count(3)
    expect(page.locator(".order-line.handheld-highlight")).to_have_count(2)
    expect(page.locator(".order-line-checkbox:checked")).to_have_count(0)
    expect(page.locator(RECEIVE_SELECTED)).to_be_disabled()
