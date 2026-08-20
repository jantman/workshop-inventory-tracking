"""
E2E tests for capturing a product page.

The bookmarklet is no longer the extractor -- it is a loader, and everything it
loads is ``app/static/js/capture-agent.js``. That agent cannot be driven against
a real Amazon listing from CI, so two pieces of local infrastructure stand in for
the vendor, and both of them are honest about what they are:

**The listing page.** ``fixtures/amazon_listing.html`` is fulfilled through
Playwright's ``page.route`` at a ``/dp/<ASIN>`` address. The agent runs against
it exactly as it would against the real thing -- same loader, same canonical
``/dp/<ASIN>`` fetch, same form submission into a new tab. What this cannot do is
fail when Amazon changes their markup. Nothing in this design can; see
research.md, "The risk that is not mitigated".

**The image host.** A stdlib ``http.server`` thread serving ``fixtures/images/``.
``page.route`` is no help for the images because it is the *application* that
fetches them, not the browser, so their addresses have to name an origin the test
controls and the server can actually reach.

**Why the fixture listing is served from this application's own origin**, rather
than from a convincing ``http://www.amazon.com/dp/...``: Chrome refuses to let
one origin load a subresource from a more-private address space without a
permission the operator grants interactively -- Private Network Access for a
public origin, and Local Network Access even between two loopback ports. Either
way the agent script never loads, and the test would be measuring that policy
instead of this feature. Serving ``/dp/<ASIN>`` on the app's own origin removes
the address-space question entirely: the loader, the canonical fetch and the form
POST are all same-origin.

Two things that costs, both stated rather than hidden. ``vendor`` comes out as
the loopback host instead of "Amazon" -- that is a rule about a URL, with no
bearing on extraction, and test_order_capture.py covers it. And the genuinely
cross-origin half of the transport is not exercised here at all; it cannot be
locally, which is why quickstart.md makes it a manual check against a real
listing over TLS.
"""

import json
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.e2e import specification_rows

FIXTURES = Path(__file__).parent / "fixtures"

ASIN = "B0CKXJLP4B"
# What the operator's tab looks like: the canonical path plus the search-result
# reference Amazon appends. The agent reads /dp/<ASIN> instead, which is FR-002.
TAB_SUFFIX = "/ref=sr_1_3"

# The six the gallery data block names. The thumbnail strip shows three.
GALLERY_IMAGE_COUNT = 6

# Any request whose path names an ASIN is the listing; everything else on that
# origin is an image and is served for real.
LISTING_ROUTE = re.compile(r"/dp/[A-Z0-9]{10}")


class _QuietHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler without a line of stderr per request"""

    def log_message(self, fmt, *args):
        # Named `fmt` rather than the stdlib's `format`, which shadows the
        # builtin. BaseHTTPRequestHandler calls this positionally, so the
        # override still matches.
        pass


@pytest.fixture
def image_host():
    """An origin the *application* can really fetch image bytes from.

    Threaded, and deliberately so. Chromium opens speculative connections and
    leaves them idle; a single-threaded HTTPServer blocks inside one of those
    reading a request that never arrives, and ``shutdown()`` then waits forever
    for a loop that cannot come back round. The suite hangs rather than fails,
    which is the worst failure mode a fixture has.
    """
    handler = partial(_QuietHandler, directory=str(FIXTURES / "images"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://127.0.0.1:{server.server_port}"

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def serve_listing(page, image_host, fixture="amazon_listing.html"):
    """Fulfil /dp/<ASIN> with the fixture, wherever it is asked for."""
    body = (FIXTURES / fixture).read_text().replace("__IMAGE_HOST__", image_host)
    page.route(
        LISTING_ROUTE,
        lambda route: route.fulfill(status=200, content_type="text/html", body=body),
    )


def run_bookmarklet(page, live_server, tab_url):
    """Click the real bookmarklet on whatever page is being served; return the tab.

    The bookmarklet is read off this application's own page rather than
    reconstructed, so the loader is under test too: one pointing at the wrong
    address, or one that stopped cache-busting, fails here.

    It is *clicked* rather than evaluated because a form submission into a new
    tab needs a user activation to escape the popup blocker -- which is exactly
    what the operator's click on a real bookmark provides.
    """
    page.goto(f"{live_server.url}/products/capture")
    expect(page.locator("#capture-bookmarklet")).to_be_visible()
    bookmarklet = page.locator("#capture-bookmarklet").get_attribute("href")

    page.goto(tab_url)
    page.evaluate(
        """(href) => {
            const link = document.createElement('a');
            link.id = 'e2e-run-bookmarklet';
            link.href = href;
            link.textContent = 'Capture to Workshop';
            document.body.appendChild(link);
        }""",
        bookmarklet,
    )

    with page.expect_popup() as popup:
        page.click("#e2e-run-bookmarklet")

    landed = popup.value
    # The landing is a full navigation, so the form's presence is the completion
    # signal and a field read before it lands would read empty (pattern C).
    expect(landed.locator("#capture-form")).to_be_visible()
    return landed


def listing_url(live_server):
    """The tab the operator is looking at, on the origin the agent can load from."""
    return f"{live_server.url}/dp/{ASIN}{TAB_SUFFIX}"


def capture_from_listing(page, live_server, image_host, fixture="amazon_listing.html"):
    """Serve the fixture listing and capture from it."""
    serve_listing(page, image_host, fixture)
    return run_bookmarklet(page, live_server, listing_url(live_server))


def confirm(landed, **fields):
    """Fill anything the operator would type, and submit the capture."""
    for field, value in fields.items():
        landed.fill(f"#{field}", value)
    landed.click("#capture-btn")


def payload_of(landed):
    """The extraction as it sits in the hidden field, before anything is written."""
    return json.loads(landed.locator("input[name='listing']").input_value())


@pytest.mark.e2e
def test_the_agent_fills_in_the_price_and_the_brand(page, live_server, image_host):
    """US1 scenarios 1 and 2: neither was typed, and both are on the page"""
    landed = capture_from_listing(page, live_server, image_host)

    expect(landed.locator("#unit_price")).to_have_value("24.99")
    expect(landed.locator("#manufacturer")).to_have_value("Acme Components")
    # What the address already yielded is still there, unchanged by any of this.
    expect(landed.locator("#vendor_item_id")).to_have_value(ASIN)


@pytest.mark.e2e
def test_a_thousands_separator_and_currency_symbol_do_not_reach_the_form(
    page, live_server, image_host
):
    """"$1,249.50" is a price; it is not a value _validate_price accepts"""
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )

    expect(landed.locator("#unit_price")).to_have_value("1249.50")


@pytest.mark.e2e
def test_the_price_crosses_the_boundary_as_a_string(page, live_server, image_host):
    """Constitution III. The reviewer's whole check is whether it has quotes."""
    landed = capture_from_listing(page, live_server, image_host)

    raw = landed.locator("input[name='listing']").input_value()
    assert '"price": "24.99"' in raw or '"price":"24.99"' in raw
    assert isinstance(payload_of(landed)["price"], str)


@pytest.mark.e2e
def test_confirming_records_the_price_and_the_brand(page, live_server, image_host):
    """US1's independent test: recorded, not merely displayed"""
    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU, barrel plug")

    # The receive screen is the redirect target; its arrival is the write.
    expect(landed.locator("#unit_price")).to_have_value("24.99")

    landed.goto(f"{live_server.url}/products")
    rows = landed.locator("#product-table tbody tr")
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text("12V 3A PSU, barrel plug")


@pytest.mark.e2e
def test_what_the_operator_types_survives_the_extraction(page, live_server, image_host):
    """US1 scenario 3: they were looking at the thing, a selector was not"""
    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU", unit_price="19.95", manufacturer="Mean Well")

    expect(landed.locator("#unit_price")).to_have_value("19.95")


@pytest.mark.e2e
def test_the_canonical_listing_is_read_rather_than_the_open_tab(
    page, live_server, image_host
):
    """US1 scenario 4 / FR-002.

    The tab is at /dp/<ASIN>/ref=sr_1_3; the agent reports the address it
    actually read from, which is the bare canonical one.
    """
    landed = capture_from_listing(page, live_server, image_host)

    payload = payload_of(landed)
    assert payload["source_url"] == f"{live_server.url}/dp/{ASIN}"
    assert payload["vendor_item_id"] == ASIN


@pytest.mark.e2e
def test_a_page_the_agent_cannot_read_captures_exactly_as_it_does_today(
    page, live_server, image_host
):
    """US1 scenario 5 / FR-007: the fallback is the requirement, not decoration"""
    page.route(
        LISTING_ROUTE,
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="<html><head><title>Order Details</title></head>"
                 "<body><p>Nothing here.</p></body></html>",
        ),
    )
    landed = run_bookmarklet(page, live_server, listing_url(live_server))

    # Exactly today's behaviour: the item id off the address, the title off the
    # page, and nothing claimed that was not found.
    expect(landed.locator("#vendor_item_id")).to_have_value(ASIN)
    expect(landed.locator("#listing_title")).to_have_value("Order Details")
    expect(landed.locator("#unit_price")).to_have_value("")
    expect(landed.locator("#manufacturer")).to_have_value("")

    confirm(landed, description="Something from an order page")
    expect(landed.locator("#receive-listing")).to_have_text("Order Details")


@pytest.mark.e2e
def test_the_whole_gallery_comes_across_not_just_the_thumbnails(
    page, live_server, image_host
):
    """FR-003. The fixture's data block names six; its thumbnail strip shows three.

    Reading the strip is the mistake this asserts against, and it is the finding
    that ruled out every approach working from rendered markup.
    """
    landed = capture_from_listing(page, live_server, image_host)

    assert len(payload_of(landed)["images"]) == GALLERY_IMAGE_COUNT
    expect(landed.locator("#summary-images")).to_contain_text(str(GALLERY_IMAGE_COUNT))


@pytest.mark.e2e
def test_the_transform_token_is_stripped_so_the_original_is_fetched(
    page, live_server, image_host
):
    """FR-004: ._AC_SL1500_. is a rendition, not the original file"""
    landed = capture_from_listing(page, live_server, image_host)

    for address in payload_of(landed)["images"]:
        assert "_AC_SL1500_" not in address
        assert "_SX679_" not in address
    assert f"{image_host}/steel_rod_sample.jpg" in payload_of(landed)["images"]


@pytest.mark.e2e
def test_confirming_stores_every_gallery_image_on_the_product(
    page, live_server, image_host
):
    """The application really fetches real bytes over real HTTP here"""
    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    # Establish the grid before counting anything: a count() against a card
    # deck that has not rendered reads zero and passes a weaker assertion.
    cards = landed.locator("#attachment-list .attachment-row")
    expect(cards).to_have_count(GALLERY_IMAGE_COUNT)
    expect(landed.locator("#no-attachments")).to_have_count(0)
    # FR-013: a grid of thumbnails, not a list of filenames.
    expect(cards.first.locator("img")).to_have_attribute(
        "src", re.compile(r"\?size=thumbnail$")
    )


@pytest.mark.e2e
def test_an_unreachable_image_costs_that_image_and_nothing_else(
    page, live_server, image_host
):
    """FR-020: the capture has already succeeded before the first fetch"""
    body = (
        (FIXTURES / "amazon_listing.html")
        .read_text()
        .replace("__IMAGE_HOST__", image_host)
        .replace("steel_rod_sample._AC_SL1500_", "not_a_file_at_all._AC_SL1500_")
    )
    page.route(
        LISTING_ROUTE,
        lambda route: route.fulfill(status=200, content_type="text/html", body=body),
    )
    landed = run_bookmarklet(page, live_server, listing_url(live_server))
    confirm(landed, description="12V 3A PSU")

    # The purchase exists, and the flash names what did not land. Its own
    # locator rather than ".alert": the success flash is there too, and matching
    # "an alert somewhere on the page" would pass on the wrong one.
    expect(
        landed.locator(".alert").filter(has_text="could not be retrieved")
    ).to_be_visible()

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")
    expect(landed.locator("#attachment-list .attachment-row")).to_have_count(
        GALLERY_IMAGE_COUNT - 1
    )


@pytest.mark.e2e
def test_the_same_image_named_twice_is_stored_once(page, live_server, image_host):
    """FR-018, the within-one-capture half, judged by content"""
    body = (
        (FIXTURES / "amazon_listing.html")
        .read_text()
        .replace("__IMAGE_HOST__", image_host)
        # A second, genuinely different address naming the same bytes -- which
        # is what a vendor serving one source file under several renditions
        # looks like. The query string is what makes it a different *address*
        # after the transform token comes off; the file server ignores it, so
        # the bytes that come back are identical and only the content hash can
        # tell. Two addresses that merely differed by token would be collapsed
        # by the agent before the server ever saw them.
        .replace("brass_rod_sample._AC_SL1500_.jpg", "steel_rod_sample._AC_SL1500_.jpg?v=2")
    )
    page.route(
        LISTING_ROUTE,
        lambda route: route.fulfill(status=200, content_type="text/html", body=body),
    )
    landed = run_bookmarklet(page, live_server, listing_url(live_server))

    # Two distinct addresses go across; only one image is stored.
    assert len(payload_of(landed)["images"]) == GALLERY_IMAGE_COUNT
    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")
    expect(landed.locator("#attachment-list .attachment-row")).to_have_count(
        GALLERY_IMAGE_COUNT - 1
    )


@pytest.mark.e2e
def test_product_information_becomes_filterable_specifications(
    page, live_server, image_host
):
    """US3 / FR-008, FR-009: rows off the listing, merged across four containers"""
    landed = capture_from_listing(page, live_server, image_host)

    # FR-017: the count is on the page before anything is written.
    expect(landed.locator("#summary-specifications")).to_contain_text("row")
    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    names = landed.locator("#product-specifications .specification-name")
    expect(names).to_contain_text(["Brand", "Material", "Connector Type"])
    # Gathered from every container, not just the first one that matched.
    expect(landed.locator("#product-specifications")).to_contain_text("300 Millimeters")
    expect(landed.locator("#product-specifications")).to_contain_text("36 Watts")
    # FR-008: bookkeeping rows are stored like everything else.
    expect(landed.locator("#product-specifications")).to_contain_text("Best Sellers Rank")
    # FR-009: "Material" and "  material " are one name, first occurrence winning.
    expect(names.filter(has_text=re.compile(r"^Material$", re.I))).to_have_count(1)
    expect(landed.locator("#product-specifications")).to_contain_text("6061 Aluminium")
    expect(landed.locator("#product-specifications")).not_to_contain_text("Steel")


@pytest.mark.e2e
def test_a_captured_specification_filter_finds_the_product(page, live_server, image_host):
    """The point of FR-008: filterable, rather than free text in a note"""
    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.fill("#filter-spec-name", "Voltage")
    landed.fill("#filter-spec-value", "12 Volts")
    landed.click("#apply-filters-btn")

    rows = landed.locator("#product-table tbody tr")
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text("12V 3A PSU")


@pytest.mark.e2e
def test_a_hand_edited_value_survives_a_re_capture(page, live_server, image_host):
    """US3's independent test, and FR-010 and FR-011 together"""
    landed = capture_from_listing(page, live_server, image_host)
    # The part number is cleared so this capture leaves the product without one.
    # 019 fills that field from the listing, and a product carrying both the
    # manufacturer and the part number *corroborates* a later capture of the
    # same listing -- which suppresses the recycled-identifier question this
    # test needs in order to reach its subject. That suppression is the intended
    # payoff and is covered by
    # test_a_repeat_buy_no_longer_has_to_answer_the_identifier_question.
    confirm(landed, description="12V 3A PSU", manufacturer_part_number="")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")
    expect(landed.locator("#product-specifications")).to_be_visible()
    product_url = landed.url

    # Edit one row by hand, the way the operator would after measuring it.
    landed.goto(f"{product_url}/edit")
    editor = landed.locator(specification_rows.ROWS)
    # Establish the editor before touching a field: the rows are server-rendered
    # but a fill() against a form that has not landed goes nowhere.
    expect(editor).not_to_have_count(0)
    editor.first.locator(specification_rows.VALUE_INPUT).fill("What I actually measured")
    landed.click("#save-product-btn")
    expect(landed.locator("#product-specifications")).to_contain_text(
        "What I actually measured"
    )

    before = landed.locator("#product-specifications .specification-name").count()

    # Capture the same listing again. The questions are raised *in response to*
    # the submit, not on the landing page -- nothing is written until they are
    # answered, which is the whole shape of feature 006's decision flow.
    again = capture_from_listing(page, live_server, image_host)
    again.click("#capture-btn")
    expect(again.locator("#duplicate-warning")).to_be_visible()
    expect(again.locator("#identifier-warning")).to_be_visible()
    again.check("#acknowledged_duplicate_of")
    again.check("#attach-existing")
    again.click("#capture-btn")

    again.goto(product_url)
    expect(again.locator("#product-specifications")).to_contain_text(
        "What I actually measured"
    )
    # Nothing removed, and nothing added twice.
    expect(again.locator("#product-specifications .specification-name")).to_have_count(
        before
    )


def serve_aplus_variant(page, image_host, transform):
    """Serve the A+ fixture with ``transform`` applied to its markup.

    021's cases are all "the same listing, one structural thing different", and
    the thing that differs is markup rather than data -- so it is edited here
    rather than carried as four near-identical fixture files that would drift
    apart the first time one of them was updated.
    """
    body = transform(
        (FIXTURES / "amazon_listing_aplus.html")
        .read_text()
        .replace("__IMAGE_HOST__", image_host)
    )
    page.route(
        LISTING_ROUTE,
        lambda route: route.fulfill(status=200, content_type="text/html", body=body),
    )


def without_brand_story(body):
    """The same listing from a vendor who never published a brand story."""
    return re.sub(
        r"<!--BRAND-STORY-START-->.*?<!--BRAND-STORY-END-->", "", body, flags=re.S
    )


@pytest.mark.e2e
def test_the_brand_story_is_not_read_as_the_product_description(
    page, live_server, image_host
):
    """021 FR-011 / C-16, the half of #94 the issue did not report.

    The captured description came from the carousel, so ``B0FX4PDW6M`` landed in
    the catalog describing the *vendor* -- "a global leader in advanced display
    solutions" -- instead of the product. Both halves come from one wrong block,
    which is why an image-only fix would have left this in place.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )

    description = payload_of(landed)["description_text"]
    assert "Extruded 6063-T5 aluminium" in description
    assert "From the brand" not in description
    assert "Sheffield" not in description


@pytest.mark.e2e
def test_a_listing_without_a_brand_story_captures_exactly_as_before(
    page, live_server, image_host
):
    """021 C-2: an absent container behaves like the empty one two of three
    probed listings carry. The exclusion must not need the container to exist.
    """
    serve_aplus_variant(page, image_host, without_brand_story)
    landed = run_bookmarklet(page, live_server, listing_url(live_server))

    payload = payload_of(landed)
    assert payload["images"] == [
        f"{image_host}/aluminum_tube_sample.jpg",
        f"{image_host}/spec_sheet_preview.jpg",
        f"{image_host}/aluminum_plate_sample.jpg",
        f"{image_host}/steel_plate_sample.jpg",
        f"{image_host}/brass_rod_sample.jpg",
    ]
    assert "Extruded 6063-T5 aluminium" in payload["description_text"]


@pytest.mark.e2e
def test_images_are_gathered_from_every_region_not_only_the_first(
    page, live_server, image_host
):
    """021 FR-003 / FR-009 / C-6, in one case, because they share a cause.

    Renaming the carousel's container is what happens when Amazon moves on. The
    block stops being recognised as a cross-sell and becomes what it structurally
    is: a second, legitimate description region carrying a duplicate ``id=aplus``
    that sorts *first*.

    Two things must follow, and only the second is obvious. The capture must
    degrade to collecting the carousel again -- unwanted images the operator
    deletes, never a refused capture and never a dropped content image (FR-009).
    And every image from the *real* block must still be there, which is the
    assertion that proves ``descriptionBlocks()`` reads past the first match:
    the nested shape in the other tests cannot prove it, because there both
    selectors resolve to the same element.
    """
    serve_aplus_variant(
        page,
        image_host,
        lambda body: body.replace(
            'id="aplusBrandStory_feature_div"', 'id="aplusStoryRenamed_feature_div"'
        ),
    )
    landed = run_bookmarklet(page, live_server, listing_url(live_server))

    images = payload_of(landed)["images"]
    # Not one content image lost, though the first block matched is now the
    # renamed one.
    for content in (
        "spec_sheet_preview.jpg",
        "aluminum_plate_sample.jpg",
        "steel_plate_sample.jpg",
        "brass_rod_sample.jpg",
    ):
        assert f"{image_host}/{content}" in images
    # And the documented degradation, asserted rather than hoped for: the
    # carousel comes back, which is the cost of a renamed container and is
    # strictly better than losing the description.
    assert f"{image_host}/vendor_other_extrusion.jpg" in images


@pytest.mark.e2e
def test_the_rich_description_is_kept_and_its_furniture_is_not(
    page, live_server, image_host
):
    """US4 / FR-005, FR-006, FR-019, against the A+ form of the description.

    The real block holds eight images and exactly four are content. The other
    four are a 1x1 spacer, a 970x20 rule, a 16x16 bullet and a 150px mark -- the
    categories that make a captured gallery useless to look through if they are
    stored. Gallery images are exempt from the filter and are not in this block.

    021 added three more ways to get this wrong, and the exact-list assertion
    below is what rules out all of them at once: the brand-story carousel's three
    cross-sells (large enough to clear 300px, and the wrong product), the
    deferred-loading placeholder, and the second copy of the deferred image that
    its ``<noscript>`` twin names.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )

    payload = payload_of(landed)
    assert payload["images"] == [
        f"{image_host}/aluminum_tube_sample.jpg",   # the gallery, exempt
        # 021 C-4/C-13/C-14: named by `data-src` behind a grey-pixel `src`, and
        # named a second time by the `<noscript>` twin. One entry, at the real
        # address, with the transform token off.
        f"{image_host}/spec_sheet_preview.jpg",
        # 021 C-13: a double-underscore token, the shape Amazon actually serves.
        # `knownEdges()` establishes nothing from it, so FR-019 keeps the image.
        f"{image_host}/aluminum_plate_sample.jpg",
        f"{image_host}/steel_plate_sample.jpg",     # 970 on its longest edge
        f"{image_host}/brass_rod_sample.jpg",       # 800x600
    ]
    # 021 FR-004 and C-4, stated so a failure names the defect rather than an
    # index. The list above already forbids these; this says why.
    assert not [a for a in payload["images"] if "vendor_other" in a]
    assert not [a for a in payload["images"] if "grey-pixel" in a]
    expect(landed.locator("#summary-description")).to_contain_text("kept in full")

    # FR-014 / SC-006. Issue #91 changed how text is read, and every one of these
    # goes through the same helper -- so "the description got cleaner" has to be
    # accompanied by "and nothing else moved". These are the pre-#91 values.
    assert payload["listing_title"] == "Acme Aluminium Extrusion 20x20 T-Slot"
    assert payload["brand"] == "Acme Components"
    assert payload["price"] == "1249.50"
    assert [row["name"] for row in payload["specifications"]] == [
        # 020: the bullets lead, and the detail table's own "about this item"
        # row is folded away behind them rather than appearing twice.
        "About this item",
        "Material", "Item Length", "Customer Reviews", "Finish", "Country of Origin",
    ]

    confirm(landed, description="20x20 T-slot extrusion")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    expect(landed.locator("#attachment-list .attachment-row")).to_have_count(5)
    specifications = landed.locator("#product-specifications")
    expect(specifications).to_contain_text("Description")
    expect(specifications).to_contain_text("Extruded 6063-T5 aluminium")
    # The operator's label wording is untouched by a description many times its
    # length -- FR-006's second half.
    expect(landed.locator("h1, h2")).to_contain_text("20x20 T-slot extrusion")


@pytest.mark.e2e
def test_the_plain_description_form_is_kept_too(page, live_server, image_host):
    """FR-005: whichever of the two forms the listing uses, and never both"""
    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    expect(landed.locator("#product-specifications")).to_contain_text(
        "regulated 12 volts at up to 3 amps"
    )


# ---------------------------------------------------------------
# Issue #91: the description is the listing's words, not its markup
# ---------------------------------------------------------------

# What amazon_listing_aplus.html's block yields once the stylesheet, the script
# and the <noscript> are out and the block boundaries are in.
#
# Asserted **whole** rather than by substring, deliberately. The shape is the
# requirement here: a substring check passes just as happily against paragraphs
# that arrived in the wrong order, against a stray blank line, and against a
# <br> that became a paragraph break. One equality catches all three.
APLUS_DESCRIPTION = (
    "Built for the workshop\n"
    "\n"
    "Extruded 6063-T5 aluminium with a 6mm T-slot on all four faces, cut square "
    "to 300mm. Anodised clear; takes M5 T-nuts without tapping.\n"
    "\n"
    "Cut square to length.\n"          # the <br>: one newline, not a paragraph
    "Deburred both ends.\n"            # indented across three source lines
    "\n"
    "Packed in a protective sleeve.\n"  # nested three deep: still one blank line
    "\n"
    "Ships from a UK warehouse.\n"      # the whitespace-only div left no gap
    "\n"
    "6mm slot, four faces\n"
    "\n"
    "Clear anodised finish\n"
    "\n"
    "Sold singly\n"                     # a <br> inside a list item
    "not in packs"
)

# The plain form, which has no stylesheet to lose. The only difference from what
# capture produced before #91 is the break after the heading, which is FR-006
# working -- see test_the_plain_description_loses_no_prose.
PLAIN_DESCRIPTION = (
    "Product Description\n"
    "\n"
    "This power supply provides a regulated 12 volts at up to 3 amps through a "
    "5.5x2.1mm centre-positive barrel plug. Short-circuit and over-current "
    "protected, with a 1.5 metre lead."
)

# Byte-for-byte what capture stored for the plain fixture before #91.
PLAIN_DESCRIPTION_BEFORE_91 = (
    "Product Description This power supply provides a regulated 12 volts at up "
    "to 3 amps through a 5.5x2.1mm centre-positive barrel plug. Short-circuit "
    "and over-current protected, with a 1.5 metre lead."
)


@pytest.mark.e2e
def test_the_description_carries_no_stylesheet_or_script(
    page, live_server, image_host
):
    """US1 / FR-001. The defect that made a captured description 21,415 chars.

    ``textContent`` includes the text of any <style> and <script> descendant,
    and an A+ block routinely carries both. So a stylesheet and a function body
    were stored and displayed as though they were the manufacturer's writing.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )

    description = payload_of(landed)["description_text"]

    # The stylesheet.
    assert ".aplus-module" not in description
    assert "font-size" not in description
    assert "border-top" not in description
    # The script.
    assert "aplusModuleReady" not in description
    assert "function aplusInit" not in description
    # The <noscript> fallback, which is markup's answer to not having script.
    assert "Enable JavaScript" not in description

    # Positively, so this cannot be satisfied by capturing nothing at all.
    assert "Extruded 6063-T5 aluminium" in description


@pytest.mark.e2e
def test_a_block_of_only_markup_is_not_a_description(page, live_server, image_host):
    """US1 / FR-004: an empty block is skipped, not stored.

    The empty block in this fixture is ``#productDescription``, which is the one
    the container list checks *first*. That ordering is the whole point: the
    only way the A+ copy can arrive is if the emptiness test rejected the block
    ahead of it.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_markup_only.html"
    )

    description = payload_of(landed)["description_text"]

    assert description == "Knurled brass standoff, M3 thread, 10mm between faces."
    assert "renderDescription" not in description
    assert "line-height" not in description


@pytest.mark.e2e
def test_the_plain_description_loses_no_prose(page, live_server, image_host):
    """US1 / FR-010, SC-003. The half of this feature that is easy to break.

    Making the A+ descriptions shorter is worthless if it also makes the plain
    ones shorter -- that trades one data-loss defect for another, and FR-006 of
    the capture feature says nothing is truncated. Collapsing the newlines this
    feature introduces must give back exactly the pre-#91 value.
    """
    landed = capture_from_listing(page, live_server, image_host)

    description = payload_of(landed)["description_text"]

    assert description == PLAIN_DESCRIPTION
    assert re.sub(r"\s+", " ", description) == PLAIN_DESCRIPTION_BEFORE_91


@pytest.mark.e2e
def test_reading_the_listing_does_not_change_it(page, live_server, image_host):
    """US1 / FR-003: the extraction removes nodes from a clone, never the page.

    ``canonicalDocument()`` falls back to the operator's live ``document``
    whenever the canonical fetch fails, so a removal in place would edit the
    page they are looking at -- and the second capture would see a page with no
    stylesheet, no script and possibly no description at all. Two captures from
    the one tab agreeing is what says the first one left no mark.
    """
    serve_listing(page, image_host, "amazon_listing_aplus.html")

    first = payload_of(run_bookmarklet(page, live_server, listing_url(live_server)))
    second = payload_of(run_bookmarklet(page, live_server, listing_url(live_server)))

    assert first == second


@pytest.mark.e2e
def test_the_description_keeps_the_shape_the_listing_gave_it(
    page, live_server, image_host
):
    """US2 / FR-005 to FR-008, as one string.

    Every case at once: an explicit break becomes one newline, a paragraph
    becomes a paragraph, three levels of nesting still yield one blank line, a
    division holding only spaces yields none, and a paragraph indented across
    three source lines stays on one line -- because a newline in the markup is
    not a newline the reader ever saw.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )

    description = payload_of(landed)["description_text"]

    assert description == APLUS_DESCRIPTION
    # The guarantees, restated as properties, so a future fixture edit that
    # changes the expected string still cannot quietly break them.
    assert description == description.strip()
    assert "\n\n\n" not in description
    assert not any(line != line.strip() for line in description.split("\n"))


@pytest.mark.e2e
def test_a_captured_description_is_displayed_with_its_breaks(
    page, live_server, image_host
):
    """US2 / FR-011: storing newlines and flattening them at render solves nothing"""
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )
    confirm(landed, description="20x20 T-slot extrusion")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    # Establish the region before reading it: inner_text() does not wait, and
    # against a table that has not rendered it reads empty -- which would pass
    # the "no run-on paragraph" half of this by accident.
    specifications = landed.locator("#product-specifications")
    expect(specifications).to_contain_text("Description")

    values = landed.locator("#product-specifications .specification-value")
    shown = [values.nth(i).inner_text() for i in range(values.count())]
    description = next(v for v in shown if "Extruded 6063-T5 aluminium" in v)

    assert "Built for the workshop\n" in description
    assert "Cut square to length.\nDeburred both ends." in description


@pytest.mark.e2e
def test_an_unrelated_edit_does_not_reflow_a_captured_description(
    page, live_server, image_host
):
    """US2 / FR-012: the round trip an <input> would silently destroy.

    The HTML value sanitization algorithm strips CR and LF, so a multi-line
    value in an ``<input>`` posts back as one run-on line. The form renders a
    textarea instead whenever the stored value has a newline in it; this is the
    test that says so for a value that arrived from a *capture* rather than from
    the migration that first needed it.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )
    confirm(landed, description="20x20 T-slot extrusion")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")
    expect(landed.locator("#product-specifications")).to_contain_text("Description")
    product_url = landed.url

    landed.goto(f"{product_url}/edit")
    expect(landed.locator(specification_rows.ROWS)).not_to_have_count(0)
    landed.fill("#description", "Renamed, specifications untouched")
    landed.click("#save-product-btn")

    expect(landed.locator("#product-description")).to_have_text(
        "Renamed, specifications untouched"
    )
    # And the region being read, established in its own right rather than
    # inferred from the description above having rendered.
    expect(landed.locator("#product-specifications")).to_contain_text("Description")

    values = landed.locator("#product-specifications .specification-value")
    shown = [values.nth(i).inner_text() for i in range(values.count())]
    description = next(v for v in shown if "Extruded 6063-T5 aluminium" in v)

    assert "Cut square to length.\nDeburred both ends." in description


@pytest.mark.e2e
def test_a_specification_value_carries_no_stylesheet_or_script(
    page, live_server, image_host
):
    """US3 / FR-002: the same helper read the table cells, so the same junk landed.

    On B09GM8FB3X it was the ``Customer Reviews`` row: a rating widget with its
    own inline styling and script.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )

    rows = {row["name"]: row["value"] for row in payload_of(landed)["specifications"]}

    assert rows["Customer Reviews"] == "4.6 out of 5 stars"


@pytest.mark.e2e
def test_a_specification_value_keeps_its_lines_and_its_name_does_not(
    page, live_server, image_host
):
    """US3 / FR-009: values may span lines, names never may.

    A name carrying a newline would be two spellings of one name to both folds
    that key on it -- the agent's own merge across containers, and
    ``merge_specifications`` against the product's existing rows.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )

    entries = payload_of(landed)["specifications"]
    rows = {row["name"]: row["value"] for row in entries}

    assert rows["Finish"] == "Clear anodised, 10 micron.\n\nMatte, non-conductive."
    # The <th> holding "Country of<br>Origin".
    assert rows["Country of Origin"] == "United Kingdom"
    assert not any("\n" in row["name"] for row in entries)


@pytest.mark.e2e
def test_detail_bullets_still_split_into_name_and_value(
    page, live_server, image_host
):
    """US3: the rewrite that removed the slice arithmetic was equivalent.

    The value used to be ``whole.slice(textOf(bold).length)``, which assumed the
    name's text was a character-for-character prefix of the item's. It is now
    the item with the bold node removed. These three rows are the ones that
    would have moved if the two were not the same thing.
    """
    landed = capture_from_listing(page, live_server, image_host)

    rows = {row["name"]: row["value"] for row in payload_of(landed)["specifications"]}

    assert rows["Date First Available"] == "March 14, 2023"
    assert rows["Best Sellers Rank"] == "#4,812 in Tools & Home Improvement"
    assert rows["Customer Reviews"] == "4.5 out of 5 stars"


@pytest.mark.e2e
def test_a_repeat_buy_merges_and_stores_no_second_copy(page, live_server, image_host):
    """US5's independent test, and the case the capture is most often used in.

    Capturing the same listing twice on the same day raises both questions;
    answering them must write the second purchase, merge the rows it already has
    without duplicating them, and store **no second copy of any image**.
    """
    landed = capture_from_listing(page, live_server, image_host)
    # The part number is cleared so this capture leaves the product without one.
    # 019 fills that field from the listing, and a product carrying both the
    # manufacturer and the part number *corroborates* a later capture of the
    # same listing -- which suppresses the recycled-identifier question this
    # test needs in order to reach its subject. That suppression is the intended
    # payoff and is covered by
    # test_a_repeat_buy_no_longer_has_to_answer_the_identifier_question.
    confirm(landed, description="12V 3A PSU", manufacturer_part_number="")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")
    expect(landed.locator("#product-specifications")).to_be_visible()
    product_url = landed.url
    rows_before = landed.locator("#product-specifications .specification-name").count()

    again = capture_from_listing(page, live_server, image_host)
    again.click("#capture-btn")
    expect(again.locator("#duplicate-warning")).to_be_visible()
    expect(again.locator("#identifier-warning")).to_be_visible()
    # The payload has to still be here, or answering costs the operator the
    # gallery -- which is the whole of FR-016.
    assert len(payload_of(again)["images"]) == GALLERY_IMAGE_COUNT

    again.check("#acknowledged_duplicate_of")
    again.check("#attach-existing")
    again.click("#capture-btn")
    expect(again.locator(".alert").filter(has_text="already stored")).to_be_visible()

    again.goto(product_url)
    expect(again.locator("#product-specifications")).to_be_visible()
    # One product, two purchases, and one copy of each image.
    expect(again.locator("#product-specifications .specification-name")).to_have_count(
        rows_before
    )
    expect(again.locator("#attachment-list .attachment-row")).to_have_count(
        GALLERY_IMAGE_COUNT
    )
    again.goto(f"{live_server.url}/products")
    expect(again.locator("#product-table tbody tr")).to_have_count(1)
    expect(again.locator("#no-products")).to_have_count(0)


@pytest.mark.e2e
def test_an_abandoned_capture_leaves_no_trace_of_any_kind(page, live_server, image_host):
    """FR-014, FR-015: an unconfirmed capture is a form, and a closed tab.

    The whole payload is sitting in a hidden field -- fourteen image addresses,
    two dozen rows and a description -- and none of it has been written. That
    property is what makes FR-014 and FR-015 cost nothing to satisfy, and this is
    the test that would notice if a future change started writing early.
    """
    landed = capture_from_listing(page, live_server, image_host)
    assert len(payload_of(landed)["images"]) == GALLERY_IMAGE_COUNT
    landed.close()

    # Establish the list before asserting the absence: an empty-state assertion
    # against a page that has not rendered passes for the wrong reason. And the
    # assertion is on the empty state itself rather than on a row count, because
    # the empty state *is* a row -- counting rows would read 1 either way.
    page.goto(f"{live_server.url}/products")
    expect(page.locator("#product-table")).to_be_visible()
    expect(page.locator("#no-products")).to_be_visible()


# ---------------------------------------------------------------------------
# 016: the captured UPC row becomes a scannable identifier
# ---------------------------------------------------------------------------

FIXTURE_UPC = "012345678905"          # the row in the fixture's tech-spec table
FIXTURE_GTIN_KEY = "00012345678905"   # what the catalog stores it as
CORRUPTED_UPC = "012345678906"        # one digit out, so the check digit fails


def serve_listing_with_upc(page, image_host, upc):
    """The fixture listing with its UPC row rewritten."""
    body = (
        (FIXTURES / "amazon_listing.html")
        .read_text()
        .replace("__IMAGE_HOST__", image_host)
        .replace(FIXTURE_UPC, upc)
    )
    page.route(
        LISTING_ROUTE,
        lambda route: route.fulfill(status=200, content_type="text/html", body=body),
    )


def scan(page, text):
    """Type a scan into the global scan input and terminate it like a wedge does"""
    page.click("#global-scan-input")
    page.keyboard.type(text)
    page.keyboard.press("Enter")


@pytest.mark.e2e
def test_a_captured_upc_makes_the_product_scannable(page, live_server, image_host):
    """016 US1, end to end: the listing hands us the barcode, so the box scans"""
    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU")

    # Its own locator rather than ".alert": the success flash and the image tally
    # are on the page too, and "an alert somewhere" would pass on the wrong one.
    expect(
        landed.locator(".alert").filter(has_text=FIXTURE_GTIN_KEY)
    ).to_be_visible()

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    identifiers = landed.locator("#identifier-list")
    expect(identifiers).to_contain_text("GTIN")
    expect(identifiers).to_contain_text(FIXTURE_GTIN_KEY)
    # FR-005: promotion adds, it never moves the row out of the specifications.
    expect(landed.locator("#product-specifications")).to_contain_text(FIXTURE_UPC)

    # And the point of all of it: the barcode off the box finds the product.
    landed.goto(live_server.url)
    scan(landed, FIXTURE_UPC)

    expect(landed.locator("#product-description")).to_have_text("12V 3A PSU")


@pytest.mark.e2e
def test_a_barcode_that_fails_its_check_digit_is_not_recorded(
    page, live_server, image_host
):
    """016 US2: nobody typed it, so nobody would see a prompt -- refuse it"""
    serve_listing_with_upc(page, image_host, CORRUPTED_UPC)
    landed = run_bookmarklet(page, live_server, listing_url(live_server))
    confirm(landed, description="12V 3A PSU")

    expect(
        landed.locator(".alert").filter(has_text="not a valid barcode")
    ).to_be_visible()

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    # Establish the card with a positive assertion first -- the capture always
    # leaves a VENDOR identifier, so an empty list would mean the page has not
    # rendered rather than that nothing was promoted.
    identifiers = landed.locator("#identifier-list")
    expect(identifiers).to_contain_text("VENDOR")
    expect(identifiers).not_to_contain_text("GTIN")
    # The value is kept, just not as an identifier.
    expect(landed.locator("#product-specifications")).to_contain_text(CORRUPTED_UPC)


@pytest.mark.e2e
def test_a_barcode_another_product_holds_is_left_alone(page, live_server, image_host):
    """016 US3: a collision does not guess, and says so"""
    page.goto(f"{live_server.url}/products/new")
    page.fill("#description", "The product that got there first")
    page.select_option("#identifier_type", "GTIN")
    page.fill("#identifier_value", FIXTURE_UPC)
    page.click("#save-product-btn")
    expect(page.locator("#identifier-list")).to_contain_text(FIXTURE_GTIN_KEY)

    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU")

    expect(
        landed.locator(".alert").filter(has_text="already holds it")
    ).to_be_visible()
    expect(
        landed.locator(".alert").filter(has_text="The product that got there first")
    ).to_be_visible()

    landed.goto(f"{live_server.url}/products")
    rows = landed.locator("#product-table tbody tr")
    expect(rows).to_have_count(2)
    rows.filter(has_text="12V 3A PSU").locator("td a").first.click()

    identifiers = landed.locator("#identifier-list")
    expect(identifiers).to_contain_text("VENDOR")
    expect(identifiers).not_to_contain_text("GTIN")
    expect(landed.locator("#product-specifications")).to_contain_text(FIXTURE_UPC)


# ---------------------------------------------------------------------------
# 019: the listing fills in the manufacturer part number (issue #90)
# ---------------------------------------------------------------------------

FIXTURE_MPN = "ACME-7700-B"   # the Mfr Part Number row in the fixture's tech-spec table


@pytest.mark.e2e
def test_the_listing_fills_in_the_manufacturer_part_number(
    page, live_server, image_host
):
    """019 US1, end to end: the row was on the page, so the field is filled.

    Issue #90's whole complaint: the capture displayed a `Mfr Part Number` row
    and left the field next to it blank.
    """
    landed = capture_from_listing(page, live_server, image_host)

    # Nothing has been typed into it. The form is server-rendered, so the value
    # being there is the completion signal -- no further wait is possible or
    # needed (CLAUDE.md, render-implies-completion).
    expect(landed.locator("#manufacturer_part_number")).to_have_value(FIXTURE_MPN)

    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    expect(landed.locator("#product-mpn")).to_have_text(FIXTURE_MPN)
    # FR-008: the row it came from is still an ordinary specification.
    expect(landed.locator("#product-specifications")).to_contain_text(FIXTURE_MPN)


@pytest.mark.e2e
def test_a_cleared_part_number_is_not_put_back(page, live_server, image_host):
    """019 US2 scenario 2: it is a default, and clearing it is a decision"""
    landed = capture_from_listing(page, live_server, image_host)
    expect(landed.locator("#manufacturer_part_number")).to_have_value(FIXTURE_MPN)

    confirm(landed, description="12V 3A PSU", manufacturer_part_number="")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    # The region first, then the absence -- #product-mpn is rendered only when
    # the product has one, so "no such element" would also be true of a page
    # that has not loaded.
    expect(landed.locator("#product-description")).to_have_text("12V 3A PSU")
    expect(landed.locator("#product-mpn")).to_have_count(0)
    # ...and the row is still there regardless, unfiltered.
    expect(landed.locator("#product-specifications")).to_contain_text(FIXTURE_MPN)


@pytest.mark.e2e
def test_an_unusable_higher_priority_row_is_passed_over(page, live_server, image_host):
    """019 US3 scenario 2, in a browser.

    The fixture carries a `Manufacturer Part Number` row longer than the column
    holds, above its usable `Mfr Part Number`. Ending the search on the unusable
    one would leave the field blank -- the bug this feature exists to fix,
    reintroduced through the front door. Offering it instead would fail the
    write at the end of the capture.

    The empty and whitespace-only cases cannot be reached from here: the agent
    drops a row with no value before the payload is built. They are covered in
    ``TestThePartNumberTheListingNames``.
    """
    landed = capture_from_listing(page, live_server, image_host)

    expect(landed.locator("#manufacturer_part_number")).to_have_value(FIXTURE_MPN)

    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    expect(landed.locator("#product-mpn")).to_have_text(FIXTURE_MPN)
    # FR-008: passed over as a default, still kept as a specification row.
    expect(landed.locator("#product-specifications")).to_contain_text(
        "NOT-A-PART-NUMBER"
    )


@pytest.mark.e2e
def test_a_repeat_buy_no_longer_has_to_answer_the_identifier_question(
    page, live_server, image_host
):
    """019's payoff beyond the field itself, and a behaviour change worth pinning.

    The manufacturer and the part number together are the evidence that decides
    whether a capture landing on an existing product's identifier is the same
    product or a recycled id (006 FR-019, `_corroborates`). The bookmarklet has
    always supplied the manufacturer; until 019 nothing supplied the part number,
    so the pair never corroborated and every re-capture raised the question.

    Now the listing supplies both halves, so a repeat buy of the same listing
    attaches to the product without being asked -- which is the reason the spec
    calls the empty field a cost paid at every later purchase, not a cosmetic
    gap.

    The duplicate-purchase question is unaffected and is still raised: that one
    is about two orders on one day, and no part number can answer it.
    """
    landed = capture_from_listing(page, live_server, image_host)
    expect(landed.locator("#manufacturer_part_number")).to_have_value(FIXTURE_MPN)
    confirm(landed, description="12V 3A PSU")

    again = capture_from_listing(page, live_server, image_host)
    again.click("#capture-btn")

    # The duplicate question still stands, and its arrival is what tells us the
    # submit was processed -- so the absence below is a real absence, not a page
    # that has not rendered yet.
    expect(again.locator("#duplicate-warning")).to_be_visible()
    expect(again.locator("#identifier-warning")).to_have_count(0)

    again.check("#acknowledged_duplicate_of")
    again.click("#capture-btn")

    again.goto(f"{live_server.url}/products")
    # One product, not two: it attached rather than branching.
    expect(again.locator("#product-table tbody tr")).to_have_count(1)


# ---------------------------------------------------------------
# Issue #92: the listing's own "About this item" bullets
# ---------------------------------------------------------------

ABOUT_THIS_ITEM = "About this item"

# What amazon_listing.html's bullet list must yield. Two of B01N4OSKWE's real
# bullets -- the second is where that listing publishes its dimensions, and it
# publishes them nowhere else -- and one that had to be cleaned of the styling
# and script inside it. The whitespace-only item and the image-only item are
# absent, because a bullet with no words is not a line.
BULLET_LINES = [
    "Country of Manufacture: CHINA; Material: Plastic,Metal; Net Weight: 9g",
    'Main Body Size: 15 x 7 x 7mm/0.59"x0.28"x0.28"(L*W*H); Overall Size: 23 x 16 x 7mm',
    "Action Type: Latching; Contact Type: DPDT; Terminal Quantity: 6",
]


def about_this_item(payload):
    """The bullets row out of a payload, or None.

    Folded the way both merges fold a name, so a fixture that changed the
    heading's capitalisation would still be found rather than silently missed.
    """
    for row in payload.get("specifications", []):
        if row["name"].strip().lower() == ABOUT_THIS_ITEM.lower():
            return row
    return None


@pytest.mark.e2e
def test_the_about_this_item_bullets_are_captured(page, live_server, image_host):
    """US1 scenarios 1-3 / FR-001..FR-004, FR-010.

    The whole feature. On B01N4OSKWE every dimension the product has is in
    these bullets and in no table on the page, so a capture that skipped them
    stored a record that said nothing about the thing that was bought.
    """
    landed = capture_from_listing(page, live_server, image_host)

    entries = payload_of(landed)["specifications"]

    # FR-010, and not an accident of ordering: `specificationsFrom` seeds both
    # its list and its fold with this row before it reads a single container.
    assert entries[0]["name"] == ABOUT_THIS_ITEM
    # FR-003: one bullet per line, in the order the listing shows them.
    assert entries[0]["value"].split("\n") == BULLET_LINES


@pytest.mark.e2e
def test_the_bullets_reach_the_product(page, live_server, image_host):
    """US1 scenario 4: the dimensions are in the catalog, not just the payload"""
    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")

    specifications = landed.locator("#product-specifications")
    expect(specifications).to_contain_text(ABOUT_THIS_ITEM)
    # The reason the issue was filed, in one assertion.
    expect(specifications).to_contain_text("Main Body Size: 15 x 7 x 7mm")


@pytest.mark.e2e
def test_the_bullets_row_changes_nothing_else(page, live_server, image_host):
    """US1 scenario 5 / FR-012: a row was added to the reading, not swapped in"""
    landed = capture_from_listing(page, live_server, image_host)
    payload = payload_of(landed)

    assert payload["listing_title"] == "Acme 12V 3A Power Supply Adapter"
    assert payload["brand"] == "Acme Components"
    assert payload["price"] == "24.99"
    assert len(payload["images"]) == GALLERY_IMAGE_COUNT
    # Every container is still read and still merged across all four of them.
    names = [row["name"] for row in payload["specifications"]]
    for expected in ("Brand", "Connector Type", "Item Length", "Best Sellers Rank"):
        assert expected in names


@pytest.mark.e2e
def test_the_bullets_row_holds_no_page_furniture(page, live_server, image_host):
    """US3 / FR-005..FR-007, and the trap issue #92 only half identified.

    ``#feature-bullets`` is not only bullets. It opens with an ``<h2>About this
    item</h2>`` and closes with a "See more product details" link, both inside
    the container and both outside the list -- so the container's own
    ``textContent`` begins "About this item Country of Manufacture: CHINA...".
    Reading the ``li`` elements is what excludes them.

    Nothing here tests visibility, and nothing could: ``canonicalDocument()``
    parses a detached document with no layout and no stylesheets, where
    ``offsetHeight`` is 0 for everything. The exclusion is structural.
    """
    landed = capture_from_listing(page, live_server, image_host)
    value = about_this_item(payload_of(landed))["value"]

    # The heading, which shares its wording with the row's own name.
    assert ABOUT_THIS_ITEM not in value
    # The trailing link. Issue #92 expected a hidden <li>; it is a visible
    # sibling <div>, and `li` scoping excludes it either way.
    assert "See more product details" not in value

    lines = value.split("\n")
    # FR-006: the whitespace-only bullet and the image-only bullet contributed
    # nothing, and neither left a blank line behind them.
    assert lines == BULLET_LINES
    assert "" not in lines
    assert value == value.strip()

    # FR-007: #91's rule, on a third surface. Neither is writing.
    assert "color: #0F1111" not in value
    assert "bulletsReady" not in value


@pytest.mark.e2e
def test_a_table_row_of_the_same_name_loses_to_the_bullets(
    page, live_server, image_host
):
    """US2 scenario 3 / FR-009, and the reason the fold is *seeded*.

    The A+ fixture publishes a detail-table row named ``about this item``,
    differing from the bullets' name only in case. Exactly one row of that name
    may survive and it must be the bullets -- which holds only because
    ``specificationsFrom`` seeds its ``seen`` map before reading any container.
    Pushing the bullets onto the list without seeding would yield both, and
    neither fold downstream would catch it.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_aplus.html"
    )
    entries = payload_of(landed)["specifications"]

    matching = [
        row for row in entries
        if row["name"].strip().lower() == ABOUT_THIS_ITEM.lower()
    ]
    assert len(matching) == 1
    assert matching[0]["value"].startswith("Stocked in 300mm")
    assert "must lose to the bullets" not in matching[0]["value"]


@pytest.mark.e2e
def test_re_capturing_leaves_one_bullets_row(page, live_server, image_host):
    """US2 scenarios 1-2 / FR-009. Delivered by machinery that already existed.

    ``merge_specifications`` drops a captured name the product already carries,
    value included. Nothing was written for this story; what is asserted here is
    that the new row is not somehow exempt from the rule.
    """
    landed = capture_from_listing(page, live_server, image_host)
    confirm(landed, description="12V 3A PSU")

    landed.goto(f"{live_server.url}/products")
    landed.click("#product-table tbody tr td a")
    # Establishes the region before the count below is read: the negative half
    # of this test is a count, and a count against a page that has not rendered
    # is zero for the wrong reason.
    expect(landed.locator("#product-specifications")).to_contain_text(ABOUT_THIS_ITEM)
    product_url = landed.url
    before = landed.locator("#product-specifications .specification-name").count()

    again = capture_from_listing(page, live_server, image_host)
    again.click("#capture-btn")
    # Raised in response to the submit rather than on the landing page, so its
    # arrival is what tells us the submit was processed. The identifier question
    # is not raised: 019 fills the part number, which corroborates.
    expect(again.locator("#duplicate-warning")).to_be_visible()
    again.check("#acknowledged_duplicate_of")
    again.click("#capture-btn")

    again.goto(product_url)
    names = again.locator("#product-specifications .specification-name")
    expect(names).to_have_count(before)
    expect(names.filter(has_text=re.compile(r"^About this item$"))).to_have_count(1)


@pytest.mark.e2e
def test_a_listing_with_no_bullet_list_captures_as_before(
    page, live_server, image_host
):
    """US4 scenario 1 / FR-008, FR-012: no section, no row, nothing else moved"""
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_markup_only.html"
    )
    payload = payload_of(landed)

    assert about_this_item(payload) is None
    # FR-008: and not an empty-valued row either. One would be dropped by
    # `_payload_specifications` on arrival without anyone hearing about it,
    # which is why the agent must not emit it rather than merely tolerate it.
    assert all(row["value"] for row in payload["specifications"])
    # FR-012, on the fixture that has no bullets to distract from it.
    assert payload["description_text"] == (
        "Knurled brass standoff, M3 thread, 10mm between faces."
    )
    assert payload["price"] == "8.75"
    assert [row["name"] for row in payload["specifications"]] == ["Material"]


@pytest.mark.e2e
def test_a_bullet_list_with_nothing_readable_yields_no_row(
    page, live_server, image_host
):
    """US4 scenario 2 / FR-008, FR-011: found the container, read nothing from it.

    A different branch from the test above, which never finds the container at
    all. This one finds it, finds the heading, the "See more" link and one empty
    item, and must still produce no row.
    """
    landed = capture_from_listing(
        page, live_server, image_host, fixture="amazon_listing_bullets_empty.html"
    )
    payload = payload_of(landed)

    assert about_this_item(payload) is None
    assert all(row["value"] for row in payload["specifications"])
    assert payload["price"] == "4.20"
