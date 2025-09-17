"""
Test audit data inclusion in JSON logs

This test verifies that the fix for issue #10 is working correctly - 
ensuring that audit logging includes all necessary data (form_data, item_before, 
item_after, changes) in the JSON log output for data reconstruction.
"""

import pytest
import json
import io
import logging

from app.logging_config import log_audit_operation, JSONFormatter


class TestAuditDataInJSONLogs:
    """Test that audit data is properly included in JSON formatted logs"""

    def setup_method(self):
        """Set up log capture for each test"""
        self.log_capture = io.StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        self.handler.setFormatter(JSONFormatter())

        self.logger = logging.getLogger('test_audit_fix')
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()  # Clear any existing handlers
        self.logger.addHandler(self.handler)

    def teardown_method(self):
        """Clean up after each test"""
        self.logger.handlers.clear()

    @pytest.mark.unit
    def test_form_data_present_in_add_operation(self):
        """Test that user form data is included for add operations"""
        form_data = {
            'ja_id': 'JA000123',
            'item_type': 'STOCK',
            'shape': 'BAR',
            'material': 'Steel',
            'length': '12.0',
            'width': '2.0',
            'location': 'Shop A',
            'notes': 'Test item for reconstruction'
        }

        log_audit_operation('add_item', 'input', 
                           item_id='JA000123',
                           form_data=form_data,
                           logger_name='test_audit_fix')

        log_output = self.log_capture.getvalue().strip()
        log_entry = json.loads(log_output)

        # Verify core audit structure
        assert log_entry['audit_operation'] == 'add_item'
        assert log_entry['audit_phase'] == 'input'
        assert log_entry['item_id'] == 'JA000123'
        
        # Verify audit_data section exists and contains form_data
        assert 'audit_data' in log_entry
        assert 'form_data' in log_entry['audit_data']
        
        # Verify all user input is captured for reconstruction
        logged_form = log_entry['audit_data']['form_data']
        assert logged_form['ja_id'] == 'JA000123'
        assert logged_form['item_type'] == 'STOCK'
        assert logged_form['shape'] == 'BAR'
        assert logged_form['material'] == 'Steel'
        assert logged_form['length'] == '12.0'
        assert logged_form['width'] == '2.0'
        assert logged_form['location'] == 'Shop A'
        assert logged_form['notes'] == 'Test item for reconstruction'

    @pytest.mark.unit
    def test_before_after_states_present_in_edit_operation(self):
        """Test that before/after states are included for edit operations"""
        form_data = {
            'ja_id': 'JA000456',
            'item_type': 'STOCK',
            'material': 'Aluminum',
            'length': '14.0',
            'notes': 'Updated item'
        }
        
        item_before = {
            'ja_id': 'JA000456',
            'item_type': 'STOCK',
            'material': 'Steel',
            'length': '12.0',
            'notes': 'Original item'
        }

        item_after = {
            'ja_id': 'JA000456',
            'item_type': 'STOCK',
            'material': 'Aluminum',
            'length': '14.0',
            'notes': 'Updated item'
        }

        changes = {
            'material': {'before': 'Steel', 'after': 'Aluminum'},
            'length': {'before': '12.0', 'after': '14.0'},
            'notes': {'before': 'Original item', 'after': 'Updated item'}
        }

        log_audit_operation('edit_item', 'success',
                           item_id='JA000456',
                           form_data=form_data,
                           item_before=item_before,
                           item_after=item_after,
                           changes=changes,
                           logger_name='test_audit_fix')

        log_output = self.log_capture.getvalue().strip()
        log_entry = json.loads(log_output)

        # Verify audit structure
        assert log_entry['audit_operation'] == 'edit_item'
        assert log_entry['audit_phase'] == 'success'
        assert log_entry['item_id'] == 'JA000456'

        # Verify all required audit data is present
        audit_data = log_entry['audit_data']
        assert 'form_data' in audit_data
        assert 'item_before' in audit_data
        assert 'item_after' in audit_data
        assert 'changes' in audit_data

        # Verify form_data captures user input
        assert audit_data['form_data']['material'] == 'Aluminum'
        assert audit_data['form_data']['length'] == '14.0'

        # Verify item_before shows original state
        assert audit_data['item_before']['material'] == 'Steel'
        assert audit_data['item_before']['length'] == '12.0'
        assert audit_data['item_before']['notes'] == 'Original item'

        # Verify item_after shows final state
        assert audit_data['item_after']['material'] == 'Aluminum'
        assert audit_data['item_after']['length'] == '14.0'
        assert audit_data['item_after']['notes'] == 'Updated item'

        # Verify changes show specific field modifications
        assert audit_data['changes']['material']['before'] == 'Steel'
        assert audit_data['changes']['material']['after'] == 'Aluminum'
        assert audit_data['changes']['length']['before'] == '12.0'
        assert audit_data['changes']['length']['after'] == '14.0'

    @pytest.mark.unit
    def test_error_details_present_in_error_scenarios(self):
        """Test that error details are included for error scenarios"""
        form_data = {'ja_id': 'JA000789', 'item_type': 'INVALID'}
        error_details = 'Invalid item type: INVALID'

        log_audit_operation('add_item', 'error',
                           item_id='JA000789',
                           form_data=form_data,
                           error_details=error_details,
                           logger_name='test_audit_fix')

        log_output = self.log_capture.getvalue().strip()
        log_entry = json.loads(log_output)

        # Verify error logging
        assert log_entry['audit_operation'] == 'add_item'
        assert log_entry['audit_phase'] == 'error'
        assert log_entry['item_id'] == 'JA000789'

        # Verify error data is captured
        audit_data = log_entry['audit_data']
        assert 'form_data' in audit_data
        assert 'error_details' in audit_data
        assert audit_data['error_details'] == 'Invalid item type: INVALID'
        assert audit_data['form_data']['ja_id'] == 'JA000789'

    @pytest.mark.unit
    def test_message_format_unchanged_for_compatibility(self):
        """Test that human-readable message format is unchanged for grep compatibility"""
        log_audit_operation('edit_item', 'input',
                           item_id='JA000999',
                           form_data={'ja_id': 'JA000999'},
                           logger_name='test_audit_fix')

        log_output = self.log_capture.getvalue().strip()
        log_entry = json.loads(log_output)

        # Verify message format is still grep-friendly
        expected_message = "AUDIT: edit_item item=JA000999 phase=input capturing user input for reconstruction"
        assert log_entry['message'] == expected_message

        # But now we also have the structured data
        assert 'audit_data' in log_entry
        assert 'form_data' in log_entry['audit_data']