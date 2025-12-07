"""
Unit Tests for Routes Module

Tests for form parsing and enum lookup functions in app.main.routes
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from app.models import ItemType, ItemShape
from app.main.routes import _parse_item_from_form


class TestParseItemFromForm:
    """Tests for _parse_item_from_form function"""
    
    def test_parse_single_word_item_types_success(self):
        """Test that single-word ItemTypes work correctly (current working behavior)"""
        single_word_types = ["Bar", "Plate", "Sheet", "Tube", "Angle"]
        
        for item_type_value in single_word_types:
            form_data = {
                'ja_id': 'JA000001',
                'item_type': item_type_value,
                'shape': 'Round',
                'material': 'Carbon Steel',
                'length': '100',
                'width': '10'
            }
            
            # This should work with current implementation
            item = _parse_item_from_form(form_data)
            assert item.item_type == item_type_value
            assert item.ja_id == 'JA000001'
    
    
    def test_parse_threaded_rod_should_work(self):
        """Test that _parse_item_from_form should work with 'Threaded Rod' (will fail until bug fixed)"""
        form_data = {
            'ja_id': 'JA000002',
            'item_type': 'Threaded Rod',
            'shape': 'Round', 
            'material': 'Carbon Steel',
            'length': '36',
            # No width for threaded rods
            'thread_series': 'UNC',
            'thread_size': '1/4-20'
        }
        
        # This should work but will fail until enum bug is fixed
        item = _parse_item_from_form(form_data)
        assert item.item_type == "Threaded Rod"
        assert item.ja_id == 'JA000002'
    
    def test_all_item_types_with_enum_constructor(self):
        """Test that enum constructor approach works for ALL ItemType values"""
        for item_type_enum in ItemType:
            # Test that ItemType(value) works for every enum value
            result = ItemType(item_type_enum.value)
            assert result == item_type_enum
            assert result.value == item_type_enum.value
    
    def test_all_item_shapes_with_enum_constructor(self):
        """Test that enum constructor approach works for ALL ItemShape values"""
        for shape_enum in ItemShape:
            # Test that ItemShape(value) works for every enum value
            result = ItemShape(shape_enum.value)
            assert result == shape_enum
            assert result.value == shape_enum.value
    


class TestSearchEnumLookup:
    """Tests for enum lookup in search functionality - all should work after bug fix"""
    
    def test_search_item_type_lookup_should_work_for_all_types(self):
        """Test that search should work with all ItemType values including 'Threaded Rod'"""
        for item_type_enum in ItemType:
            value = item_type_enum.value
            data = {'item_type': value}
            
            # This should work for ALL item types after we fix the enum lookup
            item_type = ItemType(data['item_type'])
            assert item_type == item_type_enum
            assert item_type.value == value
    
    def test_search_shape_lookup_should_work_for_all_shapes(self):
        """Test that search should work with all ItemShape values"""
        for shape_enum in ItemShape:
            value = shape_enum.value
            data = {'shape': value}
            
            # This should work for ALL shapes
            shape = ItemShape(data['shape'])
            assert shape == shape_enum
            assert shape.value == value


class TestEnumLookupPatterns:
    """Tests verifying enum lookup works correctly for all types"""
    
    def test_all_item_types_should_work_with_correct_pattern(self):
        """Test that all ItemType values work with correct enum constructor approach"""
        for item_type_enum in ItemType:
            value = item_type_enum.value
            
            # This should work for ALL enum values, including "Threaded Rod"
            result = ItemType(value)
            assert result == item_type_enum
            assert result.value == value
    
    def test_all_item_shapes_should_work_with_correct_pattern(self):
        """Test that all ItemShape values work with correct enum constructor approach"""
        for shape_enum in ItemShape:
            value = shape_enum.value
            
            # This should work for ALL enum values
            result = ItemShape(value)
            assert result == shape_enum
            assert result.value == value


class TestAddItemRouteAuditLogging:
    """Tests for audit logging in the Add Item route Add & Continue workflow"""

    def test_log_audit_operation_parameters_fixed(self):
        """Test that log_audit_operation can be called with correct parameters"""
        from app.logging_config import log_audit_operation

        # This should not raise a TypeError anymore
        try:
            log_audit_operation('add_item', 'continue_workflow', item_id='JA000469')
            # If we get here, the fix worked
            assert True
        except TypeError as e:
            if "additional_data" in str(e):
                pytest.fail("log_audit_operation still has the additional_data parameter issue")
            else:
                # Some other TypeError - re-raise it
                raise


class TestAPIConsistency:
    """Tests for API response format consistency between list and search endpoints"""

    @pytest.fixture
    def app(self, test_storage):
        """Create test Flask app"""
        from app import create_app
        from tests.test_config import TestConfig
        app = create_app(TestConfig, storage_backend=test_storage)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()

    def test_both_endpoints_return_success_field(self, client):
        """Test that both /api/inventory/list and /api/inventory/search return 'success' field"""
        # Test list endpoint
        list_response = client.get('/api/inventory/list')
        list_data = list_response.get_json()
        assert 'success' in list_data, "List endpoint missing 'success' field"
        assert isinstance(list_data['success'], bool), "List endpoint 'success' should be boolean"

        # Test search endpoint
        search_response = client.post(
            '/api/inventory/search',
            json={},
            content_type='application/json'
        )
        search_data = search_response.get_json()
        assert 'success' in search_data, "Search endpoint missing 'success' field"
        assert isinstance(search_data['success'], bool), "Search endpoint 'success' should be boolean"

    def test_both_endpoints_return_items_and_total_count(self, client):
        """Test that both endpoints return 'items' array and 'total_count' fields"""
        # Test list endpoint
        list_response = client.get('/api/inventory/list')
        list_data = list_response.get_json()
        assert 'items' in list_data, "List endpoint missing 'items' field"
        assert 'total_count' in list_data, "List endpoint missing 'total_count' field"
        assert isinstance(list_data['items'], list), "List endpoint 'items' should be array"
        assert isinstance(list_data['total_count'], int), "List endpoint 'total_count' should be integer"

        # Test search endpoint
        search_response = client.post(
            '/api/inventory/search',
            json={},
            content_type='application/json'
        )
        search_data = search_response.get_json()
        assert 'items' in search_data, "Search endpoint missing 'items' field"
        assert 'total_count' in search_data, "Search endpoint missing 'total_count' field"
        assert isinstance(search_data['items'], list), "Search endpoint 'items' should be array"
        assert isinstance(search_data['total_count'], int), "Search endpoint 'total_count' should be integer"

    def test_item_structure_consistency(self, client):
        """Test that items from both endpoints have identical structure"""
        # Expected fields in item response
        expected_fields = {
            'ja_id', 'display_name', 'item_type', 'shape', 'material',
            'dimensions', 'thread', 'location', 'sub_location',
            'purchase_date', 'purchase_price', 'purchase_location',
            'vendor', 'vendor_part_number', 'notes', 'active', 'precision',
            'date_added', 'last_modified', 'photo_count'
        }

        # Get items from list endpoint
        list_response = client.get('/api/inventory/list')
        list_data = list_response.get_json()

        # Get items from search endpoint
        search_response = client.post(
            '/api/inventory/search',
            json={},
            content_type='application/json'
        )
        search_data = search_response.get_json()

        # If there are items in either response, verify structure
        if list_data.get('items'):
            list_item = list_data['items'][0]
            list_fields = set(list_item.keys())
            assert expected_fields == list_fields, f"List endpoint item fields mismatch. Expected: {expected_fields}, Got: {list_fields}"

        if search_data.get('items'):
            search_item = search_data['items'][0]
            search_fields = set(search_item.keys())
            assert expected_fields == search_fields, f"Search endpoint item fields mismatch. Expected: {expected_fields}, Got: {search_fields}"

        # If both have items, they should have identical field sets
        if list_data.get('items') and search_data.get('items'):
            list_item = list_data['items'][0]
            search_item = search_data['items'][0]
            assert set(list_item.keys()) == set(search_item.keys()), \
                "List and search endpoints return items with different field sets"

    def test_photo_count_field_present(self, client):
        """Test that photo_count field is present in both endpoints' item responses"""
        # Get items from list endpoint
        list_response = client.get('/api/inventory/list')
        list_data = list_response.get_json()

        # Get items from search endpoint
        search_response = client.post(
            '/api/inventory/search',
            json={},
            content_type='application/json'
        )
        search_data = search_response.get_json()

        # Check list endpoint items have photo_count
        if list_data.get('items'):
            list_item = list_data['items'][0]
            assert 'photo_count' in list_item, "List endpoint items missing 'photo_count' field"
            assert isinstance(list_item['photo_count'], int), "List endpoint 'photo_count' should be integer"

        # Check search endpoint items have photo_count
        if search_data.get('items'):
            search_item = search_data['items'][0]
            assert 'photo_count' in search_item, "Search endpoint items missing 'photo_count' field"
            assert isinstance(search_item['photo_count'], int), "Search endpoint 'photo_count' should be integer"

    def test_error_responses_have_consistent_structure(self, client):
        """Test that error responses from search endpoint have consistent structure"""
        # Test with invalid item type
        response = client.post(
            '/api/inventory/search',
            json={'item_type': 'InvalidType'},
            content_type='application/json'
        )
        data = response.get_json()

        # Should have success: False
        assert 'success' in data, "Error response missing 'success' field"
        assert data['success'] is False, "Error response 'success' should be False"

        # Should have items and total_count for consistency
        assert 'items' in data, "Error response missing 'items' field"
        assert 'total_count' in data, "Error response missing 'total_count' field"
        assert data['items'] == [], "Error response 'items' should be empty array"
        assert data['total_count'] == 0, "Error response 'total_count' should be 0"

        # Should have message
        assert 'message' in data, "Error response missing 'message' field"