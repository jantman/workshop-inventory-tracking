"""
Route tests for the handheld screens (feature 068), under ``/h/``.

Author: Jason Antman, 2026.
"""

import re

import pytest

from decimal import Decimal

from app.catalog_service import CatalogService
from app.database import InventoryItem
from app.mariadb_inventory_service import InventoryService


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


def _scan_input(html: str) -> str:
    match = re.search(r'<input[^>]*id="handheld-scan-input"[^>]*>', html)
    assert match, 'no #handheld-scan-input'
    return match.group(0)


class TestLanding:
    def test_renders_the_scan_entry_without_a_keyboard(self, client):
        response = client.get('/h/')

        assert response.status_code == 200
        scan_input = _scan_input(response.get_data(as_text=True))
        assert 'inputmode="none"' in scan_input
        assert 'data-scan-capture="handheld"' in scan_input
        assert 'data-handheld-scan' in scan_input

    def test_links_to_the_four_tasks(self, client):
        html = client.get('/h/').get_data(as_text=True)

        for href in ('/h/move?kind=items', '/h/move?kind=products', '/h/shorten', '/h/orders'):
            assert f'href="{href}"' in html

    def test_has_no_desktop_navbar_or_footer(self, client):
        html = client.get('/h/').get_data(as_text=True)

        assert 'id="global-scan-input"' not in html
        assert '<footer' not in html
        assert 'css/handheld.css' in html
        assert 'js/handheld.js' in html
        assert 'id="handheld-confirm-modal"' in html


class TestItem:
    def test_shows_the_ja_id(self, client, test_storage):
        InventoryService(test_storage).add_item(InventoryItem(
            ja_id='JA000042', item_type='Bar', shape='Round', material='Steel',
            length=Decimal('1000'), width=Decimal('25'), location='M1-A', active=True,
        ))

        response = client.get('/h/item/JA000042')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'JA000042' in html
        assert 'M1-A' in html

    def test_a_missing_ja_id_is_a_200_not_a_404(self, client):
        response = client.get('/h/item/JA999999')

        assert response.status_code == 200
        assert 'JA999999' in response.get_data(as_text=True)


class TestProduct:
    def test_shows_the_description_and_location(self, client, service):
        product = service.create_product(
            description='Blue widget, 10mm', location='Bin 7', sub_location='Drawer 2'
        )

        response = client.get(f'/h/product/{product.id}')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'Blue widget, 10mm' in html
        assert 'Bin 7' in html
        assert 'Drawer 2' in html

    def test_an_unknown_product_is_handled_as_on_desktop(self, client):
        """contracts/handheld-routes.md: the same ItemNotFoundError handling as
        the desktop route, through the centralized handler. For a page that is a
        flash and a redirect (test_product_routes.py asserts the same of
        /products/<id>), not a bare 404."""
        desktop = client.get('/products/999999')
        handheld = client.get('/h/product/999999')

        assert handheld.status_code == desktop.status_code
        assert handheld.headers.get('Location') == desktop.headers.get('Location')
