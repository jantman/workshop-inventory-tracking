"""Recording an order that has already arrived (feature 031, US3).

Backfilling means running an order placed two years ago through the same review
as one placed this morning. The only thing that differs is that this one has
already turned up, and saying so at capture is what keeps the two screens that
answer *what is still on its way* -- the captured-orders list and the reorder
list -- telling the truth afterwards.

**Two of the requirements here are true by construction and false the moment
somebody refactors.** FR-028 (a counted product does not move) holds only
because a purchase born with a ``received_date`` never passes through
``receive_purchase``; FR-030 (a re-capture does not re-date a delivered line)
holds only because ``capture_order_lines`` settles already-captured lines before
the include gate. Nothing in the code *states* either. These tests are the only
thing that will notice.

Driven through Amazon because it is the cheapest order to build, plus one pass
through McMaster to prove the argument is threaded by the vendor-named wrappers
too. The flow itself is one implementation for all three vendors (029 FR-036),
so what is tested here is the flow, not the vendor.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from app.catalog_service import (
    AMAZON_ORDER_VENDOR,
    AMAZON_VENDOR,
    MCMASTER_VENDOR,
    CatalogService,
)
from app.exceptions import ValidationError
from app.models import (
    AMAZON_PAYLOAD_VENDOR,
    AMAZON_PAYLOAD_VERSION,
    MCMASTER_PAYLOAD_VENDOR,
    MCMASTER_PAYLOAD_VERSION,
    AmazonOrder,
    IdentifierType,
    McMasterOrder,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def build_order(lines=None, **overrides):
    """An Amazon order dated well in the past -- a backfill's raw material."""
    body = {
        'version': AMAZON_PAYLOAD_VERSION,
        'vendor': AMAZON_PAYLOAD_VENDOR,
        'order_number': '111-2223334-5556667',
        'order_date': 'March 4, 2024',
        'source_url': 'https://www.amazon.com/your-orders/order-details'
                      '?orderID=111-2223334-5556667',
        'lines': lines if lines is not None else [
            {'asin': 'B0BACK0001', 'title': 'Digital Calipers', 'unit_price': '9.99'},
            {'asin': 'B0BACK0002', 'title': 'Heat Shrink Kit',
             'quantity': 3, 'unit_price': '13.95'},
        ],
    }
    body.update(overrides)
    order = AmazonOrder.from_payload(body)
    assert order is not None
    return order


def take_all(order, **extra):
    return {
        line.form_key: dict({'include': True}, **extra)
        for line in order.lines
    }


def purchases_for(catalog, order_number='111-2223334-5556667',
                  vendor=AMAZON_VENDOR):
    return catalog.find_order_lines_for(vendor, order_number)


class TestTheDateThatGetsRecorded:
    def test_a_ticked_line_records_the_date_given(self, catalog):
        """FR-024."""
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2024-03-11',
        )

        lines = purchases_for(catalog)
        assert len(lines) == 2
        assert all(p.received_date == datetime(2024, 3, 11) for p in lines)

    def test_the_result_counts_what_it_recorded_as_arrived(self, catalog):
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2024-03-11',
        )

        assert result.lines_arrived == 2

    def test_a_blank_date_falls_back_to_the_orders_own(self, catalog):
        """FR-026 -- and the half that matters is that it is not today."""
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='',
        )

        lines = purchases_for(catalog)
        assert all(p.received_date == p.order_date for p in lines)
        assert all(p.received_date.year == 2024 for p in lines), (
            'a 2024 delivery recorded in 2026 must not be dated 2026'
        )

    def test_a_blank_date_is_never_today(self, catalog):
        """The failure this whole feature exists to avoid, stated on its own."""
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
        )

        today = datetime.now().date()
        assert all(
            p.received_date.date() != today for p in purchases_for(catalog)
        )

    def test_a_date_before_the_order_date_is_refused(self, catalog):
        """The same rule receiving already enforces, so the two agree."""
        order = build_order()

        with pytest.raises(ValidationError):
            catalog.capture_order_lines(
                order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
                arrived_date='2024-03-01',
            )

    def test_and_a_refusal_writes_nothing_at_all(self, catalog):
        """Validated before the session opens, so there is no half-order."""
        order = build_order()

        with pytest.raises(ValidationError):
            catalog.capture_order_lines(
                order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
                arrived_date='2024-03-01',
            )

        assert catalog.search_products() == []
        assert purchases_for(catalog) == []

    def test_an_unreadable_date_is_refused_rather_than_ignored(self, catalog):
        order = build_order()

        with pytest.raises(ValidationError):
            catalog.capture_order_lines(
                order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
                arrived_date='last thursday',
            )


class TestNotTicked:
    def test_an_ordinary_capture_is_still_outstanding(self, catalog):
        """FR-025. A present-day capture must be the capture that shipped in 029."""
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order),
        )

        assert result.lines_arrived == 0
        assert all(p.received_date is None for p in purchases_for(catalog))

    def test_a_date_without_a_tick_records_nothing_as_arrived(self, catalog):
        """The date is the order's; the ticks are what select lines."""
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order),
            arrived_date='2024-03-11',
        )

        assert all(p.received_date is None for p in purchases_for(catalog))

    def test_a_line_can_be_held_back(self, catalog):
        """FR-029 -- one item was back-ordered and never turned up."""
        order = build_order()
        decisions = take_all(order, arrived=True)
        decisions[order.lines[1].form_key]['arrived'] = False

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, decisions, arrived_date='2024-03-11',
        )

        lines = purchases_for(catalog)
        assert result.lines_arrived == 1
        assert sorted(p.received_date is None for p in lines) == [False, True]


class TestTheProductIsLeftAlone:
    """FR-028, and the reason is worth repeating: goods delivered two years ago
    have already been used, and a low flag set last month is a statement about
    today's shelf. Receiving does move both. Backfilling must not.
    """

    def _tracked_and_flagged(self, catalog):
        """A product that already exists, is counted, and is flagged low."""
        first = build_order(lines=[
            {'asin': 'B0BACK0001', 'title': 'Digital Calipers', 'unit_price': '9.99'},
        ])
        catalog.capture_order_lines(first, AMAZON_ORDER_VENDOR, take_all(first))
        product = catalog.find_product_by_identifier(
            'B0BACK0001', id_type=IdentifierType.VENDOR.value, vendor=AMAZON_VENDOR,
        )
        catalog.set_quantity(product.id, 4)
        catalog.set_stock_status(product.id, 'low')
        return catalog.get_product(product.id)

    def test_a_counted_quantity_does_not_move(self, catalog):
        before = self._tracked_and_flagged(catalog)

        second = build_order(order_number='111-9999999-9999999', lines=[
            {'asin': 'B0BACK0001', 'title': 'Digital Calipers',
             'quantity': 5, 'unit_price': '9.99'},
        ])
        catalog.capture_order_lines(
            second, AMAZON_ORDER_VENDOR, take_all(second, arrived=True),
            arrived_date='2024-03-11',
        )

        after = catalog.get_product(before.id)
        assert after.quantity == 4, (
            'an arrived capture must not add to a count; if this moved, the '
            'implementation went through receive_purchase and should not have'
        )

    def test_the_counts_age_does_not_move_either(self, catalog):
        before = self._tracked_and_flagged(catalog)

        second = build_order(order_number='111-9999999-9999999', lines=[
            {'asin': 'B0BACK0001', 'title': 'Digital Calipers', 'unit_price': '9.99'},
        ])
        catalog.capture_order_lines(
            second, AMAZON_ORDER_VENDOR, take_all(second, arrived=True),
            arrived_date='2024-03-11',
        )

        after = catalog.get_product(before.id)
        assert after.quantity_updated_at == before.quantity_updated_at

    def test_a_manual_low_flag_is_not_cleared(self, catalog):
        before = self._tracked_and_flagged(catalog)

        second = build_order(order_number='111-9999999-9999999', lines=[
            {'asin': 'B0BACK0001', 'title': 'Digital Calipers', 'unit_price': '9.99'},
        ])
        catalog.capture_order_lines(
            second, AMAZON_ORDER_VENDOR, take_all(second, arrived=True),
            arrived_date='2024-03-11',
        )

        after = catalog.get_product(before.id)
        assert after.stock_status == before.stock_status
        assert after.stock_status_updated_at == before.stock_status_updated_at


class TestWhatTheDerivedScreensSay:
    """FR-027. Neither is stored, so both follow from received_date alone -- but
    that is asserted here rather than assumed, because it is the whole point.
    """

    def test_the_order_reads_complete(self, catalog):
        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2024-03-11',
        )

        captured = catalog.find_captured_orders()

        assert len(captured) == 1
        assert captured[0].outstanding_count == 0
        assert captured[0].is_complete

    def test_an_ordinary_capture_still_reads_outstanding(self, catalog):
        order = build_order()
        catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, take_all(order))

        captured = catalog.find_captured_orders()

        assert captured[0].outstanding_count == 2
        assert not captured[0].is_complete

    def test_nothing_is_reported_as_on_the_way(self, catalog):
        """A backfilled product must not be marked on order on the reorder list."""
        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2024-03-11',
        )
        product = catalog.find_product_by_identifier(
            'B0BACK0001', id_type=IdentifierType.VENDOR.value, vendor=AMAZON_VENDOR,
        )
        catalog.set_stock_status(product.id, 'low')

        rows = [r for r in catalog.get_reorder_products()
                if r['product'].id == product.id]

        assert len(rows) == 1
        assert rows[0]['is_on_order'] is False
        assert rows[0]['outstanding'] == []


class TestRecapture:
    def test_a_delivered_line_is_not_re_dated(self, catalog):
        """FR-030. True only because already-captured lines are settled before
        the include gate -- an ordering this suite exists to hold in place.
        """
        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2024-03-11',
        )

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2026-08-28',
        )

        lines = purchases_for(catalog)
        assert len(lines) == 2
        assert all(p.received_date == datetime(2024, 3, 11) for p in lines)

    def test_and_records_nothing_new(self, catalog):
        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2024-03-11',
        )

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2024-03-11',
        )

        assert result.purchase_ids == ()
        assert result.lines_arrived == 0
        assert result.lines_already_captured == 2


class TestTheOtherVendorsWrappers:
    """The flow is one implementation; the wrappers are what the routes call."""

    def test_mcmaster_threads_the_arrival_date(self, catalog):
        order = McMasterOrder.from_payload({
            'version': MCMASTER_PAYLOAD_VERSION,
            'vendor': MCMASTER_PAYLOAD_VENDOR,
            'source_url': 'https://www.mcmaster.com/order-history/order/6a5ffba81f17e12ac4fb7d70',
            'order_number': 'BACKFILL-2024',
            'order_id': '6a5ffba81f17e12ac4fb7d70',
            'order_date': 'March 4, 2024',
            'lines': [{
                'line_number': 1,
                'part_number': '3103A21',
                'description': 'Steel Pilot For Changeable-Pilot Counterbores',
                'packs': 1,
                'pack_price': '10.23',
            }],
        })
        assert order is not None

        catalog.capture_mcmaster_order(
            order, take_all(order, arrived=True), arrived_date='2024-03-20',
        )

        lines = purchases_for(catalog, 'BACKFILL-2024', MCMASTER_VENDOR)
        assert len(lines) == 1
        assert lines[0].received_date == datetime(2024, 3, 20)


class TestDigiKeyWhoseOrderDateCarriedAnOffset:
    """The crash found in review of PR #128.

    DigiKey publishes real UTC offsets (`2026-08-07T17:34:04.332-05:00`), while
    an arrival date typed into an ``<input type="date">`` parses naive. Comparing
    the two raised ``TypeError``, which is not a ``ValidationError`` and so went
    straight past the confirm route's handler as a 500 -- losing the capture the
    operator had just reviewed.

    Nothing in this suite reached it before, because the two vendors it drove
    both produce naive order dates. So this class drives **DigiKey**, and it
    drives it through the route, which is where the 500 actually happened.
    """

    def test_the_parsed_order_date_is_naive(self):
        """The invariant the fix rests on: a payload parser never returns an
        aware datetime, because no column it can reach keeps one.
        """
        import json
        from pathlib import Path

        from app.models import DigiKeyOrder

        fixtures = Path(__file__).resolve().parents[1] / 'fixtures' / 'digikey'
        order = DigiKeyOrder.from_payload(json.loads(
            (fixtures / 'salesorder.json').read_text(), parse_float=Decimal
        ))

        assert order.order_date is not None
        assert order.order_date.tzinfo is None

    def test_the_offset_is_dropped_and_not_converted(self):
        """Converting would shift new rows against every row already stored."""
        from app.models import _digikey_datetime

        parsed = _digikey_datetime('2026-08-07T17:34:04.332-05:00')

        assert parsed == datetime(2026, 8, 7, 17, 34, 4, 332000)

    def test_an_agent_sending_an_offset_is_naive_too(self):
        """The same latent crash on the page-read vendors, closed with it."""
        from app.models import _order_datetime

        parsed = _order_datetime('2026-08-07T17:34:04.332-05:00')

        assert parsed is not None and parsed.tzinfo is None

    def test_capturing_a_digikey_order_with_a_typed_arrival_date(
        self, app, client, test_storage, digikey_fixture_client,
    ):
        """The reproduction: a 500 before the fix, a capture after it."""
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client

        response = client.post('/products/digikey/orders/capture', data={
            'sales_order_number': '100882558',
            'include[1]': 'on', 'include[2]': 'on',
            'arrived[1]': 'on', 'arrived[2]': 'on',
            'arrived_date': '2026-08-11',
        })

        assert response.status_code in (200, 302), response.status_code

    def test_and_the_lines_are_recorded_delivered_on_that_date(
        self, app, client, test_storage, digikey_fixture_client,
    ):
        from app.database import Purchase

        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        client.post('/products/digikey/orders/capture', data={
            'sales_order_number': '100882558',
            'include[1]': 'on', 'include[2]': 'on',
            'arrived[1]': 'on', 'arrived[2]': 'on',
            'arrived_date': '2026-08-11',
        })

        session = test_storage._get_session()
        try:
            received = [p.received_date for p in session.query(Purchase).all()]
        finally:
            session.close()

        assert received and all(d == datetime(2026, 8, 11) for d in received)

    def test_a_blank_date_on_a_digikey_order_still_works(
        self, app, client, test_storage, digikey_fixture_client,
    ):
        """The path that never crashed -- aware against aware -- must stay right
        now that both sides are naive.
        """
        from app.database import Purchase

        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        client.post('/products/digikey/orders/capture', data={
            'sales_order_number': '100882558',
            'include[1]': 'on', 'include[2]': 'on',
            'arrived[1]': 'on', 'arrived[2]': 'on',
        })

        session = test_storage._get_session()
        try:
            rows = [(p.order_date, p.received_date) for p in session.query(Purchase).all()]
        finally:
            session.close()

        assert rows and all(ordered == arrived for ordered, arrived in rows)

    def test_an_arrival_before_a_digikey_order_date_is_still_refused(
        self, app, client, test_storage, digikey_fixture_client,
    ):
        """The comparison has to still *work*, not merely stop raising."""
        from app.database import Purchase

        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        response = client.post('/products/digikey/orders/capture', data={
            'sales_order_number': '100882558',
            'include[1]': 'on', 'include[2]': 'on',
            'arrived[1]': 'on', 'arrived[2]': 'on',
            'arrived_date': '2020-01-01',
        })

        assert response.status_code == 200
        session = test_storage._get_session()
        try:
            assert session.query(Purchase).count() == 0
        finally:
            session.close()


class TestAnOrderNobodyCanDate:
    """An order whose vendor gave no date, or gave one nothing could parse.

    `_order_datetime` treats an unparseable date as an absent one and an absent
    one as ordinary, so this is a documented state for all three vendors rather
    than a corrupt payload.

    Before the fix, `order.order_date or datetime.now()` became the **validation
    floor**, so typing the real arrival date of a genuinely old undated order --
    the exact case backfilling exists for -- was refused because the floor was
    today. Found in review of PR #128.
    """

    def test_an_undated_order_is_still_an_order(self):
        assert build_order(order_date=None) is not None

    def test_a_real_past_arrival_date_is_accepted(self, catalog):
        order = build_order(order_date=None)

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2023-06-19',
        )

        lines = purchases_for(catalog)
        assert lines and all(
            p.received_date == datetime(2023, 6, 19) for p in lines
        )

    def test_an_unparseable_date_from_the_vendor_behaves_the_same(self, catalog):
        order = build_order(order_date='sometime last spring')

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
            arrived_date='2023-06-19',
        )

        assert all(
            p.received_date == datetime(2023, 6, 19)
            for p in purchases_for(catalog)
        )

    def test_a_dated_order_still_refuses_an_impossible_arrival(self, catalog):
        """Removing the floor where there is no date must not remove it where
        there is one -- otherwise this fix trades one bug for a worse one.
        """
        order = build_order()

        with pytest.raises(ValidationError):
            catalog.capture_order_lines(
                order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
                arrived_date='2020-01-01',
            )


class TestADateTypedAndThenThoughtBetterOf:
    """The review hides the date field with `d-none` when the operator unticks
    "already arrived", and `display: none` does not keep a field out of a
    submission -- only `disabled` does.

    So a date that was typed and then abandoned still arrives at the service.
    Validating it unconditionally refused the **whole capture** over a value no
    line would have used, and the re-render then hid the offending field, so the
    operator saw an error tied to something they could no longer see and
    resubmitting reproduced it. Found in review of PR #128.

    Gated on the server rather than in the page's JavaScript, because a fix
    there is only as good as the JavaScript having run.
    """

    def test_a_stale_date_with_nothing_ticked_does_not_refuse_the_capture(
        self, catalog
    ):
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order),
            arrived_date='2020-01-01',
        )

        assert len(result.purchase_ids) == 2

    def test_and_the_lines_are_outstanding(self, catalog):
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order),
            arrived_date='2020-01-01',
        )

        assert all(p.received_date is None for p in purchases_for(catalog))

    def test_an_unreadable_stale_date_is_ignored_too(self, catalog):
        """Nothing will read it, so nothing should refuse over it."""
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, take_all(order),
            arrived_date='last thursday',
        )

        assert len(result.purchase_ids) == 2

    def test_but_a_bad_date_is_still_refused_when_a_line_claims_it(self, catalog):
        """The gate is about whether the date is used, not about giving up on it."""
        order = build_order()

        with pytest.raises(ValidationError):
            catalog.capture_order_lines(
                order, AMAZON_ORDER_VENDOR, take_all(order, arrived=True),
                arrived_date='last thursday',
            )

    def test_one_ticked_line_is_enough_to_validate(self, catalog):
        """The gate is `any`, not `all` -- a partially arrived order still has a
        date that has to be right.
        """
        order = build_order()
        decisions = take_all(order)
        decisions[order.lines[0].form_key]['arrived'] = True

        with pytest.raises(ValidationError):
            catalog.capture_order_lines(
                order, AMAZON_ORDER_VENDOR, decisions, arrived_date='2020-01-01',
            )
