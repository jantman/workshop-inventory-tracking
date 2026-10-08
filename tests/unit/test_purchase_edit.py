"""
Unit tests for editing a purchase and an order (feature 061, issue #192).

A capture that got something wrong used to be fixable only in the database or
by deleting the purchase and recording it again by hand -- which lost the order
line it came from. These cover the corrections and their boundaries: the
product's count never moves, nothing is half-written, and an order line or an
order number is never silently shared.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ValidationError

ORDER = '111-9281973-9357866'


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def product(service):
    product = service.create_product(description='ELECROW ESP32 E-Ink 4.2in')
    return service.set_quantity(product.id, 5)


@pytest.fixture
def purchase(service, product):
    """A received order line, as a capture would leave it."""
    return service.record_purchase(
        product.id,
        vendor='Amazon',
        vendor_item_id='B0G43FCHFX',
        order_date=datetime(2026, 7, 23, 14, 30),
        received_date=datetime(2026, 7, 25, 9, 0),
        quantity=1,
        unit_price='13.23',
        supplier_order_reference=ORDER,
    )


def line(service, purchase, number):
    """Give a purchase an order line number, as order capture does."""
    with service._session() as session:
        from app.database import Purchase
        session.query(Purchase).filter(Purchase.id == purchase.id).update(
            {'order_line_number': number}
        )


class TestUpdatePurchase:
    def test_it_corrects_quantity_price_and_pack(self, service, purchase):
        updated = service.update_purchase(
            purchase.id, quantity='100', unit_price='0.13',
            pack_size='100', pack_price='13.23',
        )

        assert updated.quantity == 100
        assert updated.unit_price == Decimal('0.13')
        assert updated.pack_size == 100
        assert updated.pack_price == Decimal('13.23')

    def test_absent_fields_are_left_alone(self, service, purchase):
        updated = service.update_purchase(purchase.id, notes='checked')

        assert updated.notes == 'checked'
        assert updated.vendor_item_id == 'B0G43FCHFX'
        assert updated.quantity == 1
        assert updated.received_date == datetime(2026, 7, 25, 9, 0)

    def test_blank_clears_a_field(self, service, purchase):
        updated = service.update_purchase(purchase.id, vendor_item_id='', unit_price='')

        assert updated.vendor_item_id is None
        assert updated.unit_price is None

    def test_an_unknown_purchase_is_none(self, service):
        assert service.update_purchase(999999, notes='x') is None

    def test_vendor_cannot_be_cleared(self, service, purchase):
        with pytest.raises(ValidationError):
            service.update_purchase(purchase.id, vendor='  ')

    @pytest.mark.parametrize('fields', [
        {'quantity': '0'},
        {'quantity': 'many'},
        {'unit_price': '-1'},
        {'unit_price': 'cheap'},
        {'pack_size': '1', 'pack_price': '5'},
        {'pack_size': '10', 'pack_price': ''},
        {'pack_size': '', 'pack_price': '5'},
        {'order_line_number': '0'},
        {'order_date': 'yesterday'},
        {'received_date': '2026-07-20'},
    ])
    def test_a_refusal_writes_nothing(self, service, purchase, fields):
        with pytest.raises(ValidationError):
            service.update_purchase(purchase.id, notes='should not land', **fields)

        stored = service.get_purchase(purchase.id)
        assert stored.notes is None
        assert stored.quantity == 1
        assert stored.unit_price == Decimal('13.23')

    def test_a_float_price_is_refused(self, service, purchase):
        with pytest.raises(ValidationError):
            service.update_purchase(purchase.id, unit_price=0.13)

    def test_both_pack_fields_blank_clears_the_pack(self, service, purchase):
        service.update_purchase(purchase.id, pack_size='100', pack_price='13.23')

        updated = service.update_purchase(purchase.id, pack_size='', pack_price='')

        assert updated.pack_size is None
        assert updated.pack_price is None

    def test_an_unchanged_date_keeps_its_time(self, service, purchase):
        """R7: the form shows a date; re-saving it must not truncate the time"""
        updated = service.update_purchase(
            purchase.id, order_date='2026-07-23', received_date='2026-07-25'
        )

        assert updated.order_date == datetime(2026, 7, 23, 14, 30)
        assert updated.received_date == datetime(2026, 7, 25, 9, 0)

    def test_a_changed_date_is_the_new_day(self, service, purchase):
        updated = service.update_purchase(purchase.id, order_date='2026-07-20')

        assert updated.order_date == datetime(2026, 7, 20)

    def test_a_received_date_can_be_corrected(self, service, purchase):
        updated = service.update_purchase(purchase.id, received_date='2026-07-27')

        assert updated.received_date == datetime(2026, 7, 27)

    def test_clearing_the_received_date_puts_it_back_on_order(self, service, purchase):
        updated = service.update_purchase(purchase.id, received_date='')

        assert updated.is_outstanding

    def test_an_outstanding_purchase_is_not_received_by_an_edit(self, service, product):
        """R2: receiving is what adds to a count; the Receive screen does it"""
        outstanding = service.record_purchase(product.id, vendor='Amazon', quantity=3)

        with pytest.raises(ValidationError):
            service.update_purchase(outstanding.id, received_date='2026-08-01')

        assert service.get_purchase(outstanding.id).is_outstanding

    def test_an_outstanding_purchase_with_no_received_date_saves(self, service, product):
        outstanding = service.record_purchase(product.id, vendor='Amazon', quantity=3)

        updated = service.update_purchase(outstanding.id, received_date='', quantity='4')

        assert updated.quantity == 4
        assert updated.is_outstanding

    @pytest.mark.parametrize('fields', [
        {'quantity': '100'},
        {'received_date': ''},
        {'received_date': '2026-08-01'},
    ])
    def test_the_product_count_never_moves(self, service, product, purchase, fields):
        """FR-007, SC-004"""
        before = service.get_product(product.id)

        service.update_purchase(purchase.id, **fields)

        after = service.get_product(product.id)
        assert after.quantity == 5
        assert after.quantity_updated_at == before.quantity_updated_at
        assert after.stock_status == before.stock_status

    def test_fields_the_form_does_not_show_are_kept(self, service, purchase):
        """FR-008"""
        from app.database import Purchase
        with service._session() as session:
            session.query(Purchase).filter(Purchase.id == purchase.id).update(
                {'vendor_order_id': 'mc-123'}
            )

        updated = service.update_purchase(purchase.id, notes='x')

        assert updated.vendor_order_id == 'mc-123'
        assert updated.product_id == purchase.product_id


class TestReattachingToAnOrder:
    """US2: a purchase recorded by hand put back on the order it belongs to."""

    def test_setting_the_order_number_puts_it_on_the_order(self, service, product, purchase):
        hand = service.record_purchase(product.id, vendor='Amazon', quantity=2)

        service.update_purchase(hand.id, supplier_order_reference=ORDER, order_line_number='2')

        lines = service.find_order_lines_for('Amazon', ORDER)
        assert [p.id for p in lines] == [purchase.id, hand.id]
        assert lines[1].order_line_number == 2

    def test_changing_the_number_moves_it_between_orders(self, service, product, purchase):
        service.update_purchase(purchase.id, supplier_order_reference='OTHER-1')

        assert service.find_order_lines_for('Amazon', ORDER) == []
        assert len(service.find_order_lines_for('Amazon', 'OTHER-1')) == 1

    def test_a_taken_line_number_is_refused(self, service, product, purchase):
        line(service, purchase, 1)
        hand = service.record_purchase(product.id, vendor='Amazon', quantity=2)

        with pytest.raises(ValidationError, match='already another purchase'):
            service.update_purchase(
                hand.id, supplier_order_reference=ORDER, order_line_number='1'
            )

        assert service.get_purchase(hand.id).supplier_order_reference is None

    def test_the_same_number_on_another_vendors_order_is_fine(self, service, product, purchase):
        line(service, purchase, 1)
        other = service.record_purchase(
            product.id, vendor='eBay', supplier_order_reference=ORDER
        )

        updated = service.update_purchase(other.id, order_line_number='1')

        assert updated.order_line_number == 1

    def test_an_unchanged_duplicate_does_not_block_other_edits(self, service, product, purchase):
        """R5: a pre-existing clash is not re-litigated on every save"""
        line(service, purchase, 1)
        twin = service.record_purchase(
            product.id, vendor='Amazon', supplier_order_reference=ORDER
        )
        line(service, twin, 1)

        updated = service.update_purchase(twin.id, unit_price='9.99', order_line_number='1')

        assert updated.unit_price == Decimal('9.99')


class TestUpdateOrder:
    @pytest.fixture
    def order(self, service, product, purchase):
        second = service.record_purchase(
            product.id, vendor='Amazon', supplier_order_reference=ORDER,
            order_date=datetime(2026, 7, 23, 14, 30), quantity=2,
        )
        third = service.record_purchase(
            product.id, vendor='Amazon', supplier_order_reference=ORDER,
            order_date=datetime(2026, 7, 23, 14, 30), quantity=3,
        )
        return [purchase, second, third]

    def test_it_updates_every_line(self, service, order):
        count = service.update_order(
            'Amazon', ORDER, 'NEW-1', order_date='2026-07-22', order_reference='PO-7'
        )

        assert count == 3
        lines = service.find_order_lines_for('Amazon', 'NEW-1')
        assert len(lines) == 3
        assert {p.order_date for p in lines} == {datetime(2026, 7, 22)}
        assert {p.order_reference for p in lines} == {'PO-7'}
        assert service.find_order_lines_for('Amazon', ORDER) == []

    def test_an_unchanged_date_keeps_each_lines_time(self, service, order):
        service.update_order('Amazon', ORDER, ORDER, order_date='2026-07-23')

        lines = service.find_order_lines_for('Amazon', ORDER)
        assert {p.order_date for p in lines} == {datetime(2026, 7, 23, 14, 30)}

    def test_the_number_is_required(self, service, order):
        with pytest.raises(ValidationError):
            service.update_order('Amazon', ORDER, '  ')

    def test_it_never_merges_into_another_order(self, service, product, order):
        service.record_purchase(product.id, vendor='Amazon', supplier_order_reference='TAKEN')

        with pytest.raises(ValidationError, match='already exists'):
            service.update_order('Amazon', ORDER, 'TAKEN')

        assert len(service.find_order_lines_for('Amazon', ORDER)) == 3

    def test_another_vendors_order_of_that_number_is_no_conflict(self, service, product, order):
        service.record_purchase(product.id, vendor='eBay', supplier_order_reference='SHARED')

        assert service.update_order('Amazon', ORDER, 'SHARED') == 3

    def test_a_date_after_a_receipt_changes_no_line(self, service, order):
        """FR-012, FR-014: all or nothing"""
        with pytest.raises(ValidationError):
            service.update_order('Amazon', ORDER, 'NEW-1', order_date='2026-07-30')

        lines = service.find_order_lines_for('Amazon', ORDER)
        assert len(lines) == 3
        assert {p.order_date for p in lines} == {datetime(2026, 7, 23, 14, 30)}

    def test_an_order_with_no_lines_is_zero(self, service):
        assert service.update_order('Amazon', 'NOTHING', 'X') == 0


class TestThePurchaseEditPage:
    def test_it_is_prefilled(self, client, purchase):
        body = client.get(f'/purchases/{purchase.id}/edit').data.decode()

        assert 'value="Amazon"' in body
        assert 'value="B0G43FCHFX"' in body
        assert 'value="13.23"' in body
        assert 'value="2026-07-23"' in body
        assert 'value="2026-07-25"' in body
        assert f'value="{ORDER}"' in body

    def test_an_outstanding_purchase_offers_receive_not_a_date(self, client, service, product):
        outstanding = service.record_purchase(product.id, vendor='Amazon')

        body = client.get(f'/purchases/{outstanding.id}/edit').data.decode()

        assert 'id="received_date"' not in body
        assert f'/purchases/{outstanding.id}/receive' in body

    def test_saving_returns_to_the_product(self, client, service, product, purchase):
        response = client.post(
            f'/purchases/{purchase.id}/edit',
            data={'vendor': 'Amazon', 'quantity': '100', 'unit_price': '0.13'},
        )

        assert response.status_code == 302
        assert response.headers['Location'].endswith(f'/products/{product.id}')
        assert service.get_purchase(purchase.id).quantity == 100

    def test_saving_from_the_order_returns_to_the_order(self, client, purchase):
        response = client.post(
            f'/purchases/{purchase.id}/edit',
            data={'vendor': 'Amazon', 'supplier_order_reference': ORDER, 'return_to': 'order'},
        )

        assert f'/products/orders/Amazon/{ORDER}' in response.headers['Location']

    def test_a_move_lands_on_the_new_order(self, client, purchase):
        response = client.post(
            f'/purchases/{purchase.id}/edit',
            data={'vendor': 'Amazon', 'supplier_order_reference': 'NEW-9', 'return_to': 'order'},
        )

        assert '/products/orders/Amazon/NEW-9' in response.headers['Location']

    def test_a_refusal_keeps_what_was_typed(self, client, service, purchase):
        response = client.post(
            f'/purchases/{purchase.id}/edit',
            data={'vendor': 'Amazon', 'quantity': '0', 'notes': 'typed this'},
        )

        body = response.data.decode()
        assert response.status_code == 200
        assert 'greater than zero' in body
        assert 'typed this' in body
        assert service.get_purchase(purchase.id).notes is None

    def test_an_unknown_purchase_is_reported(self, client):
        response = client.get('/purchases/999999/edit', follow_redirects=True)

        assert b'not found' in response.data

    def test_both_listings_link_to_it(self, client, product, purchase):
        detail = client.get(f'/products/{product.id}').data.decode()
        order = client.get(f'/products/orders/Amazon/{ORDER}').data.decode()

        assert f'/purchases/{purchase.id}/edit' in detail
        assert f'/purchases/{purchase.id}/edit?return_to=order' in order


class TestTheOrderEditPage:
    def test_the_order_page_links_to_it(self, client, purchase):
        body = client.get(f'/products/orders/Amazon/{ORDER}').data.decode()

        assert f'/products/orders/Amazon/{ORDER}/edit' in body

    def test_it_is_prefilled(self, client, purchase):
        body = client.get(f'/products/orders/Amazon/{ORDER}/edit').data.decode()

        assert f'value="{ORDER}"' in body
        assert 'value="2026-07-23"' in body
        assert 'order-dates-differ' not in body

    def test_it_says_when_lines_disagree(self, client, service, product, purchase):
        service.record_purchase(
            product.id, vendor='Amazon', supplier_order_reference=ORDER,
            order_date=datetime(2026, 7, 1),
        )

        body = client.get(f'/products/orders/Amazon/{ORDER}/edit').data.decode()

        assert 'order-dates-differ' in body

    def test_saving_lands_on_the_new_address(self, client, service, purchase):
        response = client.post(
            f'/products/orders/Amazon/{ORDER}/edit',
            data={'order_number': 'NEW-1', 'order_date': '2026-07-22', 'order_reference': ''},
        )

        assert response.status_code == 302
        assert response.headers['Location'].endswith('/products/orders/Amazon/NEW-1')
        assert service.get_purchase(purchase.id).supplier_order_reference == 'NEW-1'

    def test_a_refusal_keeps_what_was_typed(self, client, service, product, purchase):
        service.record_purchase(product.id, vendor='Amazon', supplier_order_reference='TAKEN')

        response = client.post(
            f'/products/orders/Amazon/{ORDER}/edit',
            data={'order_number': 'TAKEN', 'order_date': '2026-07-23', 'order_reference': 'PO-9'},
        )

        body = response.data.decode()
        assert response.status_code == 200
        assert 'already exists' in body
        assert 'value="PO-9"' in body
        assert service.get_purchase(purchase.id).supplier_order_reference == ORDER

    def test_an_order_with_no_lines_is_reported(self, client):
        response = client.get('/products/orders/Amazon/NOTHING/edit', follow_redirects=True)

        assert b'No Amazon order NOTHING' in response.data
