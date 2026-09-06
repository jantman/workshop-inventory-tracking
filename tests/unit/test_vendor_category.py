"""
A vendor's category is not the shop's category (feature 040, issue #138).

``Product.category_path`` is free-form, and the browsable tree on
``/products/categories`` is built from the distinct values products actually
carry. There is no step at which a category is "created", so there is no step
at which a vendor's value could be reviewed before it becomes part of the
taxonomy: **writing the field is extending the tree**. That is why a value the
operator can override is not good enough here and is elsewhere -- the cost of
not noticing is paid on the categories page, not in the one record.

The order-capture and enrichment halves of the rule are asserted where those
paths are already tested (``test_digikey_capture.py``,
``test_order_enrichment.py``). This file covers the two *pages* that used to
hand DigiKey's category to the create form: the single-part capture page, which
posted it in a hidden input the operator could not see, and the Add Product
form a bag scan opens, which pre-loaded it into the visible box.
"""

import pytest

from app.catalog_service import CatalogService
from tests.unit.test_digikey_capture import (  # noqa: F401 -- fixtures
    catalog,
    digikey,
    include_all,
    order,
)

pytestmark = pytest.mark.unit

# What DigiKey files the recorded fixture part under. Not a path in anybody's
# shelves, which is the whole complaint.
DIGIKEY_CATEGORY = b'Power Supplies - Board Mount'


@pytest.fixture
def part_page(app, client, digikey_fixture_client):
    """The single-part capture page, having looked a part up."""
    app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
    response = client.post(
        '/products/digikey/part', data={'part_number': '1866-3027-ND'}
    )
    assert response.status_code == 200
    return response.data


class TestTheSinglePartCapturePage:

    def test_the_category_field_is_visible_and_empty(self, part_page):
        """040 FR-003, FR-004.

        One input, not hidden, no value. It used to be a hidden input named
        ``category_path`` carrying ``part.category_path`` -- the operator could
        neither see the value nor decline it.
        """
        html = part_page.decode()
        assert html.count('name="category_path"') == 1
        field = html[html.index('name="category_path"') - 200:
                     html.index('name="category_path"') + 200]
        assert 'type="hidden"' not in field
        assert 'value=""' in field

    def test_the_category_is_not_posted_as_the_vendors(self, part_page):
        """It must not reach the create form under any other name either."""
        html = part_page.decode()
        for line in html.splitlines():
            if 'input' in line and 'category' in line:
                assert DIGIKEY_CATEGORY.decode() not in line

    def test_digikeys_own_category_is_still_shown(self, part_page):
        """040 FR-005. Reading it and recording it are different acts.

        It stays in "What DigiKey says", a read-only block that posts nothing.
        """
        assert DIGIKEY_CATEGORY in part_page

    def test_the_field_carries_the_shops_own_suggestions(self, part_page):
        """The ids are a contract: catalog-suggestions.js fills them by id.

        A renamed id leaves a box that looks right and offers nothing, so the
        operator is handed a blank field with no vocabulary at the moment the
        vendor's is taken away.
        """
        html = part_page.decode()
        assert 'list="category-suggestions"' in html
        assert '<datalist id="category-suggestions">' in html
        assert 'catalog-suggestions.js' in html


class TestCreatingFromThatPage:

    def test_creating_without_typing_leaves_the_product_uncategorized(
        self, app, client, test_storage, digikey_fixture_client
    ):
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        client.post('/products/new', data={
            'description': 'AC/DC CONVERTER 5V 5W',
            'manufacturer': 'MEAN WELL USA Inc.',
            'manufacturer_part_number': 'IRM-05-5',
            'category_path': '',
            'identifier_type': 'MPN',
            'identifier_value': 'IRM-05-5',
        }, follow_redirects=True)

        product = CatalogService(test_storage).find_product_by_identifier(
            'IRM-05-5', id_type='MPN'
        )
        assert product is not None
        assert not product.category_path

    def test_a_category_the_operator_types_is_stored(
        self, app, client, test_storage, digikey_fixture_client
    ):
        """The field is the operator's; taking the vendor out does not take
        filing-at-capture-time away."""
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        client.post('/products/new', data={
            'description': 'AC/DC CONVERTER 5V 5W',
            'manufacturer_part_number': 'IRM-05-5',
            'category_path': 'electronics/power/power supplies',
            'identifier_type': 'MPN',
            'identifier_value': 'IRM-05-5',
        }, follow_redirects=True)

        product = CatalogService(test_storage).find_product_by_identifier(
            'IRM-05-5', id_type='MPN'
        )
        assert product.category_path == 'electronics/power/power supplies'


class TestTheFormAScanOpens:

    @pytest.fixture
    def scanned_form(self, app, client, digikey_fixture_client):
        """The Add Product form as a scanned bag opens it (024 FR-033)."""
        app.config['DIGIKEY_CLIENT'] = digikey_fixture_client
        response = client.get(
            '/products/new?identifier=IRM-05-5&id_type=MPN'
            '&distributor_part_number=1866-3027-ND'
        )
        assert response.status_code == 200
        return response.data.decode()

    def test_the_category_box_is_empty(self, scanned_form):
        """040 FR-010. Visible and editable is better than hidden, and still
        not good enough: a pre-loaded value that is simply accepted is how a
        vendor's vocabulary becomes a branch."""
        field = scanned_form[
            scanned_form.index('name="category_path"') - 300:
            scanned_form.index('name="category_path"') + 300
        ]
        assert 'value=""' in field
        assert DIGIKEY_CATEGORY.decode() not in field

    def test_everything_else_the_scan_yielded_is_still_pre_loaded(
        self, scanned_form
    ):
        """The rule is about the one field whose values are the taxonomy, not
        about pre-loading in general. FR-033 is untouched."""
        assert 'AC/DC CONVERTER 5V 5W' in scanned_form
        assert 'MEAN WELL USA Inc.' in scanned_form
        assert 'IRM-05-5' in scanned_form


class TestTheCategoryTree:
    """040 SC-001. The assertion the other tests are a proxy for.

    Every test above looks at a product's field. This one looks at the thing
    the field feeds, which is where the cost was actually being paid: the
    browsable tree is the union of the paths products carry and the branches
    the declared taxonomy names, so a stored vendor category is a branch nobody
    declared, sitting alongside the operator's own.
    """

    def test_a_capture_adds_no_branch(self, catalog, order, digikey):
        before = {entry['path'] for entry in catalog.category_tree()}

        catalog.capture_digikey_order(order, include_all(order), digikey)

        assert {entry['path'] for entry in catalog.category_tree()} == before

    def test_the_operators_own_branch_still_appears(self, catalog):
        """The tree is not being suppressed -- only the vendor is."""
        catalog.create_product(
            description='5V PSU',
            category_path='electronics/power/power supplies',
        )

        paths = {entry['path'] for entry in catalog.category_tree()}
        assert 'electronics/power/power supplies' in paths
