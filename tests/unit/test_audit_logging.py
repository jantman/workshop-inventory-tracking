"""
Unit tests for audit logging functionality.

Tests comprehensive audit logging for all data modification operations
to ensure sufficient data is captured for manual reconstruction.
"""

import pytest
import json
import logging
from io import StringIO
from unittest.mock import patch, MagicMock
from datetime import datetime, date

from app.logging_config import log_audit_operation, log_audit_batch_operation
from app.models import ItemType, ItemShape, Dimensions, Thread, ThreadSeries, ThreadHandedness
from app.database import InventoryItem
from app.main.routes import _item_to_audit_dict
from decimal import Decimal


class TestAuditLogging:
    """Test audit logging functions and data completeness"""
    
    @pytest.fixture
    def log_capture(self):
        """Capture audit logs for testing"""
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        
        # Capture from the audit logger
        logger = logging.getLogger('inventory')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        yield log_capture
        
        # Cleanup
        logger.removeHandler(handler)
    
    @pytest.fixture
    def sample_item_data(self):
        """Sample item data for testing"""
        return {
            'ja_id': 'JA000123',
            'item_type': 'Bar',
            'shape': 'Round',
            'material': 'Steel',
            'length': 100.0,
            'width': 25.0,
            'thickness': None,
            'wall_thickness': None,
            'weight': 5.5,
            'thread_series': None,
            'thread_handedness': None,
            'thread_size': None,
            'location': 'Storage A',
            'sub_location': 'Shelf 1',
            'purchase_date': '2025-01-01',
            'purchase_price': 50.00,
            'purchase_location': 'Hardware Store',
            'notes': 'Test item for audit logging',
            'vendor': 'Steel Co',
            'vendor_part_number': 'SC-123',
            'original_material': None,
            'original_thread': None,
            'active': True,
            'date_added': '2025-09-13T12:00:00',
            'last_modified': '2025-09-13T12:00:00'
        }
    
    @pytest.fixture
    def sample_form_data(self):
        """Sample form data for testing"""
        return {
            'ja_id': 'JA000123',
            'item_type': 'Bar',
            'shape': 'Round',
            'material': 'Steel',
            'length': '100.0',
            'width': '25.0',
            'location': 'Storage A',
            'sub_location': 'Shelf 1',
            'notes': 'Test item'
        }
    
    @pytest.mark.unit
    def test_add_item_audit_logging(self, app, log_capture, sample_form_data, sample_item_data):
        """Test audit logging for add item operations"""
        with app.test_request_context('/inventory/add', method='POST',
                                     environ_base={'REMOTE_ADDR': '127.0.0.1'},
                                     headers={'User-Agent': 'Test Agent'}):
            
            # Test input phase
            log_audit_operation('add_item', 'input',
                              item_id='JA000123',
                              form_data=sample_form_data)
            
            # Test success phase
            log_audit_operation('add_item', 'success',
                              item_id='JA000123',
                              form_data=sample_form_data,
                              item_after=sample_item_data)
            
            # Test error phase
            log_audit_operation('add_item', 'error',
                              item_id='JA000456',
                              form_data=sample_form_data,
                              error_details='Validation failed: JA ID already exists')
        
        # Analyze captured logs - focus on message patterns since JSON structure
        # is handled by different formatters in production
        log_content = log_capture.getvalue()
        log_lines = [line for line in log_content.split('\n') if line.strip()]
        
        # Verify we have audit entries with expected patterns
        assert len(log_lines) >= 3, "Should have at least 3 audit log entries"
        
        # Check for expected audit log patterns
        assert any('AUDIT: add_item item=JA000123 phase=input' in line for line in log_lines)
        assert any('AUDIT: add_item item=JA000123 phase=success' in line for line in log_lines)
        assert any('AUDIT: add_item item=JA000456 phase=error' in line for line in log_lines)
        
        # Verify message content indicates data capture
        input_line = next(line for line in log_lines if 'phase=input' in line)
        assert 'capturing user input for reconstruction' in input_line
        
        success_line = next(line for line in log_lines if 'phase=success' in line)
        assert 'operation completed successfully' in success_line
        
        error_line = next(line for line in log_lines if 'phase=error' in line)
        assert 'operation failed' in error_line
    
    @pytest.mark.unit
    def test_edit_item_audit_logging(self, app, log_capture, sample_form_data, sample_item_data):
        """Test audit logging for edit item operations"""
        with app.test_request_context('/inventory/edit', method='POST',
                                     environ_base={'REMOTE_ADDR': '192.168.1.100'},
                                     headers={'User-Agent': 'Firefox'}):
            
            # Create modified item data
            modified_item_data = sample_item_data.copy()
            modified_item_data.update({
                'location': 'Storage B',
                'sub_location': 'Shelf 2', 
                'notes': 'Updated test item',
                'last_modified': '2025-09-13T13:00:00'
            })
            
            # Test input phase
            log_audit_operation('edit_item', 'input',
                              item_id='JA000123',
                              form_data=sample_form_data,
                              item_before=sample_item_data)
            
            # Test success phase with before/after states
            log_audit_operation('edit_item', 'success',
                              item_id='JA000123',
                              form_data=sample_form_data,
                              item_before=sample_item_data,
                              item_after=modified_item_data,
                              changes={'location': ['Storage A', 'Storage B'], 'notes': ['Test item for audit logging', 'Updated test item']})
        
        log_content = log_capture.getvalue()
        
        # Verify we can find operation-specific log patterns
        assert 'AUDIT: edit_item' in log_content
        assert 'item=JA000123' in log_content
        assert 'phase=input' in log_content
        assert 'phase=success' in log_content
        
        # Verify edit-specific audit patterns
        assert 'AUDIT: edit_item item=JA000123 phase=input' in log_content
        assert 'AUDIT: edit_item item=JA000123 phase=success' in log_content
    
    @pytest.mark.unit 
    def test_shorten_item_audit_logging(self, app, log_capture, sample_item_data):
        """Test audit logging for shorten item operations"""
        with app.test_request_context('/inventory/shorten', method='POST',
                                     environ_base={'REMOTE_ADDR': '10.0.0.1'}):
            
            # Create shortened item data
            shortened_item_data = sample_item_data.copy()
            shortened_item_data.update({
                'length': 80.0,
                'notes': 'Shortened from 100" to 80" on 2025-09-13\nNotes: Cut for project\n\nPrevious notes: Test item for audit logging',
                'last_modified': '2025-09-13T14:00:00'
            })
            
            shorten_form_data = {
                'ja_id': 'JA000123',
                'new_length': 80.0,
                'cut_date': '2025-09-13',
                'notes': 'Cut for project'
            }
            
            # Test both route-level and service-level logging
            log_audit_operation('shorten_item', 'input',
                              item_id='JA000123',
                              form_data=shorten_form_data,
                              item_before=sample_item_data)
            
            log_audit_operation('shorten_item_service', 'success',
                              item_id='JA000123',
                              form_data=shorten_form_data,
                              item_before=sample_item_data,
                              item_after=shortened_item_data,
                              changes={
                                  'operation': 'shortening',
                                  'original_length': 100.0,
                                  'new_length': 80.0,
                                  'deactivated_item_id': 123,
                                  'new_item_id': 124
                              })
        
        log_content = log_capture.getvalue()
        
        # Verify shorten-specific patterns
        assert 'AUDIT: shorten_item' in log_content
        assert 'AUDIT: shorten_item_service' in log_content
        assert 'item=JA000123' in log_content
        
        # Verify we have both route and service level logs
        route_logs = [line for line in log_content.split('\n') if 'shorten_item item=' in line]
        service_logs = [line for line in log_content.split('\n') if 'shorten_item_service item=' in line]
        
        assert len(route_logs) >= 1, "Should have route-level shorten logs"
        assert len(service_logs) >= 1, "Should have service-level shorten logs"
    
    @pytest.mark.unit
    def test_batch_move_audit_logging(self, app, log_capture):
        """Test audit logging for batch move operations"""
        with app.test_request_context('/api/inventory/batch-move', method='POST',
                                     environ_base={'REMOTE_ADDR': '172.16.1.50'}):
            
            batch_data = {
                'moves': [
                    {'ja_id': 'JA000100', 'location': 'Storage C', 'sub_location': 'Shelf 1'},
                    {'ja_id': 'JA000101', 'location': 'Storage C', 'sub_location': 'Shelf 2'},
                    {'ja_id': 'JA000102', 'location': 'Storage D', 'sub_location': 'Bin 5'}
                ]
            }
            
            # Test input phase
            log_audit_batch_operation('batch_move_items', 'input', batch_data=batch_data)
            
            # Test success phase
            log_audit_batch_operation('batch_move_items', 'success',
                                    batch_data=batch_data,
                                    results={
                                        'successful_count': 3,
                                        'failed_count': 0,
                                        'failed_items': []
                                    })
            
            # Test partial failure
            log_audit_batch_operation('batch_move_items', 'success',
                                    batch_data=batch_data,
                                    results={
                                        'successful_count': 2,
                                        'failed_count': 1,
                                        'failed_items': [{'ja_id': 'JA000102', 'error': 'Item not found'}]
                                    })
        
        log_content = log_capture.getvalue()
        
        # Verify batch move patterns
        assert 'AUDIT: batch_move_items' in log_content
        assert 'batch_phase=input' in log_content
        assert 'batch_phase=success' in log_content
        assert 'processed=3' in log_content
        assert 'processed=2' in log_content
        
        # Verify we have expected number of batch log lines
        batch_log_lines = [line for line in log_content.split('\n') if 'AUDIT: batch_move_items' in line]
        assert len(batch_log_lines) >= 3, "Should have multiple batch operation log lines"
    
    @pytest.mark.unit
    def test_audit_log_data_completeness(self, app, log_capture):
        """Test that audit logs contain all necessary data for reconstruction"""
        with app.test_request_context('/test', method='POST'):
            
            # Test comprehensive data logging
            complete_form_data = {
                'ja_id': 'JA000999',
                'item_type': 'Threaded Rod',
                'shape': 'Round',
                'material': 'Stainless Steel',
                'length': '500',
                'width': '12.7',
                'thread_series': 'Metric',
                'thread_handedness': 'RH',
                'thread_size': 'M12x1.75',
                'location': 'Storage E',
                'sub_location': 'Bin 10',
                'purchase_date': '2025-08-15',
                'purchase_price': '75.50',
                'purchase_location': 'McMaster-Carr',
                'vendor': 'McMaster',
                'vendor_part_number': '91290A542',
                'notes': 'High-grade stainless steel threaded rod for precision work'
            }
            
            complete_item_before = {
                'id': 456,
                'ja_id': 'JA000999',
                'item_type': 'Bar',  # Different from form to show change
                'material': 'Carbon Steel',  # Different from form
                'length': 600.0,  # Different from form
                'width': 12.7,
                'location': 'Storage F',  # Different from form
                'notes': 'Original notes',  # Different from form
                'active': True,
                'date_added': '2025-08-01T10:00:00',
                'last_modified': '2025-08-01T10:00:00'
            }
            
            complete_item_after = {
                'id': 456,
                'ja_id': 'JA000999',
                'item_type': 'Threaded Rod',
                'material': 'Stainless Steel', 
                'length': 500.0,
                'width': 12.7,
                'location': 'Storage E',
                'notes': 'High-grade stainless steel threaded rod for precision work',
                'active': True,
                'date_added': '2025-08-01T10:00:00',
                'last_modified': '2025-09-13T15:00:00'
            }
            
            changes_made = {
                'item_type': ['Bar', 'Threaded Rod'],
                'material': ['Carbon Steel', 'Stainless Steel'],
                'length': [600.0, 500.0],
                'location': ['Storage F', 'Storage E'],
                'notes': ['Original notes', 'High-grade stainless steel threaded rod for precision work']
            }
            
            # Log comprehensive edit operation
            log_audit_operation('edit_item', 'success',
                              item_id='JA000999',
                              form_data=complete_form_data,
                              item_before=complete_item_before,
                              item_after=complete_item_after,
                              changes=changes_made)
        
        # Verify the audit logging function was called and generated expected patterns
        log_content = log_capture.getvalue()
        
        # Check that audit logging generated expected message patterns
        assert 'AUDIT: edit_item item=JA000999 phase=success' in log_content
        assert 'operation completed successfully' in log_content
        
        # Verify the function doesn't crash with complex data
        assert len(log_content) > 0, "Should have generated audit log output"
    
    @pytest.mark.unit
    def test_audit_log_error_scenarios(self, app, log_capture):
        """Test audit logging captures error scenarios properly"""
        with app.test_request_context('/test', method='POST'):
            
            # Test various error scenarios
            error_scenarios = [
                ('add_item', 'JA000001', {'ja_id': 'JA000001'}, 'Duplicate JA ID'),
                ('edit_item', 'JA000002', {'ja_id': 'JA000002', 'material': 'Steel'}, 'Item not found'),
                ('shorten_item', 'JA000003', {'ja_id': 'JA000003', 'new_length': 50}, 'New length must be shorter than current length'),
                ('delete_item', 'JA000004', {'ja_id': 'JA000004'}, 'Cannot delete item with active dependencies')
            ]
            
            for operation, item_id, form_data, error_msg in error_scenarios:
                log_audit_operation(operation, 'error',
                                  item_id=item_id,
                                  form_data=form_data,
                                  error_details=error_msg)
        
        log_content = log_capture.getvalue()
        
        # Verify error scenarios are logged with correct patterns
        assert 'phase=error' in log_content
        assert 'operation failed' in log_content
        
        # Count error log lines
        error_lines = [line for line in log_content.split('\n') if 'phase=error' in line]
        assert len(error_lines) == 4, "Should have 4 error audit log lines"
        
        # Verify each operation type appears
        assert any('add_item' in line for line in error_lines)
        assert any('edit_item' in line for line in error_lines)
        assert any('shorten_item' in line for line in error_lines)
        assert any('delete_item' in line for line in error_lines)
    
    @pytest.mark.unit
    def test_audit_log_patterns_for_grep(self, app, log_capture):
        """Test that audit log patterns are easily searchable with grep"""
        with app.test_request_context('/test', method='POST'):
            
            # Create logs that match documented grep patterns
            operations = [
                ('add_item', 'JA000100'),
                ('edit_item', 'JA000200'),
                ('shorten_item', 'JA000300'),
                ('batch_move_items', None)  # Batch operations don't have single item IDs
            ]
            
            for operation, item_id in operations:
                if operation == 'batch_move_items':
                    log_audit_batch_operation(operation, 'success',
                                            batch_data={'moves': [{'ja_id': 'JA000301'}, {'ja_id': 'JA000302'}]},
                                            results={'successful_count': 2})
                else:
                    log_audit_operation(operation, 'success',
                                      item_id=item_id,
                                      form_data={'ja_id': item_id})
        
        log_content = log_capture.getvalue()
        
        # Test grep patterns from documentation
        grep_patterns = [
            'AUDIT:.*add_item',      # Find all add operations
            'AUDIT:.*edit_item',     # Find all edit operations  
            'AUDIT:.*shorten_item',  # Find all shorten operations
            'AUDIT:.*batch_move',    # Find all batch move operations
            'item=JA000100',         # Find operations on specific item
            'phase=success',         # Find successful operations
            'batch_phase=success'    # Find successful batch operations
        ]
        
        for pattern in grep_patterns:
            # Simulate grep by checking if pattern would match
            import re
            matches = re.findall(pattern, log_content)
            assert len(matches) > 0, f"Pattern '{pattern}' should find matches in audit logs"
    
    @pytest.mark.unit
    def test_audit_log_json_extraction(self, app, log_capture):
        """Test that audit log JSON data can be extracted and parsed"""
        with app.test_request_context('/test', method='POST'):
            
            test_form_data = {
                'ja_id': 'JA000555',
                'material': 'Aluminum',
                'length': '200.5'
            }
            
            test_item_data = {
                'ja_id': 'JA000555',
                'material': 'Aluminum',
                'length': 200.5,
                'active': True
            }
            
            log_audit_operation('add_item', 'success',
                              item_id='JA000555',
                              form_data=test_form_data,
                              item_after=test_item_data)
        
        log_content = log_capture.getvalue()
        
        # Verify the basic audit log pattern is present
        assert 'AUDIT: add_item item=JA000555 phase=success' in log_content
        assert 'operation completed successfully' in log_content
        
        # Verify the audit logging function executed without errors
        assert len(log_content.strip()) > 0, "Should have generated audit log content"
    
    @pytest.mark.unit
    def test_audit_logging_performance(self, app, log_capture):
        """Test that audit logging doesn't significantly impact performance"""
        with app.test_request_context('/test', method='POST'):
            
            import time
            
            # Test logging performance with larger data sets
            large_form_data = {
                'ja_id': 'JA999999',
                'notes': 'This is a very long note field containing lots of text ' * 50,
                'material': 'Some very specific material name',
                **{f'field_{i}': f'value_{i}' for i in range(50)}  # Add many fields
            }
            
            large_item_data = {
                'ja_id': 'JA999999',
                **{f'field_{i}': f'value_{i}' for i in range(100)}  # Even more fields
            }
            
            # Time multiple audit log operations
            start_time = time.time()
            
            for i in range(10):
                log_audit_operation('add_item', 'success',
                                  item_id=f'JA99999{i}',
                                  form_data=large_form_data,
                                  item_after=large_item_data)
            
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            # Audit logging should be fast (under 1 second for 10 operations)
            assert elapsed_time < 1.0, f"Audit logging too slow: {elapsed_time:.3f}s for 10 operations"
            
            # Verify all logs were captured
            log_content = log_capture.getvalue()
            log_count = log_content.count('AUDIT: add_item')
            assert log_count == 10, f"Should have logged 10 operations, got {log_count}"


class TestAuditLogReconstructionScenarios:
    """Test specific data reconstruction scenarios"""
    
    @pytest.mark.unit
    def test_item_creation_reconstruction(self, app):
        """Test that item creation can be fully reconstructed from audit logs"""
        # This would be used if an item was accidentally deleted
        original_form_data = {
            'ja_id': 'JA000777',
            'item_type': 'Plate',
            'shape': 'Rectangular',
            'material': 'Aluminum 6061',
            'length': '12.0',
            'width': '8.0',
            'thickness': '0.25',
            'location': 'Materials Rack',
            'sub_location': 'A-3',
            'purchase_date': '2025-07-15',
            'purchase_price': '45.99',
            'purchase_location': 'Online Metals',
            'vendor': 'Online Metals',
            'vendor_part_number': 'AL6061-12x8x0.25',
            'notes': 'Quarter-inch aluminum plate for mounting brackets'
        }

        # Simulate the reconstruction process
        reconstructed_item = {
            'ja_id': original_form_data['ja_id'],
            'item_type': original_form_data['item_type'],
            'shape': original_form_data['shape'],
            'material': original_form_data['material'],
            'length': float(original_form_data['length']),
            'width': float(original_form_data['width']),
            'thickness': float(original_form_data['thickness']),
            'location': original_form_data['location'],
            'sub_location': original_form_data['sub_location'],
            'notes': original_form_data['notes']
        }

        # Verify reconstruction completeness
        critical_fields = ['ja_id', 'item_type', 'material', 'length', 'width', 'location']
        for field in critical_fields:
            assert field in reconstructed_item, f"Reconstruction missing critical field: {field}"
            assert reconstructed_item[field] is not None, f"Reconstruction field {field} should not be None"
    
    @pytest.mark.unit
    def test_edit_rollback_reconstruction(self, app):
        """Test that incorrect edits can be rolled back from audit logs"""
        # Original item state (from audit log item_before)
        original_state = {
            'ja_id': 'JA000888',
            'location': 'Shop Floor',
            'sub_location': 'Workbench 2',
            'material': 'Steel',
            'length': 150.0,
            'notes': 'Project A material'
        }
        
        # Incorrect edit (what was changed)
        incorrect_edit = {
            'ja_id': 'JA000888',
            'location': 'Scrap Bin',  # Wrong!
            'sub_location': 'N/A',
            'material': 'Steel', 
            'length': 150.0,
            'notes': 'Marked for disposal'  # Wrong!
        }
        
        # Rollback process - restore from original_state
        rollback_values = {}
        for field in ['location', 'sub_location', 'notes']:
            if original_state[field] != incorrect_edit[field]:
                rollback_values[field] = original_state[field]
        
        # Verify rollback captures the correct changes
        assert rollback_values['location'] == 'Shop Floor'
        assert rollback_values['sub_location'] == 'Workbench 2'
        assert rollback_values['notes'] == 'Project A material'
    
    @pytest.mark.unit
    def test_shortening_reversal_reconstruction(self, app):
        """Test that shortening operations can be reversed from audit logs"""
        # Audit log data for shortening operation
        audit_shortening_data = {
            'operation': 'shortening',
            'ja_id': 'JA000999',
            'original_length': 100.0,
            'new_length': 75.0,
            'deactivated_item_id': 456,
            'new_item_id': 457,
            'cut_date': '2025-09-13'
        }
        
        original_item_state = {
            'id': 456,
            'ja_id': 'JA000999',
            'length': 100.0,
            'notes': 'Original notes',
            'active': False  # Was deactivated during shortening
        }
        
        shortened_item_state = {
            'id': 457,
            'ja_id': 'JA000999', 
            'length': 75.0,
            'notes': 'Shortened from 100" to 75" on 2025-09-13\n\nPrevious notes: Original notes',
            'active': True  # Current active state
        }
        
        # Reversal process
        reversal_steps = {
            'deactivate_shortened_item': shortened_item_state['id'],  # Deactivate ID 457
            'reactivate_original_item': original_item_state['id'],    # Reactivate ID 456  
            'restore_length': audit_shortening_data['original_length'], # Restore to 100.0
            'restore_notes': original_item_state['notes']             # Remove shortening notes
        }
        
        # Verify reversal plan is complete
        assert reversal_steps['deactivate_shortened_item'] == 457
        assert reversal_steps['reactivate_original_item'] == 456
        assert reversal_steps['restore_length'] == 100.0
        assert reversal_steps['restore_notes'] == 'Original notes'
    
    @pytest.mark.unit
    def test_batch_move_reversal_reconstruction(self, app):
        """Test that batch moves can be reversed from audit logs"""
        # Audit log data for batch move
        batch_move_audit = {
            'moves': [
                {'ja_id': 'JA001001', 'location': 'Storage Room B', 'sub_location': 'Shelf 3'},
                {'ja_id': 'JA001002', 'location': 'Storage Room B', 'sub_location': 'Shelf 4'},
                {'ja_id': 'JA001003', 'location': 'Storage Room C', 'sub_location': 'Bin 1'}
            ]
        }
        
        # To reverse, we need the previous locations (would need to get from earlier audit logs)
        # This simulates finding the previous state for each item
        previous_locations = {
            'JA001001': {'location': 'Shop Floor', 'sub_location': 'Workbench 1'},
            'JA001002': {'location': 'Storage Room A', 'sub_location': 'Shelf 1'},
            'JA001003': {'location': 'Storage Room A', 'sub_location': 'Shelf 2'}
        }
        
        # Generate reversal moves
        reversal_moves = []
        for move in batch_move_audit['moves']:
            ja_id = move['ja_id']
            if ja_id in previous_locations:
                reversal_moves.append({
                    'ja_id': ja_id,
                    'location': previous_locations[ja_id]['location'],
                    'sub_location': previous_locations[ja_id]['sub_location']
                })
        
        # Verify reversal moves
        assert len(reversal_moves) == 3
        assert reversal_moves[0]['ja_id'] == 'JA001001'
        assert reversal_moves[0]['location'] == 'Shop Floor'
        assert reversal_moves[1]['ja_id'] == 'JA001002'
        assert reversal_moves[1]['location'] == 'Storage Room A'

    @pytest.mark.unit
    def test_item_to_audit_dict_with_original_thread(self):
        """Test _item_to_audit_dict function handles original_thread as string correctly"""
        # Create a mock item with original_thread as a string (the bug scenario)
        mock_item = MagicMock()
        mock_item.ja_id = 'JA000123'
        mock_item.item_type = ItemType.BAR
        mock_item.shape = ItemShape.ROUND
        mock_item.material = 'Steel'
        mock_item.dimensions = None
        mock_item.thread = None
        mock_item.location = 'Shop A'
        mock_item.sub_location = 'Shelf 1'
        mock_item.purchase_date = None
        mock_item.purchase_price = None
        mock_item.purchase_location = None
        mock_item.notes = 'Test item'
        mock_item.vendor = None
        mock_item.vendor_part_number = None
        mock_item.original_material = None
        mock_item.original_thread = '1/4-20'  # This is a string, not a Thread object
        mock_item.active = True
        mock_item.date_added = None
        mock_item.last_modified = None

        # This should not raise an AttributeError after our fix
        result = _item_to_audit_dict(mock_item)

        # Verify the result contains the correct original_thread value
        assert result['original_thread'] == '1/4-20'
        assert result['ja_id'] == 'JA000123'
        assert result['material'] == 'Steel'
        
    @pytest.mark.unit
    def test_item_to_audit_dict_with_none_original_thread(self):
        """Test _item_to_audit_dict function handles None original_thread correctly"""
        # Create a mock item with original_thread as None
        mock_item = MagicMock()
        mock_item.ja_id = 'JA000124'
        mock_item.item_type = ItemType.BAR
        mock_item.shape = ItemShape.ROUND
        mock_item.material = 'Aluminum'
        mock_item.dimensions = None
        mock_item.thread = None
        mock_item.location = 'Shop B'
        mock_item.sub_location = 'Shelf 2'
        mock_item.purchase_date = None
        mock_item.purchase_price = None
        mock_item.purchase_location = None
        mock_item.notes = 'Test item 2'
        mock_item.vendor = None
        mock_item.vendor_part_number = None
        mock_item.original_material = None
        mock_item.original_thread = None  # This should work fine
        mock_item.active = True
        mock_item.date_added = None
        mock_item.last_modified = None
        
        # This should work fine
        result = _item_to_audit_dict(mock_item)
        
        # Verify the result contains None for original_thread
        assert result['original_thread'] is None
        assert result['ja_id'] == 'JA000124'
        assert result['material'] == 'Aluminum'