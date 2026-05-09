"""
Unit tests for InventoryService class.

Tests the database-backed inventory service implementation.
"""

import pytest
from decimal import Decimal
from app.mariadb_inventory_service import SearchFilter
from app.mariadb_inventory_service import InventoryService
from app.models import ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
from app.database import InventoryItem


class TestSearchFilter:
    """Tests for SearchFilter class"""
    
    @pytest.mark.unit
    def test_search_filter_creation(self):
        """Test basic search filter creation"""
        search_filter = SearchFilter()
        
        assert search_filter.filters == {}
        assert search_filter.ranges == {}
        assert search_filter.text_searches == {}
    
    @pytest.mark.unit
    def test_add_exact_match(self):
        """Test adding exact match filter"""
        search_filter = SearchFilter()
        result = search_filter.add_exact_match('material', 'Steel')
        
        assert result is search_filter  # Should return self for chaining
        assert search_filter.filters['material'] == 'Steel'
    
    @pytest.mark.unit
    def test_add_range_filter(self):
        """Test adding range filter"""
        search_filter = SearchFilter()
        result = search_filter.add_range('length', Decimal('100'), Decimal('500'))
        
        assert result is search_filter
        assert search_filter.ranges['length'] == {'min': Decimal('100'), 'max': Decimal('500')}
    
    @pytest.mark.unit
    def test_add_text_search(self):
        """Test adding text search filter"""
        search_filter = SearchFilter()
        result = search_filter.add_text_search('notes', 'important', exact=False)
        
        assert result is search_filter
        assert search_filter.text_searches['notes'] == {'query': 'important', 'exact': False}
    
    @pytest.mark.unit
    def test_convenience_methods(self):
        """Test convenience filter methods"""
        search_filter = SearchFilter()
        
        # Test chaining
        result = (search_filter
                 .active_only()
                 .material('Steel')
                 .item_type(ItemType.BAR)
                 .shape(ItemShape.ROUND)
                 .location('Storage A')
                 .length_range(Decimal('100'), Decimal('500'))
                 .notes_contain('test'))
        
        assert result is search_filter
        assert search_filter.filters['active'] is True
        assert search_filter.text_searches['material']['query'] == 'Steel'
        assert search_filter.text_searches['material']['exact'] is True
        assert search_filter.filters['item_type'] == 'Bar'
        assert search_filter.filters['shape'] == 'Round'
        assert search_filter.filters['location'] == 'Storage A'
        assert 'length' in search_filter.ranges
        assert search_filter.text_searches['notes']['query'] == 'test'


class TestInventoryService:
    """Tests for InventoryService class"""
    
    @pytest.fixture
    def service(self, test_storage, app):
        """Create inventory service with test storage (app provides Flask context)"""
        # InventoryService doesn't use batching or caching, reads directly from database
        service = InventoryService(test_storage)
        
        yield service
    
    @pytest.fixture
    def sample_item(self):
        """Create a sample item for testing"""
        return InventoryItem(
            ja_id='JA000001',
            item_type='Bar',  # Store as string
            shape='Round',    # Store as string
            material='Steel',
            length=1000,      # Store as float
            width=25,         # Store as float
            location='Storage A',
            notes='Test item',
            active=True,
            precision=False
        )
    
    @pytest.fixture
    def sample_threaded_item(self):
        """Create a sample threaded item for testing"""
        return InventoryItem(
            ja_id='JA000002',
            item_type='Threaded Rod',  # Store as string
            shape='Round',             # Store as string
            material='Stainless Steel',
            length=500,                # Store as float
            width=12,                  # Store as float
            thread_series='METRIC',    # Store thread info as separate fields
            thread_handedness='RH',
            thread_size='M12x1.5',
            location='Storage B',
            notes='M12 threaded rod',
            active=True,
            precision=False
        )
    
    @pytest.mark.unit
    def test_service_creation(self, test_storage):
        """Test inventory service creation"""
        service = InventoryService(test_storage)
        
        assert service.storage is test_storage
        assert service._cache == {}
        assert service._cache_timestamp is None
    
    @pytest.mark.unit
    def test_add_item(self, service, sample_item):
        """Test adding an item to inventory"""
        result = service.add_item(sample_item)
        assert result is True
        
        # Verify item was added to storage
        storage_result = service.storage.read_all('Metal')
        assert storage_result.success
        assert len(storage_result.data) == 2  # Headers + 1 data row
        
        # Verify data format (data[0] is headers, data[1] is first item)
        row = storage_result.data[1]
        assert row[0] == 'JA000001'  # JA ID (column 0)
        assert row[1] == 'Bar'      # Type (column 1) 
        assert row[2] == 'Round'    # Shape (column 2)
        assert row[3] == 'Steel'    # Material (column 3)
    
    @pytest.mark.unit
    def test_get_item(self, service, sample_item):
        """Test retrieving an item by JA_ID"""
        # Add item first
        service.add_item(sample_item)
        
        # Retrieve item
        retrieved_item = service.get_item('JA000001')
        
        assert retrieved_item is not None
        assert retrieved_item.ja_id == 'JA000001'
        assert retrieved_item.material == 'Steel'
        assert retrieved_item.item_type == 'Bar'  # InventoryItem stores as string
    
    @pytest.mark.unit
    def test_get_item_not_found(self, service):
        """Test retrieving non-existent item"""
        item = service.get_item('NONEXISTENT')
        
        assert item is None
    
    @pytest.mark.unit
    def test_get_all_items(self, service, sample_item, sample_threaded_item):
        """Test retrieving all items"""
        # Add multiple items
        service.add_item(sample_item)
        service.add_item(sample_threaded_item)
        
        # Get all items
        items = service.get_all_items()
        
        assert len(items) == 2
        ja_ids = [item.ja_id for item in items]
        assert 'JA000001' in ja_ids
        assert 'JA000002' in ja_ids
    
    @pytest.mark.unit
    def test_update_item(self, service, sample_item):
        """Test updating an existing item"""
        # Add item first
        service.add_item(sample_item)
        
        # Update item
        sample_item.location = 'Updated Location'
        sample_item.notes = 'Updated notes'
        
        result = service.update_item(sample_item)
        
        assert result is True
        
        # Verify update
        updated_item = service.get_item('JA000001')
        assert updated_item.location == 'Updated Location'
        assert updated_item.notes == 'Updated notes'
    
    @pytest.mark.unit
    def test_deactivate_item(self, service, sample_item):
        """Test deactivating an item"""
        # Add item first
        service.add_item(sample_item)
        
        # Deactivate item
        result = service.deactivate_item('JA000001')
        
        assert result is True
        
        # Verify deactivation - get_item returns None for inactive items
        item = service.get_item('JA000001')
        assert item is None
        
        # Verify item exists but is inactive in history
        history = service.get_item_history('JA000001')
        assert len(history) >= 1
        most_recent = history[-1]  # Last item in history should be the deactivated one
        assert most_recent.active is False
    
    @pytest.mark.unit
    def test_activate_item(self, service, sample_item):
        """Test activating an item"""
        # Add and deactivate item first
        service.add_item(sample_item)
        service.deactivate_item('JA000001')
        
        # Activate item
        result = service.activate_item('JA000001')
        
        assert result is True
        
        # Verify activation
        item = service.get_item('JA000001')
        assert item.active is True
    
    @pytest.mark.unit
    def test_search_items_by_material(self, service, sample_item, sample_threaded_item):
        """Test searching items by material"""
        # Add items with different materials
        service.add_item(sample_item)      # Steel
        service.add_item(sample_threaded_item)  # Stainless Steel
        
        # Search for Steel items
        search_filter = SearchFilter().material('Steel')
        results = service.search_items(search_filter)
        
        assert len(results) == 1
        assert results[0].ja_id == 'JA000001'
        assert results[0].material == 'Steel'
    
    @pytest.mark.unit
    def test_search_items_by_type(self, service, sample_item, sample_threaded_item):
        """Test searching items by type"""
        service.add_item(sample_item)
        service.add_item(sample_threaded_item)
        
        # Search for threaded rods
        search_filter = SearchFilter().item_type(ItemType.THREADED_ROD)
        results = service.search_items(search_filter)
        
        assert len(results) == 1
        assert results[0].ja_id == 'JA000002'
        assert results[0].item_type == 'Threaded Rod'  # InventoryItem stores as string
    
    @pytest.mark.unit
    def test_search_items_active_only(self, service, sample_item, sample_threaded_item):
        """Test searching for active items only"""
        service.add_item(sample_item)
        service.add_item(sample_threaded_item)
        
        # Deactivate one item
        service.deactivate_item('JA000001')
        
        # Search for active items only
        search_filter = SearchFilter().active_only()
        results = service.search_items(search_filter)
        
        assert len(results) == 1
        assert results[0].ja_id == 'JA000002'
        assert results[0].active is True
    
    @pytest.mark.unit
    def test_search_items_by_length_range(self, service, sample_item, sample_threaded_item):
        """Test searching items by length range"""
        service.add_item(sample_item)      # 1000mm length
        service.add_item(sample_threaded_item)  # 500mm length
        
        # Search for items between 600-1200mm
        search_filter = SearchFilter().length_range(Decimal('600'), Decimal('1200'))
        results = service.search_items(search_filter)
        
        assert len(results) == 1
        assert results[0].ja_id == 'JA000001'
        assert results[0].dimensions.length == Decimal('1000')
    
    @pytest.mark.unit
    def test_search_items_notes_contain(self, service, sample_item, sample_threaded_item):
        """Test searching items by notes content"""
        service.add_item(sample_item)      # notes: "Test item"
        service.add_item(sample_threaded_item)  # notes: "M12 threaded rod"
        
        # Search for items with "M12" in notes
        search_filter = SearchFilter().notes_contain('M12')
        results = service.search_items(search_filter)
        
        assert len(results) == 1
        assert results[0].ja_id == 'JA000002'
        assert 'M12' in results[0].notes
    
    @pytest.mark.unit
    def test_search_items_multiple_filters(self, service, sample_item, sample_threaded_item):
        """Test searching with multiple filters"""
        service.add_item(sample_item)
        service.add_item(sample_threaded_item)
        
        # Search for Steel items that are Rods
        search_filter = (SearchFilter()
                        .material('Steel')
                        .item_type(ItemType.BAR)
                        .active_only())
        results = service.search_items(search_filter)
        
        assert len(results) == 1
        assert results[0].ja_id == 'JA000001'
        assert results[0].material == 'Steel'
        assert results[0].item_type == 'Bar'  # InventoryItem stores as string
    
    @pytest.mark.unit
    def test_batch_move_items(self, service, sample_item, sample_threaded_item):
        """Test moving multiple items to new location"""
        service.add_item(sample_item)
        service.add_item(sample_threaded_item)
        
        # Move both items to new location
        moved_count, failed_ids = service.batch_move_items(
            ['JA000001', 'JA000002'], 
            'New Storage Location',
            'Batch move test'
        )
        
        assert moved_count == 2
        assert len(failed_ids) == 0
        
        # Verify items were moved
        item1 = service.get_item('JA000001')
        item2 = service.get_item('JA000002')
        assert item1.location == 'New Storage Location'
        assert item2.location == 'New Storage Location'
    
    @pytest.mark.unit
    def test_batch_deactivate_items(self, service, sample_item, sample_threaded_item):
        """Test deactivating multiple items"""
        service.add_item(sample_item)
        service.add_item(sample_threaded_item)
        
        # Deactivate both items
        deactivated_count, failed_ids = service.batch_deactivate_items(['JA000001', 'JA000002'])
        
        assert deactivated_count == 2
        assert len(failed_ids) == 0
        
        # Verify items were deactivated - get_item returns None for inactive items
        item1 = service.get_item('JA000001')
        item2 = service.get_item('JA000002')
        assert item1 is None
        assert item2 is None
        
        # Verify items exist but are inactive in history
        history1 = service.get_item_history('JA000001')
        history2 = service.get_item_history('JA000002')
        assert len(history1) >= 1
        assert len(history2) >= 1
        assert history1[-1].active is False  # Most recent should be inactive
        assert history2[-1].active is False  # Most recent should be inactive
    
    @pytest.mark.unit
    def test_cache_invalidation(self, service, sample_item):
        """Test that cache behavior works consistently"""
        # Add item and get all items
        service.add_item(sample_item)
        items1 = service.get_all_items()
        assert len(items1) == 1
        
        # Add another properly formatted item through the service
        from app.database import InventoryItem
        direct_item = InventoryItem(
            ja_id='JA000999',
            item_type='Bar',
            shape='Round',
            material='Aluminum',
            length=200,
            width=10,
            location='Storage A',
            notes='Cache test item',
            active=True,
            precision=False
        )
        service.add_item(direct_item)
        
        # Get all items again - should see both items
        items2 = service.get_all_items()
        assert len(items2) == 2
        
        # Verify we can find both items
        ja_ids = [item.ja_id for item in items2]
        assert 'JA000001' in ja_ids
        assert 'JA000999' in ja_ids
    
    @pytest.mark.unit
    def test_error_handling_invalid_ja_id(self, service):
        """Test error handling for invalid JA_ID operations"""
        result = service.deactivate_item('INVALID_ID')
        assert result is False

        result = service.activate_item('INVALID_ID')
        assert result is False


class TestFieldValueSuggestions:
    """Tests for InventoryService.get_field_value_suggestions."""

    @pytest.fixture
    def service(self, test_storage, app):
        return InventoryService(test_storage)

    def _make_item(self, ja_id, **overrides):
        defaults = dict(
            item_type='Bar',
            shape='Round',
            material='Steel',
            length=100,
            width=10,
            location='Shelf A',
            active=True,
            precision=False,
        )
        defaults.update(overrides)
        return InventoryItem(ja_id=ja_id, **defaults)

    @pytest.fixture
    def populated(self, service):
        # Active items
        service.add_item(self._make_item(
            'JA000001',
            location='Shelf A', sub_location='Top',
            vendor='McMaster-Carr', purchase_location='McMaster-Carr',
            thread_size='1/4-20',
        ))
        service.add_item(self._make_item(
            'JA000002',
            location='Shelf A', sub_location='Bottom',
            vendor='Online Metals', purchase_location='OnlineMetals.com',
            thread_size='M10x1.5',
        ))
        service.add_item(self._make_item(
            'JA000003',
            location='Rack 3', sub_location='Bin 7',
            vendor='Grainger', purchase_location='Grainger',
            thread_size='1/2-13',
        ))

        # Inactive item to confirm history still seeds suggestions
        service.add_item(self._make_item(
            'JA000004',
            location='Old Cabinet', sub_location='Drawer 1',
            vendor='Discontinued Vendor',
            purchase_location='Discontinued Place',
            thread_size='3/8-16',
        ))
        service.deactivate_item('JA000004')

        return service

    @pytest.mark.unit
    def test_unsupported_field_raises(self, service):
        with pytest.raises(ValueError):
            service.get_field_value_suggestions('material')
        with pytest.raises(ValueError):
            service.get_field_value_suggestions('not_a_field')

    @pytest.mark.unit
    def test_vendor_suggestions_include_inactive(self, populated):
        result = populated.get_field_value_suggestions('vendor', limit=20)
        assert 'McMaster-Carr' in result
        assert 'Online Metals' in result
        assert 'Grainger' in result
        # Inactive item's vendor still seeds suggestions
        assert 'Discontinued Vendor' in result

    @pytest.mark.unit
    def test_no_query_returns_alphabetized_distinct(self, populated):
        result = populated.get_field_value_suggestions('location', limit=20)
        # Distinct, sorted case-insensitively
        assert result == sorted(result, key=str.lower)
        # Distinct
        assert len(result) == len(set(v.lower() for v in result))
        assert 'Shelf A' in result  # appears twice in DB but once in result
        assert 'Rack 3' in result
        assert 'Old Cabinet' in result

    @pytest.mark.unit
    def test_query_filters_substring_case_insensitive(self, populated):
        result = populated.get_field_value_suggestions('vendor', query='metal')
        assert 'Online Metals' in result
        assert 'McMaster-Carr' not in result

    @pytest.mark.unit
    def test_exact_match_first_then_starts_then_contains(self, populated):
        # Add a few overlapping entries to exercise ordering
        populated.add_item(self._make_item(
            'JA000010', vendor='Steel', location='Shelf X',
        ))
        populated.add_item(self._make_item(
            'JA000011', vendor='Steel Supply', location='Shelf Y',
        ))
        populated.add_item(self._make_item(
            'JA000012', vendor='Acme Steel Inc', location='Shelf Z',
        ))

        result = populated.get_field_value_suggestions('vendor', query='steel')
        # Exact match should come first
        assert result[0] == 'Steel'
        # Then starts-with
        assert result[1] == 'Steel Supply'
        # Then contains
        assert result[2] == 'Acme Steel Inc'

    @pytest.mark.unit
    def test_limit_clamping(self, populated, service):
        # Use an empty service so we control the corpus
        for i in range(60):
            service.add_item(self._make_item(
                f'JA{200 + i:06d}', vendor=f'Vendor-{i:02d}'
            ))
        result = service.get_field_value_suggestions('vendor', limit=999)
        assert len(result) == 50  # clamped to 50

        result_zero = service.get_field_value_suggestions('vendor', limit=0)
        assert len(result_zero) == 1  # clamped to 1

    @pytest.mark.unit
    def test_empty_and_whitespace_values_excluded(self, service):
        service.add_item(self._make_item('JA000050', vendor='Real Vendor'))
        # Item without vendor (None) — should not pollute suggestions
        service.add_item(self._make_item('JA000051'))
        result = service.get_field_value_suggestions('vendor')
        assert result == ['Real Vendor']

    @pytest.mark.unit
    def test_sub_location_filtered_by_location(self, populated):
        # Without filter: includes all sub-locations
        unfiltered = populated.get_field_value_suggestions('sub_location', limit=20)
        assert 'Top' in unfiltered
        assert 'Bin 7' in unfiltered
        assert 'Drawer 1' in unfiltered

        # Scoped to "Shelf A" only
        scoped = populated.get_field_value_suggestions(
            'sub_location', location='Shelf A', limit=20
        )
        assert 'Top' in scoped
        assert 'Bottom' in scoped
        assert 'Bin 7' not in scoped
        assert 'Drawer 1' not in scoped

    @pytest.mark.unit
    def test_sub_location_location_filter_case_insensitive(self, populated):
        scoped = populated.get_field_value_suggestions(
            'sub_location', location='shelf a', limit=20
        )
        assert 'Top' in scoped
        assert 'Bottom' in scoped

    @pytest.mark.unit
    def test_thread_size_field(self, populated):
        result = populated.get_field_value_suggestions('thread_size', limit=20)
        assert '1/4-20' in result
        assert 'M10x1.5' in result
        assert '1/2-13' in result
        assert '3/8-16' in result

    @pytest.mark.unit
    def test_purchase_location_field(self, populated):
        result = populated.get_field_value_suggestions(
            'purchase_location', query='mc'
        )
        assert any('McMaster' in v for v in result)