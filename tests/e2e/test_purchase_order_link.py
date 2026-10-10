"""E2E: the product page's purchase history links to the order (issue #203).

**Waiting note.** No `fetch` and no JS-rendered region: the link is plain
server-rendered HTML, so the only waits are navigations and `expect()` on
locators. `#purchase-history` is established with `expect()` before the
negative assertion, which would otherwise pass against an unloaded page.
"""

from datetime import datetime

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService

ORDER_NUMBER = "111-9281973-9357866"


def seed(live_server, **purchase_fields):
    service = CatalogService(live_server.storage)
    product = service.create_product(description='ELECROW ESP32 E-Ink 4.2in')
    service.record_purchase(
        product.id, vendor='Amazon', order_date=datetime(2026, 7, 23),
        quantity=1, unit_price='37.59', **purchase_fields,
    )
    return product


@pytest.mark.e2e
def test_following_the_link_reaches_the_order(page, live_server):
    product = seed(live_server, supplier_order_reference=ORDER_NUMBER)

    page.goto(f"{live_server.url}/products/{product.id}")
    link = page.locator("#purchase-history .purchase-order-link")
    expect(link).to_have_text(f"Order {ORDER_NUMBER}")
    link.click()

    expect(page.locator("#order-lines")).to_contain_text(
        'ELECROW ESP32 E-Ink 4.2in'
    )
    expect(page).to_have_url(
        f"{live_server.url}/products/orders/Amazon/{ORDER_NUMBER}"
    )


@pytest.mark.e2e
def test_a_purchase_with_no_order_has_no_link(page, live_server):
    product = seed(live_server)

    page.goto(f"{live_server.url}/products/{product.id}")
    expect(page.locator("#purchase-history .purchase-row")).to_have_count(1)
    expect(page.locator("#purchase-history .purchase-order-link")).to_have_count(0)
