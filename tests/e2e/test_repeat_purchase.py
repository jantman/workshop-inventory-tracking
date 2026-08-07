"""
E2E tests for repeat purchases.

Story 5: a second purchase of a known product joins one chronological history
rather than creating a duplicate, and the most recent price is visible.
"""

import pytest
from playwright.sync_api import expect


def create_product(page, base_url, description, gtin=None):
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)
    if gtin:
        page.select_option("#identifier_type", "GTIN")
        page.fill("#identifier_value", gtin)
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")
    return page.url


def add_purchase(page, base_url, product_url, vendor, order_date, price, quantity="10"):
    page.goto(product_url)
    page.click("#add-purchase-btn" if page.locator("#add-purchase-btn").count()
              else "text=Add Purchase")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#vendor", vendor)
    page.fill("#order_date", order_date)
    page.fill("#unit_price", price)
    page.fill("#quantity", quantity)
    page.click("#save-purchase-btn")
    page.wait_for_load_state("domcontentloaded")


@pytest.mark.e2e
def test_two_purchases_build_one_chronological_history(page, live_server):
    """SC-005"""
    product_url = create_product(page, live_server.url, "Blue widget, 10mm")

    add_purchase(page, live_server.url, product_url, "Amazon", "2026-01-14", "12.34")
    add_purchase(page, live_server.url, product_url, "eBay", "2026-03-02", "11.00")

    rows = page.locator("#purchase-history tbody tr.purchase-row")
    assert rows.count() == 2
    # Oldest order first.
    expect(rows.nth(0)).to_contain_text("Amazon")
    expect(rows.nth(0)).to_contain_text("2026-01-14")
    expect(rows.nth(1)).to_contain_text("eBay")
    expect(rows.nth(1)).to_contain_text("2026-03-02")


@pytest.mark.e2e
def test_the_most_recent_price_is_visible(page, live_server):
    """FR-006"""
    product_url = create_product(page, live_server.url, "Blue widget, 10mm")

    add_purchase(page, live_server.url, product_url, "Amazon", "2026-01-14", "12.34")
    add_purchase(page, live_server.url, product_url, "eBay", "2026-03-02", "11.00")

    expect(page.locator("#latest-price")).to_contain_text("11.00")


@pytest.mark.e2e
def test_no_duplicate_product_is_created(page, live_server):
    product_url = create_product(page, live_server.url, "Blue widget, 10mm")
    add_purchase(page, live_server.url, product_url, "Amazon", "2026-01-14", "12.34")
    add_purchase(page, live_server.url, product_url, "eBay", "2026-03-02", "11.00")

    page.goto(f"{live_server.url}/products")
    assert page.locator("#product-table tbody tr").count() == 1


@pytest.mark.e2e
def test_a_scan_during_receiving_offers_to_add_a_purchase_to_this_product(page, live_server):
    """FR-019: the same resolution, a different call site"""
    create_product(page, live_server.url, "Blue widget, 10mm", gtin="012345678905")

    page.goto(live_server.url)
    page.click("#global-scan-input")
    page.keyboard.type("012345678905")
    page.keyboard.press("Enter")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#scan-match-banner")).to_be_visible()
    expect(page.locator("#add-purchase-to-this-btn")).to_be_visible()


@pytest.mark.e2e
def test_that_offer_leads_to_a_purchase_on_the_same_product(page, live_server):
    create_product(page, live_server.url, "Blue widget, 10mm", gtin="012345678905")

    page.goto(live_server.url)
    page.click("#global-scan-input")
    page.keyboard.type("012345678905")
    page.keyboard.press("Enter")
    page.wait_for_load_state("domcontentloaded")

    page.click("#add-purchase-to-this-btn")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#vendor", "Amazon")
    page.fill("#order_date", "2026-03-02")
    page.fill("#unit_price", "11.00")
    page.click("#save-purchase-btn")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#purchase-history")).to_contain_text("Amazon")

    page.goto(f"{live_server.url}/products")
    assert page.locator("#product-table tbody tr").count() == 1


@pytest.mark.e2e
def test_a_scan_of_an_outstanding_order_offers_to_receive_it(page, live_server):
    """The thing in your hand is usually the thing you just ordered"""
    product_url = create_product(page, live_server.url, "Blue widget", gtin="012345678905")

    page.goto(product_url)
    page.click("text=Add Purchase")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#vendor", "Amazon")
    page.fill("#order_date", "2026-01-14")
    page.click("#save-purchase-btn")
    page.wait_for_load_state("domcontentloaded")

    page.goto(live_server.url)
    page.click("#global-scan-input")
    page.keyboard.type("012345678905")
    page.keyboard.press("Enter")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#receive-outstanding-btn")).to_be_visible()
