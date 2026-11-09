"""E2E: scanning several IDs, then one location (feature 069, issue #223).

IDs scanned back to back on a move page form a *scanned group* that waits for
one destination; the next location queues them all, and a sub-location
scanned straight after applies to the whole group. Covers Move Products,
Move Items and the handheld Move screen, which share MoveManager.

Every scan goes through ``waits.scan_on_move_page``, which waits on the
transition's own signal (a group row appended, the queue count, an alert), so
nothing here waits on a clock.

Author: Jason Antman, 2026.
"""

import pytest
from playwright.sync_api import Page, expect

from app.catalog_service import CatalogService
from tests.e2e.waits import scan_on_move_page, wait_for_move_executed

GROUP_ROWS = "#scan-group-rows tr"


def _product(live_server, **fields):
    return CatalogService(live_server.storage).create_product(**fields)


def _item(ja_id: str) -> dict:
    return {
        "ja_id": ja_id, "item_type": "Bar", "shape": "Round", "material": "Carbon Steel",
        "length": "12.0", "width": "0.5", "location": "Storage A", "active": True,
    }


def _open(page: Page, url: str) -> None:
    page.goto(url)
    expect(page.locator("#barcode-input")).to_be_focused()
    expect(page.locator("#scanner-status")).to_have_text("Ready")


def _row(page: Page, subject_id: str):
    return page.locator("#queue-items tr").filter(has_text=subject_id)


def _alerts(page: Page):
    return page.locator("#form-alerts .alert")


@pytest.mark.e2e
def test_three_products_one_location_and_sub_location(page, live_server):
    """US1 scenarios 1-3 and SC-002: scan many, one location, one sub-location,
    execute; each row keeps its own current location."""
    a = _product(live_server, description="Bag A", location="M2", sub_location="Bin 4")
    b = _product(live_server, description="Bag B")
    c = _product(live_server, description="Bag C", location="Old shelf")
    _open(page, f"{live_server.url}/products/move")

    for product in (a, b, c):
        scan_on_move_page(page, product.internal_code)
    expect(page.locator("#scan-group")).to_be_visible()
    expect(page.locator("#scan-group-count")).to_have_text("3 products awaiting a destination")
    expect(page.locator("#queue-count")).to_have_text("0 items")
    expect(page.locator("#scanner-status")).to_have_text("Waiting for Destination")
    # Each waiting row shows where the product is now, once looked up.
    expect(page.locator(GROUP_ROWS).filter(has_text=a.internal_code)
           .locator(".pending-current-location")).to_have_text("M2")

    scan_on_move_page(page, "Shelf 2")
    expect(page.locator("#scan-group")).to_be_hidden()
    expect(page.locator(GROUP_ROWS)).to_have_count(0)
    scan_on_move_page(page, "Bin 9")
    scan_on_move_page(page, ">>DONE<<")

    expect(page.locator("#queue-count")).to_have_text("3 items")
    for product in (a, b, c):
        row = _row(page, product.internal_code)
        expect(row.locator("td").nth(3)).to_have_text("Shelf 2")
        expect(row.locator("td").nth(4)).to_contain_text("Bin 9")
    expect(_row(page, a.internal_code).locator("td").nth(1)).to_have_text("M2")
    expect(_row(page, a.internal_code).locator("td").nth(2)).to_have_text("Bin 4")
    expect(_row(page, c.internal_code).locator("td").nth(1)).to_have_text("Old shelf")

    page.locator("#validate-btn").click()
    expect(page.locator("#execute-moves-btn")).to_be_enabled()
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#execute-moves-btn").click()
    wait_for_move_executed(page)

    for product in (a, b, c):
        page.goto(f"{live_server.url}/products/{product.id}")
        expect(page.locator("#product-location")).to_have_text("Shelf 2")
        expect(page.locator("#product-sub-location")).to_have_text("Bin 9")


@pytest.mark.e2e
def test_items_group_then_a_new_id_starts_a_new_move(page, live_server):
    """US1 scenarios 4-5: on Move Items, a group takes an M-location; an ID
    scanned after it starts a new move, and the group keeps no sub-location."""
    live_server.add_test_data([_item("JA230001"), _item("JA230002"), _item("JA230003")])
    _open(page, f"{live_server.url}/inventory/move")

    scan_on_move_page(page, "JA230001")
    scan_on_move_page(page, "JA230002")
    scan_on_move_page(page, "M1-A")
    expect(page.locator("#queue-count")).to_have_text("2 items")

    scan_on_move_page(page, "JA230003")
    scan_on_move_page(page, "M3-C")
    scan_on_move_page(page, "Drawer 1")
    expect(page.locator("#queue-count")).to_have_text("3 items")

    for ja_id in ("JA230001", "JA230002"):
        row = _row(page, ja_id)
        expect(row.locator("td").nth(3)).to_have_text("M1-A")
        expect(row.locator("td").nth(4)).not_to_contain_text("Drawer 1")
    third = _row(page, "JA230003")
    expect(third.locator("td").nth(3)).to_have_text("M3-C")
    expect(third.locator("td").nth(4)).to_contain_text("Drawer 1")


@pytest.mark.e2e
def test_a_sub_location_is_refused_while_a_group_waits(page, live_server):
    """Items page: free text while a group waits is a sub-location, and the
    group has no location yet to hang one on."""
    live_server.add_test_data([_item("JA230011"), _item("JA230012")])
    _open(page, f"{live_server.url}/inventory/move")

    scan_on_move_page(page, "JA230011")
    scan_on_move_page(page, "JA230012")
    scan_on_move_page(page, "Drawer 1")
    expect(_alerts(page).last).to_contain_text("a sub-location is not one")
    expect(page.locator(GROUP_ROWS)).to_have_count(2)


@pytest.mark.e2e
def test_duplicates_are_refused_and_members_can_be_removed(page, live_server):
    """US3 scenarios 1-3: a duplicate leaves the group unchanged; Remove takes
    one subject out; removing the last returns to waiting for an ID."""
    live_server.add_test_data([_item(f"JA23002{n}") for n in range(1, 6)])
    _open(page, f"{live_server.url}/inventory/move")

    # Already queued.
    scan_on_move_page(page, "JA230021")
    scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, "JA230022")
    scan_on_move_page(page, "JA230021")
    expect(_alerts(page).last).to_contain_text("already in the move queue")

    # The subject in progress, scanned again.
    scan_on_move_page(page, "JA230022")
    expect(_alerts(page).last).to_contain_text("already waiting for a destination")
    expect(page.locator(GROUP_ROWS)).to_have_count(0)

    # Already in the group.
    scan_on_move_page(page, "JA230023")
    scan_on_move_page(page, "JA230024")
    scan_on_move_page(page, "JA230023")
    expect(_alerts(page).last).to_contain_text("already waiting for a destination")
    expect(page.locator(GROUP_ROWS)).to_have_count(3)

    page.locator(f'{GROUP_ROWS}[data-id="JA230024"] .scan-group-remove').click()
    expect(page.locator(GROUP_ROWS)).to_have_count(2)
    expect(page.locator("#scan-group-count")).to_have_text("2 items awaiting a destination")

    scan_on_move_page(page, "M2-B")
    expect(page.locator("#queue-count")).to_have_text("3 items")
    expect(_row(page, "JA230024")).to_have_count(0)
    expect(_row(page, "JA230022").locator("td").nth(3)).to_have_text("M2-B")
    expect(_row(page, "JA230023").locator("td").nth(3)).to_have_text("M2-B")

    # Removing every member returns the page to waiting for an ID.
    scan_on_move_page(page, "JA230024")
    scan_on_move_page(page, "JA230025")
    expect(page.locator(GROUP_ROWS)).to_have_count(2)
    for ja_id in ("JA230024", "JA230025"):
        page.locator(f'{GROUP_ROWS}[data-id="{ja_id}"] .scan-group-remove').click()
    expect(page.locator("#scan-group")).to_be_hidden()
    expect(page.locator("#scanner-status")).to_have_text("Ready for JA ID")
    expect(page.locator("#validate-btn")).to_be_enabled()


@pytest.mark.e2e
def test_done_and_validate_while_a_group_waits(page, live_server):
    """US3 scenario 4 and FR-011: >>DONE<< does not queue a group with no
    destination; Validate stays unavailable and says why until it has one."""
    live_server.add_test_data([_item("JA230031"), _item("JA230032"), _item("JA230033")])
    _open(page, f"{live_server.url}/inventory/move")

    scan_on_move_page(page, "JA230031")
    scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, "JA230032")
    scan_on_move_page(page, "JA230033")
    expect(page.locator("#validate-btn")).to_be_disabled()
    expect(page.locator("#validate-hint")).to_contain_text("2 items still need a destination")

    scan_on_move_page(page, ">>DONE<<")
    expect(_alerts(page).last).to_contain_text("2 items awaiting a destination were not queued")
    # The move finished before the group started is still queued.
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(page.locator(GROUP_ROWS)).to_have_count(2)

    scan_on_move_page(page, "M2-B")
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("3 items")
    expect(page.locator("#validate-btn")).to_be_enabled()


@pytest.mark.e2e
def test_clear_all_discards_a_waiting_group(page, live_server):
    """US3 scenario 5."""
    live_server.add_test_data([_item("JA230041"), _item("JA230042")])
    _open(page, f"{live_server.url}/inventory/move")

    scan_on_move_page(page, "JA230041")
    scan_on_move_page(page, "JA230042")
    expect(page.locator("#scan-group")).to_be_visible()

    page.locator("#clear-all-btn").click()
    expect(page.locator("#scan-group")).to_be_hidden()
    expect(page.locator(GROUP_ROWS)).to_have_count(0)
    expect(page.locator("#scanner-status")).to_have_text("Ready")

    # And the page scans normally afterwards.
    scan_on_move_page(page, "JA230041")
    scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("1 item")


@pytest.mark.e2e
def test_handheld_two_codes_then_a_location(handheld_page, live_server):
    """US4: the handheld Move screen shows the waiting group and queues it."""
    page = handheld_page
    a = _product(live_server, description="Bag A")
    b = _product(live_server, description="Bag B")
    _open(page, f"{live_server.url}/h/move?kind=products")

    scan_on_move_page(page, a.internal_code)
    scan_on_move_page(page, b.internal_code)
    expect(page.locator("#scan-group")).to_be_visible()
    expect(page.locator("#scan-group-count")).to_have_text("2 products awaiting a destination")

    scan_on_move_page(page, "Shelf 2")
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("2 items")
    for product in (a, b):
        expect(_row(page, product.internal_code)).to_contain_text("Shelf 2")


@pytest.mark.e2e
def test_a_group_queued_before_its_lookups_return_is_corrected(page, live_server):
    """Queueing a group does not wait on the network: a row whose lookup is
    still out shows "Unknown", then its real current location once it lands,
    and a sub-location scanned in between still applies to the whole group."""
    a = _product(live_server, description="Bag A", location="Bench")
    b = _product(live_server, description="Bag B", location="Floor")
    _open(page, f"{live_server.url}/products/move")

    held = []
    page.route("**/api/products/by-code/**", lambda route: held.append(route))
    scan_on_move_page(page, a.internal_code)
    scan_on_move_page(page, b.internal_code)
    scan_on_move_page(page, "Shelf 2")
    scan_on_move_page(page, "Bin 1")
    # A round trip flushes the route events to the handler before they are read.
    page.evaluate("1")
    assert len(held) == 2

    rows = page.locator("#queue-items tr")
    expect(rows).to_have_count(2)
    expect(_row(page, a.internal_code).locator("td").nth(1)).to_have_text("Unknown")

    for route in held:
        route.continue_()
    page.unroute("**/api/products/by-code/**")
    expect(_row(page, a.internal_code).locator("td").nth(1)).to_have_text("Bench")
    expect(_row(page, b.internal_code).locator("td").nth(1)).to_have_text("Floor")
    for product in (a, b):
        expect(_row(page, product.internal_code).locator("td").nth(4)).to_contain_text("Bin 1")
