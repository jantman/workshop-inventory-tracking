"""Receiving a line from the order screen (feature 029, US2).

Amazon is why this story exists. A DigiKey bag label names its sales order *and*
its part; a McMaster bag names the part. **An Amazon package names neither** --
and a product created from an order line carries no barcode either, because an
order page has none to read. So for Amazon the order screen is not a progress
display, it is where the work is done.

What is asserted here is that receiving from that screen is the *same*
receiving: it routes to the receipt that already exists, and the effects on the
product are the ones ``receive_purchase`` has always had. There is deliberately
no second receiving implementation to test.
"""

import pytest

from app.catalog_service import AMAZON_ORDER_VENDOR, AMAZON_VENDOR, CatalogService
from app.models import AMAZON_PAYLOAD_VENDOR, AMAZON_PAYLOAD_VERSION, AmazonOrder

pytestmark = pytest.mark.unit

ORDER_NUMBER = '111-2223334-5556667'


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def captured(catalog):
    """One captured two-line Amazon order."""
    order = AmazonOrder.from_payload({
        'version': AMAZON_PAYLOAD_VERSION,
        'vendor': AMAZON_PAYLOAD_VENDOR,
        'order_number': ORDER_NUMBER,
        'order_date': 'August 22, 2026',
        'lines': [
            {'asin': 'B0TESTAAA1', 'title': 'Digital Calipers', 'unit_price': '9.99'},
            {'asin': 'B0TESTAAA2', 'title': 'Heat Shrink Kit',
             'quantity': 3, 'unit_price': '13.95'},
        ],
    })
    catalog.capture_order_lines(
        order, AMAZON_ORDER_VENDOR,
        {line.form_key: {'include': True} for line in order.lines},
    )
    return catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)


class TestTheOrderScreen:
    def test_offers_a_receipt_for_every_outstanding_line(self, client, captured):
        body = client.get(f'/products/orders/Amazon/{ORDER_NUMBER}').get_data(as_text=True)

        for purchase in captured:
            assert f'/purchases/{purchase.id}/receive' in body

    def test_says_how_many_are_still_outstanding(self, client, captured):
        body = client.get(f'/products/orders/Amazon/{ORDER_NUMBER}').get_data(as_text=True)

        assert 'outstanding-count' in body
        assert '2 of 2' in body

    def test_a_received_line_offers_no_second_receipt(self, catalog, client, captured):
        """FR-031. Nothing is received twice."""
        catalog.receive_purchase(captured[0].id, quantity=1)

        body = client.get(f'/products/orders/Amazon/{ORDER_NUMBER}').get_data(as_text=True)

        assert f'/purchases/{captured[0].id}/receive' not in body
        assert f'/purchases/{captured[1].id}/receive' in body
        assert '1 of 2' in body

    def test_an_order_number_naming_nothing_is_not_a_404(self, client):
        """FR-032. Nothing dead-ends."""
        resp = client.get('/products/orders/Amazon/111-0000000-0000000')

        assert resp.status_code == 200
        assert 'not-captured' in resp.get_data(as_text=True)

    def test_a_vendor_no_capture_flow_knows_still_renders(self, client):
        """A purchase can carry a vendor recorded by hand. It must not 500."""
        resp = client.get('/products/orders/Some%20Shop/ORDER-1')

        assert resp.status_code == 200


class TestReceivingHasTheSameEffectAsAnywhereElse:
    def test_the_purchase_is_recorded_received(self, catalog, captured):
        catalog.receive_purchase(captured[0].id, quantity=1)

        lines = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)
        assert lines[0].received_date is not None
        assert lines[1].received_date is None

    def test_a_counted_products_quantity_rises_by_what_arrived(self, catalog, captured):
        """The received quantity, not the ordered one -- Amazon ships short."""
        product_id = captured[1].product_id
        catalog.set_quantity(product_id, 10)

        catalog.receive_purchase(captured[1].id, quantity=2)

        assert catalog.get_product(product_id).quantity == 12

    def test_the_amended_quantity_is_what_is_recorded(self, catalog, captured):
        catalog.receive_purchase(captured[1].id, quantity=2)

        lines = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)
        assert lines[1].quantity == 2

    def test_the_remaining_line_stays_outstanding(self, catalog, captured):
        catalog.receive_purchase(captured[0].id, quantity=1)

        orders = [
            order for order in catalog.find_captured_orders()
            if order.order_number == ORDER_NUMBER
        ]
        assert orders[0].outstanding_count == 1
        assert orders[0].is_complete is False

    def test_receiving_everything_completes_the_order(self, catalog, captured):
        for purchase in captured:
            catalog.receive_purchase(purchase.id, quantity=1)

        orders = [
            order for order in catalog.find_captured_orders()
            if order.order_number == ORDER_NUMBER
        ]
        assert orders[0].is_complete is True
