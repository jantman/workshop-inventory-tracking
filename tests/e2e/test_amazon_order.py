"""E2E: capturing a whole Amazon order (feature 029, US1).

The same harness as ``test_mcmaster_order.py``, and for the same reason its
module docstring sets out: the fixture order page is served from **this
application's own origin**, because Chrome will not let one origin load a
subresource from a more-private address space and the agent script would never
load from a convincing ``https://www.amazon.com/...``. That is why the dispatch
keys on the URL *path* and never the hostname.

**The test that matters most here is the row-scoping one.** A real Amazon
order-details page carries roughly 26 ``/dp/`` links across 9 distinct ASINs for
a four-line order; the surplus are "buy it again" and "related to items you
viewed" carousels. A reader that sweeps the document for ASINs invents five order
lines out of Amazon's advertising, and every one of them would look plausible on
the review. The fixture reproduces that ratio deliberately, so asserting the
*count* is what catches it -- asserting that "some lines were read" would pass
against the bug.
"""

import json
import re
from datetime import datetime

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService
from tests.e2e.test_product_page_capture import FIXTURES, run_capture

# The shape the agent dispatches on: /your-orders/order-details?orderID=...
ORDER_ID = "111-2223334-5556667"
ORDER_ROUTE = re.compile(r"/your-orders/order-details")

# What the fixture's own markup says. The reader has to get these right rather
# than these being chosen to suit it.
LINE_COUNT = 4
DISTINCT_ASINS_ON_PAGE = 9      # 4 ordered + 5 recommended
FIRST_ASIN = "B0TESTAAA1"
LAST_ASIN = "B0TESTAAA4"


def serve_order(page, image_host, fixture="amazon_order.html"):
    """Fulfil the order path with the fixture, wherever it is asked for."""
    body = (FIXTURES / fixture).read_text().replace("__IMAGE_HOST__", image_host)
    page.route(
        ORDER_ROUTE,
        lambda route: route.fulfill(
            status=200, content_type="text/html", body=body
        ),
    )


def capture_order(page, live_server, image_host, fixture="amazon_order.html",
                  order_id=ORDER_ID):
    """Serve the fixture order and run the real reader on it."""
    serve_order(page, image_host, fixture)
    return run_capture(
        page,
        live_server,
        f"{live_server.url}/your-orders/order-details?orderID={order_id}",
        landing="#order-lines, #no-order",
    )


def payload_of(review):
    """The order as it sits in the hidden field, before anything is written."""
    return json.loads(review.locator("#order-payload").input_value())


def line(review, key):
    """One review row, by the form key that names its controls."""
    return review.locator(f'tr.order-line[data-line="{key}"]')


def confirm(review):
    """Submit the review, and wait for the order screen it lands on."""
    review.click("#confirm-capture")
    # A full navigation, so the landing page's own marker is the completion
    # signal (pattern C). Reading a count before it lands would read zero.
    expect(review.locator("#order-progress, #not-captured")).to_be_visible()
    return review


def order_screen(page, live_server, order_number=ORDER_ID):
    page.goto(f"{live_server.url}/products/orders/Amazon/{order_number}")
    expect(page.locator("#not-captured, #order-lines")).to_be_visible()
    return page


# --------------------------------------------------------------------------
# Reading the page
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_the_agent_reads_exactly_the_ordered_lines(page, live_server, image_host):
    """US1, and the recommendation trap (research.md §4).

    The count is the assertion. The page offers nine distinct ASINs and only
    four of them were ordered.
    """
    review = capture_order(page, live_server, image_host)

    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)


@pytest.mark.e2e
def test_no_recommended_item_becomes_an_order_line(page, live_server, image_host):
    """The other half of the same trap, stated as a negative.

    Established with an ``expect`` first, so this cannot pass against a page
    that has not rendered.
    """
    review = capture_order(page, live_server, image_host)
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)

    parts = review.locator("tr.order-line").evaluate_all(
        "rows => rows.map(r => r.dataset.part)"
    )

    assert not any(part.startswith("B0RECOMM") for part in parts), parts
    assert parts == ["B0TESTAAA1", "B0TESTAAA2", "B0TESTAAA3", "B0TESTAAA4"]


@pytest.mark.e2e
def test_the_order_number_and_date_are_read(page, live_server, image_host):
    review = capture_order(page, live_server, image_host)

    payload = payload_of(review)

    assert payload["order_number"] == ORDER_ID
    assert payload["order_date"] == "August 22, 2026"


@pytest.mark.e2e
def test_the_price_is_read_without_its_screen_reader_twin(page, live_server, image_host):
    """`.a-offscreen`, not innerText -- which would yield "$9.99 $9.99"."""
    review = capture_order(page, live_server, image_host)

    prices = [ln["unit_price"] for ln in payload_of(review)["lines"]]

    assert prices == ["9.99", "13.95", "8.99", "16.99"]


@pytest.mark.e2e
def test_a_multi_quantity_line_is_read_from_its_badge(page, live_server, image_host):
    """The quantity is a badge over the image, in the row's **left** grid.

    `[data-component="quantity"]` is on every row and is always empty -- even on
    a line of four -- so a reader that keys on it records every multi-quantity
    line as a single item, silently. This is the test that would have caught
    that; the fixture's row 2 is a quantity of 4 and the rest are 1, which is how
    a real order with one multi-quantity line renders (research.md §6).
    """
    review = capture_order(page, live_server, image_host)

    quantities = [ln["quantity"] for ln in payload_of(review)["lines"]]

    assert quantities == [1, 4, 1, 1]


@pytest.mark.e2e
def test_a_line_with_no_badge_reads_as_one(page, live_server, image_host):
    """Amazon omits the badge entirely for a quantity of one."""
    review = capture_order(page, live_server, image_host)

    lines = payload_of(review)["lines"]

    assert lines[0]["quantity"] == 1
    assert lines[3]["quantity"] == 1


@pytest.mark.e2e
def test_lines_split_across_two_shipment_groups_are_all_read(page, live_server, image_host):
    """`purchasedItems` is a group, not a line: the fixture has 3 then 1."""
    review = capture_order(page, live_server, image_host)

    payload = payload_of(review)

    assert payload["lines_read"] == LINE_COUNT
    assert len(payload["lines"]) == LINE_COUNT


@pytest.mark.e2e
def test_the_review_writes_nothing(page, live_server, image_host):
    """FR-005. Closing the tab leaves no trace."""
    capture_order(page, live_server, image_host)

    page.goto(f"{live_server.url}/products")
    expect(page.locator("body")).not_to_contain_text("Digital Calipers")


# --------------------------------------------------------------------------
# Confirming
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_confirming_records_one_outstanding_line_each(page, live_server, image_host):
    review = capture_order(page, live_server, image_host)
    confirm(review)

    order_screen(page, live_server)
    expect(page.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(page.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT} of {LINE_COUNT}"
    )


@pytest.mark.e2e
def test_an_excluded_line_produces_nothing(page, live_server, image_host):
    review = capture_order(page, live_server, image_host)
    review.uncheck("#include-2")
    confirm(review)

    order_screen(page, live_server)
    expect(page.locator("tr.order-line")).to_have_count(LINE_COUNT - 1)


@pytest.mark.e2e
def test_recapturing_records_nothing_new(page, live_server, image_host):
    """SC-003."""
    confirm(capture_order(page, live_server, image_host))

    review = capture_order(page, live_server, image_host)
    expect(review.locator('tr.order-line[data-state="CAPTURED"]')).to_have_count(
        LINE_COUNT
    )

    confirm(review)
    order_screen(page, live_server)
    expect(page.locator("tr.order-line")).to_have_count(LINE_COUNT)


@pytest.mark.e2e
def test_the_review_says_the_products_will_be_thin(page, live_server, image_host):
    """FR-026. The operator is told, rather than discovering it later."""
    review = capture_order(page, live_server, image_host)

    expect(review.locator("#order-page-detail-note")).to_be_visible()


@pytest.mark.e2e
def test_the_captured_order_appears_in_the_orders_list(page, live_server, image_host):
    """FR-033: one place that answers "what is on its way?"."""
    confirm(capture_order(page, live_server, image_host))

    page.goto(f"{live_server.url}/products/orders")
    expect(page.locator("#orders-table")).to_be_visible()
    expect(
        page.locator(f'tr.captured-order[data-order="{ORDER_ID}"]')
    ).to_have_count(1)


# --------------------------------------------------------------------------
# A purchase already recorded from the item's listing page (feature 033)
# --------------------------------------------------------------------------

# The fixture order is dated 22 August 2026; a listing capture the operator made
# a few days earlier is inside the ninety-day window and is the case issue #129
# was reported for.
LISTING_CAPTURE_DATE = "2026-08-18"


def seed_listing_capture(live_server, asin=FIRST_ASIN):
    """A purchase as the single-listing capture writes one: no order number.

    Seeded directly rather than driven through the capture form, which takes
    about three seconds and is not what these tests are about.
    """
    service = CatalogService(live_server.storage)
    product = service.create_product(description="Digital Calipers")
    return service.record_purchase(
        product.id,
        vendor="Amazon",
        vendor_item_id=asin,
        listing_url=f"https://www.amazon.com/dp/{asin}",
        order_date=datetime.fromisoformat(LISTING_CAPTURE_DATE),
        quantity=1,
        unit_price="9.99",
    )


def purchase_rows(page, live_server, product_id):
    """The product's purchase history, established before it is counted."""
    page.goto(f"{live_server.url}/products/{product_id}")
    expect(page.locator("#purchase-history")).to_be_visible()
    return page.locator("#purchase-history tbody tr.purchase-row")


@pytest.mark.e2e
def test_a_line_already_captured_from_its_listing_asks_rather_than_duplicating(
    page, live_server, image_host
):
    """033 US1: the review states it, and offers the choice."""
    seed_listing_capture(live_server)

    review = capture_order(page, live_server, image_host)
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)

    asked = line(review, "1").locator(".same-purchase")
    expect(asked).to_be_visible()
    expect(asked).to_contain_text("already recorded")
    # The other three lines have nothing already recorded for them.
    expect(review.locator("tr.order-line .same-purchase")).to_have_count(1)


@pytest.mark.e2e
def test_adopting_it_leaves_one_purchase_carrying_the_order(
    page, live_server, image_host
):
    """033 FR-012, FR-013: the row already there joins the order."""
    seeded = seed_listing_capture(live_server)

    review = capture_order(page, live_server, image_host)
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    review.check("#adopt-1")
    confirm(review)

    # The order carries all four lines, and the adopted one is the row that was
    # already there -- proved by the link pointing at the seeded product rather
    # than at one this capture created.
    order_screen(page, live_server)
    expect(page.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(
        page.locator(
            f'tr.order-line a[href$="/products/{seeded.product_id}"]'
        )
    ).to_have_count(1)

    # One purchase, not two -- issue #129. The product page does not render the
    # order number, so the date is what says which row this is: the seeded
    # capture was dated 18 August and the order states the 22nd, and the stamp
    # is what makes them agree (033 FR-012).
    rows = purchase_rows(page, live_server, seeded.product_id)
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text("2026-08-22")


@pytest.mark.e2e
def test_leaving_the_question_unanswered_refuses_the_whole_capture(
    page, live_server, image_host
):
    """033 FR-008a, FR-016: an order-level question, so nothing is written."""
    seeded = seed_listing_capture(live_server)

    review = capture_order(page, live_server, image_host)
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    review.click("#confirm-capture")

    # The review comes back with the refusal flashed, rather than navigating on.
    expect(review.locator(".alert-danger")).to_be_visible()
    expect(review.locator("tr.order-line .same-purchase")).to_have_count(1)

    # **Established before it is counted.** A negative assertion against a table
    # that has not rendered passes for the wrong reason.
    rows = purchase_rows(page, live_server, seeded.product_id)
    expect(rows).to_have_count(1)
    expect(rows.first).to_contain_text(LISTING_CAPTURE_DATE)


# --------------------------------------------------------------------------
# Packs recorded as units (feature 046, issue #137)
# --------------------------------------------------------------------------
#
# The fixture already carries the two shapes this needs, which is why nothing
# new is served here: line 2 is "Assorted Heat Shrink Tubing Kit, **560
# Pieces**" and line 4 is "Magnetic Parts Tray Set, **3 Piece**", while lines 1
# and 3 name no count at all. A real four-line order with two pack lines, read
# off markup written before the feature existed.

# Line 1: "Digital Calipers 6 Inch Stainless Steel with Fractions". The "6" is
# a dimension and the parse must not read it, so this is the line the operator
# has to state a pack size on by hand.
PLAIN_LINE = "1"
# Line 2: "... 560 Pieces ...", quantity 4 on the fixture's badge.
SUGGESTED_LINE = "2"
SUGGESTED_PACK = 560


def pack_size_field(review, key):
    return line(review, key).locator(".line-pack-size")


def quantity_field(review, key):
    return line(review, key).locator(".line-quantity")


def unit_price_field(review, key):
    return line(review, key).locator(".line-unit-price")


@pytest.mark.e2e
def test_stating_a_pack_size_converts_the_line(page, live_server, image_host):
    """US1 scenario 1, the reported defect.

    ``to_have_value`` polls; ``input_value()`` does not, and against a field a
    script is about to rewrite it reads the pre-conversion number on a slow
    machine (CLAUDE.md pattern E).
    """
    review = capture_order(page, live_server, image_host)

    # The plain line starts unconverted, at what Amazon stated.
    expect(quantity_field(review, PLAIN_LINE)).to_have_value("1")
    expect(unit_price_field(review, PLAIN_LINE)).to_have_value("9.99")

    pack_size_field(review, PLAIN_LINE).fill("100")

    expect(quantity_field(review, PLAIN_LINE)).to_have_value("100")
    expect(unit_price_field(review, PLAIN_LINE)).to_have_value("0.10")


@pytest.mark.e2e
def test_a_converted_line_records_items(page, live_server, image_host):
    """SC-001. The purchase is in items at a per-item price."""
    review = capture_order(page, live_server, image_host)
    pack_size_field(review, PLAIN_LINE).fill("100")
    expect(quantity_field(review, PLAIN_LINE)).to_have_value("100")
    confirm(review)

    order_screen(page, live_server)
    first = page.locator("tr.order-line").first
    expect(first).to_contain_text("100")
    expect(first.locator(".line-pack")).to_contain_text("pack of 100")


@pytest.mark.e2e
def test_a_line_left_alone_records_what_the_order_stated(
    page, live_server, image_host
):
    """FR-002, SC-005. The change costs nothing where it is not used."""
    review = capture_order(page, live_server, image_host)

    expect(pack_size_field(review, PLAIN_LINE)).to_have_value("1")
    confirm(review)

    order_screen(page, live_server)
    first = page.locator("tr.order-line").first
    expect(first).to_contain_text("9.99")
    # Establish the row before asserting an absence, or this passes against a
    # table that has not rendered (CLAUDE.md, negative assertions).
    expect(first.locator(".line-pack")).to_have_count(0)


@pytest.mark.e2e
def test_a_title_naming_a_count_arrives_pre_filled_and_marked(
    page, live_server, image_host
):
    """US3. "560 Pieces" is read, offered, and plainly labelled a guess."""
    review = capture_order(page, live_server, image_host)

    expect(pack_size_field(review, SUGGESTED_LINE)).to_have_value(
        str(SUGGESTED_PACK)
    )
    expect(line(review, SUGGESTED_LINE).locator(".pack-size-suggested")).to_be_visible()


@pytest.mark.e2e
def test_a_title_naming_no_count_is_not_guessed_at(page, live_server, image_host):
    """FR-022, and the reason the parse anchors on a word.

    "Digital Calipers **6 Inch**" and "Cutting Fluid, **16 oz** Bottle" are the
    trap: a parse that read a bare number would multiply both purchases.
    """
    review = capture_order(page, live_server, image_host)

    expect(pack_size_field(review, PLAIN_LINE)).to_have_value("1")
    expect(line(review, PLAIN_LINE).locator(".pack-size-suggested")).to_have_count(0)


@pytest.mark.e2e
def test_the_review_says_which_lines_were_converted(page, live_server, image_host):
    """US2, FR-014. A missed pack line must not look like a finished one.

    Asserted as the **presence** of the marking on the converted lines, never
    its absence on the others: the absent form also passes against a table
    that has not rendered (CLAUDE.md pattern F).
    """
    review = capture_order(page, live_server, image_host)

    expect(line(review, SUGGESTED_LINE).locator(".line-converted")).to_be_visible()
    expect(
        line(review, SUGGESTED_LINE).locator(".line-converted")
    ).to_contain_text(str(SUGGESTED_PACK))

    # The plain line is not claimed to have been converted. Asserted as the
    # positive fact that it carries the hidden class, rather than as an
    # absence -- the marking is always rendered so the script has something to
    # reveal, so "count == 0" would be wrong here and "not visible" would pass
    # against a row that has not rendered.
    expect(line(review, PLAIN_LINE).locator(".line-converted")).to_have_class(
        re.compile(r"\bd-none\b")
    )


@pytest.mark.e2e
def test_converting_a_line_by_hand_marks_it(page, live_server, image_host):
    """US2 for the line the operator converts themselves.

    The marking is rendered hidden for every line, so that setting a pack size
    on a line that arrived at 1 reveals it. A marking created only for
    already-converted lines would be absent for exactly the lines just
    converted by hand.
    """
    review = capture_order(page, live_server, image_host)
    marking = line(review, PLAIN_LINE).locator(".line-converted")
    expect(marking).to_have_class(re.compile(r"\bd-none\b"))

    pack_size_field(review, PLAIN_LINE).fill("100")

    expect(marking).to_be_visible()
    expect(marking).to_contain_text("1 \u00d7 100")


@pytest.mark.e2e
def test_overruling_a_suggestion_sticks(page, live_server, image_host):
    """FR-021. A guess the operator has corrected is no longer a guess."""
    review = capture_order(page, live_server, image_host)
    expect(pack_size_field(review, SUGGESTED_LINE)).to_have_value(
        str(SUGGESTED_PACK)
    )

    pack_size_field(review, SUGGESTED_LINE).fill("10")

    expect(quantity_field(review, SUGGESTED_LINE)).to_have_value("40")
    expect(
        line(review, SUGGESTED_LINE).locator(".pack-size-suggested")
    ).to_have_count(0)


@pytest.mark.e2e
def test_a_refused_pack_size_keeps_every_other_entry(page, live_server, image_host):
    """FR-011, FR-012, FR-013. Nothing is written and nothing is retyped."""
    review = capture_order(page, live_server, image_host)
    review.fill('input[name="description[3]"]', "Way Oil")
    pack_size_field(review, PLAIN_LINE).fill("0")

    review.click("#confirm-capture")

    # The review comes back rather than landing on the order screen.
    expect(review.locator("#order-lines")).to_be_visible()
    expect(review.locator('input[name="description[3]"]')).to_have_value("Way Oil")
    expect(pack_size_field(review, PLAIN_LINE)).to_have_value("0")

    order_screen(page, live_server)
    expect(page.locator("#not-captured")).to_be_visible()


@pytest.mark.e2e
def test_a_captured_pack_order_shows_both_views(page, live_server, image_host):
    """US5, FR-034. The invoice reconciles without opening Amazon."""
    review = capture_order(page, live_server, image_host)
    expect(pack_size_field(review, SUGGESTED_LINE)).to_have_value(
        str(SUGGESTED_PACK)
    )
    confirm(review)

    order_screen(page, live_server)
    expect(page.locator("tr.order-line")).to_have_count(LINE_COUNT)

    row = page.locator("tr.order-line").nth(1)
    expect(row.locator(".line-pack")).to_contain_text(f"pack of {SUGGESTED_PACK}")
    expect(row.locator(".line-pack-price")).to_contain_text("13.95")
