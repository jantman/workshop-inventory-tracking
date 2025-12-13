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


@pytest.mark.unit
class TestPhotoCopyAPI:
    """Test the POST /api/photos/copy endpoint for manual photo copying"""

    @pytest.fixture
    def mock_photo_service(self):
        """Mock PhotoService for testing"""
        with patch('app.photo_service.PhotoService') as mock:
            yield mock

    def test_copy_photos_success_single_target(self, client, mock_photo_service):
        """Test successful photo copy to single target item"""
        # Mock PhotoService context manager
        mock_service_instance = MagicMock()
        mock_photo_service.return_value.__enter__.return_value = mock_service_instance

        # Mock source has 3 photos
        mock_assoc1 = MagicMock()
        mock_assoc1.id = 1
        mock_assoc2 = MagicMock()
        mock_assoc2.id = 2
        mock_assoc3 = MagicMock()
        mock_assoc3.id = 3
        mock_service_instance.get_photos.return_value = [mock_assoc1, mock_assoc2, mock_assoc3]

        # Mock copy_photos returns 3
        mock_service_instance.copy_photos.return_value = 3

        response = client.post(
            '/api/photos/copy',
            json={
                'source_ja_id': 'JA000100',
                'target_ja_ids': ['JA000200']
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is True
        assert data['photos_copied'] == 3
        assert data['items_updated'] == 1
        assert len(data['details']) == 1
        assert data['details'][0]['ja_id'] == 'JA000200'
        assert data['details'][0]['photos_copied'] == 3
        assert data['details'][0]['success'] is True

        # Verify copy_photos was called
        mock_service_instance.copy_photos.assert_called_once_with('JA000100', 'JA000200')

    def test_copy_photos_success_multiple_targets(self, client, mock_photo_service):
        """Test successful photo copy to multiple target items"""
        mock_service_instance = MagicMock()
        mock_photo_service.return_value.__enter__.return_value = mock_service_instance

        # Mock source has 2 photos
        mock_assoc1 = MagicMock()
        mock_assoc2 = MagicMock()
        mock_service_instance.get_photos.return_value = [mock_assoc1, mock_assoc2]
        mock_service_instance.copy_photos.return_value = 2

        response = client.post(
            '/api/photos/copy',
            json={
                'source_ja_id': 'JA000100',
                'target_ja_ids': ['JA000200', 'JA000201', 'JA000202']
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is True
        assert data['photos_copied'] == 2
        assert data['items_updated'] == 3
        assert len(data['details']) == 3

        # All targets should have success
        for detail in data['details']:
            assert detail['success'] is True
            assert detail['photos_copied'] == 2

    def test_copy_photos_source_has_no_photos(self, client, mock_photo_service):
        """Test error when source item has no photos"""
        mock_service_instance = MagicMock()
        mock_photo_service.return_value.__enter__.return_value = mock_service_instance

        # Mock source has no photos
        mock_service_instance.get_photos.return_value = []

        response = client.post(
            '/api/photos/copy',
            json={
                'source_ja_id': 'JA000100',
                'target_ja_ids': ['JA000200']
            },
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.get_json()

        assert data['success'] is False
        assert 'no photos' in data['error'].lower()

    def test_copy_photos_missing_source_ja_id(self, client, mock_photo_service):
        """Test error when source_ja_id is missing"""
        response = client.post(
            '/api/photos/copy',
            json={
                'target_ja_ids': ['JA000200']
            },
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.get_json()

        assert data['success'] is False
        assert 'source_ja_id is required' in data['error']

    def test_copy_photos_missing_target_ja_ids(self, client, mock_photo_service):
        """Test error when target_ja_ids is missing"""
        response = client.post(
            '/api/photos/copy',
            json={
                'source_ja_id': 'JA000100'
            },
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.get_json()

        assert data['success'] is False
        assert 'target_ja_ids' in data['error']

    def test_copy_photos_empty_target_list(self, client, mock_photo_service):
        """Test error when target_ja_ids is empty"""
        response = client.post(
            '/api/photos/copy',
            json={
                'source_ja_id': 'JA000100',
                'target_ja_ids': []
            },
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.get_json()

        assert data['success'] is False
        assert 'target_ja_ids must be a non-empty list' in data['error']

    def test_copy_photos_invalid_json(self, client, mock_photo_service):
        """Test error when empty JSON object provided"""
        response = client.post(
            '/api/photos/copy',
            json={},
            content_type='application/json'
        )

        assert response.status_code == 400
        data = response.get_json()

        assert data['success'] is False
        # Empty JSON {} is treated as "no JSON data" by the if not data check
        assert 'no json data' in data['error'].lower() or 'source_ja_id is required' in data['error']

    def test_copy_photos_target_not_found(self, client, mock_photo_service):
        """Test handling when target item doesn't exist"""
        mock_service_instance = MagicMock()
        mock_photo_service.return_value.__enter__.return_value = mock_service_instance

        # Mock source has photos
        mock_assoc = MagicMock()
        mock_service_instance.get_photos.return_value = [mock_assoc]

        # Mock copy_photos raises ValueError for non-existent item
        mock_service_instance.copy_photos.side_effect = ValueError('Target item JA000999 not found')

        response = client.post(
            '/api/photos/copy',
            json={
                'source_ja_id': 'JA000100',
                'target_ja_ids': ['JA000999']
            },
            content_type='application/json'
        )

        assert response.status_code == 500
        data = response.get_json()

        assert data['success'] is False
        assert data['items_updated'] == 0
        assert len(data['details']) == 1
        assert data['details'][0]['success'] is False
        assert 'not found' in data['details'][0]['error'].lower()

    def test_copy_photos_partial_success(self, client, mock_photo_service):
        """Test partial success when some targets fail"""
        mock_service_instance = MagicMock()
        mock_photo_service.return_value.__enter__.return_value = mock_service_instance

        # Mock source has photos
        mock_assoc = MagicMock()
        mock_service_instance.get_photos.return_value = [mock_assoc]

        # First call succeeds, second fails
        mock_service_instance.copy_photos.side_effect = [
            1,  # Success for JA000200
            ValueError('Target item JA000999 not found')  # Fail for JA000999
        ]

        response = client.post(
            '/api/photos/copy',
            json={
                'source_ja_id': 'JA000100',
                'target_ja_ids': ['JA000200', 'JA000999']
            },
            content_type='application/json'
        )

        # Should return 207 Multi-Status for partial success
        assert response.status_code == 207
        data = response.get_json()

        assert data['success'] is False  # Not all succeeded
        assert data['items_updated'] == 1  # Only 1 succeeded
        assert len(data['details']) == 2

        # First target succeeded
        assert data['details'][0]['success'] is True
        assert data['details'][0]['ja_id'] == 'JA000200'

        # Second target failed
        assert data['details'][1]['success'] is False
        assert data['details'][1]['ja_id'] == 'JA000999'
        assert 'warning' in data


@pytest.mark.unit
class TestBatchMoveAPIWithSubLocation:
    """Test the POST /api/inventory/batch-move endpoint with sub-location support"""

    @pytest.fixture
    def setup_test_items(self, client, test_storage):
        """Create test items for batch move tests"""
        from app.mariadb_inventory_service import InventoryService
        from app.database import InventoryItem
        from app.models import ItemType, ItemShape

        service = InventoryService(test_storage)

        # Create test items with various location/sub-location combinations
        item1 = InventoryItem(
            ja_id='JA000001',
            item_type=ItemType.BAR.value,
            shape=ItemShape.ROUND.value,
            material='Steel',
            location='M1-A',
            sub_location=None
        )

        item2 = InventoryItem(
            ja_id='JA000002',
            item_type=ItemType.BAR.value,
            shape=ItemShape.ROUND.value,
            material='Steel',
            location='M2-B',
            sub_location='Drawer 1'
        )

        item3 = InventoryItem(
            ja_id='JA000003',
            item_type=ItemType.BAR.value,
            shape=ItemShape.ROUND.value,
            material='Steel',
            location='T-5',
            sub_location='Shelf 2'
        )

        service.add_item(item1)
        service.add_item(item2)
        service.add_item(item3)

        return service

    def test_move_with_sub_location_provided(self, client, setup_test_items):
        """Test moving an item with sub-location specified"""
        service = setup_test_items

        response = client.post(
            '/api/inventory/batch-move',
            json={
                'moves': [{
                    'ja_id': 'JA000001',
                    'new_location': 'M3-C',
                    'new_sub_location': 'Drawer 3'
                }]
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is True
        assert data['moved_count'] == 1
        assert data['total_count'] == 1

        # Verify item was updated correctly
        item = service.get_item('JA000001')
        assert item.location == 'M3-C'
        assert item.sub_location == 'Drawer 3'

    def test_move_without_sub_location_clears_existing(self, client, setup_test_items):
        """Test that moving without specifying sub-location clears existing sub-location"""
        service = setup_test_items

        # Item JA000002 has sub_location='Drawer 1'
        response = client.post(
            '/api/inventory/batch-move',
            json={
                'moves': [{
                    'ja_id': 'JA000002',
                    'new_location': 'M4-D'
                    # No new_sub_location specified
                }]
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is True
        assert data['moved_count'] == 1

        # Verify sub_location was cleared
        item = service.get_item('JA000002')
        assert item.location == 'M4-D'
        assert item.sub_location is None

    def test_move_with_empty_string_sub_location_clears(self, client, setup_test_items):
        """Test that empty string sub-location clears the field"""
        service = setup_test_items

        # Item JA000003 has sub_location='Shelf 2'
        response = client.post(
            '/api/inventory/batch-move',
            json={
                'moves': [{
                    'ja_id': 'JA000003',
                    'new_location': 'T-10',
                    'new_sub_location': ''  # Empty string should clear
                }]
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is True

        # Verify sub_location was cleared
        item = service.get_item('JA000003')
        assert item.location == 'T-10'
        assert item.sub_location is None

    def test_move_with_whitespace_only_sub_location_clears(self, client, setup_test_items):
        """Test that whitespace-only sub-location clears the field"""
        service = setup_test_items

        response = client.post(
            '/api/inventory/batch-move',
            json={
                'moves': [{
                    'ja_id': 'JA000002',
                    'new_location': 'M5-E',
                    'new_sub_location': '   '  # Whitespace only
                }]
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is True

        # Verify sub_location was cleared
        item = service.get_item('JA000002')
        assert item.sub_location is None

    def test_move_with_sub_location_strips_whitespace(self, client, setup_test_items):
        """Test that sub-location values are stripped of leading/trailing whitespace"""
        service = setup_test_items

        response = client.post(
            '/api/inventory/batch-move',
            json={
                'moves': [{
                    'ja_id': 'JA000001',
                    'new_location': 'M6-F',
                    'new_sub_location': '  Drawer 5  '
                }]
            },
            content_type='application/json'
        )

        assert response.status_code == 200

        # Verify sub_location was stripped
        item = service.get_item('JA000001')
        assert item.sub_location == 'Drawer 5'

    def test_batch_move_mixed_sub_locations(self, client, setup_test_items):
        """Test batch move with mixed sub-location scenarios"""
        service = setup_test_items

        response = client.post(
            '/api/inventory/batch-move',
            json={
                'moves': [
                    {
                        'ja_id': 'JA000001',
                        'new_location': 'M7-G',
                        'new_sub_location': 'Bin A'
                    },
                    {
                        'ja_id': 'JA000002',
                        'new_location': 'M8-H'
                        # No sub_location - should clear
                    },
                    {
                        'ja_id': 'JA000003',
                        'new_location': 'T-15',
                        'new_sub_location': 'Shelf 10'
                    }
                ]
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is True
        assert data['moved_count'] == 3
        assert data['total_count'] == 3

        # Verify all items
        item1 = service.get_item('JA000001')
        assert item1.location == 'M7-G'
        assert item1.sub_location == 'Bin A'

        item2 = service.get_item('JA000002')
        assert item2.location == 'M8-H'
        assert item2.sub_location is None

        item3 = service.get_item('JA000003')
        assert item3.location == 'T-15'
        assert item3.sub_location == 'Shelf 10'

    def test_move_nonexistent_item_with_sub_location(self, client, setup_test_items):
        """Test that moving a nonexistent item fails appropriately"""
        response = client.post(
            '/api/inventory/batch-move',
            json={
                'moves': [{
                    'ja_id': 'JA999999',
                    'new_location': 'M1-A',
                    'new_sub_location': 'Drawer 1'
                }]
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is False
        assert data['moved_count'] == 0
        assert len(data['failed_moves']) == 1
        assert data['failed_moves'][0]['ja_id'] == 'JA999999'
        assert 'not found' in data['failed_moves'][0]['error'].lower()

    def test_move_same_location_different_sub_location(self, client, setup_test_items):
        """Test moving to the same location but with different sub-location"""
        service = setup_test_items

        # Item JA000002 is at M2-B, Drawer 1
        response = client.post(
            '/api/inventory/batch-move',
            json={
                'moves': [{
                    'ja_id': 'JA000002',
                    'new_location': 'M2-B',  # Same location
                    'new_sub_location': 'Drawer 5'  # Different sub-location
                }]
            },
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()

        assert data['success'] is True

        # Verify only sub_location changed
        item = service.get_item('JA000002')
        assert item.location == 'M2-B'
        assert item.sub_location == 'Drawer 5'