"""E2E: the handheld landing page and scan routing (feature 068, US1).

At the TC52's 360x512 touch viewport, a scan typed on ``/h/`` with nothing
tapped first opens the right screen: a JA ID the handheld item screen, a WIT
code or known retail GTIN the handheld product screen, and anything the
handheld has no screen for (create, search) the desktop page.

**Waiting note.** A scan is resolved by a ``fetch`` to /api/scan and then a
navigation, so every scan is waited on with ``to_have_url`` for where it lands.
``scan()`` waits for the scan entry to hold focus before typing, since
handheld.js focuses it on DOMContentLoaded. US1 scenario 3 (receive) is in
test_handheld_receive.py.

Author: Jason Antman, 2026.
"""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.handheld import (
    assert_handheld_layout,
    assert_scan_entry_no_keyboard,
    long_product,
    scan,
)

SCAN = "#handheld-scan-input"
ITEM = {
    "ja_id": "JA300001",
    "item_type": "Bar",
    "shape": "Round",
    "material": "Carbon Steel",
    "length": 1000,
    "width": 25,
    "location": "M1-A",
    "active": True,
}
KNOWN_GTIN = "012345678905"
UNKNOWN_GTIN = "036000291452"


def open_landing(page, live_server):
    page.goto(f"{live_server.url}/h/")
    expect(page.locator(SCAN)).to_be_visible()
    assert_scan_entry_no_keyboard(page, SCAN)


@pytest.mark.e2e
def test_a_ja_id_opens_the_handheld_item_screen(handheld_page, live_server):
    """US1 scenario 1"""
    page = handheld_page
    live_server.add_test_data([ITEM])
    open_landing(page, live_server)

    scan(page, "JA300001")

    expect(page).to_have_url(f"{live_server.url}/h/item/JA300001")
    expect(page.locator("#handheld-item-ja-id")).to_have_text("JA300001")
    assert_scan_entry_no_keyboard(page, SCAN)


@pytest.mark.e2e
def test_a_wit_code_and_a_retail_gtin_open_the_handheld_product_screen(
    handheld_page, live_server
):
    """US1 scenario 2, against a 255-character description (FR-006)"""
    page = handheld_page
    product = live_server.add_test_products([long_product(
        identifiers=[{"id_type": "GTIN", "value": KNOWN_GTIN}],
    )])[0]
    product_url = f"{live_server.url}/h/product/{product.id}"

    for code in (product.internal_code, KNOWN_GTIN):
        open_landing(page, live_server)
        scan(page, code)

        expect(page).to_have_url(product_url)
        expect(page.locator("#handheld-product-description")).to_have_text(product.description)
        assert_scan_entry_no_keyboard(page, SCAN)
        # Label, in the fixed action bar (research.md D12).
        assert_handheld_layout(page, SCAN, "#print-product-label-btn")


@pytest.mark.e2e
def test_create_and_search_outcomes_open_the_desktop_pages(handheld_page, live_server):
    """US1 scenario 4: the handheld has no create or search screen (FR-003)"""
    page = handheld_page

    open_landing(page, live_server)
    scan(page, UNKNOWN_GTIN)
    expect(page).to_have_url(re.compile(r"/products/new\?.*identifier=00036000291452"))

    open_landing(page, live_server)
    scan(page, "hex bolt")
    expect(page).to_have_url(re.compile(r"/products\?q=hex(\+|%20)bolt$"))


@pytest.mark.e2e
def test_the_landing_layout(handheld_page, live_server):
    """US1 scenario 5: scan entry and the four tasks on screen, no sideways scroll"""
    page = handheld_page
    open_landing(page, live_server)

    assert_handheld_layout(page, SCAN, "#landing-move-items")
    expected = {
        "#landing-move-items": "/h/move?kind=items",
        "#landing-move-products": "/h/move?kind=products",
        "#landing-shorten": "/h/shorten",
        "#landing-orders": "/h/orders",
    }
    for selector, href in expected.items():
        button = page.locator(selector)
        expect(button).to_be_in_viewport()
        expect(button).to_have_attribute("href", href)
    expect(page.locator(SCAN)).to_be_focused()


@pytest.mark.e2e
def test_a_scan_on_the_product_screen_resolves_like_the_landing_page(
    handheld_page, live_server
):
    """US1 scenario 6"""
    page = handheld_page
    live_server.add_test_data([ITEM])
    product = live_server.add_test_products([{"description": "Blue widget"}])[0]
    page.goto(f"{live_server.url}/h/product/{product.id}")
    assert_scan_entry_no_keyboard(page, SCAN)

    scan(page, "JA300001")

    expect(page).to_have_url(f"{live_server.url}/h/item/JA300001")


@pytest.mark.e2e
def test_the_keyboard_button_raises_the_keyboard_for_one_entry(handheld_page, live_server):
    """FR-029: inputmode text while typing; the next screen's entry is back to none"""
    page = handheld_page
    live_server.add_test_data([ITEM])
    open_landing(page, live_server)
    scan_entry = page.locator(SCAN)

    page.locator("#handheld-keyboard-btn").tap()

    expect(scan_entry).to_have_attribute("inputmode", "text")
    expect(scan_entry).to_be_focused()
    page.keyboard.type("JA300001")
    page.keyboard.press("Enter")

    expect(page).to_have_url(f"{live_server.url}/h/item/JA300001")
    assert_scan_entry_no_keyboard(page, SCAN)
    expect(scan_entry).to_be_focused()
