"""E2E: the handheld product screen (feature 068, US2).

At the TC52's 360x512 touch viewport the product's name, location and stock
controls are above the fold, and the stock controls, label dialog and
attachments behave as they do on the desktop product page -- each change is
checked there (SC-005).

**Waiting note.** ``product-stock.js`` and ``product-attachments.js`` reload
the page after every successful request, so each change is waited on through
the reloaded, server-rendered state (CLAUDE.md pattern C): the quantity text,
the flag button's class (``waits.wait_for_stock_flag``), which counting button
is rendered, the number of attachment tiles.

Author: Jason Antman, 2026.
"""

import io

import pytest
from PIL import Image
from playwright.sync_api import expect

from tests.e2e.handheld import assert_handheld_layout, assert_scan_entry_no_keyboard, long_product
from tests.e2e.waits import wait_for_modal_hidden, wait_for_modal_shown, wait_for_stock_flag

SCAN = "#handheld-scan-input"
TILES = "#attachment-list .attachment-row"


def open_product(page, live_server, product):
    page.goto(f"{live_server.url}/h/product/{product.id}")
    expect(page.locator("#stock-card")).to_be_visible()
    assert_scan_entry_no_keyboard(page, SCAN)


def wait_for_stock_reload(page, quantity: str) -> None:
    """A stock button PATCHes and then reloads the page.

    The new quantity is in the server-rendered HTML, so it shows before the
    page's scripts have run; a tap in that gap reaches a button with no
    handler. handheld.js focuses the scan entry on DOMContentLoaded, the same
    event product-stock.js wires the buttons on, so focus is the signal that
    the reloaded page is ready for the next tap.
    """
    expect(page.locator("#quantity-value")).to_have_text(quantity)
    expect(page.locator(SCAN)).to_be_focused()


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def fail_on_dialog(page) -> list[str]:
    """FR-026: record any native dialog (dismissing it) so the test can assert none fired."""
    seen: list[str] = []

    def handler(dialog):
        seen.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", handler)
    return seen


@pytest.mark.e2e
@pytest.mark.parametrize("long_data", [False, True], ids=["short", "long"])
def test_name_location_and_stock_controls_are_above_the_fold(
    handheld_page, live_server, long_data
):
    """US2 scenario 1 (FR-014, FR-006, FR-007)"""
    page = handheld_page
    fields = (
        long_product(quantity=5)
        if long_data
        else {"description": "Blue widget", "location": "Bin 7", "sub_location": "Drawer 2",
              "quantity": 5}
    )
    product = live_server.add_test_products([fields])[0]
    open_product(page, live_server, product)

    for selector in ("#handheld-product-description", "#handheld-product-location",
                     "#quantity-decrement", "#quantity-increment", "#quantity-set-btn"):
        expect(page.locator(selector)).to_be_in_viewport()
    # In the viewport is not enough: the fixed action bar covers the bottom
    # of it. Set must sit clear above the bar.
    set_box = page.locator("#quantity-set-btn").bounding_box()
    bar_box = page.locator("#handheld-action-bar").bounding_box()
    assert set_box["y"] + set_box["height"] <= bar_box["y"], (set_box, bar_box)
    # Set is the first block's control, above the fold at load (research.md
    # D12); Label in the fixed action bar is what stays reachable on scroll.
    assert_handheld_layout(page, SCAN, "#print-product-label-btn")
    expect(page.locator(SCAN)).to_be_focused()


@pytest.mark.e2e
def test_quantity_and_stock_status_change_as_on_the_desktop(handheld_page, live_server):
    """US2 scenarios 2-3 (FR-015)"""
    page = handheld_page
    product = live_server.add_test_products([{"description": "Blue widget", "quantity": 5}])[0]
    open_product(page, live_server, product)

    page.locator("#quantity-decrement").tap()
    wait_for_stock_reload(page, "4")
    page.locator("#quantity-increment").tap()
    wait_for_stock_reload(page, "5")
    page.locator("#quantity-input").fill("12")
    page.locator("#quantity-set-btn").tap()
    wait_for_stock_reload(page, "12")

    page.locator("#flag-low-btn").tap()
    wait_for_stock_flag(page, "low")

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#quantity-value")).to_have_text("12")
    wait_for_stock_flag(page, "low")

    open_product(page, live_server, product)
    page.locator("#flag-out-btn").tap()
    wait_for_stock_flag(page, "out")
    page.goto(f"{live_server.url}/products/{product.id}")
    wait_for_stock_flag(page, "out")

    open_product(page, live_server, product)
    page.locator("#clear-flag-btn").tap()
    wait_for_stock_flag(page, None)
    page.goto(f"{live_server.url}/products/{product.id}")
    wait_for_stock_flag(page, None)
    expect(page.locator("#flag-age")).to_have_count(0)


@pytest.mark.e2e
def test_start_and_stop_counting(handheld_page, live_server):
    """US2 scenario 4"""
    page = handheld_page
    product = live_server.add_test_products([{"description": "Uncounted widget"}])[0]
    open_product(page, live_server, product)

    page.locator("#start-tracking-btn").tap()
    expect(page.locator("#stop-tracking-btn")).to_be_visible()
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#stop-tracking-btn")).to_be_visible()
    expect(page.locator("#quantity-value")).to_have_text("None on hand")

    open_product(page, live_server, product)
    page.locator("#stop-tracking-btn").tap()
    expect(page.locator("#start-tracking-btn")).to_be_visible()
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#quantity-value")).to_have_text("Not tracked")


@pytest.mark.e2e
@pytest.mark.parametrize("long_data", [False, True], ids=["short", "long"])
def test_print_label_dialog_fits_the_screen(handheld_page, live_server, long_data):
    """US2 scenario 5 (FR-016)"""
    page = handheld_page
    fields = long_product() if long_data else {"description": "Blue widget"}
    product = live_server.add_test_products([fields])[0]
    open_product(page, live_server, product)

    page.locator("#print-product-label-btn").tap()
    wait_for_modal_shown(page, "product-label-modal")

    expect(page.locator("#product-label-print-confirm")).to_be_in_viewport()
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1


@pytest.mark.e2e
def test_attach_a_file(handheld_page, live_server):
    """US2 scenario 6 (FR-017): Attach opens the device chooser; choosing uploads"""
    page = handheld_page
    product = live_server.add_test_products([{"description": "Blue widget"}])[0]
    open_product(page, live_server, product)
    expect(page.locator("#no-attachments")).to_be_visible()
    # The Attach button is the label for the file input, so a tap opens the
    # device's chooser (camera and files: no capture attribute).
    expect(page.locator("#handheld-attach-btn")).to_have_attribute(
        "for", "product-attachment-input"
    )
    expect(page.locator("#product-attachment-input")).not_to_have_attribute("capture", "")

    page.locator("#product-attachment-input").set_input_files(
        files=[{"name": "shelf.png", "mimeType": "image/png", "buffer": png_bytes()}]
    )

    expect(page.locator(TILES)).to_have_count(1)
    expect(page.locator(TILES)).to_contain_text("shelf.png")
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator(TILES)).to_have_count(1)


@pytest.mark.e2e
def test_delete_an_attachment_with_the_in_page_confirm(handheld_page, live_server):
    """US2 scenario 7 (FR-017, FR-026)"""
    page = handheld_page
    product = live_server.add_test_products([{"description": "Blue widget"}])[0]
    live_server.add_product_attachments(product.id, 2)
    dialogs = fail_on_dialog(page)
    open_product(page, live_server, product)
    tiles = page.locator(TILES)
    expect(tiles).to_have_count(2)
    expect(page.locator(".delete-attachment-btn")).to_have_count(0)

    # The whole tile is the tap target for its checkbox (FR-008).
    tiles.first.tap()
    expect(tiles.first.locator(".attachment-select")).to_be_checked()
    delete = page.locator("#delete-selected-attachments")
    expect(delete).to_be_enabled()
    delete.tap()
    wait_for_modal_shown(page, "handheld-confirm-modal")
    page.locator("#handheld-confirm-ok").tap()

    expect(tiles).to_have_count(1)
    assert dialogs == []
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator(TILES)).to_have_count(1)


@pytest.mark.e2e
def test_cancel_in_the_delete_confirm_keeps_the_attachment(handheld_page, live_server):
    """FR-026: Cancel in the in-page confirm deletes nothing"""
    page = handheld_page
    product = live_server.add_test_products([{"description": "Blue widget"}])[0]
    live_server.add_product_attachments(product.id, 2)
    deletes: list[str] = []
    page.on("request", lambda r: deletes.append(r.url) if r.method in ("DELETE", "POST") else None)
    open_product(page, live_server, product)
    tiles = page.locator(TILES)
    expect(tiles).to_have_count(2)

    tiles.first.tap()
    expect(tiles.first.locator(".attachment-select")).to_be_checked()
    page.locator("#delete-selected-attachments").tap()
    wait_for_modal_shown(page, "handheld-confirm-modal")
    page.locator("#handheld-confirm-cancel").tap()
    wait_for_modal_hidden(page, "handheld-confirm-modal")

    expect(page.locator(SCAN)).to_be_focused()
    expect(tiles).to_have_count(2)
    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator(TILES)).to_have_count(2)
    assert deletes == []


@pytest.mark.e2e
def test_move_opens_handheld_move_with_the_product_queued(handheld_page, live_server):
    """US2 scenario 8 (FR-020)"""
    page = handheld_page
    product = live_server.add_test_products([{"description": "Blue widget", "location": "Bin 7"}])[0]
    open_product(page, live_server, product)

    page.locator("#handheld-move-btn").tap()

    expect(page).to_have_url(
        f"{live_server.url}/h/move?kind=products&code={product.internal_code}"
    )
    pending = page.locator(f'#pending-moves tr[data-id="{product.internal_code}"]')
    expect(pending).to_be_visible()
    expect(pending.locator(".pending-current-location")).to_have_text("Bin 7")
    expect(page.locator("#barcode-input")).to_be_focused()
