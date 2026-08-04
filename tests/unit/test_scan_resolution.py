"""
Unit tests for CatalogService.resolve_scan().

The property under test throughout: a scan is always answered. A miss is an
offer to create with the identifier already attached, never a 404 and never an
exception (FR-018, SC-008).
"""

import pytest

from app.catalog_service import CatalogService
from app.models import ScanKind
from app.utils.ecia import EOT, GS, RS

VALID_UPC_A = "012345678905"
VALID_GTIN_KEY = "00012345678905"

ENVELOPE = "[)>" + RS + "06" + GS + "1PLM358N" + GS + "Q100" + RS + EOT
FULL_ENVELOPE = (
    "[)>" + RS + "06" + GS
    + "P296-1234-5-ND" + GS + "1PLM358N" + GS + "Q100" + GS
    + "K12345678" + GS + "1KSO987654" + GS + "9D2431"
    + RS + EOT
)


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


class TestInternalCode:
    def test_a_known_internal_code_resolves_to_its_product(self, service):
        product = service.create_product(description='Blue widget')
        resolution = service.scan(product.internal_code)

        assert resolution.outcome == 'product'
        assert resolution.product.id == product.id

    def test_an_unknown_internal_code_offers_creation(self, service):
        resolution = service.scan('WIT0123456789')

        assert resolution.outcome == 'create'
        assert resolution.prefill['identifier'] == 'WIT0123456789'
        assert resolution.product is None


class TestGtin:
    def test_a_known_barcode_resolves_to_its_product(self, service):
        product = service.create_product(
            description='Blue widget',
            identifiers=[{'id_type': 'GTIN', 'value': VALID_UPC_A}],
        )
        resolution = service.scan(VALID_UPC_A)

        assert resolution.outcome == 'product'
        assert resolution.product.id == product.id

    def test_an_equivalent_form_of_the_same_barcode_resolves_to_the_same_product(self, service):
        """FR-009, exercised through the scan path rather than the storage path"""
        product = service.create_product(
            description='Blue widget',
            identifiers=[{'id_type': 'GTIN', 'value': VALID_UPC_A}],
        )
        # The EAN-13 rendering of the same UPC-A.
        resolution = service.scan('0012345678905')
        assert resolution.product.id == product.id

    def test_an_uncatalogued_barcode_offers_creation_with_it_attached(self, service):
        """FR-018: never a 404, never a dead end"""
        resolution = service.scan(VALID_UPC_A)

        assert resolution.outcome == 'create'
        assert resolution.prefill['identifier'] == VALID_GTIN_KEY
        assert resolution.prefill['id_type'] == 'GTIN'
        assert resolution.prefill['raw_scan'] == VALID_UPC_A


class TestVendorIdentifier:
    """Rule 4 -- the one rule that can only be answered by looking"""

    def test_a_stored_asin_resolves_even_though_it_has_no_shape(self, service):
        product = service.create_product(
            description='Blue widget',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        resolution = service.scan('B0ABCDEFGH')

        assert resolution.outcome == 'product'
        assert resolution.product.id == product.id

    def test_the_resolution_reports_the_vendor_kind(self, service):
        """ScanKind.VENDOR is produced by resolution, not by the classifier"""
        service.create_product(
            description='Blue widget',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0ABCDEFGH', 'vendor': 'Amazon'}],
        )
        assert service.scan('B0ABCDEFGH').classification.kind is ScanKind.VENDOR

    def test_a_distributor_identifier_resolves_too(self, service):
        product = service.create_product(
            description='Op-amp',
            identifiers=[
                {'id_type': 'DISTRIBUTOR', 'value': '296-1234-5-ND', 'vendor': 'DigiKey'}
            ],
        )
        assert service.scan('296-1234-5-ND').product.id == product.id


class TestEcia:
    """Story 4: scan a distributor label, get an editable draft"""

    def test_a_known_manufacturer_part_number_resolves_to_its_product(self, service):
        product = service.create_product(
            description='LM358 op-amp',
            identifiers=[{'id_type': 'MPN', 'value': 'LM358N'}],
        )
        resolution = service.scan(ENVELOPE)

        assert resolution.outcome == 'product'
        assert resolution.product.id == product.id

    def test_an_unknown_part_offers_creation_with_every_extracted_field(self, service):
        """FR-017: all of it editable, none of it coerced"""
        resolution = service.scan(FULL_ENVELOPE)

        assert resolution.outcome == 'create'
        prefill = resolution.prefill
        assert prefill['identifier'] == 'LM358N'
        assert prefill['id_type'] == 'MPN'
        assert prefill['manufacturer_part_number'] == 'LM358N'
        assert prefill['distributor_part_number'] == '296-1234-5-ND'
        assert prefill['quantity'] == '100'
        assert prefill['order_reference'] == '12345678'
        assert prefill['supplier_order_reference'] == 'SO987654'
        assert prefill['date_code'] == '2431'

    def test_the_quantity_stays_a_string(self, service):
        assert isinstance(service.scan(FULL_ENVELOPE).prefill['quantity'], str)

    def test_a_corrupted_envelope_surfaces_the_raw_scan_for_manual_handling(self, service):
        """Story 4 scenario 3: not a silent failure"""
        corrupted = "[)>" + RS + "06X" + GS + "1PLM358N" + RS + EOT
        resolution = service.scan(corrupted)

        assert resolution.outcome == 'search'
        assert resolution.classification.raw == corrupted

    def test_a_well_formed_envelope_with_nothing_readable_lands_on_search(self, service):
        scan = "[)>" + RS + "06" + GS + "1TLOT4471" + RS + EOT
        assert service.scan(scan).outcome == 'search'


class TestFreeText:
    def test_junk_lands_on_a_search_carrying_the_raw_scan(self, service):
        resolution = service.scan('some nonsense the operator typed')

        assert resolution.outcome == 'search'
        assert resolution.product is None
        assert resolution.classification.raw == 'some nonsense the operator typed'

    def test_an_empty_scan_is_still_answered(self, service):
        assert service.scan('').outcome == 'search'

    def test_control_character_soup_is_still_answered(self, service):
        assert service.scan('\x1d\x1e\x04' * 100).outcome == 'search'


class TestNothingRaises:
    """A miss is an answer, not an exception"""

    @pytest.mark.parametrize('scan', [
        '',
        ' ',
        'WIT0123456789',
        VALID_UPC_A,
        '00000000',
        '[)>',
        '\x00\x01\x02',
        'B0ABCDEFGH',
    ])
    def test_every_scan_gets_one_of_three_outcomes(self, service, scan):
        assert service.scan(scan).outcome in ('product', 'create', 'search')

    def test_the_classification_is_passed_through(self, service):
        resolution = service.scan(VALID_UPC_A)
        assert resolution.classification.raw == VALID_UPC_A
        assert resolution.classification.kind is ScanKind.GTIN


class TestSerialization:
    def test_a_product_outcome_serializes_the_product(self, service):
        product = service.create_product(description='Blue widget')
        payload = service.scan(product.internal_code).to_dict()

        assert payload['outcome'] == 'product'
        assert payload['product']['id'] == product.id

    def test_a_search_outcome_has_no_product(self, service):
        payload = service.scan('nonsense').to_dict()
        assert payload['outcome'] == 'search'
        assert payload['product'] is None
