"""
Unit tests for the pack fields on Record a Purchase (feature 058, issue #191).

The capture page has asked how many packs were bought, what one cost and how
many came in it since feature 046. Record a Purchase -- the form on a product's
page -- asked only for a quantity and a unit price, so a hand-recorded pack of
100 meant doing the arithmetic yourself and losing the vendor's pack price to
the rounding. These cover the server side: the derivation that does not depend
on the browser running ``pack-unit-price.js``, and the vendor pack line.
"""

from decimal import Decimal

import pytest

from app.catalog_service import CatalogService


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def product(service):
    return service.create_product(description='Widget screws, M3 x 8')


def record(client, product, **form):
    data = {'vendor': 'Acme'}
    data.update(form)
    return client.post(
        f'/products/{product.id}/purchases/new', data=data, follow_redirects=False
    )


def only_purchase(service, product):
    history = service.get_purchase_history(product.id)
    assert len(history) == 1
    return history[0]


class TestAPackRecordedByHand:
    """US1: the three pack fields do the arithmetic, and the pack is kept."""

    def test_two_packs_of_a_hundred_records_two_hundred(self, client, service, product):
        """The issue. Quantity and Unit Price empty, as with scripting off."""
        response = record(client, product, packs='2', pack_size='100', pack_price='13.23')

        assert response.status_code == 302
        purchase = only_purchase(service, product)
        assert purchase.quantity == 200
        assert purchase.unit_price == Decimal('0.13')

    def test_the_vendor_pack_is_kept(self, client, service, product):
        """SC-002. The invoice figure survives the rounding."""
        record(client, product, packs='2', pack_size='100', pack_price='13.23')

        purchase = only_purchase(service, product)
        assert purchase.pack_size == 100
        assert purchase.pack_price == Decimal('13.23')
        assert purchase.unit_price * purchase.pack_size == Decimal('13.00')

    def test_a_typed_quantity_wins(self, client, service, product):
        """FR-003. What turned up in the box, not what was ordered."""
        record(client, product, packs='2', pack_size='100', pack_price='13.23',
               quantity='190')

        assert only_purchase(service, product).quantity == 190

    def test_a_typed_unit_price_wins(self, client, service, product):
        record(client, product, packs='2', pack_size='100', pack_price='13.23',
               unit_price='0.15')

        assert only_purchase(service, product).unit_price == Decimal('0.15')

    def test_blank_packs_counts_as_one(self, client, service, product):
        record(client, product, packs='', pack_size='100', pack_price='13.23')

        assert only_purchase(service, product).quantity == 100

    def test_a_pack_without_a_price_derives_the_quantity_only(
        self, client, service, product
    ):
        """Both or neither: a pack size alone cannot restate the vendor's line."""
        record(client, product, packs='3', pack_size='10', pack_price='')

        purchase = only_purchase(service, product)
        assert purchase.quantity == 30
        assert purchase.unit_price is None
        assert purchase.pack_size is None
        assert purchase.pack_price is None

    @pytest.mark.parametrize('field, value', [
        ('pack_size', '0'),
        ('pack_size', '1.5'),
        ('pack_price', 'twelve'),
        ('pack_price', '-1'),
    ])
    def test_a_bad_pack_value_is_refused_and_records_nothing(
        self, client, service, product, field, value
    ):
        """FR-007. Re-displayed as entered, and nothing written."""
        form = {'packs': '2', 'pack_size': '100', 'pack_price': '13.23',
                'notes': 'kept on refusal'}
        form[field] = value
        response = record(client, product, **form)

        assert response.status_code == 200
        assert service.get_purchase_history(product.id) == []
        body = response.get_data(as_text=True)
        assert f'value="{value}"' in body
        assert 'kept on refusal' in body


class TestASingleItemIsUnchanged:
    """US2: a purchase that states no pack records exactly as before."""

    def test_the_default_pack_fields_change_nothing(self, client, service, product):
        record(client, product, packs='1', pack_size='1', pack_price='',
               quantity='5', unit_price='2.00')

        purchase = only_purchase(service, product)
        assert purchase.quantity == 5
        assert purchase.unit_price == Decimal('2.00')
        assert purchase.pack_size is None
        assert purchase.pack_price is None

    def test_a_pack_of_one_stores_no_pack(self, client, service, product):
        """A pack of one is no pack (046 FR-031)."""
        record(client, product, packs='1', pack_size='1', pack_price='4.50',
               quantity='1', unit_price='4.50')

        purchase = only_purchase(service, product)
        assert purchase.pack_size is None
        assert purchase.pack_price is None

    def test_a_post_without_pack_fields_still_records(self, client, service, product):
        """A form rendered before 058 submits none of the three."""
        record(client, product, quantity='5', unit_price='2.00')

        purchase = only_purchase(service, product)
        assert purchase.quantity == 5
        assert purchase.unit_price == Decimal('2.00')
        assert purchase.pack_size is None

    def test_the_form_offers_the_pack_fields(self, client, product):
        body = client.get(f'/products/{product.id}/purchases/new').get_data(as_text=True)

        for field in ('packs', 'pack_price', 'pack_size'):
            assert f'name="{field}"' in body
        assert 'js/pack-unit-price.js' in body
