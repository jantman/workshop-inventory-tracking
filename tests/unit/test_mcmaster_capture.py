"""Reviewing and capturing a McMaster order (feature 028, US1).

Two halves, and the line between them is the point:

* ``review_mcmaster_order`` reads and decides. It **writes nothing**, so the
  operator can close the tab and leave no trace (FR-005).
* ``capture_mcmaster_order`` writes, and writes the whole order in one
  transaction, so a failure part-way through leaves nothing behind (SC-009).

The difference from the DigiKey pair next door is that **the vendor cannot be
re-read**. There is no client here and no enrichment: the payload the review was
built from is the authority at confirmation, because the page is gone.
"""

from decimal import Decimal

import pytest

from app.catalog_service import CatalogService, MCMASTER_VENDOR
from app.exceptions import ValidationError
from app.models import (
    MCMASTER_PAYLOAD_VENDOR,
    MCMASTER_PAYLOAD_VERSION,
    IdentifierType,
    McMasterOrder,
    OrderLineState,
)

pytestmark = pytest.mark.unit


def build_order(lines=None, **overrides):
    """A parsed McMaster order, built the way the route builds one."""
    body = {
        'version': MCMASTER_PAYLOAD_VERSION,
        'vendor': MCMASTER_PAYLOAD_VENDOR,
        'source_url': 'https://www.mcmaster.com/order-history/order/'
                      '6a5ffba81f17e12ac4fb7d70',
        'order_number': 'MISC-AND-GRINDER',
        'order_id': '6a5ffba81f17e12ac4fb7d70',
        'order_date': 'November 16, 2025',
        'lines': lines if lines is not None else [
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
                'description': 'Stainless Steel Domed Head Solid Rivets',
                'packs': 2,
                'pack_size': 100,
                'pack_price': '6.00',
            },
        ],
    }
    body.update(overrides)
    order = McMasterOrder.from_payload(body)
    assert order is not None
    return order


def include_all(order, **extra):
    return {
        line.form_key: dict({'include': True}, **extra) for line in order.lines
    }


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def order():
    return build_order()


# --------------------------------------------------------------------------
# review_mcmaster_order -- reads and decides, writes nothing
# --------------------------------------------------------------------------

class TestReviewStates:
    """The four states, tested in the order the code tests them."""

    def test_a_line_matching_nothing_is_new(self, catalog, order):
        review = catalog.review_mcmaster_order(order)

        assert [line.state for line in review.lines] == [
            OrderLineState.NEW, OrderLineState.NEW,
        ]
        assert review.lines[0].product_id is None

    def test_a_line_whose_part_number_is_held_is_matched(self, catalog, order):
        product = catalog.create_product(
            description='Counterbore pilot',
            identifiers=[{
                'id_type': 'DISTRIBUTOR', 'value': '3103A21',
                'vendor': MCMASTER_VENDOR,
            }],
        )

        review = catalog.review_mcmaster_order(order)

        assert review.lines[0].state is OrderLineState.MATCHED
        assert review.lines[0].product_id == product.id
        assert review.lines[0].product_description == 'Counterbore pilot'

    def test_the_distributor_identifier_is_scoped_to_mcmaster(
            self, catalog, order):
        """The same part number held for another vendor is not this part."""
        catalog.create_product(
            description='Something else entirely',
            identifiers=[{
                'id_type': 'DISTRIBUTOR', 'value': '3103A21',
                'vendor': 'DigiKey',
            }],
        )

        review = catalog.review_mcmaster_order(order)

        assert review.lines[0].state is OrderLineState.NEW

    def test_a_contradicted_part_number_is_a_conflict(self, catalog):
        """FR-018. Unreachable from a real McMaster page today, because they
        state no manufacturer part number -- but the check is the one that
        matters most when it does fire, since nothing looks wrong afterwards."""
        catalog.create_product(
            description='A different part',
            manufacturer_part_number='REAL-MPN-1',
            identifiers=[{
                'id_type': 'DISTRIBUTOR', 'value': '3103A21',
                'vendor': MCMASTER_VENDOR,
            }],
        )
        order = build_order(lines=[{
            'line_number': 1, 'part_number': '3103A21',
            'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23',
            'manufacturer_part_number': 'DIFFERENT-MPN',
        }])

        review = catalog.review_mcmaster_order(order)

        assert review.lines[0].state is OrderLineState.CONFLICT
        assert review.lines[0].product_manufacturer_part_number == 'REAL-MPN-1'

    def test_an_already_captured_line_is_captured(self, catalog, order):
        catalog.capture_mcmaster_order(order, include_all(order))

        review = catalog.review_mcmaster_order(order)

        assert [line.state for line in review.lines] == [
            OrderLineState.CAPTURED, OrderLineState.CAPTURED,
        ]
        assert review.lines[0].purchase_id is not None
        assert review.lines[0].recorded_quantity == 1

    def test_captured_is_decided_before_matched(self, catalog, order):
        """A line already recorded is not a line to decide anything else
        about, so CAPTURED wins over the identifier its own capture wrote."""
        catalog.capture_mcmaster_order(order, include_all(order))

        review = catalog.review_mcmaster_order(order)

        assert review.lines[0].state is OrderLineState.CAPTURED

    def test_a_line_with_no_part_number_is_reviewed_not_refused(self, catalog):
        """FR-019."""
        order = build_order(lines=[
            {'line_number': 1, 'description': 'Handling', 'packs': 1,
             'pack_price': '4.50'},
        ])

        review = catalog.review_mcmaster_order(order)

        assert review.lines[0].state is OrderLineState.NEW
        assert review.lines[0].line.part_number == ''

    def test_part_is_never_enriched_because_the_page_is_the_detail(
            self, catalog, order):
        review = catalog.review_mcmaster_order(order)

        assert all(line.part is None for line in review.lines)
        assert all(not line.is_enriched for line in review.lines)

    def test_a_suggested_description_is_cut_to_what_fits(self, catalog):
        """Pre-filled with a value that fits, rather than silently truncated
        at the point of writing."""
        order = build_order(lines=[{
            'line_number': 1, 'part_number': '3103A21',
            'description': 'x' * 400, 'packs': 1, 'pack_price': '1.00',
        }])

        review = catalog.review_mcmaster_order(order)

        assert len(review.lines[0].suggested_description) == 255

    def test_the_review_writes_nothing(self, catalog, order):
        """FR-005. Closing the tab must leave no trace."""
        catalog.review_mcmaster_order(order)

        assert catalog.list_products() == []


# --------------------------------------------------------------------------
# capture_mcmaster_order -- the write
# --------------------------------------------------------------------------

class TestCapture:

    def test_one_purchase_per_included_line(self, catalog, order):
        result = catalog.capture_mcmaster_order(order, include_all(order))

        assert len(result.purchase_ids) == 2
        assert result.products_created == 2

    def test_the_purchase_carries_what_the_page_said(self, catalog, order):
        catalog.capture_mcmaster_order(order, include_all(order))

        product = catalog.find_product_by_identifier(
            '3103A21', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR)
        purchase = product.purchases[0]
        assert purchase.vendor == MCMASTER_VENDOR
        assert purchase.supplier_order_reference == 'MISC-AND-GRINDER'
        assert purchase.vendor_order_id == '6a5ffba81f17e12ac4fb7d70'
        assert purchase.order_line_number == 1
        assert purchase.vendor_item_id == '3103A21'
        assert purchase.quantity == 1
        assert purchase.unit_price == Decimal('10.23')
        assert purchase.order_date is not None

    def test_a_pack_line_records_units_and_a_unit_price(self, catalog, order):
        """FR-020: two packs of 100 at 6.00 a pack is 200 units at 0.06."""
        catalog.capture_mcmaster_order(order, include_all(order))

        product = catalog.find_product_by_identifier(
            '97387A173', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR)
        purchase = product.purchases[0]
        assert purchase.quantity == 200
        assert purchase.unit_price == Decimal('0.06')

    def test_every_captured_line_is_outstanding(self, catalog, order):
        """FR-011. Delivered is McMaster's state; received is the operator's."""
        catalog.capture_mcmaster_order(order, include_all(order))

        lines = catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')
        assert len(lines) == 2
        assert all(p.received_date is None for p in lines)
        assert all(p.is_outstanding for p in lines)

    def test_an_excluded_line_writes_nothing_at_all(self, catalog, order):
        """FR-009: an excluded line becomes nothing, and its exclusion is not
        recorded either."""
        decisions = {order.lines[0].form_key: {'include': True}}

        result = catalog.capture_mcmaster_order(order, decisions)

        assert len(result.purchase_ids) == 1
        assert result.lines_excluded == 1
        assert catalog.find_product_by_identifier(
            '97387A173', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR) is None

    def test_a_new_line_creates_a_product_with_a_scoped_identifier(
            self, catalog, order):
        """FR-012."""
        catalog.capture_mcmaster_order(order, include_all(order))

        product = catalog.find_product_by_identifier(
            '3103A21', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR)
        assert product is not None
        scoped = [
            i for i in product.identifiers
            if i.id_type == IdentifierType.DISTRIBUTOR.value
        ]
        assert [(i.value, i.vendor) for i in scoped] == [
            ('3103A21', MCMASTER_VENDOR)
        ]

    def test_no_mpn_is_written_when_the_page_stated_none(self, catalog, order):
        """FR-012, and it is the inverse of the DigiKey case. Inventing an MPN
        McMaster never stated would collide with a real one later."""
        catalog.capture_mcmaster_order(order, include_all(order))

        product = catalog.find_product_by_identifier(
            '3103A21', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR)
        assert not [
            i for i in product.identifiers
            if i.id_type == IdentifierType.MPN.value
        ]
        assert not product.manufacturer_part_number

    def test_an_mpn_is_written_when_the_page_stated_one(self, catalog):
        order = build_order(lines=[{
            'line_number': 1, 'part_number': '3103A21',
            'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23',
            'manufacturer_part_number': 'ACME-99',
        }])

        catalog.capture_mcmaster_order(order, include_all(order))

        product = catalog.find_product_by_identifier(
            'ACME-99', id_type='MPN')
        assert product is not None
        assert product.manufacturer_part_number == 'ACME-99'

    def test_the_operator_description_wins_over_mcmasters(self, catalog, order):
        decisions = include_all(order)
        decisions[order.lines[0].form_key]['description'] = 'Counterbore pilot'

        catalog.capture_mcmaster_order(order, decisions)

        product = catalog.find_product_by_identifier(
            '3103A21', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR)
        assert product.description == 'Counterbore pilot'

    def test_mcmasters_wording_is_kept_on_the_purchase(self, catalog, order):
        """FR-023: kept distinct from the operator's product description."""
        decisions = include_all(order)
        decisions[order.lines[0].form_key]['description'] = 'Counterbore pilot'

        catalog.capture_mcmaster_order(order, decisions)

        product = catalog.find_product_by_identifier(
            '3103A21', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR)
        assert product.purchases[0].listing_title.startswith('Steel Pilot')

    def test_an_edited_quantity_and_price_overrule_the_computed_ones(
            self, catalog, order):
        """FR-020a. The operator can see the box and the page; this code can
        only see the page."""
        decisions = include_all(order)
        decisions[order.lines[1].form_key].update(
            {'quantity': '150', 'unit_price': '0.09'})

        catalog.capture_mcmaster_order(order, decisions)

        product = catalog.find_product_by_identifier(
            '97387A173', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR)
        assert product.purchases[0].quantity == 150
        assert product.purchases[0].unit_price == Decimal('0.09')

    def test_a_matched_line_attaches_rather_than_creating(self, catalog, order):
        existing = catalog.create_product(
            description='Counterbore pilot',
            identifiers=[{
                'id_type': 'DISTRIBUTOR', 'value': '3103A21',
                'vendor': MCMASTER_VENDOR,
            }],
        )

        result = catalog.capture_mcmaster_order(order, include_all(order))

        assert result.products_attached == 1
        assert result.products_created == 1
        product = catalog.get_product(existing.id)
        assert len(product.purchases) == 1


class TestRecapture:
    """FR-015 to FR-017, and SC-003."""

    def test_a_second_capture_of_the_same_order_records_nothing(
            self, catalog, order):
        """SC-003."""
        catalog.capture_mcmaster_order(order, include_all(order))

        again = catalog.capture_mcmaster_order(order, include_all(order))

        assert again.purchase_ids == ()
        assert again.lines_already_captured == 2
        assert again.products_created == 0
        assert len(catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')) == 2

    def test_a_changed_quantity_is_shown_but_not_applied_unasked(
            self, catalog, order):
        catalog.capture_mcmaster_order(order, include_all(order))
        changed = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 6, 'pack_price': '10.23'},
        ])

        review = catalog.review_mcmaster_order(changed)
        assert review.lines[0].state is OrderLineState.CAPTURED
        assert review.lines[0].has_change
        assert review.lines[0].recorded_quantity == 1

        result = catalog.capture_mcmaster_order(changed, {})
        assert result.lines_updated == 0
        lines = catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')
        assert lines[0].quantity == 1

    def test_a_changed_quantity_is_applied_on_apply_change(
            self, catalog, order):
        """FR-017."""
        catalog.capture_mcmaster_order(order, include_all(order))
        changed = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 6, 'pack_price': '10.23'},
        ])

        result = catalog.capture_mcmaster_order(
            changed, {'1': {'apply_change': True}})

        assert result.lines_updated == 1
        assert result.purchase_ids == ()
        lines = catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')
        assert lines[0].quantity == 6

    def test_a_sub_cent_line_does_not_report_a_change_forever(
            self, catalog):
        """Both sides rounded. The recorded price has been through a
        Numeric(10, 2) column and the freshly-read one has not; comparing raw
        against stored made "Update it?" reappear on every review with no way
        to clear it. PR #116 review, and pack division reaches it too."""
        order = build_order(lines=[
            {'line_number': 1, 'part_number': '97387A173',
             'description': 'Rivets', 'packs': 1, 'pack_size': 100,
             'pack_price': '6.66'},
        ])
        catalog.capture_mcmaster_order(order, include_all(order))

        review = catalog.review_mcmaster_order(order)

        assert review.lines[0].state is OrderLineState.CAPTURED
        assert not review.lines[0].has_change, (
            '0.0666 read against 0.07 stored reported a change that applying '
            'could never clear'
        )

    def test_a_fresh_capture_reports_nothing_as_orphaned(self, catalog, order):
        """The lines a capture just wrote are not stale lines.

        `_orphaned_mcmaster_purchases` re-queries inside the open session, so
        the rows the loop has flushed come back from that query -- while the
        pairing it subtracts was built before the loop and cannot name them.
        Left uncorrected, every line of a brand-new order was reported as
        orphaned by the capture that created it, and the flash told the
        operator the lines they had just captured no longer belonged to the
        order. PR #123 review.
        """
        result = catalog.capture_mcmaster_order(order, include_all(order))

        assert len(result.purchase_ids) == 2
        assert result.orphaned == (), (
            'the capture reported its own new purchases as orphaned'
        )

    def test_a_genuine_orphan_is_still_reported_by_a_capture(self, catalog):
        """The other half: the fix must not silence a real one."""
        order = build_order()
        catalog.capture_mcmaster_order(order, include_all(order))
        shrunk = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23'},
        ])

        result = catalog.capture_mcmaster_order(shrunk, include_all(shrunk))

        assert len(result.orphaned) == 1
        assert len(catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')) == 2

    def test_a_purchase_no_line_claims_is_reported_and_not_deleted(
            self, catalog, order):
        """FR-016."""
        catalog.capture_mcmaster_order(order, include_all(order))
        shrunk = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23'},
        ])

        review = catalog.review_mcmaster_order(shrunk)

        assert len(review.orphaned) == 1
        assert len(catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')) == 2

    def test_two_lines_of_one_part_pair_by_line_number(self, catalog):
        """The corruption PR #116 bought: pairing positionally or by part
        number let one line claim the other's purchase."""
        order = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Pilot', 'packs': 1, 'pack_price': '10.23'},
            {'line_number': 2, 'part_number': '3103A21',
             'description': 'Pilot', 'packs': 4, 'pack_price': '10.23'},
        ])
        catalog.capture_mcmaster_order(order, include_all(order))

        lines = catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')
        assert sorted(p.order_line_number for p in lines) == [1, 2]
        assert sorted(p.quantity for p in lines) == [1, 4]

        review = catalog.review_mcmaster_order(order)
        assert [line.recorded_quantity for line in review.lines] == [1, 4]

    def test_applying_a_change_cannot_land_on_the_other_line(self, catalog):
        order = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Pilot', 'packs': 1, 'pack_price': '10.23'},
            {'line_number': 2, 'part_number': '3103A21',
             'description': 'Pilot', 'packs': 4, 'pack_price': '10.23'},
        ])
        catalog.capture_mcmaster_order(order, include_all(order))

        catalog.capture_mcmaster_order(order, {
            '1': {'apply_change': True}, '2': {'apply_change': True},
        })

        lines = catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')
        assert sorted(p.quantity for p in lines) == [1, 4]

    def test_an_unread_value_is_not_a_change(self, catalog, order):
        """FR-036/FR-037. A field the page did not give says nothing about
        whether the line differs from what is recorded.

        Comparing it anyway reported a change on every degraded line, offered
        an "Update it?" whose write is then skipped as a no-op, and rendered
        the reason as "the page now says 1 at None". PR #123 review.
        """
        catalog.capture_mcmaster_order(order, include_all(order))
        # The price selector stopped matching; everything else still reads.
        degraded = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 1},
        ])

        review = catalog.review_mcmaster_order(degraded)

        assert review.lines[0].state is OrderLineState.CAPTURED
        assert not review.lines[0].has_change

    def test_a_real_change_beside_an_unread_one_is_still_a_change(
            self, catalog, order):
        """The guard must not swallow a change in the field that *was* read."""
        catalog.capture_mcmaster_order(order, include_all(order))
        degraded = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 9},
        ])

        review = catalog.review_mcmaster_order(degraded)

        assert review.lines[0].has_change
        assert review.lines[0].line.unit_price is None

    def test_applying_a_change_that_writes_nothing_is_not_counted(
            self, catalog, order):
        """Otherwise the flash reports "1 line(s) updated" for a skipped
        write."""
        catalog.capture_mcmaster_order(order, include_all(order))
        degraded = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 1},
        ])

        result = catalog.capture_mcmaster_order(
            degraded, {'1': {'apply_change': True}})

        assert result.lines_updated == 0
        assert not result.wrote_anything

    def test_a_renamed_order_is_refiled_under_its_new_name(
            self, catalog, order):
        """The id is the identity; the Purchase Order string is a label.

        The order screen is keyed by the name, because that is the only thing
        a human can type -- so leaving the rows under the old name meant a
        re-capture reconciled perfectly and then redirected the operator to a
        page reading "Nothing captured under this order". PR #123 review.
        """
        catalog.capture_mcmaster_order(order, include_all(order))
        renamed = build_order(order_number='GRINDER-AND-MISC')

        result = catalog.capture_mcmaster_order(renamed, include_all(renamed))

        assert result.renamed_from == 'MISC-AND-GRINDER'
        assert result.wrote_anything, 'a refile is a write and must be reported'
        assert len(catalog.find_mcmaster_order_lines('GRINDER-AND-MISC')) == 2
        assert catalog.find_mcmaster_order_lines('MISC-AND-GRINDER') == []

    def test_a_rename_that_also_adds_a_line_keeps_the_order_whole(
            self, catalog, order):
        """Without the refile this split one order across two names, with no
        view showing it whole."""
        catalog.capture_mcmaster_order(order, include_all(order))
        grown = build_order(order_number='GRINDER-AND-MISC', lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Pilot', 'packs': 1, 'pack_price': '10.23'},
            {'line_number': 5, 'part_number': '97387A173',
             'description': 'Rivets', 'packs': 2, 'pack_size': 100,
             'pack_price': '6.00'},
            {'line_number': 6, 'part_number': '2652N1',
             'description': 'Masonry bit', 'packs': 1, 'pack_price': '21.59'},
        ])

        catalog.capture_mcmaster_order(grown, include_all(grown))

        assert len(catalog.find_mcmaster_order_lines('GRINDER-AND-MISC')) == 3

    def test_nothing_is_refiled_when_the_name_did_not_change(
            self, catalog, order):
        result = catalog.capture_mcmaster_order(order, include_all(order))

        assert result.renamed_from == ''

    def test_a_payload_with_no_order_id_refiles_nothing(self, catalog):
        """No id, no identity to rename *from* -- and a row this feature never
        wrote has no business being renamed."""
        order = build_order(order_id='')
        catalog.capture_mcmaster_order(order, include_all(order))
        renamed = build_order(order_id='', order_number='SOMETHING-ELSE')

        result = catalog.capture_mcmaster_order(renamed, include_all(renamed))

        assert result.renamed_from == ''
        assert len(catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')) == 2

    def test_a_renamed_purchase_order_still_reconciles(self, catalog, order):
        """research.md §14, and the whole reason vendor_order_id exists. The
        Purchase Order string is editable in place on McMaster's page; without
        the id, a rename makes every line read as new and confirming writes a
        second purchase for each one."""
        catalog.capture_mcmaster_order(order, include_all(order))
        renamed = build_order(order_number='GRINDER-AND-MISC')

        review = catalog.review_mcmaster_order(renamed)

        assert [line.state for line in review.lines] == [
            OrderLineState.CAPTURED, OrderLineState.CAPTURED,
        ]
        again = catalog.capture_mcmaster_order(renamed, include_all(renamed))
        assert again.purchase_ids == ()

    def test_two_orders_sharing_a_name_do_not_reconcile_against_each_other(
            self, catalog, order):
        """Auto-generated Purchase Order names are MMDD+SURNAME, so two orders
        placed on one day collide. Without the id, the second order would read
        as already captured and record nothing -- silently losing it.

        MATCHED, not NEW, is the right answer: the first capture created
        products carrying these part numbers, so the second order attaches to
        them. What must not happen is CAPTURED.
        """
        catalog.capture_mcmaster_order(order, include_all(order))
        other = build_order(order_id='0000000000000000000000ff')

        review = catalog.review_mcmaster_order(other)

        assert [line.state for line in review.lines] == [
            OrderLineState.MATCHED, OrderLineState.MATCHED,
        ]

        result = catalog.capture_mcmaster_order(other, include_all(other))
        assert len(result.purchase_ids) == 2, (
            'the second order recorded nothing -- it was mistaken for the '
            'first because they share an auto-generated name'
        )
        assert result.products_created == 0

        # **Four lines under one name is by design, not the bug above.**
        # `find_mcmaster_order_lines` is keyed by the Purchase Order string
        # because that is the only identifier a human can recognise or type,
        # and two orders that genuinely share a name are indistinguishable to
        # someone typing it. Showing both beats showing one arbitrarily or
        # showing none. What must not happen -- and does not -- is the second
        # order being *mistaken* for the first and recording nothing, which is
        # what the assertion above covers. PR #123 review.
        assert len(catalog.find_mcmaster_order_lines('MISC-AND-GRINDER')) == 4

    def test_a_hand_recorded_purchase_with_no_line_number_still_pairs(
            self, catalog, order):
        """Pass two. The Add Purchase form sets no line number and no order
        id, and must go on reconciling exactly as it does today."""
        product = catalog.create_product(description='Bought by hand')
        catalog.record_purchase(
            product.id, vendor=MCMASTER_VENDOR, vendor_item_id='3103A21',
            supplier_order_reference='MISC-AND-GRINDER', quantity=1,
        )

        review = catalog.review_mcmaster_order(order)

        assert review.lines[0].state is OrderLineState.CAPTURED
        assert review.lines[0].product_id == product.id


class TestNothingIsWrittenOnFailure:

    def test_a_conflicted_line_with_no_resolution_refuses_the_capture(
            self, catalog):
        catalog.create_product(
            description='A different part',
            manufacturer_part_number='REAL-MPN-1',
            identifiers=[{
                'id_type': 'DISTRIBUTOR', 'value': '3103A21',
                'vendor': MCMASTER_VENDOR,
            }],
        )
        order = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23',
             'manufacturer_part_number': 'DIFFERENT-MPN'},
            {'line_number': 2, 'part_number': '97387A173',
             'description': 'Rivets', 'packs': 1, 'pack_price': '6.00'},
        ])

        with pytest.raises(ValidationError):
            catalog.capture_mcmaster_order(order, include_all(order))

    def test_a_refused_description_leaves_the_database_unchanged(self, catalog):
        """SC-009. The operator answered a question about an order, not about
        a line, and half an order is worse than none."""
        order = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Pilot', 'packs': 1, 'pack_price': '10.23'},
            {'line_number': 2, 'part_number': '97387A173',
             'description': 'Rivets', 'packs': 1, 'pack_price': '6.00'},
        ])
        decisions = include_all(order)
        decisions['2']['description'] = 'x' * 400

        with pytest.raises(ValidationError):
            catalog.capture_mcmaster_order(order, decisions)

        assert catalog.list_products() == []
        assert catalog.find_mcmaster_order_lines('MISC-AND-GRINDER') == []

    def test_the_conflict_resolution_attaches_when_asked(self, catalog):
        existing = catalog.create_product(
            description='A different part',
            manufacturer_part_number='REAL-MPN-1',
            identifiers=[{
                'id_type': 'DISTRIBUTOR', 'value': '3103A21',
                'vendor': MCMASTER_VENDOR,
            }],
        )
        order = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23',
             'manufacturer_part_number': 'DIFFERENT-MPN'},
        ])

        result = catalog.capture_mcmaster_order(
            order, {'1': {'include': True, 'resolution': 'attach'}})

        assert result.products_attached == 1
        assert catalog.get_product(existing.id).purchases[0].quantity == 1

    def test_the_conflict_resolution_creates_a_separate_product_when_asked(
            self, catalog):
        existing = catalog.create_product(
            description='A different part',
            manufacturer_part_number='REAL-MPN-1',
            identifiers=[{
                'id_type': 'DISTRIBUTOR', 'value': '3103A21',
                'vendor': MCMASTER_VENDOR,
            }],
        )
        order = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 1, 'pack_price': '10.23',
             'manufacturer_part_number': 'DIFFERENT-MPN'},
        ])

        result = catalog.capture_mcmaster_order(
            order, {'1': {'include': True, 'resolution': 'separate'}})

        assert result.products_created == 1
        # The contested identifier stays where it was.
        held = catalog.find_product_by_identifier(
            '3103A21', id_type='DISTRIBUTOR', vendor=MCMASTER_VENDOR)
        assert held.id == existing.id


class TestCaptureReporting:
    """What the flash has to be able to say (FR-028, FR-037)."""

    def test_a_bare_change_application_counts_as_having_written(
            self, catalog, order):
        """Leading on the purchase count alone would report "nothing new" over
        the top of a write that landed."""
        catalog.capture_mcmaster_order(order, include_all(order))
        changed = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Pilot', 'packs': 6, 'pack_price': '10.23'},
        ])

        result = catalog.capture_mcmaster_order(
            changed, {'1': {'apply_change': True}})

        assert result.purchase_ids == ()
        assert result.wrote_anything

    def test_a_capture_that_did_nothing_says_so(self, catalog, order):
        result = catalog.capture_mcmaster_order(order, {})

        assert not result.wrote_anything
        assert result.lines_excluded == 2

    def test_a_line_the_page_gave_up_thin_is_named(self, catalog):
        """FR-037, carried past the review so the record survives leaving it."""
        order = build_order(lines=[
            {'line_number': 1, 'part_number': '3103A21',
             'description': 'Steel Pilot', 'packs': 1},
        ])

        result = catalog.capture_mcmaster_order(order, include_all(order))

        assert result.lines_incomplete == ('Steel Pilot',)

    def test_a_fully_read_capture_names_nothing_as_thin(self, catalog, order):
        result = catalog.capture_mcmaster_order(order, include_all(order))

        assert result.lines_incomplete == ()
