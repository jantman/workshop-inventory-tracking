"""Reviewing and capturing an Amazon order (feature 029, US1).

Two halves, and the line between them is the point:

* ``review_order`` reads and decides. It **writes nothing**, so the operator can
  close the tab and leave no trace (FR-005).
* ``capture_order_lines`` writes, and writes the whole order in one transaction,
  so a failure part-way through leaves nothing behind (FR-020).

Amazon is the third vendor through the one flow feature 029 built, and what is
worth testing here is what is *Amazon's*: no enrichment and no pack arithmetic,
an ASIN as the only identifier, and position as the only line identity.
"""

from decimal import Decimal

import pytest

from app.catalog_service import AMAZON_ORDER_VENDOR, AMAZON_VENDOR, CatalogService
from app.exceptions import ValidationError
from app.models import (
    AMAZON_PAYLOAD_VENDOR,
    AMAZON_PAYLOAD_VERSION,
    AmazonOrder,
    IdentifierType,
    OrderLineState,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def build_order(lines=None, **overrides):
    body = {
        'version': AMAZON_PAYLOAD_VERSION,
        'vendor': AMAZON_PAYLOAD_VENDOR,
        'order_number': '111-2223334-5556667',
        'order_date': 'August 22, 2026',
        'source_url': 'https://www.amazon.com/your-orders/order-details'
                      '?orderID=111-2223334-5556667',
        'lines': lines if lines is not None else [
            {'asin': 'B0TESTAAA1', 'title': 'Digital Calipers', 'unit_price': '9.99'},
            {'asin': 'B0TESTAAA2', 'title': 'Heat Shrink Kit',
             'quantity': 3, 'unit_price': '13.95'},
        ],
    }
    body.update(overrides)
    return AmazonOrder.from_payload(body)


def take_all(order, **extra):
    """Include every line, as the review's checkboxes default to."""
    return {
        line.form_key: dict({'include': True}, **extra)
        for line in order.lines
    }


class TestTheReviewWritesNothing:
    def test_no_product_and_no_purchase(self, catalog):
        order = build_order()

        catalog.review_order(order, AMAZON_ORDER_VENDOR)

        assert catalog.search_products() == []

    def test_every_line_is_new_against_an_empty_catalog(self, catalog):
        review = catalog.review_order(build_order(), AMAZON_ORDER_VENDOR)

        assert [line.state for line in review.lines] == [
            OrderLineState.NEW, OrderLineState.NEW,
        ]

    def test_the_suggested_description_is_amazons_title(self, catalog):
        review = catalog.review_order(build_order(), AMAZON_ORDER_VENDOR)

        assert review.lines[0].suggested_description == 'Digital Calipers'

    def test_no_line_is_enriched(self, catalog):
        """Amazon has no part lookup: the page is the detail."""
        review = catalog.review_order(build_order(), AMAZON_ORDER_VENDOR)

        assert all(line.part is None for line in review.lines)


class TestCapturing:
    def test_one_outstanding_purchase_per_included_line(self, catalog):
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order)
        )

        assert len(result.purchase_ids) == 2
        assert result.products_created == 2

    def test_the_purchase_carries_the_order_number_and_line(self, catalog):
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        lines = catalog.find_order_lines_for(AMAZON_VENDOR, '111-2223334-5556667')

        assert len(lines) == 2
        assert [line.order_line_number for line in lines] == [1, 2]
        assert all(line.vendor == AMAZON_VENDOR for line in lines)

    def test_the_quantity_and_unit_price_are_what_the_page_said(self, catalog):
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        lines = catalog.find_order_lines_for(AMAZON_VENDOR, '111-2223334-5556667')

        assert lines[0].quantity == 1
        assert lines[0].unit_price == Decimal('9.99')
        assert lines[1].quantity == 3

    def test_everything_is_outstanding_at_capture(self, catalog):
        """FR-011, whatever the page says about delivery."""
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        lines = catalog.find_order_lines_for(AMAZON_VENDOR, '111-2223334-5556667')

        assert all(line.received_date is None for line in lines)

    def test_the_product_carries_the_asin_scoped_to_amazon(self, catalog):
        """FR-012, and it is what lets a later listing capture find this product."""
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        product = catalog.find_product_by_identifier(
            'B0TESTAAA1', id_type=IdentifierType.VENDOR.value, vendor=AMAZON_VENDOR,
        )

        assert product is not None
        assert product.description == 'Digital Calipers'

    def test_the_operators_description_beats_amazons_title(self, catalog):
        order = build_order()
        decisions = take_all(order)
        decisions[order.lines[0].form_key]['description'] = 'Calipers, 6in digital'

        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, decisions)

        product = catalog.find_product_by_identifier(
            'B0TESTAAA1', id_type=IdentifierType.VENDOR.value, vendor=AMAZON_VENDOR,
        )
        assert product.description == 'Calipers, 6in digital'

    def test_amazons_title_is_kept_on_the_purchase(self, catalog):
        """Distinct from the operator's own product description."""
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        lines = catalog.find_order_lines_for(AMAZON_VENDOR, '111-2223334-5556667')

        assert lines[0].listing_title == 'Digital Calipers'


class TestExclusion:
    def test_an_excluded_line_produces_nothing(self, catalog):
        order = build_order()
        decisions = take_all(order)
        decisions[order.lines[1].form_key]['include'] = False

        result = catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, decisions)

        assert len(result.purchase_ids) == 1
        assert result.lines_excluded == 1

    def test_and_every_other_line_captures_normally(self, catalog):
        order = build_order()
        decisions = take_all(order)
        decisions[order.lines[0].form_key]['include'] = False

        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, decisions)
        lines = catalog.find_order_lines_for(AMAZON_VENDOR, '111-2223334-5556667')

        assert [line.vendor_item_id for line in lines] == ['B0TESTAAA2']


class TestRecapture:
    def test_capturing_the_same_order_twice_records_nothing_new(self, catalog):
        """SC-003."""
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        again = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order)
        )

        assert again.purchase_ids == ()
        assert again.lines_already_captured == 2
        assert len(catalog.find_order_lines_for(
            AMAZON_VENDOR, '111-2223334-5556667')) == 2

    def test_a_recaptured_line_reads_as_already_captured(self, catalog):
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        review = catalog.review_order(order, AMAZON_ORDER_VENDOR)

        assert all(
            line.state is OrderLineState.CAPTURED for line in review.lines
        )

    def test_a_changed_price_is_offered_and_applied_only_on_confirmation(self, catalog):
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        changed = build_order(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'Digital Calipers', 'unit_price': '11.49'},
            {'asin': 'B0TESTAAA2', 'title': 'Heat Shrink Kit',
             'quantity': 3, 'unit_price': '13.95'},
        ])

        review = catalog.review_order(changed, AMAZON_ORDER_VENDOR)
        assert review.lines[0].has_change is True

        result = catalog.capture_order_lines(
            changed, AMAZON_ORDER_VENDOR,
            {changed.lines[0].form_key: {'apply_change': True}},
        )

        assert result.lines_updated == 1
        lines = catalog.find_order_lines_for(AMAZON_VENDOR, '111-2223334-5556667')
        assert lines[0].unit_price == Decimal('11.49')


class TestTheSameItemOnTwoLines:
    """SC-005. The failure that corrupted data in 024 when pairing was positional."""

    def test_two_lines_naming_one_asin_become_two_purchases(self, catalog):
        order = build_order(lines=[
            {'asin': 'B0SAME00001', 'title': 'A thing', 'unit_price': '1.00'},
            {'asin': 'B0SAME00001', 'title': 'A thing', 'unit_price': '1.00'},
        ])

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order)
        )

        assert len(result.purchase_ids) == 2

    def test_and_a_change_applies_to_its_own_line_only(self, catalog):
        order = build_order(lines=[
            {'asin': 'B0SAME00001', 'title': 'A thing', 'unit_price': '1.00'},
            {'asin': 'B0SAME00001', 'title': 'A thing', 'unit_price': '1.00'},
        ])
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        changed = build_order(lines=[
            {'asin': 'B0SAME00001', 'title': 'A thing', 'unit_price': '1.00'},
            {'asin': 'B0SAME00001', 'title': 'A thing', 'unit_price': '2.50'},
        ])
        catalog.capture_order_lines(
            changed, AMAZON_ORDER_VENDOR,
            {changed.lines[1].form_key: {'apply_change': True}},
        )

        lines = catalog.find_order_lines_for(AMAZON_VENDOR, '111-2223334-5556667')
        assert [line.unit_price for line in lines] == [
            Decimal('1.00'), Decimal('2.50'),
        ]


class TestMatchingAProductAlreadyHeld:
    def test_a_known_asin_attaches_rather_than_duplicating(self, catalog):
        """SC-004."""
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        second = build_order(order_number='111-9999999-9999999', lines=[
            {'asin': 'B0TESTAAA1', 'title': 'Digital Calipers', 'unit_price': '9.99'},
        ])
        result = catalog.capture_order_lines(
            second, AMAZON_ORDER_VENDOR, take_all(second)
        )

        assert result.products_created == 0
        assert result.products_attached == 1

    def test_and_the_review_names_the_product(self, catalog):
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        second = build_order(order_number='111-9999999-9999999', lines=[
            {'asin': 'B0TESTAAA1', 'title': 'Digital Calipers', 'unit_price': '9.99'},
        ])
        review = catalog.review_order(second, AMAZON_ORDER_VENDOR)

        assert review.lines[0].state is OrderLineState.MATCHED
        assert review.lines[0].product_description == 'Digital Calipers'


class TestNothingPartial:
    def test_a_refused_description_leaves_the_whole_order_unwritten(self, catalog):
        """FR-020. Half an order is worse than none."""
        order = build_order()
        decisions = take_all(order)
        decisions[order.lines[1].form_key]['description'] = 'x' * 5000

        with pytest.raises(ValidationError):
            catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, decisions)

        assert catalog.search_products() == []
        assert catalog.find_order_lines_for(
            AMAZON_VENDOR, '111-2223334-5556667') == []


class TestThinLinesAreNamed:
    def test_a_line_missing_a_field_is_named_in_the_result(self, catalog):
        """FR-022, carried past the review."""
        order = build_order(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'Priceless thing'},
        ])

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order)
        )

        assert result.lines_incomplete == ('Priceless thing',)

    def test_a_complete_line_is_not_named(self, catalog):
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order)
        )

        assert result.lines_incomplete == ()
