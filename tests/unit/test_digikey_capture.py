"""
Unit tests for reviewing and capturing a DigiKey order (feature 024, US1).

Two halves, and the line between them is the point:

* ``review_digikey_order`` reads and decides. It **writes nothing**, so the
  operator can close the tab and leave no trace (FR-004).
* ``capture_digikey_order`` writes, and writes the whole order in one
  transaction, so a failure part-way through leaves nothing behind (FR-039).

Network stays blocked. DigiKey is a fake built from the recorded fixture.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ItemNotFoundError, ValidationError
from app.models import (
    DigiKeyOrder,
    DigiKeyPart,
    IdentifierType,
    OrderLineState,
)

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'digikey'

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

class FakeDigiKey:
    """Serves the recorded part detail, and can be told to fail.

    ``fail_for`` names the part numbers that should raise, which is how the
    FR-041 tests reproduce "DigiKey answered for the order but not for this
    part" without touching a network the unit session has blocked anyway.
    """

    def __init__(self, fail_for=(), fail_all=False):
        self.fail_for = set(fail_for)
        self.fail_all = fail_all
        self.calls = []

    def get_part(self, part_number):
        self.calls.append(part_number)
        if self.fail_all or part_number in self.fail_for:
            raise ItemNotFoundError(f"no part {part_number}", item_id=part_number)
        body = json.loads((FIXTURES / 'productdetails.json').read_text(),
                          parse_float=Decimal)
        part = DigiKeyPart.from_payload(body)
        # The fixture is one real part; give each part number its own identity
        # so a two-line order does not look like the same thing twice.
        return DigiKeyPart(
            digikey_part_number=part_number,
            manufacturer_part_number=part.manufacturer_part_number,
            manufacturer=part.manufacturer,
            description=part.description,
            detailed_description=part.detailed_description,
            datasheet_url=part.datasheet_url,
            photo_url=part.photo_url,
            product_url=part.product_url,
            category_path=part.category_path,
            unit_price=part.unit_price,
            parameters=part.parameters,
        )


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def order():
    body = json.loads((FIXTURES / 'salesorder.json').read_text(), parse_float=Decimal)
    return DigiKeyOrder.from_payload(body)


@pytest.fixture
def digikey():
    return FakeDigiKey()


def include_all(order, **overrides):
    """Decisions that capture every line, with per-line overrides."""
    decisions = {
        line.digikey_part_number: {'include': True}
        for line in order.lines
    }
    for part_number, extra in overrides.items():
        decisions.setdefault(part_number, {}).update(extra)
    return decisions


def counts(catalog):
    from app.database import Product, Purchase
    session = catalog.storage._get_session()
    try:
        return (session.query(Product).count(), session.query(Purchase).count())
    finally:
        session.close()


# --------------------------------------------------------------------------
# T017 -- the review decides, and writes nothing
# --------------------------------------------------------------------------

class TestReview:

    def test_review_writes_nothing(self, catalog, order, digikey):
        """FR-004. The operator can close the tab and leave no trace."""
        before = counts(catalog)
        catalog.review_digikey_order(order, digikey)
        assert counts(catalog) == before == (0, 0)

    def test_every_line_is_reviewed(self, catalog, order, digikey):
        review = catalog.review_digikey_order(order, digikey)
        assert len(review.lines) == len(order.lines) == 2

    def test_an_unknown_part_is_new(self, catalog, order, digikey):
        review = catalog.review_digikey_order(order, digikey)
        assert all(line.state is OrderLineState.NEW for line in review.lines)

    def test_a_new_line_suggests_a_description(self, catalog, order, digikey):
        review = catalog.review_digikey_order(order, digikey)
        assert review.lines[0].suggested_description == 'AC/DC CONVERTER 5V 5W'

    def test_a_matching_mpn_is_matched(self, catalog, order, digikey):
        catalog.create_product(
            description='5V PSU I already own',
            identifiers=[{'id_type': 'MPN', 'value': 'IRM-05-5'}],
        )
        review = catalog.review_digikey_order(order, digikey)
        line = review.lines[0]
        assert line.state is OrderLineState.MATCHED
        assert line.product_description == '5V PSU I already own'
        assert line.product_id is not None

    def test_a_matching_digikey_part_number_is_matched(self, catalog, order, digikey):
        catalog.create_product(
            description='Bought this before',
            identifiers=[{'id_type': 'DISTRIBUTOR', 'value': '1866-3027-ND',
                          'vendor': 'DigiKey'}],
        )
        review = catalog.review_digikey_order(order, digikey)
        assert review.lines[0].state is OrderLineState.MATCHED

    def test_a_recycled_digikey_part_number_is_a_conflict(self, catalog, order, digikey):
        """FR-015. The identifier names something whose MPN contradicts the line."""
        catalog.create_product(
            description='Something else entirely',
            manufacturer_part_number='WIDGET-99',
            identifiers=[
                {'id_type': 'DISTRIBUTOR', 'value': '1866-3027-ND', 'vendor': 'DigiKey'},
                {'id_type': 'MPN', 'value': 'WIDGET-99'},
            ],
        )
        review = catalog.review_digikey_order(order, digikey)
        line = review.lines[0]
        assert line.state is OrderLineState.CONFLICT
        assert line.product_manufacturer_part_number == 'WIDGET-99'

    def test_an_already_captured_line_is_captured(self, catalog, order, digikey):
        """FR-012. A sales order number is an exact key, not a same-day guess."""
        catalog.capture_digikey_order(order, include_all(order), digikey)
        review = catalog.review_digikey_order(order, digikey)
        assert all(line.state is OrderLineState.CAPTURED for line in review.lines)
        assert review.capturable == ()

    def test_a_captured_line_reports_a_changed_quantity(self, catalog, order, digikey):
        """FR-014. Shown against what is recorded, applied only if asked."""
        from app.models import DigiKeyOrder as _Order

        catalog.capture_digikey_order(order, include_all(order), digikey)
        changed_lines = list(order.lines)
        changed_lines[0] = type(changed_lines[0])(
            **{**changed_lines[0].__dict__, 'quantity': 11}
        )
        changed = _Order(
            sales_order_number=order.sales_order_number,
            purchase_order=order.purchase_order,
            order_date=order.order_date,
            currency=order.currency,
            lines=tuple(changed_lines),
        )
        review = catalog.review_digikey_order(changed, digikey)
        line = review.lines[0]
        assert line.state is OrderLineState.CAPTURED
        assert line.has_change is True
        assert line.recorded_quantity == 5

    def test_a_vanished_line_is_orphaned_not_deleted(self, catalog, order, digikey):
        """FR-013. Reported. A purchase that disappears is worse than one you can see."""
        from app.models import DigiKeyOrder as _Order

        catalog.capture_digikey_order(order, include_all(order), digikey)
        shrunk = _Order(
            sales_order_number=order.sales_order_number,
            order_date=order.order_date,
            lines=(order.lines[0],),
        )
        review = catalog.review_digikey_order(shrunk, digikey)
        assert len(review.orphaned) == 1
        # Still there.
        assert counts(catalog)[1] == 2


# --------------------------------------------------------------------------
# T019a -- enrichment (FR-040, FR-041)
# --------------------------------------------------------------------------

class TestEnrichment:

    def test_every_line_is_enriched(self, catalog, order, digikey):
        """FR-040. A v4 order line carries no manufacturer; this is where it comes from."""
        review = catalog.review_digikey_order(order, digikey)
        assert digikey.calls == ['1866-3027-ND', '1866-3032-ND']
        assert all(line.is_enriched for line in review.lines)
        assert review.lines[0].part.manufacturer == 'MEAN WELL USA Inc.'

    def test_enrichment_fills_the_product_the_order_could_not(self, catalog, order, digikey):
        catalog.capture_digikey_order(order, include_all(order), digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.manufacturer == 'MEAN WELL USA Inc.'
        assert product.category_path is not None
        names = [s.name for s in product.specifications]
        assert 'Type' in names

    def test_a_failed_part_lookup_leaves_that_line_thin(self, catalog, order):
        """FR-041. Costs that line's extra detail and nothing else."""
        digikey = FakeDigiKey(fail_for={'1866-3027-ND'})
        review = catalog.review_digikey_order(order, digikey)
        assert review.lines[0].is_enriched is False
        assert review.lines[1].is_enriched is True
        assert review.unenriched == (review.lines[0],)

    def test_a_thin_line_is_still_capturable(self, catalog, order):
        digikey = FakeDigiKey(fail_for={'1866-3027-ND'})
        result = catalog.capture_digikey_order(order, include_all(order), digikey)
        assert len(result.purchase_ids) == 2
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        # Everything the *order* gave survived; only DigiKey's extras are missing.
        assert product.description == 'AC/DC CONVERTER 5V 5W'
        assert not product.manufacturer

    def test_digikey_being_wholly_unavailable_does_not_fail_a_capture(self, catalog, order):
        """A failed *part* read degrades. Only a failed *order* read refuses."""
        result = catalog.capture_digikey_order(
            order, include_all(order), FakeDigiKey(fail_all=True)
        )
        assert len(result.purchase_ids) == 2
        assert len(result.lines_unenriched) == 2

    def test_review_without_a_client_is_unenriched_not_broken(self, catalog, order):
        review = catalog.review_digikey_order(order, None)
        assert len(review.lines) == 2
        assert all(not line.is_enriched for line in review.lines)


# --------------------------------------------------------------------------
# T018 -- the write
# --------------------------------------------------------------------------

class TestCapture:

    def test_one_outstanding_purchase_per_line(self, catalog, order, digikey):
        """FR-008, FR-009, SC-002."""
        result = catalog.capture_digikey_order(order, include_all(order), digikey)
        assert len(result.purchase_ids) == 2
        assert counts(catalog) == (2, 2)

        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        purchase = product.purchases[0]
        assert purchase.vendor == 'DigiKey'
        assert purchase.supplier_order_reference == '100882558'
        assert purchase.vendor_item_id == '1866-3027-ND'
        assert purchase.quantity == 5
        assert purchase.unit_price == Decimal('6.50')
        assert purchase.received_date is None
        assert purchase.is_outstanding

    def test_the_order_date_is_recorded(self, catalog, order, digikey):
        catalog.capture_digikey_order(order, include_all(order), digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.purchases[0].order_date.date() == order.order_date.date()

    def test_outstanding_even_though_the_order_shipped(self, catalog, order, digikey):
        """FR-009. Shipped is DigiKey's state; received is the operator's."""
        assert order.lines[0].quantity_shipped == 5
        catalog.capture_digikey_order(order, include_all(order), digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.purchases[0].received_date is None

    def test_both_identifiers_are_recorded(self, catalog, order, digikey):
        """FR-010. Both scan back to the product."""
        catalog.capture_digikey_order(order, include_all(order), digikey)
        by_mpn = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        by_dkpn = catalog.find_product_by_identifier(
            '1866-3027-ND', id_type='DISTRIBUTOR', vendor='DigiKey'
        )
        assert by_mpn.id == by_dkpn.id

    def test_the_operators_description_wins(self, catalog, order, digikey):
        decisions = include_all(order)
        decisions['1866-3027-ND']['description'] = '5V 5W brick, enclosed'
        catalog.capture_digikey_order(order, decisions, digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.description == '5V 5W brick, enclosed'
        # DigiKey's own words are kept on the purchase.
        assert product.purchases[0].listing_title == 'AC/DC CONVERTER 5V 5W'

    def test_a_blank_description_falls_back_to_digikeys(self, catalog, order, digikey):
        """FR-006."""
        decisions = include_all(order)
        decisions['1866-3027-ND']['description'] = '   '
        catalog.capture_digikey_order(order, decisions, digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.description == 'AC/DC CONVERTER 5V 5W'

    def test_an_excluded_line_writes_nothing(self, catalog, order, digikey):
        """FR-007."""
        decisions = include_all(order)
        decisions['1866-3027-ND']['include'] = False
        result = catalog.capture_digikey_order(order, decisions, digikey)
        assert len(result.purchase_ids) == 1
        assert result.lines_excluded == 1
        assert counts(catalog) == (1, 1)
        assert catalog.find_product_by_identifier('IRM-05-5', id_type='MPN') is None

    def test_a_line_absent_from_the_decisions_is_excluded(self, catalog, order, digikey):
        result = catalog.capture_digikey_order(order, {}, digikey)
        assert result.purchase_ids == ()
        assert counts(catalog) == (0, 0)

    def test_recapturing_an_unchanged_order_writes_nothing(self, catalog, order, digikey):
        """FR-012, SC-003."""
        catalog.capture_digikey_order(order, include_all(order), digikey)
        before = counts(catalog)
        result = catalog.capture_digikey_order(order, include_all(order), digikey)
        assert counts(catalog) == before
        assert result.purchase_ids == ()
        assert result.lines_already_captured == 2

    def test_a_matched_line_attaches_rather_than_duplicating(self, catalog, order, digikey):
        """SC-005."""
        existing = catalog.create_product(
            description='5V PSU I already own',
            identifiers=[{'id_type': 'MPN', 'value': 'IRM-05-5'}],
        )
        result = catalog.capture_digikey_order(order, include_all(order), digikey)
        assert result.products_attached == 1
        assert result.products_created == 1
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.id == existing.id
        assert len(product.purchases) == 1

    def test_a_line_with_no_mpn_still_captures(self, catalog, order, digikey):
        """FR-016."""
        from app.models import DigiKeyOrder as _Order

        line = order.lines[0]
        bare = type(line)(**{**line.__dict__, 'manufacturer_part_number': ''})
        stripped = _Order(
            sales_order_number=order.sales_order_number,
            order_date=order.order_date,
            lines=(bare,),
        )
        result = catalog.capture_digikey_order(
            stripped, include_all(stripped), digikey
        )
        assert len(result.purchase_ids) == 1
        product = catalog.find_product_by_identifier(
            '1866-3027-ND', id_type='DISTRIBUTOR', vendor='DigiKey'
        )
        assert product is not None

    def test_an_unresolved_conflict_refuses_the_whole_capture(self, catalog, order, digikey):
        """FR-015. The whole capture, not just that line."""
        catalog.create_product(
            description='Something else entirely',
            manufacturer_part_number='WIDGET-99',
            identifiers=[
                {'id_type': 'DISTRIBUTOR', 'value': '1866-3027-ND', 'vendor': 'DigiKey'},
                {'id_type': 'MPN', 'value': 'WIDGET-99'},
            ],
        )
        before = counts(catalog)
        with pytest.raises(ValidationError):
            catalog.capture_digikey_order(order, include_all(order), digikey)
        assert counts(catalog) == before

    def test_a_conflict_resolved_as_attach_joins_the_existing_product(
            self, catalog, order, digikey):
        existing = catalog.create_product(
            description='Something else entirely',
            manufacturer_part_number='WIDGET-99',
            identifiers=[
                {'id_type': 'DISTRIBUTOR', 'value': '1866-3027-ND', 'vendor': 'DigiKey'},
                {'id_type': 'MPN', 'value': 'WIDGET-99'},
            ],
        )
        decisions = include_all(order)
        decisions['1866-3027-ND']['resolution'] = 'attach'
        catalog.capture_digikey_order(order, decisions, digikey)
        product = catalog.get_product(existing.id)
        assert len(product.purchases) == 1

    def test_a_conflict_resolved_as_separate_leaves_the_existing_alone(
            self, catalog, order, digikey):
        """The existing product keeps its identifiers -- including the contested one."""
        existing = catalog.create_product(
            description='Something else entirely',
            manufacturer_part_number='WIDGET-99',
            identifiers=[
                {'id_type': 'DISTRIBUTOR', 'value': '1866-3027-ND', 'vendor': 'DigiKey'},
                {'id_type': 'MPN', 'value': 'WIDGET-99'},
            ],
        )
        decisions = include_all(order)
        decisions['1866-3027-ND']['resolution'] = 'separate'
        catalog.capture_digikey_order(order, decisions, digikey)

        untouched = catalog.get_product(existing.id)
        assert len(untouched.purchases) == 0
        assert {i.value for i in untouched.identifiers} >= {'1866-3027-ND', 'WIDGET-99'}
        # And a new product exists carrying the purchase.
        assert counts(catalog)[0] == 3

    def test_applying_a_change_updates_the_recorded_purchase(self, catalog, order, digikey):
        """FR-014."""
        from app.models import DigiKeyOrder as _Order

        catalog.capture_digikey_order(order, include_all(order), digikey)
        line = order.lines[0]
        changed = _Order(
            sales_order_number=order.sales_order_number,
            order_date=order.order_date,
            lines=(type(line)(**{**line.__dict__, 'quantity': 11}),),
        )
        decisions = {line.digikey_part_number: {'include': True, 'apply_change': True}}
        result = catalog.capture_digikey_order(changed, decisions, digikey)
        assert result.lines_updated == 1

        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.purchases[0].quantity == 11
        # Still one purchase -- an update, not a second capture.
        assert len(product.purchases) == 1

    def test_a_change_not_applied_leaves_the_recorded_purchase_alone(
            self, catalog, order, digikey):
        from app.models import DigiKeyOrder as _Order

        catalog.capture_digikey_order(order, include_all(order), digikey)
        line = order.lines[0]
        changed = _Order(
            sales_order_number=order.sales_order_number,
            order_date=order.order_date,
            lines=(type(line)(**{**line.__dict__, 'quantity': 11}),),
        )
        catalog.capture_digikey_order(
            changed, {line.digikey_part_number: {'include': True}}, digikey
        )
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.purchases[0].quantity == 5


# --------------------------------------------------------------------------
# T019 -- atomicity (FR-039, SC-009)
# --------------------------------------------------------------------------

class TestAtomicity:

    def test_a_failure_part_way_through_writes_nothing(self, catalog, order, digikey,
                                                       monkeypatch):
        """FR-039, SC-009. One session for the whole order, or none of it."""
        before = counts(catalog)

        real = CatalogService._add_identifier
        state = {'n': 0}

        def explode(self, session, product_id, id_type, value, **kwargs):
            state['n'] += 1
            if state['n'] > 2:  # part-way through the second line
                raise RuntimeError('the database went away')
            return real(self, session, product_id, id_type, value, **kwargs)

        monkeypatch.setattr(CatalogService, '_add_identifier', explode)

        with pytest.raises(RuntimeError):
            catalog.capture_digikey_order(order, include_all(order), digikey)

        assert counts(catalog) == before == (0, 0)

    def test_a_refused_description_writes_nothing(self, catalog, order, digikey):
        before = counts(catalog)
        decisions = include_all(order)
        decisions['1866-3032-ND']['description'] = 'x' * 500
        with pytest.raises(ValidationError):
            catalog.capture_digikey_order(order, decisions, digikey)
        assert counts(catalog) == before


# --------------------------------------------------------------------------
# T022 -- the derived order
# --------------------------------------------------------------------------

class TestFindOrderLines:

    def test_an_order_is_its_purchases(self, catalog, order, digikey):
        """FR-017. Nothing is stored; the order is derived."""
        catalog.capture_digikey_order(order, include_all(order), digikey)
        lines = catalog.find_order_lines('100882558')
        assert len(lines) == 2
        assert {p.vendor_item_id for p in lines} == {'1866-3027-ND', '1866-3032-ND'}

    def test_an_uncaptured_order_has_no_lines(self, catalog):
        assert catalog.find_order_lines('999999999') == []

    def test_outstanding_count(self, catalog, order, digikey):
        """FR-018."""
        catalog.capture_digikey_order(order, include_all(order), digikey)
        lines = catalog.find_order_lines('100882558')
        assert sum(1 for p in lines if p.is_outstanding) == 2

        catalog.receive_purchase(lines[0].id)
        lines = catalog.find_order_lines('100882558')
        assert sum(1 for p in lines if p.is_outstanding) == 1

    def test_another_vendors_purchase_is_not_in_the_order(self, catalog, order, digikey):
        catalog.capture_digikey_order(order, include_all(order), digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        catalog.record_purchase(
            product.id, vendor='Mouser', order_reference='100882558'
        )
        assert len(catalog.find_order_lines('100882558')) == 2
