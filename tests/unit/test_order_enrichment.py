"""Enriching a product an order line *matched* (feature 029, PR #126 review).

A product a line matches predates the order, and may have blanks the vendor can
fill: a manufacturer nobody typed, no category, no parametric specs. DigiKey
publishes all three, so capturing a line that attaches to such a product
backfills them.

**These tests exist because feature 029 broke exactly that and nothing noticed.**
Consolidating the two vendors' `_product_for` helpers dropped
``_enrich_digikey_product`` from the MATCHED branch, so an order line attaching to
an existing product silently stopped enriching it. The DigiKey suite -- which is
that refactor's regression gate, and passed unedited throughout -- has a test for
this exact MATCHED/attach scenario, but it asserts only the attach counts and the
product's identity, never that the product gained anything. A gate is only as
good as what its assertions actually look at.

The fill-gaps-only rule is tested here too, because it is the half that makes
enrichment safe to run against a product the operator has already curated.
"""

import pytest

from app.catalog_service import CatalogService
from app.services.order_vendors import for_vendor

# The DigiKey suite's own fixtures. Imported rather than rebuilt so these tests
# exercise the same recorded part detail the rest of the DigiKey tests do.
from tests.unit.test_digikey_capture import (  # noqa: F401
    FakeDigiKey,
    catalog,
    digikey,
    include_all,
    order,
)

pytestmark = pytest.mark.unit

# The line in the recorded order whose manufacturer part number is IRM-05-5.
MATCHED_MPN = 'IRM-05-5'


def specs_of(catalog, product_id):
    from app.database import ProductSpecification
    session = catalog.storage._get_session()
    try:
        return {
            row.name: row.value
            for row in session.query(ProductSpecification)
            .filter(ProductSpecification.product_id == product_id).all()
        }
    finally:
        session.close()


class TestAMatchedProductIsEnriched:
    def test_a_blank_manufacturer_is_filled_from_the_part_detail(
        self, catalog, order, digikey
    ):
        """The regression PR #126's review caught."""
        existing = catalog.create_product(
            description='5V PSU I already own',
            identifiers=[{'id_type': 'MPN', 'value': MATCHED_MPN}],
        )
        assert not catalog.get_product(existing.id).manufacturer

        catalog.capture_digikey_order(order, include_all(order), digikey)

        assert catalog.get_product(existing.id).manufacturer

    def test_a_blank_category_is_filled(self, catalog, order, digikey):
        existing = catalog.create_product(
            description='5V PSU I already own',
            identifiers=[{'id_type': 'MPN', 'value': MATCHED_MPN}],
        )
        assert not catalog.get_product(existing.id).category_path

        catalog.capture_digikey_order(order, include_all(order), digikey)

        assert catalog.get_product(existing.id).category_path

    def test_parametric_specifications_are_added(self, catalog, order, digikey):
        existing = catalog.create_product(
            description='5V PSU I already own',
            identifiers=[{'id_type': 'MPN', 'value': MATCHED_MPN}],
        )
        assert specs_of(catalog, existing.id) == {}

        catalog.capture_digikey_order(order, include_all(order), digikey)

        assert specs_of(catalog, existing.id) != {}

    def test_the_line_still_attaches_rather_than_duplicating(
        self, catalog, order, digikey
    ):
        """Enrichment must not have changed what the line does."""
        existing = catalog.create_product(
            description='5V PSU I already own',
            identifiers=[{'id_type': 'MPN', 'value': MATCHED_MPN}],
        )

        result = catalog.capture_digikey_order(order, include_all(order), digikey)

        assert result.products_attached == 1
        product = catalog.find_product_by_identifier(MATCHED_MPN, id_type='MPN')
        assert product.id == existing.id


class TestWhatTheOperatorSetWins:
    def test_a_manufacturer_the_operator_typed_is_not_overwritten(
        self, catalog, order, digikey
    ):
        """Enrichment fills gaps; it does not correct the operator."""
        existing = catalog.create_product(
            description='5V PSU I already own',
            manufacturer='The Name I Filed It Under',
            identifiers=[{'id_type': 'MPN', 'value': MATCHED_MPN}],
        )

        catalog.capture_digikey_order(order, include_all(order), digikey)

        assert catalog.get_product(existing.id).manufacturer == (
            'The Name I Filed It Under'
        )


class TestVendorsWithoutPartDetail:
    def test_only_digikey_enriches_a_matched_product(self):
        """McMaster and Amazon have no part lookup: the page *is* the detail.

        There is nothing for them to backfill from, which is why this hook is
        None for both rather than a no-op they have to supply.
        """
        assert for_vendor('DigiKey').enrich_product is not None
        assert for_vendor('McMaster-Carr').enrich_product is None
        assert for_vendor('Amazon').enrich_product is None

    def test_a_vendor_without_the_hook_still_captures_a_matched_line(
        self, test_storage
    ):
        """The MATCHED path must not require the hook to exist."""
        from app.catalog_service import AMAZON_ORDER_VENDOR, AMAZON_VENDOR
        from app.models import (
            AMAZON_PAYLOAD_VENDOR, AMAZON_PAYLOAD_VERSION, AmazonOrder,
        )

        service = CatalogService(test_storage)
        payload = {
            'version': AMAZON_PAYLOAD_VERSION,
            'vendor': AMAZON_PAYLOAD_VENDOR,
            'order_number': '111-2223334-5556667',
            'lines': [{'asin': 'B0TESTAAA1', 'title': 'A thing',
                       'unit_price': '9.99'}],
        }
        first = AmazonOrder.from_payload(payload)
        service.capture_order_lines(
            first, AMAZON_ORDER_VENDOR,
            {line.form_key: {'include': True} for line in first.lines},
        )

        second = AmazonOrder.from_payload(
            dict(payload, order_number='111-9999999-9999999')
        )
        result = service.capture_order_lines(
            second, AMAZON_ORDER_VENDOR,
            {line.form_key: {'include': True} for line in second.lines},
        )

        assert result.products_attached == 1
        assert result.products_created == 0
