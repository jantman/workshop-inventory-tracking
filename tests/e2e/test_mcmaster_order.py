"""E2E: capturing a whole McMaster-Carr order (feature 028, US1).

The same harness as ``test_product_page_capture.py``, and for the same reasons
its module docstring sets out at length: the fixture order page is served from
**this application's own origin**, because Chrome will not let one origin load a
subresource from a more-private address space, and the agent script would simply
never load from a convincing ``http://www.mcmaster.com/...``. That is why the
dispatch keys on the URL *path* and never the hostname -- a host gate would
leave every line of the McMaster reader with no end-to-end coverage at all.

What this exercises that no unit test can: the **real bookmarklet**, clicked,
loading the **real agent**, reading the **real markup** off the fixture, posting
a real form into a new tab, and the review that lands there carrying enough to
write the order.

What it cannot exercise, stated rather than hidden: the genuinely cross-origin
half of the transport -- a real McMaster page over TLS submitting to this app
over plain HTTP on the LAN. That is a manual check in quickstart.md, as it is
for Amazon.
"""

import json
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.test_product_page_capture import (
    FIXTURES,
    image_host,  # noqa: F401  -- a fixture, used by injection
    run_bookmarklet,
)

# The shape the agent dispatches on: /order-history/order/<24 hex>.
ORDER_ID = "6a5ffba81f17e12ac4fb7d70"
ORDER_ROUTE = re.compile(r"/order-history/order/[0-9a-f]{24}")

# What the fixture's own markup says. Transcribed from a live order, so these
# are the values the reader has to get right rather than values chosen to suit
# it.
ORDER_NUMBER = "MISC-AND-GRINDER"
LINE_COUNT = 11
PACK_LINE_KEY = "5"          # 1 pack of 100 at 6.66 -- the sub-cent division
PACK_LINE_PART = "97387A173"
EACH_LINE_KEY = "1"          # 1 each at $10.23 -- the only line with a symbol
EACH_LINE_PART = "3103A21"
PAIRS_LINE_KEY = "7"         # 2 "Pairs" -- no pack size is derivable
PAIRS_LINE_PART = "4556T34"


def serve_order(page, image_host, fixture="mcmaster_order.html"):
    """Fulfil the order path with the fixture, wherever it is asked for."""
    body = (FIXTURES / fixture).read_text().replace("__IMAGE_HOST__", image_host)
    page.route(
        ORDER_ROUTE,
        lambda route: route.fulfill(
            status=200, content_type="text/html", body=body
        ),
    )


def capture_order(page, live_server, image_host, fixture="mcmaster_order.html"):
    """Serve the fixture order and click the real bookmarklet on it."""
    serve_order(page, image_host, fixture)
    return run_bookmarklet(
        page,
        live_server,
        f"{live_server.url}/order-history/order/{ORDER_ID}",
        landing="#order-lines",
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
    # A full navigation, so the order screen's own table is the completion
    # signal (pattern C). Reading a count before it lands would read zero.
    expect(review.locator("#order-progress")).to_be_visible()
    return review


def order_screen(page, live_server, order_number=ORDER_NUMBER):
    page.goto(f"{live_server.url}/products/mcmaster/orders/{order_number}")
    expect(page.locator("#not-captured, #order-lines")).to_be_visible()
    return page


# --------------------------------------------------------------------------
# Reading the page
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_the_agent_reads_every_line_of_the_order(page, live_server, image_host):
    """US1: one click, and the whole order is on screen."""
    review = capture_order(page, live_server, image_host)

    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(review.locator("#line-tally")).to_contain_text(
        f"{LINE_COUNT} line(s) ordered"
    )


@pytest.mark.e2e
def test_the_order_number_comes_off_an_input_value(page, live_server, image_host):
    """McMaster shows no order number; the Purchase Order string is in an
    editable input's `value`, not in element text (research.md §5)."""
    review = capture_order(page, live_server, image_host)

    expect(review.locator("#review-banner")).to_be_visible()
    assert payload_of(review)["order_number"] == ORDER_NUMBER


@pytest.mark.e2e
def test_the_opaque_order_id_is_read_off_the_path(page, live_server, image_host):
    """It is what makes a re-capture survive a renamed Purchase Order."""
    review = capture_order(page, live_server, image_host)

    assert payload_of(review)["order_id"] == ORDER_ID


@pytest.mark.e2e
def test_a_pack_line_becomes_units_and_a_unit_price(page, live_server, image_host):
    """FR-020. 1 pack of 100 at 6.66 is 100 units at 0.07."""
    review = capture_order(page, live_server, image_host)

    row = line(review, PACK_LINE_KEY)
    expect(row).to_contain_text(PACK_LINE_PART)
    expect(row.locator(".line-quantity")).to_have_value("100")
    expect(row.locator(".line-unit-price")).to_have_value("0.07")
    # And it says the division did not come out even, rather than letting the
    # operator find that in a reconciliation months later.
    expect(row.locator(".price-rounded")).to_be_visible()


@pytest.mark.e2e
def test_the_currency_symbol_on_the_first_line_only_is_not_a_problem(
    page, live_server, image_host
):
    """McMaster puts the symbol on line one and omits it on every line under
    it. A parser that required a `$` would read one line of eleven."""
    review = capture_order(page, live_server, image_host)

    expect(line(review, EACH_LINE_KEY).locator(".line-unit-price")).to_have_value(
        "10.23"
    )
    expect(line(review, "2").locator(".line-unit-price")).to_have_value("9.47")


@pytest.mark.e2e
def test_a_unit_with_no_derivable_count_leaves_the_pack_size_unread(
    page, live_server, image_host
):
    """"Pairs" is plainly not one item, and McMaster states no count anywhere.
    FR-037: say so rather than quietly recording 2 of something."""
    review = capture_order(page, live_server, image_host)

    row = line(review, PAIRS_LINE_KEY)
    expect(row).to_contain_text(PAIRS_LINE_PART)
    expect(row.locator(".line-quantity")).to_have_value("2")

    payload_line = next(
        entry for entry in payload_of(review)["lines"]
        if entry["part_number"] == PAIRS_LINE_PART
    )
    assert "pack_size" not in payload_line


@pytest.mark.e2e
def test_the_description_survives_its_span_wrapping(page, live_server, image_host):
    """The description `<p>` interleaves bare text nodes with `span.Wrd` around
    tokens carrying punctuation. Reading the spans alone yields fragments."""
    review = capture_order(page, live_server, image_host)

    row = line(review, PAIRS_LINE_KEY)
    expect(row.locator(".line-description")).to_have_value(
        'Mounting Brackets For 0.6" High x 1.1" Wide Open Snap-Together '
        'Cable And Hose Carrier'
    )


@pytest.mark.e2e
def test_prices_cross_the_boundary_as_strings(page, live_server, image_host):
    """Constitution III. A JSON number would already be a float by the time
    anything could assert on it."""
    review = capture_order(page, live_server, image_host)

    raw = review.locator("#order-payload").input_value()
    assert '"pack_price": "10.23"' in raw or '"pack_price":"10.23"' in raw
    for entry in payload_of(review)["lines"]:
        if "pack_price" in entry:
            assert isinstance(entry["pack_price"], str)


# --------------------------------------------------------------------------
# Confirming, and not confirming
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_confirming_writes_one_purchase_per_line(page, live_server, image_host):
    review = capture_order(page, live_server, image_host)
    confirm(review)

    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(review.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT} of {LINE_COUNT} still outstanding"
    )


@pytest.mark.e2e
def test_the_order_screen_shows_every_line_and_the_outstanding_count(
    page, live_server, image_host
):
    """US1 scenario 8, reached by capturing and then opening the order."""
    review = capture_order(page, live_server, image_host)
    confirm(review)

    screen = order_screen(page, live_server)

    expect(screen.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(screen.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT} of {LINE_COUNT} still outstanding"
    )
    expect(
        screen.locator(f'tr.order-line[data-part="{PACK_LINE_PART}"]')
    ).to_contain_text("outstanding")


@pytest.mark.e2e
def test_closing_the_review_without_confirming_writes_nothing(
    page, live_server, image_host
):
    """FR-005. There was never a record, only a page."""
    review = capture_order(page, live_server, image_host)
    # Established first: a count read against a page that has not rendered
    # passes trivially, and this assertion is the negative kind that would.
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    review.close()

    screen = order_screen(page, live_server)

    expect(screen.locator("#not-captured")).to_be_visible()
    expect(screen.locator("tr.order-line")).to_have_count(0)


@pytest.mark.e2e
def test_an_excluded_line_produces_neither_a_product_nor_a_purchase(
    page, live_server, image_host
):
    """FR-009: an excluded line becomes nothing."""
    review = capture_order(page, live_server, image_host)
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    review.uncheck(f"#include-{PACK_LINE_KEY}")
    confirm(review)

    screen = order_screen(page, live_server)

    expect(screen.locator("tr.order-line")).to_have_count(LINE_COUNT - 1)
    expect(
        screen.locator(f'tr.order-line[data-part="{PACK_LINE_PART}"]')
    ).to_have_count(0)

    # No *product* either, and the catalog's own answer is what proves it: a
    # re-capture reads the excluded line as NEW, which it can only be when
    # nothing carries its part number and no purchase is recorded for it. The
    # lines that were taken come back CAPTURED in the same review, so this
    # cannot pass by the review having failed to load.
    review.close()
    again = capture_order(page, live_server, image_host)
    expect(again.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(line(again, PACK_LINE_KEY)).to_have_attribute("data-state", "NEW")
    expect(line(again, EACH_LINE_KEY)).to_have_attribute(
        "data-state", "CAPTURED"
    )


@pytest.mark.e2e
def test_a_second_capture_of_the_same_order_records_nothing(
    page, live_server, image_host
):
    """SC-003."""
    review = capture_order(page, live_server, image_host)
    confirm(review)
    review.close()

    again = capture_order(page, live_server, image_host)

    expect(again.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(again.locator('tr.order-line[data-state="CAPTURED"]')).to_have_count(
        LINE_COUNT
    )
    confirm(again)

    screen = order_screen(page, live_server)
    expect(screen.locator("tr.order-line")).to_have_count(LINE_COUNT)


@pytest.mark.e2e
def test_the_operator_description_is_what_lands_on_the_product(
    page, live_server, image_host
):
    """FR-008, and FR-023: McMaster's own wording is kept separately."""
    review = capture_order(page, live_server, image_host)
    row = line(review, EACH_LINE_KEY)
    expect(row.locator(".line-description")).not_to_have_value("")
    row.locator(".line-description").fill("Counterbore pilot, 5/16")
    confirm(review)

    screen = order_screen(page, live_server)

    expect(
        screen.locator(f'tr.order-line[data-part="{EACH_LINE_PART}"]')
    ).to_contain_text("Counterbore pilot, 5/16")


@pytest.mark.e2e
def test_an_edited_quantity_is_what_gets_recorded(page, live_server, image_host):
    """FR-020a. The operator can see the box and the page; the agent can only
    see the page."""
    review = capture_order(page, live_server, image_host)
    row = line(review, PACK_LINE_KEY)
    expect(row.locator(".line-quantity")).to_have_value("100")
    row.locator(".line-quantity").fill("96")
    confirm(review)

    screen = order_screen(page, live_server)

    expect(
        screen.locator(f'tr.order-line[data-part="{PACK_LINE_PART}"]')
    ).to_contain_text("96")


@pytest.mark.e2e
def test_an_order_nothing_was_captured_against_does_not_dead_end(
    page, live_server
):
    """FR-031: never a 404."""
    screen = order_screen(page, live_server, order_number="NO-SUCH-ORDER")

    expect(screen.locator("#not-captured")).to_be_visible()
