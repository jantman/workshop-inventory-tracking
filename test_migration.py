#!/usr/bin/env python3
"""
Test script for data migration functionality
Tests the migration logic without requiring actual Google Sheets connection
"""

import os
import sys
import unittest
from unittest.mock import Mock, MagicMock
from decimal import Decimal

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up Flask app context before importing
from flask import Flask
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

from migrate_data import DataMigrator

class TestDataMigrator(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        # Set up Flask app context
        self.app_context = app.app_context()
        self.app_context.push()
        
        # Mock the storage to avoid Google Sheets dependency
        self.migrator = DataMigrator('test-sheet-id', dry_run=True)
        self.migrator.storage = Mock()
    
    def tearDown(self):
        """Clean up test fixtures"""
        if hasattr(self, 'app_context'):
            self.app_context.pop()
    
    def test_fraction_to_decimal_conversion(self):
        """Test fraction to decimal conversion with various inputs"""
        test_cases = [
            ('1/2', '0.5'),
            ('3/4', '0.75'),
            ('1 1/2', '1.5'),
            ('2 3/8', '2.375'),
            ('5.25', '5.25'),
            ('0', '0'),
            ('', None),
            ('invalid', 'invalid'),  # Should return original
        ]
        
        for input_val, expected in test_cases:
            with self.subTest(input=input_val):
                result = self.migrator.fraction_to_decimal(input_val)
                self.assertEqual(result, expected, f"Failed for input '{input_val}'")
    
    def test_material_normalization(self):
        """Test material normalization and alias mapping"""
        test_cases = [
            ('4140 Pre-Hard', '4140 Pre-Hard', '4140 Pre-Hard'),
            ('304 / 304L', '304/304L Stainless', '304 / 304L'),
            ('Mystery', 'Unknown', 'Mystery'),
            ('unknown', 'Unknown', 'unknown'),
            ('', 'Unknown', ''),
            ('Custom Steel', 'Custom Steel', 'Custom Steel'),  # No alias
        ]
        
        for input_val, expected_normalized, expected_original in test_cases:
            with self.subTest(input=input_val):
                normalized, original = self.migrator.normalize_material(input_val)
                self.assertEqual(normalized, expected_normalized)
                self.assertEqual(original, expected_original)
    
    def test_thread_parsing(self):
        """Test thread parsing into structured fields"""
        test_cases = [
            ('1/2-13 UNC', 'UNC', None, '1/2-13', '1/2-13 UNC'),
            ('1/4-20 UNC RH', 'UNC', 'RH', '1/4-20', '1/4-20 UNC RH'),
            ('M12x1.75', 'Metric', None, 'M12x1.75', 'M12x1.75'),
            ('3/8-16 UNF LH', 'UNF', 'LH', '3/8-16', '3/8-16 UNF LH'),
            ('', None, None, None, ''),
        ]
        
        for input_val, expected_series, expected_handedness, expected_size, expected_original in test_cases:
            with self.subTest(input=input_val):
                series, handedness, size, original = self.migrator.parse_thread(input_val)
                self.assertEqual(series, expected_series)
                self.assertEqual(handedness, expected_handedness)
                self.assertEqual(size, expected_size)
                self.assertEqual(original, expected_original)
    
    def test_ja_id_validation(self):
        """Test JA ID format validation"""
        valid_ids = ['JA000001', 'JA123456', 'JA999999']
        invalid_ids = ['', 'JA00001', 'JA0000001', 'XX000001', 'ja000001', 'JA00000a']
        
        for ja_id in valid_ids:
            with self.subTest(ja_id=ja_id):
                self.assertTrue(self.migrator.validate_ja_id(ja_id), f"Should be valid: {ja_id}")
        
        for ja_id in invalid_ids:
            with self.subTest(ja_id=ja_id):
                self.assertFalse(self.migrator.validate_ja_id(ja_id), f"Should be invalid: {ja_id}")
    
    def test_active_status_normalization(self):
        """Test active status normalization"""
        test_cases = [
            ('Yes', 'Yes'),
            ('No', 'No'),
            ('', 'Yes'),  # Default to active
            ('n', 'No'),
            ('false', 'No'),
            ('0', 'No'),
            ('inactive', 'No'),
            ('anything else', 'Yes'),
        ]
        
        for input_val, expected in test_cases:
            with self.subTest(input=input_val):
                result = self.migrator.normalize_active_status(input_val)
                self.assertEqual(result, expected)
    
    def test_uniqueness_validation(self):
        """Test JA ID uniqueness checking"""
        # Reset the seen IDs for this test
        self.migrator.ja_ids_seen = set()
        self.migrator.errors = []
        
        # First active ID should be fine
        self.assertTrue(self.migrator.check_uniqueness('JA000001', 2, True))
        
        # Different active ID should be fine
        self.assertTrue(self.migrator.check_uniqueness('JA000002', 3, True))
        
        # Duplicate active ID should fail
        self.assertFalse(self.migrator.check_uniqueness('JA000001', 4, True))
        self.assertEqual(len(self.migrator.errors), 1)
        
        # Inactive duplicate should be allowed
        self.assertTrue(self.migrator.check_uniqueness('JA000001', 5, False))
    
    def test_transform_row(self):
        """Test complete row transformation"""
        # Sample original data (simplified)
        original_headers = [
            'Active?', 'Code128', 'Length (in)', 'Width (in)', 'Thickness (in)',
            'Wall Thickness (in)', 'Weight (lbs total)', 'Type', 'Shape', 'Material',
            'Thread', 'Quantity (>1)', 'Location', 'Sub-Location', 'Purch. Date',
            'Purch. Price (line)', 'Purch. Loc.', 'Notes', 'Vendor', 'Vendor Part #'
        ]
        
        original_row = [
            'No', 'JA000001', '5.54', '1.5625', '0.63', '', '12', 'Bar', 'Rectangular',
            '4140 Pre-Hard', '', '8', '', '', '2022-08-11', '', 'Equipment Hub',
            'Maybe vice jaws?', '', ''
        ]
        
        # Reset state for this test
        self.migrator.ja_ids_seen = set()
        self.migrator.errors = []
        self.migrator.warnings = []
        
        result = self.migrator.transform_row(original_row, original_headers, 2)
        
        # Should succeed
        self.assertIsNotNone(result)
        self.assertEqual(len(result), len(self.migrator.NEW_HEADERS))
        
        # Check key transformations
        self.assertEqual(result[0], 'No')  # Active
        self.assertEqual(result[1], 'JA000001')  # JA ID
        self.assertEqual(result[2], '5.54')  # Length (no change for decimal)
        self.assertEqual(result[9], '4140 Pre-Hard')  # Material (no normalization needed)

class TestMigrationIntegration(unittest.TestCase):
    """Integration tests for the complete migration process"""
    
    def test_dry_run_validation(self):
        """Test that dry run validation works correctly"""
        # Set up Flask app context
        with app.app_context():
            # This would require more setup with mock data
            # For now, just test that the migrator initializes correctly
            migrator = DataMigrator('test-sheet-id', dry_run=True)
            self.assertTrue(migrator.dry_run)
            self.assertEqual(migrator.spreadsheet_id, 'test-sheet-id')
            self.assertEqual(len(migrator.NEW_HEADERS), 26)

def main():
    """Run the tests"""
    # Set up test environment
    os.environ['FLASK_DEBUG'] = 'True'
    
    unittest.main(verbosity=2)

if __name__ == '__main__':
    main()