"""
E2E tests for the item hand-off into the Move page (issue #106).

Every test here operates the control the user operates -- ticks rows, opens the
Options menu, clicks Bulk Move Selected -- and never builds
`/inventory/move?ja_id=...` and calls goto(). That rule is FR-019, and it is the
whole reason these defects shipped: every pre-existing move test navigates
straight to the receiving page, so all of them passed while all four hand-offs
silently discarded the user's selection. A test that writes the URL itself
verifies the receiver against a string the test author chose, not against the one
the application produces -- which is exactly how `items=` and `ja_id=` came to
disagree with each other and with both pages.

See specs/026-fix-bulk-move-handoff/contracts/handoff.md.
"""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.pages.inventory_list_page import InventoryListPage
from tests.e2e.pages.search_page import SearchPage
from tests.e2e.waits import scan_on_move_page, wait_for_move_executed

ITEMS = [
    {"ja_id": "JA000101", "location": "M1-A"},
    {"ja_id": "JA000102", "location": "M2-B"},
    {"ja_id": "JA000117", "location": "M3-C"},
]

DESTINATION = "M9-Z"


def _seed(live_server, items=ITEMS, active=True):
    live_server.add_test_data([
        {
            "ja_id": spec["ja_id"],
            "item_type": "Bar",
            "shape": "Round",
            "material": "Carbon Steel",
            "length": "12.0",
            "width": "0.5",
            "location": spec["location"],
            "active": spec.get("active", active),
        }
        for spec in items
    ])


def _hand_off_from_list(page, live_server, ja_ids):
    """Select rows on /inventory and click the real Bulk Move Selected control."""
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    for ja_id in ja_ids:
        list_page.select_item(ja_id)
    list_page.click_bulk_move_selected()
    return list_page


def _hand_off_from_search(page, live_server, ja_ids):
    """The same, from the Search page's own Options menu."""
    search_page = SearchPage(page, live_server.url)
    search_page.navigate()
    search_page.search_by_material("Carbon Steel")
    search_page.wait_for_table_ready()
    for ja_id in ja_ids:
        search_page.select_item(ja_id)
    search_page.click_bulk_move_selected()
    return search_page


def _pending_rows(page):
    return page.locator("#pending-moves tbody tr")


def _queue_rows(page):
    return page.locator("#queue-items tr")


def _queue_row(page, ja_id):
    return _queue_rows(page).filter(has_text=ja_id)


@pytest.mark.e2e
def test_bulk_move_from_list_carries_every_selected_item(page, live_server):
    """Issue #106, end to end: select three, scan one location, execute.

    Acceptance scenarios 1, 2 and 6 of User Story 1.
    """
    _seed(live_server)
    _hand_off_from_list(page, live_server, [i["ja_id"] for i in ITEMS])

    # The Move page holds all three, awaiting a destination, and says so.
    expect(_pending_rows(page)).to_have_count(3)
    expect(page.locator("#preselected-prompt")).to_contain_text("3 items are awaiting")
    for spec in ITEMS:
        expect(_pending_rows(page).filter(has_text=spec["ja_id"])).to_have_count(1)

    # Nothing is queued yet -- a pending move has no destination to validate.
    expect(page.locator("#queue-count")).to_have_text("0 items")
    expect(page.locator("#validate-btn")).to_be_disabled()

    # One destination for all three (SC-002).
    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("3 items")

    # Each queued row shows its own current location (FR-010).
    for spec in ITEMS:
        row = _queue_row(page, spec["ja_id"])
        expect(row).to_contain_text(spec["location"])
        expect(row).to_contain_text(DESTINATION)

    page.locator("#validate-btn").click()
    expect(page.locator("#validation-section")).to_be_visible()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#execute-moves-btn").click()
    wait_for_move_executed(page)

    # And the moves are reflected on the inventory list (SC-001).
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    for spec in ITEMS:
        row = page.locator("#inventory-table-body tr").filter(has_text=spec["ja_id"])
        expect(row).to_contain_text(DESTINATION)


@pytest.mark.e2e
def test_bulk_move_from_search_behaves_identically(page, live_server):
    """Acceptance scenario 5. This is the test that catches a re-split of the
    parameter convention: the two producers are different code, so only driving
    both proves they still agree."""
    _seed(live_server)
    _hand_off_from_search(page, live_server, [i["ja_id"] for i in ITEMS])

    expect(_pending_rows(page)).to_have_count(3)
    expect(page.locator("#preselected-prompt")).to_contain_text("3 items are awaiting")

    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("3 items")
    for spec in ITEMS:
        row = _queue_row(page, spec["ja_id"])
        expect(row).to_contain_text(spec["location"])
        expect(row).to_contain_text(DESTINATION)


@pytest.mark.e2e
def test_group_sub_location_applies_to_every_item(page, live_server):
    """FR-009 / acceptance scenario 3. The sub-location belongs to the group,
    not to whichever row happens to be last."""
    _seed(live_server)
    _hand_off_from_list(page, live_server, [i["ja_id"] for i in ITEMS])

    scan_on_move_page(page, DESTINATION)
    scan_on_move_page(page, "Drawer 3")

    expect(_queue_rows(page)).to_have_count(3)
    for spec in ITEMS:
        expect(_queue_row(page, spec["ja_id"])).to_contain_text("Drawer 3")


@pytest.mark.e2e
def test_hand_scanning_continues_into_the_same_batch(page, live_server):
    """FR-011 / acceptance scenario 4. A fourth item, scanned by hand after the
    group is queued, executes with it."""
    _seed(live_server, ITEMS + [{"ja_id": "JA000118", "location": "M4-D"}])
    _hand_off_from_list(page, live_server, [i["ja_id"] for i in ITEMS])

    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("3 items")

    scan_on_move_page(page, "JA000118")
    scan_on_move_page(page, DESTINATION)
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("4 items")

    page.locator("#validate-btn").click()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#execute-moves-btn").click()
    wait_for_move_executed(page)

    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    for ja_id in [i["ja_id"] for i in ITEMS] + ["JA000118"]:
        row = page.locator("#inventory-table-body tr").filter(has_text=ja_id)
        expect(row).to_contain_text(DESTINATION)


@pytest.mark.e2e
def test_row_move_action_hands_off_one_item(page, live_server):
    """User Story 3. A single item is a list of one, so it arrives the same way."""
    _seed(live_server)
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    list_page.click_item_action("JA000102", "move")

    expect(_pending_rows(page)).to_have_count(1)
    expect(_pending_rows(page)).to_contain_text("JA000102")
    # FR-007's wording must not read as though a group arrived (T036).
    expect(page.locator("#preselected-prompt")).to_contain_text("1 item is awaiting")

    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(_queue_row(page, "JA000102")).to_contain_text("M2-B")

    page.locator("#validate-btn").click()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#execute-moves-btn").click()
    wait_for_move_executed(page)

    list_page.navigate()
    list_page.wait_for_items_loaded()
    row = page.locator("#inventory-table-body tr").filter(has_text="JA000102")
    expect(row).to_contain_text(DESTINATION)


# --- Rejections and edge cases (quickstart Step 7) --------------------------


@pytest.mark.e2e
def test_a_nonexistent_id_is_named_and_the_rest_proceed(page, live_server):
    """FR-005. Silently dropping it would recreate the bug in miniature."""
    _seed(live_server)
    list_page = InventoryListPage(page, live_server.url)
    list_page.navigate()
    list_page.wait_for_items_loaded()
    list_page.select_item("JA000101")
    # The selection is real; the extra identifier is not. Reaching this state
    # through the UI is not possible, so the URL is built here deliberately --
    # this test is about the receiving page's rejection reporting, not about the
    # hand-off convention, which the tests above cover by driving the control.
    page.goto(f"{live_server.url}/inventory/move?ja_id=JA000101,JA000999")

    expect(_pending_rows(page)).to_have_count(1)
    expect(_pending_rows(page)).to_contain_text("JA000101")
    rejected = page.locator("#rejected-items")
    expect(rejected).to_be_visible()
    expect(rejected).to_contain_text("JA000999")

    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("1 item")


@pytest.mark.e2e
def test_an_inactive_row_is_rejected_rather_than_queued(page, live_server):
    """Principle VI. A historical row must never be queued for a move."""
    _seed(live_server, [
        {"ja_id": "JA000101", "location": "M1-A"},
        {"ja_id": "JA000150", "location": "M5-E", "active": False},
    ])
    page.goto(f"{live_server.url}/inventory/move?ja_id=JA000101,JA000150")

    expect(_pending_rows(page)).to_have_count(1)
    expect(_pending_rows(page)).to_contain_text("JA000101")
    expect(page.locator("#rejected-items")).to_contain_text("JA000150")
    expect(_pending_rows(page).filter(has_text="JA000150")).to_have_count(0)


@pytest.mark.e2e
def test_every_item_rejected_says_so_plainly(page, live_server):
    """Edge case: it must not look like a normal empty arrival."""
    _seed(live_server)
    page.goto(f"{live_server.url}/inventory/move?ja_id=JA000998,JA000999")

    expect(page.locator("#preselected-none")).to_be_visible()
    expect(page.locator("#rejected-items")).to_contain_text("JA000998")
    expect(page.locator("#rejected-items")).to_contain_text("JA000999")
    expect(_pending_rows(page)).to_have_count(0)
    # And the page is still usable as a plain scanning page.
    expect(page.locator("#barcode-input")).to_be_focused()
    scan_on_move_page(page, "JA000101")
    scan_on_move_page(page, DESTINATION)
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("1 item")


@pytest.mark.e2e
def test_the_same_item_twice_appears_once(page, live_server):
    """FR-006. A queue cannot move one item to two places."""
    _seed(live_server)
    page.goto(f"{live_server.url}/inventory/move?ja_id=JA000101,JA000101")

    expect(_pending_rows(page)).to_have_count(1)
    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("1 item")


@pytest.mark.e2e
def test_arriving_with_no_parameter_is_unchanged(page, live_server):
    """FR-004 / SC-006. This is how the page is reached in normal scanning use."""
    _seed(live_server)
    page.goto(f"{live_server.url}/inventory/move")

    expect(page.locator("#preselected-section")).to_have_count(0)
    expect(page.locator("#move-queue-empty")).to_be_visible()
    expect(page.locator("#queue-count")).to_have_text("0 items")
    expect(page.locator("#status-text")).to_contain_text("Ready to scan first JA ID")
    expect(page.locator("#scanner-status")).to_have_text("Ready")

    scan_on_move_page(page, "JA000101")
    scan_on_move_page(page, DESTINATION)
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(page.locator("#validate-btn")).to_be_enabled()


@pytest.mark.e2e
def test_a_sub_location_scanned_first_is_refused_with_an_explanation(page, live_server):
    """FR-012. A destination location is required before anything else."""
    _seed(live_server)
    _hand_off_from_list(page, live_server, ["JA000101"])

    scan_on_move_page(page, "Drawer 3")
    expect(page.locator("#queue-count")).to_have_text("0 items")
    expect(page.locator("#form-alerts .alert").last).to_contain_text("location")
    # Still awaiting the destination, and a valid one still works.
    expect(_pending_rows(page)).to_have_count(1)
    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("1 item")


@pytest.mark.e2e
def test_done_with_no_destination_queues_nothing_and_says_why(page, live_server):
    """Edge case. Nothing is queued, and the page explains rather than
    reporting an empty queue as though the user had scanned nothing."""
    _seed(live_server)
    _hand_off_from_list(page, live_server, ["JA000101"])

    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("0 items")
    expect(page.locator("#validate-btn")).to_be_disabled()
    expect(page.locator("#form-alerts .alert").last).to_contain_text("destination")
    # And the destination can still be given afterwards.
    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("1 item")


@pytest.mark.e2e
def test_clearing_the_queue_after_a_hand_off_leaves_the_page_usable(page, live_server):
    """Edge case. The preselected items cannot be re-fetched by scanning a
    location again, so the page must fall back to ordinary scanning rather than
    to a dead state."""
    _seed(live_server)
    _hand_off_from_list(page, live_server, [i["ja_id"] for i in ITEMS])

    scan_on_move_page(page, DESTINATION)
    expect(page.locator("#queue-count")).to_have_text("3 items")

    page.locator("#clear-queue-btn").click()
    expect(page.locator("#queue-count")).to_have_text("0 items")
    expect(page.locator("#move-queue-empty")).to_be_visible()

    scan_on_move_page(page, "JA000101")
    scan_on_move_page(page, DESTINATION)
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(page.locator("#validate-btn")).to_be_enabled()


@pytest.mark.e2e
def test_the_hand_off_url_uses_the_one_convention(page, live_server):
    """FR-001 / contract section 1. The producers are separate code paths that
    once disagreed; this pins the spelling both of them must emit."""
    _seed(live_server)
    _hand_off_from_list(page, live_server, ["JA000101", "JA000102"])
    assert re.search(r"[?&]ja_id=JA000101(,|%2C)JA000102", page.url), page.url
    assert "items=" not in page.url, page.url

    _hand_off_from_search(page, live_server, ["JA000101", "JA000102"])
    assert re.search(r"[?&]ja_id=JA000101(,|%2C)JA000102", page.url), page.url
    assert "items=" not in page.url, page.url


@pytest.mark.e2e
def test_removing_a_queued_row_does_not_misplace_the_group_sub_location(page, live_server):
    """The group's sub-location must follow the items, not their positions.

    The queue's per-row Remove button splices `moveQueue`, so every row after
    the removed one shifts down. A group remembered by queue position would then
    write its sub-location onto whichever item slid into the vacated index --
    and, for the last index, onto nothing at all, throwing before the state
    machine could reset and leaving the page wedged with no way forward. That is
    the failure class this feature exists to close (#107), reached by a
    different route.
    """
    _seed(live_server)
    _hand_off_from_list(page, live_server, [i["ja_id"] for i in ITEMS])

    scan_on_move_page(page, DESTINATION)
    expect(_queue_rows(page)).to_have_count(3)

    # Remove the *first* row, so every remaining row's index shifts.
    _queue_row(page, "JA000101").locator("button").click()
    expect(_queue_rows(page)).to_have_count(2)

    scan_on_move_page(page, "Drawer 3")

    # Both survivors carry the sub-location, and the page is still usable.
    for spec in ITEMS[1:]:
        expect(_queue_row(page, spec["ja_id"])).to_contain_text("Drawer 3")
    expect(page.locator("#scanner-status")).to_have_text("Ready for JA ID")
    expect(page.locator("#validate-btn")).to_be_enabled()

    scan_on_move_page(page, "JA000101")
    scan_on_move_page(page, DESTINATION)
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("3 items")


@pytest.mark.e2e
def test_a_group_whose_rows_were_all_removed_leaves_the_page_usable(page, live_server):
    """The same hazard at its limit: nothing is left for the sub-location to
    attach to, and the page must say so rather than wedge."""
    _seed(live_server)
    _hand_off_from_list(page, live_server, [i["ja_id"] for i in ITEMS])

    scan_on_move_page(page, DESTINATION)
    expect(_queue_rows(page)).to_have_count(3)

    # The badge, not the row count: updateQueueDisplay() only re-renders the
    # rows while the queue is non-empty, so the last one lingers in the table
    # after it is hidden. The badge is written on every update.
    for remaining in ("2 items", "1 item", "0 items"):
        _queue_rows(page).first.locator("button").click()
        expect(page.locator("#queue-count")).to_have_text(remaining)

    scan_on_move_page(page, "Drawer 3")
    expect(page.locator("#form-alerts .alert").last).to_contain_text("no longer in the queue")

    # Still usable: an ordinary scan works from here.
    scan_on_move_page(page, "JA000101")
    scan_on_move_page(page, DESTINATION)
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(page.locator("#validate-btn")).to_be_enabled()
