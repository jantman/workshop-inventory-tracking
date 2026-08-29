"""E2E: capturing an order that has already arrived (feature 031, US3).

Rides the Amazon harness from ``test_amazon_order.py`` because it is the
cheapest whole order to get onto a review; what is under test is the arrival
control and the two derived screens behind it, neither of which is Amazon's.

**The negative assertion here is the dangerous one.** "Nothing is outstanding"
passes trivially against a table that has not rendered, so every count is taken
only after an ``expect`` has established the region -- and the order screen's own
``#outstanding-count`` is read as text rather than counted from rows, because it
is the thing the operator actually reads.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_amazon_order import ORDER_ID, capture_order


def mark_arrived(review, date="2026-08-25"):
    """Tick the order-level box and give a date.

    The master checkbox reveals the date field and ticks every line's own box --
    synchronous DOM work with no request behind it, so the per-line box being
    checked is the complete signal (no fetch to wait on).
    """
    review.check("#order-arrived")
    expect(review.locator(".line-arrived").first).to_be_checked()
    expect(review.locator("#arrival-detail")).to_be_visible()
    review.fill("#arrived_date", date)
    return review


def confirm(review):
    """Submit and wait for the order screen the confirmation lands on."""
    review.click("#confirm-capture")
    # A full navigation, so the landing page's marker is the completion signal.
    expect(review.locator("#order-progress, #not-captured")).to_be_visible()
    return review


@pytest.mark.e2e
def test_the_arrival_controls_are_hidden_until_the_order_is_marked_arrived(
    page, live_server, image_host
):
    """Never the default: an ordinary capture must not meet this at all."""
    review = capture_order(page, live_server, image_host)

    expect(review.locator("#order-arrived")).not_to_be_checked()
    expect(review.locator("#arrival-detail")).to_be_hidden()
    expect(review.locator(".arrived-cell").first).to_be_hidden()


@pytest.mark.e2e
def test_a_backfilled_order_lands_with_nothing_outstanding(
    page, live_server, image_host
):
    """FR-024 and FR-027, on the screen the operator lands on."""
    review = capture_order(page, live_server, image_host)
    mark_arrived(review)

    confirm(review)

    expect(review.locator("#order-progress")).to_be_visible()
    expect(review.locator("#outstanding-count")).to_contain_text("All")
    expect(review.locator("#outstanding-count")).not_to_contain_text("outstanding")


@pytest.mark.e2e
def test_an_ordinary_capture_still_lands_outstanding(page, live_server, image_host):
    """The control being present must not change what happens without it."""
    review = capture_order(page, live_server, image_host)

    confirm(review)

    expect(review.locator("#outstanding-count")).to_contain_text("still outstanding")


@pytest.mark.e2e
def test_the_captured_orders_list_shows_it_complete(page, live_server, image_host):
    """FR-027 on the list that exists to answer what is still on its way."""
    review = capture_order(page, live_server, image_host)
    mark_arrived(review)
    confirm(review)

    page.goto(f"{live_server.url}/products/orders")
    # Established before anything is read off it -- an empty table would satisfy
    # the assertion below by saying nothing at all.
    expect(page.locator("#orders-table")).to_be_visible()
    row = page.locator(f'tr.captured-order[data-order="{ORDER_ID}"]')
    expect(row).to_have_count(1)

    expect(row).to_contain_text("all received")
    expect(row).to_have_attribute("data-complete", "true")


@pytest.mark.e2e
def test_a_held_back_line_stays_outstanding(page, live_server, image_host):
    """FR-029 -- the box came, except for the one thing that did not."""
    review = capture_order(page, live_server, image_host)
    mark_arrived(review)
    boxes = review.locator(".line-arrived")
    expect(boxes).to_have_count(4)
    boxes.last.uncheck()

    confirm(review)

    expect(review.locator("#outstanding-count")).to_contain_text("1 of 4 still outstanding")
