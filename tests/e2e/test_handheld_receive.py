"""E2E: handheld receive (feature 068, US6; US1 scenario 3).

A distributor label scanned on the handheld lands on a one-line receive screen
with the label's quantity, the quantity, the counted choice and Receive all
above the fixed action bar at 360x512. Several candidates get a choice page,
none outstanding says so, and every result is checked on the desktop pages
(SC-005).

**Waiting note.** A scan fires ``POST /api/scan`` and then navigates on its
``url``, so every scan is waited on through ``to_have_url`` on the destination.
Receive is a plain form post that redirects with a flash, so the flash on the
handheld product screen is the signal for the POST.

Author: Jason Antman, 2026.
"""

import re

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.handheld import (
    LONG_DESCRIPTION,
    ORDER_NUMBERS,
    assert_handheld_layout,
    assert_scan_entry_no_keyboard,
    scan,
    scan_label,
)

SCAN = "#handheld-scan-input"
RECEIVE = "#handheld-receive-btn"
FLASH_OK = ".alert-success.alert-dismissible"
FLASH_INFO = ".alert-info.alert-dismissible"

DIGIKEY_ORDER = ORDER_NUMBERS["DigiKey"]
DIGIKEY_PART = "1866-3032-ND"
MCMASTER_PART = "97387A173"
RS, GS, EOT = "\x1e", "\x1d", "\x04"


def bag_label(quantity: str = "5") -> str:
    """A DigiKey bag label naming DIGIKEY_ORDER's DIGIKEY_PART line."""
    return (
        "[)>" + RS + "06" + GS
        + f"P{DIGIKEY_PART}" + GS
        + "1PIRM-10-5" + GS
        + f"1K{DIGIKEY_ORDER}" + GS
        + "10K130599231" + GS
        + f"Q{quantity}" + GS
        + "4LCN"
        + RS + EOT
    )


def seed_digikey_line(live_server, description: str = "AC/DC converter 5V 10W",
                      quantity: int | None = 4, ordered: int = 10):
    service = CatalogService(live_server.storage)
    product = service.create_product(description=description, quantity=quantity)
    purchase = service.record_purchase(
        product.id, vendor="DigiKey", vendor_item_id=DIGIKEY_PART,
        supplier_order_reference=DIGIKEY_ORDER, quantity=ordered,
    )
    return service, product, purchase


def assert_above_action_bar(page, selector: str) -> None:
    """In the viewport is not enough: the fixed action bar covers its bottom."""
    box = page.locator(selector).bounding_box()
    bar = page.locator("#handheld-action-bar").bounding_box()
    assert box["y"] + box["height"] <= bar["y"], (selector, box, bar)


def open_landing(page, live_server) -> None:
    page.goto(f"{live_server.url}/h/")
    assert_scan_entry_no_keyboard(page, SCAN)


def assert_desktop_received(page, live_server, purchase_id: int, received: bool) -> None:
    """SC-005: the desktop receipt page says whether it was received."""
    page.goto(f"{live_server.url}/purchases/{purchase_id}/receive")
    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    expect(page.locator("#already-received")).to_have_count(1 if received else 0)


@pytest.mark.e2e
@pytest.mark.parametrize("long_data", [False, True], ids=["short", "long"])
def test_a_one_line_label_opens_the_receive_screen_prefilled(
    handheld_page, live_server, long_data
):
    """US6 scenario 1, US1 scenario 3 (FR-021, FR-006, FR-007)"""
    page = handheld_page
    _, _, purchase = seed_digikey_line(
        live_server, description=LONG_DESCRIPTION if long_data else "AC/DC converter 5V 10W"
    )
    open_landing(page, live_server)

    scan_label(page, bag_label(quantity="5"))

    expect(page).to_have_url(re.compile(rf"/h/receive/{purchase.id}\?quantity=5$"))
    expect(page.locator("#quantity")).to_have_value("5")
    expect(page.locator("#handheld-receive-ordered")).to_contain_text("Ordered 10")
    assert_scan_entry_no_keyboard(page, SCAN)
    for selector in ("#quantity", "#handheld-counted-card"):
        expect(page.locator(selector)).to_be_in_viewport()
        assert_above_action_bar(page, selector)
    assert_handheld_layout(page, SCAN, RECEIVE)


@pytest.mark.e2e
def test_a_counted_receipt_updates_the_count_as_on_desktop(handheld_page, live_server):
    """US6 scenario 2 (FR-021): the count rises by what arrived."""
    page = handheld_page
    _, product, purchase = seed_digikey_line(live_server, quantity=4)
    open_landing(page, live_server)
    scan_label(page, bag_label(quantity="5"))
    expect(page.locator("#quantity")).to_have_value("5")

    page.locator("#handheld-counted-card").click()
    expect(page.locator("#counted")).to_be_checked()
    page.locator(RECEIVE).click()

    expect(page).to_have_url(re.compile(rf"/h/product/{product.id}$"))
    expect(page.locator(FLASH_OK)).to_contain_text("Received.")

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#quantity-value")).to_have_text("9")
    assert_desktop_received(page, live_server, purchase.id, received=True)


@pytest.mark.e2e
def test_several_candidates_get_a_choice_and_nothing_is_received(handheld_page, live_server):
    """US6 scenario 3 (FR-022)"""
    page = handheld_page
    service = CatalogService(live_server.storage)
    product = service.create_product(description="Rivets")
    first, second = (
        service.record_purchase(product.id, vendor="McMaster-Carr", vendor_item_id=MCMASTER_PART,
                                supplier_order_reference=order, quantity=100)
        for order in ("7319PDRK4", "7402QXRT1")
    )
    open_landing(page, live_server)

    scan(page, MCMASTER_PART)

    expect(page).to_have_url(re.compile(rf"/h/receive/choose\?scan={MCMASTER_PART}$"))
    candidates = page.locator(".receive-candidate")
    expect(candidates).to_have_count(2)
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1

    candidates.filter(has_text="7402QXRT1").click()
    expect(page).to_have_url(re.compile(rf"/h/receive/{second.id}$"))
    expect(page.locator(RECEIVE)).to_be_visible()

    for purchase in (first, second):
        assert_desktop_received(page, live_server, purchase.id, received=False)


@pytest.mark.e2e
def test_nothing_outstanding_says_so_and_receives_nothing_twice(handheld_page, live_server):
    """US6 scenario 4"""
    page = handheld_page
    service, product, purchase = seed_digikey_line(live_server, quantity=4)
    service.receive_purchase(purchase.id)
    open_landing(page, live_server)

    scan_label(page, bag_label())

    expect(page).to_have_url(re.compile(rf"/h/orders/DigiKey/{DIGIKEY_ORDER}\?highlight="))
    expect(page.locator(FLASH_INFO)).to_contain_text("is already received")
    line = page.locator(".order-line")
    expect(line).to_have_count(1)
    expect(line).to_contain_text("received")
    expect(page.locator(".order-line-checkbox")).to_have_count(0)

    # Its receive screen offers no Receive either.
    page.goto(f"{live_server.url}/h/receive/{purchase.id}")
    expect(page.locator("#handheld-already-received")).to_be_visible()
    expect(page.locator(RECEIVE)).to_have_count(0)

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#quantity-value")).to_have_text("14")


@pytest.mark.e2e
def test_receive_from_the_product_screen(handheld_page, live_server):
    """US6 scenario 5"""
    page = handheld_page
    _, product, purchase = seed_digikey_line(live_server, quantity=None)
    page.goto(f"{live_server.url}/h/product/{product.id}")
    expect(page.locator("#handheld-product-outstanding")).to_be_visible()

    page.locator(f'.handheld-outstanding-purchase[data-purchase="{purchase.id}"] '
                 ".handheld-receive-link").click()

    expect(page).to_have_url(re.compile(rf"/h/receive/{purchase.id}$"))
    expect(page.locator("#quantity")).to_have_value("10")
    # An untracked product has no count for "counted" to be about.
    expect(page.locator("#counted")).to_have_count(0)
    page.locator(RECEIVE).click()

    expect(page.locator(FLASH_OK)).to_contain_text("Received.")
    expect(page.locator("#handheld-product-outstanding")).to_have_count(0)
    assert_desktop_received(page, live_server, purchase.id, received=True)
