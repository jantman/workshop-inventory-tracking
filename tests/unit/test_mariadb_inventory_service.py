"""
Unit Tests for InventoryService

Tests the MariaDB-specific functionality for handling multi-row JA ID scenarios.
This validates the fix for Milestone 4: Fix Item Data Retrieval Logic.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from decimal import Decimal

from app.mariadb_inventory_service import InventoryService
from app.database import InventoryItem
from app.models import ItemType, ItemShape, Dimensions
# Note: Tests now work with InventoryItem directly instead of Item dataclass


class TestInventoryService:
    """Test class for MariaDB inventory service"""
    
    @pytest.fixture
    def mock_storage(self):
        """Mock MariaDB storage"""
        mock_storage = Mock()
        mock_storage.engine = Mock()
        return mock_storage
    
    @pytest.fixture
    def service(self, mock_storage):
        """Create service instance with mock storage"""
        return InventoryService(mock_storage)
    
    @pytest.fixture
    def sample_db_item(self):
        """Sample database item for testing"""
        db_item = Mock(spec=InventoryItem)
        db_item.ja_id = "JA000211"
        db_item.active = True
        db_item.item_type = "Bar"
        db_item.shape = "Round"
        db_item.material = "Steel"
        db_item.length = Decimal("45.625")
        db_item.width = Decimal("1.0")
        db_item.thickness = None
        db_item.wall_thickness = None
        db_item.weight = None
        db_item.thread_series = None
        db_item.thread_handedness = None
        db_item.thread_size = None
        db_item.location = "Workshop"
        db_item.sub_location = ""
        db_item.purchase_date = None
        db_item.purchase_price = None
        db_item.purchase_location = None
        db_item.notes = ""
        db_item.vendor = ""
        db_item.vendor_part = ""
        db_item.original_material = ""
        db_item.original_thread = ""
        db_item.date_added = datetime.now()
        db_item.last_modified = datetime.now()
        
        # Mock the dimensions property to return a Dimensions object
        mock_dimensions = Dimensions(
            length=Decimal("45.625"),
            width=Decimal("1.0"),
            thickness=None,
            wall_thickness=None,
            weight=None
        )
        db_item.dimensions = mock_dimensions
        
        return db_item
    
    def test_get_active_item_finds_active_only(self, service, sample_db_item):
        """Test that get_active_item returns only active items"""
        # Mock the database session and query
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock query chain
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = sample_db_item
            
            # Call the method
            result = service.get_active_item("JA000211")
            
            # Verify the result
            assert result is not None
            assert result.ja_id == "JA000211"
            assert result.active is True
            assert float(result.dimensions.length) == 45.625
            
            # Verify the query was called with active filter
            mock_session.query.assert_called_once()
            mock_query.filter.assert_called_once()
            # The filter should include active=True condition
            
            mock_session.close.assert_called_once()
    
    def test_get_active_item_returns_none_when_no_active(self, service):
        """Test that get_active_item returns None when no active items exist"""
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock query to return None (no active items)
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = None
            
            result = service.get_active_item("JA000001")
            
            assert result is None
            mock_session.close.assert_called_once()
    
    def test_get_item_history_returns_all_items(self, service):
        """Test that get_item_history returns all items for a JA ID ordered by date"""
        # Create mock historical items with all required fields
        item1 = Mock(spec=InventoryItem)
        item1.ja_id = "JA000211"
        item1.active = False
        item1.item_type = "Bar"
        item1.shape = "Round"
        item1.material = "Steel"  # Required field
        item1.length = Decimal("53.5")
        item1.width = Decimal("1.0")
        item1.thickness = None
        item1.wall_thickness = None
        item1.weight = None
        item1.thread_series = None
        item1.thread_handedness = None
        item1.thread_size = None
        item1.location = "Workshop"
        item1.sub_location = ""
        item1.purchase_date = None
        item1.purchase_price = None
        item1.purchase_location = ""
        item1.notes = ""
        item1.vendor = ""
        item1.vendor_part = ""
        item1.original_material = ""
        item1.original_thread = ""
        item1.date_added = datetime(2025, 1, 1)
        item1.last_modified = datetime(2025, 1, 1)
        # Mock the dimensions property
        item1.dimensions = Dimensions(
            length=Decimal("53.5"),
            width=Decimal("1.0"),
            thickness=None,
            wall_thickness=None,
            weight=None
        )

        item2 = Mock(spec=InventoryItem)
        item2.ja_id = "JA000211"
        item2.active = False
        item2.item_type = "Bar"
        item2.shape = "Round"
        item2.material = "Steel"  # Required field
        item2.length = Decimal("48.0")
        item2.width = Decimal("1.0")
        item2.thickness = None
        item2.wall_thickness = None
        item2.weight = None
        item2.thread_series = None
        item2.thread_handedness = None
        item2.thread_size = None
        item2.location = "Workshop"
        item2.sub_location = ""
        item2.purchase_date = None
        item2.purchase_price = None
        item2.purchase_location = ""
        item2.notes = ""
        item2.vendor = ""
        item2.vendor_part = ""
        item2.original_material = ""
        item2.original_thread = ""
        item2.date_added = datetime(2025, 1, 15)
        item2.last_modified = datetime(2025, 1, 15)
        # Mock the dimensions property
        item2.dimensions = Dimensions(
            length=Decimal("48.0"),
            width=Decimal("1.0"),
            thickness=None,
            wall_thickness=None,
            weight=None
        )

        item3 = Mock(spec=InventoryItem)
        item3.ja_id = "JA000211"
        item3.active = True
        item3.item_type = "Bar"
        item3.shape = "Round"
        item3.material = "Steel"  # Required field
        item3.length = Decimal("45.625")
        item3.width = Decimal("1.0")
        item3.thickness = None
        item3.wall_thickness = None
        item3.weight = None
        item3.thread_series = None
        item3.thread_handedness = None
        item3.thread_size = None
        item3.location = "Workshop"
        item3.sub_location = ""
        item3.purchase_date = None
        item3.purchase_price = None
        item3.purchase_location = ""
        item3.notes = ""
        item3.vendor = ""
        item3.vendor_part = ""
        item3.original_material = ""
        item3.original_thread = ""
        item3.date_added = datetime(2025, 1, 30)
        item3.last_modified = datetime(2025, 1, 30)
        # Mock the dimensions property
        item3.dimensions = Dimensions(
            length=Decimal("45.625"),
            width=Decimal("1.0"),
            thickness=None,
            wall_thickness=None,
            weight=None
        )
        
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock query to return all items ordered by date_added
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.all.return_value = [item1, item2, item3]
            
            result = service.get_item_history("JA000211")
            
            # Should return all 3 items
            assert len(result) == 3
            
            # Verify they're in chronological order and have correct active status
            assert result[0].active is False  # First item (oldest)
            assert result[1].active is False  # Second item
            assert result[2].active is True   # Third item (newest, active)
            
            # Verify lengths are correct
            assert float(result[0].dimensions.length) == 53.5
            assert float(result[1].dimensions.length) == 48.0
            assert float(result[2].dimensions.length) == 45.625
            
            mock_session.close.assert_called_once()
    
    def test_get_all_active_items_filters_correctly(self, service, sample_db_item):
        """Test that get_all_active_items only returns active items"""
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock query to return only active items
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.all.return_value = [sample_db_item]
            
            result = service.get_all_active_items()
            
            # Should return the active item
            assert len(result) == 1
            assert result[0].active is True
            
            # Verify the query included active=True filter
            mock_query.filter.assert_called_once()
            
            mock_session.close.assert_called_once()
    
    def test_get_item_overrides_parent_method(self, service, sample_db_item):
        """Test that get_item method is overridden to return active item only"""
        with patch.object(service, 'get_active_item') as mock_get_active:
            mock_get_active.return_value = Mock()
            mock_get_active.return_value.ja_id = "JA000211"
            
            result = service.get_item("JA000211")
            
            # Should call get_active_item instead of parent implementation
            mock_get_active.assert_called_once_with("JA000211")
            assert result.ja_id == "JA000211"
    
    def test_get_all_items_overrides_parent_method(self, service):
        """Test that get_all_items method is overridden to return active items only"""
        with patch.object(service, 'get_all_active_items') as mock_get_all_active:
            mock_get_all_active.return_value = [Mock()]
            
            result = service.get_all_items()
            
            # Should call get_all_active_items instead of parent implementation
            mock_get_all_active.assert_called_once()
            assert len(result) == 1
    
    def test_ja_id_exists_with_active_only_true(self, service):
        """Test ja_id_exists with only_active=True (default)"""
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock query
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = Mock()  # Item exists
            
            result = service.ja_id_exists("JA000211", only_active=True)
            
            assert result is True
            # Should have been called with both JA ID and active filters
            assert mock_query.filter.call_count == 2
            
            mock_session.close.assert_called_once()
    
    def test_ja_id_exists_with_active_only_false(self, service):
        """Test ja_id_exists with only_active=False"""
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session
            
            # Mock query
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = None  # Item doesn't exist
            
            result = service.ja_id_exists("JA000999", only_active=False)
            
            assert result is False
            # Should have been called with only JA ID filter
            assert mock_query.filter.call_count == 1

            mock_session.close.assert_called_once()

    def test_get_item_any_status_returns_active_item(self, service, sample_db_item):
        """Test that get_item_any_status can return active items"""
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Mock query chain
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.first.return_value = sample_db_item

            # Call the method
            result = service.get_item_any_status("JA000211")

            # Verify the result
            assert result is not None
            assert result.ja_id == "JA000211"
            assert result.active is True

            # Verify the query was called without active filter
            mock_session.query.assert_called_once()
            mock_query.filter.assert_called_once()
            mock_query.order_by.assert_called_once()

            mock_session.close.assert_called_once()

    def test_get_item_any_status_returns_inactive_item(self, service):
        """Test that get_item_any_status can return inactive items"""
        # Create an inactive sample item
        inactive_item = Mock(spec=InventoryItem)
        inactive_item.ja_id = "JA000999"
        inactive_item.active = False
        inactive_item.item_type = "Bar"
        inactive_item.shape = "Round"
        inactive_item.material = "Steel"
        inactive_item.length = Decimal("12.0")
        inactive_item.width = Decimal("0.5")
        inactive_item.location = "Storage"
        inactive_item.dimensions = Dimensions(
            length=Decimal("12.0"),
            width=Decimal("0.5"),
            thickness=None,
            wall_thickness=None,
            weight=None
        )

        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Mock query chain
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.first.return_value = inactive_item

            # Call the method
            result = service.get_item_any_status("JA000999")

            # Verify the result - should return inactive item
            assert result is not None
            assert result.ja_id == "JA000999"
            assert result.active is False

            mock_session.close.assert_called_once()

    def test_get_item_any_status_returns_most_recent_when_multiple(self, service):
        """Test that get_item_any_status returns the most recent item when multiple exist"""
        # This tests that order_by(desc(date_added)) is working correctly
        most_recent_item = Mock(spec=InventoryItem)
        most_recent_item.ja_id = "JA000211"
        most_recent_item.active = False  # Most recent is inactive
        most_recent_item.date_added = datetime(2024, 1, 15)

        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Mock query chain - first() returns most recent due to order_by
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.first.return_value = most_recent_item

            # Call the method
            result = service.get_item_any_status("JA000211")

            # Should return the most recent item (inactive in this case)
            assert result is not None
            assert result.ja_id == "JA000211"
            assert result.active is False

            mock_session.close.assert_called_once()

    def test_get_item_any_status_returns_none_when_not_found(self, service):
        """Test that get_item_any_status returns None when item doesn't exist"""
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Mock query chain returning None
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.first.return_value = None

            # Call the method
            result = service.get_item_any_status("JA999999")

            # Should return None
            assert result is None

            mock_session.close.assert_called_once()

    def test_update_item_allows_inactive_items(self, service):
        """Test that update_item can update inactive items"""
        # Create an inactive item to update
        inactive_item = Mock(spec=InventoryItem)
        inactive_item.ja_id = "JA000999"
        inactive_item.active = False
        inactive_item.item_type = "Bar"
        inactive_item.shape = "Round"
        inactive_item.material = "Aluminum"
        inactive_item.length = Decimal("24.0")
        inactive_item.width = Decimal("1.0")
        inactive_item.thickness = None
        inactive_item.wall_thickness = None
        inactive_item.weight = None
        inactive_item.location = "Storage A"
        inactive_item.sub_location = ""
        inactive_item.notes = "Updated notes"
        inactive_item.vendor = ""
        inactive_item.vendor_part = ""
        inactive_item.thread_series = ""
        inactive_item.thread_handedness = ""
        inactive_item.thread_size = ""
        inactive_item.purchase_date = None
        inactive_item.purchase_price = None
        inactive_item.purchase_location = None
        inactive_item.dimensions = Dimensions(
            length=Decimal("24.0"),
            width=Decimal("1.0"),
            thickness=None,
            wall_thickness=None,
            weight=None
        )

        # Mock database item that will be found and updated
        db_item = Mock(spec=InventoryItem)
        db_item.ja_id = "JA000999"
        db_item.active = False
        db_item.item_type = "Bar"
        db_item.shape = "Round"
        db_item.material = "Steel"
        db_item.length = Decimal("12.0")
        db_item.width = Decimal("0.5")
        db_item.thickness = None
        db_item.wall_thickness = None
        db_item.weight = None
        db_item.location = "Storage B"
        db_item.sub_location = ""
        db_item.notes = "Old notes"
        db_item.vendor = ""
        db_item.vendor_part = ""
        db_item.thread_series = ""
        db_item.thread_handedness = ""
        db_item.thread_size = ""

        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Mock query chain
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query
            mock_query.first.return_value = db_item

            # Call update_item
            result = service.update_item(inactive_item)

            # Should succeed
            assert result is True

            # Verify commit was called
            mock_session.commit.assert_called_once()
            mock_session.close.assert_called_once()


class TestMaterialDescendants:
    """Test class for hierarchical material descendant queries"""

    @pytest.fixture
    def mock_storage(self):
        """Mock MariaDB storage"""
        mock_storage = Mock()
        mock_storage.engine = Mock()
        return mock_storage

    @pytest.fixture
    def service(self, mock_storage):
        """Create service instance with mock storage"""
        return InventoryService(mock_storage)

    def test_get_material_descendants_with_children_and_grandchildren(self, service):
        """Test getting descendants for a material with children and grandchildren"""
        from app.database import MaterialTaxonomy

        # Create mock materials
        aluminum = Mock(spec=MaterialTaxonomy)
        aluminum.name = "Aluminum"
        aluminum.active = True

        six_series = Mock(spec=MaterialTaxonomy)
        six_series.name = "6000 Series Aluminum"
        six_series.parent = "Aluminum"
        six_series.active = True

        seven_series = Mock(spec=MaterialTaxonomy)
        seven_series.name = "7000 Series Aluminum"
        seven_series.parent = "Aluminum"
        seven_series.active = True

        six_zero_six_one = Mock(spec=MaterialTaxonomy)
        six_zero_six_one.name = "6061-T6"
        six_zero_six_one.parent = "6000 Series Aluminum"
        six_zero_six_one.active = True

        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Mock query chain for finding base material
            mock_query_base = Mock()
            mock_session.query.return_value = mock_query_base
            mock_query_base.filter.return_value = mock_query_base

            # First query: find base material "Aluminum"
            # Second query: find children of "Aluminum" -> returns [6000 Series, 7000 Series]
            # Third query: find grandchildren of "6000 Series Aluminum" -> returns [6061-T6]
            # Fourth query: find grandchildren of "7000 Series Aluminum" -> returns []
            mock_query_base.first.side_effect = [aluminum]
            mock_query_base.all.side_effect = [
                [six_series, seven_series],  # Children of Aluminum
                [six_zero_six_one],  # Grandchildren of 6000 Series
                []  # Grandchildren of 7000 Series
            ]

            result = service.get_material_descendants("Aluminum")

            # Should return all materials in hierarchy
            assert len(result) == 4
            assert "Aluminum" in result
            assert "6000 Series Aluminum" in result
            assert "7000 Series Aluminum" in result
            assert "6061-T6" in result
            # Results should be sorted
            assert result == sorted(result)

            mock_session.close.assert_called_once()

    def test_get_material_descendants_with_no_children(self, service):
        """Test getting descendants for a leaf material with no children"""
        from app.database import MaterialTaxonomy

        # Create mock material with no children
        six_zero_six_one = Mock(spec=MaterialTaxonomy)
        six_zero_six_one.name = "6061-T6"
        six_zero_six_one.active = True

        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = six_zero_six_one
            mock_query.all.return_value = []  # No children

            result = service.get_material_descendants("6061-T6")

            # Should return only the material itself
            assert len(result) == 1
            assert result[0] == "6061-T6"

            mock_session.close.assert_called_once()

    def test_get_material_descendants_material_not_in_taxonomy(self, service):
        """Test getting descendants for a material not in the taxonomy"""
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = None  # Material not found

            result = service.get_material_descendants("Unknown Material")

            # Should return just the material name
            assert len(result) == 1
            assert result[0] == "Unknown Material"

            mock_session.close.assert_called_once()

    def test_get_material_descendants_case_insensitive(self, service):
        """Test that material lookup is case-insensitive"""
        from app.database import MaterialTaxonomy

        aluminum = Mock(spec=MaterialTaxonomy)
        aluminum.name = "Aluminum"
        aluminum.active = True

        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = aluminum
            mock_query.all.return_value = []  # No children

            # Search with different case
            result = service.get_material_descendants("ALUMINUM")

            # Should still find and return the proper cased name
            assert len(result) == 1
            assert result[0] == "Aluminum"

            mock_session.close.assert_called_once()

    def test_get_material_descendants_only_active_materials(self, service):
        """Test that only active materials are included in descendants"""
        from app.database import MaterialTaxonomy

        steel = Mock(spec=MaterialTaxonomy)
        steel.name = "Steel"
        steel.active = True

        carbon_steel = Mock(spec=MaterialTaxonomy)
        carbon_steel.name = "Carbon Steel"
        carbon_steel.parent = "Steel"
        carbon_steel.active = True

        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = steel
            # Children query should only return active materials
            mock_query.all.side_effect = [
                [carbon_steel],  # Active children
                []  # No grandchildren
            ]

            result = service.get_material_descendants("Steel")

            # All queries should filter for active == True
            # Verify through the number of filter calls
            assert mock_query.filter.called

            assert len(result) == 2
            assert "Steel" in result
            assert "Carbon Steel" in result

            mock_session.close.assert_called_once()

    def test_get_material_descendants_error_handling(self, service):
        """Test error handling when database query fails"""
        with patch.object(service, 'Session') as mock_session_class:
            mock_session = Mock()
            mock_session_class.return_value = mock_session

            # Simulate database error
            mock_session.query.side_effect = Exception("Database error")

            result = service.get_material_descendants("Steel")

            # Should return just the material name on error
            assert len(result) == 1
            assert result[0] == "Steel"

            mock_session.close.assert_called_once()