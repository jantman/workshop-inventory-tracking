"""
Unit tests for models module.

Tests Item, Dimensions, Thread, and other model classes.
"""

import pytest
from decimal import Decimal
from app.models import (
    Item, ItemType, ItemShape, Dimensions, Thread, ThreadSeries, 
    ThreadHandedness
)
from app.exceptions import ValidationError


class TestDimensions:
    """Tests for Dimensions class"""
    
    @pytest.mark.unit
    def test_dimensions_creation_basic(self):
        """Test basic dimensions creation"""
        dims = Dimensions(length_mm=Decimal('100'), width_mm=Decimal('50'))
        
        assert dims.length_mm == Decimal('100')
        assert dims.width_mm == Decimal('50')
        assert dims.height_mm is None
        assert dims.diameter_mm is None
    
    @pytest.mark.unit
    def test_dimensions_creation_all_fields(self):
        """Test dimensions creation with all fields"""
        dims = Dimensions(
            length_mm=Decimal('1000'),
            width_mm=Decimal('200'),
            height_mm=Decimal('50'),
            diameter_mm=Decimal('25')
        )
        
        assert dims.length_mm == Decimal('1000')
        assert dims.width_mm == Decimal('200')
        assert dims.height_mm == Decimal('50')
        assert dims.diameter_mm == Decimal('25')
    
    @pytest.mark.unit
    def test_dimensions_validation_negative(self):
        """Test validation fails for negative values"""
        with pytest.raises(ValidationError, match="must be positive"):
            Dimensions(length_mm=Decimal('-100'))
    
    @pytest.mark.unit
    def test_dimensions_validation_zero(self):
        """Test validation fails for zero values"""
        with pytest.raises(ValidationError, match="must be positive"):
            Dimensions(diameter_mm=Decimal('0'))
    
    @pytest.mark.unit
    def test_dimensions_serialization(self):
        """Test dimensions can be serialized to dict"""
        dims = Dimensions(length_mm=Decimal('100'), diameter_mm=Decimal('25'))
        data = dims.to_dict()
        
        expected = {
            'length_mm': Decimal('100'),
            'width_mm': None,
            'height_mm': None,
            'diameter_mm': Decimal('25')
        }
        assert data == expected


class TestThread:
    """Tests for Thread class"""
    
    @pytest.mark.unit
    def test_thread_creation_basic(self):
        """Test basic thread creation"""
        thread = Thread(
            series=ThreadSeries.METRIC_COARSE,
            handedness=ThreadHandedness.RIGHT_HAND,
            length_mm=Decimal('100')
        )
        
        assert thread.series == ThreadSeries.METRIC_COARSE
        assert thread.handedness == ThreadHandedness.RIGHT_HAND
        assert thread.length_mm == Decimal('100')
    
    @pytest.mark.unit
    def test_thread_validation_negative_length(self):
        """Test validation fails for negative thread length"""
        with pytest.raises(ValidationError, match="Thread length must be positive"):
            Thread(
                series=ThreadSeries.METRIC_COARSE,
                handedness=ThreadHandedness.RIGHT_HAND,
                length_mm=Decimal('-50')
            )
    
    @pytest.mark.unit
    def test_thread_serialization(self):
        """Test thread can be serialized to dict"""
        thread = Thread(
            series=ThreadSeries.UNC,
            handedness=ThreadHandedness.LEFT_HAND,
            length_mm=Decimal('200')
        )
        data = thread.to_dict()
        
        expected = {
            'series': ThreadSeries.UNC,
            'handedness': ThreadHandedness.LEFT_HAND,
            'length_mm': Decimal('200')
        }
        assert data == expected


class TestItem:
    """Tests for Item class"""
    
    @pytest.mark.unit
    def test_item_creation_minimal(self):
        """Test item creation with minimal required fields"""
        item = Item(
            ja_id='TEST001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel'
        )
        
        assert item.ja_id == 'TEST001'
        assert item.item_type == ItemType.ROD
        assert item.shape == ItemShape.ROUND
        assert item.material == 'Steel'
        assert item.active is True  # Default value
        assert item.dimensions is None
        assert item.thread is None
        assert item.location == ''
        assert item.notes == ''
    
    @pytest.mark.unit
    def test_item_creation_complete(self):
        """Test item creation with all fields"""
        dimensions = Dimensions(length_mm=Decimal('1000'), diameter_mm=Decimal('25'))
        thread = Thread(
            series=ThreadSeries.METRIC_COARSE,
            handedness=ThreadHandedness.RIGHT_HAND,
            length_mm=Decimal('1000')
        )
        
        item = Item(
            ja_id='TEST002',
            item_type=ItemType.THREADED_ROD,
            shape=ItemShape.ROUND,
            material='Stainless Steel',
            dimensions=dimensions,
            thread=thread,
            location='Storage A',
            notes='Test notes',
            parent_ja_id='PARENT001',
            active=False
        )
        
        assert item.ja_id == 'TEST002'
        assert item.item_type == ItemType.THREADED_ROD
        assert item.shape == ItemShape.ROUND
        assert item.material == 'Stainless Steel'
        assert item.dimensions == dimensions
        assert item.thread == thread
        assert item.location == 'Storage A'
        assert item.notes == 'Test notes'
        assert item.parent_ja_id == 'PARENT001'
        assert item.active is False
    
    @pytest.mark.unit
    def test_item_validation_empty_ja_id(self):
        """Test validation fails for empty JA_ID"""
        with pytest.raises(ValidationError, match="JA_ID cannot be empty"):
            Item(
                ja_id='',
                item_type=ItemType.ROD,
                shape=ItemShape.ROUND,
                material='Steel'
            )
    
    @pytest.mark.unit
    def test_item_validation_empty_material(self):
        """Test validation fails for empty material"""
        with pytest.raises(ValidationError, match="Material cannot be empty"):
            Item(
                ja_id='TEST001',
                item_type=ItemType.ROD,
                shape=ItemShape.ROUND,
                material=''
            )
    
    @pytest.mark.unit
    def test_item_validation_whitespace_ja_id(self):
        """Test validation fails for whitespace-only JA_ID"""
        with pytest.raises(ValidationError, match="JA_ID cannot be empty"):
            Item(
                ja_id='   ',
                item_type=ItemType.ROD,
                shape=ItemShape.ROUND,
                material='Steel'
            )
    
    @pytest.mark.unit
    def test_item_serialization_minimal(self):
        """Test item serialization with minimal fields"""
        item = Item(
            ja_id='TEST001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel'
        )
        
        data = item.to_dict()
        
        expected = {
            'ja_id': 'TEST001',
            'item_type': ItemType.ROD,
            'shape': ItemShape.ROUND,
            'material': 'Steel',
            'dimensions': None,
            'thread': None,
            'location': '',
            'notes': '',
            'parent_ja_id': None,
            'active': True
        }
        assert data == expected
    
    @pytest.mark.unit
    def test_item_serialization_complete(self):
        """Test item serialization with all fields"""
        dimensions = Dimensions(length_mm=Decimal('1000'), diameter_mm=Decimal('25'))
        thread = Thread(
            series=ThreadSeries.METRIC_COARSE,
            handedness=ThreadHandedness.RIGHT_HAND,
            length_mm=Decimal('1000')
        )
        
        item = Item(
            ja_id='TEST002',
            item_type=ItemType.THREADED_ROD,
            shape=ItemShape.ROUND,
            material='Stainless Steel',
            dimensions=dimensions,
            thread=thread,
            location='Storage A',
            notes='Test notes',
            parent_ja_id='PARENT001',
            active=False
        )
        
        data = item.to_dict()
        
        expected = {
            'ja_id': 'TEST002',
            'item_type': ItemType.THREADED_ROD,
            'shape': ItemShape.ROUND,
            'material': 'Stainless Steel',
            'dimensions': dimensions.to_dict(),
            'thread': thread.to_dict(),
            'location': 'Storage A',
            'notes': 'Test notes',
            'parent_ja_id': 'PARENT001',
            'active': False
        }
        assert data == expected
    
    @pytest.mark.unit
    def test_item_equality(self):
        """Test item equality comparison"""
        item1 = Item(
            ja_id='TEST001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel'
        )
        
        item2 = Item(
            ja_id='TEST001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel'
        )
        
        item3 = Item(
            ja_id='TEST002',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel'
        )
        
        assert item1 == item2
        assert item1 != item3
    
    @pytest.mark.unit
    def test_item_string_representation(self):
        """Test item string representation"""
        item = Item(
            ja_id='TEST001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel'
        )
        
        str_repr = str(item)
        assert 'TEST001' in str_repr
        assert 'Steel' in str_repr
        assert 'Rod' in str_repr


class TestEnums:
    """Tests for enum classes"""
    
    @pytest.mark.unit
    def test_item_type_values(self):
        """Test ItemType enum values"""
        assert ItemType.ROD.value == 'Rod'
        assert ItemType.THREADED_ROD.value == 'Threaded Rod'
        assert ItemType.SHEET.value == 'Sheet'
        assert ItemType.TUBE.value == 'Tube'
        assert ItemType.BAR.value == 'Bar'
    
    @pytest.mark.unit
    def test_item_shape_values(self):
        """Test ItemShape enum values"""
        assert ItemShape.ROUND.value == 'Round'
        assert ItemShape.SQUARE.value == 'Square'
        assert ItemShape.RECTANGULAR.value == 'Rectangular'
        assert ItemShape.HEXAGONAL.value == 'Hexagonal'
        assert ItemShape.OCTAGONAL.value == 'Octagonal'
    
    @pytest.mark.unit
    def test_thread_series_values(self):
        """Test ThreadSeries enum values"""
        assert ThreadSeries.METRIC.value == 'Metric'
        assert ThreadSeries.UNC.value == 'UNC'
        assert ThreadSeries.UNF.value == 'UNF'
    
    @pytest.mark.unit
    def test_thread_handedness_values(self):
        """Test ThreadHandedness enum values"""
        assert ThreadHandedness.RIGHT.value == 'RH'
        assert ThreadHandedness.LEFT.value == 'LH'