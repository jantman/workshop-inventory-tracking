"""Helpers for the handheld screen e2e tests (feature 068).

Waits live in waits.py and assertions in the tests; these are the handheld's
shared actions, its layout check (FR-006, FR-007, FR-029) and the long-data
seeds FR-006 is tested against (research.md D12, D14).

Author: Jason Antman, 2026.
"""

from decimal import Decimal
from typing import Any

from playwright.sync_api import Page, expect

from app.database import InventoryItem

SCAN_ENTRY = "[data-handheld-scan]"


def scan(page: Page, code: str) -> None:
    """Deliver a scan as DataWedge does: keystrokes and an Enter, nothing tapped.

    Waits first for the screen's scan entry to hold focus, which handheld.js
    gives it on load (FR-002); keys typed before that would land nowhere.
    """
    expect(page.locator(SCAN_ENTRY)).to_be_focused()
    page.keyboard.type(code)
    page.keyboard.press("Enter")


def wedge(page: Page, code: str) -> None:
    """Deliver a scan to whatever holds focus, without waiting for the scan entry.

    DataWedge does not wait for anything: it types into the focused element.
    Use this where the test is about what a scan does when focus might not be
    on the scan entry (after a tap on a card or a field).
    """
    page.keyboard.type(code)
    page.keyboard.press("Enter")


# How a wedge delivers a distributor label's separators: as Ctrl-key events,
# which scan-capture.js maps back (test_wedge_scan.py asserts the mapping).
_CONTROL_KEYS = {"\x1d": "Control+]", "\x1e": "Control+6", "\x04": "Control+d"}


def scan_label(page: Page, label: str) -> None:
    """Deliver a distributor (ECIA) label as a wedge does, separators included.

    Plain runs are typed; each GS/RS/EOT is pressed as its Ctrl key. As
    :func:`scan`, it waits for the scan entry's focus first and ends with Enter.
    """
    expect(page.locator(SCAN_ENTRY)).to_be_focused()
    run = ""
    for char in label:
        if char in _CONTROL_KEYS:
            if run:
                page.keyboard.type(run)
                run = ""
            page.keyboard.press(_CONTROL_KEYS[char])
        else:
            run += char
    if run:
        page.keyboard.type(run)
    page.keyboard.press("Enter")


def assert_handheld_layout(page: Page, scan_selector: str, primary_selector: str) -> None:
    """The scan entry and the primary action stay on screen, with no sideways scroll.

    FR-007: both are in the viewport at load and still are after scrolling to
    the bottom (the sticky header and the fixed action bar). FR-006: the page
    is no wider than the viewport.
    """
    scan_entry = page.locator(scan_selector)
    primary = page.locator(primary_selector)
    for locator in (scan_entry, primary):
        expect(locator).to_be_visible()
        expect(locator).to_be_in_viewport()

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    expect(scan_entry).to_be_in_viewport()
    expect(primary).to_be_in_viewport()

    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, f"page scrolls sideways by {overflow}px"


def assert_scan_entry_no_keyboard(page: Page, selector: str = SCAN_ENTRY) -> None:
    """FR-029: focusing the scan entry must not raise the soft keyboard."""
    expect(page.locator(selector)).to_have_attribute("inputmode", "none")


# --- Long-data seeds (FR-006) ---------------------------------------------
# The longest values the columns hold or real orders carry, so a screen that
# would push sideways or hide its primary action does so in a test.

LONG_DESCRIPTION = (
    "Socket head cap screw, 18-8 stainless steel, M6 x 1.0 mm thread, 40 mm long, "
    "fully threaded, hex drive, DIN 912 / ISO 4762, passivated, pack of 100, "
    "for general purpose fastening in machine frames, fixtures and jigs; "
    "metric coarse thread, 5 mm hex key, A2"
)[:255]

LONG_LOCATION = "Main shop north wall steel rack, upper shelf, left-hand bay beside the bandsaw"
LONG_SUB_LOCATION = "Blue Akro-Mils bin 14, front compartment, behind the drill bit index"
LONG_VENDOR = "Bolt Depot / Fastenal Industrial & Construction Supplies of Greater Atlanta"

# Realistic order numbers by vendor, as captured.
ORDER_NUMBERS = {
    "Amazon": "113-4829175-6203418",
    "McMaster-Carr": "7319PDRK4",
    "DigiKey": "88412377",
}


def long_item(ja_id: str, **overrides: Any) -> InventoryItem:
    """An inventory item with long location fields, for ``add_test_data``.

    An object rather than a dict, because the dict form of ``add_test_data``
    does not carry ``sub_location``.
    """
    fields: dict[str, Any] = {
        "ja_id": ja_id,
        "item_type": "Bar",
        "shape": "Rectangular",
        "material": "6061-T6 Aluminum",
        "length": Decimal("1000"),
        "width": Decimal("50.8"),
        "thickness": Decimal("12.7"),
        "location": LONG_LOCATION,
        "sub_location": LONG_SUB_LOCATION,
        "notes": LONG_DESCRIPTION,
        "active": True,
    }
    fields.update(overrides)
    return InventoryItem(**fields)


def long_product(**overrides: Any) -> dict[str, Any]:
    """``add_test_products`` kwargs for a product with a 255-character description."""
    fields: dict[str, Any] = {
        "description": LONG_DESCRIPTION,
        "location": LONG_LOCATION,
        "sub_location": LONG_SUB_LOCATION,
    }
    fields.update(overrides)
    return fields


def long_purchase(vendor: str = LONG_VENDOR, **overrides: Any) -> dict[str, Any]:
    """``CatalogService.record_purchase`` kwargs (less product_id) with long text."""
    fields: dict[str, Any] = {
        "vendor": vendor,
        "vendor_item_id": "91290A215-STAINLESS-M6X40-PACK100",
        "listing_title": LONG_DESCRIPTION,
        "quantity": 100,
        "supplier_order_reference": ORDER_NUMBERS.get(vendor, "113-4829175-6203418"),
    }
    fields.update(overrides)
    return fields
