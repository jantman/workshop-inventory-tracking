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
            assert item.item_type.value == item_type_value
            assert item.ja_id == 'JA000001'
    
    def test_parse_threaded_rod_fails_current_implementation(self):
        """Test that 'Threaded Rod' fails with current implementation (documenting bug)"""
        form_data = {
            'ja_id': 'JA000002',
            'item_type': 'Threaded Rod',  # This will cause KeyError
            'shape': 'Round',
            'material': 'Carbon Steel',
            'length': '36',
            'width': '0.25'
        }
        
        # This should fail with current implementation
        with pytest.raises(KeyError, match="THREADED ROD"):
            _parse_item_from_form(form_data)
    
    def test_parse_threaded_rod_correct_approach(self):
        """Test what the correct behavior should be for 'Threaded Rod'"""
        form_data = {
            'ja_id': 'JA000002',
            'item_type': 'Threaded Rod',
            'shape': 'Round', 
            'material': 'Carbon Steel',
            'length': '36'
        }
        
        # Test the correct approach directly using enum constructor
        item_type = ItemType(form_data['item_type'])  # This should work
        shape = ItemShape(form_data['shape'])
        
        assert item_type == ItemType.THREADED_ROD
        assert item_type.value == "Threaded Rod"
        assert shape == ItemShape.ROUND
    
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
    
    def test_enum_bracket_notation_vs_constructor(self):
        """Compare bracket notation vs constructor for all enums"""
        
        # Test ItemType
        for item_type_enum in ItemType:
            value = item_type_enum.value
            
            # Constructor approach (always works)
            constructor_result = ItemType(value)
            assert constructor_result == item_type_enum
            
            # Bracket notation approach (fails for "Threaded Rod")
            if value == "Threaded Rod":
                with pytest.raises(KeyError):
                    ItemType[value.upper()]  # "THREADED ROD" != "THREADED_ROD"
            else:
                bracket_result = ItemType[value.upper()]
                assert bracket_result == item_type_enum
        
        # Test ItemShape (all should work with both approaches since no spaces)
        for shape_enum in ItemShape:
            value = shape_enum.value
            
            constructor_result = ItemShape(value)
            bracket_result = ItemShape[value.upper()]
            
            assert constructor_result == shape_enum
            assert bracket_result == shape_enum


class TestSearchEnumLookup:
    """Tests for enum lookup in search functionality (routes.py:1121, 1131)"""
    
    def test_search_enum_lookup_single_word_success(self):
        """Test search enum lookup with single-word item types (should work)"""
        # Simulate the current enum lookup logic from routes.py:1121
        data = {'item_type': 'Bar'}
        
        # This should work with current implementation
        item_type = ItemType[data['item_type'].upper()]
        assert item_type == ItemType.BAR
    
    def test_search_enum_lookup_threaded_rod_fails(self):
        """Test search enum lookup with 'Threaded Rod' fails (documenting bug)"""
        # Simulate the current enum lookup logic from routes.py:1121
        data = {'item_type': 'Threaded Rod'}
        
        # This should fail with current implementation
        with pytest.raises(KeyError, match="THREADED ROD"):
            ItemType[data['item_type'].upper()]  # "THREADED ROD" != "THREADED_ROD"
    
    def test_search_shape_enum_lookup_all_work(self):
        """Test search enum lookup for shapes (should all work since no spaces)"""
        shapes = ["Rectangular", "Round", "Square", "Hex"]
        
        for shape_value in shapes:
            data = {'shape': shape_value}
            
            # Current implementation should work for all shapes
            shape = ItemShape[data['shape'].upper()]
            expected_shape = ItemShape(shape_value)
            assert shape == expected_shape
    
    def test_search_enum_lookup_correct_approach(self):
        """Test the correct approach for search enum lookup"""
        # Simulate the data that would come from search request
        search_data = {
            'item_type': 'Threaded Rod',
            'shape': 'Round'
        }
        
        # Test correct approach using enum constructor
        if search_data.get('item_type'):
            item_type = ItemType(search_data['item_type'])  # Should work
            assert item_type == ItemType.THREADED_ROD
        
        if search_data.get('shape'):
            shape = ItemShape(search_data['shape'])  # Should work  
            assert shape == ItemShape.ROUND


class TestEnumLookupPatterns:
    """Tests documenting different enum lookup patterns in the codebase"""
    
    def test_current_broken_pattern(self):
        """Document the current broken pattern used in routes.py"""
        value = "Threaded Rod"
        
        # This is what the current code does (and fails)
        with pytest.raises(KeyError):
            ItemType[value.upper()]  # "THREADED ROD" != "THREADED_ROD"
    
    def test_correct_pattern_from_models(self):
        """Document the correct pattern from models.py:524"""
        value = "Threaded Rod"
        
        # This is what models.py does correctly
        result = ItemType(value)
        assert result == ItemType.THREADED_ROD
        assert result.value == "Threaded Rod"
    
    def test_why_single_words_work_with_broken_pattern(self):
        """Explain why single-word types work with the broken pattern"""
        single_word_values = ["Bar", "Plate", "Sheet", "Tube", "Angle"]
        
        for value in single_word_values:
            # Both approaches work for single words
            constructor_result = ItemType(value)
            bracket_result = ItemType[value.upper()]
            
            assert constructor_result == bracket_result
            
            # This is why: value.upper() == enum.name for single words
            expected_enum = next(e for e in ItemType if e.value == value)
            assert value.upper() == expected_enum.name
        
        # But NOT for "Threaded Rod"
        assert "Threaded Rod".upper() != ItemType.THREADED_ROD.name
        assert "THREADED ROD" != "THREADED_ROD"