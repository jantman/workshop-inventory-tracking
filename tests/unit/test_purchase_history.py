"""
Unit tests for purchase history and the latest price.

A second purchase of a known product joins one history rather than creating a
duplicate (FR-006, FR-019, SC-005) -- and two variants the operator deliberately
kept apart stay apart.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.catalog_service import CatalogService


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def product(service):
    return service.create_product(description='Blue widget, 10mm')


class TestOrdering:
    def test_history_is_chronological_by_order_date(self, service, product):
        service.record_purchase(product.id, vendor='eBay', order_date=datetime(2026, 3, 2))
        service.record_purchase(product.id, vendor='Amazon', order_date=datetime(2026, 1, 14))
        service.record_purchase(product.id, vendor='Mouser', order_date=datetime(2026, 2, 1))

        assert [p.vendor for p in service.get_purchase_history(product.id)] == [
            'Amazon', 'Mouser', 'eBay'
        ]

    def test_a_purchase_with_no_order_date_sorts_last(self, service, product):
        """An unknown date is not an early one"""
        service.record_purchase(product.id, vendor='Unknown')
        service.record_purchase(product.id, vendor='Amazon', order_date=datetime(2026, 1, 14))

        assert [p.vendor for p in service.get_purchase_history(product.id)] == [
            'Amazon', 'Unknown'
        ]

    def test_an_empty_history_is_an_empty_list(self, service, product):
        assert service.get_purchase_history(product.id) == []

    def test_history_is_per_product(self, service):
        first = service.create_product(description='first')
        second = service.create_product(description='second')
        service.record_purchase(first.id, vendor='Amazon')

        assert len(service.get_purchase_history(first.id)) == 1
        assert service.get_purchase_history(second.id) == []


class TestLatestPrice:
    def test_the_most_recent_order_date_wins_not_the_most_recent_row(self, service, product):
        """FR-006"""
        service.record_purchase(
            product.id, vendor='eBay', order_date=datetime(2026, 3, 2), unit_price='11.00'
        )
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), unit_price='12.34'
        )

        assert service.get_latest_price(product.id) == Decimal('11.00')

    def test_the_price_is_a_decimal(self, service, product):
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), unit_price='12.34'
        )
        assert isinstance(service.get_latest_price(product.id), Decimal)

    def test_a_history_with_no_prices_has_no_latest_price(self, service, product):
        service.record_purchase(product.id, vendor='Amazon', order_date=datetime(2026, 1, 14))
        assert service.get_latest_price(product.id) is None

    def test_an_unpriced_later_purchase_does_not_hide_the_last_known_price(self, service, product):
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), unit_price='12.34'
        )
        service.record_purchase(product.id, vendor='eBay', order_date=datetime(2026, 3, 2))

        assert service.get_latest_price(product.id) == Decimal('12.34')

    def test_no_purchases_means_no_price(self, service, product):
        assert service.get_latest_price(product.id) is None


class TestRepeatPurchaseBuildsOneHistory:
    """SC-005: buying the same thing again does not fork the catalog"""

    def test_two_purchases_of_one_product_stay_under_one_product(self, service, product):
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14),
            unit_price='12.34', quantity=10,
        )
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 3, 2),
            unit_price='11.00', quantity=10,
        )

        assert len(service.list_products()) == 1
        assert len(service.get_purchase_history(product.id)) == 2

    def test_a_scan_of_a_repeat_buy_resolves_to_the_existing_product(self, service):
        """FR-019: the same resolution, called from the receiving bench"""
        existing = service.create_product(
            description='Blue widget',
            identifiers=[{'id_type': 'GTIN', 'value': '012345678905'}],
        )
        service.record_purchase(existing.id, vendor='Amazon', order_date=datetime(2026, 1, 14))

        resolution = service.scan('012345678905')
        assert resolution.outcome == 'product'
        assert resolution.product.id == existing.id

    def test_prices_are_visible_across_the_whole_history(self, service, product):
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), unit_price='12.34'
        )
        service.record_purchase(
            product.id, vendor='eBay', order_date=datetime(2026, 3, 2), unit_price='11.00'
        )

        prices = [p.unit_price for p in service.get_purchase_history(product.id)]
        assert prices == [Decimal('12.34'), Decimal('11.00')]


class TestVariantsStayDistinct:
    """Two things the operator deliberately kept apart are not merged"""

    def test_two_products_with_different_identifiers_keep_separate_histories(self, service):
        ten_mm = service.create_product(
            description='Blue widget, 10mm',
            identifiers=[{'id_type': 'MPN', 'value': 'WIDGET-10'}],
        )
        twelve_mm = service.create_product(
            description='Blue widget, 12mm',
            identifiers=[{'id_type': 'MPN', 'value': 'WIDGET-12'}],
        )

        service.record_purchase(ten_mm.id, vendor='Amazon', unit_price='12.34')
        service.record_purchase(twelve_mm.id, vendor='Amazon', unit_price='14.00')

        assert service.get_latest_price(ten_mm.id) == Decimal('12.34')
        assert service.get_latest_price(twelve_mm.id) == Decimal('14.00')
        assert len(service.get_purchase_history(ten_mm.id)) == 1
        assert len(service.get_purchase_history(twelve_mm.id)) == 1

    def test_two_variants_with_the_same_description_are_still_two_products(self, service):
        """Description is not identity either -- the row is"""
        first = service.create_product(description='Blue widget')
        second = service.create_product(description='Blue widget')

        assert first.id != second.id
        assert first.internal_code != second.internal_code


class TestUndatedPurchasesAreNotRecent:
    """An unknown date is not an early one -- and it is not a late one either.

    get_purchase_history sorts undated purchases last, which is right. Reading
    "last in that list" as "most recent" is not: it turns an honest agnosticism
    about when something was bought into a false claim that it was bought most
    recently, and puts the wrong vendor and price on a printed label.
    """

    def test_a_dated_purchase_beats_an_undated_one_for_latest_price(self, service, product):
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), unit_price='12.34'
        )
        service.record_purchase(product.id, vendor='Junk Shop', unit_price='5.00')

        assert service.get_latest_price(product.id) == Decimal('12.34')

    def test_the_same_for_the_purchase_the_label_quotes(self, service, product):
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), unit_price='12.34'
        )
        service.record_purchase(product.id, vendor='Junk Shop', unit_price='5.00')

        assert service.get_latest_purchase(product.id).vendor == 'Amazon'

    def test_an_undated_purchase_is_used_when_nothing_carries_a_date(self, service, product):
        """It is the best available answer, not a wrong one"""
        service.record_purchase(product.id, vendor='Junk Shop', unit_price='5.00')

        assert service.get_latest_price(product.id) == Decimal('5.00')
        assert service.get_latest_purchase(product.id).vendor == 'Junk Shop'

    def test_the_most_recent_dated_purchase_still_wins_among_dated_ones(self, service, product):
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), unit_price='12.34'
        )
        service.record_purchase(
            product.id, vendor='eBay', order_date=datetime(2026, 3, 2), unit_price='11.00'
        )
        service.record_purchase(product.id, vendor='Junk Shop', unit_price='5.00')

        assert service.get_latest_price(product.id) == Decimal('11.00')
        assert service.get_latest_purchase(product.id).vendor == 'eBay'

    def test_an_unpriced_dated_purchase_falls_back_to_an_older_dated_price(self, service, product):
        service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), unit_price='12.34'
        )
        service.record_purchase(product.id, vendor='eBay', order_date=datetime(2026, 3, 2))

        assert service.get_latest_price(product.id) == Decimal('12.34')

    def test_no_purchases_at_all(self, service, product):
        assert service.get_latest_purchase(product.id) is None
        assert service.get_latest_price(product.id) is None
