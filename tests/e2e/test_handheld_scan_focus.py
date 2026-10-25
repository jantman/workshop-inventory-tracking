"""E2E: a scan always lands in the scan entry and never submits a form (feature 068).

DataWedge types into whatever holds focus and ends with Enter. After a tap on
a full-width checkbox card the next scan must still reach the scan entry, and
an Enter in any other field must not submit the screen's form: only the
action bar's buttons do (FR-002). A second scan on Shorten replaces the
first, and the in-page confirm answers one question at a time.

**Waiting note.** Each scan that lands in the scan entry has an observable
result -- a navigation (``to_have_url``) or Shorten's load filling
``#current-length`` (pattern C) -- and that result is what each test waits on
before checking that nothing was received or shortened. The one scan with no
result of its own (into the Quantity field) is checked through a ``submit``
listener: implicit submission fires ``submit`` synchronously while the Enter
is handled, and ``keyboard.press`` returns only after the page has handled it.

Author: Jason Antman, 2026.
"""

import re
from decimal import Decimal
from urllib.parse import quote

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.handheld import long_item, scan, wedge
from tests.e2e.waits import wait_for_modal_shown

SCAN = "[data-handheld-scan]"


def short_item(ja_id: str, length: str = "1000"):
    return long_item(ja_id, location="Rack 2", sub_location=None, length=Decimal(length))


def item_length(page, live_server, ja_id: str) -> tuple[float, int]:
    """The active length and the number of history rows."""
    item = page.request.get(f"{live_server.url}/api/items/{ja_id}").json()["item"]
    history = page.request.get(f"{live_server.url}/api/items/{ja_id}/history").json()
    return float(item["dimensions"]["length"]), history["total_items"]


def assert_desktop_received(page, live_server, purchase_id: int, received: bool) -> None:
    page.goto(f"{live_server.url}/purchases/{purchase_id}/receive")
    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    expect(page.locator("#already-received")).to_have_count(1 if received else 0)


def seed_receivable(live_server):
    service = CatalogService(live_server.storage)
    product = service.create_product(description="AC/DC converter 5V 10W", quantity=4)
    return service.record_purchase(
        product.id, vendor="DigiKey", vendor_item_id="1866-3032-ND",
        supplier_order_reference="88412377", quantity=10,
    )


@pytest.mark.e2e
def test_a_tapped_order_card_does_not_catch_the_next_scan(handheld_page, live_server):
    """Order lines: a scan after ticking a card opens what was scanned, receives nothing."""
    page = handheld_page
    live_server.add_test_data([short_item("JA000701")])
    service = CatalogService(live_server.storage)
    for n in range(2):
        product = service.create_product(description=f"Widget {n}")
        service.record_purchase(product.id, vendor="Amazon", vendor_item_id=f"PART-{n}",
                                supplier_order_reference="113-1", quantity=1)
    page.goto(f"{live_server.url}/h/orders/Amazon/113-1")
    cards = page.locator(".order-line")
    expect(cards).to_have_count(2)

    cards.first.tap()
    expect(cards.first.locator(".order-line-checkbox")).to_be_checked()
    expect(page.locator("#handheld-order-receive-btn")).to_be_enabled()
    wedge(page, "JA000701")

    expect(page).to_have_url(f"{live_server.url}/h/item/JA000701")
    page.goto(f"{live_server.url}/products/orders/Amazon/{quote('113-1')}")
    expect(page.locator("#order-lines")).to_be_visible()
    expect(page.locator('.order-line[data-outstanding="true"]')).to_have_count(2)


@pytest.mark.e2e
def test_a_ticked_shorten_confirm_does_not_execute_on_the_next_scan(handheld_page, live_server):
    """Shorten: scanning JA B after ticking Confirm for JA A loads B; A is not shortened."""
    page = handheld_page
    live_server.add_test_data([short_item("JA000601"), short_item("JA000602", "800")])
    page.goto(f"{live_server.url}/h/shorten")
    scan(page, "JA000601")
    expect(page.locator("#current-length")).to_have_text("1000")
    page.locator("#new-length").fill("600")

    page.locator('label[for="confirm-operation"]').tap()
    expect(page.locator("#confirm-operation")).to_be_checked()
    expect(page.locator("#execute-shortening-btn")).to_be_enabled()
    wedge(page, "JA000602")

    expect(page.locator("#current-length")).to_have_text("800")
    expect(page.locator(SCAN)).to_have_value("JA000602")
    assert item_length(page, live_server, "JA000601") == (1000.0, 1)


@pytest.mark.e2e
def test_a_ticked_counted_box_does_not_catch_the_next_scan(handheld_page, live_server):
    """Receive: a scan after ticking "counted" opens what was scanned, receives nothing."""
    page = handheld_page
    live_server.add_test_data([short_item("JA000611")])
    purchase = seed_receivable(live_server)
    page.goto(f"{live_server.url}/h/receive/{purchase.id}")

    page.locator("#handheld-counted-card").tap()
    expect(page.locator("#counted")).to_be_checked()
    wedge(page, "JA000611")

    expect(page).to_have_url(f"{live_server.url}/h/item/JA000611")
    assert_desktop_received(page, live_server, purchase.id, received=False)


@pytest.mark.e2e
def test_a_scan_into_the_quantity_field_does_not_receive(handheld_page, live_server):
    """Receive: Enter in a tapped number field never submits (only Receive does)."""
    page = handheld_page
    purchase = seed_receivable(live_server)
    page.goto(f"{live_server.url}/h/receive/{purchase.id}")
    quantity = page.locator("#quantity")
    expect(quantity).to_have_value("10")

    quantity.tap()
    expect(quantity).to_be_focused()
    page.evaluate(
        "document.getElementById('handheld-receive-form')"
        ".addEventListener('submit', () => { window.__submitted = true; })"
    )
    wedge(page, "JA000612")

    # The digits landed in the field (letters are refused by a number input)...
    expect(quantity).to_have_value(re.compile("000612"))
    # ...and the Enter, already handled when press() returned, submitted nothing.
    assert page.evaluate("window.__submitted === true") is False
    assert_desktop_received(page, live_server, purchase.id, received=False)


@pytest.mark.e2e
def test_a_second_scan_on_shorten_replaces_the_first(handheld_page, live_server):
    """Shorten: after a prefill, a not-found scan or a load, the next scan replaces the entry."""
    page = handheld_page
    live_server.add_test_data([short_item("JA000621"), short_item("JA000622", "800")])
    entry = page.locator(SCAN)

    page.goto(f"{live_server.url}/h/shorten?ja_id=JA000621")
    expect(page.locator("#current-length")).to_have_text("1000")
    scan(page, "JA000699")
    expect(page.locator("#scanner-status")).to_have_text("Item Not Found")
    expect(entry).to_have_value("JA000699")

    scan(page, "JA000622")
    expect(page.locator("#current-length")).to_have_text("800")
    expect(entry).to_have_value("JA000622")

    scan(page, "JA000621")
    expect(page.locator("#current-length")).to_have_text("1000")
    expect(entry).to_have_value("JA000621")


@pytest.mark.e2e
def test_overlapping_confirms_get_one_answer(handheld_page, live_server):
    """A confirm asked while one is open is refused; one OK answers only the first."""
    page = handheld_page
    page.goto(f"{live_server.url}/h/")
    expect(page.locator(SCAN)).to_be_focused()

    page.evaluate(
        "() => { window.__answers = {};"
        " window.confirmAction('first').then((v) => { window.__answers.first = v; });"
        " window.confirmAction('second').then((v) => { window.__answers.second = v; }); }"
    )
    wait_for_modal_shown(page, "handheld-confirm-modal")
    expect(page.locator("#handheld-confirm-message")).to_have_text("first")
    page.locator("#handheld-confirm-ok").tap()

    page.wait_for_function("'first' in window.__answers && 'second' in window.__answers")
    assert page.evaluate("window.__answers") == {"first": True, "second": False}
