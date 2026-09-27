"""A McMaster listing finds the product its order created (feature 049).

Issue #171. A McMaster order records each part number as a
``DISTRIBUTOR`` identifier; the single-listing capture used to record a
``VENDOR`` one, and both of its "does this item number already name a
product?" questions looked only for ``VENDOR``. So capturing an ordered
part's product page never offered 044's details-only choice -- only "this is
a separate order, record it anyway" -- and recording it made a second product
for the same part.

Both questions now look for either kind, scoped to the vendor, and a McMaster
product-page capture records ``DISTRIBUTOR`` as 028 FR-012 specified. Amazon is
the control: every assertion about it here is one that held before.
"""

import json

import pytest

from app.catalog_service import (
    AMAZON_VENDOR,
    DIGIKEY_VENDOR,
    MCMASTER_VENDOR,
    CatalogService,
)
from app.exceptions import CaptureDecisionRequired
from app.models import IdentifierType
from app.utils.clock import local_now
from tests.unit.test_mcmaster_capture import build_order, include_all

pytestmark = pytest.mark.unit


PART = '91290A115'
PAGE_URL = f'https://www.mcmaster.com/{PART}/'


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


def listing_payload(**overrides):
    """What the extension reads off a McMaster product page."""
    data = {
        'version': 1,
        'source_url': PAGE_URL,
        'vendor_item_id': PART,
        'listing_title': 'Alloy Steel Socket Head Screw',
        'specifications': [
            {'name': 'Thread Size', 'value': 'M3 x 0.5 mm'},
            {'name': 'Length', 'value': '10 mm'},
        ],
    }
    data.update(overrides)
    return data


def todays_date_text():
    """Today as McMaster's order page writes it, so the order is in window."""
    now = local_now()
    return f"{now:%B} {now.day}, {now:%Y}"


def capture_the_order(catalog, **decision):
    """Capture a one-line McMaster order for PART, dated today; its purchase.

    ``decision`` answers the line's questions, e.g. ``same_purchase='adopt'``
    when the part's page was captured first.
    """
    order = build_order(order_date=todays_date_text(), lines=[{
        'line_number': 1, 'part_number': PART,
        'description': 'Socket head screws', 'packs': 1,
        'pack_size': 100, 'pack_price': '13.23',
    }])
    catalog.capture_mcmaster_order(order, include_all(order, **decision))
    product = catalog.find_product_by_identifier(
        PART, id_type=IdentifierType.DISTRIBUTOR.value, vendor=MCMASTER_VENDOR)
    assert product is not None
    [purchase] = catalog.get_purchase_history(product.id)
    return purchase


def land(client):
    """What the extension's new tab shows for the product page."""
    response = client.post('/api/capture', data={
        'url': PAGE_URL,
        'listing_title': 'Alloy Steel Socket Head Screw',
        'listing': json.dumps(listing_payload()),
    })
    assert response.status_code == 200
    return response.get_data(as_text=True)


def capture_the_page(catalog, **extra):
    """A product-page purchase capture, as the service receives one."""
    return catalog.capture_order(
        vendor=MCMASTER_VENDOR, vendor_item_id=PART, url=PAGE_URL,
        quantity=1, unit_price='13.23', **extra,
    )


def holders(catalog, value=PART):
    return [
        p for p in catalog.list_products()
        if any(i.value == value for i in p.identifiers)
    ]


class TestOrderThenProductPage:
    """US1: the reported failure."""

    def test_the_listing_names_the_product_and_the_order(self, catalog):
        recorded = capture_the_order(catalog)

        match = catalog.find_listing_match(MCMASTER_VENDOR, PART, PAGE_URL)

        assert match is not None, 'the order-created product was not found'
        assert match.product_id == recorded.product_id
        assert match.from_order is True
        assert match.order_purchase_id == recorded.id
        assert match.order_reference == recorded.supplier_order_reference

    def test_the_landing_offers_details_only_naming_the_order(
        self, catalog, client
    ):
        capture_the_order(catalog)

        html = land(client)

        assert 'id="order-item-match"' in html
        assert 'id="intent-details"' in html
        assert 'id="duplicate-warning"' not in html

    def test_details_only_fills_the_product_and_records_no_purchase(
        self, catalog, client
    ):
        recorded = capture_the_order(catalog)

        response = client.post('/products/capture', data={
            'url': PAGE_URL,
            'vendor': MCMASTER_VENDOR,
            'vendor_item_id': PART,
            'listing': json.dumps(listing_payload()),
            'intent': 'details',
            'details_product_id': str(recorded.product_id),
        })

        assert response.status_code == 302
        product = catalog.get_product(recorded.product_id)
        assert {row.name for row in product.specifications} == {
            'Thread Size', 'Length',
        }
        assert len(catalog.get_purchase_history(recorded.product_id)) == 1
        assert len(holders(catalog)) == 1


class TestProductPageFirst:
    """US2: the write agrees with the order's; both directions still meet."""

    def test_the_part_number_is_recorded_as_a_distributor_identifier(
        self, catalog
    ):
        purchase = capture_the_page(catalog)

        product = catalog.get_product(purchase.product_id)
        kinds = {
            (i.id_type, i.vendor) for i in product.identifiers
            if i.value == PART
        }
        assert kinds == {(IdentifierType.DISTRIBUTOR.value, MCMASTER_VENDOR)}

    def test_capturing_the_page_again_offers_details_only(
        self, catalog, client
    ):
        purchase = capture_the_page(catalog)

        match = catalog.find_listing_match(MCMASTER_VENDOR, PART, PAGE_URL)
        html = land(client)

        assert match.product_id == purchase.product_id
        assert 'id="intent-details"' in html

    def test_a_second_purchase_capture_finds_the_product(self, catalog):
        """Not a second product, and not a clash on its own identifier."""
        first = capture_the_page(catalog)

        with pytest.raises(CaptureDecisionRequired) as asked:
            capture_the_page(catalog, acknowledged_duplicate_of=first.id)
        assert asked.value.assessment.matched_product_id == first.product_id

        second = capture_the_page(
            catalog, acknowledged_duplicate_of=first.id,
            attach_to=first.product_id,
        )
        assert second.product_id == first.product_id
        assert len(holders(catalog)) == 1

    def test_the_order_then_lands_on_the_same_product(self, catalog):
        purchase = capture_the_page(catalog)

        recorded = capture_the_order(catalog, same_purchase='adopt')

        assert recorded.id == purchase.id
        assert recorded.product_id == purchase.product_id
        assert len(holders(catalog)) == 1

    def test_a_product_recorded_the_old_way_is_still_found(self, catalog):
        """FR-007: no migration, because VENDOR is still looked for."""
        product = catalog.create_product(
            description='Captured before 049',
            identifiers=[{'id_type': 'VENDOR', 'value': PART,
                          'vendor': MCMASTER_VENDOR}],
        )

        match = catalog.find_listing_match(MCMASTER_VENDOR, PART, PAGE_URL)
        with pytest.raises(CaptureDecisionRequired) as asked:
            capture_the_page(catalog)

        assert match.product_id == product.id
        assert asked.value.assessment.matched_product_id == product.id


class TestPurchaseAfterAnOrder:
    """US3: a reorder captured from the page lands on the order's product."""

    def test_it_is_asked_about_not_filed_as_a_new_product(self, catalog):
        recorded = capture_the_order(catalog)

        with pytest.raises(CaptureDecisionRequired) as asked:
            capture_the_page(catalog, acknowledged_duplicate_of=recorded.id)
        assert asked.value.assessment.matched_product_id == recorded.product_id

        again = capture_the_page(
            catalog, acknowledged_duplicate_of=recorded.id,
            attach_to=recorded.product_id,
        )
        assert again.product_id == recorded.product_id
        assert len(holders(catalog)) == 1


class TestOtherVendors:
    """Edge cases: Amazon unchanged, scopes respected, DigiKey matched."""

    def test_an_amazon_capture_still_records_a_vendor_identifier(
        self, catalog
    ):
        purchase = catalog.capture_order(
            vendor=AMAZON_VENDOR, vendor_item_id='B0CXYZ1234',
            url='https://www.amazon.com/dp/B0CXYZ1234',
            quantity=1, unit_price='8.99',
        )

        product = catalog.get_product(purchase.product_id)
        kinds = {
            (i.id_type, i.vendor) for i in product.identifiers
            if i.value == 'B0CXYZ1234'
        }
        assert kinds == {(IdentifierType.VENDOR.value, AMAZON_VENDOR)}

    def test_another_vendors_part_number_is_not_this_part(self, catalog):
        catalog.create_product(
            description='Held for DigiKey',
            identifiers=[{'id_type': 'DISTRIBUTOR', 'value': PART,
                          'vendor': DIGIKEY_VENDOR}],
        )

        assert catalog.find_listing_match(MCMASTER_VENDOR, PART) is None

    def test_a_typed_digikey_part_number_finds_its_order_product(
        self, catalog
    ):
        """The paste form, with the DigiKey part number typed in: the product
        the DigiKey order created is the one it names."""
        product = catalog.create_product(
            description='From a DigiKey order',
            identifiers=[{'id_type': 'DISTRIBUTOR', 'value': '296-1234-ND',
                          'vendor': DIGIKEY_VENDOR}],
        )

        match = catalog.find_listing_match(DIGIKEY_VENDOR, '296-1234-ND')

        assert match.product_id == product.id
