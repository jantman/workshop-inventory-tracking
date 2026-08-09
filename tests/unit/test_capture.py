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

from datetime import datetime
from decimal import Decimal

import pytest

from app.catalog_service import CatalogService
from app.exceptions import CaptureDecisionRequired, ValidationError

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
            description='Blue widget, already catalogued',
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
        assert assessment.matched_product_description == 'Blue widget, already catalogued'
        assert assessment.matched_product_part_number == 'BW-10'
        assert assessment.has_uncorroborated_match is True
        # Nothing written while the question is open.
        assert len(service.list_products()) == 1

    def test_choosing_the_matched_product_attaches_to_it(self, service):
        existing = service.create_product(
            description='Blue widget, already catalogued',
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
            description='Blue widget, already catalogued',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            listing_title='A completely different thing', attach_to='new',
        )

        assert purchase.product_id != existing.id
        assert len(service.list_products()) == 2

        untouched = service.get_product(existing.id)
        assert untouched.description == 'Blue widget, already catalogued'
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
    def catalogued(self, service):
        return service.create_product(
            description='12V 3A PSU',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )

    def test_both_matching_attaches_silently(self, service, catalogued):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='Mean Well', manufacturer_part_number='RS-15-12',
        )
        assert purchase.product_id == catalogued.id

    def test_case_and_padding_do_not_defeat_it(self, service, catalogued):
        purchase = service.capture_order(
            vendor='Amazon', vendor_item_id='B0ABCDEFGH',
            manufacturer='  mean well ', manufacturer_part_number='rs-15-12',
        )
        assert purchase.product_id == catalogued.id

    def test_the_manufacturer_alone_is_not_evidence(self, service, catalogued):
        """One name matches a vendor's whole catalogue"""
        with pytest.raises(CaptureDecisionRequired):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH', manufacturer='Mean Well',
            )

    def test_the_part_number_alone_is_not_evidence(self, service, catalogued):
        with pytest.raises(CaptureDecisionRequired):
            service.capture_order(
                vendor='Amazon', vendor_item_id='B0ABCDEFGH',
                manufacturer_part_number='RS-15-12',
            )

    def test_a_disagreeing_part_number_asks(self, service, catalogued):
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
            description='Blue widget, already catalogued',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        response = client.post('/api/capture', json={'url': AMAZON_URL})

        assert response.status_code == 409
        assessment = response.get_json()['assessment']
        assert assessment['has_uncorroborated_match'] is True
        assert assessment['matched_product_description'] == 'Blue widget, already catalogued'
        assert len(service.list_products()) == 1

    def test_re_posting_with_the_answer_resolves_it(self, client, service):
        service.create_product(
            description='Blue widget, already catalogued',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        response = client.post('/api/capture', json={
            'url': AMAZON_URL, 'attach_to': 'new',
        })

        assert response.status_code == 201
        assert len(service.list_products()) == 2


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
