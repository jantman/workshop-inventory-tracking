"""Receiving a McMaster bag by scanning the part number off it (US3).

A McMaster bag carries a bare part number and nothing else -- no order, no
line, no quantity. So the scan is a FREE_TEXT one, and where it goes in
``resolve_scan`` is the whole of this feature's risk:

**the McMaster lookup comes before the vendor-scoped identifier lookup.**

Capturing an order creates products carrying those part numbers as identifiers.
Put the McMaster branch second and the identifier lookup matches first, so a bag
for a part you have bought before opens the *product page* instead of its
receipt -- working only for parts you have never had, which is exactly
backwards. It is the trap the ECIA branch already documents, and most of what is
asserted here is that it stays closed.

The other half is the non-regressions. FR-033 and SC-010 require every scan that
is not an outstanding McMaster part number to behave exactly as it does today.
"""

from decimal import Decimal

import pytest

from app.catalog_service import (
    CatalogService,
    DIGIKEY_VENDOR,
    MCMASTER_VENDOR,
)
from app.models import McMasterOrder, ScanKind

pytestmark = pytest.mark.unit

PART = '97387A173'
OTHER_PART = '3103A21'


def build_order(order_number='MISC-AND-GRINDER', order_id='6a5ffba81f17e12ac4fb7d70',
                lines=None):
    order = McMasterOrder.from_payload({
        'version': 1,
        'vendor': MCMASTER_VENDOR,
        'source_url': f'https://www.mcmaster.com/order-history/order/{order_id}',
        'order_number': order_number,
        'order_id': order_id,
        'lines': lines if lines is not None else [
            {'line_number': 1, 'part_number': PART, 'description': 'Rivets',
             'packs': 1, 'pack_size': 100, 'pack_price': '6.00'},
            {'line_number': 2, 'part_number': OTHER_PART,
             'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23'},
        ],
    })
    assert order is not None
    return order


def include_all(order):
    return {line.form_key: {'include': True} for line in order.lines}


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def captured(catalog):
    """One captured McMaster order, both lines outstanding."""
    order = build_order()
    catalog.capture_mcmaster_order(order, include_all(order))
    return order


class TestFindReceivable:

    def test_one_outstanding_match(self, catalog, captured):
        found = catalog.find_mcmaster_receivable(PART)

        assert len(found) == 1
        assert found[0].vendor_item_id == PART
        assert found[0].supplier_order_reference == 'MISC-AND-GRINDER'
        assert found[0].is_outstanding

    def test_two_outstanding_matches_across_two_orders(self, catalog, captured):
        """FR-032a. They can be weeks apart, which is why no single order
        screen can show them both."""
        second = build_order(
            order_number='LATER-ORDER', order_id='0000000000000000000000ff')
        catalog.capture_mcmaster_order(second, include_all(second))

        found = catalog.find_mcmaster_receivable(PART)

        assert len(found) == 2
        assert {p.supplier_order_reference for p in found} == {
            'MISC-AND-GRINDER', 'LATER-ORDER'
        }

    def test_a_received_only_match_returns_nothing(self, catalog, captured):
        """**Outstanding only**, and this is the one place this deliberately
        differs from find_receivable next door. DigiKey's includes received rows
        so it can tell "already received" from "no such line" for a label that
        names an order. A bare part number names no order, so there is no such
        distinction to draw."""
        purchase = catalog.find_mcmaster_receivable(PART)[0]
        catalog.receive_purchase(purchase.id)

        assert catalog.find_mcmaster_receivable(PART) == []

    def test_a_part_number_with_no_mcmaster_purchase_at_all(self, catalog):
        assert catalog.find_mcmaster_receivable('NOTHING-LIKE-THIS') == []

    def test_a_blank_scan_finds_nothing(self, catalog, captured):
        assert catalog.find_mcmaster_receivable('') == []
        assert catalog.find_mcmaster_receivable('   ') == []

    def test_another_vendors_item_id_is_not_a_mcmaster_line(self, catalog):
        """The predicate is scoped by vendor, so a DigiKey purchase carrying
        the same value cannot be claimed."""
        product = catalog.create_product(description='A DigiKey part')
        catalog.record_purchase(
            product.id, vendor=DIGIKEY_VENDOR, vendor_item_id=PART,
            supplier_order_reference='100882558', quantity=5,
        )

        assert catalog.find_mcmaster_receivable(PART) == []


class TestScanResolution:
    """The three FR-032 cases."""

    def test_an_outstanding_part_number_resolves_to_receive(
            self, catalog, captured):
        resolution = catalog.scan(PART)

        assert resolution.outcome == 'receive'
        assert len(resolution.purchases) == 1
        assert resolution.purchases[0].vendor_item_id == PART

    def test_two_outstanding_lines_still_resolve_to_receive(
            self, catalog, captured):
        """The catalog does not pick; the *route* offers the choice."""
        second = build_order(
            order_number='LATER-ORDER', order_id='0000000000000000000000ff')
        catalog.capture_mcmaster_order(second, include_all(second))

        resolution = catalog.scan(PART)

        assert resolution.outcome == 'receive'
        assert len(resolution.purchases) == 2

    def test_a_part_number_with_no_outstanding_line_falls_through(
            self, catalog, captured):
        """FR-032b, and the precedence test that matters most.

        Capturing the order created a product carrying this part number as a
        vendor-scoped identifier. Once the line is received, the scan must fall
        through to exactly today's answer -- the product page -- rather than
        offering to receive it again.
        """
        purchase = catalog.find_mcmaster_receivable(PART)[0]
        catalog.receive_purchase(purchase.id)

        resolution = catalog.scan(PART)

        assert resolution.outcome == 'product'
        assert resolution.product is not None
        assert resolution.classification.kind is ScanKind.VENDOR

    def test_the_mcmaster_branch_runs_before_the_identifier_lookup(
            self, catalog, captured):
        """The whole point of the precedence. A product carrying this part
        number exists -- the capture created it -- so an identifier-first order
        would answer 'product' here and the bag could never be received by
        scanning it."""
        assert catalog.find_product_by_identifier(
            PART, id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR) is not None

        assert catalog.scan(PART).outcome == 'receive'

    def test_an_unknown_free_text_scan_still_searches(self, catalog, captured):
        resolution = catalog.scan('something nobody has ever bought')

        assert resolution.outcome == 'search'


class TestNonRegressions:
    """FR-033 and SC-010: everything that is not an outstanding McMaster part
    number behaves exactly as it did."""

    def test_an_asin_still_resolves_to_its_product(self, catalog, captured):
        """An ASIN cannot match a McMaster purchase's vendor_item_id, and the
        fixture order is captured so the branch is live while this runs."""
        product = catalog.create_product(
            description='A power supply',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B08N5WRWNW',
                          'vendor': 'Amazon'}],
        )

        resolution = catalog.scan('B08N5WRWNW')

        assert resolution.outcome == 'product'
        assert resolution.product.id == product.id

    def test_a_gtin_never_reaches_the_free_text_branch(self, catalog, captured):
        resolution = catalog.scan('0012345678905')

        assert resolution.classification.kind is ScanKind.GTIN
        assert resolution.outcome in ('product', 'create')

    def test_an_internal_code_never_reaches_the_free_text_branch(
            self, catalog, captured):
        product = catalog.create_product(description='Something')
        internal = [
            i for i in product.identifiers if i.id_type == 'INTERNAL'
        ][0]

        resolution = catalog.scan(internal.value)

        assert resolution.classification.kind is ScanKind.INTERNAL
        assert resolution.outcome == 'product'

    def test_an_ecia_label_still_takes_the_ecia_branch(self, catalog, captured):
        """A DigiKey bag label. It is a structured scan and never free text."""
        label = '[)>\x1e06\x1dP1866-3027-ND\x1d1PIRM-05-5\x1dQ5\x1d1K100882558\x1e\x04'

        resolution = catalog.scan(label)

        assert resolution.classification.kind is ScanKind.ECIA

    def test_a_digikey_bag_still_resolves_to_receive_against_its_order(
            self, catalog, captured):
        """The DigiKey path is untouched (FR-033)."""
        product = catalog.create_product(description='A DigiKey part')
        catalog.record_purchase(
            product.id, vendor=DIGIKEY_VENDOR, vendor_item_id='1866-3027-ND',
            supplier_order_reference='100882558', quantity=5,
            unit_price=Decimal('1.50'),
        )
        label = '[)>\x1e06\x1dP1866-3027-ND\x1d1PIRM-05-5\x1dQ5\x1d1K100882558\x1e\x04'

        resolution = catalog.scan(label)

        assert resolution.outcome == 'receive'
        assert resolution.purchases[0].vendor == DIGIKEY_VENDOR


class TestReceiveUrl:
    """``_receive_url`` stopped reading ecia_fields, which are empty for a
    free-text scan. FR-033 protects the three DigiKey outcomes."""

    def digikey_scan(self, catalog, quantity=5, received=False):
        product = catalog.create_product(description='A DigiKey part')
        purchase = catalog.record_purchase(
            product.id, vendor=DIGIKEY_VENDOR, vendor_item_id='1866-3027-ND',
            supplier_order_reference='100882558', quantity=quantity,
        )
        if received:
            catalog.receive_purchase(purchase.id)
        label = ('[)>\x1e06\x1dP1866-3027-ND\x1d1PIRM-05-5\x1dQ5'
                 '\x1d1K100882558\x1e\x04')
        return catalog.scan(label)

    def test_one_outstanding_digikey_line_goes_to_its_receipt(
            self, catalog, app):
        from app.product.routes import _receive_url

        resolution = self.digikey_scan(catalog)

        with app.test_request_context():
            url = _receive_url(resolution)

        assert '/purchases/' in url and '/receive' in url
        assert 'quantity=5' in url

    def test_several_digikey_lines_go_to_the_order_screen(self, catalog, app):
        from app.product.routes import _receive_url

        product = catalog.create_product(description='A DigiKey part')
        for _ in range(2):
            catalog.record_purchase(
                product.id, vendor=DIGIKEY_VENDOR,
                vendor_item_id='1866-3027-ND',
                supplier_order_reference='100882558', quantity=5,
            )
        label = ('[)>\x1e06\x1dP1866-3027-ND\x1d1PIRM-05-5\x1dQ5'
                 '\x1d1K100882558\x1e\x04')
        resolution = catalog.scan(label)

        with app.test_request_context():
            url = _receive_url(resolution)

        assert '/products/digikey/orders/100882558' in url
        assert 'highlight=1866-3027-ND' in url

    def test_an_already_received_digikey_line_goes_to_the_order_screen(
            self, catalog, app):
        from app.product.routes import _receive_url

        resolution = self.digikey_scan(catalog, received=True)

        with app.test_request_context():
            url = _receive_url(resolution)

        assert '/products/digikey/orders/100882558' in url

    def test_the_order_number_comes_off_the_purchase_not_the_scan(
            self, catalog, app):
        """The change itself. It used to be read from ecia_fields['1K'], which
        a free-text scan leaves empty -- so a McMaster match would have built
        an order URL with a blank order number."""
        from app.product.routes import _receive_url

        resolution = self.digikey_scan(catalog, received=True)
        # Empty the field the old implementation read, and the URL must be
        # unchanged because the purchases carry the order number either way.
        resolution.classification.ecia_fields.clear()

        with app.test_request_context():
            url = _receive_url(resolution)

        assert '/products/digikey/orders/100882558' in url

    def test_one_outstanding_mcmaster_line_goes_to_its_receipt(
            self, catalog, captured, app):
        from app.product.routes import _receive_url

        resolution = catalog.scan(PART)

        with app.test_request_context():
            url = _receive_url(resolution)

        assert '/purchases/' in url and '/receive' in url
        # A McMaster bag states no quantity, so none is pre-filled from it.
        assert 'quantity=' not in url

    def test_several_mcmaster_lines_go_to_the_chooser(
            self, catalog, captured, app):
        """FR-032a, and research.md §11: they can be on orders weeks apart, so
        there is no single order screen that shows both."""
        from app.product.routes import _receive_url

        second = build_order(
            order_number='LATER-ORDER', order_id='0000000000000000000000ff')
        catalog.capture_mcmaster_order(second, include_all(second))
        resolution = catalog.scan(PART)

        with app.test_request_context():
            url = _receive_url(resolution)

        assert '/products/purchases/receive-choice' in url
        assert f'scan={PART}' in url
