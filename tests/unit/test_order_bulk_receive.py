"""Receiving several lines of an order at once (feature 060, issue #194).

The claim under test is that a bulk receipt *is* the single receipt, applied to
several lines with nothing amended -- same received date, same count change,
same untouched count date, same cleared manual flag -- and that it happens to
all of the ticked lines or to none of them.
"""

from datetime import datetime

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ValidationError

pytestmark = pytest.mark.unit

VENDOR = 'Some Shop'
ORDER = 'ORDER-60'
ORDER_DATE = datetime(2026, 9, 1, 14, 30)
ORDER_URL = f'/products/orders/Some%20Shop/{ORDER}'


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def _line(catalog, description, quantity=10, order_number=ORDER, product_qty=None,
          flag=None):
    product = catalog.create_product(description=description)
    if product_qty is not None:
        catalog.set_quantity(product.id, product_qty)
    if flag is not None:
        catalog.set_stock_status(product.id, flag)
    return catalog.record_purchase(
        product.id, VENDOR, vendor_item_id=description, order_date=ORDER_DATE,
        quantity=quantity, supplier_order_reference=order_number,
    )


@pytest.fixture
def lines(catalog):
    return [
        _line(catalog, 'Washer', quantity=10, product_qty=4),
        _line(catalog, 'Nut', quantity=25, product_qty=0, flag='low'),
        _line(catalog, 'Bolt', quantity=5),
    ]


def _states(catalog):
    return {p.id: p for p in catalog.find_order_lines_for(VENDOR, ORDER)}


class TestReceiveOrderLines:
    def test_ticked_lines_are_received_on_the_date_and_the_rest_stay_outstanding(
            self, catalog, lines):
        result = catalog.receive_order_lines(
            VENDOR, ORDER, [lines[0].id, lines[1].id], received_date='2026-10-03')

        assert result == (2, 0)
        states = _states(catalog)
        assert states[lines[0].id].received_date == datetime(2026, 10, 3)
        assert states[lines[1].id].received_date == datetime(2026, 10, 3)
        assert states[lines[2].id].received_date is None

    def test_blank_date_means_now(self, catalog, lines):
        catalog.receive_order_lines(VENDOR, ORDER, [lines[2].id], received_date='')

        received = _states(catalog)[lines[2].id].received_date
        assert received is not None and received.date() >= datetime(2026, 1, 1).date()

    def test_ids_arrive_as_form_strings(self, catalog, lines):
        assert catalog.receive_order_lines(VENDOR, ORDER, [str(lines[2].id)]) == (1, 0)

    def test_counts_rise_by_the_ordered_quantity_and_flags_clear(self, catalog, lines):
        before = catalog.get_product(lines[0].product_id).quantity_updated_at

        catalog.receive_order_lines(VENDOR, ORDER, [lines[0].id, lines[1].id])

        washer = catalog.get_product(lines[0].product_id)
        nut = catalog.get_product(lines[1].product_id)
        assert washer.quantity == 14
        assert washer.quantity_updated_at == before
        assert nut.quantity == 25
        assert nut.stock_status is None
        assert nut.stock_status_updated_at is None

    def test_same_end_state_as_a_single_receipt(self, catalog):
        """SC-003: bulk and single, nothing amended, are indistinguishable."""
        single = _line(catalog, 'Single', quantity=7, product_qty=3, flag='out')
        bulk = _line(catalog, 'Bulk', quantity=7, product_qty=3, flag='out')

        catalog.receive_purchase(single.id, received_date='2026-10-03')
        catalog.receive_order_lines(VENDOR, ORDER, [bulk.id], received_date='2026-10-03')

        def snapshot(purchase):
            p = catalog.get_purchase(purchase.id)
            product = catalog.get_product(purchase.product_id)
            return (p.received_date, p.quantity, product.quantity,
                    product.stock_status, product.stock_status_updated_at,
                    product.quantity_updated_at is None)

        assert snapshot(single) == snapshot(bulk)

    def test_already_received_lines_are_skipped_untouched(self, catalog, lines):
        catalog.receive_purchase(lines[0].id, received_date='2026-09-05')

        result = catalog.receive_order_lines(
            VENDOR, ORDER, [lines[0].id, lines[2].id], received_date='2026-10-03')

        assert result == (1, 1)
        assert _states(catalog)[lines[0].id].received_date == datetime(2026, 9, 5)
        assert catalog.get_product(lines[0].product_id).quantity == 14

    def test_a_date_before_the_order_receives_nothing(self, catalog, lines):
        with pytest.raises(ValidationError):
            catalog.receive_order_lines(
                VENDOR, ORDER, [lines[0].id, lines[2].id], received_date='2026-08-01')

        states = _states(catalog)
        assert states[lines[0].id].received_date is None
        assert states[lines[2].id].received_date is None
        assert catalog.get_product(lines[0].product_id).quantity == 4

    def test_a_line_of_another_order_receives_nothing(self, catalog, lines):
        other = _line(catalog, 'Elsewhere', order_number='OTHER-1')

        with pytest.raises(ValidationError):
            catalog.receive_order_lines(VENDOR, ORDER, [lines[0].id, other.id])

        assert _states(catalog)[lines[0].id].received_date is None
        assert catalog.get_purchase(other.id).received_date is None

    def test_nothing_ticked_is_refused(self, catalog, lines):
        with pytest.raises(ValidationError):
            catalog.receive_order_lines(VENDOR, ORDER, [])

    def test_an_unreadable_date_is_refused(self, catalog, lines):
        with pytest.raises(ValidationError):
            catalog.receive_order_lines(VENDOR, ORDER, [lines[0].id], received_date='soon')


class TestTheRoute:
    def test_receives_and_returns_to_the_order(self, catalog, client, lines):
        resp = client.post(f'{ORDER_URL}/receive', data={
            'purchase_id': [str(lines[0].id), str(lines[1].id)],
            'received_date': '2026-10-03',
        })

        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(ORDER_URL)
        assert _states(catalog)[lines[0].id].received_date == datetime(2026, 10, 3)

        body = client.get(ORDER_URL).get_data(as_text=True)
        assert 'Received 2 line(s).' in body

    def test_reports_skipped_lines(self, catalog, client, lines):
        catalog.receive_purchase(lines[0].id)

        client.post(f'{ORDER_URL}/receive', data={
            'purchase_id': [str(lines[0].id), str(lines[2].id)],
        })

        body = client.get(ORDER_URL).get_data(as_text=True)
        assert 'Received 1 line(s). 1 already received, skipped.' in body

    def test_only_received_lines_ticked_says_so(self, catalog, client, lines):
        catalog.receive_purchase(lines[0].id)

        client.post(f'{ORDER_URL}/receive', data={'purchase_id': [str(lines[0].id)]})

        body = client.get(ORDER_URL).get_data(as_text=True)
        assert 'Nothing to receive' in body

    def test_a_refusal_is_reported_and_changes_nothing(self, catalog, client, lines):
        resp = client.post(f'{ORDER_URL}/receive', data={
            'purchase_id': [str(lines[0].id)], 'received_date': '2026-08-01',
        })

        assert resp.status_code == 302
        assert _states(catalog)[lines[0].id].received_date is None
        body = client.get(ORDER_URL).get_data(as_text=True)
        assert 'Nothing was received' in body


class TestThePage:
    def test_every_line_with_a_product_has_a_checkbox(self, client, lines):
        body = client.get(ORDER_URL).get_data(as_text=True)

        assert 'id="order-bulk-toolbar"' in body
        assert 'id="order-select-all"' in body
        for purchase in lines:
            assert f'name="purchase_id" value="{purchase.id}"' in body
        assert 'orderBulkLabelPrintingModal' in body

    def test_an_order_with_no_lines_offers_no_bulk_actions(self, client):
        body = client.get('/products/orders/Some%20Shop/NOTHING').get_data(as_text=True)

        assert 'order-bulk-toolbar' not in body
        assert 'order-bulk-actions.js' not in body
