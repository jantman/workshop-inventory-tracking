"""E2E: receiving an Amazon order from its screen (feature 029, US2).

The Amazon order arrives in four boxes over a week, and nothing in any of them
names the order or the line it belongs to. So this is the screen-driven path,
and these tests walk it the way the operator does: open the order, receive what
turned up, come back tomorrow.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_amazon_order import (
    LINE_COUNT,
    capture_order,
    confirm,
    order_screen,
)


def receive_first_outstanding(page):
    """Click the first outstanding line's Receive, and land on its receipt."""
    page.locator("tr.order-line[data-outstanding='true'] a.receive-line").first.click()
    # A full navigation, so the receipt's own submit control is the completion
    # signal (pattern C).
    expect(page.locator("button[type=submit]").first).to_be_visible()
    return page


@pytest.mark.e2e
def test_the_order_screen_lists_every_line_as_outstanding(page, live_server, image_host):
    confirm(capture_order(page, live_server, image_host))

    order_screen(page, live_server)

    expect(page.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(
        page.locator("tr.order-line[data-outstanding='true']")
    ).to_have_count(LINE_COUNT)
    expect(page.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT} of {LINE_COUNT}"
    )


@pytest.mark.e2e
def test_receiving_a_line_takes_it_off_the_outstanding_count(
    page, live_server, image_host
):
    confirm(capture_order(page, live_server, image_host))
    order_screen(page, live_server)

    receive_first_outstanding(page)
    page.locator("button[type=submit]").first.click()

    order_screen(page, live_server)
    expect(page.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT - 1} of {LINE_COUNT}"
    )
    expect(
        page.locator("tr.order-line[data-outstanding='false']")
    ).to_have_count(1)


@pytest.mark.e2e
def test_a_received_line_offers_no_second_receipt(page, live_server, image_host):
    """FR-031. Nothing is received twice."""
    confirm(capture_order(page, live_server, image_host))
    order_screen(page, live_server)
    receive_first_outstanding(page)
    page.locator("button[type=submit]").first.click()

    order_screen(page, live_server)

    expect(page.locator("a.receive-line")).to_have_count(LINE_COUNT - 1)


@pytest.mark.e2e
def test_an_uncaptured_order_number_is_not_a_404(page, live_server):
    """FR-032. Nothing dead-ends."""
    page.goto(f"{live_server.url}/products/orders/Amazon/111-0000000-0000000")

    expect(page.locator("#not-captured")).to_be_visible()


@pytest.mark.e2e
def test_the_order_says_it_is_complete_once_everything_is_in(
    page, live_server, image_host
):
    confirm(capture_order(page, live_server, image_host))

    for _ in range(LINE_COUNT):
        order_screen(page, live_server)
        receive_first_outstanding(page)
        page.locator("button[type=submit]").first.click()

    order_screen(page, live_server)
    expect(page.locator("#outstanding-count")).to_contain_text(
        f"All {LINE_COUNT} line(s) received"
    )
