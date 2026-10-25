"""E2E: handheld Shorten (feature 068, US5).

At the TC52's 360x512 touch viewport a scanned JA ID loads the item, the new
length entry sits above the fixed action bar, and Execute -- in that bar --
is always in view. The form posts to the desktop's own handler, so the
results are checked through the item and history APIs (SC-005).

**Waiting note.** ``inventory-shorten.js`` loads the item after awaiting
``GET /api/items/<ja>`` and only then fills ``#current-length`` (CLAUDE.md
pattern C), so its text is the load's completion signal. Execute posts the
form and the route redirects with a flash, so the flash is the signal for
the POST.

Author: Jason Antman, 2026.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.handheld import assert_handheld_layout, assert_scan_entry_no_keyboard, long_item, scan

SCAN = "#source-ja-id"
EXECUTE = "#execute-shortening-btn"


def fail_on_dialog(page) -> list[str]:
    """FR-026: record any native dialog (dismissing it) so the test can assert none fired."""
    seen: list[str] = []

    def handler(dialog):
        seen.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", handler)
    return seen


def load_by_scan(page, live_server, ja_id: str) -> None:
    page.goto(f"{live_server.url}/h/shorten")
    assert_scan_entry_no_keyboard(page, SCAN)
    scan(page, ja_id)
    expect(page.locator("#current-length")).to_have_text("1000")


def assert_above_action_bar(page, selector: str) -> None:
    """In the viewport is not enough: the fixed action bar covers its bottom."""
    box = page.locator(selector).bounding_box()
    bar = page.locator("#handheld-action-bar").bounding_box()
    assert box["y"] + box["height"] <= bar["y"], (selector, box, bar)


def item_state(page, live_server, ja_id: str) -> tuple[float, dict]:
    item = page.request.get(f"{live_server.url}/api/items/{ja_id}").json()["item"]
    history = page.request.get(f"{live_server.url}/api/items/{ja_id}/history").json()
    return float(item["dimensions"]["length"]), history


@pytest.mark.e2e
@pytest.mark.parametrize("long_data", [False, True], ids=["short", "long"])
def test_a_scanned_item_loads_with_the_new_length_in_view(handheld_page, live_server, long_data):
    """US5 scenario 1 (FR-006, FR-007, FR-029)"""
    page = handheld_page
    item = long_item("JA000501") if long_data else long_item(
        "JA000501", location="Rack 2", sub_location=None
    )
    live_server.add_test_data([item])

    load_by_scan(page, live_server, "JA000501")

    new_length = page.locator("#new-length")
    expect(new_length).to_be_visible()
    expect(new_length).to_be_in_viewport()
    assert_above_action_bar(page, "#new-length")
    expect(page.locator("#item-location")).to_contain_text(item.location)
    assert_handheld_layout(page, SCAN, EXECUTE)


@pytest.mark.e2e
def test_a_hand_off_loads_the_item_without_a_scan(handheld_page, live_server):
    """US5: opened from the item screen (FR-020), the item is already loaded."""
    page = handheld_page
    live_server.add_test_data([long_item("JA000502")])

    page.goto(f"{live_server.url}/h/shorten?ja_id=JA000502")

    expect(page.locator("#current-length")).to_have_text("1000")
    expect(page.locator(SCAN)).to_have_value("JA000502")
    assert_above_action_bar(page, "#new-length")


@pytest.mark.e2e
def test_shorten_1000_to_600_keeps_the_history(handheld_page, live_server):
    """US5 scenario 2 (FR-013): the desktop operation, history retained."""
    page = handheld_page
    live_server.add_test_data([long_item("JA000503")])
    dialogs = fail_on_dialog(page)
    load_by_scan(page, live_server, "JA000503")

    page.locator("#new-length").fill("600")
    execute = page.locator(EXECUTE)
    expect(execute).to_be_disabled()
    page.locator("#confirm-operation").check()
    expect(execute).to_be_enabled()
    execute.tap()

    expect(page.locator(".alert-success")).to_contain_text("successfully shortened")
    expect(page).to_have_url(f"{live_server.url}/h/shorten")
    length, history = item_state(page, live_server, "JA000503")
    assert length == 600
    assert history["total_items"] == 2
    assert history["active_item_count"] == 1
    inactive = [row for row in history["history"] if not row["active"]]
    assert float(inactive[0]["dimensions"]["length"]) == 1000
    assert dialogs == []


@pytest.mark.e2e
def test_a_longer_length_is_refused_and_nothing_changes(handheld_page, live_server):
    """US5 scenario 3: the desktop's refusal, client-side and then server-side."""
    page = handheld_page
    live_server.add_test_data([long_item("JA000504")])
    load_by_scan(page, live_server, "JA000504")

    page.locator("#new-length").fill("1200")
    expect(page.locator("#length-validation-alert")).to_have_text(
        "New length must be shorter than the original length"
    )
    page.locator("#confirm-operation").check()
    page.locator(EXECUTE).tap()

    expect(page.locator(".alert-danger")).to_contain_text(
        "New length must be shorter than current length"
    )
    length, history = item_state(page, live_server, "JA000504")
    assert length == 1000
    assert history["total_items"] == 1
