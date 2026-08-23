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
    """Decisions that capture every line, with per-line overrides.

    Keyed by ``form_key`` -- the DetailId -- because that is what the product
    keys by and what the form emits. It used to key by part number, which a
    single-part-per-line order made look correct. PR #116 review.
    """
    decisions = {line.form_key: {'include': True} for line in order.lines}
    for key, extra in overrides.items():
        decisions.setdefault(key, {}).update(extra)
    return decisions


def key_of(order, part_number):
    """The form key of the (first) line carrying a part number."""
    for line in order.lines:
        if line.digikey_part_number == part_number:
            return line.form_key
    raise AssertionError(f'no line for {part_number}')


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
        decisions[key_of(order, '1866-3027-ND')]['description'] = '5V 5W brick, enclosed'
        catalog.capture_digikey_order(order, decisions, digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.description == '5V 5W brick, enclosed'
        # DigiKey's own words are kept on the purchase.
        assert product.purchases[0].listing_title == 'AC/DC CONVERTER 5V 5W'

    def test_a_blank_description_falls_back_to_digikeys(self, catalog, order, digikey):
        """FR-006."""
        decisions = include_all(order)
        decisions[key_of(order, '1866-3027-ND')]['description'] = '   '
        catalog.capture_digikey_order(order, decisions, digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.description == 'AC/DC CONVERTER 5V 5W'

    def test_an_excluded_line_writes_nothing(self, catalog, order, digikey):
        """FR-007."""
        decisions = include_all(order)
        decisions[key_of(order, '1866-3027-ND')]['include'] = False
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
        decisions[key_of(order, '1866-3027-ND')]['resolution'] = 'attach'
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
        decisions[key_of(order, '1866-3027-ND')]['resolution'] = 'separate'
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
        decisions = {line.form_key: {'include': True, 'apply_change': True}}
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
            changed, {line.form_key: {'include': True}}, digikey
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
        decisions[key_of(order, '1866-3032-ND')]['description'] = 'x' * 500
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


# --------------------------------------------------------------------------
# Through the form, not around it
#
# Both bugs found in PR #116's review had passing unit tests. Both tests called
# capture_digikey_order directly with a decisions dict hand-written to look like
# what the form sends -- and in one case the form could never send it, because
# the review deliberately renders no "take this line" checkbox for a line that
# is already captured.
#
# So these tests render the real page, read the inputs off it, and submit those.
# A decision the template cannot produce cannot be asserted here.
# --------------------------------------------------------------------------

import re


def form_fields(html, part_numbers=()):
    """Every input the rendered review page would actually submit.

    Checkboxes count only when they are checked, which is what makes the
    "already captured lines carry no include" property visible to a test rather
    than something a hand-written dict papers over.
    """
    fields = {}
    for tag in re.findall(r'<input\b[^>]*>', html):
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        is_checkbox = 'type="checkbox"' in tag
        if is_checkbox and 'checked' not in tag:
            continue
        value = re.search(r'value="([^"]*)"', tag)
        fields[name.group(1)] = value.group(1) if value else 'on'
    return fields


class TestCaptureThroughTheForm:
    """PR #116 review: the apply_change path was dead through the real UI."""

    @pytest.fixture
    def captured(self, client, test_storage, order, digikey_fixture_client, app):
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        CatalogService(test_storage).capture_digikey_order(
            order, include_all(order), FakeDigiKey()
        )
        return CatalogService(test_storage)

    def _review_html(self, client):
        response = client.post('/products/digikey/orders',
                               data={'sales_order_number': '100882558'})
        assert response.status_code == 200
        return response.get_data(as_text=True)

    def test_an_already_captured_line_renders_no_include_checkbox(self, client, captured):
        """The property the fix has to hold for -- asserted, not assumed."""
        fields = form_fields(self._review_html(client))
        assert 'include[1]' not in fields
        assert 'include[2]' not in fields

    def test_recapturing_through_the_form_reports_already_captured(
            self, client, captured):
        """Not "skipped". They are different words for different things."""
        response = client.post(
            '/products/digikey/orders/capture',
            data={**form_fields(self._review_html(client)),
                  'sales_order_number': '100882558'},
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)
        assert '2 already captured' in body
        assert 'skipped' not in body

    def test_ticking_update_it_actually_updates(self, client, captured, app,
                                                digikey_fixture_client, monkeypatch):
        """FR-014, through the form. This is the one that was dead."""
        # DigiKey now says a different quantity than what was recorded.
        real_get_order = digikey_fixture_client.get_order

        def changed_order(number):
            base = real_get_order(number)
            line = base.lines[0]
            return type(base)(
                sales_order_number=base.sales_order_number,
                purchase_order=base.purchase_order,
                order_date=base.order_date,
                currency=base.currency,
                lines=(type(line)(**{**line.__dict__, 'quantity': 11}),) + base.lines[1:],
            )

        monkeypatch.setattr(digikey_fixture_client, 'get_order', changed_order)
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client

        html = self._review_html(client)
        fields = form_fields(html)
        # The page offers the tick-box for the changed line...
        assert 'apply_change[1]' in html
        # ...and it is unticked by default, so tick it the way an operator would.
        fields['apply_change[1]'] = 'on'

        client.post('/products/digikey/orders/capture',
                    data={**fields, 'sales_order_number': '100882558'},
                    follow_redirects=True)

        product = captured.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.purchases[0].quantity == 11
        assert len(product.purchases) == 1, 'an update, not a second capture'

    def test_an_update_only_capture_says_it_updated_something(
            self, client, captured, app, digikey_fixture_client, monkeypatch):
        """PR #116 review: the write landed but the flash said nothing happened.

        An update-only capture writes no purchase, so a summary that leads on
        the purchase count reports "Nothing new to capture" over the top of a
        change that is now in the database. Same silent-write problem as the bug
        this class was written for, one layer out.
        """
        real_get_order = digikey_fixture_client.get_order

        def changed_order(number):
            base = real_get_order(number)
            line = base.lines[0]
            return type(base)(
                sales_order_number=base.sales_order_number,
                order_date=base.order_date,
                lines=(type(line)(**{**line.__dict__, 'quantity': 11}),) + base.lines[1:],
            )

        monkeypatch.setattr(digikey_fixture_client, 'get_order', changed_order)
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client

        fields = form_fields(self._review_html(client))
        fields['apply_change[1]'] = 'on'
        response = client.post('/products/digikey/orders/capture',
                               data={**fields, 'sales_order_number': '100882558'},
                               follow_redirects=True)

        body = response.get_data(as_text=True)
        assert '1 line(s) updated' in body
        assert 'Nothing new to capture' not in body
        # And the change really is in the database, not just in the message.
        product = captured.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.purchases[0].quantity == 11

    def test_a_capture_that_changed_nothing_still_says_so(
            self, client, captured, app, digikey_fixture_client):
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        response = client.post(
            '/products/digikey/orders/capture',
            data={**form_fields(self._review_html(client)),
                  'sales_order_number': '100882558'},
            follow_redirects=True,
        )
        assert 'Nothing new to capture' in response.get_data(as_text=True)

    def test_not_ticking_it_leaves_the_purchase_alone(self, client, captured, app,
                                                     digikey_fixture_client, monkeypatch):
        real_get_order = digikey_fixture_client.get_order

        def changed_order(number):
            base = real_get_order(number)
            line = base.lines[0]
            return type(base)(
                sales_order_number=base.sales_order_number,
                order_date=base.order_date,
                lines=(type(line)(**{**line.__dict__, 'quantity': 11}),) + base.lines[1:],
            )

        monkeypatch.setattr(digikey_fixture_client, 'get_order', changed_order)
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client

        client.post('/products/digikey/orders/capture',
                    data={**form_fields(self._review_html(client)),
                          'sales_order_number': '100882558'},
                    follow_redirects=True)

        product = captured.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.purchases[0].quantity == 5

    def test_unticking_a_line_still_excludes_it(self, client, test_storage, app,
                                                digikey_fixture_client):
        """The include gate still works for lines that are not already captured."""
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        html = self._review_html(client)
        fields = form_fields(html)
        assert 'include[1]' in fields, 'a NEW line offers the checkbox'
        del fields['include[1]']

        response = client.post('/products/digikey/orders/capture',
                               data={**fields, 'sales_order_number': '100882558'},
                               follow_redirects=True)
        assert '1 skipped' in response.get_data(as_text=True)
        catalog = CatalogService(test_storage)
        assert catalog.find_product_by_identifier('IRM-05-5', id_type='MPN') is None


class TestNoNetworkInsideTheTransaction:
    """PR #116 review: the review held a session open across per-line HTTP calls.

    ``capture_digikey_order`` already documented why that is wrong -- ten seconds
    a call, twenty-five calls, a long-lived lock in exchange for nothing -- and
    the review did the opposite of its own sibling's comment. Worse, in fact: a
    review enriches every line where a capture enriches only the included ones.
    """

    def test_every_part_is_fetched_before_the_session_opens(self, catalog, order):
        opened = []

        class WatchfulDigiKey(FakeDigiKey):
            def get_part(self, part_number):
                opened.append(('fetch', part_number))
                return super().get_part(part_number)

        real_session = type(catalog)._session

        from contextlib import contextmanager

        @contextmanager
        def watched(self):
            opened.append(('session-open', None))
            with real_session(self) as session:
                yield session
            opened.append(('session-close', None))

        type(catalog)._session = watched
        try:
            catalog.review_digikey_order(order, WatchfulDigiKey())
        finally:
            type(catalog)._session = real_session

        kinds = [kind for kind, _ in opened]
        assert kinds.count('fetch') == 2, kinds
        first_open = kinds.index('session-open')
        assert all(i < first_open for i, k in enumerate(kinds) if k == 'fetch'), (
            f'a DigiKey call happened inside an open transaction: {kinds}'
        )

    def test_capture_still_fetches_before_its_session_too(self, catalog, order):
        """The sibling that was already right, pinned so it stays that way."""
        opened = []

        class WatchfulDigiKey(FakeDigiKey):
            def get_part(self, part_number):
                opened.append(('fetch', part_number))
                return super().get_part(part_number)

        real_session = type(catalog)._session
        from contextlib import contextmanager

        @contextmanager
        def watched(self):
            opened.append(('session-open', None))
            with real_session(self) as session:
                yield session

        type(catalog)._session = watched
        try:
            catalog.capture_digikey_order(order, include_all(order), WatchfulDigiKey())
        finally:
            type(catalog)._session = real_session

        kinds = [kind for kind, _ in opened]
        first_open = kinds.index('session-open')
        assert all(i < first_open for i, k in enumerate(kinds) if k == 'fetch'), kinds


# --------------------------------------------------------------------------
# PR #116 review, third round
# --------------------------------------------------------------------------

def duplicate_part_order(order):
    """An order carrying the same DigiKey part on two lines.

    No order on the developer's account has one, so this is built from the real
    fixture and labelled as such. The feature's own spec accounts for the case
    ("two lines of one order are the same part... they become two purchases
    against one product, which is what they are"), so it is specified behaviour
    rather than a hypothetical.
    """
    first = order.lines[0]
    second = type(first)(**{**first.__dict__, 'line_number': 2, 'quantity': 7})
    return type(order)(
        sales_order_number=order.sales_order_number,
        purchase_order=order.purchase_order,
        order_date=order.order_date,
        currency=order.currency,
        lines=(first, second),
    )


class TestDuplicatePartOnOneOrder:
    """A part number does not identify a line; DetailId does."""

    def test_the_two_lines_have_different_form_keys(self, order):
        duplicated = duplicate_part_order(order)
        keys = [line.form_key for line in duplicated.lines]
        assert keys == ['1', '2'], keys
        assert len(set(keys)) == 2, 'the two lines shared one set of form fields'

    def test_both_lines_capture_as_separate_purchases(self, catalog, order, digikey):
        duplicated = duplicate_part_order(order)
        result = catalog.capture_digikey_order(
            duplicated, include_all(duplicated), digikey
        )
        assert len(result.purchase_ids) == 2
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert len(product.purchases) == 2
        assert sorted(p.quantity for p in product.purchases) == [5, 7]

    def test_one_of_two_duplicate_lines_can_be_excluded(self, catalog, order, digikey):
        """Impossible while both shared an include[] field."""
        duplicated = duplicate_part_order(order)
        decisions = include_all(duplicated)
        decisions['2']['include'] = False
        result = catalog.capture_digikey_order(duplicated, decisions, digikey)
        assert len(result.purchase_ids) == 1
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert [p.quantity for p in product.purchases] == [5]

    def test_a_recapture_sees_both_as_captured(self, catalog, order, digikey):
        """The second purchase used to be invisible to the review."""
        duplicated = duplicate_part_order(order)
        catalog.capture_digikey_order(duplicated, include_all(duplicated), digikey)
        review = catalog.review_digikey_order(duplicated, digikey)
        assert [line.state for line in review.lines] == [
            OrderLineState.CAPTURED, OrderLineState.CAPTURED
        ]
        # Each line looks at its *own* purchase.
        assert len({line.purchase_id for line in review.lines}) == 2

    def test_applying_a_change_hits_the_right_purchase(self, catalog, order, digikey):
        """It used to write to the first purchase twice, clobbering itself."""
        duplicated = duplicate_part_order(order)
        catalog.capture_digikey_order(duplicated, include_all(duplicated), digikey)

        second = duplicated.lines[1]
        changed = type(duplicated)(
            sales_order_number=duplicated.sales_order_number,
            order_date=duplicated.order_date,
            lines=(duplicated.lines[0],
                   type(second)(**{**second.__dict__, 'quantity': 99})),
        )
        catalog.capture_digikey_order(
            changed, {'1': {'include': True}, '2': {'include': True,
                                                    'apply_change': True}}, digikey
        )
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert sorted(p.quantity for p in product.purchases) == [5, 99], (
            'the change landed on the wrong purchase'
        )

    def test_a_vanished_duplicate_line_is_orphaned(self, catalog, order, digikey):
        duplicated = duplicate_part_order(order)
        catalog.capture_digikey_order(duplicated, include_all(duplicated), digikey)
        # DigiKey now reports only one line for that part.
        shrunk = type(order)(
            sales_order_number=order.sales_order_number,
            order_date=order.order_date,
            lines=(duplicated.lines[0],),
        )
        review = catalog.review_digikey_order(shrunk, digikey)
        assert len(review.orphaned) == 1


class TestSubCentPrices:
    """Numeric(10, 2) rounds silently; this catalog rounds deliberately."""

    def _order_at(self, order, price):
        line = order.lines[0]
        return type(order)(
            sales_order_number=order.sales_order_number,
            order_date=order.order_date,
            lines=(type(line)(**{**line.__dict__, 'unit_price': Decimal(price)}),),
        )

    def test_a_sub_cent_price_is_rounded_deliberately(self, catalog, order, digikey):
        cheap = self._order_at(order, '0.0126')
        catalog.capture_digikey_order(cheap, include_all(cheap), digikey)
        product = catalog.find_product_by_identifier('IRM-05-5', id_type='MPN')
        assert product.purchases[0].unit_price == Decimal('0.01')

    def test_update_it_does_not_reappear_forever(self, catalog, order, digikey):
        """The loop: raw 0.0126 never equals stored 0.01, so the prompt never cleared."""
        cheap = self._order_at(order, '0.0126')
        catalog.capture_digikey_order(cheap, include_all(cheap), digikey)

        review = catalog.review_digikey_order(cheap, digikey)
        line = review.lines[0]
        assert line.state is OrderLineState.CAPTURED
        assert line.has_change is False, (
            'a sub-cent line reports a change against itself on every review'
        )

    def test_a_real_change_is_still_seen_on_a_sub_cent_line(self, catalog, order, digikey):
        cheap = self._order_at(order, '0.0126')
        catalog.capture_digikey_order(cheap, include_all(cheap), digikey)
        dearer = self._order_at(order, '0.05')
        assert catalog.review_digikey_order(dearer, digikey).lines[0].has_change

    def test_the_review_says_what_will_be_stored(self, catalog, order, digikey):
        """017's precedent: tell them about the rounding now, not in a reconciliation."""
        cheap = self._order_at(order, '0.0126')
        line = catalog.review_digikey_order(cheap, digikey).lines[0]
        assert line.price_rounds is True
        assert line.unit_price_as_recorded == Decimal('0.01')

    def test_an_exact_price_reports_no_rounding(self, catalog, order, digikey):
        line = catalog.review_digikey_order(order, digikey).lines[0]
        assert line.price_rounds is False
