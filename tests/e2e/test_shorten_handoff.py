"""
E2E tests for the item hand-off into the Shorten page (User Story 4).

The row's Shorten action has always emitted `?ja_id=...` and the page has always
ignored it, so the link looked identical to a working one. `tests/unit/
test_routes.py` asserted the link was *rendered*, which is precisely the shape of
test FR-022 calls insufficient: it held a dead link in place for as long as it
existed. The test below clicks the real control (FR-019) and asserts on what the
page then does.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.pages.inventory_list_page import InventoryListPage


def _seed(live_server):
    live_server.add_test_data([
        {
            "ja_id": ja_id,
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "12.0",
            "width": "0.5",
            "location": "M1-A",
            "active": True,
        }
        for ja_id in ("JA000101", "JA000102")
    ])


@pytest.mark.e2e
def test_row_shorten_action_identifies_the_item(page, live_server):
    """Acceptance scenario 1 of US4: the page opens already identifying it."""
    _seed(live_server)
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    list_page.click_item_action("JA000102", "shorten")

    expect(page.locator("#source-ja-id")).to_have_value("JA000102")

    # A prefill, not a mode: the page's own workflow proceeds from it, so the
    # item's details load exactly as they would have after typing the JA ID.
    expect(page.locator("#item-details")).to_be_visible()
    expect(page.locator("#item-location")).to_have_text("M1-A")
    expect(page.locator("#scanner-status")).to_have_text("Item Loaded")


@pytest.mark.e2e
def test_shorten_without_a_parameter_is_unchanged(page, live_server):
    """FR-004 / acceptance scenario 2 of US4."""
    _seed(live_server)
    page.goto(f"{live_server.url}/inventory/shorten")

    expect(page.locator("#source-ja-id")).to_have_value("")
    expect(page.locator("#source-ja-id")).to_be_focused()
    expect(page.locator("#item-details")).not_to_be_visible()
    expect(page.locator("#scanner-status")).to_have_text("Ready")
    expect(page.locator("#handoff-rejected")).to_have_count(0)


@pytest.mark.e2e
def test_a_rejected_shorten_hand_off_is_named_not_dropped(page, live_server):
    """FR-005. The field is left empty and the reason is on screen, rather than
    the page opening as though nothing had been handed to it."""
    _seed(live_server)
    page.goto(f"{live_server.url}/inventory/shorten?ja_id=JA000999")

    expect(page.locator("#source-ja-id")).to_have_value("")
    expect(page.locator("#handoff-rejected")).to_contain_text("JA000999")
    expect(page.locator("#item-details")).not_to_be_visible()
