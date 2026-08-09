"""
E2E tests for the reorder view.

Story 6: one view of everything low, with what is already coming marked. Two
things get particular attention here because they are easy to get subtly wrong
and impossible to notice from the UI afterwards:

- quantity = 0 and quantity = NULL must look different *everywhere* (SC-007).
- FR-029 is asymmetric: receiving clears a threshold-derived low by updating the
  count, and clears a manual flag only because the receive path says so.
"""

from datetime import datetime, timedelta

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.waits import wait_for_stock_flag


def create_product(page, base_url, description):
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)
    page.click("#save-product-btn")
    # The save redirects to the detail page; wait for it rather than for the
    # form page we are leaving.
    expect(page.locator("#stock-card")).to_be_visible()
    return page.url


def set_quantity(page, product_url, quantity, threshold=None):
    """Set a quantity through the API, then a threshold through the edit form"""
    product_id = product_url.rstrip('/').split('/')[-1]
    page.goto(product_url)
    page.evaluate(
        """async ([id, quantity]) => {
            await fetch(`/api/products/${id}/quantity`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ quantity: quantity })
            });
        }""",
        [product_id, quantity],
    )

    if threshold is not None:
        page.goto(f"{product_url}/edit")
        page.wait_for_load_state("domcontentloaded")
        page.fill("#reorder_threshold", str(threshold))
        page.click("#save-product-btn")
        page.wait_for_load_state("domcontentloaded")


def flag_low(page, product_url, status='low'):
    page.goto(product_url)
    page.click(f"#flag-{status}-btn")
    wait_for_stock_flag(page, status)


def add_outstanding_order(page, product_url, vendor='Amazon', quantity='10'):
    page.goto(product_url)
    page.click("text=Add Purchase")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#vendor", vendor)
    page.fill("#order_date", "2026-01-14")
    page.fill("#quantity", quantity)
    page.click("#save-purchase-btn")
    page.wait_for_load_state("domcontentloaded")


def reorder_rows(page, base_url):
    page.goto(f"{base_url}/products/reorder")
    links = page.locator("#reorder-table tbody tr.reorder-row td:first-child a")
    return sorted(links.nth(i).inner_text().strip() for i in range(links.count()))


@pytest.mark.e2e
def test_both_kinds_of_low_appear_in_one_view(page, live_server):
    """FR-027"""
    manual = create_product(page, live_server.url, "Flagged by hand")
    flag_low(page, manual)

    tracked = create_product(page, live_server.url, "At its threshold")
    set_quantity(page, tracked, 1, threshold=5)

    plenty = create_product(page, live_server.url, "Plenty in stock")
    set_quantity(page, plenty, 50, threshold=5)

    assert reorder_rows(page, live_server.url) == ["At its threshold", "Flagged by hand"]


@pytest.mark.e2e
def test_an_outstanding_order_is_marked_on_the_way(page, live_server):
    """FR-028, derived rather than recorded"""
    product = create_product(page, live_server.url, "Already ordered")
    set_quantity(page, product, 1, threshold=5)
    add_outstanding_order(page, product)

    page.goto(f"{live_server.url}/products/reorder")
    expect(page.locator(".on-order-badge")).to_be_visible()


@pytest.mark.e2e
def test_receiving_clears_a_threshold_derived_low(page, live_server):
    """The count goes up, so the derivation stops firing on its own"""
    product = create_product(page, live_server.url, "Tracked and low")
    set_quantity(page, product, 1, threshold=5)
    add_outstanding_order(page, product, quantity="10")

    assert reorder_rows(page, live_server.url) == ["Tracked and low"]

    page.goto(f"{live_server.url}/products/reorder")
    page.click(".receive-btn")
    page.wait_for_load_state("domcontentloaded")
    page.click("#confirm-receive-btn")
    page.wait_for_load_state("domcontentloaded")

    assert reorder_rows(page, live_server.url) == []


@pytest.mark.e2e
def test_receiving_clears_a_manually_flagged_low(page, live_server):
    """The other half of FR-029 -- nothing else would clear this"""
    product = create_product(page, live_server.url, "Flagged by hand")
    flag_low(page, product)
    add_outstanding_order(page, product)

    assert reorder_rows(page, live_server.url) == ["Flagged by hand"]

    page.goto(f"{live_server.url}/products/reorder")
    page.click(".receive-btn")
    page.wait_for_load_state("domcontentloaded")
    page.click("#confirm-receive-btn")
    page.wait_for_load_state("domcontentloaded")

    assert reorder_rows(page, live_server.url) == []


@pytest.mark.e2e
def test_none_on_hand_and_not_tracked_look_different_on_the_product_page(page, live_server):
    """SC-007, on the detail view"""
    counted = create_product(page, live_server.url, "Counted, none left")
    set_quantity(page, counted, 0)
    page.goto(counted)
    expect(page.locator("#quantity-value")).to_contain_text("None on hand")

    untracked = create_product(page, live_server.url, "Never counted")
    page.goto(untracked)
    expect(page.locator("#quantity-value")).to_contain_text("Not tracked")


@pytest.mark.e2e
def test_none_on_hand_and_not_tracked_look_different_in_the_catalogue_list(page, live_server):
    """SC-007, everywhere quantity is shown"""
    counted = create_product(page, live_server.url, "Counted, none left")
    set_quantity(page, counted, 0)
    create_product(page, live_server.url, "Never counted")

    page.goto(f"{live_server.url}/products")
    table = page.locator("#product-table")
    expect(table).to_contain_text("None on hand")
    expect(table).to_contain_text("Not tracked")


@pytest.mark.e2e
def test_the_detail_view_shows_the_age_of_a_count_not_the_bare_number(page, live_server):
    """FR-024"""
    product = create_product(page, live_server.url, "Tracked thing")
    set_quantity(page, product, 7)

    page.goto(product)
    expect(page.locator("#quantity-age")).to_be_visible()
    expect(page.locator("#quantity-age")).to_contain_text("counted")


@pytest.mark.e2e
def test_an_untracked_product_shows_no_age(page, live_server):
    product = create_product(page, live_server.url, "Never counted")
    page.goto(product)
    expect(page.locator("#quantity-age")).to_have_count(0)


@pytest.mark.e2e
def test_all_three_quantity_states_are_reachable_by_button(page, live_server):
    """FR-036: no keyboard required to get to any of them"""
    product = create_product(page, live_server.url, "Widget")

    page.goto(product)
    expect(page.locator("#quantity-value")).to_contain_text("Not tracked")

    page.click("#start-tracking-btn")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#quantity-value")).to_contain_text("None on hand")

    page.click("#quantity-increment")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#quantity-value")).to_contain_text("1")

    page.click("#stop-tracking-btn")
    page.wait_for_load_state("domcontentloaded")
    expect(page.locator("#quantity-value")).to_contain_text("Not tracked")


@pytest.mark.e2e
def test_the_manual_flag_is_set_and_cleared_by_button(page, live_server):
    product = create_product(page, live_server.url, "Widget")

    page.goto(product)
    page.click("#flag-low-btn")
    wait_for_stock_flag(page, 'low')
    assert reorder_rows(page, live_server.url) == ["Widget"]

    page.goto(product)
    page.click("#clear-flag-btn")
    wait_for_stock_flag(page, None)
    assert reorder_rows(page, live_server.url) == []


@pytest.mark.e2e
def test_two_flagged_products_show_when_each_was_flagged(page, live_server):
    """008 SC-004 -- the whole point of dating the flag.

    This is the screen where the operator decides what to buy. Before feature
    008 these two rows were indistinguishable, so a flag set this morning and
    one set two years ago and forgotten looked like equally good evidence.
    Seeded rather than driven: the flag buttons are covered above, and an age
    cannot be set through them anyway.
    """
    service = CatalogService(live_server.storage)
    recent = service.create_product(description='Flagged recently')
    stale = service.create_product(description='Flagged long ago')
    for product in (recent, stale):
        service.set_stock_status(product.id, 'low')
    live_server.backdate_product(
        recent.id, stock_status_updated_at=datetime.now() - timedelta(days=9)
    )
    live_server.backdate_product(
        stale.id, stock_status_updated_at=datetime.now() - timedelta(days=800)
    )

    page.goto(f"{live_server.url}/products/reorder")
    expect(page.locator(f"tr[data-product-id='{recent.id}'] .flag-age")).to_have_text(
        "9 days ago"
    )
    expect(page.locator(f"tr[data-product-id='{stale.id}'] .flag-age")).to_have_text(
        "2 years ago"
    )
