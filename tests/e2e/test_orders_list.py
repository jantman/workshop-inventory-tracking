"""E2E: the captured-orders list (feature 029, US3).

The question this page exists to answer is "what is still on its way, from
anyone?" -- which the catalog previously could not answer at all. An order was
reachable only by knowing its number and typing it, or by being redirected onto
it by a scan.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_amazon_order import ORDER_ID, capture_order, confirm


def orders_list(page, live_server):
    page.goto(f"{live_server.url}/products/orders")
    expect(page.locator("#orders-table, #no-orders")).to_be_visible()
    return page


@pytest.mark.e2e
def test_an_empty_catalog_says_so_rather_than_showing_a_bare_table(page, live_server):
    orders_list(page, live_server)

    expect(page.locator("#no-orders")).to_be_visible()


@pytest.mark.e2e
def test_a_captured_order_appears_with_its_vendor_and_number(
    page, live_server, image_host
):
    confirm(capture_order(page, live_server, image_host))

    orders_list(page, live_server)

    row = page.locator(f'tr.captured-order[data-order="{ORDER_ID}"]')
    expect(row).to_have_count(1)
    expect(row).to_contain_text("Amazon")
    expect(row).to_contain_text("22 Aug 2026")


@pytest.mark.e2e
def test_an_order_with_outstanding_lines_is_marked_as_such(
    page, live_server, image_host
):
    confirm(capture_order(page, live_server, image_host))

    orders_list(page, live_server)

    row = page.locator(f'tr.captured-order[data-order="{ORDER_ID}"]')
    expect(row).to_have_attribute("data-complete", "false")
    expect(row).to_contain_text("outstanding")


@pytest.mark.e2e
def test_the_summary_counts_the_orders_still_arriving(page, live_server, image_host):
    confirm(capture_order(page, live_server, image_host))

    orders_list(page, live_server)

    expect(page.locator("#open-count")).to_have_text("1")


@pytest.mark.e2e
def test_the_order_number_links_to_its_own_screen(page, live_server, image_host):
    confirm(capture_order(page, live_server, image_host))
    orders_list(page, live_server)

    page.locator(f'tr.captured-order[data-order="{ORDER_ID}"] a').first.click()

    expect(page.locator("#order-lines")).to_be_visible()
    expect(page.locator("#outstanding-count")).to_be_visible()


@pytest.mark.e2e
def test_the_list_is_reachable_from_the_navigation(page, live_server):
    """FR-034: the operator must not have to know an order number."""
    page.goto(f"{live_server.url}/products")
    expect(page.locator("#products-nav")).to_be_visible()

    page.click("#products-nav")
    link = page.locator('a[href="/products/orders"]')
    expect(link).to_be_visible()
    link.click()

    expect(page.locator("#orders-table, #no-orders")).to_be_visible()
