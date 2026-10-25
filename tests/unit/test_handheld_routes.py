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


def _add_item(test_storage, ja_id: str, **overrides) -> None:
    fields = dict(
        ja_id=ja_id, item_type='Bar', shape='Round', material='Steel',
        length=Decimal('1000'), width=Decimal('25'), location='M1-A', active=True,
    )
    fields.update(overrides)
    InventoryService(test_storage).add_item(InventoryItem(**fields))


class TestItem:
    def test_shows_the_summary(self, client, test_storage):
        """US4 / FR-010: type, shape, material, dimensions, length, location."""
        _add_item(test_storage, 'JA000042', item_type='Bar', shape='Rectangular',
                  material='6061-T6 Aluminum', width=Decimal('50.8'),
                  thickness=Decimal('12.7'), sub_location='Drawer 3')

        response = client.get('/h/item/JA000042')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'JA000042' in html
        for text in ('Bar', 'Rectangular', '6061-T6 Aluminum', 'Width 50.8',
                     'Thickness 12.7', 'Length 1000', 'M1-A', 'Drawer 3'):
            assert text in html, text
        # Wall thickness is empty, so it is not shown.
        assert 'Wall' not in html

    def test_offers_label_photos_shorten_and_move(self, client, test_storage):
        """US4 scenario 5 / FR-020: the hand-offs carry the JA ID."""
        _add_item(test_storage, 'JA000043')

        html = client.get('/h/item/JA000043').get_data(as_text=True)

        assert 'id="handheld-label-btn"' in html
        assert 'id="photo-manager-container"' in html
        assert 'href="#handheld-item-photos"' in html
        assert 'href="/h/shorten?ja_id=JA000043"' in html
        assert 'href="/h/move?kind=items&amp;ja_id=JA000043"' in html
        assert 'js/label-printing-modal.js' in html
        assert 'js/label-count.js' in html

    def test_a_missing_ja_id_is_a_200_with_a_desktop_link(self, client):
        """US4 scenario 6 (handheld-routes.md, "Error behavior")."""
        response = client.get('/h/item/JA999999')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'No item with this JA ID.' in html
        assert 'href="/inventory/edit/JA999999"' in html
        assert 'id="photo-manager-container"' not in html
        assert 'id="handheld-action-bar"' not in html

    def test_an_inactive_ja_id_is_a_200_with_a_desktop_link(self, client, test_storage):
        """US4 scenario 6 (handheld-routes.md, "Error behavior")."""
        _add_item(test_storage, 'JA000044', active=False)

        response = client.get('/h/item/JA000044')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'This item is inactive.' in html
        assert 'href="/inventory/edit/JA000044"' in html
        assert 'id="handheld-shorten-btn"' not in html


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


class TestShorten:
    def test_a_hand_off_prefills_the_scan_entry(self, client, test_storage):
        """US5: ``?ja_id=`` prefills #source-ja-id, the header scan entry."""
        _add_item(test_storage, 'JA000088')

        response = client.get('/h/shorten?ja_id=JA000088')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        source = re.search(r'<input[^>]*id="source-ja-id"[^>]*>', html, re.S)
        assert source, 'no #source-ja-id'
        assert 'value="JA000088"' in source.group(0)
        assert 'data-handheld-scan' in source.group(0)
        assert 'inputmode="none"' in source.group(0)
        assert 'form="shorten-form"' in source.group(0)
        assert 'data-keyboard-for="source-ja-id"' in html
        assert 'js/inventory-shorten.js' in html

    def test_carries_the_shorten_manager_markup(self, client):
        """contracts/controller-markup.md, InventoryShortenManager."""
        html = client.get('/h/shorten').get_data(as_text=True)

        form = re.search(r'<form id="shorten-form" method="POST">.*?</form>', html, re.S)
        assert form and 'name="csrf_token"' in form.group(0)
        for element_id in (
            'source-ja-id', 'new-length', 'cut-date', 'shortening-notes', 'confirm-operation',
            'scan-ja-id-btn', 'load-item-btn', 'clear-form-btn', 'execute-shortening-btn',
            'scanner-status', 'item-details', 'item-not-found', 'shortening-section',
            'notes-section', 'summary-section', 'history-section', 'length-validation',
            'length-validation-alert', 'item-display-name', 'item-material', 'item-type',
            'item-shape', 'current-length', 'item-location', 'item-status', 'summary-ja-id',
            'summary-current-length', 'summary-new-length', 'summary-removed-length',
            'form-alerts',
        ):
            assert html.count(f'id="{element_id}"') == 1, element_id
        # Outside the form, so they must name it.
        assert re.search(r'id="confirm-operation"[^>]*form="shorten-form"', html)
        assert re.search(r'id="execute-shortening-btn"[^>]*form="shorten-form"', html)

    def test_post_shortens_and_keeps_the_history_row(self, client, test_storage):
        """US5 scenario 2 / FR-013: the desktop handler, history retained."""
        _add_item(test_storage, 'JA000089')

        response = client.post('/h/shorten', data={
            'source_ja_id': 'JA000089', 'new_length': '600', 'confirm_operation': 'on',
        })

        assert response.status_code == 302
        assert response.headers['Location'].endswith('/h/shorten')
        service = InventoryService(test_storage)
        assert service.get_item('JA000089').length == Decimal('600')
        history = service.get_item_history('JA000089')
        assert len(history) == 2
        assert [row.active for row in history].count(True) == 1
        inactive = [row for row in history if not row.active]
        assert inactive[0].length == Decimal('1000')

    @pytest.mark.parametrize('new_length', ['1200', '1000', 'abc', ''])
    def test_an_invalid_or_longer_length_changes_nothing(self, client, test_storage, new_length):
        """US5 scenario 3: refused, and the item is untouched."""
        _add_item(test_storage, 'JA000090')

        response = client.post('/h/shorten', data={
            'source_ja_id': 'JA000090', 'new_length': new_length, 'confirm_operation': 'on',
        })

        assert response.status_code == 302
        assert response.headers['Location'].endswith('/h/shorten')
        service = InventoryService(test_storage)
        assert service.get_item('JA000090').length == Decimal('1000')
        assert len(service.get_item_history('JA000090')) == 1

    def test_unconfirmed_changes_nothing(self, client, test_storage):
        _add_item(test_storage, 'JA000091')

        client.post('/h/shorten', data={'source_ja_id': 'JA000091', 'new_length': '600'})

        assert InventoryService(test_storage).get_item('JA000091').length == Decimal('1000')
