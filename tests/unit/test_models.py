"""
Unit tests for models module.

Tests Item, Dimensions, Thread, and other model classes.
"""

import pytest
from decimal import Decimal
from app.models import (
    ItemType, ItemShape, Dimensions, Thread, ThreadSeries, 
    ThreadHandedness
)
from app.database import InventoryItem
from app.exceptions import ValidationError


class TestDimensions:
    """Tests for Dimensions class"""
    
    @pytest.mark.unit
    def test_dimensions_creation_basic(self):
        """Test basic dimensions creation"""
        dims = Dimensions(length=Decimal('100'), width=Decimal('50'))
        
        assert dims.length == Decimal('100')
        assert dims.width == Decimal('50')
        assert dims.thickness is None
        assert dims.diameter == Decimal('50')  # diameter is alias for width
    
    @pytest.mark.unit
    def test_dimensions_creation_all_fields(self):
        """Test dimensions creation with all fields"""
        dims = Dimensions(
            length=Decimal('1000'),
            width=Decimal('200'),
            thickness=Decimal('50'),
            wall_thickness=Decimal('10'),
            weight=Decimal('25.5')
        )
        
        assert dims.length == Decimal('1000')
        assert dims.width == Decimal('200')
        assert dims.thickness == Decimal('50')
        assert dims.wall_thickness == Decimal('10')
        assert dims.weight == Decimal('25.5')
    
    @pytest.mark.unit
    def test_dimensions_validation_negative(self):
        """Test dimensions can have negative values (no validation currently)"""
        dims = Dimensions(length=Decimal('-100'))
        assert dims.length == Decimal('-100')
    
    @pytest.mark.unit
    def test_dimensions_validation_zero(self):
        """Test dimensions can have zero values (no validation currently)"""
        dims = Dimensions(width=Decimal('0'))
        assert dims.width == Decimal('0')
    
    @pytest.mark.unit
    def test_dimensions_serialization(self):
        """Test dimensions can be serialized to dict"""
        dims = Dimensions(length=Decimal('100'), width=Decimal('25'))
        data = dims.to_dict()
        
        expected = {
            'length': '100',
            'width': '25',
            'thickness': None,
            'wall_thickness': None,
            'weight': None
        }
        assert data == expected


class TestThread:
    """Tests for Thread class"""
    
    @pytest.mark.unit
    def test_thread_creation_basic(self):
        """Test basic thread creation"""
        thread = Thread(
            series=ThreadSeries.METRIC,
            handedness=ThreadHandedness.RIGHT,
            size="M12x1.75"
        )
        
        assert thread.series == ThreadSeries.METRIC
        assert thread.handedness == ThreadHandedness.RIGHT
        assert thread.size == "M12x1.75"
    
    @pytest.mark.unit
    def test_thread_validation_invalid_size(self):
        """Test validation fails for invalid thread size format"""
        with pytest.raises(ValueError, match="Invalid thread size format"):
            Thread(
                series=ThreadSeries.METRIC,
                handedness=ThreadHandedness.RIGHT,
                size="INVALID_SIZE"
            )
    
    @pytest.mark.unit
    def test_thread_serialization(self):
        """Test thread can be serialized to dict"""
        thread = Thread(
            series=ThreadSeries.UNC,
            handedness=ThreadHandedness.LEFT,
            size="1/2-13",
            original="1/2-13 UNC"
        )
        data = thread.to_dict()
        
        expected = {
            'series': 'UNC',
            'handedness': 'LH',
            'form': None,
            'size': '1/2-13',
            'original': '1/2-13 UNC'
        }
        assert data == expected


class TestEnums:
    """Tests for enum classes"""
    
    @pytest.mark.unit
    def test_item_type_values(self):
        """Test ItemType enum values"""
        assert ItemType.THREADED_ROD.value == 'Threaded Rod'
        assert ItemType.SHEET.value == 'Sheet'
        assert ItemType.TUBE.value == 'Tube'
        assert ItemType.BAR.value == 'Bar'
        assert ItemType.PLATE.value == 'Plate'
        assert ItemType.ANGLE.value == 'Angle'
    
    @pytest.mark.unit
    def test_item_shape_values(self):
        """Test ItemShape enum values"""
        assert ItemShape.ROUND.value == 'Round'
        assert ItemShape.SQUARE.value == 'Square'
        assert ItemShape.RECTANGULAR.value == 'Rectangular'
        assert ItemShape.HEX.value == 'Hex'
    
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