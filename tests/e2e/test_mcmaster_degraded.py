"""E2E: what a capture says when the page did not give it up (US4).

Nothing in this design *fails* when McMaster changes their markup -- a test
against a saved page proves the reader reads that page, and no more. What is
designed is the containment, and it is the containment these tests pin:

* a lost field costs that field, on that line, and the line still captures
  (FR-036, FR-037);
* the count of lines read is stated against the count offered, so "three of
  your fifteen" cannot be mistaken for "three" (FR-004);
* a page yielding no readable lines gets a plain statement and a way forward,
  never an empty review that reads like an empty order (FR-038).

Both fixtures are generated from ``mcmaster_order.html`` and say so in their own
headers. The point of deriving them rather than writing them fresh is that the
*surviving* markup is identical, so a difference in what is read is a difference
the stripping caused.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_mcmaster_order import (  # noqa: F401
    EACH_LINE_KEY,
    EACH_LINE_PART,
    LINE_COUNT,
    ORDER_NUMBER,
    PACK_LINE_KEY,
    capture_order,
    confirm,
    image_host,
    line,
    order_screen,
    payload_of,
)


def capture_stripped(page, live_server, image_host, fixture):
    return capture_order(page, live_server, image_host, fixture=fixture)


# --------------------------------------------------------------------------
# Prices stripped: every line still reads, and the loss is stated
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_every_line_still_reads_when_the_prices_are_gone(
    page, live_server, image_host
):
    """FR-036: a dead selector costs that field alone."""
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_no_prices.html"
    )

    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    expect(line(review, EACH_LINE_KEY)).to_contain_text(EACH_LINE_PART)
    # The quantity came through untouched -- only the price markup was removed.
    expect(line(review, EACH_LINE_KEY).locator(".line-quantity")).to_have_value("1")


@pytest.mark.e2e
def test_the_missing_prices_are_marked_per_line_and_left_editable(
    page, live_server, image_host
):
    """FR-037. A blank price on one line of eleven is not something the
    operator notices unaided."""
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_no_prices.html"
    )
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)

    expect(
        review.locator('.missing-field[data-field="price"]')
    ).to_have_count(LINE_COUNT)

    field = line(review, EACH_LINE_KEY).locator(".line-unit-price")
    expect(field).to_have_value("")
    expect(field).to_be_editable()


@pytest.mark.e2e
def test_the_tally_says_nothing_when_every_line_was_read(
    page, live_server, image_host
):
    """The lines were all read; only a field within them was lost. Saying
    "eleven of eleven" would be noise, and saying nothing here is what makes
    the other message mean something."""
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_no_prices.html"
    )

    expect(review.locator("#line-tally")).to_contain_text(
        f"{LINE_COUNT} line(s) ordered"
    )
    expect(review.locator("#incomplete-warning")).to_have_count(0)


@pytest.mark.e2e
def test_the_readable_lines_still_capture_with_their_parts_and_quantities(
    page, live_server, image_host
):
    """The containment, end to end: prices are lost and everything else is
    recorded, rather than the capture being lost."""
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_no_prices.html"
    )
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    confirm(review)

    screen = order_screen(page, live_server)

    expect(screen.locator("tr.order-line")).to_have_count(LINE_COUNT)
    row = screen.locator(f'tr.order-line[data-part="{EACH_LINE_PART}"]')
    expect(row).to_contain_text("1")
    expect(row).to_contain_text("outstanding")


@pytest.mark.e2e
def test_the_post_confirm_flash_names_the_lines_that_came_back_thin(
    page, live_server, image_host
):
    """FR-037, carried past the review so the record of which lines were thin
    survives leaving that page."""
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_no_prices.html"
    )
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    confirm(review)

    # `.alert` alone matches the order screen's own progress banner too.
    expect(review.locator(".alert-success")).to_contain_text(
        "The page did not give up every field for"
    )


@pytest.mark.e2e
def test_an_operator_can_fill_a_price_the_page_did_not_give(
    page, live_server, image_host
):
    """The field is blank and editable, not blank and stuck."""
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_no_prices.html"
    )
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    line(review, EACH_LINE_KEY).locator(".line-unit-price").fill("10.23")
    confirm(review)

    screen = order_screen(page, live_server)

    expect(
        screen.locator(f'tr.order-line[data-part="{EACH_LINE_PART}"]')
    ).to_contain_text("10.23")


# --------------------------------------------------------------------------
# No lines readable at all
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_an_order_with_no_readable_lines_says_so_plainly(
    page, live_server, image_host
):
    """FR-038. The order *was* recognized -- it has a Purchase Order string --
    so this must not render as an order that has no lines, and must not render
    as an error."""
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_unreadable.html"
    )

    expect(review.locator("#no-lines")).to_be_visible()
    expect(review.locator("#no-lines")).to_contain_text(ORDER_NUMBER)
    expect(review.locator("tr.order-line")).to_have_count(0)


@pytest.mark.e2e
def test_the_unreadable_order_still_names_the_order_it_found(
    page, live_server, image_host
):
    """The Purchase Order string and the date are where they always were; it
    is only the lines that moved."""
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_unreadable.html"
    )

    payload = payload_of(review)
    assert payload["order_number"] == ORDER_NUMBER
    assert payload["lines"] == []


@pytest.mark.e2e
def test_nothing_is_written_by_an_unreadable_order(
    page, live_server, image_host
):
    review = capture_stripped(
        page, live_server, image_host, "mcmaster_order_unreadable.html"
    )
    expect(review.locator("#no-lines")).to_be_visible()
    confirm(review)

    screen = order_screen(page, live_server)

    expect(screen.locator("#not-captured")).to_be_visible()
    expect(screen.locator("tr.order-line")).to_have_count(0)
