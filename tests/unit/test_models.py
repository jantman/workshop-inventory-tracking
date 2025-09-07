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


class TestItem:
    """Tests for Item class"""
    
    @pytest.mark.unit
    def test_item_creation_minimal(self):
        """Test item creation with minimal required fields"""
        item = Item(
            ja_id='JA000001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel',
            dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
        )
        
        assert item.ja_id == 'JA000001'
        assert item.item_type == ItemType.ROD
        assert item.shape == ItemShape.ROUND
        assert item.material == 'Steel'
        assert item.active is True  # Default value
        assert item.dimensions.length == Decimal('1000')
        assert item.dimensions.width == Decimal('25')
        assert item.thread is None
        assert item.location is None
        assert item.notes is None
    
    @pytest.mark.unit
    def test_item_creation_complete(self):
        """Test item creation with all fields"""
        dimensions = Dimensions(length=Decimal('1000'), width=Decimal('25'))
        thread = Thread(
            series=ThreadSeries.METRIC,
            handedness=ThreadHandedness.RIGHT,
            size="M25x1.5"
        )
        
        item = Item(
            ja_id='JA000002',
            item_type=ItemType.THREADED_ROD,
            shape=ItemShape.ROUND,
            material='Stainless Steel',
            dimensions=dimensions,
            thread=thread,
            location='Storage A',
            notes='Test notes',
            parent_ja_id='JA000999',
            active=False
        )
        
        assert item.ja_id == 'JA000002'
        assert item.item_type == ItemType.THREADED_ROD
        assert item.shape == ItemShape.ROUND
        assert item.material == 'Stainless Steel'
        assert item.dimensions == dimensions
        assert item.thread == thread
        assert item.location == 'Storage A'
        assert item.notes == 'Test notes'
        assert item.parent_ja_id == 'JA000999'
        assert item.active is False
    
    @pytest.mark.unit
    def test_item_validation_empty_ja_id(self):
        """Test validation fails for empty JA_ID"""
        with pytest.raises(ValueError, match="JA ID is required"):
            Item(
                ja_id='',
                item_type=ItemType.ROD,
                shape=ItemShape.ROUND,
                material='Steel',
                dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
            )
    
    @pytest.mark.unit
    def test_item_validation_empty_material(self):
        """Test validation fails for empty material"""
        with pytest.raises(ValueError, match="Material is required"):
            Item(
                ja_id='JA000001',
                item_type=ItemType.ROD,
                shape=ItemShape.ROUND,
                material='',
                dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
            )
    
    @pytest.mark.unit
    def test_item_validation_whitespace_ja_id(self):
        """Test validation fails for whitespace-only JA_ID"""
        with pytest.raises(ValueError, match="Invalid JA ID format"):
            Item(
                ja_id='   ',
                item_type=ItemType.ROD,
                shape=ItemShape.ROUND,
                material='Steel',
                dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
            )
    
    @pytest.mark.unit
    def test_item_serialization_minimal(self):
        """Test item serialization with minimal fields"""
        item = Item(
            ja_id='JA000001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel',
            dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
        )
        
        data = item.to_dict()
        
        expected = {
            'ja_id': 'JA000001',
            'item_type': 'Rod',  # Enum value
            'shape': 'Round',    # Enum value
            'material': 'Steel',
            'dimensions': {
                'length': '1000',
                'width': '25',
                'thickness': None,
                'wall_thickness': None,
                'weight': None
            },
            'thread': None,
            'active': True,
            'quantity': 1,
            'location': None,
            'sub_location': None,
            'purchase_date': None,
            'purchase_price': None,
            'purchase_location': None,
            'vendor': None,
            'vendor_part_number': None,
            'notes': None,
            'original_material': None,
            'original_thread': None,
            'date_added': item.date_added.isoformat(),
            'last_modified': item.last_modified.isoformat(),
            'parent_ja_id': None,
            'child_ja_ids': []
        }
        assert data == expected
    
    @pytest.mark.unit
    def test_item_serialization_complete(self):
        """Test item serialization with all fields"""
        dimensions = Dimensions(length=Decimal('1000'), width=Decimal('25'))
        thread = Thread(
            series=ThreadSeries.METRIC,
            handedness=ThreadHandedness.RIGHT,
            size="M25x1.5"
        )
        
        item = Item(
            ja_id='JA000002',
            item_type=ItemType.THREADED_ROD,
            shape=ItemShape.ROUND,
            material='Stainless Steel',
            dimensions=dimensions,
            thread=thread,
            location='Storage A',
            notes='Test notes',
            parent_ja_id='JA000999',
            active=False
        )
        
        data = item.to_dict()
        
        expected = {
            'ja_id': 'JA000002',
            'item_type': 'Threaded Rod',  # Enum value
            'shape': 'Round',    # Enum value
            'material': 'Stainless Steel',
            'dimensions': dimensions.to_dict(),
            'thread': thread.to_dict(),
            'active': False,
            'quantity': 1,
            'location': 'Storage A',
            'sub_location': None,
            'purchase_date': None,
            'purchase_price': None,
            'purchase_location': None,
            'vendor': None,
            'vendor_part_number': None,
            'notes': 'Test notes',
            'original_material': None,
            'original_thread': None,
            'date_added': item.date_added.isoformat(),
            'last_modified': item.last_modified.isoformat(),
            'parent_ja_id': 'JA000999',
            'child_ja_ids': []
        }
        assert data == expected
    
    @pytest.mark.unit
    def test_item_equality(self):
        """Test item equality comparison"""
        item1 = Item(
            ja_id='JA000001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel',
            dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
        )
        
        item2 = Item(
            ja_id='JA000001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel',
            dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
        )
        
        # Set same timestamps for equality comparison
        item2.date_added = item1.date_added
        item2.last_modified = item1.last_modified
        
        item3 = Item(
            ja_id='JA000002',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel',
            dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
        )
        
        assert item1 == item2
        assert item1 != item3
    
    @pytest.mark.unit
    def test_item_string_representation(self):
        """Test item string representation"""
        item = Item(
            ja_id='JA000001',
            item_type=ItemType.ROD,
            shape=ItemShape.ROUND,
            material='Steel',
            dimensions=Dimensions(length=Decimal('1000'), width=Decimal('25'))
        )
        
        str_repr = str(item)
        assert 'JA000001' in str_repr
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