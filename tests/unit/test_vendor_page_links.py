"""
Vendor links in the product page's Details panel (054, issue #180).

``vendor_page_links`` turns a product's vendor-scoped identifiers into links to
Amazon, McMaster-Carr and DigiKey; the product page renders them.
"""

from types import SimpleNamespace

import pytest

from app.catalog_service import CatalogService, vendor_page_links


def ident(id_type, value, vendor=''):
    return SimpleNamespace(id_type=id_type, value=value, vendor=vendor)


@pytest.fixture
def catalog(test_storage):
    return CatalogService(test_storage)


class TestVendorPageLinks:

    @pytest.mark.parametrize('vendor, id_type, value, url', [
        ('Amazon', 'VENDOR', 'B0EXAMPLE1', 'https://www.amazon.com/dp/B0EXAMPLE1'),
        ('McMaster-Carr', 'DISTRIBUTOR', '91251A540', 'https://www.mcmaster.com/91251A540/'),
        ('DigiKey', 'DISTRIBUTOR', '296-1395-5-ND',
         'https://www.digikey.com/en/products/result?keywords=296-1395-5-ND'),
    ])
    def test_each_vendor_links_to_the_address_in_the_issue(self, vendor, id_type, value, url):
        """FR-001, FR-002"""
        assert vendor_page_links([ident(id_type, value, vendor)]) == [(vendor, value, url)]

    @pytest.mark.parametrize('vendor', ['Amazon', 'McMaster-Carr', 'DigiKey'])
    @pytest.mark.parametrize('id_type', ['VENDOR', 'DISTRIBUTOR'])
    def test_either_vendor_scoped_type_links(self, vendor, id_type):
        """FR-003: legacy McMaster rows are VENDOR; page-captured DigiKey rows are too."""
        assert len(vendor_page_links([ident(id_type, 'X1', vendor)])) == 1

    def test_one_value_under_both_types_is_one_link(self):
        """FR-003"""
        links = vendor_page_links([
            ident('VENDOR', '91251A540', 'McMaster-Carr'),
            ident('DISTRIBUTOR', '91251A540', 'McMaster-Carr'),
        ])
        assert links == [('McMaster-Carr', '91251A540', 'https://www.mcmaster.com/91251A540/')]

    def test_the_value_is_encoded(self):
        """FR-006: a '/', '#' or space must not re-route the address."""
        [(_, _, amazon)] = vendor_page_links([ident('VENDOR', 'A/B#C D', 'Amazon')])
        [(_, _, digikey)] = vendor_page_links([ident('DISTRIBUTOR', 'X&Y?Z', 'DigiKey')])

        assert amazon == 'https://www.amazon.com/dp/A%2FB%23C%20D'
        assert digikey == 'https://www.digikey.com/en/products/result?keywords=X%26Y%3FZ'

    @pytest.mark.parametrize('identifier', [
        ident('MPN', 'LM358N'),
        ident('GTIN', '00012345678905'),
        ident('VENDOR', '12345', 'Mouser'),
        ident('DISTRIBUTOR', '296-1395-5-ND', 'Digi-Key'),
        ident('INTERNAL', 'W0000000001'),
    ])
    def test_nothing_else_links(self, identifier):
        """FR-007"""
        assert vendor_page_links([identifier]) == []

    def test_no_identifiers(self):
        assert vendor_page_links([]) == []

    def test_several_vendors_link_to_each_in_order(self):
        """US2"""
        links = vendor_page_links([
            ident('DISTRIBUTOR', '91251A540', 'McMaster-Carr'),
            ident('DISTRIBUTOR', '296-1395-5-ND', 'DigiKey'),
        ])
        assert [(vendor, value) for vendor, value, _ in links] == [
            ('DigiKey', '296-1395-5-ND'),
            ('McMaster-Carr', '91251A540'),
        ]

    def test_two_ids_for_one_vendor_are_two_links(self):
        """US2, FR-004"""
        links = vendor_page_links([
            ident('VENDOR', 'B0SECOND02', 'Amazon'),
            ident('VENDOR', 'B0FIRST001', 'Amazon'),
        ])
        assert [value for _, value, _ in links] == ['B0FIRST001', 'B0SECOND02']


class TestProductPage:

    def test_the_details_panel_links_to_the_vendor(self, catalog, client):
        """FR-001, FR-005"""
        product = catalog.create_product(
            description='Threadlocker',
            identifiers=[{'id_type': 'VENDOR', 'value': 'B0EXAMPLE1', 'vendor': 'Amazon'}],
        )

        html = client.get(f'/products/{product.id}').get_data(as_text=True)

        assert 'id="product-vendor-links"' in html
        assert 'href="https://www.amazon.com/dp/B0EXAMPLE1"' in html
        assert 'target="_blank"' in html
        assert 'rel="noopener" data-vendor="Amazon"' in html

    def test_a_product_with_nothing_to_link_has_no_row(self, catalog, client):
        """FR-007"""
        product = catalog.create_product(
            description='Op amp',
            identifiers=[{'id_type': 'MPN', 'value': 'LM358N'}],
        )

        html = client.get(f'/products/{product.id}').get_data(as_text=True)

        assert 'id="product-description"' in html
        assert 'product-vendor-links' not in html
        assert 'Vendor Pages' not in html
