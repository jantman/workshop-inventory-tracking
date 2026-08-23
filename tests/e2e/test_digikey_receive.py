"""
E2E tests for receiving a DigiKey order by scanning a bag (feature 024, US2).

The scan is delivered through the same ``/api/scan`` POST the wedge makes and
then followed, exactly as ``test_ecia_scan.py`` does -- driving Ctrl-key events
for GS and RS through Playwright would test the browser's keyboard model more
than this feature.

The label here is the one pasted into issue #108, with its separators restored.
Its values agree with the recorded order field for field: ``1K`` is the sales
order, ``Q`` is the quantity, ``4L`` is the country of origin.

Waiting: the scan box fires a ``fetch`` and then navigates on ``data.url``, so a
click returning says nothing. Every assertion here waits on the destination
page's own content.
"""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_digikey_order import (  # noqa: F401 -- fixtures
    SALES_ORDER,
    digikey_api,
    review_order,
)

RS, GS, EOT = "\x1e", "\x1d", "\x04"


def bag_label(digikey_part_number='1866-3032-ND', mpn='IRM-10-5',
              sales_order=SALES_ORDER, quantity='5'):
    return (
        "[)>" + RS + "06" + GS
        + f"P{digikey_part_number}" + GS
        + f"1P{mpn}" + GS
        + f"1K{sales_order}" + GS
        + "10K130599231" + GS
        + f"Q{quantity}" + GS
        + "4LCN"
        + RS + EOT
    )


def capture_the_order(page, live_server):
    """Capture the whole recorded order and land on its order screen."""
    review_order(page, live_server)
    expect(page.locator('.order-line')).to_have_count(2)
    page.click('#confirm-capture')
    expect(page.locator('#order-progress')).to_contain_text('2 of 2 still outstanding')


def scan(page, live_server, label):
    """Resolve a scan and follow where it says to go, as the scan box does."""
    result = page.evaluate(
        """async (scan) => {
            const r = await fetch('/api/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scan: scan })
            });
            return await r.json();
        }""",
        label,
    )
    page.goto(f"{live_server.url}{result['url']}")
    return result


@pytest.mark.e2e
def test_scanning_a_bag_lands_on_that_lines_receipt(page, live_server, digikey_api):
    """FR-019, FR-020, SC-004. One scan, the right line, the label's own quantity."""
    capture_the_order(page, live_server)

    result = scan(page, live_server, bag_label())
    assert result['outcome'] == 'receive'

    # The receive screen for that line, not the product page and not a draft.
    expect(page.locator('#quantity')).to_have_value('5')
    expect(page.locator('body')).to_contain_text('AC/DC CONVERTER 5V 10W')


@pytest.mark.e2e
def test_receiving_marks_the_line_received(page, live_server, digikey_api):
    """FR-021. And the order screen says one is left."""
    capture_the_order(page, live_server)
    scan(page, live_server, bag_label())

    expect(page.locator('#quantity')).to_have_value('5')
    page.click('button[type="submit"]')

    # Receiving redirects to the product; go to the order to see the progress.
    page.goto(f"{live_server.url}/products/digikey/orders/{SALES_ORDER}")
    expect(page.locator('#order-progress')).to_contain_text('1 of 2 still outstanding')
    expect(page.locator('.order-line[data-outstanding="false"]')).to_have_count(1)


@pytest.mark.e2e
def test_scanning_the_same_bag_twice_receives_nothing_twice(page, live_server, digikey_api):
    """FR-023."""
    capture_the_order(page, live_server)
    scan(page, live_server, bag_label())
    expect(page.locator('#quantity')).to_have_value('5')
    page.click('button[type="submit"]')
    expect(page.locator('h2')).to_be_visible()

    result = scan(page, live_server, bag_label())
    assert result['outcome'] == 'receive'
    # The order screen, saying so -- not a second receipt.
    expect(page.locator('#order-progress')).to_contain_text('1 of 2 still outstanding')
    expect(page.locator('.order-line[data-part="1866-3032-ND"]')).to_contain_text('received')


@pytest.mark.e2e
def test_receiving_the_last_line_completes_the_order(page, live_server, digikey_api):
    """FR-018, SC-007."""
    capture_the_order(page, live_server)

    for part, mpn in (('1866-3032-ND', 'IRM-10-5'), ('1866-3027-ND', 'IRM-05-5')):
        scan(page, live_server, bag_label(digikey_part_number=part, mpn=mpn))
        expect(page.locator('#quantity')).to_have_value('5')
        page.click('button[type="submit"]')
        expect(page.locator('h2')).to_be_visible()

    page.goto(f"{live_server.url}/products/digikey/orders/{SALES_ORDER}")
    expect(page.locator('#order-progress')).to_contain_text('All 2 line(s) received')
    expect(page.locator('.order-line[data-outstanding="true"]')).to_have_count(0)


@pytest.mark.e2e
def test_receiving_a_line_by_hand_from_the_order_screen(page, live_server, digikey_api):
    """FR-022. For a bag whose label will not read."""
    capture_the_order(page, live_server)

    page.locator('.order-line[data-part="1866-3027-ND"] .receive-line').click()
    expect(page.locator('#quantity')).to_have_value('5')
    page.click('button[type="submit"]')

    page.goto(f"{live_server.url}/products/digikey/orders/{SALES_ORDER}")
    expect(page.locator('#order-progress')).to_contain_text('1 of 2 still outstanding')


@pytest.mark.e2e
def test_a_bag_from_an_uncaptured_order_behaves_as_before(page, live_server, digikey_api):
    """FR-025. The pre-existing behaviour, unchanged."""
    capture_the_order(page, live_server)

    result = scan(page, live_server, bag_label(sales_order='999999999'))
    assert result['outcome'] == 'product'
    # The part is cataloged, so its product opens -- exactly as it did before 024.
    expect(page.locator('body')).to_contain_text('AC/DC CONVERTER 5V 10W')


@pytest.mark.e2e
def test_a_part_the_order_does_not_contain_behaves_as_before(page, live_server, digikey_api):
    """FR-024."""
    capture_the_order(page, live_server)

    result = scan(page, live_server, bag_label(
        digikey_part_number='296-1234-5-ND', mpn='LM358N'
    ))
    assert result['outcome'] == 'create'
    expect(page.locator('#identifier_value')).to_have_value('LM358N')
