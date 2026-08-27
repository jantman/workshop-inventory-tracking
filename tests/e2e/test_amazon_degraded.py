"""E2E: an Amazon order page that did not read cleanly (feature 029).

The rule these exist to hold: **a field that cannot be read costs that field
alone** (FR-021), and **the loss is stated** (FR-022). A blank price on one line
of eleven is not something the operator notices unaided, so a capture that
quietly drops it is worse than one that refuses -- they would find out during a
reconciliation months later.

The other rule is FR-023's distinction: "this page yielded no order" and "this
order has nothing in it" must not look the same.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_amazon_order import capture_order, confirm


@pytest.mark.e2e
def test_a_page_with_no_readable_rows_says_so(page, live_server, image_host):
    """FR-023. Not an empty review, and not an error page."""
    review = capture_order(
        page, live_server, image_host, fixture="amazon_order_unreadable.html"
    )

    expect(review.locator("#no-lines")).to_be_visible()
    expect(review.locator("tr.order-line")).to_have_count(0)


@pytest.mark.e2e
def test_and_it_still_names_the_order_it_recognized(page, live_server, image_host):
    """The order *was* read; only its lines were not. Saying otherwise would
    send the operator looking for a problem that is not there."""
    review = capture_order(
        page, live_server, image_host, fixture="amazon_order_unreadable.html"
    )

    expect(review.locator("#no-lines")).to_contain_text("111-9998887-7776665")


@pytest.mark.e2e
def test_recommended_items_do_not_become_lines_on_a_page_with_none(
    page, live_server, image_host
):
    """The row-scoping trap, at its most dangerous.

    This page has no order lines at all and three recommended ASINs. A
    document-wide sweep would offer three lines to capture from an order that
    yielded none.
    """
    review = capture_order(
        page, live_server, image_host, fixture="amazon_order_unreadable.html"
    )

    expect(review.locator("#no-lines")).to_be_visible()
    expect(review.locator("tr.order-line")).to_have_count(0)


@pytest.mark.e2e
def test_a_broken_row_costs_that_row_alone(page, live_server, image_host):
    """FR-021. Three rows: one complete, one with no ASIN, one with no price."""
    review = capture_order(
        page, live_server, image_host, fixture="amazon_order_partial.html"
    )

    expect(review.locator("tr.order-line")).to_have_count(3)


@pytest.mark.e2e
def test_a_line_with_no_item_id_is_marked_and_still_capturable(
    page, live_server, image_host
):
    """FR-019. Capturable on its title alone, or excludable -- never a refusal."""
    review = capture_order(
        page, live_server, image_host, fixture="amazon_order_partial.html"
    )

    row = review.locator('tr.order-line[data-line="2"]')
    expect(row.locator('.missing-field[data-field="part_number"]')).to_be_visible()
    expect(row.locator("input.include-line")).to_be_checked()


@pytest.mark.e2e
def test_an_unreadable_price_is_marked_rather_than_guessed(
    page, live_server, image_host
):
    """A blank the operator can fill in beats a number nobody chose."""
    review = capture_order(
        page, live_server, image_host, fixture="amazon_order_partial.html"
    )

    row = review.locator('tr.order-line[data-line="3"]')
    expect(row.locator('.missing-field[data-field="price"]')).to_be_visible()
    expect(row.locator("input.line-unit-price")).to_have_value("")


@pytest.mark.e2e
def test_the_complete_line_is_untouched_by_its_broken_neighbours(
    page, live_server, image_host
):
    """The whole point of FR-021, stated positively."""
    review = capture_order(
        page, live_server, image_host, fixture="amazon_order_partial.html"
    )

    row = review.locator('tr.order-line[data-line="1"]')
    expect(row.locator("input.line-unit-price")).to_have_value("4.25")
    expect(row.locator(".missing-field")).to_have_count(0)


@pytest.mark.e2e
def test_a_degraded_order_still_captures(page, live_server, image_host):
    """And what came back thin is named after the review is gone (FR-022)."""
    review = capture_order(
        page, live_server, image_host, fixture="amazon_order_partial.html"
    )
    confirm(review)

    # **Asserted on `review`, not on `page`.** The bookmarklet submits into a
    # new tab, so the review -- and the order screen the confirmation redirects
    # to -- live on that one; `page` is still sitting on the vendor's fixture.
    # And no second navigation: the flash is shown once, on the page the
    # redirect lands on, so navigating again would consume it unread.
    expect(review.locator("tr.order-line")).to_have_count(3)
    expect(review.locator("body")).to_contain_text("did not give up every field")
