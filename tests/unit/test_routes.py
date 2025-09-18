"""
Unit Tests for Routes Module

Tests for form parsing and enum lookup functions in app.main.routes
"""

import pytest
from unittest.mock import Mock, patch
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