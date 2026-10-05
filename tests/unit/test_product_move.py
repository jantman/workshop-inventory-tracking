"""
Moving products by scanning (057): the service write, the two endpoints the
product Move page calls, the page itself and its ``?code=`` hand-off.
"""

import json
import re

import pytest

from app.catalog_service import CatalogService
from app.exceptions import ItemNotFoundError, ValidationError
from app.utils.handoff import NOT_FOUND, resolve_product_handoff

UNKNOWN_CODE = 'WIT0000000000'


@pytest.fixture
def service(test_storage):
    return CatalogService(test_storage)


@pytest.fixture
def located(service):
    return service.create_product(
        description='M3 nuts', location='M2', sub_location='Bin 4', notes='keep',
        manufacturer='Acme',
    )


@pytest.fixture
def unlocated(service):
    return service.create_product(description='Blue tape')


class TestMoveProduct:
    def test_gives_an_unlocated_product_a_location(self, service, unlocated):
        moved = service.move_product(unlocated.internal_code, 'M1-A', 'Drawer 3')
        assert (moved.location, moved.sub_location) == ('M1-A', 'Drawer 3')

    @pytest.mark.parametrize('sub', [None, '', '   '])
    def test_no_sub_location_clears_the_old_one(self, service, located, sub):
        moved = service.move_product(located.internal_code, 'T-3', sub)
        assert (moved.location, moved.sub_location) == ('T-3', None)

    def test_strips(self, service, located):
        moved = service.move_product(located.internal_code, '  T-3 ', ' Shelf A ')
        assert (moved.location, moved.sub_location) == ('T-3', 'Shelf A')

    def test_changes_nothing_else(self, service, located):
        moved = service.move_product(located.internal_code, 'T-3')
        assert moved.description == 'M3 nuts'
        assert moved.notes == 'keep'
        assert moved.manufacturer == 'Acme'
        assert moved.internal_code == located.internal_code

    def test_lower_case_code(self, service, located):
        moved = service.move_product(located.internal_code.lower(), 'T-3')
        assert moved.id == located.id

    @pytest.mark.parametrize('code', [UNKNOWN_CODE, 'banana', '', None])
    def test_unknown_code(self, service, code):
        with pytest.raises(ItemNotFoundError):
            service.move_product(code, 'M1')

    @pytest.mark.parametrize('location', ['', '   ', None])
    def test_blank_location_is_refused_and_nothing_changes(self, service, located, location):
        with pytest.raises(ValidationError):
            service.move_product(located.internal_code, location)
        assert service.get_product(located.id).location == 'M2'


class TestLookupByCode:
    def test_found(self, client, located):
        response = client.get(f'/api/products/by-code/{located.internal_code}')
        assert response.status_code == 200
        product = response.get_json()['product']
        assert product['internal_code'] == located.internal_code
        assert product['description'] == 'M3 nuts'
        assert (product['location'], product['sub_location']) == ('M2', 'Bin 4')

    def test_unset_location_is_null(self, client, unlocated):
        product = client.get(
            f'/api/products/by-code/{unlocated.internal_code}').get_json()['product']
        assert product['location'] is None

    def test_lower_case(self, client, located):
        response = client.get(f'/api/products/by-code/{located.internal_code.lower()}')
        assert response.status_code == 200

    @pytest.mark.parametrize('code', [UNKNOWN_CODE, 'banana', 'JA000001'])
    def test_not_found(self, client, code):
        response = client.get(f'/api/products/by-code/{code}')
        assert response.status_code == 404
        assert response.get_json()['success'] is False


class TestBatchMove:
    def post(self, client, moves):
        return client.post('/api/products/batch-move', json={'moves': moves})

    def test_moves_every_product(self, client, service, located, unlocated):
        response = self.post(client, [
            {'code': located.internal_code, 'new_location': 'T-3', 'new_sub_location': None},
            {'code': unlocated.internal_code, 'new_location': 'M1-A',
             'new_sub_location': 'Drawer 3'},
        ])
        assert response.status_code == 200
        assert response.get_json() == {
            'success': True, 'moved_count': 2, 'total_count': 2, 'failed_moves': [],
        }
        a, b = service.get_product(located.id), service.get_product(unlocated.id)
        assert (a.location, a.sub_location) == ('T-3', None)
        assert (b.location, b.sub_location) == ('M1-A', 'Drawer 3')

    def test_one_failure_does_not_stop_the_rest(self, client, service, located):
        response = self.post(client, [
            {'code': UNKNOWN_CODE, 'new_location': 'M1'},
            {'code': located.internal_code, 'new_location': 'M9'},
            {'code': located.internal_code, 'new_location': '  '},
            {'new_location': 'M1'},
        ])
        data = response.get_json()
        assert response.status_code == 200
        assert data['success'] is False
        assert data['moved_count'] == 1
        assert data['total_count'] == 4
        assert data['error'] == '3 items failed to move'
        assert data['failed_moves'] == [
            {'code': UNKNOWN_CODE, 'error': 'Product not found'},
            {'code': located.internal_code, 'error': 'Missing product code or location'},
            {'code': None, 'error': 'Missing product code or location'},
        ]
        assert service.get_product(located.id).location == 'M9'

    @pytest.mark.parametrize('body, message', [
        ({}, 'Invalid request data'),
        ({'moves': []}, 'No moves provided'),
        ({'moves': 'x'}, 'No moves provided'),
    ])
    def test_bad_body(self, client, body, message):
        response = client.post('/api/products/batch-move', json=body)
        assert response.status_code == 400
        assert response.get_json() == {'success': False, 'error': message}


def preselected(html):
    match = re.search(r"data-ids='([^']*)'", html)
    return json.loads(match.group(1)) if match else None


class TestMovePage:
    def test_renders_for_scanning(self, client):
        response = client.get('/products/move')
        html = response.data.decode()
        assert response.status_code == 200
        assert 'Batch Move Products' in html
        assert 'js/move-manager.js' in html
        assert 'js/product-move.js' in html
        assert 'preselected-section' not in html

    def test_is_in_the_products_menu(self, client):
        assert b'href="/products/move"' in client.get('/products').data

    def test_hand_off_preselects_the_product(self, client, located):
        html = client.get(f'/products/move?code={located.internal_code.lower()}').data.decode()
        assert preselected(html) == [located.internal_code]

    def test_hand_off_rejects_by_name(self, client):
        html = client.get(f'/products/move?code={UNKNOWN_CODE},banana').data.decode()
        assert preselected(html) == []
        assert 'id="rejected-items"' in html
        assert UNKNOWN_CODE in html and 'banana' in html

    def test_detail_page_links_to_it(self, client, located):
        html = client.get(f'/products/{located.id}').data.decode()
        assert f'/products/move?code={located.internal_code}' in html
        assert 'id="move-product-btn"' in html


class TestResolveProductHandoff:
    def test_none(self, service):
        handoff = resolve_product_handoff(None, service)
        assert not handoff.has_hand_off

    def test_accepts_and_rejects(self, service, located, unlocated):
        raw = f'{located.internal_code.lower()}, {UNKNOWN_CODE},{unlocated.internal_code},JA000001'
        handoff = resolve_product_handoff(raw, service)
        assert handoff.preselected_items == [located.internal_code, unlocated.internal_code]
        assert handoff.rejected_items == [
            {'id': UNKNOWN_CODE, 'reason': NOT_FOUND},
            {'id': 'JA000001', 'reason': NOT_FOUND},
        ]

    def test_case_variants_collapse(self, service, located):
        raw = f'{located.internal_code},{located.internal_code.lower()}'
        assert resolve_product_handoff(raw, service).preselected_items == [located.internal_code]
