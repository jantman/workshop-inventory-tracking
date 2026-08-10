"""
Unit tests for tri-state quantity, manual stock flags, and derived reorder state.

The two things worth being careful about here:

- The three quantity states must stay distinguishable everywhere (SC-007).
- FR-029 is asymmetric. A threshold-derived low clears itself once a receipt
  updates the count; a manually flagged product stays flagged until something
  clears it. Both halves are tested, because the second one is the half that
  quietly does not happen if nobody writes the line of code.
"""

from datetime import datetime, timedelta

import pytest

from app.catalog_service import CatalogService
from app.database import Product
from app.exceptions import ItemNotFoundError, ValidationError
from app.product.routes import relative_age


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


def backdate(service, product_id, **fields):
    """Write a timestamp column directly, bypassing the service.

    Every path that records an age writes ``datetime.now()``, so "counted three
    months ago" and "flagged two years ago" are unreachable through the service
    or the UI. The tests that need one write the column through a session and
    then exercise the service against it (research.md, "How a test backdates a
    timestamp").
    """
    session = service.Session()
    try:
        product = session.query(Product).filter(Product.id == product_id).one()
        for name, value in fields.items():
            setattr(product, name, value)
        session.commit()
    finally:
        session.close()


class TestThreeQuantityStates:
    """Not tracked, none on hand, and a count -- all three reachable"""

    def test_a_new_product_is_not_tracked(self, service):
        product = service.create_product(description='x')
        assert product.quantity is None
        assert product.is_tracked is False

    def test_zero_is_tracked_and_is_not_the_same_as_untracked(self, service):
        product = service.create_product(description='x')
        counted = service.set_quantity(product.id, 0)

        assert counted.quantity == 0
        assert counted.is_tracked is True

    def test_a_count_is_stored(self, service):
        product = service.create_product(description='x')
        assert service.set_quantity(product.id, 7).quantity == 7

    def test_setting_null_stops_tracking(self, service):
        product = service.create_product(description='x', quantity=7)
        stopped = service.set_quantity(product.id, None)

        assert stopped.quantity is None
        assert stopped.is_tracked is False

    def test_a_negative_quantity_is_refused(self, service):
        product = service.create_product(description='x')
        with pytest.raises(ValidationError):
            service.set_quantity(product.id, -1)

    def test_a_non_numeric_quantity_is_refused(self, service):
        product = service.create_product(description='x')
        with pytest.raises(ValidationError):
            service.set_quantity(product.id, 'lots')

    def test_setting_a_quantity_on_a_missing_product_raises(self, service):
        with pytest.raises(ItemNotFoundError):
            service.set_quantity(99999, 1)


class TestQuantityTimestamp:
    def test_setting_a_count_stamps_it(self, service):
        product = service.create_product(description='x')
        assert service.set_quantity(product.id, 5).quantity_updated_at is not None

    def test_changing_a_count_restamps_it(self, service):
        product = service.create_product(description='x', quantity=5)
        original = product.quantity_updated_at
        updated = service.set_quantity(product.id, 6)
        assert updated.quantity_updated_at >= original

    def test_setting_zero_stamps_it_too(self, service):
        """Counting and finding none is still counting"""
        product = service.create_product(description='x')
        assert service.set_quantity(product.id, 0).quantity_updated_at is not None

    def test_stopping_tracking_clears_the_timestamp(self, service):
        """An age for a count that no longer exists is worse than no age"""
        product = service.create_product(description='x', quantity=5)
        stopped = service.set_quantity(product.id, None)
        assert stopped.quantity_updated_at is None

    def test_stopping_tracking_clears_the_threshold_too(self, service):
        product = service.create_product(description='x', quantity=5, reorder_threshold=2)
        assert service.set_quantity(product.id, None).reorder_threshold is None


class TestQuantityAge:
    """FR-024 -- data-model.md section 7"""

    def test_an_untracked_product_has_no_age(self, service):
        product = service.create_product(description='x')
        assert product.quantity_age is None

    def test_a_tracked_product_has_an_age(self, service):
        product = service.create_product(description='x', quantity=5)
        assert product.quantity_age is not None
        assert product.quantity_age < timedelta(minutes=1)

    def test_a_tracked_quantity_with_no_timestamp_yields_no_age_rather_than_an_error(self, service):
        product = service.create_product(description='x', quantity=5)
        product.quantity_updated_at = None
        assert product.quantity_age is None

    def test_switching_tracking_off_clears_the_age(self, service):
        product = service.create_product(description='x', quantity=5)
        assert service.set_quantity(product.id, None).quantity_age is None


class TestRelativeAgeRendering:
    """The number is never presented bare"""

    def test_no_age_reads_as_never_counted(self):
        assert relative_age(None) == 'never counted'

    def test_the_no_age_wording_can_be_overridden(self):
        """008 FR-012 -- one function renders both kinds of evidence.

        'never counted' is right for a count and wrong for a flag, which was
        certainly set; only its date was not recorded. Everything below the None
        branch is shared, so the two cannot drift into different vocabularies.
        """
        assert relative_age(None, 'at an unknown time') == 'at an unknown time'

    def test_the_override_does_not_reach_an_age_that_exists(self):
        assert relative_age(timedelta(days=240), 'at an unknown time') == '8 months ago'

    def test_minutes_read_as_just_now(self):
        assert relative_age(timedelta(minutes=5)) == 'just now'

    def test_hours(self):
        assert relative_age(timedelta(hours=3)) == '3 hours ago'

    def test_yesterday(self):
        assert relative_age(timedelta(days=1)) == 'yesterday'

    def test_days(self):
        assert relative_age(timedelta(days=9)) == '9 days ago'

    def test_months(self):
        assert relative_age(timedelta(days=240)) == '8 months ago'

    def test_years(self):
        assert relative_age(timedelta(days=800)) == '2 years ago'


class TestManualFlag:
    """FR-025 -- independent of any count"""

    def test_flagging_low(self, service):
        product = service.create_product(description='x')
        flagged = service.set_stock_status(product.id, 'low')

        assert flagged.stock_status == 'low'
        assert flagged.is_manually_low is True
        assert flagged.is_effectively_low is True

    def test_flagging_out(self, service):
        product = service.create_product(description='x')
        assert service.set_stock_status(product.id, 'out').stock_status == 'out'

    def test_an_untracked_product_can_be_flagged(self, service):
        """The operator knows things the count does not"""
        product = service.create_product(description='x')
        flagged = service.set_stock_status(product.id, 'low')

        assert flagged.quantity is None
        assert flagged.is_effectively_low is True

    def test_clearing_the_flag(self, service):
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        assert service.set_stock_status(product.id, None).stock_status is None

    def test_an_unknown_status_is_refused_with_the_valid_ones(self, service):
        product = service.create_product(description='x')
        with pytest.raises(ValidationError) as excinfo:
            service.set_stock_status(product.id, 'quite low really')
        assert 'low' in str(excinfo.value)


class TestThresholdDerivation:
    """FR-026, computed at query time"""

    def test_at_the_threshold_counts_as_low(self, service):
        product = service.create_product(description='x', quantity=2, reorder_threshold=2)
        assert product.is_threshold_low is True

    def test_below_the_threshold_counts_as_low(self, service):
        product = service.create_product(description='x', quantity=1, reorder_threshold=2)
        assert product.is_threshold_low is True

    def test_above_the_threshold_does_not(self, service):
        product = service.create_product(description='x', quantity=5, reorder_threshold=2)
        assert product.is_threshold_low is False

    def test_untracked_is_never_threshold_low(self, service):
        product = service.create_product(description='x')
        assert product.is_threshold_low is False

    def test_a_threshold_needs_a_tracked_quantity_to_be_set_at_all(self, service):
        with pytest.raises(ValidationError):
            service.create_product(description='x', reorder_threshold=2)


class TestReorderView:
    """FR-027, FR-028 -- both halves in one list, on-order marked"""

    def test_it_gathers_both_kinds_of_low(self, service):
        manual = service.create_product(description='flagged by hand')
        service.set_stock_status(manual.id, 'low')
        threshold = service.create_product(
            description='at its threshold', quantity=1, reorder_threshold=2
        )
        service.create_product(description='plenty', quantity=50, reorder_threshold=2)

        entries = service.get_reorder_products()
        assert sorted(e['product'].description for e in entries) == [
            'at its threshold', 'flagged by hand',
        ]
        assert {e['product'].id for e in entries} == {manual.id, threshold.id}

    def test_it_says_why_each_one_is_there(self, service):
        manual = service.create_product(description='flagged by hand')
        service.set_stock_status(manual.id, 'low')

        entry = service.get_reorder_products()[0]
        assert entry['is_manually_low'] is True
        assert entry['is_threshold_low'] is False

    def test_an_outstanding_order_is_marked_on_order(self, service):
        """Derived from purchase data, not recorded separately"""
        product = service.create_product(description='x', quantity=1, reorder_threshold=2)
        service.record_purchase(product.id, vendor='Amazon', order_date=datetime(2026, 1, 14))

        assert service.get_reorder_products()[0]['is_on_order'] is True

    def test_a_received_order_is_not_on_order(self, service):
        product = service.create_product(description='x', quantity=1, reorder_threshold=2)
        purchase = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14)
        )
        service.receive_purchase(purchase.id)

        entries = service.get_reorder_products()
        if entries:
            assert entries[0]['is_on_order'] is False

    def test_an_empty_reorder_list_is_an_empty_list(self, service):
        service.create_product(description='plenty', quantity=50, reorder_threshold=2)
        assert service.get_reorder_products() == []


class TestFr029BothHalves:
    """Receiving an order clears low status -- and the two halves differ"""

    def test_a_threshold_low_clears_itself_when_the_receipt_updates_the_count(self, service):
        product = service.create_product(description='x', quantity=1, reorder_threshold=5)
        assert service.get_product(product.id).is_threshold_low is True

        purchase = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), quantity=10
        )
        service.receive_purchase(purchase.id)

        after = service.get_product(product.id)
        assert after.quantity == 11
        assert after.is_threshold_low is False
        assert after.is_effectively_low is False

    def test_a_manual_flag_is_cleared_explicitly_at_receipt(self, service):
        """The half nothing else does for you"""
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        assert service.get_product(product.id).is_manually_low is True

        purchase = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14)
        )
        service.receive_purchase(purchase.id)

        after = service.get_product(product.id)
        assert after.stock_status is None
        assert after.is_manually_low is False
        assert after.is_effectively_low is False

    def test_both_halves_leave_the_reorder_list_empty(self, service):
        tracked = service.create_product(description='tracked', quantity=1, reorder_threshold=5)
        manual = service.create_product(description='manual')
        service.set_stock_status(manual.id, 'out')

        for product in (tracked, manual):
            purchase = service.record_purchase(
                product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), quantity=10
            )
            service.receive_purchase(purchase.id)

        assert service.get_reorder_products() == []

    def test_receiving_does_not_start_tracking_an_untracked_product(self, service):
        """Clearing a flag is not the same as deciding to count something"""
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')

        purchase = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), quantity=10
        )
        service.receive_purchase(purchase.id)

        assert service.get_product(product.id).quantity is None


COUNTED_IN_JANUARY = datetime(2026, 1, 14, 9, 30, 0)


class TestReceivingDoesNotVerifyACount:
    """008 FR-007 and FR-008: the number moves, the age stays where it was.

    Receiving used to stamp ``quantity_updated_at`` alongside the increment, so
    a delivery made the screen read "counted just now" when nobody had counted
    anything. Every assertion below compares the stored timestamp for
    **equality** with the seeded value, never ``>=`` and never "older than an
    hour": the weaker forms pass against exactly the bug being removed.
    """

    def _tracked_with_an_outstanding_order(self, service, quantity=4, ordered=100):
        product = service.create_product(description='M3 standoff', quantity=quantity)
        backdate(service, product.id, quantity_updated_at=COUNTED_IN_JANUARY)
        purchase = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), quantity=ordered
        )
        return product, purchase

    def test_the_count_rises_by_the_received_quantity(self, service):
        """008 FR-007 -- the increment is kept; only its dishonest half went"""
        product, purchase = self._tracked_with_an_outstanding_order(service)
        service.receive_purchase(purchase.id)

        assert service.get_product(product.id).quantity == 104

    def test_the_counted_age_does_not_move(self, service):
        """008 FR-008, SC-001 -- equality, because >= passes against the bug"""
        product, purchase = self._tracked_with_an_outstanding_order(service)
        service.receive_purchase(purchase.id)

        assert service.get_product(product.id).quantity_updated_at == COUNTED_IN_JANUARY

    def test_an_untracked_product_gains_neither_a_count_nor_an_age(self, service):
        """008 FR-009 -- receiving never begins tracking a count"""
        product = service.create_product(description='untracked')
        purchase = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), quantity=10
        )
        service.receive_purchase(purchase.id)

        after = service.get_product(product.id)
        assert after.quantity is None
        assert after.quantity_updated_at is None

    def test_a_purchase_with_no_quantity_moves_neither(self, service):
        """Nothing arrived that anyone counted, so nothing about the count changes"""
        product = service.create_product(description='M3 standoff', quantity=4)
        backdate(service, product.id, quantity_updated_at=COUNTED_IN_JANUARY)
        purchase = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14)
        )
        service.receive_purchase(purchase.id)

        after = service.get_product(product.id)
        assert after.quantity == 4
        assert after.quantity_updated_at == COUNTED_IN_JANUARY

    def test_receiving_an_already_received_purchase_moves_neither(self, service):
        """008 FR-008 -- the second receipt is a no-op for stock, as before"""
        product, purchase = self._tracked_with_an_outstanding_order(service)
        service.receive_purchase(purchase.id)
        service.receive_purchase(purchase.id)

        after = service.get_product(product.id)
        assert after.quantity == 104
        assert after.quantity_updated_at == COUNTED_IN_JANUARY


FLAGGED_TWO_YEARS_AGO = datetime(2024, 3, 5, 11, 0, 0)


class TestFlagIsDated:
    """008 FR-001 to FR-003, FR-006: the flag carries when it was set"""

    def test_flagging_records_the_moment(self, service):
        """008 FR-001"""
        product = service.create_product(description='x')
        flagged = service.set_stock_status(product.id, 'low')

        assert flagged.stock_status_updated_at is not None
        assert datetime.now() - flagged.stock_status_updated_at < timedelta(minutes=1)

    def test_an_unflagged_product_has_no_flag_date(self, service):
        product = service.create_product(description='x')
        assert product.stock_status_updated_at is None

    def test_changing_the_flag_moves_the_date(self, service):
        """008 FR-002 -- 'out' is a new assertion, not the old one"""
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, stock_status_updated_at=FLAGGED_TWO_YEARS_AGO)

        changed = service.set_stock_status(product.id, 'out')
        assert changed.stock_status == 'out'
        assert changed.stock_status_updated_at > FLAGGED_TWO_YEARS_AGO

    def test_re_asserting_the_same_flag_moves_the_date(self, service):
        """008 FR-002 -- and before this feature the press did nothing at all.

        Assigning a string equal to the stored one is no change as far as
        SQLAlchemy is concerned, so no UPDATE was emitted. The timestamp write
        is what makes re-affirming a flag -- "I have just looked, still low" --
        a real act, and it is the only way to renew evidence on a product that
        has no count to re-count.
        """
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, stock_status_updated_at=FLAGGED_TWO_YEARS_AGO)

        reasserted = service.set_stock_status(product.id, 'low')
        assert reasserted.stock_status == 'low'
        assert reasserted.stock_status_updated_at > FLAGGED_TWO_YEARS_AGO

    def test_clearing_the_flag_clears_its_date(self, service):
        """008 FR-003 -- a later flag must not inherit an older one's date"""
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')

        cleared = service.set_stock_status(product.id, None)
        assert cleared.stock_status is None
        assert cleared.stock_status_updated_at is None

    def test_flagging_again_after_a_clear_starts_a_fresh_date(self, service):
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, stock_status_updated_at=FLAGGED_TWO_YEARS_AGO)
        service.set_stock_status(product.id, None)

        reflagged = service.set_stock_status(product.id, 'low')
        assert reflagged.stock_status_updated_at > FLAGGED_TWO_YEARS_AGO

    def test_a_refused_value_leaves_both_fields_alone(self, service):
        """Validation happens before the session opens, as it always did"""
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, stock_status_updated_at=FLAGGED_TWO_YEARS_AGO)

        with pytest.raises(ValidationError):
            service.set_stock_status(product.id, 'quite low really')

        after = service.get_product(product.id)
        assert after.stock_status == 'low'
        assert after.stock_status_updated_at == FLAGGED_TWO_YEARS_AGO

    def test_receiving_clears_the_flag_and_its_date_together(self, service):
        """008 FR-006 -- no stale flag age survives to be shown later"""
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        purchase = service.record_purchase(
            product.id, vendor='Amazon', order_date=datetime(2026, 1, 14), quantity=10
        )
        service.receive_purchase(purchase.id)

        after = service.get_product(product.id)
        assert after.stock_status is None
        assert after.stock_status_updated_at is None


class TestStockStatusAge:
    """008 FR-005 -- a mirror of TestQuantityAge, because it is a mirror"""

    def test_an_unflagged_product_has_no_flag_age(self, service):
        product = service.create_product(description='x')
        assert product.stock_status_age is None

    def test_a_flagged_product_has_a_flag_age(self, service):
        product = service.create_product(description='x')
        flagged = service.set_stock_status(product.id, 'low')

        assert flagged.stock_status_age is not None
        assert flagged.stock_status_age < timedelta(minutes=1)

    def test_a_flag_with_no_date_yields_no_age_rather_than_an_error(self, service):
        """008 FR-005, SC-006 -- every row that predates this feature.

        An unrecorded age stays unrecorded and is rendered as unknown; no other
        date is substituted for it.
        """
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, stock_status_updated_at=None)

        assert service.get_product(product.id).stock_status_age is None

    def test_a_backdated_flag_reports_its_real_age(self, service):
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, stock_status_updated_at=datetime.now() - timedelta(days=800))

        assert relative_age(service.get_product(product.id).stock_status_age) == '2 years ago'

    def test_a_count_and_a_flag_are_aged_independently(self, service):
        """Two acts, two pieces of evidence, two dates"""
        product = service.create_product(description='x', quantity=5)
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, quantity_updated_at=COUNTED_IN_JANUARY)

        after = service.get_product(product.id)
        assert after.quantity_updated_at == COUNTED_IN_JANUARY
        assert after.stock_status_updated_at > COUNTED_IN_JANUARY


class TestProductJsonCarriesTheFlagDate:
    """contracts/product-json.md -- additive, shaped like quantity_updated_at"""

    def test_a_flagged_product_serializes_an_iso_date(self, service):
        product = service.create_product(description='x')
        service.set_stock_status(product.id, 'low')
        backdate(service, product.id, stock_status_updated_at=FLAGGED_TWO_YEARS_AGO)

        payload = service.get_product(product.id).to_dict()
        assert payload['stock_status'] == 'low'
        assert payload['stock_status_updated_at'] == FLAGGED_TWO_YEARS_AGO.isoformat()

    def test_an_unflagged_product_serializes_null(self, service):
        product = service.create_product(description='x')
        assert product.to_dict()['stock_status_updated_at'] is None


class TestCountingStillCountsAsCounting:
    """008 FR-010, FR-011: the boundary that makes FR-008 coherent.

    Without these, "receiving must not refresh the count's age" is one careless
    edit away from "nothing refreshes the count's age", which would silently
    break the most common way a count is kept honest -- the operator standing at
    the shelf with the things in their hand.
    """

    def test_a_typed_count_stamps_the_age(self, service):
        """008 FR-010 -- an operator entering a number is a verification"""
        product = service.create_product(description='x', quantity=4)
        backdate(service, product.id, quantity_updated_at=COUNTED_IN_JANUARY)

        counted = service.set_quantity(product.id, 6)
        assert counted.quantity == 6
        assert counted.quantity_updated_at > COUNTED_IN_JANUARY

    def test_stepping_a_count_stamps_the_age(self, service):
        """008 FR-010 -- the +/- buttons reach set_quantity and must keep doing so.

        `product-stock.js` sends them to PATCH /api/products/<id>/quantity, the
        same endpoint the typed count uses. They are not a separate path and
        must not become one.
        """
        product = service.create_product(description='x', quantity=4)
        backdate(service, product.id, quantity_updated_at=COUNTED_IN_JANUARY)

        stepped = service.set_quantity(product.id, 3)
        assert stepped.quantity == 3
        assert stepped.quantity_updated_at > COUNTED_IN_JANUARY

    def test_stopping_tracking_clears_the_count_the_age_and_the_threshold(self, service):
        """008 FR-011"""
        product = service.create_product(description='x', quantity=4, reorder_threshold=2)
        stopped = service.set_quantity(product.id, None)

        assert stopped.quantity is None
        assert stopped.quantity_updated_at is None
        assert stopped.reorder_threshold is None

    def test_counting_again_afterwards_carries_nothing_over(self, service):
        """008 FR-011 -- a fresh age, not the one from before tracking stopped"""
        product = service.create_product(description='x', quantity=4)
        backdate(service, product.id, quantity_updated_at=COUNTED_IN_JANUARY)
        service.set_quantity(product.id, None)

        restarted = service.set_quantity(product.id, 9)
        assert restarted.quantity == 9
        assert restarted.quantity_updated_at > COUNTED_IN_JANUARY
        assert datetime.now() - restarted.quantity_updated_at < timedelta(minutes=1)

    def test_creating_a_product_with_a_count_stamps_the_age(self, service):
        """Creating a product *with* a count is the operator entering one"""
        product = service.create_product(description='x', quantity=4)

        assert product.quantity_updated_at is not None
        assert datetime.now() - product.quantity_updated_at < timedelta(minutes=1)

    def test_creating_a_product_without_a_count_stamps_nothing(self, service):
        product = service.create_product(description='x')
        assert product.quantity_updated_at is None
