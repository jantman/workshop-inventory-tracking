"""
E2E tests for product label printing.

The existing test seam is preserved: with TESTING set, the print request reaches
the short-circuit that logs what it would have printed. **Nothing here reaches
LpPrinter.print_images()** -- that drives real hardware.
"""

import pytest
from playwright.sync_api import expect
from tests.e2e.waits import wait_for_select_populated


def create_product(page, base_url, description):
    page.goto(f"{base_url}/products/new")
    page.fill("#description", description)
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")
    return page.url


def print_label(page, stock="Sato 2x4", count=None):
    """Open the label modal, pick a stock and print"""
    page.click("#print-product-label-btn")
    expect(page.locator("#product-label-modal")).to_be_visible()
    # The stock list is fetched from /api/labels/types; the select ships with a
    # single placeholder option, so more than one option is proof it arrived.
    wait_for_select_populated(page, "product-label-type-select")
    page.select_option("#product-label-type-select", stock)
    if count is not None:
        page.fill("#product-label-count", str(count))
        # fill() is synchronous against a plain input, but the value is read at
        # click time -- confirm it landed before clicking, or a slow machine
        # posts the default.
        expect(page.locator("#product-label-count")).to_have_value(str(count))
    page.click("#product-label-print-confirm")
    # print() posts and reports the outcome into #product-label-alert -- on both
    # the success and the failure path -- so the alert existing means the POST
    # resolved.
    expect(page.locator("#product-label-alert")).to_be_visible()


@pytest.mark.e2e
def test_all_six_stocks_are_offered(page, live_server):
    """FR-037: product labels reuse the existing stock set in full"""
    create_product(page, live_server.url, "Blue widget")

    page.click("#print-product-label-btn")
    expect(page.locator("#product-label-modal")).to_be_visible()
    # count() does not wait, so the list has to be established first: without
    # this the loop below reads the lone placeholder option and every stock looks
    # missing.
    wait_for_select_populated(page, "product-label-type-select")

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
    page.wait_for_load_state("domcontentloaded")

    # Second print: click, confirm, done. No form to fill in.
    print_label(page)
    expect(page.locator("#product-label-alert")).to_contain_text("Reprintable widget")


@pytest.mark.e2e
def test_the_label_is_composed_from_the_record_so_an_edit_shows_up(page, live_server):
    """FR-013: no cached image, so a reprint reflects an edited description"""
    detail_url = create_product(page, live_server.url, "Original description")

    page.click("text=Edit")
    page.wait_for_load_state("domcontentloaded")
    page.fill("#description", "Edited description")
    page.click("#save-product-btn")
    page.wait_for_load_state("domcontentloaded")

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
    page.wait_for_load_state("domcontentloaded")
    page.fill("#vendor", "Amazon")
    page.fill("#order_date", "2026-01-14")
    page.fill("#quantity", "5")
    page.fill("#unit_price", "12.34")
    page.click("#save-purchase-btn")
    page.wait_for_load_state("domcontentloaded")

    expect(page.locator("#purchase-history")).to_contain_text("Amazon")
    expect(page.locator("#latest-price")).to_contain_text("12.34")

    print_label(page)
    expect(page.locator("#product-label-alert")).to_contain_text("Bought widget")


@pytest.mark.e2e
def test_several_copies_print_in_one_pass(page, live_server):
    """SC-005: N copies is one trip through the dialog, not N trips"""
    create_product(page, live_server.url, "Bagged widget")

    print_label(page, count=3)

    # The confirmation names the count, which is the only thing on the page that
    # distinguishes three labels from one -- printing itself is short-circuited.
    expect(page.locator("#product-label-alert")).to_contain_text(
        "3 labels printed for Bagged widget"
    )


@pytest.mark.e2e
def test_the_count_defaults_to_one(page, live_server):
    """Touching nothing prints one label, as it always has"""
    create_product(page, live_server.url, "Single widget")

    expect(page.locator("#product-label-count")).to_have_value("1")

    print_label(page)

    expect(page.locator("#product-label-alert")).to_contain_text(
        "Label printed for Single widget"
    )


@pytest.mark.e2e
def test_a_count_out_of_range_is_refused_and_prints_nothing(page, live_server):
    """The spinner bounds the arrows, not what can be typed into the box.

    Refused by the shared reader before the request is made, in the wording
    every print dialog uses. The route validates the same range again -- that
    backstop is covered by the unit tests, which can post past the dialog.
    """
    create_product(page, live_server.url, "Refused widget")

    print_label(page, count=200)

    expect(page.locator("#product-label-alert")).to_contain_text(
        "Label count must be a whole number between 1 and 99"
    )


@pytest.mark.e2e
def test_the_count_does_not_survive_into_the_next_job(page, live_server):
    """A job of three must not silently become the next job's default.

    The modal is one static node reused on every open, so the markup's value="1"
    applies once and never again. Without the reset in open(), reopening shows
    the previous count -- and printing accepts it.
    """
    create_product(page, live_server.url, "Reset widget")

    print_label(page, count=3)
    expect(page.locator("#product-label-alert")).to_contain_text("3 labels printed")

    page.click("#product-label-modal .btn-secondary")
    expect(page.locator("#product-label-modal")).not_to_be_visible()

    page.click("#print-product-label-btn")
    expect(page.locator("#product-label-modal")).to_be_visible()
    expect(page.locator("#product-label-count")).to_have_value("1")
