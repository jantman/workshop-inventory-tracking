"""
Unit tests for order-time capture and receipt.

Four properties carry this story now. The operator's own wording is authored at
capture and correctable at receipt; a capture that looks like a repeat is put to
the operator rather than silently swallowed; an item id that already names a
product is put to them too, unless the manufacturer and part number corroborate;
and the details captured at order time are amendable when the thing actually
turns up in a different quantity or at a different price.

**Capture used to be idempotent and is not any more.** ``TestDuplicateDetection``
is what ``TestIdempotency`` became: the same four questions about what counts as
the same capture, with "returns the existing purchase" replaced by "raises, and
writes nothing". The system cannot tell a double-click from a second order of the
same thing on the same day, and the operator can.
"""

import json
import re
from datetime import datetime
from decimal import Decimal

import pytest
from markupsafe import escape

from app.catalog_service import CatalogService, _is_barcode_row_name
from app.exceptions import CaptureDecisionRequired, ValidationError
from app.models import ListingCapture

AMAZON_URL = 'https://www.amazon.com/dp/B0ABCDEFGH/ref=sr_1_3'
MCMASTER_URL = 'https://www.mcmaster.com/91290A115/'


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


class TestCapture:
    def test_capture_creates_an_unreceived_purchase(self, service):
        """FR-020: the order is recorded, not the receipt"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='Blue Widget 10-Pack', url=AMAZON_URL,
        )

        assert purchase.received_date is None
        assert purchase.is_outstanding is True
        assert purchase.vendor == 'Amazon'
        assert purchase.vendor_item_id == 'B0ABCDEFGH'
        assert purchase.listing_title == 'Blue Widget 10-Pack'

    def test_capture_creates_a_product_when_nothing_matches(self, service):
        """FR-021, the 'otherwise' half"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='Blue Widget 10-Pack',
        )
        product = service.get_product(purchase.product_id)

        assert product is not None
        assert product.description == 'Blue Widget 10-Pack'

    def test_the_listing_title_becomes_the_starting_description(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Raw vendor wording',
        )
        assert service.get_product(purchase.product_id).description == 'Raw vendor wording'

    def test_capture_records_the_price_as_a_decimal(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', unit_price='12.34',
        )
        assert isinstance(purchase.unit_price, Decimal)
        assert purchase.unit_price == Decimal('12.34')

    def test_a_float_price_is_refused(self, service):
        """Constitution III, enforced at the boundary rather than hoped for"""
        with pytest.raises(ValidationError):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH', unit_price=12.34,
            )

    def test_vendor_is_required(self, service):
        with pytest.raises(ValidationError):
            service.capture_order(vendor='', vendor_item_id='B0ABCDEFGH')

    def test_the_url_is_kept(self, service):
        """In its own column, not smuggled into the notes the operator owns"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', url=AMAZON_URL
        )
        assert purchase.listing_url == AMAZON_URL
        assert not purchase.notes


class TestDescriptionAtCapture:
    """FR-001 to FR-006: the operator's own wording, written at the listing"""

    def test_the_entered_description_becomes_the_products(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='BLUE WIDGET 10 PACK BEST QUALITY ✨ FREE SHIPPING',
            description='Blue widget, 10mm',
        )
        assert service.get_product(purchase.product_id).description == 'Blue widget, 10mm'

    def test_the_vendors_title_is_kept_alongside_it(self, service):
        """FR-004: what the listing said is still the record of what it said"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='BLUE WIDGET 10 PACK', description='Blue widget, 10mm',
        )
        assert purchase.listing_title == 'BLUE WIDGET 10 PACK'

    def test_a_blank_description_falls_back_to_the_listing_title(self, service):
        """FR-003: the one-click case stays one click"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='Raw vendor wording', description='',
        )
        assert service.get_product(purchase.product_id).description == 'Raw vendor wording'

    def test_a_whitespace_only_description_is_treated_as_blank(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='Raw vendor wording', description='   ',
        )
        assert service.get_product(purchase.product_id).description == 'Raw vendor wording'

    def test_no_description_and_no_title_still_yields_something(self, service):
        purchase = service.capture_order(vendor='Amazon', vendor_item_id='B0ABCDEFGH')
        product = service.get_product(purchase.product_id)
        assert 'B0ABCDEFGH' in product.description

    def test_an_over_long_description_is_refused_rather_than_truncated(self, service):
        """FR-006: a truncated description is a wrong label"""
        with pytest.raises(ValidationError) as excinfo:
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH', description='x' * 300,
            )
        assert excinfo.value.field == 'description'
        assert service.list_products() == []

    def test_manufacturer_and_part_number_are_recorded(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', description='12V PSU',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
        )
        product = service.get_product(purchase.product_id)
        assert product.manufacturer == 'Mean Well'
        assert product.manufacturer_part_number == 'RS-15-12'

    def test_attaching_with_a_new_description_updates_the_product(self, service):
        """FR-005: the operator is looking at the listing and is the authority"""
        existing = service.create_product(
            description='Blue widget, old wording',
            manufacturer='Acme', manufacturer_part_number='BW-10',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Acme', manufacturer_part_number='BW-10',
            description='Blue widget, 10mm, the good ones',
        )
        assert service.get_product(existing.id).description == (
            'Blue widget, 10mm, the good ones'
        )

    def test_attaching_never_rewrites_the_matched_products_manufacturer(self, service):
        """A mismatch there is the evidence the recycled-id question needs"""
        existing = service.create_product(
            description='Blue widget',
            manufacturer='Acme', manufacturer_part_number='BW-10',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Acme', manufacturer_part_number='BW-10',
            description='Blue widget, restated',
        )
        product = service.get_product(existing.id)
        assert product.manufacturer == 'Acme'
        assert product.manufacturer_part_number == 'BW-10'


class TestDuplicateDetection:
    """What ``TestIdempotency`` became.

    The same questions about what counts as the same capture; a different answer
    to what to do about it. Capture warns and lets the operator decide (FR-015)
    because two separate orders of one thing on one day are a real thing that the
    old idempotency silently merged.
    """

    def test_the_same_listing_twice_raises_rather_than_returning_the_first(self, service):
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget',
            order_date=datetime(2026, 1, 14),
        )
        with pytest.raises(CaptureDecisionRequired) as excinfo:
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget',
                order_date=datetime(2026, 1, 14),
            )
        assert excinfo.value.assessment.duplicate_purchase_id == first.id
        assert excinfo.value.assessment.has_duplicate is True

    def test_a_refused_capture_writes_nothing_at_all(self, service):
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget',
            order_date=datetime(2026, 1, 14),
        )
        product_id = service.list_products()[0].id
        with pytest.raises(CaptureDecisionRequired):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Blue Widget',
                order_date=datetime(2026, 1, 14),
            )
        assert len(service.list_products()) == 1
        assert len(service.get_purchase_history(product_id)) == 1

    def test_acknowledging_it_records_a_second_purchase(self, service):
        """FR-015: two orders of the same thing on one day are two orders.

        Both questions have to be answered, because the first capture is what
        gave the item id a product to name -- so the repeat is a probable
        duplicate *and* an uncorroborated match. They are asked together.
        """
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        second = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
            acknowledged_duplicate_of=first.id, attach_to=first.product_id,
        )
        assert second.id != first.id
        assert second.product_id == first.product_id
        assert len(service.list_products()) == 1

    def test_both_questions_are_asked_at_once(self, service):
        """One round trip, not two: the assessment carries both halves"""
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        with pytest.raises(CaptureDecisionRequired) as excinfo:
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH',
                order_date=datetime(2026, 1, 14),
            )

        assessment = excinfo.value.assessment
        assert assessment.has_duplicate is True
        assert assessment.has_uncorroborated_match is True
        assert assessment.duplicate_purchase_id == first.id
        assert assessment.matched_product_id == first.product_id

    def test_a_stale_acknowledgement_raises_again(self, service):
        """An answer to a question about a different row is not an answer"""
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        with pytest.raises(CaptureDecisionRequired) as excinfo:
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
                acknowledged_duplicate_of=first.id + 999,
            )
        assert excinfo.value.assessment.duplicate_purchase_id == first.id

    def test_the_same_item_on_a_different_day_is_a_different_purchase(self, service):
        """Buying the same thing again in March is a second purchase"""
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        second = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 3, 2),
            manufacturer=None, manufacturer_part_number=None,
            attach_to=first.product_id,
        )
        assert second.id != first.id
        assert second.product_id == first.product_id

    def test_the_same_item_id_from_a_different_vendor_is_not_a_duplicate(self, service):
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        second = service.capture_order(
            vendor='eBay', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        assert second.id != first.id
        assert second.product_id != first.product_id

    def test_the_time_of_day_does_not_matter(self, service):
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            order_date=datetime(2026, 1, 14, 9, 15),
        )
        with pytest.raises(CaptureDecisionRequired):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH',
                order_date=datetime(2026, 1, 14, 17, 40),
            )

    def test_a_listing_with_no_item_id_is_matched_on_its_address(self, service):
        """FR-013: most vendors' URLs yield no identifier at all"""
        first = service.capture_order(
            vendor='McMaster-Carr', url=MCMASTER_URL, order_date=datetime(2026, 1, 14),
        )
        with pytest.raises(CaptureDecisionRequired) as excinfo:
            service.capture_order(
                vendor='McMaster-Carr', url=MCMASTER_URL, order_date=datetime(2026, 1, 14),
            )
        assert excinfo.value.assessment.duplicate_purchase_id == first.id

    def test_a_different_address_on_the_same_day_is_not_a_duplicate(self, service):
        service.capture_order(
            vendor='McMaster-Carr', url=MCMASTER_URL, order_date=datetime(2026, 1, 14),
        )
        second = service.capture_order(
            vendor='McMaster-Carr', url='https://www.mcmaster.com/90128A105/',
            order_date=datetime(2026, 1, 14),
        )
        assert second.id is not None
        assert len(service.list_products()) == 2

    def test_with_neither_an_id_nor_an_address_nothing_is_recognized(self, service):
        service.capture_order(vendor='A Shop', order_date=datetime(2026, 1, 14))
        second = service.capture_order(vendor='A Shop', order_date=datetime(2026, 1, 14))
        assert second.id is not None
        assert len(service.list_products()) == 2


class TestAttachVsCreate:
    """FR-017 to FR-021: a recycled item number is a question, not an assumption"""

    def test_an_uncorroborated_match_raises_and_names_the_product(self, service):
        existing = service.create_product(
            description='Blue widget, already cataloged',
            manufacturer_part_number='BW-10',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        with pytest.raises(CaptureDecisionRequired) as excinfo:
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH',
                listing_title='Something else entirely',
            )

        assessment = excinfo.value.assessment
        assert assessment.matched_product_id == existing.id
        assert assessment.matched_product_description == 'Blue widget, already cataloged'
        assert assessment.matched_product_part_number == 'BW-10'
        assert assessment.has_uncorroborated_match is True
        # Nothing written while the question is open.
        assert len(service.list_products()) == 1

    def test_choosing_the_matched_product_attaches_to_it(self, service):
        existing = service.create_product(
            description='Blue widget, already cataloged',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', attach_to=existing.id,
        )
        assert purchase.product_id == existing.id
        assert len(service.list_products()) == 1

    def test_choosing_a_separate_product_leaves_the_first_untouched(self, service):
        """FR-020, including its identifiers"""
        existing = service.create_product(
            description='Blue widget, already cataloged',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='A completely different thing', attach_to='new',
        )

        assert purchase.product_id != existing.id
        assert len(service.list_products()) == 2

        untouched = service.get_product(existing.id)
        assert untouched.description == 'Blue widget, already cataloged'
        assert [i.value for i in untouched.identifiers if i.id_type == 'VENDOR'] == [
            'B0ABCDEFGH'
        ]
        assert service.get_purchase_history(existing.id) == []
        # The purchase still records the item id even though it could not claim
        # the identifier, which is scoped to one product per vendor.
        assert purchase.vendor_item_id == 'B0ABCDEFGH'

    def test_attaching_to_a_product_that_has_since_gone_creates_one(self, service):
        """The spec's edge case: better than failing on a page nobody can fix"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', description='Blue widget',
            attach_to=99999,
        )
        assert purchase.product_id is not None
        assert service.get_product(purchase.product_id).description == 'Blue widget'

    def test_a_different_identifier_creates_a_second_product(self, service):
        service.capture_order(vendor='Amazon', vendor_item_id='B0ABCDEFGH')
        service.capture_order(vendor='Amazon', vendor_item_id='B0ZZZZZZZZ')
        assert len(service.list_products()) == 2

    def test_no_identifier_at_all_creates_without_asking(self, service):
        """FR-021: nothing to match on, so nothing to ask about"""
        purchase = service.capture_order(vendor='A Shop', description='A thing')
        assert purchase.product_id is not None

    def test_attaching_does_not_let_the_vendors_title_overwrite_a_description(self, service):
        """The vendor's wording never replaces the operator's.

        This is what the old ``test_attaching_does_not_overwrite_the_operators_own
        _description`` was protecting, and it is still true. What has changed is
        that the *operator's* own description now may replace it (FR-005) -- see
        ``TestDescriptionAtCapture``.
        """
        existing = service.create_product(
            description='Blue widget, 10mm, the good ones',
            manufacturer='Acme', manufacturer_part_number='BW-10',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Acme', manufacturer_part_number='BW-10',
            listing_title='BLUE WIDGET 10 PACK BEST QUALITY ✨',
        )
        assert service.get_product(existing.id).description == 'Blue widget, 10mm, the good ones'


class TestCorroboration:
    """FR-019: attach without asking only when the evidence is a pair"""

    @pytest.fixture
    def cataloged(self, service):
        return service.create_product(
            description='12V 3A PSU',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )

    def test_both_matching_attaches_silently(self, service, cataloged):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
        )
        assert purchase.product_id == cataloged.id

    def test_case_and_padding_do_not_defeat_it(self, service, cataloged):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='  mean well ', manufacturer_part_number='rs-15-12',
        )
        assert purchase.product_id == cataloged.id

    def test_the_manufacturer_alone_is_not_evidence(self, service, cataloged):
        """One name matches a vendor's whole catalog"""
        with pytest.raises(CaptureDecisionRequired):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH', manufacturer='Mean Well',
            )

    def test_the_part_number_alone_is_not_evidence(self, service, cataloged):
        with pytest.raises(CaptureDecisionRequired):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH',
                manufacturer_part_number='RS-15-12',
            )

    def test_a_disagreeing_part_number_asks(self, service, cataloged):
        """The recycled-identifier case the whole story exists for"""
        with pytest.raises(CaptureDecisionRequired):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH',
                manufacturer='Mean Well', manufacturer_part_number='LRS-50-24',
            )

    def test_a_product_with_no_manufacturer_never_corroborates(self, service):
        service.create_product(
            description='Blue widget',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ZZZZZZZZ', 'vendor': 'Amazon'}],
        )
        with pytest.raises(CaptureDecisionRequired):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ZZZZZZZZ',
                manufacturer='Acme', manufacturer_part_number='X-1',
            )


class TestAmendmentAtReceipt:
    """What arrives is allowed to differ from what was ordered"""

    def test_receiving_sets_the_received_date(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', quantity=10,
        )
        received = service.receive_purchase(captured.id)

        assert received.received_date is not None
        assert received.is_outstanding is False

    def test_quantity_can_be_amended_at_receipt(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', quantity=10,
        )
        received = service.receive_purchase(captured.id, quantity=8)
        assert received.quantity == 8

    def test_price_can_be_amended_at_receipt(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', unit_price='12.34',
        )
        received = service.receive_purchase(captured.id, unit_price='11.00')
        assert received.unit_price == Decimal('11.00')

    def test_receiving_an_already_received_purchase_is_a_no_op(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 1, 14),
        )
        first = service.receive_purchase(captured.id, received_date=datetime(2026, 2, 1))
        second = service.receive_purchase(captured.id, received_date=datetime(2026, 3, 1))

        assert second.received_date == first.received_date

    def test_receiving_before_the_order_date_is_refused(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=datetime(2026, 3, 1),
        )
        with pytest.raises(ValidationError):
            service.receive_purchase(captured.id, received_date=datetime(2026, 1, 1))

    def test_the_description_is_applied_in_the_same_call(self, service):
        """FR-023: one submission corrects it and marks the purchase received"""
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', description='Blue widget',
        )
        received = service.receive_purchase(
            captured.id, description='Blue widget, 10mm, matte'
        )

        assert received.received_date is not None
        assert service.get_product(captured.product_id).description == (
            'Blue widget, 10mm, matte'
        )

    def test_a_blank_description_refuses_the_whole_submission(self, service):
        """FR-024: neither the description nor the received state changes"""
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', description='Blue widget',
        )
        with pytest.raises(ValidationError) as excinfo:
            service.receive_purchase(captured.id, description='   ')

        assert excinfo.value.field == 'description'
        assert service.get_product(captured.product_id).description == 'Blue widget'
        assert service.get_purchase(captured.id).is_outstanding is True

    def test_an_over_long_description_is_refused_at_receipt_too(self, service):
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', description='Blue widget',
        )
        with pytest.raises(ValidationError):
            service.receive_purchase(captured.id, description='x' * 300)
        assert service.get_purchase(captured.id).is_outstanding is True

    def test_omitting_the_description_leaves_it_alone(self, service):
        """FR-026"""
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', description='Blue widget',
        )
        service.receive_purchase(captured.id, quantity=3)
        assert service.get_product(captured.product_id).description == 'Blue widget'

    def test_the_description_is_correctable_after_receipt(self, service):
        """FR-025: the received date is a no-op the second time; this is not.

        Fails if the assignment is placed inside the ``already_received`` guard,
        which is the one thing in this feature easiest to put in the wrong place.
        """
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', description='Blue widget',
            order_date=datetime(2026, 1, 14),
        )
        first = service.receive_purchase(captured.id, received_date=datetime(2026, 2, 1))
        second = service.receive_purchase(
            captured.id, received_date=datetime(2026, 3, 1),
            description='Blue widget, actually 12mm',
        )

        assert second.received_date == first.received_date
        assert service.get_product(captured.product_id).description == (
            'Blue widget, actually 12mm'
        )

    def test_a_hand_recorded_purchase_behaves_the_same(self, service):
        """FR-025: not only captured purchases have a receive screen"""
        product = service.create_product(description='Bought at the counter')
        purchase = service.record_purchase(product.id, vendor='Local shop')

        service.receive_purchase(purchase.id, description='Bought at the counter, 3-pack')
        assert service.get_product(product.id).description == 'Bought at the counter, 3-pack'

    def test_the_captured_details_are_already_there_at_receipt(self, service):
        """SC-002: nothing the listing yielded has to be retyped"""
        captured = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='Blue Widget 10-Pack', order_date=datetime(2026, 1, 14),
            unit_price='12.34', quantity=10,
        )
        assert captured.vendor == 'Amazon'
        assert captured.vendor_item_id == 'B0ABCDEFGH'
        assert captured.listing_title == 'Blue Widget 10-Pack'
        assert captured.order_date == datetime(2026, 1, 14)
        assert captured.unit_price == Decimal('12.34')
        assert captured.quantity == 10


class TestTheBookmarkletLanding:
    """FR-008, FR-009: a form POST from a vendor's origin writes nothing"""

    def test_it_renders_the_capture_form_rather_than_filing_a_purchase(self, client):
        response = client.post('/api/capture', data={
            'url': AMAZON_URL,
            'listing_title': 'Blue Widget 10-Pack',
        })

        assert response.status_code == 200
        assert b'id="capture-form"' in response.data
        assert b'id="description"' in response.data

    def test_it_writes_nothing(self, client, service):
        """The assertion a status-only test would miss"""
        client.post('/api/capture', data={
            'url': AMAZON_URL,
            'listing_title': 'Blue Widget 10-Pack',
        })
        assert service.list_products() == []

    def test_what_the_url_yielded_is_already_filled_in(self, client):
        response = client.post('/api/capture', data={'url': AMAZON_URL})
        body = response.data.decode()

        assert 'value="Amazon"' in body
        assert 'value="B0ABCDEFGH"' in body

    def test_the_json_representation_still_writes(self, client, service):
        response = client.post('/api/capture', json={
            'url': AMAZON_URL,
            'listing_title': 'Blue Widget',
            'description': 'Blue widget, 10mm',
        })

        assert response.status_code == 201
        assert len(service.list_products()) == 1
        assert service.list_products()[0].description == 'Blue widget, 10mm'

    def test_the_json_representation_answers_409_when_it_needs_a_decision(
        self, client, service
    ):
        service.create_product(
            description='Blue widget, already cataloged',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        response = client.post('/api/capture', json={'url': AMAZON_URL})

        assert response.status_code == 409
        assessment = response.get_json()['assessment']
        assert assessment['has_uncorroborated_match'] is True
        assert assessment['matched_product_description'] == 'Blue widget, already cataloged'
        assert len(service.list_products()) == 1

    def test_re_posting_with_the_answer_resolves_it(self, client, service):
        service.create_product(
            description='Blue widget, already cataloged',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        response = client.post('/api/capture', json={
            'url': AMAZON_URL, 'attach_to': 'new',
        })

        assert response.status_code == 201
        assert len(service.list_products()) == 2


class TestTheReceiveForm:
    """What the description field shows when a submission comes back"""

    @pytest.fixture
    def purchase(self, service):
        product = service.create_product(description='Blue widget')
        return service.record_purchase(product.id, vendor='Amazon')

    def description_input(self, response):
        match = re.search(r'<input[^>]*id="description"[^>]*>', response.data.decode(), re.S)
        assert match, "the receive form has no description input"
        return match.group(0)

    def test_it_is_prefilled_from_the_product(self, client, purchase):
        response = client.get(f'/purchases/{purchase.id}/receive')

        assert response.status_code == 200
        assert 'value="Blue widget"' in self.description_input(response)

    def test_a_refused_blank_comes_back_blank(self, client, purchase):
        """The message says a description is required; the field must agree.

        Re-filling it from the product would put text next to an error
        complaining that there is none, and would hide what was submitted.
        """
        response = client.post(f'/purchases/{purchase.id}/receive', data={'description': ''})

        assert response.status_code == 200
        assert 'value=""' in self.description_input(response)

    def test_a_refused_over_long_description_is_not_thrown_away(self, client, purchase):
        typed = 'x' * 300
        response = client.post(
            f'/purchases/{purchase.id}/receive', data={'description': typed}
        )

        assert response.status_code == 200
        assert typed in self.description_input(response)


class TestUrlParsing:
    """Reading the URL, never the page's markup"""

    def test_amazon_asin_and_vendor_come_out_of_the_url(self, client):
        from app.product.routes import _asin_from_url, _vendor_from_url

        assert _asin_from_url(AMAZON_URL) == 'B0ABCDEFGH'
        assert _vendor_from_url(AMAZON_URL) == 'Amazon'

    def test_the_gp_product_form_works_too(self, client):
        from app.product.routes import _asin_from_url

        assert _asin_from_url(
            'https://www.amazon.com/gp/product/B0ABCDEFGH?psc=1'
        ) == 'B0ABCDEFGH'

    def test_an_unknown_vendor_falls_back_to_its_host(self, client):
        from app.product.routes import _vendor_from_url

        assert _vendor_from_url('https://www.example-parts.co.uk/thing') == 'example-parts.co.uk'

    def test_a_url_with_no_asin_yields_nothing_rather_than_a_guess(self, client):
        from app.product.routes import _asin_from_url

        assert _asin_from_url('https://www.digikey.com/en/products/detail/x/y/123') == ''

    def test_a_blank_url_is_not_an_error(self, client):
        from app.product.routes import _asin_from_url, _vendor_from_url

        assert _asin_from_url('') == ''
        assert _vendor_from_url('') == ''


class TestTheListingPayload:
    """The one contract that crosses a machine boundary.

    ``capture-agent.js`` writes this JSON inside a vendor's page and
    ``ListingCapture.from_json`` reads it here. Everything it refuses, it refuses
    by returning None -- because the commonest reason for a missing payload is
    that the operator used the paste-a-URL form, which has no agent at all, and
    FR-007 requires that path to behave exactly as it did before this feature.
    """

    def payload(self, **fields):
        body = {'version': 1, 'source_url': AMAZON_URL}
        body.update(fields)
        return json.dumps(body)

    @pytest.mark.parametrize('raw', [
        None,
        '',
        'not json',
        '[]',
        '"a string"',
        '17',
    ])
    def test_an_unusable_payload_yields_none_rather_than_raising(self, raw):
        assert ListingCapture.from_json(raw) is None

    def test_a_payload_from_a_stale_agent_yields_none(self):
        """The cache-buster makes this near-impossible; `version` makes it harmless"""
        assert ListingCapture.from_json(
            json.dumps({'version': 2, 'source_url': AMAZON_URL, 'price': '1.00'})
        ) is None

    def test_a_payload_with_no_source_url_yields_none(self):
        assert ListingCapture.from_json(json.dumps({'version': 1})) is None

    def test_a_well_formed_payload_parses(self):
        listing = ListingCapture.from_json(self.payload(
            vendor_item_id='B0ABCDEFGH',
            listing_title='Blue Widget 10-Pack',
            price='24.99',
            brand='Acme Components',
            description_text='A description.',
        ))

        assert listing.source_url == AMAZON_URL
        assert listing.vendor_item_id == 'B0ABCDEFGH'
        assert listing.listing_title == 'Blue Widget 10-Pack'
        assert listing.price == '24.99'
        assert listing.brand == 'Acme Components'
        assert listing.description_text == 'A description.'

    def test_a_malformed_specification_costs_one_row_and_not_the_rest(self):
        listing = ListingCapture.from_json(self.payload(specifications=[
            {'name': 'Material', 'value': '6061 Aluminium'},
            'not a pair',
            {'name': 'Voltage'},
            {'value': 'orphaned'},
            {'name': 'Item Length', 'value': '300 Millimeters'},
        ]))

        assert listing.specifications == [
            {'name': 'Material', 'value': '6061 Aluminium'},
            {'name': 'Item Length', 'value': '300 Millimeters'},
        ]

    def test_an_address_that_is_not_http_is_dropped_and_its_siblings_kept(self):
        listing = ListingCapture.from_json(self.payload(images=[
            'https://m.media-amazon.com/images/I/71one.jpg',
            'javascript:alert(1)',
            'data:image/png;base64,AAAA',
            17,
            'http://m.media-amazon.com/images/I/81two.jpg',
        ]))

        assert listing.images == [
            'https://m.media-amazon.com/images/I/71one.jpg',
            'http://m.media-amazon.com/images/I/81two.jpg',
        ]

    def test_a_price_sent_as_a_json_number_is_refused_rather_than_coerced(self):
        """Constitution III: a float that reached str() would still have been a float"""
        listing = ListingCapture.from_json(self.payload(price=24.99))

        assert listing.price is None

    def test_the_form_representation_echoes_the_payload_back(self, client):
        """FR-016's first half: the field arrives and is re-emitted, unparsed"""
        raw = self.payload(price='24.99', brand='Acme Components')
        response = client.post('/api/capture', data={
            'url': AMAZON_URL,
            'listing_title': 'Blue Widget 10-Pack',
            'listing': raw,
        })

        assert response.status_code == 200
        body = response.data.decode()
        assert 'name="listing"' in body
        assert escape(raw) in body

    def test_a_payload_arriving_still_writes_nothing(self, client, service):
        """FR-014: until the operator submits, a capture is a form"""
        client.post('/api/capture', data={
            'url': AMAZON_URL,
            'listing': self.payload(
                specifications=[{'name': 'Material', 'value': '6061 Aluminium'}],
                images=['https://m.media-amazon.com/images/I/71one.jpg'],
            ),
        })

        assert service.list_products() == []


class TestTheListingFillsTheForm:
    """US1: the price and the brand arrive without the operator typing them.

    The rule is one-directional and it is the whole story of this class: the
    listing fills blanks, and a value the operator typed always wins. They were
    looking at the thing; a selector was not.
    """

    def payload(self, **fields):
        body = {'version': 1, 'source_url': AMAZON_URL}
        body.update(fields)
        return json.dumps(body)

    def capture(self, client, **form):
        data = {'url': AMAZON_URL, 'listing_title': 'Blue Widget 10-Pack'}
        data.update(form)
        return client.post('/products/capture', data=data, follow_redirects=False)

    def only_purchase(self, service):
        products = service.list_products()
        assert len(products) == 1
        history = service.get_purchase_history(products[0].id)
        assert len(history) == 1
        return products[0], history[0]

    def test_the_price_and_brand_come_off_the_listing(self, client, service):
        self.capture(client, listing=self.payload(price='24.99', brand='Acme Components'))

        product, purchase = self.only_purchase(service)
        assert purchase.unit_price == Decimal('24.99')
        assert product.manufacturer == 'Acme Components'

    def test_the_price_is_a_decimal_and_never_a_float(self, client, service):
        """Constitution III, across the JSON boundary as well as at the form"""
        self.capture(client, listing=self.payload(price='24.99'))

        _, purchase = self.only_purchase(service)
        assert isinstance(purchase.unit_price, Decimal)
        assert purchase.unit_price == Decimal('24.99')

    def test_what_the_operator_typed_wins(self, client, service):
        """US1 scenario 3"""
        self.capture(
            client,
            manufacturer='What I know it is',
            unit_price='19.95',
            listing=self.payload(price='24.99', brand='Acme Components'),
        )

        product, purchase = self.only_purchase(service)
        assert purchase.unit_price == Decimal('19.95')
        assert product.manufacturer == 'What I know it is'

    def test_a_price_sent_as_a_json_number_never_reaches_storage(self, client, service):
        """A float in the payload is dropped, not rounded into a Decimal"""
        self.capture(client, listing=self.payload(price=24.99, brand='Acme Components'))

        product, purchase = self.only_purchase(service)
        assert purchase.unit_price is None
        # The rest of the payload is unaffected: one bad field costs one field.
        assert product.manufacturer == 'Acme Components'

    def test_a_cleared_field_stays_cleared(self, client, service):
        """US1 scenario 3 again, in the direction that is easy to get wrong.

        The form pre-fills both of these from the payload, so a field arriving
        empty is one the operator deliberately cleared. Putting the extracted
        value back would leave no way to say "the listing is wrong about this".
        """
        self.capture(
            client,
            manufacturer='',
            unit_price='',
            listing=self.payload(price='24.99', brand='Acme Components'),
        )

        product, purchase = self.only_purchase(service)
        assert purchase.unit_price is None
        assert product.manufacturer is None

    def test_a_capture_with_no_payload_behaves_exactly_as_it_did(self, client, service):
        """FR-007, asserted against the pre-existing expectations rather than a new baseline"""
        response = self.capture(client)

        assert response.status_code == 302
        product, purchase = self.only_purchase(service)
        assert product.description == 'Blue Widget 10-Pack'
        assert purchase.vendor == 'Amazon'
        assert purchase.vendor_item_id == 'B0ABCDEFGH'
        assert purchase.listing_title == 'Blue Widget 10-Pack'
        assert purchase.unit_price is None
        assert purchase.received_date is None

    def test_an_unreadable_payload_behaves_the_same_way(self, client, service):
        response = self.capture(client, listing='{not json at all')

        assert response.status_code == 302
        product, purchase = self.only_purchase(service)
        assert product.description == 'Blue Widget 10-Pack'
        assert purchase.unit_price is None

    def test_the_landing_page_shows_the_price_and_brand_it_found(self, client):
        """US1 scenarios 1 and 2: pre-filled, so the operator sees it before confirming"""
        response = client.post('/api/capture', data={
            'url': AMAZON_URL,
            'listing': self.payload(price='24.99', brand='Acme Components'),
        })
        body = response.data.decode()

        assert re.search(r'<input[^>]*id="unit_price"[^>]*value="24\.99"', body)
        assert re.search(r'<input[^>]*id="manufacturer"[^>]*value="Acme Components"', body)

    def test_the_landing_page_is_unchanged_without_a_payload(self, client):
        """FR-007: the paste-a-URL path has no agent and must look exactly as it did"""
        response = client.post('/api/capture', data={'url': AMAZON_URL})
        body = response.data.decode()

        assert re.search(r'<input[^>]*id="unit_price"[^>]*value=""', body)
        assert re.search(r'<input[^>]*id="manufacturer"[^>]*value=""', body)


class TestCapturedSpecifications:
    """US3: the listing's product information becomes filterable catalog data.

    The invariant under all of it is FR-011, and it is a property of
    ``merge_specifications`` rather than of its callers: **a capture never
    removes anything**. ``update_product`` still replaces, because the form posts
    a complete set and a capture does not.
    """

    def listing(self, rows, **fields):
        return ListingCapture(
            source_url=AMAZON_URL,
            specifications=[{'name': n, 'value': v} for n, v in rows],
            **fields,
        )

    def specs(self, service, product_id):
        product = service.get_product(product_id)
        return [(row.name, row.value) for row in product.specifications]

    def test_rows_land_as_specifications_in_order(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=self.listing([
                ('Material', '6061 Aluminium'),
                ('Item Length', '300 Millimeters'),
                ('Voltage', '12 Volts'),
            ]),
        )

        assert self.specs(service, purchase.product_id) == [
            ('Material', '6061 Aluminium'),
            ('Item Length', '300 Millimeters'),
            ('Voltage', '12 Volts'),
        ]

    def test_an_existing_value_is_never_overwritten(self, service):
        """FR-010: the operator looked at the thing, a selector did not"""
        product = service.create_product(
            description='12V PSU',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            specifications=[{'name': 'Material', 'value': 'What I measured'}],
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )

        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            listing=self.listing([
                ('Material', '6061 Aluminium'),
                ('Voltage', '12 Volts'),
            ]),
        )

        assert self.specs(service, product.id) == [
            ('Material', 'What I measured'),
            ('Voltage', '12 Volts'),
        ]

    def test_nothing_is_ever_removed(self, service):
        """FR-011, stated as its own test because it is the whole invariant"""
        product = service.create_product(
            description='12V PSU',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            specifications=[
                {'name': 'Where I put it', 'value': 'Third drawer'},
                {'name': 'Why I bought it', 'value': 'For the mill'},
            ],
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )

        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            listing=self.listing([('Voltage', '12 Volts')]),
        )

        stored = self.specs(service, product.id)
        assert ('Where I put it', 'Third drawer') in stored
        assert ('Why I bought it', 'For the mill') in stored
        assert len(stored) == 3

    def test_existing_rows_do_not_move(self, service):
        product = service.create_product(
            description='12V PSU',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            specifications=[{'name': 'Mine', 'value': 'First'}],
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )

        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            listing=self.listing([('Voltage', '12 Volts')]),
        )

        assert self.specs(service, product.id)[0] == ('Mine', 'First')

    def test_an_over_long_name_costs_one_row_and_not_the_batch(self, service):
        """FR-008 scenario 8: a capture is all-or-nothing about nothing"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=self.listing([
                ('Material', '6061 Aluminium'),
                ('x' * 101, 'refused'),
                ('Voltage', '12 Volts'),
            ]),
        )

        assert self.specs(service, purchase.product_id) == [
            ('Material', '6061 Aluminium'),
            ('Voltage', '12 Volts'),
        ]

    def test_names_differing_only_in_case_or_space_collapse_to_one(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=self.listing([
                ('Material', '6061 Aluminium'),
                ('  material ', 'Steel'),
                ('MATERIAL', 'Brass'),
            ]),
        )

        assert self.specs(service, purchase.product_id) == [('Material', '6061 Aluminium')]

    def test_a_bookkeeping_row_is_stored_rather_than_filtered(self, service):
        """FR-008: an unwanted row is deletable, a lost physical fact is not"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=self.listing([
                ('Best Sellers Rank', '#4,812 in Tools'),
                ('Customer Reviews', '4.5 out of 5 stars'),
                ('Date First Available', 'March 14, 2023'),
            ]),
        )

        stored = dict(self.specs(service, purchase.product_id))
        assert stored['Best Sellers Rank'] == '#4,812 in Tools'
        assert stored['Customer Reviews'] == '4.5 out of 5 stars'
        assert stored['Date First Available'] == 'March 14, 2023'

    def test_recapturing_an_unchanged_listing_adds_nothing_the_second_time(self, service):
        rows = self.listing([('Material', '6061 Aluminium'), ('Voltage', '12 Volts')])
        first = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=rows,
        )
        # Both questions answered: it is the same product, and it is a second
        # order of it. Answering them is exactly what US5 is about.
        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            acknowledged_duplicate_of=first.id, attach_to=first.product_id,
            listing=rows,
        )

        assert len(self.specs(service, first.product_id)) == 2

    def test_a_capture_with_no_listing_writes_no_specifications(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
        )

        assert self.specs(service, purchase.product_id) == []

    def test_merge_specifications_refuses_a_product_that_is_not_there(self, service):
        from app.exceptions import ItemNotFoundError

        with pytest.raises(ItemNotFoundError):
            service.merge_specifications(9999, [{'name': 'Voltage', 'value': '12 V'}])

    def test_it_returns_the_rows_it_added(self, service):
        """016 FR-003 rides on this: the caller has to know *which* rows landed"""
        product = service.create_product(
            description='12V PSU',
            specifications=[{'name': 'Material', 'value': 'What I measured'}],
        )

        added = service.merge_specifications(product.id, [
            {'name': 'Material', 'value': '6061 Aluminium'},
            {'name': 'Voltage', 'value': '12 Volts'},
        ])

        assert added == [{'name': 'Voltage', 'value': '12 Volts'}]

    def test_update_product_still_replaces(self, service):
        """The two are not variants of each other, and this is the guard on that"""
        product = service.create_product(
            description='12V PSU',
            specifications=[{'name': 'Material', 'value': 'Steel'}],
        )

        service.update_product(product.id, specifications=[
            {'name': 'Voltage', 'value': '12 Volts'},
        ])

        assert self.specs(service, product.id) == [('Voltage', '12 Volts')]


class TestTheFoldHappensInPython:
    """The test that fails if the name comparison ever migrates into SQL.

    The deployed collation is accent-insensitive as well as case-insensitive, so
    a comparison performed in SQL would call ``Volt`` and ``Vôlt`` one name on
    MariaDB while SQLite -- collating BINARY -- calls them two. A rule that means
    two different things on two backends is the failure this guards.

    It passes under SQLite for the same reason it passes under MariaDB *only*
    when the comparison is Python-side, which is what makes it a real guard
    rather than an accident of the backend the unit suite happens to use.
    """

    def test_volt_and_vôlt_remain_two_specifications(self, service):
        product = service.create_product(
            description='12V PSU',
            specifications=[{'name': 'Volt', 'value': 'twelve'}],
        )

        added = service.merge_specifications(product.id, [
            {'name': 'Vôlt', 'value': 'douze'},
        ])

        assert len(added) == 1
        names = [row.name for row in service.get_product(product.id).specifications]
        assert names == ['Volt', 'Vôlt']


class TestCapturedDescription:
    """US4: what the listing was sold on is kept with the product.

    It goes into a ``Description`` specification row rather than into
    ``products.description``, which is the operator's label wording and is capped
    at 255 characters. Two different facts, and the whole point of FR-006 is that
    keeping one must not displace the other.
    """

    def listing(self, text, **fields):
        return ListingCapture(source_url=AMAZON_URL, description_text=text, **fields)

    def specs(self, service, product_id):
        return {
            row.name: row.value
            for row in service.get_product(product_id).specifications
        }

    def test_a_plain_description_lands_as_a_specification(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=self.listing('This power supply provides a regulated 12 volts.'),
        )

        assert self.specs(service, purchase.product_id)['Description'] == (
            'This power supply provides a regulated 12 volts.'
        )

    def test_a_rich_description_lands_the_same_way(self, service):
        """The two forms are the same fact and the server cannot tell them apart"""
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='Extrusion',
            listing=self.listing('Built for the workshop. Extruded 6063-T5 aluminium.'),
        )

        assert 'Description' in self.specs(service, purchase.product_id)

    def test_no_description_records_nothing_and_is_not_refused(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=ListingCapture(source_url=AMAZON_URL),
        )

        assert 'Description' not in self.specs(service, purchase.product_id)

    def test_a_long_description_is_kept_whole(self, service):
        """FR-006. Under SQLite this proves the code does not truncate; the
        column's own limit is a MariaDB limit and b1a0c0d10009 is what lifts it."""
        long_text = 'The listing said: ' + ('x' * 40000)
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=self.listing(long_text),
        )

        assert self.specs(service, purchase.product_id)['Description'] == long_text

    def test_it_does_not_displace_the_operators_label_wording(self, service):
        """FR-006's second half, and the reason it is a row and not the field"""
        long_text = 'y' * 40000
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='BLUE WIDGET 10 PACK FREE SHIPPING',
            description='12V 3A PSU, barrel plug',
            listing=self.listing(long_text),
        )

        product = service.get_product(purchase.product_id)
        assert product.description == '12V 3A PSU, barrel plug'
        assert self.specs(service, purchase.product_id)['Description'] == long_text

    def test_a_product_that_already_has_a_description_row_keeps_it(self, service):
        """The same "already present wins" rule as every other captured row"""
        product = service.create_product(
            description='12V PSU',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            specifications=[{'name': 'Description', 'value': 'What I wrote last time'}],
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )

        service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            listing=self.listing('The vendor wording, which arrived second'),
        )

        assert self.specs(service, product.id)['Description'] == 'What I wrote last time'

    def test_the_description_follows_the_rows_rather_than_leading_them(self, service):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH', listing_title='12V PSU',
            listing=ListingCapture(
                source_url=AMAZON_URL,
                description_text='A description.',
                specifications=[{'name': 'Voltage', 'value': '12 Volts'}],
            ),
        )

        names = [row.name for row in service.get_product(purchase.product_id).specifications]
        assert names == ['Voltage', 'Description']


class TestThePayloadSurvivesAQuestion:
    """US5 / FR-016.

    The round trip already works, because the payload rides a hidden field the
    template re-emits from ``form_data`` alongside every other value. These tests
    are what make that a *tested property* rather than a happy accident: the
    failure mode being guarded against is a later change to capture.html quietly
    dropping that field, which nothing else in the suite would notice until a
    real capture lost a gallery.
    """

    def payload(self, **fields):
        body = {
            'version': 1,
            'source_url': AMAZON_URL,
            'specifications': [{'name': 'Voltage', 'value': '12 Volts'}],
            'description_text': 'A description.',
        }
        body.update(fields)
        return json.dumps(body)

    def post(self, client, **form):
        data = {'url': AMAZON_URL, 'listing_title': '12V PSU'}
        data.update(form)
        return client.post('/products/capture', data=data)

    def specs(self, service, product_id):
        return {
            row.name: row.value
            for row in service.get_product(product_id).specifications
        }

    @pytest.fixture
    def already_named(self, service):
        """A product the item id already names, without corroboration"""
        return service.create_product(
            description='Something already cataloged',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )

    def test_the_question_comes_back_with_the_payload_still_attached(
        self, client, service, already_named
    ):
        raw = self.payload()
        response = self.post(client, listing=raw)

        assert response.status_code == 200
        body = response.data.decode()
        assert 'id="identifier-warning"' in body
        assert escape(raw) in body

    def test_and_writes_nothing(self, client, service, already_named):
        """The question is raised before anything is written, payload or not"""
        self.post(client, listing=self.payload())

        assert len(service.list_products()) == 1
        assert self.specs(service, already_named.id) == {}

    def test_answering_writes_the_payload_once(self, client, service, already_named):
        self.post(client, listing=self.payload())
        self.post(client, listing=self.payload(), attach_to=str(already_named.id))

        stored = self.specs(service, already_named.id)
        assert stored['Voltage'] == '12 Volts'
        assert stored['Description'] == 'A description.'
        assert len(service.get_product(already_named.id).specifications) == 2

    def test_answering_a_second_time_does_not_write_it_twice(
        self, client, service, already_named
    ):
        """A re-capture merges rather than duplicating -- FR-010 doing US5's job"""
        first = self.post(client, listing=self.payload(), attach_to=str(already_named.id))
        assert first.status_code == 302

        purchase = service.get_purchase_history(already_named.id)[0]
        self.post(
            client, listing=self.payload(),
            attach_to=str(already_named.id),
            acknowledged_duplicate_of=str(purchase.id),
        )

        assert len(service.get_product(already_named.id).specifications) == 2
        assert len(service.get_purchase_history(already_named.id)) == 2

    def test_both_questions_at_once_land_the_payload_exactly_once(self, client, service):
        """A capture can be a probable repeat *and* land on a recycled identifier"""
        product = service.create_product(
            description='Something already cataloged',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        # Dated today, because "the same capture" means the same vendor, the
        # same item and the same *day*.
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        seed = service.record_purchase(
            product.id, vendor='Amazon', vendor_item_id='B0ABCDEFGH', order_date=today,
        )

        raw = self.payload()
        asked = self.post(client, listing=raw)
        assert asked.status_code == 200
        body = asked.data.decode()
        assert 'id="duplicate-warning"' in body
        assert 'id="identifier-warning"' in body
        assert escape(raw) in body

        answered = self.post(
            client, listing=raw,
            attach_to=str(product.id), acknowledged_duplicate_of=str(seed.id),
        )

        assert answered.status_code == 302
        assert len(service.get_product(product.id).specifications) == 2
        assert self.specs(service, product.id)['Voltage'] == '12 Volts'

    def test_the_re_rendered_form_still_shows_what_will_be_written(
        self, client, already_named
    ):
        """FR-017 has to survive the question too, or the operator confirms blind"""
        response = self.post(client, listing=self.payload(
            images=['https://m.media-amazon.com/images/I/71one.jpg'],
        ))

        body = response.data.decode()
        assert 'id="capture-summary"' in body
        assert 'id="summary-images"' in body

    def test_an_abandoned_capture_leaves_nothing(self, client, service):
        """FR-014, FR-015: an unconfirmed capture is a form, and nothing else"""
        client.post('/api/capture', data={
            'url': AMAZON_URL,
            'listing': self.payload(
                images=['https://m.media-amazon.com/images/I/71one.jpg'],
            ),
        })

        assert service.list_products() == []


# ---------------------------------------------------------------------------
# 016: a captured barcode becomes a scannable identifier
# ---------------------------------------------------------------------------

VALID_UPC_A = '012345678905'
VALID_EAN_13 = '0012345678905'      # the same trade item, one form up
VALID_GTIN_KEY = '00012345678905'   # what both of them are stored as
BAD_CHECK_DIGIT = '012345678906'
VALID_ISBN_13 = '9780306406157'
ISBN_13_KEY = '09780306406157'
ISBN_10 = '0306406152'              # a different arithmetic, and only ten digits


def barcode_listing(*rows, **fields):
    """A listing carrying (name, value) product-information rows"""
    return ListingCapture(
        source_url=AMAZON_URL,
        specifications=[{'name': name, 'value': value} for name, value in rows],
        **fields,
    )


def capture(service, listing, **fields):
    """Capture the listing, defaulting the fields this story does not care about"""
    fields.setdefault('vendor', 'Amazon')
    fields.setdefault('vendor_item_id', 'B0ABCDEFGH')
    fields.setdefault('order_date', datetime(2026, 1, 15))
    return service.capture_order(listing=listing, **fields)


def gtins(service, product_id):
    """The GTIN identifier values on a product"""
    return [
        row.value for row in service.get_product(product_id).identifiers
        if row.id_type == 'GTIN'
    ]


def spec_rows(service, product_id):
    return [
        (row.name, row.value)
        for row in service.get_product(product_id).specifications
    ]


class TestWhichRowNamesMeanABarcode:
    """FR-001: six names, folded -- and nothing else, however barcode-shaped"""

    @pytest.mark.parametrize('name', [
        'UPC', 'EAN', 'GTIN', 'ISBN', 'GTIN-13', 'UPC-A',
    ])
    def test_the_six_names_are_recognized(self, name):
        assert _is_barcode_row_name(name)

    @pytest.mark.parametrize('name', ['upc', '  UPC  ', 'Upc', 'gtin-13', 'uPc-A'])
    def test_case_and_surrounding_whitespace_are_folded(self, name):
        assert _is_barcode_row_name(name)

    @pytest.mark.parametrize('name', [
        'Manufacturer UPC', 'UPC Code', 'Item UPC', 'UPCs', 'EANx', 'Barcode',
    ])
    def test_the_whole_name_must_match_not_a_part_of_it(self, name):
        """A feature that promised six names should promote six names"""
        assert not _is_barcode_row_name(name)

    @pytest.mark.parametrize('name', [None, '', '   '])
    def test_a_missing_name_is_not_a_barcode_row(self, name):
        assert not _is_barcode_row_name(name)


class TestACapturedBarcodeBecomesAnIdentifier:
    """US1: the listing hands us the barcode, so the box scans (FR-002, FR-003)"""

    def test_a_captured_upc_becomes_a_gtin_identifier(self, service):
        purchase = capture(service, barcode_listing(('UPC', VALID_UPC_A)))

        assert gtins(service, purchase.product_id) == [VALID_GTIN_KEY]

    def test_the_row_is_still_a_specification_as_well(self, service):
        """FR-005: promotion adds, it never moves or filters"""
        purchase = capture(service, barcode_listing(
            ('UPC', VALID_UPC_A), ('Voltage', '12 Volts'),
        ))

        assert spec_rows(service, purchase.product_id) == [
            ('UPC', VALID_UPC_A),
            ('Voltage', '12 Volts'),
        ]

    @pytest.mark.parametrize('name', [
        'UPC', 'EAN', 'GTIN', 'ISBN', 'GTIN-13', 'UPC-A', 'upc', ' UPC ',
    ])
    def test_every_recognized_name_promotes_the_same_way(self, service, name):
        purchase = capture(service, barcode_listing((name, VALID_UPC_A)))

        assert gtins(service, purchase.product_id) == [VALID_GTIN_KEY]

    def test_a_name_that_is_not_recognized_promotes_nothing(self, service):
        purchase = capture(service, barcode_listing(('Manufacturer UPC', VALID_UPC_A)))

        assert gtins(service, purchase.product_id) == []

    def test_an_isbn_13_is_a_valid_barcode_and_promotes(self, service):
        purchase = capture(service, barcode_listing(('ISBN', VALID_ISBN_13)))

        assert gtins(service, purchase.product_id) == [ISBN_13_KEY]

    def test_equivalent_forms_are_one_identifier(self, service):
        """The 12-digit UPC and its 13-digit EAN form are one trade item"""
        listing = barcode_listing(('UPC', VALID_UPC_A), ('EAN', VALID_EAN_13))
        purchase = capture(service, listing)

        assert gtins(service, purchase.product_id) == [VALID_GTIN_KEY]

    def test_equivalent_forms_are_also_one_report_line(self, service):
        """FR-009: two lines for one barcode reads as two barcodes"""
        listing = barcode_listing(('UPC', VALID_UPC_A), ('EAN', VALID_EAN_13))
        purchase = capture(service, listing)

        notes = service.describe_captured_barcodes(purchase.product_id, listing)

        assert [(n.value, n.outcome) for n in notes] == [(VALID_GTIN_KEY, 'recorded')]

    def test_two_different_barcodes_both_promote(self, service):
        listing = barcode_listing(('UPC', VALID_UPC_A), ('ISBN', VALID_ISBN_13))
        purchase = capture(service, listing)

        assert sorted(gtins(service, purchase.product_id)) == [
            VALID_GTIN_KEY, ISBN_13_KEY,
        ]

    def test_capturing_the_same_listing_twice_leaves_one_identifier(self, service):
        """FR-007: the second capture is a no-op, not a duplicate and not an error"""
        listing = barcode_listing(('UPC', VALID_UPC_A))
        first = capture(service, listing)
        second = capture(service, listing, order_date=datetime(2026, 1, 16),
                         attach_to=str(first.product_id))

        assert second.product_id == first.product_id
        assert gtins(service, first.product_id) == [VALID_GTIN_KEY]

    def test_the_second_capture_still_reports_it_as_recorded(self, service):
        """FR-009a: the report states what is true, not what this capture did"""
        listing = barcode_listing(('UPC', VALID_UPC_A))
        first = capture(service, listing)
        capture(service, listing, order_date=datetime(2026, 1, 16),
                attach_to=str(first.product_id))

        notes = service.describe_captured_barcodes(first.product_id, listing)

        assert [n.outcome for n in notes] == ['recorded']

    def test_a_row_the_merge_dropped_is_not_promoted(self, service):
        """FR-003, and the rule that decides what re-capturing an old product does"""
        product = service.create_product(
            description='12V PSU',
            specifications=[{'name': 'UPC', 'value': VALID_UPC_A}],
        )

        capture(service, barcode_listing(('UPC', VALID_UPC_A)),
                attach_to=str(product.id))

        assert gtins(service, product.id) == []

    def test_that_row_is_reported_as_not_examined(self, service):
        """FR-010: otherwise the rule is silent exactly where it surprises"""
        product = service.create_product(
            description='12V PSU',
            # A value no product holds, so 'not examined' is the only reading.
            specifications=[{'name': 'UPC', 'value': VALID_UPC_A}],
        )
        listing = barcode_listing(('UPC', VALID_UPC_A))

        capture(service, listing, attach_to=str(product.id))
        notes = service.describe_captured_barcodes(product.id, listing)

        assert [(n.row_name, n.outcome) for n in notes] == [('UPC', 'not_examined')]

    def test_a_listing_with_no_barcode_row_reports_nothing(self, service):
        """FR-013: today's behaviour, byte for byte, and nothing said about it"""
        listing = barcode_listing(('Voltage', '12 Volts'), ('Wattage', '36 Watts'))
        purchase = capture(service, listing)

        assert gtins(service, purchase.product_id) == []
        assert service.describe_captured_barcodes(purchase.product_id, listing) == []


class TestAWrongBarcodeIsNeverRecorded:
    """US2: nobody typed this value, so nobody would see a prompt (FR-004)"""

    @pytest.mark.parametrize('value', [
        BAD_CHECK_DIGIT,        # one digit out
        '00000000000000',       # a wedge scanner's no-read
        '01234567890X',         # not all digits
        '0123456789',           # wrong length
        '',                     # nothing at all
        ISBN_10,                # ten digits and a different arithmetic
        f'{VALID_UPC_A} {VALID_EAN_13}',   # two codes in one row
        f'  {VALID_UPC_A}-{VALID_EAN_13}',
    ])
    def test_an_unusable_value_records_no_identifier(self, service, value):
        purchase = capture(service, barcode_listing(('UPC', value)))

        assert gtins(service, purchase.product_id) == []

    @pytest.mark.parametrize('value', [BAD_CHECK_DIGIT, ISBN_10, ''])
    def test_the_row_is_kept_as_a_specification(self, service, value):
        """FR-005: refusing to promote is not refusing to record"""
        purchase = capture(service, barcode_listing(
            ('UPC', value), ('Voltage', '12 Volts'),
        ))

        names = [name for name, _ in spec_rows(service, purchase.product_id)]
        assert 'UPC' in names or value == ''
        assert 'Voltage' in names

    def test_nothing_is_ever_stored_as_an_override(self, service):
        """FR-004: there is no override, and this is the test that says so"""
        purchase = capture(service, barcode_listing(('UPC', BAD_CHECK_DIGIT)))

        identifiers = service.get_product(purchase.product_id).identifiers
        assert not any(row.validation_overridden for row in identifiers)

    def test_an_unusable_value_is_reported_with_the_value(self, service):
        listing = barcode_listing(('UPC', BAD_CHECK_DIGIT))
        purchase = capture(service, listing)

        notes = service.describe_captured_barcodes(purchase.product_id, listing)

        assert [(n.row_name, n.value, n.outcome) for n in notes] == [
            ('UPC', BAD_CHECK_DIGIT, 'unusable')
        ]

    def test_a_refusal_costs_the_row_and_nothing_else(self, service):
        """FR-011: a refused promotion never fails the capture"""
        purchase = capture(service, barcode_listing(
            ('UPC', BAD_CHECK_DIGIT),
            ('Voltage', '12 Volts'),
            ('Material', '6061 Aluminium'),
        ), description='12V PSU', unit_price='24.99')

        assert purchase.id is not None
        assert purchase.unit_price == Decimal('24.99')
        assert spec_rows(service, purchase.product_id) == [
            ('UPC', BAD_CHECK_DIGIT),
            ('Voltage', '12 Volts'),
            ('Material', '6061 Aluminium'),
        ]

    def test_one_unusable_row_does_not_cost_a_usable_one(self, service):
        purchase = capture(service, barcode_listing(
            ('UPC', BAD_CHECK_DIGIT), ('ISBN', VALID_ISBN_13),
        ))

        assert gtins(service, purchase.product_id) == [ISBN_13_KEY]


class TestABarcodeAnotherProductHolds:
    """US3: a collision does not guess (FR-006)"""

    @pytest.fixture
    def holder(self, service):
        return service.create_product(
            description='The product that got there first',
            identifiers=[{'id_type': 'GTIN', 'value': VALID_UPC_A}],
        )

    def test_the_captured_product_gets_no_identifier(self, service, holder):
        purchase = capture(service, barcode_listing(('UPC', VALID_UPC_A)))

        assert purchase.product_id != holder.id
        assert gtins(service, purchase.product_id) == []

    def test_the_holding_product_is_left_exactly_as_it_was(self, service, holder):
        capture(service, barcode_listing(('UPC', VALID_UPC_A)))

        assert gtins(service, holder.id) == [VALID_GTIN_KEY]

    def test_the_value_is_still_kept_as_a_specification(self, service, holder):
        purchase = capture(service, barcode_listing(('UPC', VALID_UPC_A)))

        assert spec_rows(service, purchase.product_id) == [('UPC', VALID_UPC_A)]

    def test_the_report_names_the_product_that_holds_it(self, service, holder):
        listing = barcode_listing(('UPC', VALID_UPC_A))
        purchase = capture(service, listing)

        note = service.describe_captured_barcodes(purchase.product_id, listing)[0]

        assert note.outcome == 'taken'
        assert note.holder_id == holder.id
        assert note.holder_description == 'The product that got there first'

    def test_a_collision_does_not_fail_the_capture(self, service, holder):
        """FR-011 again, on the other refusal path"""
        purchase = capture(service, barcode_listing(
            ('UPC', VALID_UPC_A), ('Voltage', '12 Volts'),
        ), description='12V PSU')

        assert purchase.id is not None
        assert service.get_product(purchase.product_id).description == '12V PSU'

    def test_the_same_barcode_on_the_same_product_is_a_no_op(self, service, holder):
        """FR-007: recapturing a product onto its own identifier is not a duplicate"""
        listing = barcode_listing(('UPC', VALID_UPC_A))

        capture(service, listing, attach_to=str(holder.id))

        assert gtins(service, holder.id) == [VALID_GTIN_KEY]
        notes = service.describe_captured_barcodes(holder.id, listing)
        assert [n.outcome for n in notes] == ['recorded']


class TestADroppedRowNeverClaimsToBeKept:
    """The row the merge dropped took its value with it, whatever the value was.

    ``describe_captured_barcodes`` used to classify from the value alone, so a
    dropped row carrying a bad check digit was reported ``unusable`` -- with the
    confirmation page's "It is kept as a specification" attached to a value that
    was stored nowhere. Telling the operator a value is on the product when it is
    not is the silent loss the report exists to prevent, so these are the tests
    for the drop being recognized before anything about the value is considered.
    """

    def listing_of(self, value):
        return barcode_listing(('UPC', value))

    def test_a_dropped_row_with_a_bad_check_digit_is_not_examined(self, service):
        product = service.create_product(
            description='12V PSU',
            specifications=[{'name': 'UPC', 'value': VALID_UPC_A}],
        )
        listing = self.listing_of(BAD_CHECK_DIGIT)

        capture(service, listing, attach_to=str(product.id))
        note = service.describe_captured_barcodes(product.id, listing)[0]

        assert note.outcome == 'not_examined'
        assert note.kept_as_specification is False

    def test_the_captured_value_really_is_stored_nowhere(self, service):
        """The claim the old message made, stated as an assertion"""
        product = service.create_product(
            description='12V PSU',
            specifications=[{'name': 'UPC', 'value': VALID_UPC_A}],
        )

        capture(service, self.listing_of(BAD_CHECK_DIGIT), attach_to=str(product.id))

        assert spec_rows(service, product.id) == [('UPC', VALID_UPC_A)]
        assert gtins(service, product.id) == []

    def test_a_dropped_row_another_product_holds_is_not_examined_either(self, service):
        """The same false claim reached through the collision branch"""
        service.create_product(
            description='The product that got there first',
            identifiers=[{'id_type': 'GTIN', 'value': VALID_ISBN_13}],
        )
        product = service.create_product(
            description='12V PSU',
            specifications=[{'name': 'UPC', 'value': VALID_UPC_A}],
        )
        listing = self.listing_of(VALID_ISBN_13)

        capture(service, listing, attach_to=str(product.id))
        note = service.describe_captured_barcodes(product.id, listing)[0]

        assert note.outcome == 'not_examined'
        assert note.kept_as_specification is False
        assert spec_rows(service, product.id) == [('UPC', VALID_UPC_A)]

    def test_a_row_the_merge_kept_still_says_so(self, service):
        """The guard on over-correcting: an added row *is* kept"""
        listing = self.listing_of(BAD_CHECK_DIGIT)
        purchase = capture(service, listing)

        note = service.describe_captured_barcodes(purchase.product_id, listing)[0]

        assert note.outcome == 'unusable'
        assert note.kept_as_specification is True

    def test_the_same_value_arriving_twice_is_still_the_ordinary_drop(self, service):
        """FR-010's original case: the row is dropped, but the value is listed"""
        product = service.create_product(
            description='12V PSU',
            specifications=[{'name': 'UPC', 'value': VALID_UPC_A}],
        )
        listing = self.listing_of(VALID_UPC_A)

        capture(service, listing, attach_to=str(product.id))
        note = service.describe_captured_barcodes(product.id, listing)[0]

        assert note.outcome == 'not_examined'
        assert note.kept_as_specification is True


class TestTheReportCoversEveryRow:
    """FR-009: only equivalent *valid* forms collapse into one line"""

    def test_two_unusable_rows_are_two_lines(self, service):
        listing = barcode_listing(('UPC', BAD_CHECK_DIGIT), ('EAN', BAD_CHECK_DIGIT))
        purchase = capture(service, listing)

        notes = service.describe_captured_barcodes(purchase.product_id, listing)

        assert [(n.row_name, n.outcome) for n in notes] == [
            ('UPC', 'unusable'), ('EAN', 'unusable'),
        ]

    def test_two_valid_equivalent_rows_are_one_line(self, service):
        """The dedupe that is still wanted, as the counterweight"""
        listing = barcode_listing(('UPC', VALID_UPC_A), ('EAN', VALID_EAN_13))
        purchase = capture(service, listing)

        assert len(service.describe_captured_barcodes(purchase.product_id, listing)) == 1


class TestTheMessageTheOperatorReads:
    """_barcode_tally is where a wrong classification becomes a wrong sentence"""

    def note(self, **fields):
        from app.models import CapturedBarcode
        fields.setdefault('row_name', 'UPC')
        fields.setdefault('value', BAD_CHECK_DIGIT)
        return CapturedBarcode(**fields)

    def tally(self, *notes):
        from app.product.routes import _barcode_tally
        return _barcode_tally(list(notes))

    def test_a_kept_row_is_said_to_be_kept(self):
        message = self.tally(self.note(outcome='unusable'))

        assert 'not a valid barcode' in message
        assert 'kept as a specification' in message

    def test_a_dropped_row_is_never_said_to_be_kept(self):
        message = self.tally(self.note(outcome='unusable', kept_as_specification=False))

        assert 'not a valid barcode' in message
        assert 'kept as a specification' not in message

    def test_a_dropped_collision_is_never_said_to_be_kept(self):
        message = self.tally(self.note(
            outcome='taken', value=VALID_GTIN_KEY, holder_id=7,
            holder_description='Something else', kept_as_specification=False,
        ))

        assert 'already holds it' in message
        assert 'kept as a specification' not in message

    def test_an_unusable_value_is_quoted_rather_than_repr_ed(self):
        message = self.tally(self.note(outcome='unusable'))

        assert f'"{BAD_CHECK_DIGIT}"' in message
