"""Reference lookup tools over MCP (070).

Author: Jason Antman, 2026.
"""

import pytest

from app.catalog_service import CatalogService
from app.services.label_printer import get_available_label_types
from app.taxonomy import type_shape_validator
from tests.unit.mcp_helpers import ok, seed_item, seed_materials


@pytest.mark.unit
class TestLookups:
    def test_label_types(self, client):
        assert ok(client, 'list_label_types') == {'label_types': get_available_label_types()}

    def test_materials(self, client, test_storage):
        seed_materials(test_storage, 'Steel', 'Brass')
        assert ok(client, 'list_materials') == {'materials': ['Brass', 'Steel']}

    def test_item_types_and_shapes(self, client):
        result = ok(client, 'list_item_types_and_shapes')
        assert 'Threaded Rod' in result['item_types']
        assert 'Round' in result['shapes']
        assert result['requirements'] == type_shape_validator.requirements_by_name()

    def test_locations_and_sub_locations(self, client, test_storage):
        seed_item(test_storage, 'JA000001', location='Rack A', sub_location='Top')
        seed_item(test_storage, 'JA000002', location='Rack B', sub_location='Bottom')
        CatalogService(test_storage).create_product(description='Widget', location='Cabinet')

        assert ok(client, 'list_locations') == {
            'field': 'location', 'values': ['Cabinet', 'Rack A', 'Rack B']}
        assert ok(client, 'list_locations', {'query': 'rack'})['values'] == ['Rack A', 'Rack B']
        assert ok(client, 'list_locations', {'location': 'Rack A'}) == {
            'field': 'sub_location', 'values': ['Top']}

    def test_product_categories(self, client, test_storage):
        service = CatalogService(test_storage)
        service.create_product(description='Widget', category_path='zz-test/widgets')
        result = ok(client, 'list_product_categories', {'prefix': 'zz-test'})
        assert result == {'categories': ['zz-test/widgets']}
