#!/usr/bin/env python3
"""
Test suite for data models and services
"""

import os
import sys
import unittest
from unittest.mock import Mock, MagicMock
from decimal import Decimal
from datetime import datetime

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up Flask app context before importing
from flask import Flask
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

from app.models import Item, ItemType, ItemShape, Thread, ThreadSeries, ThreadHandedness, Dimensions
from app.taxonomy import TaxonomyManager, MaterialInfo
from app.inventory_service import InventoryService, SearchFilter

class TestDimensions(unittest.TestCase):
    
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
    
    def tearDown(self):
        if hasattr(self, 'app_context'):
            self.app_context.pop()
    
    def test_dimensions_creation(self):
        """Test dimensions creation with various inputs"""
        dims = Dimensions(
            length=Decimal('10.5'),
            width=Decimal('2.75'),
            thickness=Decimal('0.5')
        )
        
        self.assertEqual(dims.length, Decimal('10.5'))
        self.assertEqual(dims.width, Decimal('2.75'))
        self.assertEqual(dims.thickness, Decimal('0.5'))
    
    def test_dimensions_string_conversion(self):
        """Test automatic string to Decimal conversion"""
        dims = Dimensions(
            length='10.5',
            width='2.75',
            thickness='0.5'
        )
        
        self.assertIsInstance(dims.length, Decimal)
        self.assertEqual(dims.length, Decimal('10.5'))
    
    def test_dimensions_volume_rectangular(self):
        """Test volume calculation for rectangular shapes"""
        dims = Dimensions(length='10', width='2', thickness='1')
        volume = dims.volume(ItemShape.RECTANGULAR)
        
        self.assertEqual(volume, Decimal('20'))
    
    def test_dimensions_volume_round(self):
        """Test volume calculation for round shapes"""
        dims = Dimensions(length='10', width='2')  # diameter = 2
        volume = dims.volume(ItemShape.ROUND)
        
        # π * r² * h = π * 1² * 10 ≈ 31.4159
        self.assertIsNotNone(volume)
        self.assertAlmostEqual(float(volume), 31.4159, places=3)
    
    def test_dimensions_to_dict(self):
        """Test dimensions dictionary serialization"""
        dims = Dimensions(length='10.5', width='2.75')
        data = dims.to_dict()
        
        expected = {
            'length': '10.5',
            'width': '2.75',
            'thickness': None,
            'wall_thickness': None,
            'weight': None
        }
        
        self.assertEqual(data, expected)
    
    def test_dimensions_from_dict(self):
        """Test dimensions creation from dictionary"""
        data = {
            'length': '10.5',
            'width': '2.75',
            'thickness': '0.5'
        }
        
        dims = Dimensions.from_dict(data)
        
        self.assertEqual(dims.length, Decimal('10.5'))
        self.assertEqual(dims.width, Decimal('2.75'))
        self.assertEqual(dims.thickness, Decimal('0.5'))

class TestThread(unittest.TestCase):
    
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
    
    def tearDown(self):
        if hasattr(self, 'app_context'):
            self.app_context.pop()
    
    def test_thread_creation(self):
        """Test thread creation"""
        thread = Thread(
            series=ThreadSeries.UNC,
            handedness=ThreadHandedness.RIGHT,
            size='1/2-13'
        )
        
        self.assertEqual(thread.series, ThreadSeries.UNC)
        self.assertEqual(thread.handedness, ThreadHandedness.RIGHT)
        self.assertEqual(thread.size, '1/2-13')
    
    def test_thread_size_validation(self):
        """Test thread size format validation"""
        valid_sizes = ['1/2-13', '10-24', '#10-24', 'M12x1.75', 'M12', '1/2"']
        
        for size in valid_sizes:
            thread = Thread(size=size)
            self.assertEqual(thread.size, size)
    
    def test_thread_to_dict(self):
        """Test thread dictionary serialization"""
        thread = Thread(
            series=ThreadSeries.UNC,
            handedness=ThreadHandedness.RIGHT,
            size='1/2-13',
            original='1/2-13 UNC RH'
        )
        
        data = thread.to_dict()
        expected = {
            'series': 'UNC',
            'handedness': 'RH',
            'size': '1/2-13',
            'original': '1/2-13 UNC RH'
        }
        
        self.assertEqual(data, expected)
    
    def test_thread_from_dict(self):
        """Test thread creation from dictionary"""
        data = {
            'series': 'UNC',
            'handedness': 'RH',
            'size': '1/2-13',
            'original': '1/2-13 UNC RH'
        }
        
        thread = Thread.from_dict(data)
        
        self.assertEqual(thread.series, ThreadSeries.UNC)
        self.assertEqual(thread.handedness, ThreadHandedness.RIGHT)
        self.assertEqual(thread.size, '1/2-13')
        self.assertEqual(thread.original, '1/2-13 UNC RH')

class TestItem(unittest.TestCase):
    
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
    
    def tearDown(self):
        if hasattr(self, 'app_context'):
            self.app_context.pop()
    
    def test_item_creation_basic(self):
        """Test basic item creation"""
        item = Item(
            ja_id='JA000001',
            item_type=ItemType.BAR,
            shape=ItemShape.RECTANGULAR,
            material='4140 Pre-Hard',
            dimensions=Dimensions(length='10', width='2', thickness='1')
        )
        
        self.assertEqual(item.ja_id, 'JA000001')
        self.assertEqual(item.item_type, ItemType.BAR)
        self.assertEqual(item.shape, ItemShape.RECTANGULAR)
        self.assertEqual(item.material, '4140 Pre-Hard')
        self.assertTrue(item.active)
    
    def test_ja_id_validation(self):
        """Test JA ID format validation"""
        valid_ids = ['JA000001', 'JA123456', 'JA999999']
        invalid_ids = ['JA00001', 'JA0000001', 'XX000001', 'ja000001']
        
        for ja_id in valid_ids:
            item = Item(
                ja_id=ja_id,
                item_type=ItemType.BAR,
                shape=ItemShape.RECTANGULAR,
                material='Steel',
                dimensions=Dimensions(length='10', width='2', thickness='1')
            )
            self.assertEqual(item.ja_id, ja_id)
        
        for ja_id in invalid_ids:
            with self.assertRaises(ValueError):
                Item(
                    ja_id=ja_id,
                    item_type=ItemType.BAR,
                    shape=ItemShape.RECTANGULAR,
                    material='Steel',
                    dimensions=Dimensions(length='10', width='2', thickness='1')
                )
    
    def test_required_dimensions_validation(self):
        """Test required dimensions validation for rectangular items"""
        # Valid rectangular item
        item = Item(
            ja_id='JA000001',
            item_type=ItemType.BAR,
            shape=ItemShape.RECTANGULAR,
            material='Steel',
            dimensions=Dimensions(length='10', width='2', thickness='1')
        )
        self.assertIsNotNone(item)
        
        # Missing width should raise error
        with self.assertRaises(ValueError):
            Item(
                ja_id='JA000002',
                item_type=ItemType.BAR,
                shape=ItemShape.RECTANGULAR,
                material='Steel',
                dimensions=Dimensions(length='10', thickness='1')
            )
    
    def test_display_name_generation(self):
        """Test display name generation"""
        item = Item(
            ja_id='JA000001',
            item_type=ItemType.BAR,
            shape=ItemShape.RECTANGULAR,
            material='4140 Pre-Hard',
            dimensions=Dimensions(length='10', width='2', thickness='1')
        )
        
        expected = '4140 Pre-Hard Bar Rectangular 2 × 1 × 10'
        self.assertEqual(item.display_name, expected)
    
    def test_item_serialization(self):
        """Test item to/from dictionary conversion"""
        original_item = Item(
            ja_id='JA000001',
            item_type=ItemType.BAR,
            shape=ItemShape.RECTANGULAR,
            material='4140 Pre-Hard',
            dimensions=Dimensions(length='10', width='2', thickness='1'),
            location='Shop A',
            notes='Test item'
        )
        
        # Convert to dict and back
        data = original_item.to_dict()
        restored_item = Item.from_dict(data)
        
        self.assertEqual(restored_item.ja_id, original_item.ja_id)
        self.assertEqual(restored_item.item_type, original_item.item_type)
        self.assertEqual(restored_item.material, original_item.material)
        self.assertEqual(restored_item.dimensions.length, original_item.dimensions.length)
        self.assertEqual(restored_item.location, original_item.location)
        self.assertEqual(restored_item.notes, original_item.notes)
    
    def test_parent_child_relationships(self):
        """Test parent-child relationship tracking"""
        parent = Item(
            ja_id='JA000001',
            item_type=ItemType.BAR,
            shape=ItemShape.RECTANGULAR,
            material='Steel',
            dimensions=Dimensions(length='10', width='2', thickness='1')
        )
        
        parent.add_child('JA000002')
        parent.add_child('JA000003')
        
        self.assertIn('JA000002', parent.child_ja_ids)
        self.assertIn('JA000003', parent.child_ja_ids)
        
        parent.remove_child('JA000002')
        self.assertNotIn('JA000002', parent.child_ja_ids)
        self.assertIn('JA000003', parent.child_ja_ids)

class TestTaxonomyManager(unittest.TestCase):
    
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        self.taxonomy = TaxonomyManager()
    
    def tearDown(self):
        if hasattr(self, 'app_context'):
            self.app_context.pop()
    
    def test_material_normalization(self):
        """Test material name normalization"""
        test_cases = [
            ('4140 Pre-Hard', '4140 Pre-Hard', False),
            ('4140', '4140 Pre-Hard', False),
            ('304 / 304L', '304/304L Stainless', False),
            ('Mystery', 'Unknown', False),
            ('Custom Material', 'Custom Material', True)
        ]
        
        for input_material, expected_normalized, expected_custom in test_cases:
            normalized, is_custom = self.taxonomy.normalize_material(input_material)
            self.assertEqual(normalized, expected_normalized, f"Failed for input: {input_material}")
            self.assertEqual(is_custom, expected_custom, f"Custom flag wrong for: {input_material}")
    
    def test_type_shape_compatibility(self):
        """Test type/shape compatibility validation"""
        # Valid combinations
        self.assertTrue(self.taxonomy.is_shape_compatible_with_type(ItemType.BAR, ItemShape.RECTANGULAR))
        self.assertTrue(self.taxonomy.is_shape_compatible_with_type(ItemType.BAR, ItemShape.ROUND))
        self.assertTrue(self.taxonomy.is_shape_compatible_with_type(ItemType.PIPE, ItemShape.ROUND))
        
        # Invalid combinations
        self.assertFalse(self.taxonomy.is_shape_compatible_with_type(ItemType.PIPE, ItemShape.RECTANGULAR))
        self.assertFalse(self.taxonomy.is_shape_compatible_with_type(ItemType.ANGLE, ItemShape.ROUND))
    
    def test_required_dimensions(self):
        """Test required dimensions retrieval"""
        # Rectangular bar should require length
        required = self.taxonomy.get_required_dimensions(ItemType.BAR, ItemShape.RECTANGULAR)
        self.assertIn('length', required)
        
        # Pipe should require length, width, and wall thickness
        required = self.taxonomy.get_required_dimensions(ItemType.PIPE, ItemShape.ROUND)
        self.assertIn('length', required)
        self.assertIn('width', required)
        self.assertIn('wall_thickness', required)
    
    def test_material_suggestions(self):
        """Test material name suggestions"""
        suggestions = self.taxonomy.suggest_material_matches('41', limit=3)
        
        self.assertGreater(len(suggestions), 0)
        # Should find 4140 Pre-Hard
        material_names = [s[0] for s in suggestions]
        self.assertIn('4140 Pre-Hard', material_names)
    
    def test_custom_material_addition(self):
        """Test adding custom materials"""
        success = self.taxonomy.add_custom_material(
            name='Custom Alloy X',
            aliases=['Alloy X', 'Special Steel'],
            category='Custom Steel'
        )
        
        self.assertTrue(success)
        
        # Test normalization works
        normalized, is_custom = self.taxonomy.normalize_material('Alloy X')
        self.assertEqual(normalized, 'Custom Alloy X')
        self.assertTrue(is_custom)

class TestInventoryService(unittest.TestCase):
    
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        
        # Mock storage
        self.mock_storage = Mock()
        self.service = InventoryService(self.mock_storage)
    
    def tearDown(self):
        if hasattr(self, 'app_context'):
            self.app_context.pop()
    
    def test_search_filter_creation(self):
        """Test search filter creation and chaining"""
        search_filter = (SearchFilter()
                        .active_only()
                        .material('Steel')
                        .length_range(Decimal('5'), Decimal('20'))
                        .notes_contain('test'))
        
        self.assertEqual(search_filter.filters['active'], True)
        self.assertEqual(search_filter.filters['material'], 'Steel')
        self.assertEqual(search_filter.ranges['length']['min'], Decimal('5'))
        self.assertEqual(search_filter.ranges['length']['max'], Decimal('20'))
        self.assertEqual(search_filter.text_searches['notes']['query'], 'test')
    
    def test_statistics_calculation(self):
        """Test inventory statistics calculation"""
        # Mock data
        mock_items = [
            Item(ja_id='JA000001', item_type=ItemType.BAR, shape=ItemShape.RECTANGULAR, 
                 material='Steel', active=True,
                 dimensions=Dimensions(length='10', width='2', thickness='1')),
            Item(ja_id='JA000002', item_type=ItemType.PLATE, shape=ItemShape.RECTANGULAR, 
                 material='Steel', active=True,
                 dimensions=Dimensions(length='12', width='6', thickness='0.5')),
            Item(ja_id='JA000003', item_type=ItemType.BAR, shape=ItemShape.ROUND, 
                 material='Aluminum', active=False,
                 dimensions=Dimensions(length='8', width='1')),
        ]
        
        # Mock the get_all_items method
        self.service.get_all_items = Mock(return_value=mock_items)
        
        stats = self.service.get_statistics()
        
        self.assertEqual(stats['total_items'], 3)
        self.assertEqual(stats['active_items'], 2)
        self.assertEqual(stats['inactive_items'], 1)
        self.assertEqual(stats['unique_materials'], 2)
        self.assertEqual(stats['by_type']['Bar'], 1)  # Only active bars
        self.assertEqual(stats['by_type']['Plate'], 1)

class TestModelIntegration(unittest.TestCase):
    """Integration tests combining multiple components"""
    
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
    
    def tearDown(self):
        if hasattr(self, 'app_context'):
            self.app_context.pop()
    
    def test_full_item_lifecycle(self):
        """Test complete item creation, modification, and serialization"""
        # Create item with thread
        thread = Thread(
            series=ThreadSeries.UNC,
            handedness=ThreadHandedness.RIGHT,
            size='1/2-13',
            original='1/2-13 UNC RH'
        )
        
        dimensions = Dimensions(
            length='12.5',
            width='0.5',
            thickness=None,
            weight='2.3'
        )
        
        item = Item(
            ja_id='JA000001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='4140 Pre-Hard',
            dimensions=dimensions,
            thread=thread,
            location='Shop A',
            notes='Threaded rod for fixture'
        )
        
        # Test properties
        self.assertTrue(item.is_threaded)
        self.assertIsNotNone(item.estimated_volume)
        
        # Test serialization roundtrip
        data = item.to_dict()
        restored = Item.from_dict(data)
        
        self.assertEqual(restored.ja_id, item.ja_id)
        self.assertEqual(restored.thread.series, item.thread.series)
        self.assertEqual(restored.dimensions.length, item.dimensions.length)
        self.assertTrue(restored.is_threaded)

def main():
    """Run the tests"""
    unittest.main(verbosity=2)

if __name__ == '__main__':
    main()