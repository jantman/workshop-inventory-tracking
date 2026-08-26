"""The captured-orders list (feature 029, US3).

What this covers is the *derived query*, because that is where the feature's one
real claim lives: an order is its purchases, and the list is worked out from them
each time rather than stored. There is no orders table, so there is nothing to
fall out of step -- and the tests that matter are the ones that would catch a
table creeping in: grouping, counting, and what happens to a purchase that
belongs to no order at all.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.catalog_service import AMAZON_VENDOR, CatalogService, DIGIKEY_VENDOR, MCMASTER_VENDOR
from app.database import Product, Purchase

pytestmark = pytest.mark.unit


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def seed(catalog, rows):
    """Write purchases directly.

    Straight to the session rather than through a capture: this is a test of the
    query, and driving three vendors' capture flows to reach it would be testing
    those instead.
    """
    with catalog._session() as session:
        for row in rows:
            product = Product(description=row.pop('description', 'A thing'))
            session.add(product)
            session.flush()
            session.add(Purchase(product_id=product.id, **row))


class TestGrouping:
    def test_one_order_per_vendor_and_number(self, catalog):
        seed(catalog, [
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='100882558',
                 order_date=datetime(2026, 8, 1), quantity=2),
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='100882558',
                 order_date=datetime(2026, 8, 1), quantity=5),
            dict(vendor=MCMASTER_VENDOR, supplier_order_reference='0812SMITH',
                 order_date=datetime(2026, 8, 2), quantity=1),
        ])

        orders = catalog.find_captured_orders()

        assert len(orders) == 2
        assert {(o.vendor, o.order_number) for o in orders} == {
            (DIGIKEY_VENDOR, '100882558'),
            (MCMASTER_VENDOR, '0812SMITH'),
        }

    def test_the_same_number_at_two_vendors_is_two_orders(self, catalog):
        """Nothing says two vendors cannot both use the number 1000."""
        seed(catalog, [
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='1000'),
            dict(vendor=AMAZON_VENDOR, supplier_order_reference='1000'),
        ])

        assert len(catalog.find_captured_orders()) == 2

    def test_the_line_count_is_the_number_of_purchases(self, catalog):
        seed(catalog, [
            dict(vendor=AMAZON_VENDOR, supplier_order_reference='111-2223334-5556667')
            for _ in range(4)
        ])

        assert catalog.find_captured_orders()[0].line_count == 4


class TestOutstanding:
    def test_outstanding_counts_only_unreceived_lines(self, catalog):
        seed(catalog, [
            dict(vendor=AMAZON_VENDOR, supplier_order_reference='111-0000001-0000001'),
            dict(vendor=AMAZON_VENDOR, supplier_order_reference='111-0000001-0000001'),
            dict(vendor=AMAZON_VENDOR, supplier_order_reference='111-0000001-0000001',
                 received_date=datetime(2026, 8, 20)),
        ])

        order = catalog.find_captured_orders()[0]

        assert order.line_count == 3
        assert order.outstanding_count == 2
        assert order.is_complete is False

    def test_an_order_with_everything_received_is_complete(self, catalog):
        """The list has to distinguish these at a glance; that is its whole job."""
        seed(catalog, [
            dict(vendor=MCMASTER_VENDOR, supplier_order_reference='DONE',
                 received_date=datetime(2026, 8, 20)),
        ])

        order = catalog.find_captured_orders()[0]

        assert order.outstanding_count == 0
        assert order.is_complete is True


class TestWhatIsNotAnOrder:
    def test_a_purchase_with_no_order_reference_belongs_to_no_order(self, catalog):
        """A hand-recorded purchase, or a single-listing Amazon capture.

        It is reachable from its product, and it is not an order. Listing it
        would put a row on this page for every one-off purchase ever made.
        """
        seed(catalog, [
            dict(vendor=AMAZON_VENDOR, supplier_order_reference=None),
            dict(vendor=AMAZON_VENDOR, supplier_order_reference=''),
        ])

        assert catalog.find_captured_orders() == []

    def test_nothing_captured_is_an_empty_list_not_an_error(self, catalog):
        assert catalog.find_captured_orders() == []


class TestOrdering:
    def test_most_recent_first(self, catalog):
        seed(catalog, [
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='OLD',
                 order_date=datetime(2026, 1, 1)),
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='NEW',
                 order_date=datetime(2026, 8, 1)),
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='MIDDLE',
                 order_date=datetime(2026, 4, 1)),
        ])

        assert [o.order_number for o in catalog.find_captured_orders()] == [
            'NEW', 'MIDDLE', 'OLD',
        ]

    def test_an_order_with_no_date_sorts_last_rather_than_crashing(self, catalog):
        """Sorted in Python because the two backends disagree about NULL order."""
        seed(catalog, [
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='UNDATED',
                 order_date=None),
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='DATED',
                 order_date=datetime(2026, 4, 1)),
        ])

        assert [o.order_number for o in catalog.find_captured_orders()] == [
            'DATED', 'UNDATED',
        ]

    def test_the_order_date_is_the_earliest_on_the_order(self, catalog):
        """Lines of one order share a date, but a hand-added line may not."""
        seed(catalog, [
            dict(vendor=MCMASTER_VENDOR, supplier_order_reference='SPLIT',
                 order_date=datetime(2026, 3, 5)),
            dict(vendor=MCMASTER_VENDOR, supplier_order_reference='SPLIT',
                 order_date=datetime(2026, 3, 9)),
        ])

        assert catalog.find_captured_orders()[0].order_date == datetime(2026, 3, 5)


class TestTheRoute:
    def test_the_list_renders_every_vendor(self, client, catalog):
        seed(catalog, [
            dict(vendor=DIGIKEY_VENDOR, supplier_order_reference='100882558',
                 order_date=datetime(2026, 8, 1), unit_price=Decimal('1.50')),
            dict(vendor=MCMASTER_VENDOR, supplier_order_reference='0812SMITH',
                 order_date=datetime(2026, 8, 2)),
            dict(vendor=AMAZON_VENDOR, supplier_order_reference='111-2223334-5556667',
                 order_date=datetime(2026, 8, 3)),
        ])

        body = client.get('/products/orders').get_data(as_text=True)

        assert '100882558' in body
        assert '0812SMITH' in body
        assert '111-2223334-5556667' in body

    def test_an_empty_catalog_says_so_rather_than_showing_a_bare_table(self, client):
        body = client.get('/products/orders').get_data(as_text=True)

        assert 'no-orders' in body
