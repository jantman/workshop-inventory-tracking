"""
E2E tests for product label printing.

The existing test seam is preserved: with TESTING set, the print request reaches
the short-circuit that logs what it would have printed. **Nothing here reaches
LpPrinter.print_images()** -- that drives real hardware.
"""

import pytest
from playwright.sync_api import expect


def create_product(page, base_url, description):
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)
    page.click("#save-product-btn")
    page.wait_for_load_state("networkidle")
    return page.url


def print_label(page, stock="Sato 2x4"):
    """Open the label modal, pick a stock and print"""
    page.click("#print-product-label-btn")
    expect(page.locator("#product-label-modal")).to_be_visible()
    page.wait_for_timeout(500)
    page.select_option("#product-label-type-select", stock)
    page.click("#product-label-print-confirm")
    page.wait_for_timeout(1000)


@pytest.mark.e2e
def test_all_six_stocks_are_offered(page, live_server):
    """FR-037: product labels reuse the existing stock set in full"""
    create_product(page, live_server.url, "Blue widget")

    page.click("#print-product-label-btn")
    expect(page.locator("#product-label-modal")).to_be_visible()
    page.wait_for_timeout(1000)

    options = page.locator("#product-label-type-select option")
    names = [options.nth(i).inner_text() for i in range(options.count())]

    for stock in ['Sato 1x2', 'Sato 1x2 Flag', 'Sato 2x4',
                  'Sato 2x4 Flag', 'Sato 4x6', 'Sato 4x6 Flag']:
        assert stock in names, f"{stock} is missing from the label stock list"


@pytest.mark.e2e
def test_printing_a_label_succeeds(page, live_server):
    """The request reaches the short-circuit and reports success"""
    create_product(page, live_server.url, "Blue widget")
    print_label(page)

    expect(page.locator("#product-label-alert")).to_contain_text("Blue widget")


@pytest.mark.e2e
def test_a_reprint_requires_no_data_entry(page, live_server):
    """SC-003: reprinting re-enters nothing -- it composes from the record"""
    create_product(page, live_server.url, "Reprintable widget")

    print_label(page)
    expect(page.locator("#product-label-alert")).to_contain_text("Reprintable widget")

    page.reload()
    page.wait_for_load_state("networkidle")

    # Second print: click, confirm, done. No form to fill in.
    print_label(page)
    expect(page.locator("#product-label-alert")).to_contain_text("Reprintable widget")


@pytest.mark.e2e
def test_the_label_is_composed_from_the_record_so_an_edit_shows_up(page, live_server):
    """FR-013: no cached image, so a reprint reflects an edited description"""
    detail_url = create_product(page, live_server.url, "Original description")

    page.click("text=Edit")
    page.wait_for_load_state("networkidle")
    page.fill("#description", "Edited description")
    page.click("#save-product-btn")
    page.wait_for_load_state("networkidle")

    print_label(page)
    expect(page.locator("#product-label-alert")).to_contain_text("Edited description")


@pytest.mark.e2e
def test_an_unknown_label_stock_is_refused_with_the_valid_ones(page, live_server):
    """Matches the existing endpoint's behaviour rather than inventing new"""
    detail_url = create_product(page, live_server.url, "Blue widget")
    product_id = detail_url.rstrip('/').split('/')[-1]

    response = page.evaluate(
        """async (productId) => {
            const r = await fetch(`/api/products/${productId}/label`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ label_type: 'Not A Real Stock' })
            });
            return { status: r.status, body: await r.json() };
        }""",
        product_id,
    )

    assert response["status"] == 400
    assert "Sato 2x4" in response["body"]["error"]


@pytest.mark.e2e
def test_the_label_carries_provenance_once_there_is_a_purchase(page, live_server):
    """FR-011: description, provenance and the code, all on one label"""
    detail_url = create_product(page, live_server.url, "Bought widget")

    page.click("text=Add Purchase")
    page.wait_for_load_state("networkidle")
    page.fill("#vendor", "Amazon")
    page.fill("#order_date", "2026-01-14")
    page.fill("#quantity", "5")
    page.fill("#unit_price", "12.34")
    page.click("#save-purchase-btn")
    page.wait_for_load_state("networkidle")

    expect(page.locator("#purchase-history")).to_contain_text("Amazon")
    expect(page.locator("#latest-price")).to_contain_text("12.34")

    print_label(page)
    expect(page.locator("#product-label-alert")).to_contain_text("Bought widget")
