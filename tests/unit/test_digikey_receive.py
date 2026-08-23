"""
Unit tests for receiving a DigiKey order by scanning a bag (feature 024, US2).

The mechanism: a bag's 2D label carries the sales order number as ECIA ``1K`` and
the DigiKey part number as ``P``. Those two together name exactly one line of
exactly one order. ``app/utils/ecia.py`` has parsed both since the first release;
what was missing was somewhere for ``1K`` to go, and now there is.

The label in these tests is the real one from issue #108, re-split with its
separators restored -- its values agree with the recorded order field for field.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.catalog_service import CatalogService
from app.models import DigiKeyOrder, DigiKeyPart, ScanKind

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures' / 'digikey'

RS, GS, EOT = "\x1e", "\x1d", "\x04"

pytestmark = pytest.mark.unit


def bag_label(digikey_part_number='1866-3032-ND', mpn='IRM-10-5',
              sales_order='100882558', quantity='5'):
    """A DigiKey bag label, in the shape a wedge delivers it."""
    return (
        "[)>" + RS + "06" + GS
        + f"P{digikey_part_number}" + GS
        + f"1P{mpn}" + GS
        + f"1K{sales_order}" + GS
        + "10K130599231" + GS
        + f"Q{quantity}" + GS
        + "4LCN"
        + RS + EOT
    )


class FakeDigiKey:
    def get_part(self, part_number):
        body = json.loads((FIXTURES / 'productdetails.json').read_text(),
                          parse_float=Decimal)
        return DigiKeyPart.from_payload(body)


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def order():
    return DigiKeyOrder.from_payload(
        json.loads((FIXTURES / 'salesorder.json').read_text(), parse_float=Decimal)
    )


@pytest.fixture
def captured(catalog, order):
    """An order already captured, with two outstanding lines."""
    decisions = {line.form_key: {'include': True} for line in order.lines}
    catalog.capture_digikey_order(order, decisions, FakeDigiKey())
    return order


class TestReceiveOutcome:

    def test_a_bag_from_a_captured_order_resolves_to_receive(self, catalog, captured):
        """FR-019. Not the product page, not a blank draft -- the receipt for that line."""
        resolution = catalog.scan(bag_label())
        assert resolution.outcome == 'receive'
        assert len(resolution.purchases) == 1
        assert resolution.purchases[0].vendor_item_id == '1866-3032-ND'
        assert resolution.purchases[0].is_outstanding

    def test_the_order_line_beats_the_mpn_product_lookup(self, catalog, captured):
        """The ordering that makes FR-019 true for the common case.

        Capture created a product carrying this MPN, so the pre-existing 1P
        lookup would happily resolve to it. If that ran first, a bag for a part
        you have bought before would open the product page -- satisfying FR-019
        only for parts you have never bought, which is backwards.
        """
        product = catalog.find_product_by_identifier('IRM-10-5', id_type='MPN')
        assert product is not None, 'the MPN lookup would have matched'

        resolution = catalog.scan(bag_label())
        assert resolution.outcome == 'receive'

    def test_the_classification_is_still_ecia(self, catalog, captured):
        resolution = catalog.scan(bag_label())
        assert resolution.classification.kind is ScanKind.ECIA
        assert resolution.classification.ecia_fields['1K'] == '100882558'
        assert resolution.classification.ecia_fields['Q'] == '5'

    def test_an_already_received_line_is_reported_not_received_again(
            self, catalog, captured):
        """FR-023."""
        lines = catalog.find_order_lines('100882558')
        target = [p for p in lines if p.vendor_item_id == '1866-3032-ND'][0]
        catalog.receive_purchase(target.id)

        resolution = catalog.scan(bag_label())
        assert resolution.outcome == 'receive'
        # The purchase is found, but nothing about it is outstanding.
        assert len(resolution.purchases) == 1
        assert not resolution.purchases[0].is_outstanding

    def test_two_outstanding_lines_for_one_part_return_both(self, catalog, captured):
        """FR-026. The catalog shows the candidates; it does not pick one."""
        lines = catalog.find_order_lines('100882558')
        product_id = [p for p in lines if p.vendor_item_id == '1866-3032-ND'][0].product_id
        catalog.record_purchase(
            product_id, vendor='DigiKey', vendor_item_id='1866-3032-ND',
            supplier_order_reference='100882558',
        )
        resolution = catalog.scan(bag_label())
        assert len(resolution.purchases) == 2


class TestUnchangedBehaviour:
    """Everything that did not match must behave exactly as it did before."""

    def test_a_label_for_an_uncaptured_order_is_unchanged(self, catalog, captured):
        """FR-025."""
        resolution = catalog.scan(bag_label(sales_order='999999999'))
        assert resolution.outcome != 'receive'
        # The part is in the catalog, so this is the pre-existing MPN behaviour.
        assert resolution.outcome == 'product'

    def test_a_part_the_order_does_not_contain_is_unchanged(self, catalog, captured):
        """FR-024."""
        resolution = catalog.scan(
            bag_label(digikey_part_number='999-9999-ND', mpn='NOT-IN-THIS-ORDER')
        )
        assert resolution.outcome == 'create'

    def test_a_label_with_no_sales_order_number_is_unchanged(self, catalog, captured):
        label = (
            "[)>" + RS + "06" + GS + "P1866-3032-ND" + GS + "1PIRM-10-5"
            + GS + "Q5" + RS + EOT
        )
        resolution = catalog.scan(label)
        assert resolution.outcome == 'product'

    def test_an_ordinary_barcode_is_unchanged(self, catalog, captured):
        assert catalog.scan('012345678905').outcome in ('product', 'create')

    def test_free_text_still_searches(self, catalog, captured):
        assert catalog.scan('some notes about a thing').outcome == 'search'


class TestFindReceivable:

    def test_finds_the_line(self, catalog, captured):
        found = catalog.find_receivable('100882558', '1866-3027-ND')
        assert len(found) == 1
        assert found[0].vendor_item_id == '1866-3027-ND'

    def test_returns_received_lines_too(self, catalog, captured):
        """The route distinguishes 'already received' from 'no such line'."""
        lines = catalog.find_order_lines('100882558')
        catalog.receive_purchase(lines[0].id)
        found = catalog.find_receivable('100882558', lines[0].vendor_item_id)
        assert len(found) == 1
        assert not found[0].is_outstanding

    def test_nothing_for_an_uncaptured_order(self, catalog, captured):
        assert catalog.find_receivable('999999999', '1866-3027-ND') == []

    def test_nothing_for_a_blank_key(self, catalog, captured):
        assert catalog.find_receivable('', '1866-3027-ND') == []
        assert catalog.find_receivable('100882558', '') == []

    def test_another_vendor_is_not_matched(self, catalog, captured):
        lines = catalog.find_order_lines('100882558')
        catalog.record_purchase(
            lines[0].product_id, vendor='Mouser', vendor_item_id='1866-3027-ND',
        )
        assert len(catalog.find_receivable('100882558', '1866-3027-ND')) == 1


class TestScanApiUrl:
    """Where the header scan box is sent (FR-019, FR-023, FR-026).

    ``app/static/js/scan-capture.js`` follows ``data.url`` without looking at
    ``outcome``, so the whole of the fourth outcome's behaviour is this URL --
    which is why the feature needed no JavaScript change.
    """

    @pytest.fixture
    def client_with_order(self, app, client, test_storage, order):
        catalog = CatalogService(test_storage)
        decisions = {line.form_key: {'include': True} for line in order.lines}
        catalog.capture_digikey_order(order, decisions, FakeDigiKey())
        return client, catalog

    def _scan(self, client, label):
        response = client.post('/api/scan', json={'scan': label})
        assert response.status_code == 200
        return response.get_json()

    def test_one_outstanding_line_goes_to_its_receipt_with_the_label_quantity(
            self, client_with_order):
        client, catalog = client_with_order
        payload = self._scan(client, bag_label(quantity='5'))
        assert payload['outcome'] == 'receive'

        target = catalog.find_receivable('100882558', '1866-3032-ND')[0]
        assert payload['url'] == f'/purchases/{target.id}/receive?quantity=5'

    def test_the_label_quantity_is_uncoerced(self, client_with_order):
        """Cut tape quantities can be lengths. Taken as printed, editable after."""
        client, _ = client_with_order
        payload = self._scan(client, bag_label(quantity='2.5M'))
        assert payload['url'].endswith('quantity=2.5M')

    def test_an_already_received_line_goes_to_the_order_screen(self, client_with_order):
        """FR-023."""
        client, catalog = client_with_order
        target = catalog.find_receivable('100882558', '1866-3032-ND')[0]
        catalog.receive_purchase(target.id)

        payload = self._scan(client, bag_label())
        assert payload['outcome'] == 'receive'
        assert '/products/digikey/orders/100882558' in payload['url']
        assert 'highlight=1866-3032-ND' in payload['url']

    def test_several_candidates_go_to_the_order_screen(self, client_with_order):
        """FR-026. The catalog asks; it does not pick."""
        client, catalog = client_with_order
        existing = catalog.find_receivable('100882558', '1866-3032-ND')[0]
        catalog.record_purchase(
            existing.product_id, vendor='DigiKey', vendor_item_id='1866-3032-ND',
            supplier_order_reference='100882558',
        )
        payload = self._scan(client, bag_label())
        assert len(payload['purchases']) == 2
        assert '/products/digikey/orders/100882558' in payload['url']

    def test_an_uncaptured_order_is_unchanged(self, client_with_order):
        """FR-025."""
        client, _ = client_with_order
        payload = self._scan(client, bag_label(sales_order='999999999'))
        assert payload['outcome'] == 'product'
        assert '/receive' not in payload['url']

    def test_existing_outcomes_still_carry_no_purchases(self, client_with_order):
        client, _ = client_with_order
        payload = self._scan(client, 'just some text')
        assert payload['outcome'] == 'search'
        assert payload['purchases'] == []
