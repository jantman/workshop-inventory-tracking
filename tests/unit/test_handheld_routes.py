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

    def test_carries_the_stock_card_label_modal_and_attachments(self, client, service):
        """US2 (research.md D8, D9): the desktop Stock card and label modal, and
        the attachments markup product-attachments.js binds -- without the
        desktop's unconfirmed per-tile delete button."""
        product = service.create_product(description='Counted widget', quantity=5)

        html = client.get(f'/h/product/{product.id}').get_data(as_text=True)

        assert re.search(rf'id="stock-card"[^>]*data-product-id="{product.id}"', html)
        assert 'id="quantity-set-btn"' in html
        assert 'id="product-label-modal"' in html
        assert 'id="print-product-label-btn"' in html
        assert re.search(rf'id="attachments-card"[^>]*data-product-id="{product.id}"', html)
        assert 'id="product-attachment-input"' in html
        assert 'id="upload-product-attachment-btn"' in html
        assert 'delete-attachment-btn' not in html
        assert 'js/product-stock.js' in html
        assert 'js/product-label-modal.js' in html
        assert 'js/product-attachments.js' in html

    def test_move_opens_handheld_move_with_the_product(self, client, service):
        """US2 scenario 8 / FR-020"""
        product = service.create_product(description='Movable widget')

        html = client.get(f'/h/product/{product.id}').get_data(as_text=True)

        assert f'href="/h/move?kind=products&amp;code={product.internal_code}"' in html


class TestMove:
    @pytest.mark.parametrize('kind', ['items', 'products'])
    def test_renders_the_move_manager_markup(self, client, kind):
        response = client.get(f'/h/move?kind={kind}')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        barcode = re.search(r'<input[^>]*id="barcode-input"[^>]*>', html)
        assert barcode, 'no #barcode-input'
        assert 'data-handheld-scan' in barcode.group(0)
        assert 'inputmode="none"' in barcode.group(0)
        assert 'data-keyboard-for="barcode-input"' in html
        assert 'id="handheld-scan-input"' not in html
        assert '<tbody id="queue-items">' in html
        form = re.search(r'<form id="batch-move-form".*?</form>', html, re.S)
        assert form and 'name="csrf_token"' in form.group(0)
        for element_id in ('validate-btn', 'execute-moves-btn', 'manual-entry-mode',
                           'clear-all-btn', 'scanner-status', 'form-alerts'):
            assert f'id="{element_id}"' in html
        script = 'inventory-move.js' if kind == 'items' else 'product-move.js'
        assert f'js/{script}' in html

    @pytest.mark.parametrize('query', ['', '?kind=', '?kind=widgets'])
    def test_a_missing_or_unknown_kind_is_a_404(self, client, query):
        """``abort(404)``, which the app's 404 handler turns into a flash and a
        redirect for a page request -- the same response as any unknown URL."""
        unknown_page = client.get('/no-such-page')
        response = client.get(f'/h/move{query}')

        assert response.status_code == unknown_page.status_code == 302
        assert response.headers.get('Location') == unknown_page.headers.get('Location')

    def test_an_item_hand_off_is_preselected(self, client, test_storage):
        InventoryService(test_storage).add_item(InventoryItem(
            ja_id='JA000077', item_type='Bar', shape='Round', material='Steel',
            length=Decimal('1000'), width=Decimal('25'), location='M1-A', active=True,
        ))

        html = client.get('/h/move?kind=items&ja_id=JA000077').get_data(as_text=True)

        assert 'id="preselected-section"' in html
        assert '<tr data-id="JA000077">' in html

    def test_a_product_hand_off_is_preselected(self, client, service):
        product = service.create_product(description='Movable widget')

        html = client.get(
            f'/h/move?kind=products&code={product.internal_code}'
        ).get_data(as_text=True)

        assert 'id="preselected-section"' in html
        assert f'<tr data-id="{product.internal_code}">' in html
