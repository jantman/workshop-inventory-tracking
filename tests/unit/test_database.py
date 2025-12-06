"""
Unit tests for database module.

Tests InventoryItem enhanced with enum properties and business logic methods.
"""

import pytest
from decimal import Decimal
from datetime import datetime
from app.database import InventoryItem, MaterialTaxonomy
from app.models import (
    ItemType, ItemShape, ThreadSeries, ThreadHandedness, 
    Dimensions, Thread
)


class TestInventoryItemEnumProperties:
    """Tests for InventoryItem enum properties"""
    
    @pytest.mark.unit
    def test_item_type_enum_property_getter(self):
        """Test item_type_enum property getter"""
        item = InventoryItem()
        
        # Test with valid enum value
        item.item_type = "Bar"
        assert item.item_type_enum == ItemType.BAR
        
        # Test with None
        item.item_type = None
        assert item.item_type_enum is None
        
        # Test with empty string
        item.item_type = ""
        assert item.item_type_enum is None
    
    @pytest.mark.unit
    def test_item_type_enum_property_setter(self):
        """Test item_type_enum property setter"""
        item = InventoryItem()
        
        # Test setting with enum
        item.item_type_enum = ItemType.PLATE
        assert item.item_type == "Plate"
        
        # Test setting with None
        item.item_type_enum = None
        assert item.item_type is None
    
    @pytest.mark.unit
    def test_item_type_enum_legacy_format_handling(self):
        """Test handling of legacy enum class name format"""
        item = InventoryItem()
        
        # Test legacy format like 'ItemType.PLATE'
        item.item_type = "ItemType.PLATE"
        assert item.item_type_enum == ItemType.PLATE
        
        # Test legacy format with capitalization
        item.item_type = "ItemType.BAR"
        assert item.item_type_enum == ItemType.BAR
    
    @pytest.mark.unit
    def test_shape_enum_property(self):
        """Test shape_enum property getter and setter"""
        item = InventoryItem()
        
        # Test getter
        item.shape = "Round"
        assert item.shape_enum == ItemShape.ROUND
        
        # Test setter
        item.shape_enum = ItemShape.RECTANGULAR
        assert item.shape == "Rectangular"
    
    @pytest.mark.unit
    def test_thread_series_enum_property(self):
        """Test thread_series_enum property getter and setter"""
        item = InventoryItem()
        
        # Test getter
        item.thread_series = "UNC"
        assert item.thread_series_enum == ThreadSeries.UNC
        
        # Test setter
        item.thread_series_enum = ThreadSeries.METRIC
        assert item.thread_series == "Metric"
    
    @pytest.mark.unit
    def test_thread_handedness_enum_property(self):
        """Test thread_handedness_enum property getter and setter"""
        item = InventoryItem()
        
        # Test getter
        item.thread_handedness = "RH"
        assert item.thread_handedness_enum == ThreadHandedness.RIGHT
        
        # Test setter
        item.thread_handedness_enum = ThreadHandedness.LEFT
        assert item.thread_handedness == "LH"


class TestInventoryItemValidation:
    """Tests for InventoryItem validation methods"""
    
    @pytest.mark.unit
    def test_validate_basic_item(self):
        """Test validation of basic valid item"""
        item = InventoryItem()
        item.ja_id = "JA000001"
        item.item_type = "Bar"
        item.shape = "Round"
        item.material = "Steel"
        item.length = 12.0
        item.width = 1.0

        errors = item.validate()
        assert len(errors) == 0
    
    @pytest.mark.unit
    def test_validate_missing_ja_id(self):
        """Test validation fails for missing JA ID"""
        item = InventoryItem()
        item.item_type = "Bar"
        item.material = "Steel"
        
        errors = item.validate()
        assert any("JA ID is required" in error for error in errors)
    
    @pytest.mark.unit
    def test_validate_invalid_ja_id_format(self):
        """Test validation fails for invalid JA ID format"""
        item = InventoryItem()
        item.ja_id = "INVALID"
        item.item_type = "Bar"
        item.material = "Steel"
        
        errors = item.validate()
        assert any("Invalid JA ID format" in error for error in errors)
    
    @pytest.mark.unit
    def test_validate_missing_material(self):
        """Test validation fails for missing material"""
        item = InventoryItem()
        item.ja_id = "JA000001"
        item.item_type = "Bar"
        
        errors = item.validate()
        assert any("Material is required" in error for error in errors)
    
    @pytest.mark.unit
    def test_validate_threaded_rod_requirements(self):
        """Test validation for threaded rod specific requirements"""
        item = InventoryItem()
        item.ja_id = "JA000001"
        item.item_type = "Threaded Rod"
        item.material = "Steel"
        
        # Missing length and thread size
        errors = item.validate()
        assert any("Length is required for threaded rods" in error for error in errors)
        assert any("Thread size is required for threaded rods" in error for error in errors)
        
        # Add required fields
        item.length = 12.0
        item.thread_size = "1/4-20"
        errors = item.validate()
        length_errors = [e for e in errors if "Length is required" in e]
        thread_errors = [e for e in errors if "Thread size is required" in e]
        assert len(length_errors) == 0
        assert len(thread_errors) == 0
    
    @pytest.mark.unit
    def test_validate_rectangular_item_requirements(self):
        """Test validation for rectangular item specific requirements"""
        item = InventoryItem()
        item.ja_id = "JA000001"
        item.item_type = "Plate"
        item.shape = "Rectangular"
        item.material = "Steel"
        
        # Missing dimensions
        errors = item.validate()
        assert any("Length is required for rectangular items" in error for error in errors)
        assert any("Width is required for rectangular items" in error for error in errors)
        assert any("Thickness is required for rectangular items" in error for error in errors)
    
    @pytest.mark.unit
    def test_validate_positive_dimensions(self):
        """Test validation fails for negative dimensions"""
        item = InventoryItem()
        item.ja_id = "JA000001"
        item.item_type = "Bar"
        item.material = "Steel"
        item.length = -1.0  # Negative length
        item.width = 0.0    # Zero width
        
        errors = item.validate()
        assert any("Length must be positive" in error for error in errors)
        assert any("Width must be positive" in error for error in errors)


class TestInventoryItemBusinessLogic:
    """Tests for InventoryItem business logic methods"""
    
    @pytest.mark.unit
    def test_display_name_basic(self):
        """Test display_name property for basic item"""
        item = InventoryItem()
        item.material = "Steel"
        item.item_type = "Bar"
        item.shape = "Round"
        
        expected = "Steel Bar Round"
        assert item.display_name == expected
    
    @pytest.mark.unit
    def test_display_name_with_dimensions_round(self):
        """Test display_name with dimensions for round item"""
        item = InventoryItem()
        item.material = "Aluminum"
        item.item_type = "Bar"
        item.shape = "Round"
        item.length = 12.0
        item.width = 1.0  # diameter
        
        expected = "Aluminum Bar Round ⌀1.0\" × 12.0\""
        assert item.display_name == expected
    
    @pytest.mark.unit
    def test_display_name_with_dimensions_rectangular(self):
        """Test display_name with dimensions for rectangular item"""
        item = InventoryItem()
        item.material = "Steel"
        item.item_type = "Plate"
        item.shape = "Rectangular"
        item.length = 12.0
        item.width = 6.0
        item.thickness = 0.25
        
        expected = "Steel Plate Rectangular 6.0\" × 0.25\" × 12.0\""
        assert item.display_name == expected
    
    @pytest.mark.unit
    def test_is_threaded_property(self):
        """Test is_threaded property"""
        item = InventoryItem()
        
        # No thread info
        assert item.is_threaded is False
        
        # With thread series
        item.thread_series = "UNC"
        assert item.is_threaded is True
        
        # Reset and test with thread size
        item.thread_series = None
        item.thread_size = "1/4-20"
        assert item.is_threaded is True
        
        # Reset and test with handedness
        item.thread_size = None
        item.thread_handedness = "RH"
        assert item.is_threaded is True
    
    @pytest.mark.unit
    def test_dimensions_property(self):
        """Test dimensions property getter and setter"""
        item = InventoryItem()
        item.length = 12.0
        item.width = 6.0
        item.thickness = 0.25
        
        # Test getter
        dims = item.dimensions
        assert dims.length == Decimal('12.0')
        assert dims.width == Decimal('6.0')
        assert dims.thickness == Decimal('0.25')
        
        # Test setter
        new_dims = Dimensions(length=Decimal('24.0'), width=Decimal('3.0'))
        item.dimensions = new_dims
        assert item.length == 24.0
        assert item.width == 3.0
        assert item.thickness is None
    
    @pytest.mark.unit
    def test_thread_property(self):
        """Test thread property getter and setter"""
        item = InventoryItem()
        
        # No thread data - should return None
        assert item.thread is None
        
        # Add thread data
        item.thread_series = "UNC"
        item.thread_handedness = "RH"
        item.thread_size = "1/4-20"
        
        # Test getter
        thread = item.thread
        assert thread is not None
        assert thread.series == ThreadSeries.UNC
        assert thread.handedness == ThreadHandedness.RIGHT
        assert thread.size == "1/4-20"
        
        # Test setter
        new_thread = Thread(
            series=ThreadSeries.METRIC,
            handedness=ThreadHandedness.LEFT,
            size="M10x1.5"
        )
        item.thread = new_thread
        assert item.thread_series == "Metric"
        assert item.thread_handedness == "LH"
        assert item.thread_size == "M10x1.5"


class TestInventoryItemDictMethods:
    """Tests for InventoryItem dictionary conversion methods"""
    
    @pytest.mark.unit
    def test_to_dict_enhanced(self):
        """Test to_dict_enhanced method"""
        item = InventoryItem()
        item.ja_id = "JA000001"
        item.item_type = "Bar"
        item.shape = "Round"
        item.material = "Steel"
        item.length = 12.0
        item.width = 1.0
        
        result = item.to_dict_enhanced()
        
        # Check that enum values are included
        assert result['item_type_enum'] == "Bar"
        assert result['shape_enum'] == "Round"
        assert result['display_name'] == "Steel Bar Round ⌀1.0\" × 12.0\""
        assert result['is_threaded'] is False
    
    @pytest.mark.unit
    def test_from_dict_enhanced(self):
        """Test from_dict_enhanced method"""
        data = {
            'ja_id': 'JA000001',
            'item_type_enum': 'Bar',
            'shape_enum': 'Round',
            'material': 'Steel',
            'length': 12.0,
            'width': 1.0,
            'active': True
        }

        item = InventoryItem.from_dict_enhanced(data)

        assert item.ja_id == 'JA000001'
        assert item.item_type == 'Bar'
        assert item.shape == 'Round'
        assert item.material == 'Steel'
        assert item.length == 12.0
        assert item.width == 1.0
        assert item.active is True


class TestInventoryItemRowMethods:
    """Tests for InventoryItem row conversion methods"""
    
    @pytest.mark.unit
    def test_to_row(self):
        """Test to_row method"""
        item = InventoryItem()
        item.ja_id = "JA000001"
        item.item_type = "Bar"
        item.shape = "Round"
        item.material = "Steel"
        item.length = 12.0
        item.width = 1.0
        item.active = True

        headers = ['JA ID', 'Type', 'Shape', 'Material', 'Length', 'Width', 'Active']
        row = item.to_row(headers)

        expected = ['JA000001', 'Bar', 'Round', 'Steel', '12.0', '1.0', 'Yes']
        assert row == expected
    
    @pytest.mark.unit
    def test_from_row(self):
        """Test from_row method"""
        headers = ['JA ID', 'Type', 'Shape', 'Material', 'Length', 'Width', 'Active']
        row = ['JA000001', 'Bar', 'Round', 'Steel', '12.0', '1.0', 'Yes']

        item = InventoryItem.from_row(row, headers)

        assert item.ja_id == 'JA000001'
        assert item.item_type == 'Bar'
        assert item.shape == 'Round'
        assert item.material == 'Steel'
        assert item.length == 12.0
        assert item.width == 1.0
        assert item.active is True
    
    @pytest.mark.unit
    def test_from_row_with_currency_price(self):
        """Test from_row method handles currency symbols in price"""
        headers = ['JA ID', 'Material', 'Purchase Price']
        row = ['JA000001', 'Steel', '$25.99']
        
        item = InventoryItem.from_row(row, headers)
        
        assert item.ja_id == 'JA000001'
        assert item.material == 'Steel'
        assert item.purchase_price == 25.99


class TestInventoryItemBackwardCompatibility:
    """Tests to ensure backward compatibility with existing string-based access"""
    
    @pytest.mark.unit
    def test_enum_properties_coexist_with_string_fields(self):
        """Test that enum properties work alongside string fields"""
        item = InventoryItem()
        
        # Set via string field
        item.item_type = "Bar"
        # Access via enum property
        assert item.item_type_enum == ItemType.BAR
        
        # Set via enum property
        item.shape_enum = ItemShape.ROUND
        # Access via string field
        assert item.shape == "Round"
    
    @pytest.mark.unit
    def test_existing_to_dict_still_works(self):
        """Test that existing to_dict method still works"""
        item = InventoryItem()
        item.ja_id = "JA000001"
        item.item_type = "Bar"
        item.material = "Steel"
        
        # Should not raise any errors
        result = item.to_dict()
        assert 'ja_id' in result
        assert 'item_type' in result
        assert 'material' in result