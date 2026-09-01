"""One physical purchase, captured twice, recorded once (feature 033, issue #129).

The catalog has two ways to record a purchase and they used to be blind to each
other. A product captured from its listing page and then captured again as a line
of the order it came on produced **two** purchases for one physical purchase --
doubled spend, doubled quantity-on-order, and a reorder list that reads wrong.

The two halves are tested separately because they are separate mechanisms:

* **The order path** (US1) gains a *candidate*: a purchase for the same vendor
  and item carrying no supplier order number, close enough in date to be the same
  one. The review asks; the operator answers; adopting stamps the order's number
  and line number onto the row that already exists rather than writing a second.
* **The single-listing path** (US2) already asks a duplicate question, but only
  about purchases recorded on the same calendar day. An operator's typed date is
  the value least likely to match the vendor's -- the case that found this was
  four days out -- so it gains one more arm, restricted to rows that carry an
  order number.

**The window is where the operator is asked, not where anything is merged.**
Nothing here joins two rows without an answer, which is why ninety days is safe.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.catalog_service import (
    AMAZON_ORDER_VENDOR,
    AMAZON_VENDOR,
    CatalogService,
)
from app.exceptions import CaptureDecisionRequired, ValidationError
from app.models import (
    AMAZON_PAYLOAD_VENDOR,
    AMAZON_PAYLOAD_VERSION,
    AmazonOrder,
    OrderLineState,
)

pytestmark = pytest.mark.unit


# The live case from issue #129, kept as the values it actually had.
ASIN = 'B0G43FCHFX'
ORDER_NUMBER = '111-9281973-9357866'
LISTING_DATE = datetime(2026, 7, 27)
ORDER_DATE_TEXT = 'July 23, 2026'
ORDER_DATE = datetime(2026, 7, 23)


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def build_order(lines=None, order_number=ORDER_NUMBER, order_date=ORDER_DATE_TEXT):
    """An Amazon order as the capture agent reads one off the order page."""
    return AmazonOrder.from_payload({
        'version': AMAZON_PAYLOAD_VERSION,
        'vendor': AMAZON_PAYLOAD_VENDOR,
        'order_number': order_number,
        'order_date': order_date,
        'source_url': (
            'https://www.amazon.com/your-orders/order-details'
            f'?orderID={order_number}'
        ),
        'lines': lines if lines is not None else [
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
        ],
    })


def decisions_for(order, **extra):
    """Include every line, as the review's checkboxes default to."""
    return {
        line.form_key: dict({'include': True}, **extra)
        for line in order.lines
    }


def capture_listing(catalog, item_id=ASIN, order_date=LISTING_DATE,
                    vendor=AMAZON_VENDOR, **kwargs):
    """Record the purchase a single-listing capture writes."""
    return catalog.capture_order(
        vendor=vendor,
        vendor_item_id=item_id,
        listing_title='ELECROW ESP32 E-Ink 4.2"',
        url=f'https://www.amazon.com/dp/{item_id}',
        quantity=1,
        unit_price='37.59',
        order_date=order_date,
        **kwargs,
    )


class TestTheReportedFailure:
    """FR-023: the exact sequence that produced purchases 10 and 11."""

    def test_capturing_the_order_adopts_the_listing_capture(self, catalog):
        """One purchase, not two -- issue #129 in a single test."""
        listing = capture_listing(catalog)
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        history = catalog.get_purchase_history(listing.product_id)
        assert len(history) == 1
        adopted = history[0]
        assert adopted.id == listing.id
        assert adopted.supplier_order_reference == ORDER_NUMBER
        assert adopted.order_line_number == order.lines[0].line_number
        assert result.purchases_adopted == (listing.id,)
        assert result.purchase_ids == ()


class TestTheOtherTwoAnswers:
    """FR-008a: the operator answers, and an unanswered line refuses the order."""

    def test_separate_records_a_second_purchase(self, catalog):
        """The operator says these are two purchases, so two is what is recorded."""
        listing = capture_listing(catalog)
        before = catalog.get_purchase(listing.id)
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='separate'),
        )

        history = catalog.get_purchase_history(listing.product_id)
        assert len(history) == 2
        assert len(result.purchase_ids) == 1
        assert result.purchases_adopted == ()

        # The first is left entirely alone -- including the NULLs that make it a
        # candidate, so it is still one for a different order.
        after = catalog.get_purchase(listing.id)
        assert after.supplier_order_reference is None
        assert after.order_line_number is None
        assert after.order_date == before.order_date
        assert after.quantity == before.quantity
        assert after.unit_price == before.unit_price

    def test_an_unanswered_line_refuses_the_capture(self, catalog):
        """A question about an order, so the whole order waits for the answer."""
        listing = capture_listing(catalog)
        order = build_order()

        with pytest.raises(ValidationError) as excinfo:
            catalog.capture_order_lines(
                order, AMAZON_ORDER_VENDOR, decisions_for(order)
            )

        assert excinfo.value.field == f'same_purchase[{order.lines[0].form_key}]'
        assert len(catalog.get_purchase_history(listing.product_id)) == 1

    def test_nothing_at_all_is_written_including_the_other_lines(self, catalog):
        """FR-016: half an order is worse than none."""
        listing = capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
            {'asin': 'B0OTHERAAA', 'title': 'Something else',
             'quantity': 2, 'unit_price': '4.50'},
        ])

        with pytest.raises(ValidationError):
            catalog.capture_order_lines(
                order, AMAZON_ORDER_VENDOR, decisions_for(order)
            )

        # The second line would have created a product and a purchase.
        assert len(catalog.list_products()) == 1
        assert len(catalog.get_purchase_history(listing.product_id)) == 1

    def test_an_unanswered_line_the_operator_excluded_refuses_nothing(self, catalog):
        """FR-008b: nothing was going to be written for it anyway."""
        listing = capture_listing(catalog)
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            {order.lines[0].form_key: {'include': False}},
        )

        assert result.lines_excluded == 1
        assert result.purchases_adopted == ()
        after = catalog.get_purchase(listing.id)
        assert after.supplier_order_reference is None


class TestWhatIsNotACandidate:
    """The boundaries. Every one of these must capture as it does today."""

    def test_a_purchase_outside_the_window_is_not_offered(self, catalog):
        """FR-003: buying the same thing again in April is a second purchase."""
        listing = capture_listing(catalog, order_date=ORDER_DATE - timedelta(days=100))
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, decisions_for(order)
        )

        assert len(result.purchase_ids) == 1
        assert result.purchases_adopted == ()
        assert len(catalog.get_purchase_history(listing.product_id)) == 2

    def test_the_review_raises_no_question_outside_the_window(self, catalog):
        capture_listing(catalog, order_date=ORDER_DATE - timedelta(days=100))

        review = catalog.review_order(build_order(), AMAZON_ORDER_VENDOR)

        assert review.lines[0].candidate is None
        assert review.lines[0].needs_same_purchase_answer is False

    def test_a_purchase_carrying_another_orders_number_is_not_offered(self, catalog):
        """FR-002: it is already a line of an order, and not of this one."""
        first = build_order(order_number='111-0000000-0000000')
        catalog.capture_order_lines(
            first, AMAZON_ORDER_VENDOR, decisions_for(first)
        )

        second = build_order()
        review = catalog.review_order(second, AMAZON_ORDER_VENDOR)

        assert review.lines[0].candidate is None
        assert review.lines[0].state is OrderLineState.MATCHED

    def test_a_purchase_with_no_order_date_is_not_offered(self, catalog):
        """FR-006: a candidate cannot be dated against nothing."""
        product = catalog.create_product(description='Undated widget')
        catalog.record_purchase(
            product.id, vendor=AMAZON_VENDOR, vendor_item_id=ASIN,
            order_date=None,
        )

        review = catalog.review_order(build_order(), AMAZON_ORDER_VENDOR)

        assert review.lines[0].candidate is None

    def test_an_order_with_no_date_offers_nothing(self, catalog):
        """The other half of FR-006, and the one a page-read order can produce."""
        capture_listing(catalog)

        review = catalog.review_order(
            build_order(order_date=''), AMAZON_ORDER_VENDOR
        )

        assert review.lines[0].candidate is None

    def test_another_vendors_purchase_is_not_offered(self, catalog):
        """The same item id from a different shop is a different thing."""
        capture_listing(catalog, vendor='eBay')

        review = catalog.review_order(build_order(), AMAZON_ORDER_VENDOR)

        assert review.lines[0].candidate is None


class TestOneCandidatePerLine:
    """FR-004, FR-005: a row is claimable once, and exactness wins."""

    def test_two_lines_of_one_item_are_both_offered_it(self, catalog):
        """Both are asked; which one takes it is settled when they answer.

        Offering it to only the first line looks tidier and is wrong: exclude
        that line and the second captures with no question raised, writing the
        duplicate this feature exists to prevent. PR #144 review.
        """
        listing = capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
        ])

        review = catalog.review_order(order, AMAZON_ORDER_VENDOR)

        offered = [line for line in review.lines if line.candidate is not None]
        assert len(offered) == 2
        assert {line.candidate.purchase_id for line in offered} == {listing.id}

    def test_excluding_the_first_line_does_not_lose_the_question(self, catalog):
        """The regression PR #144's review found, stated as a test.

        Two lines for one item, one candidate, and the operator takes the
        *second* line. The surviving line must still be asked, and adopting on it
        must leave one purchase.
        """
        listing = capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
        ])
        first, second = (line.form_key for line in order.lines)

        result = catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, {
            first: {'include': False},
            second: {'include': True, 'same_purchase': 'adopt'},
        })

        assert result.purchases_adopted == (listing.id,)
        assert result.purchase_ids == ()
        assert len(catalog.get_purchase_history(listing.product_id)) == 1

    def test_and_leaving_that_survivor_unanswered_still_refuses(self, catalog):
        """The other half: the question cannot be dodged by excluding a line."""
        listing = capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
        ])
        first, second = (line.form_key for line in order.lines)

        with pytest.raises(ValidationError) as excinfo:
            catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, {
                first: {'include': False},
                second: {'include': True},
            })

        assert excinfo.value.field == f'same_purchase[{second}]'
        assert len(catalog.get_purchase_history(listing.product_id)) == 1

    def test_one_row_cannot_be_two_lines(self, catalog):
        """Both lines answer "same purchase"; only one can be right.

        The first takes it and the second records its own -- which is the true
        answer as well as the safe one, because two lines of an order are two
        purchases.
        """
        listing = capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
        ])

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        assert result.purchases_adopted == (listing.id,)
        assert len(result.purchase_ids) == 1
        history = catalog.get_purchase_history(listing.product_id)
        assert len(history) == 2
        assert sorted(
            row.order_line_number for row in history
        ) == [line.line_number for line in order.lines]

    def test_and_capturing_them_writes_one_row_and_adopts_one(self, catalog):
        listing = capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 1, 'unit_price': '37.59'},
        ])

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        assert result.purchases_adopted == (listing.id,)
        assert len(result.purchase_ids) == 1
        assert len(catalog.get_purchase_history(listing.product_id)) == 2

    def test_the_nearest_candidate_by_date_is_the_one_offered(self, catalog):
        """Two listing captures inside the window; the closer one is meant."""
        far = capture_listing(catalog, order_date=ORDER_DATE - timedelta(days=60))
        near = capture_listing(
            catalog, order_date=ORDER_DATE + timedelta(days=2),
            acknowledged_duplicate_of=None, attach_to=far.product_id,
        )

        review = catalog.review_order(build_order(), AMAZON_ORDER_VENDOR)

        assert review.lines[0].candidate.purchase_id == near.id

    def test_a_line_already_captured_exactly_takes_no_candidate(self, catalog):
        """FR-005: CAPTURED is settled first and is not a question."""
        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, decisions_for(order)
        )
        # A purchase for the same item recorded by hand afterwards. It is
        # candidate-shaped -- same vendor, same item, no order number -- and the
        # exactly-paired line must still not take it.
        product = catalog.create_product(description='A hand-recorded one')
        catalog.record_purchase(
            product.id, vendor=AMAZON_VENDOR, vendor_item_id=ASIN,
            order_date=LISTING_DATE,
        )

        review = catalog.review_order(order, AMAZON_ORDER_VENDOR)

        assert review.lines[0].state is OrderLineState.CAPTURED
        assert review.lines[0].candidate is None


class TestAdoptingPreserves:
    """FR-014, FR-015: what claiming a row must not touch."""

    def test_a_received_purchase_stays_received(self, catalog):
        listing = capture_listing(catalog)
        catalog.receive_purchase(listing.id, received_date=datetime(2026, 7, 28))
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        adopted = catalog.get_purchase(listing.id)
        assert adopted.received_date == datetime(2026, 7, 28)
        assert adopted.quantity == 1

    def test_a_tracked_count_does_not_move_and_a_low_flag_is_not_cleared(self, catalog):
        listing = capture_listing(catalog)
        catalog.set_quantity(listing.product_id, 4)
        catalog.set_stock_status(listing.product_id, 'LOW')
        before = catalog.get_product(listing.product_id)
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        after = catalog.get_product(listing.product_id)
        assert after.quantity == before.quantity
        assert after.quantity_updated_at == before.quantity_updated_at
        assert after.stock_status == before.stock_status
        assert after.stock_status_updated_at == before.stock_status_updated_at

    def test_the_product_is_not_changed_and_none_is_created(self, catalog):
        """FR-015: the purchase keeps the product the operator chose."""
        listing = capture_listing(catalog)
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        assert result.products_created == 0
        assert result.products_attached == 0
        assert catalog.get_purchase(listing.id).product_id == listing.product_id
        assert len(catalog.list_products()) == 1

    def test_the_order_date_is_not_pushed_past_a_recorded_receipt(self, catalog):
        """Nothing arrives before it is ordered -- research.md section 5."""
        listing = capture_listing(catalog, order_date=datetime(2026, 7, 20))
        catalog.receive_purchase(listing.id, received_date=datetime(2026, 7, 21))
        order = build_order()  # ordered 23 Jul, after that receipt

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        adopted = catalog.get_purchase(listing.id)
        assert adopted.order_date == datetime(2026, 7, 20)
        assert adopted.received_date == datetime(2026, 7, 21)
        assert adopted.supplier_order_reference == ORDER_NUMBER

    def test_the_order_date_is_stamped_when_it_can_be(self, catalog):
        """So the order does not report two dates for one order."""
        listing = capture_listing(catalog)

        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        assert catalog.get_purchase(listing.id).order_date == ORDER_DATE


class TestAfterAdopting:
    """What the next read of the same order says."""

    def test_a_re_capture_asks_nothing_and_writes_nothing(self, catalog):
        """SC-004: the adopted row is now an ordinary already-captured line."""
        listing = capture_listing(catalog)
        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        review = catalog.review_order(order, AMAZON_ORDER_VENDOR)
        assert review.lines[0].state is OrderLineState.CAPTURED
        assert review.lines[0].candidate is None
        assert review.lines[0].purchase_id == listing.id

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, decisions_for(order)
        )
        assert result.lines_already_captured == 1
        assert result.purchase_ids == ()
        assert len(catalog.get_purchase_history(listing.product_id)) == 1

    def test_an_adopted_row_is_not_reported_as_orphaned(self, catalog):
        """research.md section 8 -- the trap, and the assertion that catches it."""
        capture_listing(catalog)
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        assert result.orphaned == ()

    def test_the_adopted_row_joins_its_order(self, catalog):
        """An order is its purchases; the adopted one is now one of them."""
        listing = capture_listing(catalog)
        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        lines = catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)
        assert [row.id for row in lines] == [listing.id]


class TestWhatAdoptingWrites:
    """contracts section 5: order fields land, line fields are the operator's."""

    def test_the_quantity_and_price_are_left_alone_by_default(self, catalog):
        listing = capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 3, 'unit_price': '41.00'},
        ])

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        adopted = catalog.get_purchase(listing.id)
        assert adopted.quantity == 1
        assert adopted.unit_price == Decimal('37.59')

    def test_apply_change_takes_the_orders_values(self, catalog):
        """FR-009, through the mechanism a re-captured line already uses."""
        listing = capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 3, 'unit_price': '41.00'},
        ])

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt', apply_change=True),
        )

        adopted = catalog.get_purchase(listing.id)
        assert adopted.quantity == 3
        assert adopted.unit_price == Decimal('41.00')
        assert result.lines_updated == 1

    def test_the_review_offers_that_change(self, catalog):
        """has_change has to fire for an adoptable line, or the tick never renders."""
        capture_listing(catalog)
        order = build_order(lines=[
            {'asin': ASIN, 'title': 'ELECROW ESP32 E-Ink 4.2"',
             'quantity': 3, 'unit_price': '41.00'},
        ])

        review = catalog.review_order(order, AMAZON_ORDER_VENDOR)

        assert review.lines[0].has_change is True
        assert review.lines[0].candidate.quantity == 1
        assert review.lines[0].candidate.unit_price == Decimal('37.59')

    def test_an_identical_line_offers_no_change(self, catalog):
        capture_listing(catalog)

        review = catalog.review_order(build_order(), AMAZON_ORDER_VENDOR)

        assert review.lines[0].has_change is False

    def test_the_listing_address_survives_adoption(self, catalog):
        """Gap-filled only: the order page address must not replace the listing's."""
        listing = capture_listing(catalog)
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        adopted = catalog.get_purchase(listing.id)
        assert adopted.listing_url == f'https://www.amazon.com/dp/{ASIN}'

    def test_an_order_field_the_purchase_lacks_is_filled(self, catalog):
        """The other half of the same rule."""
        product = catalog.create_product(description='ELECROW ESP32 E-Ink 4.2"')
        purchase = catalog.record_purchase(
            product.id, vendor=AMAZON_VENDOR, vendor_item_id=ASIN,
            order_date=LISTING_DATE, quantity=1, unit_price='37.59',
        )
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        adopted = catalog.get_purchase(purchase.id)
        assert adopted.listing_url == order.source_url


class TestCapturingAListingAfterItsOrder:
    """US2: the direction 029's spec claimed was already covered, and was not.

    ``_find_captured_purchase`` narrows to a single calendar day. An operator
    typing the date they remember onto a listing capture will rarely land on the
    day the vendor states -- the reported case was four days out -- so the
    same-day rule let a second purchase through in silence.
    """

    def _capture_the_order(self, catalog, **extra):
        order = build_order()
        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, decisions_for(order, **extra)
        )
        return catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)[0]

    def test_a_listing_captured_days_later_raises_the_question(self, catalog):
        """FR-017, FR-018: and it names the order, not just the purchase."""
        recorded = self._capture_the_order(catalog)

        with pytest.raises(CaptureDecisionRequired) as excinfo:
            capture_listing(catalog, order_date=LISTING_DATE)

        assessment = excinfo.value.assessment
        assert assessment.has_duplicate is True
        assert assessment.duplicate_purchase_id == recorded.id
        assert assessment.duplicate_order_reference == ORDER_NUMBER
        assert assessment.duplicate_vendor == AMAZON_VENDOR

    def test_and_nothing_is_written(self, catalog):
        """The existing contract: a refused capture leaves the database alone."""
        self._capture_the_order(catalog)
        before = len(catalog.list_products())

        with pytest.raises(CaptureDecisionRequired):
            capture_listing(catalog, order_date=LISTING_DATE)

        assert len(catalog.list_products()) == before
        assert len(catalog.find_order_lines_for(AMAZON_VENDOR, ORDER_NUMBER)) == 1

    def test_acknowledging_it_records_a_separate_purchase(self, catalog):
        """FR-019, through the escape that already exists."""
        recorded = self._capture_the_order(catalog)

        second = capture_listing(
            catalog, order_date=LISTING_DATE,
            acknowledged_duplicate_of=recorded.id,
            attach_to=recorded.product_id,
        )

        assert second.id != recorded.id
        assert len(catalog.get_purchase_history(recorded.product_id)) == 2

    def test_a_hit_outside_the_window_is_not_recognized(self, catalog):
        """The same window both directions use (FR-003)."""
        self._capture_the_order(catalog)

        second = capture_listing(
            catalog, order_date=ORDER_DATE + timedelta(days=100),
            attach_to='new',
        )

        assert second.id is not None

    def test_two_listing_captures_months_apart_are_unchanged(self, catalog):
        """FR-020: the widened arm only sees rows that carry an order number.

        This is what keeps the blast radius to this feature. An ordinary repeat
        capture of a listing still meets only the same-day rule and still records
        a second purchase without a question.
        """
        first = capture_listing(catalog, order_date=datetime(2026, 1, 14))

        second = capture_listing(
            catalog, order_date=datetime(2026, 3, 2),
            attach_to=first.product_id,
        )

        assert second.id != first.id
        assert len(catalog.get_purchase_history(first.product_id)) == 2

    def test_the_same_day_rule_still_wins_where_both_could_match(self, catalog):
        """The existing query runs first and is not widened, only supplemented."""
        same_day = capture_listing(catalog, order_date=ORDER_DATE)
        # The order capture sees that row as a candidate too; the operator says
        # it is a separate purchase, which is what leaves both rows in place for
        # the listing capture below to choose between.
        self._capture_the_order(catalog, same_purchase='separate')

        with pytest.raises(CaptureDecisionRequired) as excinfo:
            capture_listing(
                catalog, order_date=ORDER_DATE, attach_to=same_day.product_id,
            )

        assert excinfo.value.assessment.duplicate_purchase_id == same_day.id
        assert excinfo.value.assessment.duplicate_order_reference is None

    def test_the_json_representation_names_the_order(self, catalog, client):
        """The assessment reaches /api/capture unchanged in shape, plus one key."""
        recorded = self._capture_the_order(catalog)

        response = client.post('/api/capture', json={
            'url': f'https://www.amazon.com/dp/{ASIN}',
            'order_date': LISTING_DATE.strftime('%Y-%m-%d'),
        })

        assert response.status_code == 409
        assessment = response.get_json()['assessment']
        assert assessment['has_duplicate'] is True
        assert assessment['duplicate_purchase_id'] == recorded.id
        assert assessment['duplicate_order_reference'] == ORDER_NUMBER


class TestTheOtherTwoVendors:
    """FR-021: the recognition is vendor-agnostic, and these prove it.

    **No production code exists for these.** The candidate lookup asks for a
    vendor name, a vendor item id and an order date, and all three are written
    identically by every path -- so nothing about it is Amazon-shaped and nothing
    about it belongs on :class:`OrderVendor`. If either of these ever needs a
    branch, that seam is in the wrong place and should be re-cut rather than
    branched (029 FR-037).
    """

    def test_a_mcmaster_part_captured_from_its_page_is_adopted(self, catalog):
        from tests.unit.test_mcmaster_capture import build_order as build_mcmaster
        from app.catalog_service import MCMASTER_ORDER_VENDOR, MCMASTER_VENDOR

        listing = catalog.capture_order(
            vendor=MCMASTER_VENDOR,
            vendor_item_id='3103A21',
            url='https://www.mcmaster.com/3103A21/',
            quantity=1,
            unit_price='10.23',
            order_date=datetime(2025, 11, 20),
        )
        order = build_mcmaster()

        result = catalog.capture_order_lines(
            order, MCMASTER_ORDER_VENDOR,
            {
                line.form_key: dict(
                    {'include': True},
                    **({'same_purchase': 'adopt'}
                       if line.part_number == '3103A21' else {}),
                )
                for line in order.lines
            },
        )

        assert result.purchases_adopted == (listing.id,)
        adopted = catalog.get_purchase(listing.id)
        assert adopted.supplier_order_reference == 'MISC-AND-GRINDER'
        assert adopted.order_line_number == 1
        assert len(catalog.get_purchase_history(listing.product_id)) == 1

    def test_a_digikey_part_captured_from_its_page_is_adopted(self, catalog):
        import json
        from pathlib import Path

        from app.catalog_service import DIGIKEY_ORDER_VENDOR, DIGIKEY_VENDOR
        from app.models import DigiKeyOrder
        from tests.unit.test_digikey_capture import FakeDigiKey

        fixtures = Path(__file__).resolve().parents[1] / 'fixtures' / 'digikey'
        order = DigiKeyOrder.from_payload(
            json.loads((fixtures / 'salesorder.json').read_text(),
                       parse_float=Decimal)
        )

        listing = catalog.capture_order(
            vendor=DIGIKEY_VENDOR,
            vendor_item_id='1866-3027-ND',
            url='https://www.digikey.com/en/products/detail/1866-3027-ND',
            quantity=5,
            unit_price='6.50',
            order_date=datetime(2026, 8, 4),
        )

        result = catalog.capture_order_lines(
            order, DIGIKEY_ORDER_VENDOR,
            {
                line.form_key: dict(
                    {'include': True},
                    **({'same_purchase': 'adopt'}
                       if line.digikey_part_number == '1866-3027-ND' else {}),
                )
                for line in order.lines
            },
            FakeDigiKey(),
        )

        assert result.purchases_adopted == (listing.id,)
        adopted = catalog.get_purchase(listing.id)
        assert adopted.supplier_order_reference == order.sales_order_number
        assert adopted.order_line_number == 1
        assert len(catalog.get_purchase_history(listing.product_id)) == 1


class TestTheReviewAndTheCaptureAgree:
    """They must offer and demand the same answers, or a capture is unresolvable.

    ``capture_order_lines`` derives an order date for an order the vendor did not
    date -- the arrival date, or today -- so that a backfilled purchase is not
    recorded as ordered and received on contradicting days. ``review_order`` has
    no such fallback. Matching candidates on the derived date would find rows the
    review never showed, and refuse the capture over a question the re-rendered
    page has no control to answer.
    """

    def test_an_undated_order_asks_nothing_and_captures(self, catalog):
        listing = capture_listing(catalog)
        order = build_order(order_date='')

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR, decisions_for(order)
        )

        assert len(result.purchase_ids) == 1
        assert result.purchases_adopted == ()
        assert len(catalog.get_purchase_history(listing.product_id)) == 2

    def test_every_line_the_review_asks_about_can_be_answered(self, catalog):
        """The general form: what the review asks is what the capture reads."""
        capture_listing(catalog)
        order = build_order()

        review = catalog.review_order(order, AMAZON_ORDER_VENDOR)
        asked = {
            line.line.form_key for line in review.lines
            if line.needs_same_purchase_answer
        }

        # Answering exactly those keys is enough for the capture to proceed.
        decisions = decisions_for(order)
        for key in asked:
            decisions[key]['same_purchase'] = 'adopt'

        result = catalog.capture_order_lines(order, AMAZON_ORDER_VENDOR, decisions)

        assert len(result.purchases_adopted) == len(asked)


class TestAContradictedLineCarryingACandidate:
    """Two questions on one line, and the first one settles the second.

    A candidate is found by vendor item id alone. CONFLICT means that id has
    probably been recycled for a different part -- in which case a purchase
    recorded under it belongs to the *old* part and cannot be this line's. Only
    "same thing, attach" makes the two answers coherent.

    Amazon can never reach this: its order page states no manufacturer part
    number, so a line can never contradict a product's. DigiKey can.
    """

    def _digikey(self, catalog):
        import json
        from pathlib import Path

        from app.catalog_service import DIGIKEY_ORDER_VENDOR, DIGIKEY_VENDOR
        from app.models import DigiKeyOrder
        from tests.unit.test_digikey_capture import FakeDigiKey

        fixtures = Path(__file__).resolve().parents[1] / 'fixtures' / 'digikey'
        order = DigiKeyOrder.from_payload(
            json.loads((fixtures / 'salesorder.json').read_text(),
                       parse_float=Decimal)
        )
        # The part number names a product whose MPN contradicts the line.
        catalog.create_product(
            description='Something else entirely',
            manufacturer_part_number='WIDGET-99',
            identifiers=[
                {'id_type': 'DISTRIBUTOR', 'value': '1866-3027-ND',
                 'vendor': DIGIKEY_VENDOR},
                {'id_type': 'MPN', 'value': 'WIDGET-99'},
            ],
        )
        listing = catalog.capture_order(
            vendor=DIGIKEY_VENDOR,
            vendor_item_id='1866-3027-ND',
            url='https://www.digikey.com/en/products/detail/1866-3027-ND',
            quantity=5, unit_price='6.50',
            order_date=datetime(2026, 8, 4),
            attach_to='new',
        )
        return order, listing, DIGIKEY_ORDER_VENDOR, FakeDigiKey()

    def _decisions(self, order, conflicted, **extra):
        return {
            line.form_key: dict(
                {'include': True},
                **(extra if line.digikey_part_number == conflicted else {}),
            )
            for line in order.lines
        }

    def test_the_review_asks_both_questions(self, catalog):
        order, listing, vendor, client = self._digikey(catalog)

        review = catalog.review_order(order, vendor, client)
        line = review.lines[0]

        assert line.state is OrderLineState.CONFLICT
        assert line.candidate is not None
        assert line.candidate.purchase_id == listing.id

    def test_separate_plus_adopt_is_refused(self, catalog):
        """"A different part" and "the same purchase" cannot both be true."""
        order, listing, vendor, client = self._digikey(catalog)

        with pytest.raises(ValidationError) as excinfo:
            catalog.capture_order_lines(
                order, vendor,
                self._decisions(order, '1866-3027-ND',
                                resolution='separate', same_purchase='adopt'),
                client,
            )

        assert excinfo.value.field.startswith('resolution[')
        assert len(catalog.get_purchase_history(listing.product_id)) == 1
        assert catalog.get_purchase(listing.id).supplier_order_reference is None

    def test_a_blank_resolution_plus_adopt_is_refused(self, catalog):
        """The adopt branch used to skip the only check that reads it."""
        order, listing, vendor, client = self._digikey(catalog)

        with pytest.raises(ValidationError) as excinfo:
            catalog.capture_order_lines(
                order, vendor,
                self._decisions(order, '1866-3027-ND', same_purchase='adopt'),
                client,
            )

        assert excinfo.value.field.startswith('resolution[')
        assert catalog.get_purchase(listing.id).supplier_order_reference is None

    def test_attach_plus_adopt_claims_the_row(self, catalog):
        """The one coherent combination: the id was not recycled after all."""
        order, listing, vendor, client = self._digikey(catalog)
        products_before = len(catalog.list_products())

        result = catalog.capture_order_lines(
            order, vendor,
            self._decisions(order, '1866-3027-ND',
                            resolution='attach', same_purchase='adopt'),
            client,
        )

        assert result.purchases_adopted == (listing.id,)
        adopted = catalog.get_purchase(listing.id)
        assert adopted.supplier_order_reference == order.sales_order_number
        assert adopted.product_id == listing.product_id
        # The contradicted product is left entirely alone, and the other line of
        # the order still creates its own.
        assert len(catalog.list_products()) == products_before + 1

    def test_separate_without_adopting_still_works(self, catalog):
        """The existing CONFLICT path is unchanged when the row is not claimed."""
        order, listing, vendor, client = self._digikey(catalog)

        result = catalog.capture_order_lines(
            order, vendor,
            self._decisions(order, '1866-3027-ND',
                            resolution='separate', same_purchase='separate'),
            client,
        )

        assert result.purchases_adopted == ()
        assert len(result.purchase_ids) == 2
        assert catalog.get_purchase(listing.id).supplier_order_reference is None


class TestAdoptingABackfilledOrder:
    """An adopted line arrives like any other (031 FR-024).

    The review renders the same "arrived" box for an adoptable line, and the
    order-level box ticks every one of them -- so backfilling a delivered order
    is the natural way to reach an adoption. Dropping the tick left the purchase
    on order for ever and under-counted the flash. PR #144 review.
    """

    def test_an_adopted_line_marked_arrived_is_received(self, catalog):
        listing = capture_listing(catalog)
        assert catalog.get_purchase(listing.id).received_date is None
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt', arrived=True),
            arrived_date='2026-07-30',
        )

        adopted = catalog.get_purchase(listing.id)
        assert adopted.received_date == datetime(2026, 7, 30)
        assert result.lines_arrived == 1

    def test_a_blank_arrival_date_falls_back_to_the_orders_own(self, catalog):
        """031 FR-026, and never to today -- the same rule the create path has."""
        listing = capture_listing(catalog)
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt', arrived=True),
        )

        assert catalog.get_purchase(listing.id).received_date == ORDER_DATE

    def test_an_unticked_line_stays_outstanding(self, catalog):
        listing = capture_listing(catalog)
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt'),
        )

        assert catalog.get_purchase(listing.id).received_date is None
        assert result.lines_arrived == 0

    def test_an_already_received_candidate_keeps_its_own_receipt(self, catalog):
        """FR-014 asks that a receipt survive, not that a fresh one be dropped."""
        listing = capture_listing(catalog)
        catalog.receive_purchase(listing.id, received_date=datetime(2026, 7, 28))
        order = build_order()

        result = catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt', arrived=True),
            arrived_date='2026-07-30',
        )

        adopted = catalog.get_purchase(listing.id)
        assert adopted.received_date == datetime(2026, 7, 28)
        # Nothing was written, so nothing is counted.
        assert result.lines_arrived == 0

    def test_arriving_moves_no_count_and_clears_no_flag(self, catalog):
        """031 FR-028: goods delivered long ago have already been consumed."""
        listing = capture_listing(catalog)
        catalog.set_quantity(listing.product_id, 4)
        catalog.set_stock_status(listing.product_id, 'LOW')
        before = catalog.get_product(listing.product_id)
        order = build_order()

        catalog.capture_order_lines(
            order, AMAZON_ORDER_VENDOR,
            decisions_for(order, same_purchase='adopt', arrived=True),
        )

        after = catalog.get_product(listing.product_id)
        assert after.quantity == before.quantity
        assert after.quantity_updated_at == before.quantity_updated_at
        assert after.stock_status == before.stock_status
        assert after.stock_status_updated_at == before.stock_status_updated_at
