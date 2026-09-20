"""E2E: filling in the products an Amazon order created (feature 044, issue #156).

Two harnesses, chosen per journey:

* **The order journeys run the real agent** against the fixture order page, with
  every ``/dp/<ASIN>`` fulfilled by the fixture listing or by a robot-check page.
  Reading each line's listing is the agent's new work, so it is what these drive.
* **The listing journeys post the landing form from the page** rather than
  running the agent on a listing. On this harness the listing is served from the
  application's own loopback origin, so ``_vendor_from_url`` names that host
  rather than "Amazon" (see ``test_product_page_capture.py``) and the listing
  could never match an Amazon product. What these journeys test is the
  confirmation page and what it writes; the agent's listing extraction is
  covered where it lives.

Orders the listing journeys need are seeded through the service, dated today,
because the confirmation page recognizes an order purchase by the ninety-day
window around today's date.
"""

import json
import re

import pytest
from playwright.sync_api import expect

from app.catalog_service import AMAZON_ORDER_VENDOR, AMAZON_VENDOR, CatalogService
from app.models import AMAZON_PAYLOAD_VENDOR, AMAZON_PAYLOAD_VERSION, AmazonOrder
from app.utils.clock import local_now
from tests.e2e.test_amazon_order import (
    LINE_COUNT,
    ORDER_ID,
    capture_order,
    confirm,
    line,
    purchase_rows,
)
from tests.e2e.test_product_page_capture import FIXTURES, LISTING_ROUTE, serve_listing

ASIN = "B0CXYZ1234"
SECOND_ASIN = "B0CXYZ5678"
SEEDED_ORDER = "112-4455667-8899001"


def listing_fields(asin, **overrides):
    """What the agent would read off a listing, as a payload object."""
    listing = {
        "version": 1,
        "source_url": f"https://www.amazon.com/dp/{asin}",
        "vendor_item_id": asin,
        "listing_title": "M3 Socket Head Cap Screws, 100 pack",
        "brand": "Acme Fasteners",
        "description_text": "Alloy steel, black oxide finish.",
        "specifications": [
            {"name": "Thread Size", "value": "M3"},
            {"name": "Length", "value": "10 mm"},
        ],
    }
    listing.update(overrides)
    return listing


def land_listing(page, live_server, asin, **overrides):
    """Post what the extension posts, and wait for the landing to render.

    ``#extension-landing`` only renders on the landing, never on the capture
    page this starts from, so it is a completion signal that cannot be satisfied
    early (pattern C).
    """
    page.goto(f"{live_server.url}/products/capture")
    expect(page.locator("#capture-form")).to_be_visible()
    page.evaluate(
        """([endpoint, fields]) => {
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = endpoint;
            for (const [name, value] of Object.entries(fields)) {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = name;
                input.value = value;
                form.appendChild(input);
            }
            document.body.appendChild(form);
            form.submit();
        }""",
        [
            f"{live_server.url}/api/capture",
            {
                "url": f"https://www.amazon.com/dp/{asin}",
                "listing_title": "M3 Socket Head Cap Screws, 100 pack",
                "listing": json.dumps(listing_fields(asin, **overrides)),
            },
        ],
    )
    expect(page.locator("#extension-landing")).to_be_visible()
    return page


def seed_order_of(live_server, *asins):
    """An Amazon order captured today, each line a new, detail-less product."""
    now = local_now()
    order = AmazonOrder.from_payload({
        "version": AMAZON_PAYLOAD_VERSION,
        "vendor": AMAZON_PAYLOAD_VENDOR,
        "order_number": SEEDED_ORDER,
        "order_date": f"{now:%B} {now.day}, {now:%Y}",
        "source_url": (
            "https://www.amazon.com/your-orders/order-details"
            f"?orderID={SEEDED_ORDER}"
        ),
        "lines": [
            {"asin": asin, "title": f"Item {asin}", "quantity": 1, "unit_price": "8.99"}
            for asin in asins
        ],
    })
    service = CatalogService(live_server.storage)
    service.capture_order_lines(order, AMAZON_ORDER_VENDOR, {
        ln.form_key: {"include": True} for ln in order.lines
    })
    return {
        purchase.vendor_item_id: purchase.product_id
        for purchase in service.find_order_lines_for(AMAZON_VENDOR, SEEDED_ORDER)
    }


def open_order(page, live_server, order_number):
    page.goto(f"{live_server.url}/products/orders/Amazon/{order_number}")
    expect(page.locator("#order-lines")).to_be_visible()
    return page


# --------------------------------------------------------------------------
# US1 -- details without a purchase
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_details_only_fills_a_product_in_without_a_purchase(page, live_server):
    service = CatalogService(live_server.storage)
    product = service.create_product(
        description="M3 Socket Head Cap Screws",
        identifiers=[{"id_type": "VENDOR", "value": ASIN, "vendor": AMAZON_VENDOR}],
    )
    service.record_purchase(product.id, vendor=AMAZON_VENDOR, vendor_item_id=ASIN,
                            quantity=1, unit_price="8.99")

    land_listing(page, live_server, ASIN)
    expect(page.locator("#listing-match")).to_be_visible()
    expect(page.locator("#intent-purchase")).to_be_checked()
    page.check("#intent-details")
    page.click("#capture-btn")

    # The redirect lands after the write, so the product's rows appearing is
    # the whole wait (pattern C).
    expect(page.locator("#product-specifications")).to_contain_text("Thread Size")
    expect(purchase_rows(page, live_server, product.id)).to_have_count(1)


# --------------------------------------------------------------------------
# US2 -- one question after an order capture
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_a_listing_after_its_order_asks_once_and_fills_the_product(page, live_server):
    """SC-001, in a browser: confirm the page as it is first shown."""
    products = seed_order_of(live_server, ASIN)

    land_listing(page, live_server, ASIN)
    expect(page.locator("#order-item-match")).to_be_visible()
    expect(page.locator("#order-item-match")).to_contain_text(SEEDED_ORDER)
    expect(page.locator("#intent-details")).to_be_checked()
    # Negative assertions, only now that the page has established itself.
    expect(page.locator("#duplicate-warning")).to_have_count(0)
    expect(page.locator("#identifier-warning")).to_have_count(0)

    page.click("#capture-btn")

    # Back on the order's page, which now has nothing left to fill in.
    expect(page.locator("#details-progress")).to_contain_text(
        "Every product on this order has its details"
    )
    expect(purchase_rows(page, live_server, products[ASIN])).to_have_count(1)


# --------------------------------------------------------------------------
# US3 -- the order page as a checklist
# --------------------------------------------------------------------------

@pytest.mark.e2e
def test_the_order_page_walks_through_each_product(page, live_server):
    seed_order_of(live_server, ASIN, SECOND_ASIN)

    open_order(page, live_server, SEEDED_ORDER)
    expect(page.locator("#details-progress")).to_contain_text("2 of 2")
    expect(page.locator("a.open-listing")).to_have_count(2)
    expect(page.locator(f'tr.order-line[data-part="{ASIN}"] a.open-listing')).to_have_attribute(
        "href", f"https://www.amazon.com/dp/{ASIN}"
    )

    land_listing(page, live_server, ASIN)
    expect(page.locator("#intent-details")).to_be_checked()
    page.click("#capture-btn")

    expect(page.locator("#details-progress")).to_contain_text("1 of 2")
    expect(page.locator(f'tr.order-line[data-part="{ASIN}"] .details-captured')).to_be_visible()


# --------------------------------------------------------------------------
# US4 -- one order capture reads every listing
# --------------------------------------------------------------------------

def serve_listings_except(page, image_host, unreadable):
    """Every listing readable, except one ASIN, which gets the robot check."""
    listing = (FIXTURES / "amazon_listing.html").read_text().replace(
        "__IMAGE_HOST__", image_host
    )
    robot = (FIXTURES / "amazon_robot_check.html").read_text()
    page.route(
        LISTING_ROUTE,
        lambda route: route.fulfill(
            status=200, content_type="text/html",
            body=robot if unreadable in route.request.url else listing,
        ),
    )


@pytest.mark.e2e
def test_one_order_capture_fills_in_every_product(page, live_server, image_host):
    serve_listing(page, image_host)

    review = capture_order(page, live_server, image_host)
    expect(review.locator(".line-listing-summary")).to_have_count(LINE_COUNT)
    expect(review.locator("#order-page-detail-note")).to_have_attribute(
        "data-listings-read", str(LINE_COUNT)
    )
    # What Werkzeug's per-field limit was raised for (research.md §7): the
    # order field now carries four listings. Recorded in verification.md.
    payload_bytes = len(review.locator("#order-payload").input_value().encode())
    assert payload_bytes < 16 * 1024 * 1024

    confirm(review)
    expect(review.locator("#details-progress")).to_contain_text(
        "Every product on this order has its details"
    )


@pytest.mark.e2e
def test_a_listing_amazon_would_not_serve_falls_back_to_the_checklist(
    page, live_server, image_host
):
    serve_listings_except(page, image_host, "B0TESTAAA2")

    review = capture_order(page, live_server, image_host)
    unread = line(review, "2")
    expect(unread.locator(".details-not-read")).to_be_visible()
    expect(unread.locator(".listing-problem")).to_contain_text("not a listing")
    expect(review.locator(".line-listing-summary")).to_have_count(LINE_COUNT - 1)

    confirm(review)
    expect(review.locator("#details-progress")).to_contain_text(
        f"1 of {LINE_COUNT}"
    )
    expect(
        review.locator('tr.order-line[data-part="B0TESTAAA2"] a.open-listing')
    ).to_be_visible()


@pytest.mark.e2e
def test_recapturing_an_order_fills_in_what_it_created(page, live_server, image_host):
    """FR-030: the repair for an order captured before its listings were read."""
    # First capture with every listing unreadable: the thin products 044 found.
    serve_listings_except(page, image_host, "B0TEST")
    first = confirm(capture_order(page, live_server, image_host))
    expect(first.locator("#details-progress")).to_contain_text(
        f"{LINE_COUNT} of {LINE_COUNT}"
    )

    page.unroute(LISTING_ROUTE)
    serve_listing(page, image_host)
    review = capture_order(page, live_server, image_host)
    expect(review.locator('tr.order-line[data-state="CAPTURED"]')).to_have_count(LINE_COUNT)
    expect(review.locator(".line-listing-summary")).to_have_count(LINE_COUNT)

    confirm(review)
    expect(review.locator("#details-progress")).to_contain_text(
        "Every product on this order has its details"
    )
    expect(review.locator("tr.order-line")).to_have_count(LINE_COUNT)
    assert re.search(r"Details added to \d+ product", review.content())
