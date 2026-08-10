"""
Route tests for reaching a product by the code printed on its label.

Covers GET /products/<product_code> -- 009 FR-015 through FR-018. The printed
code and the way back to the product become one fact instead of two.

TestExistingProductRoutesAreNotShadowed is the reason this file is worth its
length. A rule on `/products/<product_code>` shares a path shape with six
static pages, and if it ever outranked them the failure would surface somewhere
else entirely.
"""

import pytest

from app.catalog_service import CatalogService

# Static pages under /products that the new parameterized rule must not capture.
STATIC_PRODUCT_PATHS = [
    ('/products', 'product.product_search'),
    ('/products/new', 'product.product_new'),
    ('/products/capture', 'product.product_capture'),
    ('/products/reorder', 'product.product_reorder'),
    ('/products/categories', 'product.product_categories'),
    ('/products/tags', 'product.product_tags'),
]


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


class TestReachingAProductByItsCode:
    def test_the_printed_code_redirects_to_the_product(self, client, service):
        product = service.create_product(description='LM358 dual op-amp')

        response = client.get(f'/products/{product.internal_code}')

        assert response.status_code == 302
        assert response.headers['Location'].endswith(f'/products/{product.id}')

    def test_it_lands_on_the_product_when_followed(self, client, service):
        product = service.create_product(description='LM358 dual op-amp')

        response = client.get(
            f'/products/{product.internal_code}', follow_redirects=True
        )

        assert response.status_code == 200
        assert b'LM358 dual op-amp' in response.data

    def test_a_retyped_lowercase_code_reaches_the_same_product(self, client, service):
        """Crockford's alphabet exists so a scuffed label can be retyped"""
        product = service.create_product(description='Blue widget')

        response = client.get(f'/products/{product.internal_code.lower()}')

        assert response.status_code == 302
        assert response.headers['Location'].endswith(f'/products/{product.id}')

    @pytest.mark.parametrize(
        "encoded_suffix,label",
        [
            ('%20', 'a trailing space'),
            ('%0A', 'a trailing newline'),
            ('%09', 'a trailing tab'),
        ],
    )
    def test_trailing_whitespace_in_the_address_still_reaches_the_product(
        self, client, service, encoded_suffix, label
    ):
        """Raised in review on PR #82: is_internal_id() strips before matching,
        so a padded code passes validation -- does the lookup then miss it and
        report a real code as missing?

        It does not. find_product_by_identifier compares against value.strip(),
        so both halves canonicalize the same way and the product is found. The
        claim was worth checking and the behaviour is worth pinning, because the
        two strips are in different modules and nothing else says they agree.
        """
        product = service.create_product(description='Blue widget')

        response = client.get(f'/products/{product.internal_code}{encoded_suffix}')

        assert response.status_code == 302
        assert response.headers['Location'].endswith(f'/products/{product.id}')

    def test_a_well_formed_code_no_product_carries_is_reported_missing(
        self, client, service
    ):
        """009 FR-016 -- and by "the catalog's existing treatment" the spec
        means literally the same response an unknown record number produces,
        which for an HTML request is a flash and a redirect rather than a 404.
        Asserted as equivalence so the two cannot drift apart."""
        unknown_code = client.get('/products/WITZZZZZZZZZZ')
        unknown_id = client.get('/products/999999')

        assert unknown_code.status_code == unknown_id.status_code
        assert unknown_code.headers['Location'] == unknown_id.headers['Location']

    @pytest.mark.parametrize(
        "segment",
        [
            'WITSHORT',            # too few characters
            'WIT0123456789X',      # too many
            'WITI123456789',       # I is excluded from the alphabet
            'NOTACODE12345',       # wrong prefix
            'JA000123',            # an inventory item id, not a product code
        ],
    )
    def test_a_segment_that_is_not_a_code_never_reaches_a_product(
        self, client, service, segment
    ):
        product = service.create_product(description='Blue widget')

        response = client.get(f'/products/{segment}')

        # 009 FR-018: whatever else happens, it must not serve a product.
        assert response.status_code != 200
        assert not response.headers['Location'].endswith(f'/products/{product.id}')

    def test_the_json_form_of_a_missing_code_is_a_404(self, client, service):
        """The same handler answers an API caller with a status code"""
        response = client.get(
            '/products/WITZZZZZZZZZZ', headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 404

    def test_the_record_number_address_still_works(self, client, service):
        """009 FR-017: it stays canonical, and nothing that used it breaks"""
        product = service.create_product(description='Blue widget')

        response = client.get(f'/products/{product.id}')

        assert response.status_code == 200
        assert b'Blue widget' in response.data


class TestExistingProductRoutesAreNotShadowed:
    """009 FR-017. Werkzeug ranks argument-free rules above parameterized ones
    and the integer converter above the string one, so all of these keep their
    own handlers. Defined behaviour rather than luck -- but it would break
    silently, so it is pinned here."""

    @pytest.mark.parametrize("path,endpoint", STATIC_PRODUCT_PATHS)
    def test_a_static_page_still_reaches_its_own_handler(self, app, path, endpoint):
        matched, _ = app.url_map.bind('localhost').match(path)
        assert matched == endpoint

    @pytest.mark.parametrize("path,_endpoint", STATIC_PRODUCT_PATHS)
    def test_a_static_page_still_renders(self, client, path, _endpoint):
        assert client.get(path).status_code == 200

    def test_a_numeric_address_still_reaches_product_detail(self, app):
        """The int converter outranks the string one, so /products/42 is a record
        number and not a malformed code"""
        matched, args = app.url_map.bind('localhost').match('/products/42')
        assert matched == 'product.product_detail'
        assert args == {'product_id': 42}

    def test_a_code_shaped_address_reaches_the_new_handler(self, app):
        matched, args = app.url_map.bind('localhost').match('/products/WIT0123456789')
        assert matched == 'product.product_by_code'
        assert args == {'product_code': 'WIT0123456789'}
