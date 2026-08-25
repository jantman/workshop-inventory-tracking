"""Parsing a McMaster order payload, and the pack-to-unit arithmetic.

The payload is the machine boundary between the capture agent and this server
(contracts/capture-payload.md). The agent cache-busts itself and the server is
deployed separately, so a version of one **will** meet a version of the other.
The rule both sides obey is that a payload the server cannot read is not an
error -- it renders today's behaviour -- and most of what is asserted here is
that rule holding.

The other half is FR-020's arithmetic. McMaster states packs; this catalog
records units.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.models import (
    MCMASTER_PAYLOAD_VENDOR,
    MCMASTER_PAYLOAD_VERSION,
    McMasterOrder,
    McMasterOrderLine,
)


def payload(**overrides):
    """A well-formed order payload, with the fixture's own values."""
    body = {
        'version': MCMASTER_PAYLOAD_VERSION,
        'vendor': MCMASTER_PAYLOAD_VENDOR,
        'source_url': 'https://www.mcmaster.com/order-history/order/'
                      '6a5ffba81f17e12ac4fb7d70',
        'order_number': 'MISC-AND-GRINDER',
        'order_id': '6a5ffba81f17e12ac4fb7d70',
        'order_date': 'November 16, 2025',
        'lines_read': 2,
        'lines': [
            {
                'line_number': 1,
                'part_number': '3103A21',
                'description': 'Steel Pilot For Changeable-Pilot Counterbores',
                'packs': 1,
                'pack_price': '10.23',
            },
            {
                'line_number': 5,
                'part_number': '97387A173',
                'description': '18-8 Stainless Steel Domed Head Solid Rivets',
                'packs': 1,
                'pack_size': 100,
                'pack_price': '6.66',
            },
        ],
    }
    body.update(overrides)
    return body


class TestOrderParsing:

    def test_a_well_formed_order(self):
        order = McMasterOrder.from_payload(payload())

        assert order is not None
        assert order.order_number == 'MISC-AND-GRINDER'
        assert order.order_id == '6a5ffba81f17e12ac4fb7d70'
        assert order.order_date == datetime(2025, 11, 16)
        assert len(order.lines) == 2
        assert order.lines[0].part_number == '3103A21'

    def test_an_unknown_version_is_not_read(self):
        """A stale cached agent must be harmless, not a 500. 007 FR-007."""
        assert McMasterOrder.from_payload(payload(version=2)) is None
        assert McMasterOrder.from_payload(payload(version='1')) is None
        assert McMasterOrder.from_payload(payload(version=None)) is None

    @pytest.mark.parametrize('body', [None, [], 'an order', 42, True])
    def test_a_non_object_is_not_read(self, body):
        assert McMasterOrder.from_payload(body) is None

    def test_a_body_naming_no_order_number_is_not_read(self):
        """No order number, no order -- it is the key everything hangs off."""
        assert McMasterOrder.from_payload(payload(order_number='')) is None
        assert McMasterOrder.from_payload(payload(order_number='   ')) is None
        assert McMasterOrder.from_payload(payload(order_number=None)) is None

    def test_another_vendor_is_not_a_mcmaster_order(self):
        assert McMasterOrder.from_payload(payload(vendor='Amazon')) is None
        assert McMasterOrder.from_payload(payload(vendor='')) is None

    def test_empty_lines_with_a_valid_order_number_is_still_an_order(self):
        """FR-038. Never an error page, and never an empty review that reads
        like an order with no lines."""
        order = McMasterOrder.from_payload(payload(lines=[], lines_read=15))

        assert order is not None
        assert order.order_number == 'MISC-AND-GRINDER'
        assert order.lines == ()
        assert order.lines_read == 15
        assert order.is_incomplete

    def test_one_malformed_line_is_dropped_and_the_rest_survive(self):
        """FR-036: a lost line costs that line, not the capture."""
        body = payload()
        body['lines'].insert(1, 'not a line')
        # neither a part number nor a description
        body['lines'].append({'packs': 3})
        body['lines_read'] = 4

        order = McMasterOrder.from_payload(body)

        assert [line.part_number for line in order.lines] == [
            '3103A21', '97387A173'
        ]
        assert order.lines_read == 4

    def test_lines_read_is_what_the_agent_reported(self):
        """The whole of FR-004. If this collapses to len(lines), "I could only
        read 2 of your 15" becomes indistinguishable from "you ordered 2."""
        order = McMasterOrder.from_payload(payload(lines_read=15))

        assert order.lines_read == 15
        assert order.lines_offered == 2
        assert order.is_incomplete

    def test_an_absent_lines_read_falls_back_to_what_survived(self):
        body = payload()
        del body['lines_read']

        order = McMasterOrder.from_payload(body)

        assert order.lines_read == 2
        assert not order.is_incomplete

    def test_a_lines_read_below_what_survived_is_corrected_upward(self):
        """A claim of "1 seen" against 2 parsed lines is malformed. Reporting
        "2 of 1" would be worse than reporting nothing."""
        order = McMasterOrder.from_payload(payload(lines_read=1))

        assert order.lines_read == 2
        assert not order.is_incomplete

    def test_an_unparseable_date_is_the_same_as_an_absent_one(self):
        assert McMasterOrder.from_payload(
            payload(order_date='sometime last autumn')).order_date is None
        assert McMasterOrder.from_payload(
            payload(order_date=None)).order_date is None

    def test_a_date_with_no_year_is_taken_as_this_year(self):
        """McMaster omits the year exactly when the order is from this one."""
        order = McMasterOrder.from_payload(payload(order_date='July 21'))

        assert order.order_date is not None
        assert (order.order_date.month, order.order_date.day) == (7, 21)
        assert order.order_date.year == datetime.now().year

    def test_a_year_less_date_does_not_warn_or_break_on_leap_day(self):
        """strptime's default year is 1900, which is not a leap year, so
        parsing a bare "February 29" against it raises. Deprecated from 3.13
        and changing in 3.15 besides."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter('error', DeprecationWarning)
            order = McMasterOrder.from_payload(payload(order_date='March 1'))

        assert (order.order_date.month, order.order_date.day) == (3, 1)

    def test_a_missing_order_id_is_ordinary(self):
        """It only strengthens re-capture pairing; nothing requires it."""
        body = payload()
        del body['order_id']

        assert McMasterOrder.from_payload(body).order_id == ''

    def test_lines_is_not_a_list(self):
        order = McMasterOrder.from_payload(payload(lines='nope'))

        assert order is not None
        assert order.lines == ()


class TestLineParsing:

    def test_a_part_number_with_no_description_is_kept(self):
        line = McMasterOrderLine.from_payload({'part_number': '3103A21'})

        assert line is not None
        assert line.part_number == '3103A21'
        assert line.description == ''

    def test_a_description_with_no_part_number_is_kept(self):
        """A line with no part number is capturable on its description or
        excludable -- it is not dropped (FR-019)."""
        line = McMasterOrderLine.from_payload({'description': 'Shipping'})

        assert line is not None
        assert line.part_number == ''
        assert line.description == 'Shipping'

    def test_a_line_with_neither_is_dropped(self):
        """There is nothing for the operator to decide about."""
        assert McMasterOrderLine.from_payload({'packs': 2}) is None
        assert McMasterOrderLine.from_payload(
            {'part_number': '', 'description': '  '}) is None

    @pytest.mark.parametrize('data', [None, [], 'line', 7])
    def test_a_non_object_line_is_dropped(self, data):
        assert McMasterOrderLine.from_payload(data) is None

    def test_form_key_is_the_line_number(self):
        line = McMasterOrderLine.from_payload(
            {'part_number': '3103A21', 'line_number': 7})

        assert line.form_key == '7'

    def test_form_key_falls_back_to_the_part_number(self):
        line = McMasterOrderLine.from_payload({'part_number': '3103A21'})

        assert line.form_key == '3103A21'

    def test_two_lines_of_one_part_get_distinct_form_keys(self):
        """The corruption PR #116 bought: one shared set of controls for two
        lines meant neither could be included or amended on its own."""
        order = McMasterOrder.from_payload(payload(lines=[
            {'line_number': 1, 'part_number': '3103A21', 'packs': 1},
            {'line_number': 2, 'part_number': '3103A21', 'packs': 4},
        ]))

        assert [line.form_key for line in order.lines] == ['1', '2']

    def test_a_zero_or_negative_count_is_not_a_fact_about_the_order(self):
        line = McMasterOrderLine.from_payload({
            'part_number': '3103A21', 'packs': 0, 'pack_size': -5,
        })

        assert line.packs is None
        assert line.pack_size is None
        assert line.quantity is None

    def test_missing_fields_are_named_for_the_review(self):
        """FR-037: a blank price on one line of fifteen is not something the
        operator notices unaided."""
        line = McMasterOrderLine.from_payload({'part_number': '3103A21'})

        assert set(line.missing_fields) == {'description', 'quantity', 'price'}

    def test_a_fully_read_line_is_missing_nothing(self):
        line = McMasterOrderLine.from_payload({
            'part_number': '3103A21', 'description': 'Pilot',
            'packs': 1, 'pack_price': '10.23',
        })

        assert line.missing_fields == ()


class TestPackArithmetic:
    """FR-020. McMaster states packs; this catalog records units."""

    def test_packs_times_pack_size_is_the_recorded_quantity(self):
        line = McMasterOrderLine.from_payload({
            'part_number': '97387A173', 'packs': 4, 'pack_size': 25,
            'pack_price': '6.00',
        })

        assert line.quantity == 100

    def test_unit_price_is_the_pack_price_divided_and_rounded(self):
        line = McMasterOrderLine.from_payload({
            'part_number': '90519A871', 'packs': 1, 'pack_size': 4,
            'pack_price': '6.00',
        })

        assert line.unit_price == Decimal('1.50')

    def test_an_absent_pack_size_means_one_unit_is_one_unit(self):
        """"Each" -- and "Pairs", where McMaster states no count at all."""
        line = McMasterOrderLine.from_payload({
            'part_number': '6111K257', 'packs': 2, 'pack_price': '47.00',
        })

        assert line.pack_size is None
        assert line.quantity == 2
        assert line.unit_price == Decimal('47.00')

    def test_a_pack_of_one_is_one_unit_each(self):
        line = McMasterOrderLine.from_payload({
            'part_number': '90519A871', 'packs': 4, 'pack_size': 1,
            'pack_price': '6.17',
        })

        assert line.quantity == 4
        assert line.unit_price == Decimal('6.17')

    def test_price_rounds_is_true_when_the_division_loses_a_cent(self):
        """The fixture's line 5: 6.66 across a pack of 100."""
        line = McMasterOrderLine.from_payload({
            'part_number': '97387A173', 'packs': 1, 'pack_size': 100,
            'pack_price': '6.66',
        })

        assert line.exact_unit_price == Decimal('0.0666')
        assert line.unit_price == Decimal('0.07')
        assert line.price_rounds

    def test_price_rounds_is_false_when_the_division_is_exact(self):
        line = McMasterOrderLine.from_payload({
            'part_number': '90189A118', 'packs': 1, 'pack_size': 25,
            'pack_price': '15.00',
        })

        assert line.unit_price == Decimal('0.60')
        assert not line.price_rounds

    def test_price_rounds_is_false_when_there_is_no_price(self):
        line = McMasterOrderLine.from_payload({'part_number': '3103A21'})

        assert line.unit_price is None
        assert not line.price_rounds

    def test_prices_arrive_as_strings_and_become_decimals(self):
        """Constitution III has no exemption for a value in transit. A JSON
        number would already be a float before any assertion could see it, so
        the assertion that matters is the type."""
        order = McMasterOrder.from_payload(payload())

        price = order.lines[1].pack_price
        assert isinstance(price, Decimal)
        assert price == Decimal('6.66')

    def test_a_price_sent_as_a_json_number_is_refused(self):
        """By the time a float is here the damage is done, and dropping it
        leaves a blank to fill in rather than an inexact price."""
        line = McMasterOrderLine.from_payload({
            'part_number': '3103A21', 'packs': 1,
            'pack_price': 6.9000000000000004,
        })

        assert line.pack_price is None
        assert line.unit_price is None
        assert 'price' in line.missing_fields

    def test_a_negative_price_is_refused(self):
        line = McMasterOrderLine.from_payload({
            'part_number': '3103A21', 'packs': 1, 'pack_price': '-4.00',
        })

        assert line.pack_price is None

    def test_an_unparseable_price_costs_that_field_alone(self):
        """FR-036. The line still captures, with a blank editable price."""
        line = McMasterOrderLine.from_payload({
            'part_number': '3103A21', 'description': 'Pilot',
            'packs': 3, 'pack_price': 'call for pricing',
        })

        assert line is not None
        assert line.pack_price is None
        assert line.quantity == 3
        assert line.part_number == '3103A21'
