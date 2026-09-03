"""
E2E tests for the age shown beside a stock assertion (feature 008).

The feature is one claim in two places: an assertion about stock displays the age
of the evidence behind it, and nothing claims evidence it does not have. These
tests drive the two screens where that shows -- the product detail page and the
reorder list -- and seed everything else directly, because the seeding is not
what is under test.

Every age is server-rendered: `product-stock.js` reloads the page after each
successful PATCH rather than patching the DOM, so nothing here is asserting
against a JavaScript-rendered region.
"""

from datetime import datetime, timedelta

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from app.utils.clock import utc_now
from tests.e2e.waits import wait_for_stock_flag


def days_ago(days):
    """An age is unreachable through the UI -- every write path stamps now()

    Seeded on the application clock, which is what the age properties
    subtract from (feature 037). A local ``datetime.now()`` here would be
    off by the UTC offset -- harmless at the 100- and 400-day ages below,
    and the same defect this feature exists to remove.
    """
    return utc_now() - timedelta(days=days)


@pytest.mark.e2e
def test_receiving_does_not_reset_a_counted_age(page, live_server):
    """008 FR-007, FR-008, SC-001: the number moves and the age does not.

    Receiving used to stamp the count as freshly updated, so the screen read
    "counted just now" when nobody had counted anything.
    """
    service = CatalogService(live_server.storage)
    product = service.create_product(
        description='M3 standoff', quantity=4, reorder_threshold=5
    )
    service.record_purchase(
        product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), quantity=100
    )
    live_server.backdate_product(product.id, quantity_updated_at=days_ago(100))

    page.goto(f"{live_server.url}/products/reorder")
    receive = page.locator(f"tr[data-product-id='{product.id}'] .receive-btn")
    expect(receive).to_be_visible()
    receive.click()

    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    page.click("#confirm-receive-btn")

    # Receiving redirects to the product page. The increased count is the proof
    # the round trip landed, so it is also the wait for the age assertion below.
    expect(page.locator("#quantity-value")).to_contain_text("104")
    expect(page.locator("#quantity-age")).to_contain_text("3 months ago")


@pytest.mark.e2e
def test_flagging_a_product_shows_the_flag_as_just_set(page, live_server):
    """008 FR-001, FR-004 -- the flag arrives with its age attached"""
    product = CatalogService(live_server.storage).create_product(description='Blue tape')

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#flag-age")).to_have_count(0)

    page.click("#flag-low-btn")
    wait_for_stock_flag(page, 'low')

    expect(page.locator("#flag-age")).to_have_text("Flagged low just now")


@pytest.mark.e2e
def test_a_flag_with_no_recorded_date_says_so(page, live_server):
    """008 FR-005, SC-006 -- every row that predates this feature.

    Nothing is backfilled, so the honest answer is that the date is unknown. No
    other date is substituted, and this is not an error state.
    """
    service = CatalogService(live_server.storage)
    product = service.create_product(description='Legacy flagged thing')
    service.set_stock_status(product.id, 'low')
    live_server.backdate_product(product.id, stock_status_updated_at=None)

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#flag-age")).to_have_text("Flagged low at an unknown time")


@pytest.mark.e2e
def test_clearing_a_flag_removes_the_age_line_entirely(page, live_server):
    """008 FR-003 -- absent, not blank: there is no flag to date"""
    service = CatalogService(live_server.storage)
    product = service.create_product(description='Blue tape')
    service.set_stock_status(product.id, 'low')

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#flag-age")).to_be_visible()

    page.click("#clear-flag-btn")
    wait_for_stock_flag(page, None)

    expect(page.locator("#flag-age")).to_have_count(0)


@pytest.mark.e2e
def test_receiving_leaves_neither_a_flag_nor_a_flag_age(page, live_server):
    """008 FR-006 -- no stale age survives to be shown if it is flagged again"""
    service = CatalogService(live_server.storage)
    product = service.create_product(description='Flagged by hand')
    service.set_stock_status(product.id, 'low')
    service.record_purchase(
        product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), quantity=10
    )
    live_server.backdate_product(product.id, stock_status_updated_at=days_ago(400))

    page.goto(f"{live_server.url}/products/reorder")
    expect(page.locator(f"tr[data-product-id='{product.id}'] .flag-age")).to_have_text(
        "1 year ago"
    )
    page.click(f"tr[data-product-id='{product.id}'] .receive-btn")

    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    page.click("#confirm-receive-btn")

    # Redirected to the product page: the flag buttons are back to their outline
    # variants, which is the proof the receipt landed.
    wait_for_stock_flag(page, None)
    expect(page.locator("#flag-age")).to_have_count(0)


@pytest.mark.e2e
def test_adjusting_a_count_at_the_shelf_resets_its_age(page, live_server):
    """008 FR-010 -- the boundary that keeps FR-008 from over-reaching.

    The operator pressing + or - is holding the things, so that *is* a count.
    The buttons reach PATCH /api/products/<id>/quantity, the same endpoint the
    typed count uses; they must not become a separate path that forgets to
    stamp the age.
    """
    product = CatalogService(live_server.storage).create_product(
        description='M3 standoff', quantity=4
    )
    live_server.backdate_product(product.id, quantity_updated_at=days_ago(100))

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#quantity-age")).to_contain_text("3 months ago")

    page.click("#quantity-increment")

    # The button PATCHes and then reloads; the new count is the proof the round
    # trip finished, and the age line is re-rendered by that same reload.
    expect(page.locator("#quantity-value")).to_contain_text("5")
    expect(page.locator("#quantity-age")).to_have_text("counted just now")
