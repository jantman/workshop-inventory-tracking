"""E2E: handheld Move for items and products (feature 068, US3).

The handheld move screen is the desktop move page's MoveManager in a 360x512
layout: the scan entry in the sticky header, the queue as a list of cards,
Validate and Execute in the fixed action bar, and the Execute confirmation
in-page rather than a browser dialog (FR-026). Results are checked through the
item API and the desktop product page (SC-005).

**Waiting note.** Every scan goes through ``waits.scan_on_move_page``, which
asks the page how it classifies the value and waits on the matching signal,
and Execute is waited on with ``waits.wait_for_move_executed``. Neither types
anywhere but ``#barcode-input``, and nothing is tapped before a scan.

Author: Jason Antman, 2026.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.handheld import (
    LONG_LOCATION,
    assert_handheld_layout,
    assert_scan_entry_no_keyboard,
    long_item,
    long_product,
)
from tests.e2e.waits import (
    scan_on_move_page,
    wait_for_modal_hidden,
    wait_for_modal_shown,
    wait_for_move_executed,
)

BARCODE = "#barcode-input"


def item(ja_id: str, location: str = "M1-A") -> dict:
    return {
        "ja_id": ja_id, "item_type": "Bar", "shape": "Round", "material": "Carbon Steel",
        "length": 1000, "width": 25, "location": location, "active": True,
    }


def open_move(page, live_server, kind: str):
    page.goto(f"{live_server.url}/h/move?kind={kind}")
    expect(page.locator(BARCODE)).to_be_focused()
    expect(page.locator("#scanner-status")).to_have_text("Ready")
    assert_scan_entry_no_keyboard(page, BARCODE)


def fail_on_dialog(page) -> list[str]:
    """FR-026: record any native dialog (dismissing it) so the test can assert none fired."""
    seen: list[str] = []

    def handler(dialog):
        seen.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", handler)
    return seen


def execute_in_page(page) -> None:
    """Tap Execute and accept the in-page confirmation."""
    page.locator("#execute-moves-btn").tap()
    wait_for_modal_shown(page, "handheld-confirm-modal")
    expect(page.locator("#handheld-confirm-message")).to_contain_text("Are you sure")
    page.locator("#handheld-confirm-ok").tap()
    wait_for_move_executed(page)


def item_location(page, live_server, ja_id: str) -> str:
    response = page.request.get(f"{live_server.url}/api/items/{ja_id}")
    assert response.ok
    return response.json()["item"]["location"]


@pytest.mark.e2e
def test_scan_two_items_validate_and_execute(handheld_page, live_server):
    """US3 scenarios 1-2"""
    page = handheld_page
    live_server.add_test_data([item("JA310001"), item("JA310002")])
    dialogs = fail_on_dialog(page)
    open_move(page, live_server, "items")

    scan_on_move_page(page, "JA310001")
    scan_on_move_page(page, "T-3")
    scan_on_move_page(page, "JA310002")
    scan_on_move_page(page, "M2-B")
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("2 items")
    rows = page.locator("#queue-items tr")
    expect(rows).to_have_count(2)
    assert_handheld_layout(page, BARCODE, "#execute-moves-btn")

    page.locator("#validate-btn").tap()
    expect(page.locator("#validation-section")).to_be_visible()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()
    expect(page.locator("#execute-moves-btn")).to_be_in_viewport()
    execute_in_page(page)

    assert dialogs == []
    assert item_location(page, live_server, "JA310001") == "T-3"
    assert item_location(page, live_server, "JA310002") == "M2-B"
    expect(page.locator(BARCODE)).to_be_focused()


@pytest.mark.e2e
def test_done_finalizes_and_enables_validate(handheld_page, live_server):
    """US3 scenario 3: >>DONE<< finalizes the move, as on the desktop"""
    page = handheld_page
    live_server.add_test_data([item("JA310003")])
    open_move(page, live_server, "items")

    scan_on_move_page(page, "JA310003")
    scan_on_move_page(page, "T-3")
    expect(page.locator("#validate-btn")).to_be_disabled()

    scan_on_move_page(page, ">>DONE<<")

    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(page.locator("#validate-btn")).to_be_enabled()


@pytest.mark.e2e
def test_rejected_scans_keep_the_scan_entry_in_view(handheld_page, live_server):
    """US3 scenario 4 (FR-019): rejections show, the scan entry stays visible and focused"""
    page = handheld_page
    open_move(page, live_server, "items")
    alerts = page.locator("#form-alerts .alert")

    # A location where an ID is expected, refused immediately; repeated, the
    # accumulating alerts scroll inside their own box.
    for count in range(1, 6):
        scan_on_move_page(page, "M1-A")
        expect(alerts).to_have_count(count)
    barcode = page.locator(BARCODE)
    expect(barcode).to_be_in_viewport()
    expect(barcode).to_be_focused()
    expect(page.locator("#input-status")).to_be_in_viewport()

    # An unknown JA ID is queued and refused at validation, as on the desktop.
    scan_on_move_page(page, "JA399999")
    scan_on_move_page(page, "T-3")
    scan_on_move_page(page, ">>DONE<<")
    page.locator("#validate-btn").tap()
    expect(page.locator("#queue-items tr").first.locator("td").nth(5)).to_have_text("not_found")
    expect(page.locator("#execute-moves-btn")).to_be_disabled()
    expect(barcode).to_be_in_viewport()
    expect(barcode).to_be_focused()


@pytest.mark.e2e
def test_products_move_as_on_the_desktop(handheld_page, live_server):
    """US3 scenario 5"""
    page = handheld_page
    product = live_server.add_test_products([long_product()])[0]
    dialogs = fail_on_dialog(page)
    open_move(page, live_server, "products")

    scan_on_move_page(page, product.internal_code)
    scan_on_move_page(page, "Woodshop shelf 2")
    scan_on_move_page(page, "Drawer 3")
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("1 item")
    assert_handheld_layout(page, BARCODE, "#execute-moves-btn")

    page.locator("#validate-btn").tap()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()
    execute_in_page(page)

    assert dialogs == []
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#product-location")).to_have_text("Woodshop shelf 2")
    expect(page.locator("#product-sub-location")).to_have_text("Drawer 3")


@pytest.mark.e2e
def test_a_long_queue_fits_the_width_and_keeps_execute_in_view(handheld_page, live_server):
    """FR-006, FR-007, FR-019: ten moves of long-location items"""
    page = handheld_page
    ja_ids = [f"JA3200{n:02d}" for n in range(10)]
    live_server.add_test_data([long_item(ja_id) for ja_id in ja_ids])
    open_move(page, live_server, "items")

    for ja_id in ja_ids:
        scan_on_move_page(page, ja_id)
        scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, ">>DONE<<")

    expect(page.locator("#queue-count")).to_have_text("10 items")
    first = page.locator("#queue-items tr").first
    expect(first).to_contain_text(LONG_LOCATION)
    assert_handheld_layout(page, BARCODE, "#execute-moves-btn")


@pytest.mark.e2e
def test_the_keyboard_button_turns_on_manual_entry_for_one_code(handheld_page, live_server):
    """FR-029: typed by hand, the code is not auto-processed mid-word"""
    page = handheld_page
    live_server.add_test_data([item("JA310004")])
    open_move(page, live_server, "items")
    barcode = page.locator(BARCODE)
    manual = page.locator("#manual-entry-mode")

    page.locator("#handheld-keyboard-btn").tap()

    expect(barcode).to_have_attribute("inputmode", "text")
    expect(manual).to_be_checked()
    expect(barcode).to_be_focused()
    # At hand-typing speed, slower than the 100 ms auto-process delay: a code
    # processed mid-word would leave the status on an error, not this item.
    page.keyboard.type("JA310004", delay=150)
    page.keyboard.press("Enter")

    expect(page.locator("#scanner-status")).to_have_text("Waiting for Location")
    expect(page.locator("#status-text")).to_contain_text("JA310004")
    expect(manual).not_to_be_checked()
    assert_scan_entry_no_keyboard(page, BARCODE)
    expect(barcode).to_be_focused()


@pytest.mark.e2e
def test_cancel_in_the_execute_confirm_moves_nothing(handheld_page, live_server):
    """FR-026: Cancel in the in-page confirm leaves the queue and the items as they were"""
    page = handheld_page
    live_server.add_test_data([item("JA310005")])
    posts: list[str] = []
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    open_move(page, live_server, "items")
    scan_on_move_page(page, "JA310005")
    scan_on_move_page(page, "T-3")
    scan_on_move_page(page, ">>DONE<<")
    page.locator("#validate-btn").tap()
    execute = page.locator("#execute-moves-btn")
    expect(execute).to_be_enabled()
    posts.clear()

    execute.tap()
    wait_for_modal_shown(page, "handheld-confirm-modal")
    page.locator("#handheld-confirm-cancel").tap()
    wait_for_modal_hidden(page, "handheld-confirm-modal")

    expect(page.locator(BARCODE)).to_be_focused()
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(execute).to_be_enabled()
    assert item_location(page, live_server, "JA310005") == "M1-A"
    assert posts == []
