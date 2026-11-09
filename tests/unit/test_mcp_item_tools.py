"""Inventory item tools over MCP (070): reads, writes, parity with the web, labels.

Author: Jason Antman, 2026.
"""

from decimal import Decimal

import pytest

from app.mariadb_inventory_service import InventoryService
from tests.unit.mcp_helpers import fails, item_count, ok, seed_item, seed_materials

_STORED_FIELDS = (
    'item_type', 'shape', 'material', 'length', 'width', 'thickness', 'wall_thickness',
    'weight', 'thread_series', 'thread_handedness', 'thread_size', 'location',
    'sub_location', 'purchase_location', 'vendor', 'vendor_part', 'notes', 'precision',
    'active',
)


def _stored(storage, ja_id):
    item = InventoryService(storage).get_canonical_item(ja_id)
    assert item is not None, ja_id
    return item


@pytest.mark.unit
class TestSearchItems:
    @pytest.fixture(autouse=True)
    def _items(self, test_storage):
        seed_item(test_storage, 'JA000001', material='Steel', location='Rack A')
        seed_item(test_storage, 'JA000002', material='Aluminum', shape='Rectangular',
                  item_type='Plate', length=Decimal('12'), width=Decimal('6'),
                  thickness=Decimal('0.25'), location='Shelf 3')
        seed_item(test_storage, 'JA000003', material='Steel', length=Decimal('6'),
                  location='Rack B', active=False)

    def test_all_active_by_default(self, client):
        result = ok(client, 'search_items')
        assert sorted(i['ja_id'] for i in result['items']) == ['JA000001', 'JA000002']
        assert result['total'] == 2

    def test_include_inactive(self, client):
        result = ok(client, 'search_items', {'include_inactive': True})
        assert sorted(i['ja_id'] for i in result['items']) == ['JA000001', 'JA000002', 'JA000003']

    def test_filters(self, client):
        assert [i['ja_id'] for i in ok(client, 'search_items',
                                       {'material': 'Aluminum'})['items']] == ['JA000002']
        assert [i['ja_id'] for i in ok(client, 'search_items',
                                       {'location': 'rack'})['items']] == ['JA000001']
        assert [i['ja_id'] for i in ok(client, 'search_items',
                                       {'shape': 'Rectangular'})['items']] == ['JA000002']

    def test_dimension_range_takes_fractions(self, client):
        result = ok(client, 'search_items', {'thickness_min': '1/8', 'thickness_max': 0.5})
        assert [i['ja_id'] for i in result['items']] == ['JA000002']

    def test_bad_range_value(self, client):
        error = fails(client, 'search_items', {'length_min': 'long'})['error']
        assert 'length_min' in error

    def test_paging(self, client):
        first = ok(client, 'search_items', {'limit': 1})
        assert first['returned'] == 1
        assert first['total'] == 2
        assert first['has_more'] is True
        second = ok(client, 'search_items', {'limit': 1, 'offset': 1})
        assert second['has_more'] is False
        assert {first['items'][0]['ja_id'], second['items'][0]['ja_id']} == {'JA000001', 'JA000002'}

    def test_summary_shape(self, client):
        item = next(i for i in ok(client, 'search_items')['items'] if i['ja_id'] == 'JA000002')
        assert item['dimensions'] == {'length': '12', 'width': '6', 'thickness': '0.25',
                                      'wall_thickness': None, 'weight': None}
        assert item['active'] is True
        assert item['location'] == 'Shelf 3'


@pytest.mark.unit
class TestGetItem:
    def test_details_and_history_after_shortening(self, client, test_storage):
        seed_item(test_storage, 'JA000010', length=Decimal('36'))
        ok(client, 'shorten_item', {'ja_id': 'JA000010', 'new_length': '24 1/2'})

        result = ok(client, 'get_item', {'ja_id': 'ja000010'})
        assert result['item']['ja_id'] == 'JA000010'
        assert result['item']['dimensions']['length'] == '24.5'
        history = result['history']
        assert [row['active'] for row in history] == [False, True]
        assert history[0]['dimensions']['length'] == '36'
        assert history[1]['dimensions']['length'] == '24.5'

    def test_not_found(self, client):
        assert fails(client, 'get_item', {'ja_id': 'JA999999'})['error'] == 'Item JA999999 not found'


@pytest.mark.unit
class TestFindStock:
    def test_returns_fits(self, client, test_storage):
        seed_materials(test_storage, 'Steel')
        seed_item(test_storage, 'JA000020', length=Decimal('36'), width=Decimal('1'))
        seed_item(test_storage, 'JA000021', length=Decimal('2'), width=Decimal('1'))

        result = ok(client, 'find_stock', {'material': 'Steel', 'shape': 'Round',
                                           'diameter': '3/4', 'length': 12})
        assert [fit['item']['ja_id'] for fit in result['fits']] == ['JA000020']
        assert 'excess' in result['fits'][0]

    def test_missing_dimension(self, client):
        error = fails(client, 'find_stock', {'material': 'Steel', 'shape': 'Round',
                                             'length': 12})['error']
        assert 'required' in error


@pytest.mark.unit
class TestAddItems:
    def test_creates_quantity_items(self, client, test_storage):
        result = ok(client, 'add_items', {
            'item_type': 'Bar', 'shape': 'Round', 'material': 'Steel',
            'location': 'Rack A', 'length': '1 1/4', 'width': 0.375, 'quantity': 3,
        })
        assert result['created_ja_ids'] == ['JA000001', 'JA000002', 'JA000003']
        item = _stored(test_storage, 'JA000002')
        assert item.active is True
        assert item.dimensions.length == Decimal('1.25')
        assert item.dimensions.width == Decimal('0.375')

    def test_invalid_material_writes_nothing(self, client, test_storage):
        seed_materials(test_storage, 'Steel')
        result = fails(client, 'add_items', {
            'item_type': 'Bar', 'shape': 'Round', 'material': 'Unobtainium',
            'location': 'Rack A', 'length': '12', 'width': '1',
        })
        assert 'Unobtainium' in result['error']
        assert result['details'][0]['message'] == result['error']
        assert item_count(test_storage) == 0

    def test_missing_dimension_writes_nothing(self, client, test_storage):
        result = fails(client, 'add_items', {
            'item_type': 'Bar', 'shape': 'Round', 'material': 'Steel', 'location': 'Rack A',
            'length': '12',
        })
        assert result['error'].startswith('Missing required field(s) for Bar/Round')
        assert item_count(test_storage) == 0

    def test_missing_required_argument_writes_nothing(self, client, test_storage):
        error = fails(client, 'add_items', {'item_type': 'Bar', 'shape': 'Round',
                                            'material': 'Steel'})['error']
        assert 'location' in error
        assert item_count(test_storage) == 0

    def test_parity_with_the_json_api(self, client, test_storage):
        payload = {
            'item_type': 'Tube', 'shape': 'Round', 'material': 'Steel', 'location': 'Rack C',
            'sub_location': 'Top', 'length': '48', 'width': '1 1/2', 'wall_thickness': '0.065',
            'weight': '3.25', 'notes': 'DOM', 'vendor': 'Metals Depot',
            'vendor_part_number': 'T112065', 'purchase_location': 'Online', 'precision': True,
            'active': True,
        }
        web = client.post('/api/inventory/items', json=payload).get_json()
        assert web['success'] is True
        tool = ok(client, 'add_items', payload)

        web_item = _stored(test_storage, web['created_ja_ids'][0])
        tool_item = _stored(test_storage, tool['created_ja_ids'][0])
        for field in _STORED_FIELDS:
            assert getattr(tool_item, field) == getattr(web_item, field), field


@pytest.mark.unit
class TestEditItem:
    def test_changes_only_supplied_fields(self, client, test_storage):
        seed_item(test_storage, 'JA000030', length=Decimal('36'), width=Decimal('1'),
                  location='Rack A', sub_location='Left', notes='keep me', vendor='ACME')

        result = ok(client, 'edit_item', {'ja_id': 'JA000030', 'width': '1 1/4',
                                          'sub_location': None})
        assert set(result['changed_fields']) == {'dimensions', 'sub_location'}
        assert result['item']['dimensions']['width'] == '1.25'

        item = _stored(test_storage, 'JA000030')
        assert item.dimensions.width == Decimal('1.25')
        assert item.dimensions.length == Decimal('36')
        assert item.sub_location is None
        assert item.notes == 'keep me'
        assert item.vendor == 'ACME'
        assert item.location == 'Rack A'
        assert item.active is True

    def test_deactivate(self, client, test_storage):
        seed_item(test_storage, 'JA000031')
        ok(client, 'edit_item', {'ja_id': 'JA000031', 'active': False})
        assert _stored(test_storage, 'JA000031').active is False

    def test_invalid_material_writes_nothing(self, client, test_storage):
        seed_materials(test_storage, 'Steel')
        seed_item(test_storage, 'JA000032')
        error = fails(client, 'edit_item', {'ja_id': 'JA000032',
                                            'material': 'Unobtainium'})['error']
        assert 'Unobtainium' in error
        assert _stored(test_storage, 'JA000032').material == 'Steel'

    def test_clearing_a_required_dimension_is_refused(self, client, test_storage):
        seed_item(test_storage, 'JA000033')
        error = fails(client, 'edit_item', {'ja_id': 'JA000033', 'width': None})['error']
        assert 'Missing required field' in error
        assert _stored(test_storage, 'JA000033').dimensions.width == Decimal('1')

    def test_parity_with_the_edit_page(self, client, test_storage):
        seed_item(test_storage, 'JA000034', notes='old')
        seed_item(test_storage, 'JA000035', notes='old')

        from app.main.routes import _item_to_form_data
        form = _item_to_form_data(_stored(test_storage, 'JA000034'))
        form.update({'notes': 'new notes', 'length': '30 1/8'})
        response = client.post('/inventory/edit/JA000034', data=form)
        assert response.status_code == 302

        ok(client, 'edit_item', {'ja_id': 'JA000035', 'notes': 'new notes',
                                 'length': '30 1/8'})
        web_item = _stored(test_storage, 'JA000034')
        tool_item = _stored(test_storage, 'JA000035')
        for field in _STORED_FIELDS:
            assert getattr(tool_item, field) == getattr(web_item, field), field
        assert tool_item.dimensions.length == Decimal('30.125')

    def test_not_found(self, client):
        assert 'not found' in fails(client, 'edit_item', {'ja_id': 'JA000999',
                                                          'notes': 'x'})['error']


@pytest.mark.unit
class TestShortenItem:
    def test_keeps_one_active_row_and_history(self, client, test_storage):
        seed_item(test_storage, 'JA000040', length=Decimal('36'))
        result = ok(client, 'shorten_item', {'ja_id': 'JA000040', 'new_length': 30,
                                             'cut_date': '2026-11-01', 'notes': 'cut for bracket'})
        assert result == {'ja_id': 'JA000040', 'original_length': '36', 'new_length': '30'}

        history = InventoryService(test_storage).get_item_history('JA000040')
        assert len(history) == 2
        assert [row.active for row in history].count(True) == 1
        assert history[0].dimensions.length == Decimal('36')
        assert 'cut for bracket' in history[-1].notes

    def test_longer_length_is_refused(self, client, test_storage):
        seed_item(test_storage, 'JA000041', length=Decimal('36'))
        result = fails(client, 'shorten_item', {'ja_id': 'JA000041', 'new_length': '40'})
        assert result['error']
        assert len(InventoryService(test_storage).get_item_history('JA000041')) == 1

    def test_parity_with_the_shorten_page(self, client, test_storage):
        seed_item(test_storage, 'JA000042', length=Decimal('36'))
        seed_item(test_storage, 'JA000043', length=Decimal('36'))
        client.post('/inventory/shorten', data={'source_ja_id': 'JA000042', 'new_length': '20.5',
                                                'confirm_operation': 'on'})
        ok(client, 'shorten_item', {'ja_id': 'JA000043', 'new_length': '20 1/2'})

        service = InventoryService(test_storage)
        web_rows = service.get_item_history('JA000042')
        tool_rows = service.get_item_history('JA000043')
        assert [(r.active, r.dimensions.length) for r in web_rows] == \
               [(r.active, r.dimensions.length) for r in tool_rows]


@pytest.mark.unit
class TestMoveItems:
    def test_moves_and_reports_unknown(self, client, test_storage):
        seed_item(test_storage, 'JA000050', location='Rack A', sub_location='Left')
        seed_item(test_storage, 'JA000051', location='Rack B')

        result = ok(client, 'move_items', {'ja_ids': ['ja000050', 'JA000051', 'JA000999'],
                                           'location': 'Rack Z', 'sub_location': 'Bin 2'})
        assert result['moved'] == 2
        assert result['total'] == 3
        assert result['failed'] == [{'ja_id': 'JA000999', 'error': 'Item not found'}]
        for ja_id in ('JA000050', 'JA000051'):
            item = _stored(test_storage, ja_id)
            assert (item.location, item.sub_location) == ('Rack Z', 'Bin 2')

    def test_sub_location_cleared_when_not_given(self, client, test_storage):
        seed_item(test_storage, 'JA000052', location='Rack A', sub_location='Left')
        ok(client, 'move_items', {'ja_ids': ['JA000052'], 'location': 'Rack Q'})
        item = _stored(test_storage, 'JA000052')
        assert (item.location, item.sub_location) == ('Rack Q', None)

    def test_nothing_moved_is_an_error(self, client):
        result = fails(client, 'move_items', {'ja_ids': ['JA000999'], 'location': 'Rack Q'})
        assert result['details']['failed'][0]['ja_id'] == 'JA000999'


@pytest.mark.unit
class TestPrintItemLabels:
    @pytest.fixture
    def printed(self, monkeypatch):
        calls = []
        monkeypatch.setattr('app.services.label_printer.print_label_for_ja_id',
                            lambda ja_id, label_type, label_count: calls.append(
                                (ja_id, label_type, label_count)))
        return calls

    def test_prints_each(self, client, test_storage, printed):
        seed_item(test_storage, 'JA000060')
        seed_item(test_storage, 'JA000061')
        result = ok(client, 'print_item_labels', {'ja_ids': ['JA000060', 'JA000061', 'JA000999'],
                                                  'label_type': 'Sato 1x2', 'label_count': 3})
        assert result['printed'] == ['JA000060', 'JA000061']
        assert result['failed'] == [{'ja_id': 'JA000999', 'error': 'Item JA000999 not found'}]
        assert printed == [('JA000060', 'Sato 1x2', 3), ('JA000061', 'Sato 1x2', 3)]

    def test_bad_label_type_lists_valid_types(self, client, test_storage, printed):
        seed_item(test_storage, 'JA000062')
        error = fails(client, 'print_item_labels', {'ja_ids': ['JA000062'],
                                                    'label_type': 'Napkin'})['error']
        assert 'Available types' in error
        assert 'Sato 1x2' in error
        assert printed == []

    def test_count_out_of_range(self, client, test_storage, printed):
        seed_item(test_storage, 'JA000063')
        assert fails(client, 'print_item_labels', {'ja_ids': ['JA000063'],
                                                   'label_type': 'Sato 1x2',
                                                   'label_count': 100})
        assert printed == []
