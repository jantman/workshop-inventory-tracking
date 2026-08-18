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


# ---------------------------------------------------------------------------
# The unit price of one item out of a pack (issue #97)
# ---------------------------------------------------------------------------

# paid, pack size, unit price, exact
ROUNDING_TABLE = [
    ("29.97", "3", "9.99", True),
    # $17.99 across three is $5.996666..., which is the ordinary case rather
    # than the awkward one. Rounded to the cent, and said so on the page.
    ("17.99", "3", "6.00", False),
    ("0.01", "3", "0.00", False),
    ("10.00", "4", "2.50", True),
    # The half-up step, exactly on the boundary: 8.9975 -> 9.00.
    ("17.995", "2", "9.00", False),
    # A pack of one is not a division: the amount comes back untouched, not
    # reformatted, which is what keeps a single-unit capture what it was.
    ("1249.50", "1", "1249.50", True),
    ("1249.50", "", "1249.50", True),
    ("9", "2", "4.50", True),
]

# paid, pack size, the field named
REJECTIONS = [
    ("1,249.50", "3", "pack_price"),
    ("$5", "3", "pack_price"),
    ("", "3", "pack_price"),
    ("5.", "3", "pack_price"),
    ("29.97", "0", "pack_size"),
    ("29.97", "-1", "pack_size"),
    ("29.97", "2.5", "pack_size"),
    ("29.97", "three", "pack_size"),
]


def open_capture(page, base_url, url=AMAZON_URL):
    """The capture form, with a listing URL in it and the script loaded"""
    page.goto(f"{base_url}/products/capture")
    page.fill("#url", url)
    return page


@pytest.mark.e2e
def test_the_unit_price_arithmetic_is_exact(page, live_server):
    """FR-006/FR-007: integer division, half up at the cent, and never a float.

    Driven against the function rather than through the form. There is no JS
    test runner in this repository and there is not going to be one for ninety
    lines of arithmetic, so `window.unitPriceFromPack` is exposed the way
    `window.readLabelCount` is and the whole table costs one page load instead
    of sixteen.
    """
    open_capture(page, live_server.url)
    # The state to wait on is the script having run -- `goto` waits for `load`,
    # but this says so rather than relying on it.
    page.wait_for_function("() => typeof window.unitPriceFromPack === 'function'")

    for paid, size, value, exact in ROUNDING_TABLE:
        result = page.evaluate(
            "([p, n]) => window.unitPriceFromPack(p, n)", [paid, size]
        )
        assert result == {"ok": True, "value": value, "exact": exact}, (paid, size)

    for paid, size, field in REJECTIONS:
        result = page.evaluate(
            "([p, n]) => window.unitPriceFromPack(p, n)", [paid, size]
        )
        assert result["ok"] is False, (paid, size)
        assert result["field"] == field, (paid, size)
        assert result["error"], (paid, size)

    # A price that arrived as a number is refused rather than coerced: this is
    # the guard that makes "no float, ever" true instead of merely intended.
    refused = page.evaluate("() => window.unitPriceFromPack(17.99, '3')")
    assert refused["ok"] is False
    assert refused["field"] == "pack_price"


@pytest.mark.e2e
def test_the_unit_price_is_worked_out_from_the_pack(page, live_server):
    """US1 scenarios 1 and 4: the calculator issue #97 was reaching for"""
    open_capture(page, live_server.url)
    page.fill("#listing_title", "Blue Widget 3-Pack")
    page.fill("#pack_price", "29.97")
    page.fill("#pack_size", "3")

    expect(page.locator("#unit_price")).to_have_value("9.99")

    page.click("#capture-btn")
    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    # What was recorded is what the page showed.
    expect(page.locator("#unit_price")).to_have_value("9.99")


@pytest.mark.e2e
def test_the_operator_can_overrule_the_worked_out_price(page, live_server):
    """US1 scenario 2/FR-004: it is a field, not a verdict"""
    open_capture(page, live_server.url)
    page.fill("#listing_title", "Blue Widget 3-Pack")
    page.fill("#pack_price", "29.97")
    page.fill("#pack_size", "3")
    expect(page.locator("#unit_price")).to_have_value("9.99")

    page.fill("#unit_price", "9.95")
    page.click("#capture-btn")

    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    expect(page.locator("#unit_price")).to_have_value("9.95")


@pytest.mark.e2e
def test_it_recomputes_from_the_two_inputs_not_from_what_it_last_wrote(
    page, live_server
):
    """US1 scenario 3/FR-005: the derivation has one source, and it is the inputs.

    The trap this guards is a recompute that folds the *displayed* unit price
    back in -- changing the pack size twice would then give a different answer
    from typing the second value first.
    """
    open_capture(page, live_server.url)
    page.fill("#pack_price", "29.97")
    page.fill("#pack_size", "3")
    expect(page.locator("#unit_price")).to_have_value("9.99")

    page.fill("#unit_price", "1.00")
    page.fill("#pack_size", "6")

    # 29.97 / 6 = 4.995, rounded up. Nothing derived from the 1.00.
    expect(page.locator("#unit_price")).to_have_value("5.00")


@pytest.mark.e2e
def test_an_unusable_pack_size_destroys_nothing(page, live_server):
    """FR-011: the failure mode is a message, never a cleared price field"""
    open_capture(page, live_server.url)
    page.fill("#pack_price", "12.00")
    page.fill("#unit_price", "4.00")

    page.fill("#pack_size", "0")

    error = page.locator("#unit-price-error")
    expect(error).to_be_visible()
    expect(error).to_contain_text("pack size")
    # The price the operator typed is still theirs.
    expect(page.locator("#unit_price")).to_have_value("4.00")


@pytest.mark.e2e
def test_a_price_that_does_not_divide_evenly_says_so(page, live_server):
    """US2 scenarios 1 and 2/FR-008, FR-009: the rounding is not silent.

    The operator who later reconciles three at six pounds against a 17.99
    charge needs to have been told where the penny went at the time, rather
    than suspecting the wrong price was recorded.
    """
    open_capture(page, live_server.url)
    page.fill("#pack_price", "17.99")
    page.fill("#pack_size", "3")

    expect(page.locator("#unit_price")).to_have_value("6.00")
    note = page.locator("#unit-price-inexact")
    expect(note).to_be_visible()
    # All three numbers, so the claim can be checked without doing it again.
    expect(note).to_contain_text("3")
    expect(note).to_contain_text("6.00")
    expect(note).to_contain_text("17.99")

    # And absent when it comes out even.
    page.fill("#pack_price", "29.97")
    expect(page.locator("#unit_price")).to_have_value("9.99")
    expect(note).not_to_be_visible()


@pytest.mark.e2e
def test_the_note_goes_away_when_the_pack_size_divides_evenly(page, live_server):
    """US2 scenario 3: and the amount paid comes back verbatim at a pack of one"""
    open_capture(page, live_server.url)
    page.fill("#pack_price", "17.99")
    page.fill("#pack_size", "3")
    expect(page.locator("#unit-price-inexact")).to_be_visible()

    page.fill("#pack_size", "1")

    expect(page.locator("#unit-price-inexact")).not_to_be_visible()
    expect(page.locator("#unit_price")).to_have_value("17.99")


@pytest.mark.e2e
def test_a_rounded_price_still_explains_itself_on_a_page_nobody_typed_into(
    page, live_server
):
    """FR-008 across a re-render, and FR-005's other half.

    The GET path renders `form_data` from the query string, which is the same
    mechanism that carries the pack fields back through a duplicate question.
    The note has to survive that; writing the unit price must not, because a
    re-render can be carrying one the operator typed by hand.
    """
    page.goto(f"{live_server.url}/products/capture?pack_price=17.99&pack_size=3")

    # Wait for the note first: it is the proof that the load-time recompute
    # ran, and without it the assertion below would pass against a page whose
    # script had simply not executed yet.
    expect(page.locator("#unit-price-inexact")).to_be_visible()
    expect(page.locator("#unit_price")).to_have_value("")


@pytest.mark.e2e
def test_the_pack_fields_survive_a_question(page, live_server):
    """US3/FR-012: a derivation that stops explaining itself is worse than none.

    This passes on the strength of `form_data=request.form`, which the route
    already did. The test is here so that a later edit to the template cannot
    quietly take it away.
    """
    capture(page, live_server.url, listing_title="Blue Widget 3-Pack")

    open_capture(page, live_server.url)
    page.fill("#listing_title", "Blue Widget 3-Pack")
    page.fill("#pack_price", "29.97")
    page.fill("#pack_size", "3")
    expect(page.locator("#unit_price")).to_have_value("9.99")
    page.click("#capture-btn")

    expect(page.locator("#duplicate-warning")).to_be_visible()
    expect(page.locator("#pack_price")).to_have_value("29.97")
    expect(page.locator("#pack_size")).to_have_value("3")
    expect(page.locator("#unit_price")).to_have_value("9.99")


# ---------------------------------------------------------------------------
# Filing at capture: category, location and sub-location (issue #99)
# ---------------------------------------------------------------------------

FILING = {
    "category_path": "electronics/passives/resistors",
    "location": "Shelf A",
    "sub_location": "Bin 3",
}


def open_product_from_receive(page):
    """Follow the receive page's own link back to the product it captured.

    A successful capture lands on the receive screen, so the product id is not
    something the test knows. Clicking the link the page already carries beats
    reconstructing the URL, and the click is a plain navigation rather than a
    fetch -- the heading is the whole wait.
    """
    page.click("text=Back to Product")
    expect(page.locator("#product-description")).to_be_visible()


@pytest.mark.e2e
def test_a_capture_files_the_product(page, live_server):
    """US1/SC-001: filed while the listing was on screen, with no second visit"""
    capture(page, live_server.url, description="Blue widget, 10mm", **FILING)
    open_product_from_receive(page)

    expect(page.locator("#product-category")).to_have_text(
        "electronics/passives/resistors"
    )
    expect(page.locator("#product-location")).to_have_text("Shelf A")
    expect(page.locator("#product-sub-location")).to_have_text("Bin 3")


@pytest.mark.e2e
def test_leaving_them_blank_files_nothing_and_says_nothing(page, live_server):
    """FR-003: uncategorized is an ordinary state, not a deficiency"""
    capture(page, live_server.url, description="Blue widget, 10mm")
    open_product_from_receive(page)

    # Established by the heading wait in the helper, so a negative assertion
    # here is against a page that has rendered rather than one that has not.
    expect(page.locator("#product-category")).to_have_count(0)
    expect(page.locator("#product-location")).to_have_text("Not recorded")
    expect(page.locator("#product-sub-location")).to_have_text("Not recorded")


@pytest.mark.e2e
def test_a_category_typed_here_did_not_have_to_exist_first(page, live_server):
    """FR-006: typing a path is how a path is created -- there is no setup step"""
    capture(page, live_server.url, category_path="Shop/Consumables/Abrasives")
    open_product_from_receive(page)

    expect(page.locator("#product-category")).to_have_text("shop/consumables/abrasives")

    page.goto(f"{live_server.url}/products/categories")
    expect(page.locator("body")).to_contain_text("shop/consumables/abrasives")


@pytest.mark.e2e
def test_attaching_to_an_existing_product_refiles_it(page, live_server):
    """FR-009: the operator is holding the thing, which outranks an older record"""
    live_server.add_test_products([{
        'description': 'Blue widget, already cataloged',
        'location': 'Shelf B',
        'sub_location': 'Bin 1',
        'identifiers': [
            {'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}
        ],
    }])

    capture(page, live_server.url, listing_title="A COMPLETELY DIFFERENT THING",
            location="Shelf A", sub_location="Bin 3")
    expect(page.locator("#identifier-warning")).to_be_visible()

    page.check("#attach-existing")
    page.click("#capture-btn")
    open_product_from_receive(page)

    expect(page.locator("#product-location")).to_have_text("Shelf A")
    expect(page.locator("#product-sub-location")).to_have_text("Bin 3")


@pytest.mark.e2e
def test_attaching_with_the_fields_blank_leaves_the_filing_alone(page, live_server):
    """FR-010: blank is "I am not saying", never "erase it".

    The failure this catches is silent: pass the three keys through
    unconditionally and this capture unfiles a product nobody asked to move.
    """
    live_server.add_test_products([{
        'description': 'Blue widget, already cataloged',
        'category_path': 'misc',
        'location': 'Shelf B',
        'sub_location': 'Bin 1',
        'identifiers': [
            {'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}
        ],
    }])

    capture(page, live_server.url, listing_title="A COMPLETELY DIFFERENT THING")
    expect(page.locator("#identifier-warning")).to_be_visible()

    page.check("#attach-existing")
    page.click("#capture-btn")
    open_product_from_receive(page)

    expect(page.locator("#product-category")).to_have_text("misc")
    expect(page.locator("#product-location")).to_have_text("Shelf B")
    expect(page.locator("#product-sub-location")).to_have_text("Bin 1")


# ---------------------------------------------------------------------------
# The suggestion vocabularies, shared with the product form (issue #99, US2)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_the_category_datalist_offers_what_is_already_in_use(page, live_server):
    """FR-008: the same list the product form gets, from the same endpoint"""
    live_server.add_test_products([
        {'description': 'A resistor', 'category_path': 'electronics/passives'},
    ])

    open_capture(page, live_server.url)

    # The datalist is filled by a fetch after DOMContentLoaded, so the option is
    # the completion signal -- the element existing empty proves nothing.
    expect(
        page.locator("#category-suggestions option[value='electronics/passives']")
    ).to_have_count(1)


@pytest.mark.e2e
def test_a_location_recorded_on_metal_stock_is_offered_here(page, live_server):
    """FR-008: one vocabulary across both halves of the shop.

    Seeded as a metal stock item and on no product, so a suggestion list built
    only from the catalog would come back empty.
    """
    live_server.add_test_data([{
        'ja_id': 'JA000201',
        'item_type': 'Bar',
        'shape': 'Rectangular',
        'material': 'Aluminum',
        'length': '36',
        'location': 'Rack 7',
    }])

    open_capture(page, live_server.url)
    page.fill("#location", "Rack")

    # field-autocomplete.js debounces then fetches; expect() polls, which is
    # what absorbs both. A count() here would read the dropdown before it filled.
    expect(page.locator("#location-suggestions")).to_contain_text("Rack 7")


@pytest.mark.e2e
def test_sub_location_suggestions_are_scoped_to_the_location(page, live_server):
    """FR-008: already inside Shelf A, only Shelf A's bins are worth offering"""
    live_server.add_test_products([
        {'description': 'One', 'location': 'Shelf A', 'sub_location': 'Bin 3'},
        {'description': 'Two', 'location': 'Shelf B', 'sub_location': 'Drawer 9'},
    ])

    open_capture(page, live_server.url)
    page.fill("#location", "Shelf A")
    page.fill("#sub_location", "")

    dropdown = page.locator("#sub_location-suggestions")
    # Establish the region on its positive content first; the assertion that
    # Shelf B's bin is absent would otherwise pass against an unfilled dropdown.
    expect(dropdown).to_contain_text("Bin 3")
    expect(dropdown).not_to_contain_text("Drawer 9")


@pytest.mark.e2e
def test_a_value_in_no_list_is_still_accepted(page, live_server):
    """FR-008: these are suggestions, never a permitted set"""
    live_server.add_test_products([
        {'description': 'A resistor', 'category_path': 'electronics/passives'},
    ])

    capture(page, live_server.url, category_path="fasteners/socket-head-cap-screws",
            location="Somewhere nobody has ever recorded")
    open_product_from_receive(page)

    expect(page.locator("#product-category")).to_have_text(
        "fasteners/socket-head-cap-screws"
    )
    expect(page.locator("#product-location")).to_have_text(
        "Somewhere nobody has ever recorded"
    )


# ---------------------------------------------------------------------------
# The filing survives a question (issue #99, US3)
# ---------------------------------------------------------------------------


def expect_filing_preserved(page):
    """All three fields still holding what the operator typed"""
    expect(page.locator("#category_path")).to_have_value(FILING["category_path"])
    expect(page.locator("#location")).to_have_value(FILING["location"])
    expect(page.locator("#sub_location")).to_have_value(FILING["sub_location"])


@pytest.mark.e2e
def test_the_filing_survives_the_duplicate_question(page, live_server):
    """FR-011: the page comes back with the question, not with empty fields"""
    capture(page, live_server.url, listing_title="Blue Widget 10-Pack")

    capture(page, live_server.url, listing_title="Blue Widget 10-Pack", **FILING)
    expect(page.locator("#duplicate-warning")).to_be_visible()
    expect_filing_preserved(page)

    # Two questions, not one: it is a probable repeat *and* the item number now
    # names the product the first capture created. Answering only the duplicate
    # leaves the second open and the page comes back again.
    page.check("#acknowledged_duplicate_of")
    page.check("#attach-existing")
    page.click("#capture-btn")
    open_product_from_receive(page)

    expect(page.locator("#product-category")).to_have_text(FILING["category_path"])
    expect(page.locator("#product-location")).to_have_text(FILING["location"])


@pytest.mark.e2e
def test_the_filing_survives_the_recycled_identifier_question(page, live_server):
    """FR-011, on the other question -- the two re-render through one path"""
    live_server.add_test_products([{
        'description': 'Blue widget, already cataloged',
        'manufacturer': 'Acme',
        'manufacturer_part_number': 'BW-10',
        'identifiers': [
            {'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}
        ],
    }])

    capture(page, live_server.url, listing_title="A COMPLETELY DIFFERENT THING",
            **FILING)
    expect(page.locator("#identifier-warning")).to_be_visible()
    expect_filing_preserved(page)


@pytest.mark.e2e
def test_the_category_field_will_not_take_an_over_long_path(page, live_server):
    """FR-005 as a browser actually meets it.

    ``maxlength="512"`` refuses the 513th character at the keyboard, and
    canonicalization never lengthens a path, so an over-length path cannot be
    submitted from this page at all -- the service's rejection is the backstop
    behind that, not the thing the operator sees. Asserting the cap here is
    therefore the honest E2E claim; the rejection itself is unreachable through
    a browser and is covered where it is reachable, in
    ``tests/unit/test_capture.py``.

    This is worth a test rather than a comment because the two halves have to
    keep agreeing: widen the column without widening ``maxlength`` and the field
    silently stops accepting paths the catalog would store.
    """
    open_capture(page, live_server.url)
    page.fill("#category_path", "a" * 513)

    expect(page.locator("#category_path")).to_have_value("a" * 512)
