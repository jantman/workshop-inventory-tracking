"""The Outstanding Products page (feature 062, issue #200).

Two claims. The list is every purchase not yet received -- from every order and
from none -- with an order's lines together and the oldest order first. And a
receipt from it *is* the order page's bulk receipt without the one-order
restriction: the same effects, and all of the ticked lines or none of them.
"""

from datetime import datetime

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ValidationError

pytestmark = pytest.mark.unit

URL = '/products/outstanding'


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def _line(catalog, description, vendor='Shop A', order='A-1',
          order_date=datetime(2026, 9, 1), quantity=10, product_qty=None, flag=None):
    product = catalog.create_product(description=description)
    if product_qty is not None:
        catalog.set_quantity(product.id, product_qty)
    if flag is not None:
        catalog.set_stock_status(product.id, flag)
    return catalog.record_purchase(
        product.id, vendor, vendor_item_id=description, order_date=order_date,
        quantity=quantity, supplier_order_reference=order,
    )


@pytest.fixture
def lines(catalog):
    """Two orders from two vendors, each with one line already received."""
    a1 = _line(catalog, 'Washer', product_qty=4)
    a2 = _line(catalog, 'Nut', quantity=25, product_qty=0, flag='low')
    a3 = _line(catalog, 'A received')
    b1 = _line(catalog, 'Bolt', vendor='Shop B', order='B-7',
               order_date=datetime(2026, 8, 15), quantity=5)
    b2 = _line(catalog, 'B received', vendor='Shop B', order='B-7',
               order_date=datetime(2026, 8, 15))
    catalog.receive_purchase(a3.id, received_date='2026-09-10')
    catalog.receive_purchase(b2.id, received_date='2026-09-10')
    return {'a1': a1, 'a2': a2, 'a3': a3, 'b1': b1, 'b2': b2}


class TestFindOutstandingPurchases:
    def test_only_outstanding_purchases_from_every_order(self, catalog, lines):
        ids = {p.id for p in catalog.find_outstanding_purchases()}

        assert ids == {lines['a1'].id, lines['a2'].id, lines['b1'].id}

    def test_oldest_order_first_then_undated_then_no_order(self, catalog, lines):
        undated = _line(catalog, 'Undated', vendor='Shop C', order='C-1', order_date=None)
        loose = _line(catalog, 'Loose', order=None, order_date=datetime(2020, 1, 1))
        blank = _line(catalog, 'Blank ref', order='  ', order_date=datetime(2019, 1, 1))

        ordered = [p.id for p in catalog.find_outstanding_purchases()]

        assert ordered[:4] == [lines['b1'].id, lines['a1'].id, lines['a2'].id, undated.id]
        assert set(ordered[4:]) == {loose.id, blank.id}

    def test_products_are_loaded(self, catalog, lines):
        first = catalog.find_outstanding_purchases()[0]

        assert first.product.description == 'Bolt'


class TestReceivePurchases:
    def test_lines_from_two_orders_are_received_together(self, catalog, lines):
        result = catalog.receive_purchases(
            [lines['a1'].id, str(lines['b1'].id)], received_date='2026-10-03')

        assert result == (2, 0)
        assert catalog.get_purchase(lines['a1'].id).received_date == datetime(2026, 10, 3)
        assert catalog.get_purchase(lines['b1'].id).received_date == datetime(2026, 10, 3)
        assert catalog.get_purchase(lines['a2'].id).received_date is None

    def test_counts_rise_dates_stay_and_flags_clear(self, catalog, lines):
        before = catalog.get_product(lines['a1'].product_id).quantity_updated_at

        catalog.receive_purchases([lines['a1'].id, lines['a2'].id])

        washer = catalog.get_product(lines['a1'].product_id)
        nut = catalog.get_product(lines['a2'].product_id)
        assert washer.quantity == 14
        assert washer.quantity_updated_at == before
        assert nut.quantity == 25
        assert nut.stock_status is None
        assert nut.stock_status_updated_at is None

    def test_same_end_state_as_a_single_receipt(self, catalog):
        """SC-003: from this page, from the receipt screen -- indistinguishable."""
        single = _line(catalog, 'Single', quantity=7, product_qty=3, flag='out')
        bulk = _line(catalog, 'Bulk', vendor='Shop B', order='B-9', quantity=7,
                     product_qty=3, flag='out')

        catalog.receive_purchase(single.id, received_date='2026-10-03')
        catalog.receive_purchases([bulk.id], received_date='2026-10-03')

        def snapshot(purchase):
            p = catalog.get_purchase(purchase.id)
            product = catalog.get_product(purchase.product_id)
            return (p.received_date, p.quantity, product.quantity,
                    product.stock_status, product.stock_status_updated_at,
                    product.quantity_updated_at is None)

        assert snapshot(single) == snapshot(bulk)

    def test_a_line_on_no_order_can_be_received(self, catalog):
        loose = _line(catalog, 'Loose', order=None)

        assert catalog.receive_purchases([loose.id]) == (1, 0)

    def test_already_received_lines_are_skipped_untouched(self, catalog, lines):
        result = catalog.receive_purchases(
            [lines['a3'].id, lines['b1'].id], received_date='2026-10-03')

        assert result == (1, 1)
        assert catalog.get_purchase(lines['a3'].id).received_date == datetime(2026, 9, 10)

    def test_a_date_too_early_for_one_line_receives_none(self, catalog, lines):
        # After B-7's order date, before A-1's.
        with pytest.raises(ValidationError):
            catalog.receive_purchases(
                [lines['a1'].id, lines['b1'].id], received_date='2026-08-20')

        assert catalog.get_purchase(lines['a1'].id).received_date is None
        assert catalog.get_purchase(lines['b1'].id).received_date is None
        assert catalog.get_product(lines['a1'].product_id).quantity == 4

    def test_a_purchase_that_no_longer_exists_receives_none(self, catalog, lines):
        with pytest.raises(ValidationError, match='no longer exist'):
            catalog.receive_purchases([lines['a1'].id, 999999])

        assert catalog.get_purchase(lines['a1'].id).received_date is None

    def test_nothing_ticked_is_refused(self, catalog, lines):
        with pytest.raises(ValidationError):
            catalog.receive_purchases([])

    def test_the_order_page_still_refuses_another_orders_line(self, catalog, lines):
        with pytest.raises(ValidationError, match='not on Shop A order A-1'):
            catalog.receive_order_lines('Shop A', 'A-1', [lines['a1'].id, lines['b1'].id])

        assert catalog.get_purchase(lines['a1'].id).received_date is None


class TestThePage:
    def test_lists_outstanding_lines_with_their_orders(self, catalog, client, lines):
        loose = _line(catalog, 'Loose', order=None)

        body = client.get(URL).get_data(as_text=True)

        assert 'id="outstanding-summary"' in body
        assert '4 line(s) outstanding across 2 order(s).' in body
        for key in ('a1', 'a2', 'b1'):
            assert f'name="purchase_id" value="{lines[key].id}"' in body
        assert f'name="purchase_id" value="{loose.id}"' in body
        assert f'name="purchase_id" value="{lines["a3"].id}"' not in body
        assert 'href="/products/orders/Shop%20A/A-1"' in body
        assert 'href="/products/orders/Shop%20B/B-7"' in body
        assert 'class="text-body-secondary no-order"' in body
        assert 'action="/products/outstanding/receive"' in body
        assert 'orderBulkLabelPrintingModal' in body
        assert 'order-bulk-actions.js' in body

    def test_nothing_outstanding_offers_no_actions(self, client):
        body = client.get(URL).get_data(as_text=True)

        assert 'id="nothing-outstanding"' in body
        assert 'order-bulk-toolbar' not in body
        assert 'order-bulk-actions.js' not in body

    def test_the_products_menu_links_here(self, client):
        body = client.get('/products').get_data(as_text=True)

        assert 'href="/products/outstanding"' in body


class TestTheReceiveRoute:
    def test_receives_and_returns_here(self, catalog, client, lines):
        resp = client.post(f'{URL}/receive', data={
            'purchase_id': [str(lines['a1'].id), str(lines['b1'].id)],
            'received_date': '2026-10-03',
        })

        assert resp.status_code == 302
        assert resp.headers['Location'].endswith(URL)
        assert catalog.get_purchase(lines['b1'].id).received_date == datetime(2026, 10, 3)

        body = client.get(URL).get_data(as_text=True)
        assert 'Received 2 line(s).' in body
        assert f'name="purchase_id" value="{lines["a1"].id}"' not in body

    def test_reports_skipped_lines(self, client, lines):
        client.post(f'{URL}/receive', data={
            'purchase_id': [str(lines['a3'].id), str(lines['a2'].id)],
        })

        body = client.get(URL).get_data(as_text=True)
        assert 'Received 1 line(s). 1 already received, skipped.' in body

    def test_a_refusal_is_reported_and_changes_nothing(self, catalog, client, lines):
        resp = client.post(f'{URL}/receive', data={
            'purchase_id': [str(lines['a1'].id)], 'received_date': '2026-08-01',
        })

        assert resp.status_code == 302
        assert catalog.get_purchase(lines['a1'].id).received_date is None
        body = client.get(URL).get_data(as_text=True)
        assert 'Nothing was received' in body
