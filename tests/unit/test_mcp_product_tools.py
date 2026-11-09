"""Product tools over MCP (070): reads, writes, counts, flags, moves, labels.

Author: Jason Antman, 2026.
"""

import pytest

from app.catalog_service import CatalogService
from tests.unit.mcp_helpers import fails, ok


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.mark.unit
class TestReads:
    def test_search_by_text_and_category(self, client, service):
        service.create_product(description='LM358 dual op-amp', category_path='electronics/ics')
        service.create_product(description='M3 socket head screw', category_path='hardware/screws')

        found = ok(client, 'search_products', {'query': 'op-amp'})
        assert [p['description'] for p in found['products']] == ['LM358 dual op-amp']
        assert found['total'] == 1
        assert found['products'][0]['code'].startswith('WIT')

        by_category = ok(client, 'search_products', {'category': 'hardware'})
        assert [p['description'] for p in by_category['products']] == ['M3 socket head screw']

    def test_search_by_identifier_and_paging(self, client, service):
        product = service.create_product(description='Widget')
        service.create_product(description='Gadget')
        found = ok(client, 'search_products', {'query': product.internal_code})
        assert [p['product_id'] for p in found['products']] == [product.id]

        page = ok(client, 'search_products', {'limit': 1})
        assert (page['total'], page['returned'], page['has_more']) == (2, 1, True)

    def test_get_by_code_and_by_id(self, client, service):
        product = service.create_product(description='Blue widget', quantity=4,
                                         tags=['blue'], identifiers=[{'id_type': 'MPN',
                                                                      'value': 'BW-1'}])
        by_code = ok(client, 'get_product', {'code': product.internal_code.lower()})['product']
        by_id = ok(client, 'get_product', {'product_id': product.id})['product']
        assert by_code == by_id
        assert by_code['quantity'] == 4
        assert by_code['quantity_tracked'] is True
        assert by_code['quantity_counted_at'] is not None
        assert by_code['tags'] == ['blue']
        assert {'type': 'MPN', 'value': 'BW-1', 'vendor': None} in by_code['identifiers']

    def test_get_needs_exactly_one_reference(self, client, service):
        product = service.create_product(description='Blue widget')
        assert 'exactly one' in fails(client, 'get_product', {})['error']
        assert 'exactly one' in fails(client, 'get_product', {
            'code': product.internal_code, 'product_id': product.id})['error']

    def test_get_not_found(self, client):
        error = fails(client, 'get_product', {'code': 'WIT0000000000'})['error']
        assert 'No product carries' in error
        assert 'not found' in fails(client, 'get_product', {'product_id': 999})['error']

    def test_reorder_list(self, client, service):
        low = service.create_product(description='Low one', quantity=1, reorder_threshold=2)
        flagged = service.create_product(description='Flagged one')
        service.set_stock_status(flagged.id, 'out')
        service.create_product(description='Plenty', quantity=50, reorder_threshold=2)

        entries = ok(client, 'get_reorder_list')['products']
        by_id = {e['product']['product_id']: e for e in entries}
        assert set(by_id) == {low.id, flagged.id}
        assert by_id[low.id]['reason'] == 'below reorder threshold'
        assert by_id[flagged.id]['reason'] == 'flagged out'
        assert by_id[low.id]['on_order'] is False
        assert by_id[low.id]['product']['code'] == low.internal_code


@pytest.mark.unit
class TestAddAndEdit:
    def test_add_returns_code(self, client, service):
        product = ok(client, 'add_product', {
            'description': 'Hex key set', 'manufacturer': 'Bondhus', 'location': 'Drawer 4',
            'sub_location': 'Front', 'quantity': 2, 'tags': ['tools'],
            'specifications': [{'name': 'Sizes', 'value': '1.5-10 mm'}],
            'identifiers': [{'type': 'MPN', 'value': '12199'}],
        })['product']
        assert product['code'].startswith('WIT')
        stored = service.get_product(product['product_id'])
        assert stored.sub_location == 'Front'
        assert stored.quantity == 2
        assert [s.value for s in stored.specifications] == ['1.5-10 mm']

    def test_add_without_description_writes_nothing(self, client, service):
        assert fails(client, 'add_product', {'description': '   '})['error']
        assert service.search_products() == []

    def test_edit_touches_only_supplied_fields(self, client, service):
        product = service.create_product(description='Widget', manufacturer='ACME',
                                         notes='keep', location='Shelf 1')
        result = ok(client, 'edit_product', {'code': product.internal_code,
                                             'description': 'Better widget',
                                             'location': None})['product']
        assert result['description'] == 'Better widget'
        stored = service.get_product(product.id)
        assert (stored.manufacturer, stored.notes, stored.location) == ('ACME', 'keep', None)

    def test_edit_refusal_writes_nothing(self, client, service):
        product = service.create_product(description='Widget')
        assert fails(client, 'edit_product', {'product_id': product.id, 'description': ''})
        assert service.get_product(product.id).description == 'Widget'


@pytest.mark.unit
class TestCategory:
    def test_sets_several_and_creates_the_category(self, client, service):
        one = service.create_product(description='One')
        two = service.create_product(description='Two')
        result = ok(client, 'set_product_category', {
            'products': [one.internal_code, two.id], 'category_path': 'brand/new/place'})
        assert result['category_path'] == 'brand/new/place'
        assert {p['category_path'] for p in result['products']} == {'brand/new/place'}
        assert 'brand/new/place' in ok(client, 'list_product_categories')['categories']

    def test_blank_is_refused_and_nothing_changes(self, client, service):
        one = service.create_product(description='One', category_path='old/path')
        assert fails(client, 'set_product_category', {'products': [one.id],
                                                      'category_path': '  '})['error']
        assert service.get_product(one.id).category_path == 'old/path'

    def test_unknown_product_changes_nothing(self, client, service):
        one = service.create_product(description='One', category_path='old/path')
        assert fails(client, 'set_product_category', {'products': [one.id, 999],
                                                      'category_path': 'new/path'})
        assert service.get_product(one.id).category_path == 'old/path'


@pytest.mark.unit
class TestCounts:
    def test_set_count_and_stop_tracking(self, client, service):
        product = service.create_product(description='Widget')
        counted = ok(client, 'set_product_count', {'product_id': product.id,
                                                   'quantity': 7})['product']
        assert counted['quantity'] == 7
        assert counted['quantity_counted_at'] is not None

        untracked = ok(client, 'set_product_count', {'product_id': product.id,
                                                     'quantity': None})['product']
        assert untracked['quantity'] is None
        assert untracked['quantity_tracked'] is False

    def test_negative_count_refused(self, client, service):
        product = service.create_product(description='Widget', quantity=3)
        assert fails(client, 'set_product_count', {'product_id': product.id, 'quantity': -1})
        assert service.get_product(product.id).quantity == 3

    def test_adjust_up_and_down_stamps_the_age(self, client, service):
        product = service.create_product(description='Widget', quantity=5)
        before = service.get_product(product.id).quantity_updated_at

        up = ok(client, 'adjust_product_count', {'code': product.internal_code, 'delta': 3})
        assert (up['previous_quantity'], up['product']['quantity']) == (5, 8)
        down = ok(client, 'adjust_product_count', {'code': product.internal_code, 'delta': -8})
        assert down['product']['quantity'] == 0
        assert service.get_product(product.id).quantity_updated_at >= before

    def test_adjust_refusals(self, client, service):
        untracked = service.create_product(description='Untracked')
        tracked = service.create_product(description='Tracked', quantity=2)
        assert 'not tracked' in fails(client, 'adjust_product_count',
                                      {'product_id': untracked.id, 'delta': 1})['error']
        assert 'below zero' in fails(client, 'adjust_product_count',
                                     {'product_id': tracked.id, 'delta': -3})['error']
        assert fails(client, 'adjust_product_count', {'product_id': tracked.id, 'delta': 0})
        assert service.get_product(tracked.id).quantity == 2
        assert service.get_product(untracked.id).quantity is None


@pytest.mark.unit
class TestFlag:
    def test_set_and_clear(self, client, service):
        product = service.create_product(description='Widget')
        flagged = ok(client, 'set_product_stock_flag', {'product_id': product.id,
                                                        'flag': 'low'})['product']
        assert flagged['stock_status'] == 'low'
        assert flagged['stock_status_set_at'] is not None
        cleared = ok(client, 'set_product_stock_flag', {'product_id': product.id,
                                                        'flag': None})['product']
        assert cleared['stock_status'] is None

    def test_bad_flag(self, client, service):
        product = service.create_product(description='Widget')
        assert 'flag' in fails(client, 'set_product_stock_flag', {'product_id': product.id,
                                                                  'flag': 'empty'})['error']


@pytest.mark.unit
class TestMoveProducts:
    def test_moves_and_reports_unknown(self, client, service):
        one = service.create_product(description='One', location='A', sub_location='Old')
        two = service.create_product(description='Two', location='B')
        result = ok(client, 'move_products', {
            'products': [one.internal_code.lower(), two.internal_code, 'WIT0000000000'],
            'location': 'Cabinet 2', 'sub_location': 'Drawer 1'})
        assert (result['moved'], result['total']) == (2, 3)
        assert result['failed'] == [{'code': 'WIT0000000000', 'error': 'Product not found'}]
        for product in (one, two):
            stored = service.get_product(product.id)
            assert (stored.location, stored.sub_location) == ('Cabinet 2', 'Drawer 1')

    def test_sub_location_cleared(self, client, service):
        one = service.create_product(description='One', location='A', sub_location='Old')
        ok(client, 'move_products', {'products': [one.internal_code], 'location': 'B'})
        assert service.get_product(one.id).sub_location is None


@pytest.mark.unit
class TestPrintProductLabels:
    @pytest.fixture
    def printed(self, monkeypatch):
        calls = []
        monkeypatch.setattr('app.services.product_label.print_product_label',
                            lambda **kwargs: calls.append(kwargs))
        return calls

    def test_prints_each(self, client, service, printed):
        one = service.create_product(description='One')
        two = service.create_product(description='Two')
        result = ok(client, 'print_product_labels', {
            'products': [one.internal_code, two.id, 999], 'label_type': 'Sato 2x4',
            'label_count': 2})
        assert result['printed'] == [one.internal_code, two.internal_code]
        assert result['failed'] == [{'code': 999, 'error': 'Product 999 not found'}]
        assert [(c['code'], c['num_copies']) for c in printed] == \
               [(one.internal_code, 2), (two.internal_code, 2)]

    def test_bad_label_type(self, client, service, printed):
        one = service.create_product(description='One')
        error = fails(client, 'print_product_labels', {'products': [one.id],
                                                       'label_type': 'Napkin'})['error']
        assert 'Available types' in error
        assert printed == []

    def test_printer_failure_reported(self, client, service, monkeypatch):
        def jammed(**kwargs):
            raise OSError('printer jammed')
        monkeypatch.setattr('app.services.product_label.print_product_label', jammed)
        one = service.create_product(description='One')
        error = fails(client, 'print_product_labels', {'products': [one.id],
                                                       'label_type': 'Sato 2x4'})['error']
        assert 'printer jammed' in error
