"""
E2E tests for order-time capture.

Covers the **paste-a-URL** path end to end. The bookmarklet cannot be driven
against a real vendor page from CI -- it depends on that page's form-action
policy and on this app being served over TLS -- so it is verified by hand and
this covers the path that always works.

Capture confirms rather than guesses. A capture with nothing ambiguous about it
still writes on the first submit and lands on the receive screen; one that finds
a probable repeat or an item id already naming a product comes back with the
question and has written nothing.
"""

import pytest
from playwright.sync_api import expect

AMAZON_URL = "https://www.amazon.com/dp/B0ABCDEFGH/ref=sr_1_3"
MCMASTER_URL = "https://www.mcmaster.com/91290A115/"


def capture(page, base_url, url=AMAZON_URL, **fields):
    """Paste a listing URL into the capture form and submit it"""
    page.goto(f"{base_url}/products/capture")
    page.fill("#url", url)
    for field, value in fields.items():
        page.fill(f"#{field}", value)
    page.click("#capture-btn")
    page.wait_for_load_state("domcontentloaded")


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
def test_the_operator_writes_the_description_at_capture(page, live_server):
    """US1/FR-001: the label's wording, authored while the listing is open"""
    capture(
        page, live_server.url,
        listing_title="BLUE WIDGET 10 PACK BEST QUALITY FREE SHIPPING",
        description="Blue widget, 10mm",
    )

    # The receive screen shows the operator's wording in the editable field and
    # the vendor's in the read-only block -- both, so they can be compared.
    expect(page.locator("#description")).to_have_value("Blue widget, 10mm")
    expect(page.locator("#receive-listing")).to_have_text(
        "BLUE WIDGET 10 PACK BEST QUALITY FREE SHIPPING"
    )

    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table tbody tr")).to_have_count(1)
    expect(page.locator("#product-table tbody tr").first).to_contain_text("Blue widget, 10mm")


@pytest.mark.e2e
def test_a_blank_description_still_falls_back_to_the_listing_title(page, live_server):
    """FR-003: the one-click case stays one click"""
    capture(page, live_server.url, listing_title="Raw vendor wording")

    expect(page.locator("#description")).to_have_value("Raw vendor wording")


@pytest.mark.e2e
def test_capturing_the_same_listing_twice_asks_before_filing_a_second(page, live_server):
    """US3: people double-click bookmarks, and they also order two of a thing"""
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack")
    first_url = page.url

    # The second capture comes back with the questions, having written nothing.
    # Two of them, in fact: it is a probable repeat *and* the item number now
    # names the product the first capture created. Both are asked at once.
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack")
    expect(page.locator("#duplicate-warning")).to_be_visible()
    expect(page.locator("#duplicate-existing-link")).to_be_visible()
    expect(page.locator("#identifier-warning")).to_be_visible()

    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table tbody tr")).to_have_count(1)

    # Answering both records it as a second purchase of the same product.
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack")
    page.check("#acknowledged_duplicate_of")
    page.check("#attach-existing")
    page.click("#capture-btn")
    page.wait_for_load_state("domcontentloaded")

    assert page.url != first_url
    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table tbody tr")).to_have_count(1)
    page.click("#product-table tbody tr a")
    expect(page.locator("#purchase-history tbody tr")).to_have_count(2)


@pytest.mark.e2e
def test_a_listing_with_no_item_number_is_recognized_by_its_address(page, live_server):
    """FR-013: most vendors' URLs yield no identifier to be recognized by"""
    capture(page, live_server.url, url=MCMASTER_URL, listing_title="Socket head screw")
    capture(page, live_server.url, url=MCMASTER_URL, listing_title="Socket head screw")

    expect(page.locator("#duplicate-warning")).to_be_visible()

    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table tbody tr")).to_have_count(1)


@pytest.mark.e2e
def test_an_outstanding_capture_shows_as_on_order(page, live_server):
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack")

    page.goto(f"{live_server.url}/products")
    page.click("#product-table tbody tr a")
    page.wait_for_load_state("domcontentloaded")

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
    page.wait_for_load_state("domcontentloaded")

    history = page.locator("#purchase-history")
    expect(history).to_contain_text("Amazon")
    expect(history).to_contain_text("8")
    expect(history).to_contain_text("11.00")
    expect(page.locator(".purchase-outstanding")).to_have_count(0)


@pytest.mark.e2e
def test_the_description_is_correctable_when_the_box_arrives(page, live_server):
    """US2/FR-023: corrected and received in one submission, without leaving"""
    products = live_server.add_test_products([
        {'description': 'Blue widget, guessed at'},
    ])
    product_id = products[0].id

    # A purchase recorded by hand, not captured -- FR-025 covers both. Reached by
    # URL rather than by clicking: the detail page's add-purchase link carries no
    # id, and the two that do (#add-purchase-to-this-btn, #receive-outstanding-btn)
    # only render inside the scan-match banner.
    page.goto(f"{live_server.url}/products/{product_id}/purchases/new")
    page.fill("#vendor", "Amazon")
    page.click("#save-purchase-btn")
    expect(page.locator(".purchase-outstanding")).to_be_visible()

    page.click("#purchase-history a[href*='/receive']")
    expect(page.locator("#description")).to_have_value("Blue widget, guessed at")

    page.fill("#description", "Blue widget, 12mm as it turns out")
    page.click("#confirm-receive-btn")

    # One submission did both: the wording is corrected and the order is in.
    expect(page.locator("#product-description")).to_have_text(
        "Blue widget, 12mm as it turns out"
    )
    expect(page.locator(".purchase-outstanding")).to_have_count(0)


@pytest.mark.e2e
def test_a_recycled_item_number_asks_before_attaching(page, live_server):
    """US4/FR-017: the invisible failure, made visible"""
    live_server.add_test_products([{
        'description': 'Blue widget, already cataloged',
        'manufacturer': 'Acme',
        'manufacturer_part_number': 'BW-10',
        'identifiers': [
            {'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}
        ],
    }])

    capture(page, live_server.url, listing_title="A COMPLETELY DIFFERENT THING")

    expect(page.locator("#identifier-warning")).to_be_visible()
    expect(page.locator("#identifier-warning")).to_contain_text(
        "Blue widget, already cataloged"
    )
    expect(page.locator("#identifier-warning")).to_contain_text("BW-10")

    # Nothing written while the question is open, and neither option preselected.
    expect(page.locator("#attach-existing")).not_to_be_checked()
    expect(page.locator("#attach-new")).not_to_be_checked()
    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table tbody tr")).to_have_count(1)


@pytest.mark.e2e
def test_choosing_a_separate_product_leaves_the_first_alone(page, live_server):
    """FR-020"""
    live_server.add_test_products([{
        'description': 'Blue widget, already cataloged',
        'identifiers': [
            {'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}
        ],
    }])

    capture(page, live_server.url, listing_title="A COMPLETELY DIFFERENT THING",
            description="Green gizmo")
    expect(page.locator("#identifier-warning")).to_be_visible()

    page.check("#attach-new")
    page.click("#capture-btn")
    page.wait_for_load_state("domcontentloaded")

    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table tbody tr")).to_have_count(2)
    expect(page.locator("#product-table")).to_contain_text("Blue widget, already cataloged")
    expect(page.locator("#product-table")).to_contain_text("Green gizmo")


@pytest.mark.e2e
def test_a_corroborated_match_attaches_without_asking(page, live_server):
    """FR-019: both values agreeing, case and padding notwithstanding"""
    live_server.add_test_products([{
        'description': '12V 3A PSU',
        'manufacturer': 'Mean Well',
        'manufacturer_part_number': 'RS-15-12',
        'identifiers': [
            {'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}
        ],
    }])

    capture(page, live_server.url, listing_title="MEAN WELL PSU",
            manufacturer="mean well", manufacturer_part_number=" rs-15-12 ")

    # Straight to the receive screen: no question was asked.
    expect(page.locator("#identifier-warning")).to_have_count(0)
    expect(page.locator("#confirm-receive-btn")).to_be_visible()

    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table tbody tr")).to_have_count(1)


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
    """It is a loader now, and what it loads has to come from *this* server.

    This test used to assert `location.href`, `document.title` and
    `createElement('form')`, because the bookmarklet was the extractor. All three
    are false of a loader, and none of them were deleted: the extraction and the
    form submission moved into capture-agent.js and are asserted there, in
    test_product_page_capture.py. What is left here is what the *bookmarklet*
    still has to get right, which is every part of it that cannot be fixed
    without the operator dragging it again.
    """
    page.goto(f"{live_server.url}/products/capture")
    expect(page.locator("#capture-bookmarklet")).to_be_visible()

    href = page.locator("#capture-bookmarklet").get_attribute("href")
    assert href.startswith("javascript:")
    # Both addresses are baked in at render time and must be this server's.
    assert f"{live_server.url}/static/js/capture-agent.js" in href
    assert f"{live_server.url}/api/capture" in href
    # FR-024: cache-busted, so editing the agent takes effect without a re-drag.
    assert "Date.now()" in href
    # Still not a fetch -- mixed content would block one before CORS or CSP got
    # a say, which is the whole reason the agent submits a form.
    assert "fetch(" not in href
