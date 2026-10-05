"""
E2E tests for the product Move page (feature 057, issue #188).

The page is the item Move page's scan machine (MoveManager) driven by
ProductMoveManager, so these tests cover what is particular to products --
the WIT code, products with no location, the JA-label refusal, the product
endpoints and the detail page's Move button -- plus the refusals of US2 on
this page. Every scan goes through waits.scan_on_move_page, which asks the
page how it classifies the value, so no scan here waits on a clock.

Products are seeded through CatalogService directly (milliseconds) rather than
through the Add Product form, which is not under test.
"""

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.waits import scan_on_move_page, wait_for_move_executed

UNKNOWN_CODE = "WIT0000000000"


def _seed(live_server, **fields):
    return CatalogService(live_server.storage).create_product(**fields)


def _open(page, live_server):
    page.goto(f"{live_server.url}/products/move")
    expect(page.locator("#barcode-input")).to_be_focused()
    expect(page.locator("#scanner-status")).to_have_text("Ready")


def _row(page, code):
    return page.locator("#queue-items tr").filter(has_text=code)


def _alerts(page):
    return page.locator("#form-alerts .alert")


@pytest.mark.e2e
def test_shelve_two_products_scan_validate_execute(page, live_server):
    """US1: one product never located, one being moved; both end up shelved."""
    new = _seed(live_server, description="Blue tape")
    moving = _seed(live_server, description="M3 nuts", location="M2", sub_location="Bin 4")
    _open(page, live_server)

    scan_on_move_page(page, new.internal_code)
    scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, "Drawer 3")
    # Lower case, as a person retyping a scuffed label would.
    scan_on_move_page(page, moving.internal_code.lower())
    scan_on_move_page(page, "T-3")
    scan_on_move_page(page, ">>DONE<<")

    expect(page.locator("#queue-count")).to_have_text("2 items")

    # A product with no location reads "None", not "Unknown" (US1 scenario 1).
    new_row = _row(page, new.internal_code)
    expect(new_row).to_contain_text("Blue tape")
    expect(new_row.locator("td").nth(1)).to_have_text("None")
    expect(new_row.locator("td").nth(3)).to_have_text("M1-A")
    expect(new_row.locator("td").nth(4)).to_have_text("Drawer 3")

    # The existing sub-location is visibly about to be cleared (scenario 5).
    moving_row = _row(page, moving.internal_code)
    expect(moving_row.locator("td").nth(1)).to_have_text("M2")
    expect(moving_row.locator("td").nth(2)).to_have_text("Bin 4")
    expect(moving_row.locator("td").nth(4)).to_have_text("Cleared")

    page.locator("#validate-btn").click()
    expect(page.locator("#validation-section")).to_be_visible()
    expect(new_row.locator("td").nth(5)).to_have_text("validated")
    expect(moving_row.locator("td").nth(5)).to_have_text("validated")
    # Validation refreshes the current location rather than losing it.
    expect(moving_row.locator("td").nth(1)).to_have_text("M2")
    expect(page.locator("#execute-moves-btn")).to_be_enabled()

    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#execute-moves-btn").click()
    wait_for_move_executed(page)

    page.goto(f"{live_server.url}/products/{new.id}")
    expect(page.locator("#product-location")).to_have_text("M1-A")
    expect(page.locator("#product-sub-location")).to_have_text("Drawer 3")

    page.goto(f"{live_server.url}/products/{moving.id}")
    expect(page.locator("#product-location")).to_have_text("T-3")
    expect(page.locator("#product-sub-location")).to_contain_text("Not recorded")


@pytest.mark.e2e
def test_out_of_order_scans_are_refused(page, live_server):
    """US2 scenarios 1, 3 and 5: nothing queued that was not intended."""
    product = _seed(live_server, description="M3 nuts")
    _open(page, live_server)

    # A location where a product was expected.
    scan_on_move_page(page, "M1-A")
    expect(_alerts(page).last).to_contain_text("Expected Product Code")

    scan_on_move_page(page, product.internal_code)
    scan_on_move_page(page, "M1-A")
    # Two locations in a row.
    scan_on_move_page(page, "M2-B")
    expect(_alerts(page).last).to_contain_text("two locations in a row")
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("1 item")

    # The same product again.
    scan_on_move_page(page, product.internal_code)
    expect(_alerts(page).last).to_contain_text("already in the move queue")
    expect(page.locator("#queue-count")).to_have_text("1 item")


@pytest.mark.e2e
def test_an_inventory_item_label_is_refused_not_taken_as_a_sub_location(page, live_server):
    """US2 / edge case: a JA label after a location would otherwise become
    the product's sub-location."""
    product = _seed(live_server, description="M3 nuts")
    _open(page, live_server)

    scan_on_move_page(page, product.internal_code)
    scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, "JA000001")
    expect(_alerts(page).last).to_contain_text("Move Items page")

    # Still waiting for this move's sub-location or the next product.
    expect(page.locator("#scanner-status")).to_have_text(
        "Waiting for Product Code or Sub-Location")
    scan_on_move_page(page, ">>DONE<<")
    row = _row(page, product.internal_code)
    expect(row.locator("td").nth(3)).to_have_text("M1-A")
    expect(row.locator("td").nth(4)).not_to_contain_text("JA000001")


@pytest.mark.e2e
def test_a_missed_location_abandons_the_first_product(page, live_server):
    """US2 scenario 4 and 6: product then product, and the half-entered hint."""
    first = _seed(live_server, description="First")
    second = _seed(live_server, description="Second")
    _open(page, live_server)

    scan_on_move_page(page, first.internal_code)
    scan_on_move_page(page, second.internal_code)
    expect(_alerts(page).last).to_contain_text(f"No location was scanned for {first.internal_code}")

    scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, "Shelf 2")
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(_row(page, second.internal_code)).to_have_count(1)
    expect(_row(page, first.internal_code)).to_have_count(0)

    # Half-entered: Validate is unavailable and says why.
    scan_on_move_page(page, first.internal_code)
    expect(page.locator("#validate-btn")).to_be_disabled()
    expect(page.locator("#validate-hint")).to_contain_text(
        f"{first.internal_code} has no location yet")


@pytest.mark.e2e
def test_an_unknown_code_fails_validation_and_can_be_removed(page, live_server):
    """US2 scenarios 2 and 7."""
    product = _seed(live_server, description="M3 nuts")
    _open(page, live_server)

    scan_on_move_page(page, UNKNOWN_CODE)
    scan_on_move_page(page, "M1-A")
    scan_on_move_page(page, product.internal_code)
    scan_on_move_page(page, "M2-B")
    scan_on_move_page(page, ">>DONE<<")
    expect(page.locator("#queue-count")).to_have_text("2 items")

    page.locator("#validate-btn").click()
    expect(page.locator("#validation-section")).to_be_visible()
    unknown_row = _row(page, UNKNOWN_CODE)
    expect(unknown_row.locator("td").nth(5)).to_have_text("not_found")
    expect(_row(page, product.internal_code).locator("td").nth(5)).to_have_text("validated")
    expect(page.locator("#execute-moves-btn")).to_be_disabled()

    unknown_row.locator("button[title='Remove from queue']").click()
    expect(page.locator("#queue-count")).to_have_text("1 item")
    expect(page.locator("#execute-moves-btn")).to_be_enabled()


@pytest.mark.e2e
def test_move_from_the_product_page(page, live_server):
    """US3: the detail page's Move button opens the page with the product
    awaiting a destination."""
    # Angle brackets and an ampersand: the description is free text, and the
    # queue must show it literally rather than parse it.
    description = "Washers <spare> & nuts"
    product = _seed(live_server, description=description, location="M2")
    page.goto(f"{live_server.url}/products/{product.id}")

    page.locator("#move-product-btn").click()
    expect(page).to_have_url(f"{live_server.url}/products/move?code={product.internal_code}")

    pending = page.locator("#pending-moves tbody tr")
    expect(pending).to_have_count(1)
    expect(pending).to_contain_text(product.internal_code)
    # Its current location arrives through the lookup.
    expect(pending.locator(".pending-current-location")).to_have_text("M2")
    expect(page.locator("#scanner-status")).to_have_text("Waiting for Destination")

    scan_on_move_page(page, "T-5")
    expect(page.locator("#queue-count")).to_have_text("1 item")
    row = _row(page, product.internal_code)
    expect(row.locator("td").nth(0)).to_contain_text(description)
    expect(row.locator("td").nth(1)).to_have_text("M2")
    expect(row.locator("td").nth(3)).to_have_text("T-5")
