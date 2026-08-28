"""Reducing an Amazon order-history export to the orders it names (031, US2).

The export states one row per **item**, so the thing being tested is mostly
arithmetic about identity: eleven rows are one order, a digital order is not an
order this catalog can capture, and a marketplace is part of an order's address
rather than an assumption.

The refusal cases matter as much as the reductions. A short list and a
successful run over a small file look identical, so a file this cannot read has
to say so and emit nothing rather than emit what it managed.
"""

import re

import pytest

from app.exceptions import ValidationError
from app.services.amazon_order_export import (
    ORDER_ID_PATTERN,
    AmazonExportOrder,
    summarize,
)

pytestmark = pytest.mark.unit


def row(order_id='111-2223334-5556667', website='www.amazon.com', **extra):
    body = {
        'Website': website,
        'Order ID': order_id,
        'Order Date': '2024-03-04',
        'ASIN': 'B0TESTAAA1',
        'Product Name': 'Digital Calipers',
        'Order Status': 'Closed',
    }
    body.update(extra)
    return body


class TestOneOrderPerOrder:
    def test_eleven_rows_naming_one_order_yield_it_once(self):
        summary = summarize([row() for _ in range(11)])

        assert len(summary.orders) == 1
        assert summary.orders[0].order_id == '111-2223334-5556667'

    def test_and_it_says_how_many_rows_that_was(self):
        """So an order of eleven items is visibly that on the review later."""
        summary = summarize([row() for _ in range(11)])

        assert summary.rows_read == 11
        assert summary.orders[0].row_count == 11

    def test_orders_come_back_in_the_files_own_order(self):
        """First-seen, which is the order the operator was just looking at."""
        summary = summarize([
            row(order_id='333-3333333-3333333'),
            row(order_id='111-1111111-1111111'),
            row(order_id='333-3333333-3333333'),
        ])

        assert [o.order_id for o in summary.orders] == [
            '333-3333333-3333333', '111-1111111-1111111',
        ]

    def test_only_orders_the_kept_rows_name(self):
        """The operator's edit of the file is what selects; nothing else does."""
        summary = summarize([row(order_id='111-1111111-1111111')])

        assert [o.order_id for o in summary.orders] == ['111-1111111-1111111']

    def test_an_empty_file_is_not_an_error(self):
        summary = summarize([])

        assert summary.orders == ()
        assert summary.rows_read == 0


class TestTheAddress:
    def test_it_is_built_from_the_rows_own_marketplace(self):
        """A mixed export must not produce thirty dead links."""
        summary = summarize([
            row(order_id='111-1111111-1111111', website='www.amazon.com'),
            row(order_id='222-2222222-2222222', website='www.amazon.co.uk'),
        ])

        assert summary.orders[0].url.startswith('https://www.amazon.com/')
        assert summary.orders[1].url.startswith('https://www.amazon.co.uk/')

    def test_a_website_with_a_scheme_is_not_doubled(self):
        summary = summarize([row(website='https://www.amazon.com')])

        assert summary.orders[0].url == (
            'https://www.amazon.com/gp/css/order-details'
            '?orderID=111-2223334-5556667'
        )

    def test_a_blank_website_falls_back_rather_than_breaking(self):
        summary = summarize([row(website='')])

        assert summary.orders[0].url.startswith('https://www.amazon.com/')

    def test_the_address_carries_an_id_the_capture_agent_recognizes(self):
        """The agent's own pattern, so this cannot drift away from it.

        `app/static/js/capture-agent.js` matches
        ``orderID=(\\d{3}-\\d{7}-\\d{7})`` on the order-details path. An address
        this emits that the agent will not act on is a dead link.
        """
        agent_pattern = re.compile(r'(?:^|[?&])orderID=(\d{3}-\d{7}-\d{7})(?:&|$)')
        url = AmazonExportOrder('111-2223334-5556667', 'www.amazon.com').url

        assert agent_pattern.search(url)
        assert 'order-details' in url


class TestWhatItWillNotUse:
    def test_a_digital_order_is_not_emitted(self):
        """`D01-...` is a different file of the export and not physical goods."""
        summary = summarize([
            row(), row(order_id='D01-1111111-1111111'),
        ])

        assert [o.order_id for o in summary.orders] == ['111-2223334-5556667']

    def test_and_it_is_counted_rather_than_silently_dropped(self):
        summary = summarize([row(), row(order_id='D01-1111111-1111111')])

        assert summary.rows_unusable == 1
        assert 'could not use' in summary.render()

    def test_a_blank_order_id_is_counted_too(self):
        summary = summarize([row(), row(order_id='')])

        assert summary.rows_unusable == 1

    def test_the_pattern_is_the_agents(self):
        assert ORDER_ID_PATTERN.match('111-2223334-5556667')
        assert not ORDER_ID_PATTERN.match('D01-1111111-1111111')
        assert not ORDER_ID_PATTERN.match('111-222333-5556667')


class TestRefusingAFileItCannotRead:
    def test_a_missing_order_id_column_is_refused(self):
        with pytest.raises(ValidationError) as caught:
            summarize([{'Website': 'www.amazon.com', 'Order Date': '2024-03-04'}])

        assert 'Order ID' in caught.value.message

    def test_and_the_message_lists_what_it_did_find(self):
        """So the operator can see they passed the wrong file out of the zip."""
        with pytest.raises(ValidationError) as caught:
            summarize([{'Website': 'www.amazon.com', 'Order Date': '2024-03-04'}])

        assert 'Order Date' in caught.value.message
        assert 'Website' in caught.value.message

    def test_a_missing_website_column_is_refused(self):
        with pytest.raises(ValidationError) as caught:
            summarize([{'Order ID': '111-2223334-5556667'}])

        assert 'Website' in caught.value.message

    def test_a_file_of_unrelated_columns_names_both(self):
        with pytest.raises(ValidationError) as caught:
            summarize([{'Foo': '1', 'Bar': '2'}])

        assert 'Order ID' in caught.value.message
        assert 'Website' in caught.value.message


class TestTheSummary:
    def test_it_always_states_rows_and_orders(self):
        """A file edited down to four rows that yields one order is visibly that."""
        summary = summarize([row(), row(), row(order_id='222-2222222-2222222')])

        rendered = summary.render()
        assert 'Read 3 row(s)' in rendered
        assert '2 distinct order(s)' in rendered

    def test_it_names_the_statuses_when_they_differ(self):
        summary = summarize([
            row(order_id='111-1111111-1111111', **{'Order Status': 'Closed'}),
            row(order_id='222-2222222-2222222', **{'Order Status': 'Cancelled'}),
        ])

        assert summary.status_counts == (('Cancelled', 1), ('Closed', 1))
        assert 'Cancelled (1)' in summary.render()

    def test_a_cancelled_order_is_reported_and_never_dropped(self):
        """The operator's edit is authoritative; a filter would be a knob."""
        summary = summarize([
            row(order_id='222-2222222-2222222', **{'Order Status': 'Cancelled'}),
        ])

        assert [o.order_id for o in summary.orders] == ['222-2222222-2222222']

    def test_one_status_everywhere_is_not_worth_saying(self):
        summary = summarize([row(), row(order_id='222-2222222-2222222')])

        assert 'statuses seen' not in summary.render()

    def test_a_file_without_a_status_column_still_works(self):
        """Only two columns are required; the rest are read if they are there."""
        summary = summarize([
            {'Order ID': '111-2223334-5556667', 'Website': 'www.amazon.com'},
        ])

        assert len(summary.orders) == 1
        assert summary.status_counts == ()


class TestTheHeaderWhenThereAreNoRows:
    """A file edited down to its header alone is a real state: the operator
    deleted every row. It is a shape question, not an empty one, and the rows
    cannot answer it -- which is why the caller passes ``fieldnames``.
    """

    def test_a_valid_header_with_no_rows_is_empty_rather_than_refused(self):
        summary = summarize([], fieldnames=['Website', 'Order ID', 'ASIN'])

        assert summary.orders == ()
        assert summary.rows_read == 0

    def test_a_wrong_header_with_no_rows_is_still_refused(self):
        with pytest.raises(ValidationError) as caught:
            summarize([], fieldnames=['Foo', 'Bar'])

        assert 'Order ID' in caught.value.message

    def test_fieldnames_beat_the_rows_when_both_are_given(self):
        summary = summarize(
            [{'Website': 'www.amazon.com', 'Order ID': '111-2223334-5556667'}],
            fieldnames=['Website', 'Order ID'],
        )

        assert len(summary.orders) == 1
