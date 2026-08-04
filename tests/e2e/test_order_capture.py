"""
E2E tests for order-time capture.

Covers the **paste-a-URL** path end to end. The bookmarklet cannot be driven
against a real vendor page from CI -- it depends on that page's form-action
policy -- so it is verified by hand and this covers the path that always works.
"""

import pytest
from playwright.sync_api import expect

AMAZON_URL = "https://www.amazon.com/dp/B0ABCDEFGH/ref=sr_1_3"


def capture(page, base_url, url=AMAZON_URL, **fields):
    """Paste a listing URL into the capture form and submit it"""
    page.goto(f"{base_url}/products/capture")
    page.fill("#url", url)
    for field, value in fields.items():
        page.fill(f"#{field}", value)
    page.click("#capture-btn")
    page.wait_for_load_state("networkidle")


@pytest.mark.e2e
def test_capture_creates_an_unreceived_purchase_with_the_details(page, live_server):
    """SC-002: vendor, item identifier, listing title and date, without retyping"""
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack", unit_price="12.34")

    # Lands on the confirmation page, which is where anything the URL did not
    # yield gets amended.
    expect(page.locator("#receive-vendor")).to_have_text("Amazon")
    expect(page.locator("#receive-vendor-item")).to_have_text("B0ABCDEFGH")
    expect(page.locator("#receive-listing")).to_have_text("Blue Widget 10-Pack")
    expect(page.locator("#unit_price")).to_have_value("12.34")


@pytest.mark.e2e
def test_the_vendor_and_item_id_are_read_from_the_url(page, live_server):
    """No page markup is consulted -- markup is not a contract, a URL path is"""
    capture(page, live_server.url, listing_title="Something")

    expect(page.locator("#receive-vendor")).to_have_text("Amazon")
    expect(page.locator("#receive-vendor-item")).to_have_text("B0ABCDEFGH")


@pytest.mark.e2e
def test_capturing_the_same_listing_twice_creates_nothing_new(page, live_server):
    """People double-click bookmarks"""
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack")
    first_url = page.url

    capture(page, live_server.url, listing_title="Blue Widget 10-Pack")
    assert page.url == first_url

    page.goto(f"{live_server.url}/products")
    rows = page.locator("#product-table tbody tr")
    assert rows.count() == 1


@pytest.mark.e2e
def test_an_outstanding_capture_shows_as_on_order(page, live_server):
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack")

    page.goto(f"{live_server.url}/products")
    page.click("#product-table tbody tr a")
    page.wait_for_load_state("networkidle")

    expect(page.locator(".purchase-outstanding")).to_be_visible()


@pytest.mark.e2e
def test_completing_it_on_arrival(page, live_server):
    """The captured details are already there; only what differed gets amended"""
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack",
            quantity="10", unit_price="12.34")

    # What actually turned up: eight of them, at a different price.
    page.fill("#quantity", "8")
    page.fill("#unit_price", "11.00")
    page.click("#confirm-receive-btn")
    page.wait_for_load_state("networkidle")

    history = page.locator("#purchase-history")
    expect(history).to_contain_text("Amazon")
    expect(history).to_contain_text("8")
    expect(history).to_contain_text("11.00")
    expect(page.locator(".purchase-outstanding")).to_have_count(0)


@pytest.mark.e2e
def test_a_capture_attaches_to_a_product_that_already_owns_the_identifier(page, live_server):
    """FR-021"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", "Blue widget, already catalogued")
    page.select_option("#identifier_type", "VENDOR")
    page.fill("#identifier_value", "B0ABCDEFGH")
    page.fill("#identifier_vendor", "Amazon")
    page.click("#save-product-btn")
    page.wait_for_load_state("networkidle")

    capture(page, live_server.url, listing_title="BLUE WIDGET 10 PACK")

    # Attached to the existing product, and the vendor's shouting did not
    # overwrite the operator's own wording.
    expect(page.locator("#receive-product")).to_have_text("Blue widget, already catalogued")

    page.goto(f"{live_server.url}/products")
    assert page.locator("#product-table tbody tr").count() == 1


@pytest.mark.e2e
def test_the_bookmarklet_says_so_when_it_cannot_work(page, live_server):
    """Over plain http the bookmarklet is dead on arrival, and says so.

    Amazon sends `upgrade-insecure-requests`, which rewrites the bookmarklet's
    destination to https; against a plain-http server that is an SSL error rather
    than a capture. Offering the button with no warning would send the operator
    to debug a failure that is not theirs. See issue #54.
    """
    page.goto(f"{live_server.url}/products/capture")

    expect(page.locator("#bookmarklet-http-warning")).to_be_visible()
    expect(page.locator("#bookmarklet-http-warning")).to_contain_text("https")
    # The paste box is right there and works.
    expect(page.locator("#url")).to_be_visible()


@pytest.mark.e2e
def test_the_bookmarklet_is_offered_and_points_at_this_server(page, live_server):
    """It is a convenience layered on the paste path, not a replacement for it"""
    page.goto(f"{live_server.url}/products/capture")

    href = page.locator("#capture-bookmarklet").get_attribute("href")
    assert href.startswith("javascript:")
    assert "/api/capture" in href
    # Reads the URL and the title, and nothing else.
    assert "location.href" in href
    assert "document.title" in href
    # A form submission, not a fetch -- mixed content would block the latter.
    assert "createElement('form')" in href
    assert "fetch(" not in href
