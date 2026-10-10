"""Setting one category on several products (feature 063, issue #201).

Two claims. A category set in bulk is the category Edit Product would store for
the same input. And the set is all or nothing: a blank category, an over-long
one or a product that no longer exists leaves every product as it was.
"""

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ItemNotFoundError, ValidationError

pytestmark = pytest.mark.unit

URL = '/api/products/category'


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def products(catalog):
    return [
        catalog.create_product(description='Washer', category_path='fasteners',
                               location='Shelf A', quantity=4),
        catalog.create_product(description='Nut', category_path='hardware'),
        catalog.create_product(description='Bolt'),
    ]


def _categories(catalog, products):
    return [catalog.get_product(p.id).category_path for p in products]


class TestSetCategory:
    def test_sets_the_category_on_each_named_product_only(self, catalog, products):
        result = catalog.set_category([products[0].id, products[2].id], 'tools/hand')

        assert result == {'category_path': 'tools/hand', 'products': 2}
        assert _categories(catalog, products) == ['tools/hand', 'hardware', 'tools/hand']

    def test_stores_what_edit_product_stores_for_the_same_input(self, catalog, products):
        raw = '  Tools / Hand //Pliers '
        catalog.update_product(products[1].id, category_path=raw)
        catalog.set_category([products[0].id], raw)

        edited, bulk = _categories(catalog, products[:2])
        assert bulk == edited == 'tools/hand/pliers'

    def test_a_new_category_is_accepted(self, catalog, products):
        catalog.set_category([products[0].id], 'never/seen/before')

        assert 'never/seen/before' in catalog.list_categories()

    def test_repeated_ids_count_once(self, catalog, products):
        result = catalog.set_category([products[0].id, products[0].id], 'x')

        assert result['products'] == 1

    def test_only_the_category_changes(self, catalog, products):
        catalog.set_category([products[0].id], 'tools')

        product = catalog.get_product(products[0].id)
        assert (product.description, product.location, product.quantity) == (
            'Washer', 'Shelf A', 4)

    @pytest.mark.parametrize('blank', ['', '   ', '/', ' / / '])
    def test_blank_is_refused_and_nothing_changes(self, catalog, products, blank):
        with pytest.raises(ValidationError):
            catalog.set_category([p.id for p in products], blank)

        assert _categories(catalog, products) == ['fasteners', 'hardware', None]

    def test_over_long_is_refused_and_nothing_changes(self, catalog, products):
        with pytest.raises(ValidationError):
            catalog.set_category([products[0].id], 'a' * 513)

        assert _categories(catalog, products) == ['fasteners', 'hardware', None]

    def test_a_missing_product_leaves_every_product_unchanged(self, catalog, products):
        with pytest.raises(ItemNotFoundError) as excinfo:
            catalog.set_category([products[0].id, products[1].id, 99999], 'tools')

        assert '99999' in excinfo.value.message
        assert _categories(catalog, products) == ['fasteners', 'hardware', None]

    def test_no_products_is_refused(self, catalog):
        with pytest.raises(ValidationError):
            catalog.set_category([], 'tools')


class TestRoute:
    def test_success_returns_the_count_and_flashes(self, client, catalog, products):
        response = client.post(URL, json={
            'product_ids': [products[0].id, products[1].id, products[1].id],
            'category_path': 'Tools/Hand',
        })

        assert response.status_code == 200
        assert response.get_json() == {
            'success': True, 'updated': 2, 'category_path': 'tools/hand'}
        assert _categories(catalog, products)[:2] == ['tools/hand', 'tools/hand']
        page = client.get('/products')
        assert 'Set category &#34;tools/hand&#34; on 2 products.' in page.get_data(as_text=True)

    @pytest.mark.parametrize('body', [
        None,
        [],
        {'category_path': 'x'},
        {'product_ids': [], 'category_path': 'x'},
        {'product_ids': ['1'], 'category_path': 'x'},
        {'product_ids': [True], 'category_path': 'x'},
        {'product_ids': [1]},
        {'product_ids': [1], 'category_path': 5},
    ])
    def test_malformed_body_is_400(self, client, products, body):
        response = client.post(URL, json=body)

        assert response.status_code == 400
        assert response.get_json()['success'] is False

    def test_blank_category_is_400(self, client, catalog, products):
        response = client.post(URL, json={
            'product_ids': [products[0].id], 'category_path': '  '})

        assert response.status_code == 400
        assert _categories(catalog, products)[0] == 'fasteners'

    def test_missing_product_is_404_and_nothing_changes(self, client, catalog, products):
        response = client.post(URL, json={
            'product_ids': [products[0].id, 99999], 'category_path': 'tools'})

        assert response.status_code == 404
        assert '99999' in response.get_json()['error']
        assert _categories(catalog, products)[0] == 'fasteners'


class TestPages:
    """Each page carries the button and the dialog (FR-001)."""

    def test_products_list(self, client, products):
        html = client.get('/products').get_data(as_text=True)

        assert 'id="bulk-category-btn"' in html
        assert 'id="bulkCategoryModal"' in html
        assert 'js/bulk-set-category.js' in html

    def test_order_page_and_outstanding(self, client, catalog, products):
        catalog.record_purchase(products[0].id, 'Shop A', vendor_item_id='W',
                                quantity=1, supplier_order_reference='A-1')
        for url in ('/products/orders/Shop A/A-1', '/products/outstanding'):
            html = client.get(url).get_data(as_text=True)

            assert 'id="bulk-category-btn"' in html, url
            assert 'id="bulkCategoryModal"' in html, url
            assert 'id="bulk-category-suggestions"' in html, url
            assert 'js/catalog-suggestions.js' in html, url
