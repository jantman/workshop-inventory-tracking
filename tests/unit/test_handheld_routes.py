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


def _flashes(client) -> list:
    with client.session_transaction() as session:
        return session.get('_flashes', [])


class TestReceive:
    """US6 (research.md D7): the desktop receipt's effects, a handheld screen."""

    def test_get_prefills_the_label_quantity(self, client, service):
        product = service.create_product(description='Rivets', quantity=4)
        purchase = service.record_purchase(product.id, vendor='McMaster-Carr', quantity=10,
                                           pack_size=5)

        response = client.get(f'/h/receive/{purchase.id}?quantity=3')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert re.search(r'<input[^>]*id="quantity"[^>]*value="3"', html)
        assert 'Rivets' in html
        assert 'Ordered 10, as packs of 5' in html
        assert 'id="counted"' in html
        assert 'id="handheld-receive-btn"' in html
        for field in ('description', 'unit_price', 'notes', 'received_date', 'csrf_token'):
            assert re.search(rf'<input type="hidden" name="{field}"', html), field

    def test_without_a_count_there_is_no_counted_choice(self, client, service):
        product = service.create_product(description='Untracked rivets')
        purchase = service.record_purchase(product.id, vendor='McMaster-Carr', quantity=10)

        html = client.get(f'/h/receive/{purchase.id}').get_data(as_text=True)

        assert re.search(r'<input[^>]*id="quantity"[^>]*value="10"', html)
        assert 'id="counted"' not in html

    def test_an_unknown_purchase_is_handled_as_on_desktop(self, client):
        desktop = client.get('/purchases/999999/receive')
        handheld = client.get('/h/receive/999999')

        assert handheld.status_code == desktop.status_code
        assert handheld.headers.get('Location') == desktop.headers.get('Location')

    def test_post_receives_and_returns_to_the_handheld_product(self, client, service):
        product = service.create_product(description='Rivets', quantity=4)
        purchase = service.record_purchase(product.id, vendor='McMaster-Carr', quantity=10)

        response = client.post(f'/h/receive/{purchase.id}', data={
            'quantity': '7', 'counted': 'on', 'description': 'Rivets',
            'unit_price': '', 'notes': '', 'received_date': '',
        })

        assert response.status_code == 302
        assert response.headers['Location'].endswith(f'/h/product/{product.id}')
        assert ('success', 'Received.') in _flashes(client)
        received = service.get_purchase(purchase.id)
        assert received.received_date is not None
        assert received.quantity == 7
        assert service.get_product(product.id).quantity == 11

    def test_a_refusal_re_renders_the_handheld_screen(self, client, service):
        product = service.create_product(description='Rivets')
        purchase = service.record_purchase(product.id, vendor='McMaster-Carr', quantity=10)

        response = client.post(f'/h/receive/{purchase.id}', data={
            'quantity': 'lots', 'description': 'Rivets',
        })

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'id="handheld-receive-form"' in html
        assert re.search(r'<input[^>]*id="quantity"[^>]*value="lots"', html)
        assert service.get_purchase(purchase.id).received_date is None

    def test_an_already_received_purchase_offers_no_receive(self, client, service):
        product = service.create_product(description='Rivets')
        purchase = service.record_purchase(product.id, vendor='McMaster-Carr', quantity=10)
        service.receive_purchase(purchase.id)

        html = client.get(f'/h/receive/{purchase.id}').get_data(as_text=True)

        assert 'id="handheld-already-received"' in html
        assert 'id="handheld-receive-btn"' not in html
        assert 'id="handheld-receive-form"' not in html


class TestReceiveChoose:
    PART = '97387A173'

    def test_lists_the_candidates_selecting_none(self, client, service):
        product = service.create_product(description='Rivets')
        first = service.record_purchase(product.id, vendor='McMaster-Carr',
                                        vendor_item_id=self.PART,
                                        supplier_order_reference='FIRST')
        second = service.record_purchase(product.id, vendor='McMaster-Carr',
                                         vendor_item_id=self.PART,
                                         supplier_order_reference='SECOND')

        html = client.get(f'/h/receive/choose?scan={self.PART}').get_data(as_text=True)

        for purchase in (first, second):
            assert f'href="/h/receive/{purchase.id}"' in html
        assert 'Order FIRST' in html and 'Order SECOND' in html
        assert not re.search(r'<input[^>]*\bchecked\b', html)

    def test_nothing_outstanding_says_so(self, client, service):
        product = service.create_product(description='Rivets')
        purchase = service.record_purchase(product.id, vendor='McMaster-Carr',
                                           vendor_item_id=self.PART)
        service.receive_purchase(purchase.id)

        html = client.get(f'/h/receive/choose?scan={self.PART}').get_data(as_text=True)

        assert 'id="nothing-outstanding"' in html
        assert 'receive-candidate' not in html
        # No product carries the part number, so it offers the desktop search.
        assert 'id="handheld-choice-search-link"' in html


def _order_line(service, product, order='ORD-1', vendor='DigiKey', **fields):
    return service.record_purchase(
        product.id, vendor=vendor, supplier_order_reference=order, quantity=2, **fields,
    )


class TestGroupOutstandingOrders:
    def test_groups_counts_and_skips_blank_references(self, service):
        from app.handheld.routes import group_outstanding_orders

        product = service.create_product(description='Widget')
        _order_line(service, product, order='OLD', vendor='DigiKey')
        _order_line(service, product, order='NEW', vendor='Amazon')
        _order_line(service, product, order='OLD', vendor='DigiKey')
        _order_line(service, product, order='  ', vendor='DigiKey')
        _order_line(service, product, order=None, vendor='DigiKey')
        # Same number, another vendor: another order.
        _order_line(service, product, order='OLD', vendor='Mouser')

        orders = group_outstanding_orders(service.find_outstanding_purchases())

        # Undated orders, so the service's sort fixes no order among them;
        # test_keeps_the_input_order covers the ordering.
        assert sorted((o.vendor, o.order_number, o.outstanding) for o in orders) == [
            ('Amazon', 'NEW', 1), ('DigiKey', 'OLD', 2), ('Mouser', 'OLD', 1),
        ]

    def test_keeps_the_input_order(self):
        from types import SimpleNamespace

        from app.handheld.routes import group_outstanding_orders

        lines = [
            SimpleNamespace(vendor='B', supplier_order_reference='2', order_date=None),
            SimpleNamespace(vendor='A', supplier_order_reference='1', order_date=None),
            SimpleNamespace(vendor='B', supplier_order_reference='2', order_date=None),
            SimpleNamespace(vendor='A', supplier_order_reference='', order_date=None),
        ]

        orders = group_outstanding_orders(lines)

        assert [(o.vendor, o.order_number, o.outstanding) for o in orders] == [
            ('B', '2', 2), ('A', '1', 1),
        ]


class TestOrders:
    def test_lists_only_orders_with_outstanding_lines(self, client, service):
        product = service.create_product(description='Widget')
        _order_line(service, product, order='OPEN-1')
        _order_line(service, product, order='OPEN-1')
        done = _order_line(service, product, order='DONE-1')
        service.receive_purchase(done.id)

        html = client.get('/h/orders').get_data(as_text=True)

        assert 'href="/h/orders/DigiKey/OPEN-1"' in html
        assert '2 outstanding' in html
        assert 'DONE-1' not in html

    def test_an_empty_list_says_so(self, client):
        html = client.get('/h/orders').get_data(as_text=True)

        assert 'id="handheld-no-orders"' in html


class TestOrder:
    def test_only_outstanding_lines_are_selectable(self, client, service):
        product = service.create_product(description='Widget')
        first = _order_line(service, product, vendor_item_id='P-1')
        second = _order_line(service, product, vendor_item_id='P-2')
        received = _order_line(service, product, vendor_item_id='P-3')
        service.receive_purchase(received.id)

        html = client.get('/h/orders/DigiKey/ORD-1?highlight=P-2').get_data(as_text=True)

        boxes = re.findall(r'name="purchase_id"\s+value="(\d+)"', html)
        assert sorted(boxes) == sorted([str(first.id), str(second.id)])
        assert not re.search(r'<input[^>]*\bchecked\b', html)
        assert re.search(r'handheld-highlight"\s+data-purchase="%d"' % second.id, html)
        assert 'id="handheld-order-receive-btn"' in html
        assert '2 of 3 outstanding' in html

    def test_an_unknown_order_is_a_200_saying_not_captured(self, client):
        response = client.get('/h/orders/DigiKey/NOPE-9')

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'No order NOPE-9 from DigiKey was captured' in html
        assert 'id="handheld-order-home-link"' in html
        assert 'id="handheld-order-receive-btn"' not in html

    def test_post_receives_exactly_the_posted_lines(self, client, service):
        product = service.create_product(description='Widget')
        lines = [_order_line(service, product, vendor_item_id=f'P-{n}') for n in range(3)]

        response = client.post('/h/orders/DigiKey/ORD-1/receive', data={
            'purchase_id': [str(lines[0].id), str(lines[2].id)],
        })

        assert response.status_code == 302
        assert response.headers['Location'].endswith('/h/orders/DigiKey/ORD-1')
        assert ('success', 'Received 2 line(s).') in _flashes(client)
        states = [service.get_purchase(line.id).received_date is not None for line in lines]
        assert states == [True, False, True]


class TestProductOutstanding:
    def test_offers_receive_for_each_outstanding_purchase(self, client, service):
        product = service.create_product(description='Widget')
        open_line = _order_line(service, product)
        done = _order_line(service, product)
        service.receive_purchase(done.id)

        html = client.get(f'/h/product/{product.id}').get_data(as_text=True)

        assert f'href="/h/receive/{open_line.id}"' in html
        assert f'href="/h/receive/{done.id}"' not in html

    def test_one_order_link_per_distinct_order(self, client, service):
        product = service.create_product(description='Widget')
        _order_line(service, product, order='ORD-1')
        _order_line(service, product, order='ORD-1')
        _order_line(service, product, order='ORD-2', vendor='Amazon')
        _order_line(service, product, order=None)

        html = client.get(f'/h/product/{product.id}').get_data(as_text=True)

        links = re.findall(r'class="[^"]*handheld-order-link[^"]*"\s+href="([^"]+)"', html)
        assert links == ['/h/orders/DigiKey/ORD-1', '/h/orders/Amazon/ORD-2']
        # Two orders: the action bar's button opens the choice between them.
        assert re.search(r'id="handheld-order-btn"\s+href="#handheld-product-outstanding"', html)

    def test_a_single_order_button_opens_it(self, client, service):
        product = service.create_product(description='Widget')
        _order_line(service, product, order='ORD-1')

        html = client.get(f'/h/product/{product.id}').get_data(as_text=True)

        assert re.search(r'id="handheld-order-btn"\s+href="/h/orders/DigiKey/ORD-1"', html)

    def test_nothing_outstanding_shows_no_order_button(self, client, service):
        product = service.create_product(description='Widget')

        html = client.get(f'/h/product/{product.id}').get_data(as_text=True)

        assert 'id="handheld-order-btn"' not in html
        assert 'id="handheld-product-outstanding"' not in html
