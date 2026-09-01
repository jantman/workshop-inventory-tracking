"""E2E: deleting a purchase (feature 032, issue #130).

A purchase written in error used to be permanent without shell access to the
database host. Two entry points -- the product page's purchase history (US1) and
the order screen (US2) -- reach one confirmation page.

**Waiting note.** This feature has no `fetch`, no dialog and no JS-rendered
region: every control is a plain link and the deletion is a form POST that
redirects. So every wait here is either a navigation or an `expect()` on a
locator, and none of CLAUDE.md's six trap patterns applies. The one rule that
still binds is the negative-assertion rule: `#purchase-history` and `#order-lines`
are established with `expect()` before anything asserts that a row is *absent*,
because "the row is gone" passes trivially against a page that has not loaded.
"""

from datetime import datetime

import pytest
from playwright.sync_api import expect

from app.catalog_service import CatalogService

ORDER_NUMBER = "111-9281973-9357866"


def seed(live_server, **overrides):
    """A product with one purchase, written straight to the database.

    Directly rather than through the Add Item and Add Purchase forms: the forms
    are not what is under test here, and driving them costs seconds per row.
    """
    service = CatalogService(live_server.storage)
    product = service.create_product(
        description=overrides.pop('description', 'ELECROW ESP32 E-Ink 4.2in')
    )
    fields = {
        'vendor': 'Amazon',
        'vendor_item_id': 'B0G43FCHFX',
        'order_date': datetime(2026, 7, 23),
        'quantity': 1,
        'unit_price': '37.59',
        'supplier_order_reference': ORDER_NUMBER,
    }
    fields.update(overrides)
    purchase = service.record_purchase(product.id, **fields)
    return service, product, purchase


def open_product(page, live_server, product_id):
    page.goto(f"{live_server.url}/products/{product_id}")
    expect(page.locator("#purchase-history")).to_be_visible()
    return page


def open_order(page, live_server, vendor="Amazon", order_number=ORDER_NUMBER):
    page.goto(f"{live_server.url}/products/orders/{vendor}/{order_number}")
    expect(page.locator("#order-lines, #no-lines")).to_be_visible()
    return page


# ---------------------------------------------------------------------------
# User Story 1 -- the product page
# ---------------------------------------------------------------------------


@pytest.mark.e2e
def test_the_purchase_history_offers_a_delete_control(page, live_server):
    _, product, _ = seed(live_server)

    open_product(page, live_server, product.id)

    expect(page.locator(".delete-purchase-btn")).to_have_count(1)


@pytest.mark.e2e
def test_the_confirmation_names_the_purchase_it_is_about_to_delete(page, live_server):
    """FR-003. Two near-identical rows is the case this exists for, so the
    confirmation has to say which one was pressed."""
    service, product, first = seed(live_server)
    service.record_purchase(
        product.id, vendor='eBay', order_date=datetime(2026, 3, 2),
        quantity=4, unit_price='2.50',
    )

    open_product(page, live_server, product.id)
    page.locator(".purchase-row", has_text="eBay").locator(".delete-purchase-btn").click()

    expect(page.locator("#delete-vendor")).to_have_text("eBay")
    expect(page.locator("#delete-quantity")).to_have_text("4")
    expect(page.locator("#delete-unit-price")).to_contain_text("2.50")


@pytest.mark.e2e
def test_the_confirmation_states_both_consequences(page, live_server):
    """FR-004: the two things the operator cannot see from the row."""
    _, product, purchase = seed(live_server)

    page.goto(f"{live_server.url}/purchases/{purchase.id}/delete")

    expect(page.locator("#delete-attachment-count")).to_contain_text("no attached files")
    expect(page.locator("#delete-quantity-notice")).to_contain_text(
        "counted quantity will not change"
    )


@pytest.mark.e2e
def test_cancelling_changes_nothing(page, live_server):
    """FR-002"""
    _, product, purchase = seed(live_server)

    open_product(page, live_server, product.id)
    page.locator(".delete-purchase-btn").click()
    expect(page.locator("#confirm-delete-purchase")).to_be_visible()
    page.locator("#cancel-delete-purchase").click()

    expect(page.locator("#purchase-history")).to_be_visible()
    expect(page.locator(".purchase-row")).to_have_count(1)


@pytest.mark.e2e
def test_one_of_two_purchases_is_deleted_and_the_other_stays(page, live_server):
    """US1 scenario 1, and the recovery path for the duplicate in #129."""
    service, product, _ = seed(live_server)
    service.record_purchase(
        product.id, vendor='eBay', order_date=datetime(2026, 3, 2), quantity=4
    )

    open_product(page, live_server, product.id)
    expect(page.locator(".purchase-row")).to_have_count(2)
    page.locator(".purchase-row", has_text="eBay").locator(".delete-purchase-btn").click()
    page.locator("#confirm-delete-purchase").click()

    # Established before the count is read: an empty table would otherwise
    # satisfy "the eBay row is gone" without the deletion having happened.
    expect(page.locator("#purchase-history")).to_be_visible()
    expect(page.locator(".purchase-row")).to_have_count(1)
    expect(page.locator("#purchase-history")).not_to_contain_text("eBay")
    expect(page.locator("#purchase-history")).to_contain_text("Amazon")


@pytest.mark.e2e
def test_it_says_what_was_removed(page, live_server):
    """FR-008"""
    _, product, _ = seed(live_server)

    open_product(page, live_server, product.id)
    page.locator(".delete-purchase-btn").click()
    page.locator("#confirm-delete-purchase").click()

    expect(page.locator(".alert-success")).to_contain_text("Deleted the Amazon purchase")


@pytest.mark.e2e
def test_the_product_survives_its_last_purchase(page, live_server):
    """FR-005, and the "last purchase of a product" edge case."""
    _, product, _ = seed(live_server)

    open_product(page, live_server, product.id)
    page.locator(".delete-purchase-btn").click()
    page.locator("#confirm-delete-purchase").click()

    expect(page.locator("#purchase-history")).to_be_visible()
    expect(page.locator("#no-purchases")).to_be_visible()
    expect(page.locator("h1, h2, h3")).to_contain_text("ELECROW ESP32 E-Ink 4.2in")


@pytest.mark.e2e
def test_an_outstanding_purchase_stops_being_on_order(page, live_server):
    """FR-009: the derived views lose it too."""
    _, product, _ = seed(live_server)

    open_product(page, live_server, product.id)
    expect(page.locator(".purchase-outstanding")).to_have_count(1)
    page.locator(".delete-purchase-btn").click()
    page.locator("#confirm-delete-purchase").click()

    expect(page.locator("#purchase-history")).to_be_visible()
    expect(page.locator(".purchase-outstanding")).to_have_count(0)
