"""
Unit tests for order-time capture and receipt.

Three properties carry this story: capture is idempotent (people double-click
bookmarks), it attaches to an existing product when the identifier already names
one, and the details captured at order time are amendable when the thing actually
turns up in a different quantity or at a different price.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ValidationError

AMAZON_URL = 'https://www.amazon.com/dp/B0ABCDEFGH/ref=sr_1_3'


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


class TestCapture:
    def test_capture_creates_an_unreceived_purchase(self, service):
        """FR-020: the order is recorded, not the receipt"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='Blue Widget 10-Pack', url=AMAZON_URL,
        )

        assert purchase.received_date is None
        assert purchase.is_outstanding is True
        assert purchase.vendor == 'Amazon'
        assert purchase.vendor_item_id == 'B0ABCDEFGH'
        assert purchase.listing_title == 'Blue Widget 10-Pack'

    def test_capture_creates_a_product_when_nothing_matches(self, service):
        """FR-021, the 'otherwise' half"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='Blue Widget 10-Pack',
        )
        product = service.get_product(purchase.product_id)

        assert product is not None
        assert product.description == 'Blue Widget 10-Pack'

    def test_the_listing_title_becomes_the_starting_description(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Raw vendor wording',
        )
        assert service.get_product(purchase.product_id).description == 'Raw vendor wording'

    def test_capture_records_the_price_as_a_decimal(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', unit_price='12.34',
        )
        assert isinstance(purchase.unit_price, Decimal)
        assert purchase.unit_price == Decimal('12.34')

    def test_a_float_price_is_refused(self, service):
        """Constitution III, enforced at the boundary rather than hoped for"""
        with pytest.raises(ValidationError):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH', unit_price=12.34,
            )

    def test_vendor_is_required(self, service):
        with pytest.raises(ValidationError):
            service.capture_order(vendor='', vendor_item_id='B0ABCDEFGH')

    def test_the_url_is_kept(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', url=AMAZON_URL
        )
        assert AMAZON_URL in purchase.notes


class TestIdempotency:
    """Capturing the same listing twice attaches nothing new"""

    def test_the_same_listing_twice_is_one_purchase(self, service):
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget',
            order_date=datetime(2026, 1, 14),
        )
        second = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget',
            order_date=datetime(2026, 1, 14),
        )
        assert second.id == first.id

    def test_no_duplicate_product_is_created_either(self, service):
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget',
            order_date=datetime(2026, 1, 14),
        )
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget',
            order_date=datetime(2026, 1, 14),
        )
        assert len(service.list_products()) == 1

    def test_the_same_item_on_a_different_day_is_a_different_purchase(self, service):
        """Buying the same thing again in March is a second purchase"""
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        second = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 3, 2),
        )
        assert second.id != first.id
        assert second.product_id == first.product_id

    def test_the_same_item_id_from_a_different_vendor_is_a_different_purchase(self, service):
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        second = service.capture_order(
            vendor='eBay', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        assert second.id != first.id
        assert second.product_id != first.product_id

    def test_the_time_of_day_does_not_break_idempotency(self, service):
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            order_date=datetime(2026, 1, 14, 9, 15),
        )
        second = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            order_date=datetime(2026, 1, 14, 17, 40),
        )
        assert second.id == first.id


class TestAttachVsCreate:
    """FR-021"""

    def test_capture_attaches_to_a_product_that_already_owns_the_identifier(self, service):
        existing = service.create_product(
            description='Blue widget, already catalogued',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget 10-Pack',
        )

        assert purchase.product_id == existing.id
        assert len(service.list_products()) == 1

    def test_attaching_does_not_overwrite_the_operators_own_description(self, service):
        """The vendor's wording does not get to replace the operator's"""
        existing = service.create_product(
            description='Blue widget, 10mm, the good ones',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='BLUE WIDGET 10 PACK BEST QUALITY ✨',
        )
        assert service.get_product(existing.id).description == 'Blue widget, 10mm, the good ones'

    def test_a_different_identifier_creates_a_second_product(self, service):
        service.capture_order(vendor='Amazon', vendor_item_id='B0ABCDEFGH')
        service.capture_order(vendor='Amazon', vendor_item_id='B0ZZZZZZZZ')
        assert len(service.list_products()) == 2


class TestAmendmentAtReceipt:
    """What arrives is allowed to differ from what was ordered"""

    def test_receiving_sets_the_received_date(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', quantity=10,
        )
        received = service.receive_purchase(captured.id)

        assert received.received_date is not None
        assert received.is_outstanding is False

    def test_quantity_can_be_amended_at_receipt(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', quantity=10,
        )
        received = service.receive_purchase(captured.id, quantity=8)
        assert received.quantity == 8

    def test_price_can_be_amended_at_receipt(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', unit_price='12.34',
        )
        received = service.receive_purchase(captured.id, unit_price='11.00')
        assert received.unit_price == Decimal('11.00')

    def test_receiving_an_already_received_purchase_is_a_no_op(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        first = service.receive_purchase(captured.id, received_date=datetime(2026, 2, 1))
        second = service.receive_purchase(captured.id, received_date=datetime(2026, 3, 1))

        assert second.received_date == first.received_date

    def test_receiving_before_the_order_date_is_refused(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 3, 1),
        )
        with pytest.raises(ValidationError):
            service.receive_purchase(captured.id, received_date=datetime(2026, 1, 1))

    def test_the_captured_details_are_already_there_at_receipt(self, service):
        """SC-002: only description and specifications are left to author"""
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='Blue Widget 10-Pack', order_date=datetime(2026, 1, 14),
            unit_price='12.34', quantity=10,
        )
        assert captured.vendor == 'Amazon'
        assert captured.vendor_item_id == 'B0ABCDEFGH'
        assert captured.listing_title == 'Blue Widget 10-Pack'
        assert captured.order_date == datetime(2026, 1, 14)
        assert captured.unit_price == Decimal('12.34')
        assert captured.quantity == 10


class TestUrlParsing:
    """Reading the URL, never the page's markup"""

    def test_amazon_asin_and_vendor_come_out_of_the_url(self, client):
        from app.product.routes import _asin_from_url, _vendor_from_url

        assert _asin_from_url(AMAZON_URL) == 'B0ABCDEFGH'
        assert _vendor_from_url(AMAZON_URL) == 'Amazon'

    def test_the_gp_product_form_works_too(self, client):
        from app.product.routes import _asin_from_url

        assert _asin_from_url(
            'https://www.amazon.com/gp/product/B0ABCDEFGH?psc=1'
        ) == 'B0ABCDEFGH'

    def test_an_unknown_vendor_falls_back_to_its_host(self, client):
        from app.product.routes import _vendor_from_url

        assert _vendor_from_url('https://www.example-parts.co.uk/thing') == 'example-parts.co.uk'

    def test_a_url_with_no_asin_yields_nothing_rather_than_a_guess(self, client):
        from app.product.routes import _asin_from_url

        assert _asin_from_url('https://www.digikey.com/en/products/detail/x/y/123') == ''

    def test_a_blank_url_is_not_an_error(self, client):
        from app.product.routes import _asin_from_url, _vendor_from_url

        assert _asin_from_url('') == ''
        assert _vendor_from_url('') == ''
