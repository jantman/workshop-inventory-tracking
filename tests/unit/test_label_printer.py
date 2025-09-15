"""
Unit tests for the label printing service.

Tests the label printing functionality including service functions,
test mode short-circuiting, and API endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
import json
from app.services.label_printer import (
    LABEL_TYPES, 
    generate_and_print_label, 
    print_label_for_ja_id, 
    get_available_label_types,
    get_label_type_config
)


class TestLabelPrinterService:
    """Test the label printer service functions"""
    
    @pytest.mark.unit
    def test_label_types_defined(self):
        """Test that LABEL_TYPES is properly defined"""
        assert isinstance(LABEL_TYPES, dict)
        assert len(LABEL_TYPES) == 6
        
        expected_types = {
            'Sato 1x2', 'Sato 1x2 Flag', 'Sato 2x4', 
            'Sato 2x4 Flag', 'Sato 4x6', 'Sato 4x6 Flag'
        }
        assert set(LABEL_TYPES.keys()) == expected_types
    
    @pytest.mark.unit 
    def test_label_type_config_structure(self):
        """Test that each label type has required configuration"""
        required_keys = {'lp_options', 'maxlen_inches', 'lp_width_px', 'fixed_len_px', 'lp_dpi'}
        
        for label_type, config in LABEL_TYPES.items():
            assert isinstance(config, dict)
            # All configs should have base required keys
            for key in required_keys:
                assert key in config, f"Missing {key} in {label_type}"
            
            # Flag mode types should have flag_mode=True
            if 'Flag' in label_type:
                assert config.get('flag_mode') is True
            else:
                assert config.get('flag_mode', False) is False
    
    @pytest.mark.unit
    def test_get_available_label_types(self):
        """Test getting list of available label types"""
        types = get_available_label_types()
        assert isinstance(types, list)
        assert len(types) == 6
        assert 'Sato 1x2' in types
        assert 'Sato 4x6 Flag' in types
    
    @pytest.mark.unit
    def test_get_label_type_config_valid(self):
        """Test getting configuration for valid label type"""
        config = get_label_type_config('Sato 1x2')
        assert config is not None
        assert isinstance(config, dict)
        assert config['lp_dpi'] == 305
        assert config['maxlen_inches'] == 2.0
    
    @pytest.mark.unit
    def test_get_label_type_config_invalid(self):
        """Test getting configuration for invalid label type"""
        config = get_label_type_config('Invalid Type')
        assert config is None
    
    @pytest.mark.unit
    def test_generate_and_print_label_test_mode(self, app):
        """Test that label printing is short-circuited in test mode"""
        with app.app_context():
            # Ensure we're in test mode
            app.config['TESTING'] = True
            
            # Mock the printer classes to ensure they're not called
            with patch('app.services.label_printer.BarcodeLabelGenerator') as mock_generator, \
                 patch('app.services.label_printer.LpPrinter') as mock_printer:
                
                generate_and_print_label(
                    barcode_value='JA123456',
                    lp_options='-d test',
                    maxlen_inches=2.0,
                    lp_width_px=305,
                    fixed_len_px=610,
                    lp_dpi=305
                )
                
                # Verify that printing components were not called in test mode
                mock_generator.assert_not_called()
                mock_printer.assert_not_called()
    
    @pytest.mark.unit
    def test_generate_and_print_label_production_mode(self, app):
        """Test that label printing works in production mode"""
        with app.app_context():
            # Set to production mode
            app.config['TESTING'] = False
            
            # Mock the printer classes
            with patch('app.services.label_printer.BarcodeLabelGenerator') as mock_generator_class, \
                 patch('app.services.label_printer.LpPrinter') as mock_printer_class:
                
                mock_generator = MagicMock()
                mock_generator.file_obj = MagicMock()
                mock_generator_class.return_value = mock_generator
                
                mock_printer = MagicMock()
                mock_printer_class.return_value = mock_printer
                
                generate_and_print_label(
                    barcode_value='JA123456',
                    lp_options='-d test',
                    maxlen_inches=2.0,
                    lp_width_px=305,
                    fixed_len_px=610,
                    lp_dpi=305
                )
                
                # Verify that printing components were called in production mode
                mock_generator_class.assert_called_once()
                mock_printer_class.assert_called_once_with('-d test')
                mock_printer.print_images.assert_called_once()
    
    @pytest.mark.unit
    def test_generate_and_print_label_flag_mode(self, app):
        """Test label printing with flag mode enabled"""
        with app.app_context():
            # Set to production mode  
            app.config['TESTING'] = False
            
            with patch('app.services.label_printer.FlagModeGenerator') as mock_flag_generator_class, \
                 patch('app.services.label_printer.BarcodeLabelGenerator') as mock_generator_class, \
                 patch('app.services.label_printer.LpPrinter') as mock_printer_class:
                
                mock_generator = MagicMock()
                mock_generator.file_obj = MagicMock()
                mock_flag_generator_class.return_value = mock_generator
                
                mock_printer = MagicMock()
                mock_printer_class.return_value = mock_printer
                
                generate_and_print_label(
                    barcode_value='JA123456',
                    lp_options='-d test',
                    maxlen_inches=2.0,
                    lp_width_px=305,
                    fixed_len_px=610,
                    flag_mode=True,
                    lp_dpi=305
                )
                
                # Verify FlagModeGenerator was used instead of BarcodeLabelGenerator
                mock_flag_generator_class.assert_called_once()
                mock_generator_class.assert_not_called()
                mock_printer_class.assert_called_once()
    
    @pytest.mark.unit
    def test_print_label_for_ja_id_valid(self, app):
        """Test printing label for valid JA ID and label type"""
        with app.app_context():
            app.config['TESTING'] = True
            
            with patch('app.services.label_printer.generate_and_print_label') as mock_print:
                print_label_for_ja_id('JA123456', 'Sato 1x2')
                
                mock_print.assert_called_once()
                args, kwargs = mock_print.call_args
                assert kwargs['barcode_value'] == 'JA123456'
                assert kwargs['lp_dpi'] == 305
                assert kwargs['maxlen_inches'] == 2.0
    
    @pytest.mark.unit
    def test_print_label_for_ja_id_invalid_type(self, app):
        """Test printing label with invalid label type"""
        with app.app_context():
            with pytest.raises(ValueError) as exc_info:
                print_label_for_ja_id('JA123456', 'Invalid Type')
            
            assert "Invalid label type" in str(exc_info.value)
            assert "Valid types:" in str(exc_info.value)
    
    @pytest.mark.unit
    def test_print_label_for_ja_id_flag_mode(self, app):
        """Test printing flag mode label"""
        with app.app_context():
            app.config['TESTING'] = True
            
            with patch('app.services.label_printer.generate_and_print_label') as mock_print:
                print_label_for_ja_id('JA123456', 'Sato 1x2 Flag')
                
                mock_print.assert_called_once()
                args, kwargs = mock_print.call_args
                assert kwargs['barcode_value'] == 'JA123456'
                assert kwargs['flag_mode'] is True


class TestLabelPrinterAPI:
    """Test the label printer API endpoints"""
    
    @pytest.mark.unit
    def test_get_label_types_endpoint(self, client):
        """Test GET /api/labels/types endpoint"""
        response = client.get('/api/labels/types')
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'label_types' in data
        assert isinstance(data['label_types'], list)
        assert len(data['label_types']) == 6
        assert 'Sato 1x2' in data['label_types']
    
    @pytest.mark.unit
    def test_print_label_endpoint_success(self, client):
        """Test POST /api/labels/print with valid data"""
        with patch('app.services.label_printer.print_label_for_ja_id') as mock_print:
            response = client.post('/api/labels/print',
                json={'ja_id': 'JA123456', 'label_type': 'Sato 1x2'},
                content_type='application/json')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert data['ja_id'] == 'JA123456'
            assert data['label_type'] == 'Sato 1x2'
            assert 'message' in data
            
            mock_print.assert_called_once_with('JA123456', 'Sato 1x2')
    
    @pytest.mark.unit
    def test_print_label_endpoint_missing_ja_id(self, client):
        """Test POST /api/labels/print without JA ID"""
        response = client.post('/api/labels/print',
            json={'label_type': 'Sato 1x2'},
            content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'ja_id is required' in data['error']
    
    @pytest.mark.unit
    def test_print_label_endpoint_missing_label_type(self, client):
        """Test POST /api/labels/print without label type"""
        response = client.post('/api/labels/print',
            json={'ja_id': 'JA123456'},
            content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'label_type is required' in data['error']
    
    @pytest.mark.unit
    def test_print_label_endpoint_invalid_ja_id_format(self, client):
        """Test POST /api/labels/print with invalid JA ID format"""
        response = client.post('/api/labels/print',
            json={'ja_id': 'INVALID', 'label_type': 'Sato 1x2'},
            content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Invalid JA ID format' in data['error']
    
    @pytest.mark.unit
    def test_print_label_endpoint_invalid_label_type(self, client):
        """Test POST /api/labels/print with invalid label type"""
        response = client.post('/api/labels/print',
            json={'ja_id': 'JA123456', 'label_type': 'Invalid Type'},
            content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'Invalid label type' in data['error']
    
    @pytest.mark.unit
    def test_print_label_endpoint_print_error(self, client):
        """Test POST /api/labels/print with printing error"""
        with patch('app.services.label_printer.print_label_for_ja_id', 
                   side_effect=Exception('Printer error')):
            response = client.post('/api/labels/print',
                json={'ja_id': 'JA123456', 'label_type': 'Sato 1x2'},
                content_type='application/json')
            
            assert response.status_code == 500
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Failed to print label' in data['error']
    
    @pytest.mark.unit
    def test_print_label_endpoint_validation_error(self, client):
        """Test POST /api/labels/print with validation error from service"""
        with patch('app.services.label_printer.print_label_for_ja_id', 
                   side_effect=ValueError('Custom validation error')):
            response = client.post('/api/labels/print',
                json={'ja_id': 'JA123456', 'label_type': 'Sato 1x2'},
                content_type='application/json')
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data['success'] is False
            assert 'Custom validation error' in data['error']