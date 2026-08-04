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
from app.exceptions import ItemNotFoundError, ValidationError
from app.product.routes import relative_age


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


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
