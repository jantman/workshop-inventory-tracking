"""E2E: unpacking a McMaster box a bag at a time (US3).

Capture an order, scan a part number off a bag, and land on **that line's
receipt** rather than on the product page. That distinction is the whole story:
capturing the order created products carrying those part numbers, so the
ordinary identifier lookup would match happily and open the product -- which
would work only for parts you had never bought before, exactly backwards.

The seeding here goes through the real capture, not ``add_test_data``, because
what is under test is the state a capture leaves behind: outstanding purchases
carrying a vendor, an order number and a line number, which is what the scan
matches on.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_mcmaster_order import (  # noqa: F401
    EACH_LINE_PART,
    LINE_COUNT,
    ORDER_NUMBER,
    PACK_LINE_PART,
    capture_order,
    confirm,
    image_host,
    order_screen,
)

SECOND_ORDER_ID = "0000000000000000000000ff"
SECOND_ORDER_NUMBER = "LATER-ORDER"


def capture_the_order(page, live_server, image_host):
    """Capture the fixture order and come back to the original tab."""
    review = capture_order(page, live_server, image_host)
    confirm(review)
    expect(review.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT} of {LINE_COUNT} still outstanding"
    )
    review.close()


def scan(page, live_server, value):
    """Resolve a scan and follow where it says to go.

    The same shape ``test_ecia_scan.py`` uses. ``scan-capture.js`` navigates to
    whatever ``/api/scan`` returns without inspecting the outcome, so driving
    the endpoint and following its url exercises the same routing the scanner
    does.
    """
    page.goto(live_server.url)
    result = page.evaluate(
        """async (scan) => {
            const r = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scan: scan })
            });
            return await r.json();
        }""",
        value,
    )
    page.goto(f"{live_server.url}{result['url']}")
    page.wait_for_load_state("domcontentloaded")
    return result


@pytest.mark.e2e
def test_scanning_a_bag_lands_on_its_receipt(page, live_server, image_host):
    """FR-032, and the precedence that makes it work. A product carrying this
    part number exists -- the capture created it -- so an identifier-first
    lookup would open that product instead."""
    capture_the_order(page, live_server, image_host)

    result = scan(page, live_server, EACH_LINE_PART)
    assert result["outcome"] == "receive", (
        'the scan resolved to %r -- the identifier lookup matched first'
        % result["outcome"]
    )

    # A full navigation to the receipt. Its own button is the completion
    # signal; a field read before it lands would read empty (pattern C).
    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    expect(page.locator("#receive-vendor")).to_have_text("McMaster-Carr")
    expect(page.locator("#receive-vendor-item")).to_have_text(EACH_LINE_PART)


@pytest.mark.e2e
def test_receiving_marks_the_line_and_drops_the_outstanding_count(
    page, live_server, image_host
):
    """Receiving itself is untouched (FR-029): the purchase is marked
    received, and what arrived is allowed to differ from what was ordered."""
    capture_the_order(page, live_server, image_host)

    result = scan(page, live_server, PACK_LINE_PART)
    assert result["outcome"] == "receive"
    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    expect(page.locator("#quantity")).to_have_value("100")
    # What arrived was short. The field is amendable, which is the point of it.
    page.fill("#quantity", "97")
    page.click("#confirm-receive-btn")

    # The receipt navigates on submit; the order screen is where the outcome
    # can be read back.
    screen = order_screen(page, live_server)

    expect(screen.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT - 1} of {LINE_COUNT} still outstanding"
    )
    row = screen.locator(f'tr.order-line[data-part="{PACK_LINE_PART}"]')
    expect(row).to_contain_text("received")
    expect(row).to_contain_text("97")


@pytest.mark.e2e
def test_two_candidates_offer_a_choice_and_receive_nothing(
    page, live_server, image_host
):
    """FR-032a. The catalog does not pick, and the two orders can be weeks
    apart -- which is why this is its own page rather than an order screen."""
    capture_the_order(page, live_server, image_host)
    # A second order carrying the same parts, distinguished by its own id.
    second = capture_order(
        page, live_server, image_host, order_id=SECOND_ORDER_ID,
        order_number=SECOND_ORDER_NUMBER,
    )
    confirm(second)
    second.close()

    result = scan(page, live_server, PACK_LINE_PART)
    assert result["outcome"] == "receive"

    expect(page.locator("#choose-line")).to_be_visible()
    expect(page.locator("tr.receive-candidate")).to_have_count(2)
    # Nothing was received by arriving here.
    expect(page.locator("#receive-candidates")).to_contain_text(ORDER_NUMBER)
    expect(page.locator("#receive-candidates")).to_contain_text(
        SECOND_ORDER_NUMBER
    )

    screen = order_screen(page, live_server)
    expect(screen.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT} of {LINE_COUNT} still outstanding"
    )


@pytest.mark.e2e
def test_picking_a_candidate_receives_only_that_line(
    page, live_server, image_host
):
    capture_the_order(page, live_server, image_host)
    second = capture_order(
        page, live_server, image_host, order_id=SECOND_ORDER_ID,
        order_number=SECOND_ORDER_NUMBER,
    )
    confirm(second)
    second.close()

    result = scan(page, live_server, PACK_LINE_PART)
    assert result["outcome"] == "receive"
    expect(page.locator("tr.receive-candidate")).to_have_count(2)
    page.locator(
        f'tr.receive-candidate[data-order="{ORDER_NUMBER}"] .receive-candidate-link'
    ).click()

    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    page.click("#confirm-receive-btn")

    # The first order lost a line; the second did not.
    screen = order_screen(page, live_server)
    expect(screen.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT - 1} of {LINE_COUNT} still outstanding"
    )
    other = order_screen(page, live_server, order_number=SECOND_ORDER_NUMBER)
    expect(other.locator("#outstanding-count")).to_contain_text(
        f"{LINE_COUNT} of {LINE_COUNT} still outstanding"
    )


@pytest.mark.e2e
def test_a_part_with_no_outstanding_line_falls_through_to_today(
    page, live_server, image_host
):
    """FR-032b. Once the line is received the scan must behave exactly as it
    does today -- the product page -- rather than offering to receive it a
    second time."""
    capture_the_order(page, live_server, image_host)

    result = scan(page, live_server, EACH_LINE_PART)
    assert result["outcome"] == "receive"
    expect(page.locator("#confirm-receive-btn")).to_be_visible()
    page.click("#confirm-receive-btn")
    expect(page.locator("#product-description")).to_be_visible()

    # Scanning the same bag again.
    result = scan(page, live_server, EACH_LINE_PART)
    assert result["outcome"] == "product", (
        'a received line was offered for receipt a second time'
    )

    expect(page.locator("#product-description")).to_be_visible()
    expect(page.locator("#confirm-receive-btn")).to_have_count(0)


@pytest.mark.e2e
def test_a_part_number_nothing_was_captured_for_does_not_offer_a_receipt(
    page, live_server, image_host
):
    """The other half of FR-032b: a McMaster-shaped part number the catalog
    has never seen behaves as any unknown free text does."""
    capture_the_order(page, live_server, image_host)

    result = scan(page, live_server, "99999Z999")
    assert result["outcome"] != "receive"

    expect(page.locator("#confirm-receive-btn")).to_have_count(0)
    expect(page.locator("#choose-line")).to_have_count(0)
