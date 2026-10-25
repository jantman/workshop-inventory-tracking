"""E2E: the handheld item screen (feature 068, US4).

At the TC52's 360x512 touch viewport a JA ID's screen shows the item's
summary above the fold, opens the desktop item label dialog, adds, views and
deletes photos through the desktop PhotoManager, and hands off to handheld
Shorten and Move. Changes are checked through the APIs (SC-005).

**Waiting note.** ``photo-manager.js`` awaits the upload POST before it
appends the card, and removes a card only after the DELETE succeeds, so the
card count is the whole wait (CLAUDE.md pattern C).

Author: Jason Antman, 2026.
"""

import io

import pytest
from PIL import Image
from playwright.sync_api import expect

from app.photo_service import PhotoService
from tests.e2e.handheld import assert_handheld_layout, assert_scan_entry_no_keyboard, long_item
from tests.e2e.waits import wait_for_modal_shown, wait_for_photo_viewer_open

SCAN = "#handheld-scan-input"
LABEL = "#handheld-label-btn"
CARDS = "#photo-manager-container .photo-card"


def jpeg_bytes(colour: str) -> bytes:
    """A real JPEG -- the server decodes and resizes what it is given."""
    buffer = io.BytesIO()
    Image.new("RGB", (120, 90), color=colour).save(buffer, format="JPEG")
    return buffer.getvalue()


def fail_on_dialog(page) -> list[str]:
    """FR-026: record any native dialog (dismissing it) so the test can assert none fired."""
    seen: list[str] = []

    def handler(dialog):
        seen.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", handler)
    return seen


def open_item(page, live_server, ja_id: str) -> None:
    page.goto(f"{live_server.url}/h/item/{ja_id}")
    expect(page.locator("#handheld-item-ja-id")).to_have_text(ja_id)
    assert_scan_entry_no_keyboard(page, SCAN)


def assert_above_action_bar(page, selector: str) -> None:
    """In the viewport is not enough: the fixed action bar covers its bottom."""
    box = page.locator(selector).bounding_box()
    bar = page.locator("#handheld-action-bar").bounding_box()
    assert box["y"] + box["height"] <= bar["y"], (selector, box, bar)


@pytest.mark.e2e
@pytest.mark.parametrize("long_data", [False, True], ids=["short", "long"])
def test_summary_and_actions_fit_the_screen(handheld_page, live_server, long_data):
    """US4 scenario 1 (FR-010, FR-006, FR-007)"""
    page = handheld_page
    item = long_item("JA000601") if long_data else long_item(
        "JA000601", location="Rack 2", sub_location="Shelf B"
    )
    live_server.add_test_data([item])

    open_item(page, live_server, "JA000601")

    expect(page.locator("#handheld-item-kind")).to_have_text(
        "6061-T6 Aluminum · Bar · Rectangular"
    )
    dimensions = page.locator("#handheld-item-dimensions")
    expect(dimensions).to_contain_text('Width 50.8"')
    expect(dimensions).to_contain_text('Thickness 12.7"')
    expect(page.locator("#handheld-item-length")).to_have_text('Length 1000"')
    location = page.locator("#handheld-item-location")
    expect(location).to_have_text(f"{item.location} / {item.sub_location}")
    for selector in ("#handheld-item-kind", "#handheld-item-dimensions",
                     "#handheld-item-location"):
        expect(page.locator(selector)).to_be_in_viewport()
    assert_above_action_bar(page, "#handheld-item-location")
    for selector in ("#handheld-photos-btn", "#handheld-shorten-btn", "#handheld-move-btn"):
        expect(page.locator(selector)).to_be_in_viewport()
    assert_handheld_layout(page, SCAN, LABEL)


@pytest.mark.e2e
def test_label_opens_the_item_label_dialog(handheld_page, live_server):
    """US4 scenario 2 (FR-011)"""
    page = handheld_page
    live_server.add_test_data([long_item("JA000602")])
    open_item(page, live_server, "JA000602")

    page.locator(LABEL).tap()

    wait_for_modal_shown(page, "label-printing-modal")
    expect(page.locator("#label-ja-id-display")).to_have_text("JA000602")
    expect(page.locator("#modal-print-label-btn")).to_be_in_viewport()


@pytest.mark.e2e
def test_add_view_and_delete_photos(handheld_page, live_server):
    """US4 scenarios 3-4 (FR-012, FR-026)"""
    page = handheld_page
    live_server.add_test_data([long_item("JA000603", location="Rack 2", sub_location=None)])
    with PhotoService(live_server.storage) as photos:
        photos.upload_photo("JA000603", jpeg_bytes("red"), "seeded.jpg", "image/jpeg")
    dialogs = fail_on_dialog(page)
    open_item(page, live_server, "JA000603")
    cards = page.locator(CARDS)
    expect(cards).to_have_count(1)

    # Scenario 3: the device's file chooser feeds this input.
    page.locator("#photo-manager-container .photo-file-input").set_input_files(
        files=[{"name": "added.jpg", "mimeType": "image/jpeg", "buffer": jpeg_bytes("blue")}]
    )
    expect(cards).to_have_count(2)

    # Scenario 4: delete one through the in-page confirm, no native dialog.
    cards.first.locator(".photo-delete-btn").tap()
    wait_for_modal_shown(page, "handheld-confirm-modal")
    page.locator("#handheld-confirm-ok").tap()
    expect(cards).to_have_count(1)
    assert dialogs == []
    listed = page.request.get(f"{live_server.url}/api/items/JA000603/photos").json()
    assert len(listed["photos"]) == 1

    # ...and open the remaining one full size.
    cards.first.locator(".photo-thumbnail").tap()
    wait_for_photo_viewer_open(page)


@pytest.mark.e2e
def test_shorten_and_move_open_with_the_item(handheld_page, live_server):
    """US4 scenario 5 (FR-020)"""
    page = handheld_page
    live_server.add_test_data([long_item("JA000604", location="Rack 2", sub_location=None)])
    open_item(page, live_server, "JA000604")

    page.locator("#handheld-shorten-btn").tap()
    expect(page).to_have_url(f"{live_server.url}/h/shorten?ja_id=JA000604")
    expect(page.locator("#current-length")).to_have_text("1000")

    open_item(page, live_server, "JA000604")
    page.locator("#handheld-move-btn").tap()
    expect(page).to_have_url(f"{live_server.url}/h/move?kind=items&ja_id=JA000604")
    pending = page.locator('#pending-moves tr[data-id="JA000604"]')
    expect(pending).to_be_visible()
    expect(pending.locator(".pending-current-location")).to_have_text("Rack 2")


@pytest.mark.e2e
@pytest.mark.parametrize("state", ["missing", "inactive"])
def test_a_missing_or_inactive_ja_id_says_so(handheld_page, live_server, state):
    """US4 scenario 6"""
    page = handheld_page
    if state == "inactive":
        live_server.add_test_data([long_item("JA000605", active=False)])
    message = "No item with this JA ID." if state == "missing" else "This item is inactive."

    open_item(page, live_server, "JA000605")

    expect(page.locator("#handheld-item-state")).to_have_text(message)
    link = page.locator("#handheld-item-desktop-link")
    expect(link).to_have_attribute("href", "/inventory/edit/JA000605")
    expect(link).to_be_in_viewport()
    expect(page.locator("#photo-manager-container")).to_have_count(0)
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1
