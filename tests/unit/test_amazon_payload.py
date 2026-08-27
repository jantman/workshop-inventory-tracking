"""Parsing the Amazon order payload (feature 029, US1).

The rule every one of these tests is really about: **a payload this server
cannot read is None, never an exception.** That is what makes a stale cached
agent harmless rather than a 500, and it is the same contract the McMaster
payload already has.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.models import (
    AMAZON_PAYLOAD_VENDOR,
    AMAZON_PAYLOAD_VERSION,
    AmazonOrder,
)

pytestmark = pytest.mark.unit


def build(lines=None, **overrides):
    body = {
        'version': AMAZON_PAYLOAD_VERSION,
        'vendor': AMAZON_PAYLOAD_VENDOR,
        'order_number': '111-2223334-5556667',
        'order_date': 'August 22, 2026',
        'source_url': 'https://www.amazon.com/your-orders/order-details'
                      '?orderID=111-2223334-5556667',
        'lines': lines if lines is not None else [
            {'line_number': 1, 'asin': 'B0TESTAAA1',
             'title': 'Digital Calipers', 'quantity': 1, 'unit_price': '9.99'},
            {'line_number': 2, 'asin': 'B0TESTAAA2',
             'title': 'Heat Shrink Kit', 'quantity': 3, 'unit_price': '13.95'},
        ],
    }
    body.update(overrides)
    return body


class TestAnOrderIsRead:
    def test_the_order_number_and_date(self):
        order = AmazonOrder.from_payload(build())

        assert order.order_number == '111-2223334-5556667'
        assert order.order_date == datetime(2026, 8, 22)

    def test_every_line(self):
        order = AmazonOrder.from_payload(build())

        assert [line.asin for line in order.lines] == ['B0TESTAAA1', 'B0TESTAAA2']
        assert [line.quantity for line in order.lines] == [1, 3]

    def test_a_price_is_a_decimal_never_a_float(self):
        """Constitution III."""
        order = AmazonOrder.from_payload(build())

        assert order.lines[0].unit_price == Decimal('9.99')
        assert isinstance(order.lines[0].unit_price, Decimal)

    def test_a_price_sent_as_a_json_number_is_refused_rather_than_coerced(self):
        """By then it is already a float, and a blank beats an inexact price."""
        order = AmazonOrder.from_payload(build(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'A thing', 'unit_price': 9.99},
        ]))

        assert order.lines[0].unit_price is None


class TestQuantity:
    def test_an_absent_quantity_is_one_not_missing(self):
        """Amazon renders the quantity component empty for a quantity of one.

        So "no digits" is a value, not a failure -- which is why quantity never
        appears in ``missing_fields``.
        """
        order = AmazonOrder.from_payload(build(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'A thing', 'unit_price': '1.00'},
        ]))

        assert order.lines[0].quantity == 1
        assert 'quantity' not in order.lines[0].missing_fields

    def test_a_stated_quantity_wins(self):
        order = AmazonOrder.from_payload(build(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'A thing', 'quantity': 4},
        ]))

        assert order.lines[0].quantity == 4

    def test_an_unusable_quantity_falls_back_to_one(self):
        order = AmazonOrder.from_payload(build(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'A thing', 'quantity': 'lots'},
        ]))

        assert order.lines[0].quantity == 1


class TestLineIdentity:
    def test_the_form_key_is_the_position(self):
        """Amazon numbers nothing, so position is the only line identity."""
        order = AmazonOrder.from_payload(build())

        assert [line.form_key for line in order.lines] == ['1', '2']

    def test_position_is_supplied_when_the_agent_omits_it(self):
        order = AmazonOrder.from_payload(build(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'One'},
            {'asin': 'B0TESTAAA2', 'title': 'Two'},
        ]))

        assert [line.line_number for line in order.lines] == [1, 2]

    def test_the_same_item_twice_gets_two_distinct_keys(self):
        """The failure that corrupted data in 024 when pairing was positional."""
        order = AmazonOrder.from_payload(build(lines=[
            {'asin': 'B0SAME00001', 'title': 'A thing'},
            {'asin': 'B0SAME00001', 'title': 'A thing'},
        ]))

        keys = [line.form_key for line in order.lines]
        assert keys == ['1', '2']
        assert len(set(keys)) == 2


class TestThinLines:
    def test_a_line_with_no_asin_is_still_offered(self):
        """FR-019: capturable on its title alone, or excludable. Never a refusal."""
        order = AmazonOrder.from_payload(build(lines=[
            {'title': 'Something with no item link', 'unit_price': '7.50'},
        ]))

        assert len(order.lines) == 1
        assert order.lines[0].asin == ''
        assert 'part_number' in order.lines[0].missing_fields

    def test_a_line_with_no_price_is_still_offered_and_marked(self):
        order = AmazonOrder.from_payload(build(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'A thing'},
        ]))

        assert order.lines[0].unit_price is None
        assert 'price' in order.lines[0].missing_fields

    def test_a_row_yielding_neither_item_nor_title_is_not_a_line(self):
        order = AmazonOrder.from_payload(build(lines=[
            {'asin': 'B0TESTAAA1', 'title': 'Real'},
            {'unit_price': '1.00'},
        ]))

        assert len(order.lines) == 1

    def test_lines_read_reports_what_the_agent_saw(self):
        """FR-004: "4 of 11" and "4" must not look the same."""
        order = AmazonOrder.from_payload(build(lines_read=11))

        assert order.lines_offered == 2
        assert order.lines_read == 11
        assert order.is_incomplete is True

    def test_a_count_below_what_survived_is_corrected_upward(self):
        order = AmazonOrder.from_payload(build(lines_read=1))

        assert order.lines_read == 2
        assert order.is_incomplete is False


class TestAPayloadThisServerCannotRead:
    @pytest.mark.parametrize('body', [
        None,
        'not an object',
        [],
        {},
    ])
    def test_is_none_rather_than_an_exception(self, body):
        assert AmazonOrder.from_payload(body) is None

    def test_an_unknown_version_is_none(self):
        """A stale cached agent is harmless, not a 500."""
        assert AmazonOrder.from_payload(build(version=99)) is None

    def test_another_vendors_payload_is_none(self):
        assert AmazonOrder.from_payload(build(vendor='McMaster-Carr')) is None

    def test_no_order_number_is_none(self):
        assert AmazonOrder.from_payload(build(order_number='')) is None

    def test_an_unparseable_date_is_absent_not_fatal(self):
        order = AmazonOrder.from_payload(build(order_date='sometime last week'))

        assert order is not None
        assert order.order_date is None


class TestAnOrderWithNoReadableLines:
    def test_is_not_none(self):
        """FR-023. A real order whose lines could not be read must not look
        like an order with nothing in it."""
        order = AmazonOrder.from_payload(build(lines=[]))

        assert order is not None
        assert order.order_number == '111-2223334-5556667'
        assert order.lines == ()

    def test_and_neither_is_one_whose_lines_field_is_rubbish(self):
        order = AmazonOrder.from_payload(build(lines='nonsense'))

        assert order is not None
        assert order.lines == ()
