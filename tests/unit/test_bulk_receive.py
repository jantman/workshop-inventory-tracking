"""Bulk-receiving a backfill's outstanding purchases (feature 042, issue #140).

Capturing an order records every line outstanding. That is right for an order
placed this week and wrong for one placed in 2023, and feature 031 fixed it at
capture time with a tick. Nothing reached what was already captured before that
existed, which is what the command tested here is for.

**Phase 5 below is the reason this file matters.** 031 states its equivalent
guarantee -- a backfill receipt moves no count, no count age and no manual low
flag -- and notes that it holds *by construction*, because a purchase born with
a ``received_date`` never passes through ``receive_purchase``.
``apply_outstanding_receipts`` is the first code that receives an
**already-existing** purchase without going through that method, so construction
stops covering it here. If somebody later routes the sweep through
``receive_purchase``, these tests are the only thing that will notice, and what
they would be noticing is every counted quantity in the catalog inflated by
years of consumed stock.
"""

from datetime import datetime

import click
import pytest
from click.testing import CliRunner

from app.catalog_service import CatalogService
from app.database import Product
from app.models import OutstandingReceipt, OutstandingReceiptPlan, StockStatus

pytestmark = pytest.mark.unit


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def seed(catalog, *, vendor='DigiKey', order_date=datetime(2023, 4, 11),
         received_date=None, order_number='62301442', quantity=10,
         description=None, product_quantity=None, **product_fields):
    """One product plus one purchase of it. Returns (product_id, purchase_id)."""
    product = catalog.create_product(
        description=description or f"{vendor} part ordered {order_date}",
        quantity=product_quantity,
        **product_fields,
    )
    purchase = catalog.record_purchase(
        product_id=product.id,
        vendor=vendor,
        order_date=order_date,
        received_date=received_date,
        quantity=quantity,
        supplier_order_reference=order_number,
    )
    return product.id, purchase.id


CUTOFF = datetime(2026, 1, 1)


# -- The sweep itself (US1) -------------------------------------------------


def test_outstanding_purchases_before_the_cutoff_are_planned_and_received(catalog):
    _, first = seed(catalog, order_date=datetime(2023, 4, 11))
    _, second = seed(catalog, order_date=datetime(2024, 11, 2), order_number='63887190')

    plan = catalog.plan_outstanding_receipts(before=CUTOFF)
    assert plan.purchase_ids == [first, second]

    assert catalog.apply_outstanding_receipts(plan) == 2
    assert catalog.get_purchase(first).received_date is not None
    assert catalog.get_purchase(second).received_date is not None


def test_each_purchase_is_received_on_its_own_order_date(catalog):
    """FR-008. Not today's date -- that is the failure backfilling exists to avoid."""
    _, first = seed(catalog, order_date=datetime(2023, 4, 11))
    _, second = seed(catalog, order_date=datetime(2024, 11, 2), order_number='63887190')

    catalog.apply_outstanding_receipts(
        catalog.plan_outstanding_receipts(before=CUTOFF)
    )

    assert catalog.get_purchase(first).received_date == datetime(2023, 4, 11)
    assert catalog.get_purchase(second).received_date == datetime(2024, 11, 2)


def test_the_plan_carries_what_the_listing_needs(catalog):
    seed(
        catalog, vendor='DigiKey', order_date=datetime(2023, 4, 11),
        order_number='62301442', quantity=10,
        description='Molex 22-23-2021 header, 2 pos',
    )

    receipt, = catalog.plan_outstanding_receipts(before=CUTOFF).receipts

    assert receipt.vendor == 'DigiKey'
    assert receipt.order_number == '62301442'
    assert receipt.order_date == datetime(2023, 4, 11)
    assert receipt.quantity == 10
    assert receipt.product_description == 'Molex 22-23-2021 header, 2 pos'


def test_a_swept_order_reports_no_outstanding_lines(catalog):
    """FR-013 through the captured-orders list, which is where the operator looks."""
    product = catalog.create_product(description='Resistor')
    for _ in range(3):
        catalog.record_purchase(
            product_id=product.id, vendor='DigiKey',
            order_date=datetime(2023, 4, 11), quantity=1,
            supplier_order_reference='62301442',
        )

    before, = catalog.find_captured_orders()
    assert before.outstanding_count == 3
    assert not before.is_complete

    catalog.apply_outstanding_receipts(
        catalog.plan_outstanding_receipts(before=CUTOFF)
    )

    after, = catalog.find_captured_orders()
    assert after.outstanding_count == 0
    assert after.is_complete


def test_a_swept_product_is_no_longer_on_the_way(catalog):
    """FR-013 through the reorder list -- the other screen that reads outstanding."""
    product_id, _ = seed(
        catalog, description='Low resistor', product_quantity=0, reorder_threshold=5,
    )

    entry, = catalog.get_reorder_products()
    assert entry['is_on_order'] is True

    catalog.apply_outstanding_receipts(
        catalog.plan_outstanding_receipts(before=CUTOFF)
    )

    entry, = catalog.get_reorder_products()
    assert entry['product'].id == product_id
    assert entry['is_on_order'] is False
    assert entry['outstanding'] == []


# -- Selection (US1) --------------------------------------------------------


def test_an_already_received_purchase_is_not_selected_or_re_dated(catalog):
    """FR-002. An existing receipt is never overwritten."""
    _, purchase_id = seed(
        catalog, order_date=datetime(2023, 4, 11),
        received_date=datetime(2023, 5, 1),
    )

    plan = catalog.plan_outstanding_receipts(before=CUTOFF)

    assert plan.is_empty
    assert catalog.get_purchase(purchase_id).received_date == datetime(2023, 5, 1)


def test_an_already_received_purchase_smuggled_into_a_plan_is_still_left_alone(catalog):
    """The write re-checks rather than trusting the ids it was handed (FR-002)."""
    _, purchase_id = seed(
        catalog, order_date=datetime(2023, 4, 11),
        received_date=datetime(2023, 5, 1),
    )
    forged = OutstandingReceiptPlan(receipts=(
        OutstandingReceipt(
            purchase_id=purchase_id, vendor='DigiKey',
            order_date=datetime(2023, 4, 11),
        ),
    ))

    assert catalog.apply_outstanding_receipts(forged) == 0
    assert catalog.get_purchase(purchase_id).received_date == datetime(2023, 5, 1)


def test_a_purchase_that_no_longer_exists_is_skipped(catalog):
    """The plan was read in an earlier session; the row may be gone by the write."""
    plan = OutstandingReceiptPlan(receipts=(
        OutstandingReceipt(
            purchase_id=9999, vendor='DigiKey', order_date=datetime(2023, 4, 11),
        ),
    ))

    assert catalog.apply_outstanding_receipts(plan) == 0


def test_the_cutoff_is_exclusive(catalog):
    """FR-004. "Before" means before."""
    _, on_the_day = seed(catalog, order_date=datetime(2026, 1, 1))
    _, the_day_before = seed(
        catalog, order_date=datetime(2025, 12, 31), order_number='63887190',
    )

    plan = catalog.plan_outstanding_receipts(before=CUTOFF)

    assert plan.purchase_ids == [the_day_before]
    assert catalog.get_purchase(on_the_day).received_date is None


def test_the_vendor_filter_excludes_other_vendors(catalog):
    """FR-003."""
    _, digikey = seed(catalog, vendor='DigiKey')
    _, mcmaster = seed(catalog, vendor='McMaster-Carr', order_number='0411SMITH')

    plan = catalog.plan_outstanding_receipts(before=CUTOFF, vendor='DigiKey')

    assert plan.purchase_ids == [digikey]
    assert catalog.get_purchase(mcmaster).received_date is None


@pytest.mark.parametrize('typed', ['digikey', 'DIGIKEY', '  DigiKey  '])
def test_the_vendor_filter_ignores_case_and_whitespace(catalog, typed):
    """FR-003. The operator typing it is recalling a name, not reading one."""
    _, purchase_id = seed(catalog, vendor='DigiKey')

    plan = catalog.plan_outstanding_receipts(before=CUTOFF, vendor=typed)

    assert plan.purchase_ids == [purchase_id]


def test_no_vendor_means_every_vendor(catalog):
    """FR-005."""
    _, digikey = seed(catalog, vendor='DigiKey')
    _, mcmaster = seed(catalog, vendor='McMaster-Carr', order_number='0411SMITH')

    plan = catalog.plan_outstanding_receipts(before=CUTOFF)

    assert sorted(plan.purchase_ids) == sorted([digikey, mcmaster])


def test_a_hand_recorded_purchase_is_eligible(catalog):
    """FR-007. Provenance is not part of the predicate."""
    _, purchase_id = seed(catalog, vendor='Grainger', order_number=None)

    receipt, = catalog.plan_outstanding_receipts(before=CUTOFF).receipts

    assert receipt.purchase_id == purchase_id
    assert receipt.order_number is None


# -- Not a receiving-desk receipt (US3) -------------------------------------
#
# The four tests below are what 031 FR-028 gets instead of "satisfied by
# construction", now that construction no longer covers it.


def test_a_tracked_count_does_not_move(catalog):
    """FR-009. Goods delivered in 2023 were consumed in 2023."""
    product_id, _ = seed(catalog, product_quantity=4, quantity=100)

    catalog.apply_outstanding_receipts(
        catalog.plan_outstanding_receipts(before=CUTOFF)
    )

    assert catalog.get_product(product_id).quantity == 4


def test_a_counts_age_does_not_move(catalog):
    """FR-010. Nobody counted anything; the operator is at a terminal."""
    product_id, _ = seed(catalog, product_quantity=4)
    counted_in_january = datetime(2026, 1, 15, 9, 30)
    with catalog._session() as session:
        session.query(Product).filter(Product.id == product_id).first(
        ).quantity_updated_at = counted_in_january

    catalog.apply_outstanding_receipts(
        catalog.plan_outstanding_receipts(before=CUTOFF)
    )

    assert catalog.get_product(product_id).quantity_updated_at == counted_in_january


def test_an_untracked_count_is_not_started(catalog):
    """US3 scenario 4. Receiving never starts a count, and this least of all."""
    product_id, _ = seed(catalog, product_quantity=None, quantity=100)

    catalog.apply_outstanding_receipts(
        catalog.plan_outstanding_receipts(before=CUTOFF)
    )

    product = catalog.get_product(product_id)
    assert product.quantity is None
    assert product.quantity_updated_at is None


def test_a_manual_low_flag_survives(catalog):
    """FR-011. A flag set last month is a statement about today's shelf."""
    product_id, _ = seed(catalog)
    catalog.set_stock_status(product_id, StockStatus.LOW.value)
    flagged_at = catalog.get_product(product_id).stock_status_updated_at
    assert flagged_at is not None

    catalog.apply_outstanding_receipts(
        catalog.plan_outstanding_receipts(before=CUTOFF)
    )

    product = catalog.get_product(product_id)
    assert product.stock_status == StockStatus.LOW.value
    assert product.stock_status_updated_at == flagged_at


def test_nothing_but_the_receipt_date_is_amended(catalog):
    """FR-012. Not asked for and not knowable in bulk."""
    product = catalog.create_product(description='Molex header')
    purchase = catalog.record_purchase(
        product_id=product.id, vendor='DigiKey', order_date=datetime(2023, 4, 11),
        quantity=10, unit_price='1.23', notes='from the 2023 order',
        supplier_order_reference='62301442',
    )

    catalog.apply_outstanding_receipts(
        catalog.plan_outstanding_receipts(before=CUTOFF)
    )

    after = catalog.get_purchase(purchase.id)
    assert after.quantity == 10
    assert str(after.unit_price) == '1.23'
    assert after.notes == 'from the 2023 order'
    assert catalog.get_product(product.id).description == 'Molex header'


def test_the_sweep_lands_whole_or_not_at_all(catalog, monkeypatch):
    """FR-020. _session rolls back on any exception, so a failure writes nothing."""
    _, first = seed(catalog, order_date=datetime(2023, 4, 11))
    _, second = seed(catalog, order_date=datetime(2024, 11, 2), order_number='63887190')
    plan = catalog.plan_outstanding_receipts(before=CUTOFF)
    assert len(plan.receipts) == 2

    sessionmaker = catalog.Session

    def failing_session():
        session = sessionmaker()

        def boom():
            raise RuntimeError('database went away')

        session.commit = boom
        return session

    monkeypatch.setattr(catalog, 'Session', failing_session)

    with pytest.raises(RuntimeError):
        catalog.apply_outstanding_receipts(plan)

    monkeypatch.undo()
    assert catalog.get_purchase(first).received_date is None
    assert catalog.get_purchase(second).received_date is None


# -- Purchases the vendor never dated (US4) ---------------------------------


def test_an_undated_purchase_is_left_alone_and_counted(catalog):
    """FR-006. There is no date to receive it at, and today's would be wrong."""
    _, dated = seed(catalog, order_date=datetime(2023, 4, 11))
    _, undated = seed(catalog, order_date=None, order_number='63887190')

    plan = catalog.plan_outstanding_receipts(before=CUTOFF)
    assert plan.purchase_ids == [dated]
    assert plan.undated_count == 1

    catalog.apply_outstanding_receipts(plan)
    assert catalog.get_purchase(undated).received_date is None


def test_the_undated_count_respects_the_vendor_filter(catalog):
    seed(catalog, vendor='DigiKey', order_date=None)
    seed(catalog, vendor='McMaster-Carr', order_date=None, order_number='0411SMITH')

    assert catalog.plan_outstanding_receipts(
        before=CUTOFF, vendor='DigiKey'
    ).undated_count == 1
    assert catalog.plan_outstanding_receipts(before=CUTOFF).undated_count == 2


def test_an_undated_purchase_smuggled_into_a_plan_is_not_written(catalog):
    _, undated = seed(catalog, order_date=None)
    forged = OutstandingReceiptPlan(receipts=(
        OutstandingReceipt(
            purchase_id=undated, vendor='DigiKey', order_date=datetime(2023, 4, 11),
        ),
    ))

    assert catalog.apply_outstanding_receipts(forged) == 0
    assert catalog.get_purchase(undated).received_date is None


# -- Rendering (US2) --------------------------------------------------------


def _plan(**overrides):
    defaults = dict(
        receipts=(
            OutstandingReceipt(
                purchase_id=412, vendor='DigiKey', order_date=datetime(2023, 4, 11),
                order_number='62301442', product_description='Molex header',
                quantity=10,
            ),
        ),
    )
    defaults.update(overrides)
    return OutstandingReceiptPlan(**defaults)


def test_the_listing_names_every_selected_purchase(catalog):
    """FR-014."""
    rendered = _plan().render('Would receive')

    assert 'Would receive 1 outstanding purchase(s)' in rendered
    assert '#412' in rendered
    assert 'DigiKey' in rendered
    assert '62301442' in rendered
    assert '2023-04-11' in rendered
    assert '10' in rendered
    assert 'Molex header' in rendered


def test_a_purchase_belonging_to_no_order_renders_a_dash():
    receipt = OutstandingReceipt(
        purchase_id=9, vendor='Grainger', order_date=datetime(2024, 1, 5),
    )

    assert ' - ' in OutstandingReceiptPlan(receipts=(receipt,)).render('Would receive')


def test_the_skip_line_appears_only_when_something_was_skipped():
    assert 'skipped' not in _plan().render('Would receive')
    assert '2 outstanding purchase(s) skipped' in _plan(undated_count=2).render(
        'Would receive'
    )


def test_an_empty_plan_says_so():
    """FR-017."""
    assert OutstandingReceiptPlan().render('Would receive') == (
        'No outstanding purchases match. Nothing to do.'
    )


def test_an_empty_plan_still_reports_undated_purchases():
    """"Nothing matched" and "nothing matched, but four carry no date" differ."""
    rendered = OutstandingReceiptPlan(undated_count=4).render('Would receive')

    assert 'Nothing to do.' in rendered
    assert '4 outstanding purchase(s) skipped' in rendered


# -- The command at a terminal (US2) ----------------------------------------


class StubService:
    """Stands in for CatalogService so the CLI tests need no database."""

    def __init__(self, plan):
        self._plan = plan
        self.planned_with = None
        self.applied = None

    def plan_outstanding_receipts(self, before, vendor=None):
        self.planned_with = (before, vendor)
        return self._plan

    def apply_outstanding_receipts(self, plan):
        self.applied = plan
        return len(plan.receipts)


@pytest.fixture
def cli(monkeypatch):
    """The ``orders`` group with its CatalogService replaced.

    ``manage.py`` imports CatalogService inside the command body -- the file's
    established style -- so patching the class where it is defined is enough and
    no database is touched.
    """
    import app.catalog_service
    import manage

    service = StubService(_plan())
    monkeypatch.setattr(app.catalog_service, 'CatalogService', lambda: service)
    return CliRunner(), manage.orders, service


def test_dry_run_lists_and_writes_nothing(cli):
    """FR-015."""
    runner, group, service = cli

    result = runner.invoke(
        group, ['receive-outstanding', '--before', '2026-01-01', '--dry-run']
    )

    assert result.exit_code == 0
    assert '#412' in result.output
    assert 'Would receive' in result.output
    assert 'nothing was written' in result.output
    assert service.applied is None


def test_confirming_applies_the_plan(cli):
    """FR-016, FR-018."""
    runner, group, service = cli

    result = runner.invoke(
        group, ['receive-outstanding', '--before', '2026-01-01'], input='y\n'
    )

    assert result.exit_code == 0
    assert 'About to receive' in result.output
    assert service.applied is service._plan
    assert 'Received 1 outstanding purchase(s).' in result.output


def test_declining_writes_nothing(cli):
    """FR-016."""
    runner, group, service = cli

    result = runner.invoke(
        group, ['receive-outstanding', '--before', '2026-01-01'], input='n\n'
    )

    assert result.exit_code == 0
    assert service.applied is None
    assert 'Nothing was written.' in result.output


def test_the_filters_reach_the_service(cli):
    runner, group, service = cli

    runner.invoke(
        group,
        ['receive-outstanding', '--before', '2026-01-01', '--vendor', 'digikey',
         '--dry-run'],
    )

    assert service.planned_with == (datetime(2026, 1, 1), 'digikey')


def test_an_empty_selection_never_prompts(cli, monkeypatch):
    """FR-017. Nothing to confirm, so nothing is asked."""
    runner, group, service = cli
    service._plan = OutstandingReceiptPlan()
    monkeypatch.setattr(
        click, 'confirm', lambda *a, **k: pytest.fail('should not have prompted')
    )

    result = runner.invoke(group, ['receive-outstanding', '--before', '2026-01-01'])

    assert result.exit_code == 0
    assert 'Nothing to do.' in result.output
    assert service.applied is None


def test_a_malformed_cutoff_is_refused_before_anything_is_read(cli):
    """FR-019."""
    runner, group, service = cli

    result = runner.invoke(group, ['receive-outstanding', '--before', 'last-tuesday'])

    assert result.exit_code != 0
    assert 'last-tuesday' in result.output
    assert service.planned_with is None


def test_the_cutoff_is_required(cli):
    """FR-004. An unbounded sweep is not offered."""
    runner, group, service = cli

    result = runner.invoke(group, ['receive-outstanding'])

    assert result.exit_code != 0
    assert '--before' in result.output
    assert service.planned_with is None
