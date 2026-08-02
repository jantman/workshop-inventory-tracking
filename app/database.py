"""
SQLAlchemy database models for Workshop Material Inventory Tracking

This module defines the database schema using SQLAlchemy ORM models.
The schema supports multiple rows per JA ID for maintaining shortening history,
with proper constraints to ensure data integrity.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, UniqueConstraint, CheckConstraint, LargeBinary, ForeignKey, Index
from sqlalchemy.sql.sqltypes import Numeric
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import enum
import re

# Import enums and helper classes from models module
from .models import ItemType, ItemShape, ThreadSeries, ThreadHandedness, Dimensions, Thread

Base = declarative_base()

class InventoryItem(Base):
    """
    Main inventory items table.
    
    Supports multiple rows per JA ID for shortening history tracking.
    Only one row per JA ID can be active at any time.
    """
    __tablename__ = 'inventory_items'
    
    # Primary key - row-based, not JA ID based
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Item identification
    ja_id = Column(String(10), nullable=False, index=True)  # Format: JA000001
    active = Column(Boolean, nullable=False, default=True, index=True)
    
    # Physical dimensions
    length = Column(Numeric(10, 4), nullable=True)  # inches, supports fractions
    width = Column(Numeric(10, 4), nullable=True)   # inches
    thickness = Column(Numeric(10, 4), nullable=True)  # inches 
    wall_thickness = Column(Numeric(10, 4), nullable=True)  # inches
    weight = Column(Numeric(10, 2), nullable=True)  # pounds
    
    # Item classification
    item_type = Column(String(50), nullable=False)  # Bar, Plate, Sheet, etc.
    shape = Column(String(50), nullable=True)  # Round, Square, Rectangular, etc.
    material = Column(String(100), nullable=False)  # Steel, Aluminum, etc.
    
    # Threading information (for threaded items)
    thread_series = Column(String(10), nullable=True)  # UNC, UNF, Metric, etc.
    thread_handedness = Column(String(10), nullable=True)  # RH, LH
    thread_size = Column(String(20), nullable=True)  # 1/4-20, M10x1.5, etc.

    # Inventory tracking
    location = Column(String(100), nullable=True)
    sub_location = Column(String(100), nullable=True)
    
    # Purchase information
    purchase_date = Column(DateTime, nullable=True)
    purchase_price = Column(Numeric(10, 2), nullable=True)
    purchase_location = Column(String(200), nullable=True)
    
    # Additional information
    notes = Column(Text, nullable=True)
    vendor = Column(String(200), nullable=True)
    vendor_part = Column(String(100), nullable=True)
    original_material = Column(String(100), nullable=True)  # For tracking material changes
    original_thread = Column(String(50), nullable=True)  # For tracking thread changes
    precision = Column(Boolean, nullable=False, default=False)  # Indicates item has precision dimensions
    
    # Timestamps
    date_added = Column(DateTime, nullable=False, default=func.now())
    last_modified = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Constraints
    __table_args__ = (
        # Note: "Only one active row per JA ID" constraint handled at application level
        # since MariaDB doesn't support partial unique indexes
        
        # Ensure positive dimensions
        CheckConstraint('length IS NULL OR length > 0', name='ck_positive_length'),
        CheckConstraint('width IS NULL OR width > 0', name='ck_positive_width'),
        CheckConstraint('thickness IS NULL OR thickness > 0', name='ck_positive_thickness'),
        CheckConstraint('wall_thickness IS NULL OR wall_thickness > 0', name='ck_positive_wall_thickness'),
        CheckConstraint('weight IS NULL OR weight > 0', name='ck_positive_weight'),

        # Ensure valid JA ID format (MariaDB/MySQL compatible)
        CheckConstraint("ja_id REGEXP '^JA[0-9]{6}$'", name='ck_valid_ja_id_format'),
    )
    
    # Enum properties for automatic conversion between database strings and enum objects
    @hybrid_property
    def item_type_enum(self) -> Optional[ItemType]:
        """Get item type as enum object"""
        if not self.item_type:
            return None
        try:
            return ItemType(self.item_type)
        except ValueError:
            # Handle legacy enum class name format (e.g., 'ItemType.PLATE' -> 'Plate')
            if '.' in self.item_type:
                enum_name = self.item_type.split('.')[-1]  # 'ItemType.PLATE' -> 'PLATE'
                for enum_item in ItemType:
                    if enum_item.name == enum_name:
                        return enum_item
                    # Try with common case transformations
                    if enum_item.value == enum_name.capitalize():
                        return enum_item
            return None
    
    @item_type_enum.setter
    def item_type_enum(self, value: Optional[ItemType]):
        """Set item type from enum object"""
        self.item_type = value.value if value else None
    
    @hybrid_property
    def shape_enum(self) -> Optional[ItemShape]:
        """Get shape as enum object"""
        if not self.shape:
            return None
        try:
            return ItemShape(self.shape)
        except ValueError:
            # Handle legacy enum class name format
            if '.' in self.shape:
                enum_name = self.shape.split('.')[-1]
                for enum_item in ItemShape:
                    if enum_item.name == enum_name:
                        return enum_item
                    # Try with common case transformations
                    if enum_item.value == enum_name.capitalize():
                        return enum_item
            return None
    
    @shape_enum.setter
    def shape_enum(self, value: Optional[ItemShape]):
        """Set shape from enum object"""
        self.shape = value.value if value else None
    
    @hybrid_property
    def thread_series_enum(self) -> Optional[ThreadSeries]:
        """Get thread series as enum object"""
        if not self.thread_series:
            return None
        try:
            return ThreadSeries(self.thread_series)
        except ValueError:
            # Handle legacy enum class name format
            if '.' in self.thread_series:
                enum_name = self.thread_series.split('.')[-1]
                for enum_item in ThreadSeries:
                    if enum_item.name == enum_name:
                        return enum_item
                    if enum_item.value == enum_name:
                        return enum_item
            return None
    
    @thread_series_enum.setter
    def thread_series_enum(self, value: Optional[ThreadSeries]):
        """Set thread series from enum object"""
        self.thread_series = value.value if value else None
    
    @hybrid_property
    def thread_handedness_enum(self) -> Optional[ThreadHandedness]:
        """Get thread handedness as enum object"""
        if not self.thread_handedness:
            return None
        try:
            return ThreadHandedness(self.thread_handedness)
        except ValueError:
            # Handle legacy enum class name format
            if '.' in self.thread_handedness:
                enum_name = self.thread_handedness.split('.')[-1]
                for enum_item in ThreadHandedness:
                    if enum_item.name == enum_name:
                        return enum_item
                    if enum_item.value == enum_name:
                        return enum_item
            return None
    
    @thread_handedness_enum.setter
    def thread_handedness_enum(self, value: Optional[ThreadHandedness]):
        """Set thread handedness from enum object"""
        self.thread_handedness = value.value if value else None
    
    def validate(self) -> List[str]:
        """
        Validate item data and return list of error messages.
        Similar to Item._validate_required_fields but returns errors instead of raising.
        """
        errors = []
        
        # Validate JA ID format
        if not self.ja_id:
            errors.append("JA ID is required")
        elif not re.match(r'^JA\d{6}$', self.ja_id):
            errors.append(f"Invalid JA ID format: {self.ja_id}. Expected format: JA######")
        
        # Basic required fields
        if not self.material or not self.material.strip():
            errors.append("Material is required")
        
        if not self.item_type:
            errors.append("Item type is required")
        
        # Type and shape-specific dimension requirements
        item_type_enum = self.item_type_enum
        shape_enum = self.shape_enum
        
        if item_type_enum == ItemType.THREADED_ROD:
            # Threaded rods only need length and thread specification
            if not self.length:
                errors.append("Length is required for threaded rods")
            if not self.thread_size or not self.thread_size.strip():
                errors.append("Thread size is required for threaded rods")
        elif shape_enum == ItemShape.RECTANGULAR:
            if not self.length:
                errors.append("Length is required for rectangular items")
            if not self.width:
                errors.append("Width is required for rectangular items") 
            if not self.thickness:
                errors.append("Thickness is required for rectangular items")
        elif shape_enum == ItemShape.ROUND:
            if not self.length:
                errors.append("Length is required for round items")
            if not self.width:  # width = diameter for round items
                errors.append("Diameter (width) is required for round items")
        elif shape_enum == ItemShape.SQUARE:
            if not self.length:
                errors.append("Length is required for square items")
            if not self.width:
                errors.append("Width is required for square items")
        
        # Validate dimension values are positive
        dimension_fields = ['length', 'width', 'thickness', 'wall_thickness']
        for field_name in dimension_fields:
            value = getattr(self, field_name)
            if value is not None and float(value) <= 0:
                errors.append(f"{field_name.replace('_', ' ').title()} must be positive")

        return errors
    
    @property
    def display_name(self) -> str:
        """Generate a human-readable display name"""
        parts = [self.material]
        
        if self.item_type_enum:
            parts.append(self.item_type_enum.value)
        if self.shape_enum:
            parts.append(self.shape_enum.value)
        
        if self.length:
            if self.shape_enum == ItemShape.ROUND:
                parts.append(f"⌀{self.width}\" × {self.length}\"")
            elif self.shape_enum == ItemShape.RECTANGULAR:
                parts.append(f"{self.width}\" × {self.thickness}\" × {self.length}\"")
            elif self.shape_enum == ItemShape.SQUARE:
                parts.append(f"{self.width}\" × {self.length}\"")
        
        return " ".join(str(p) for p in parts if p)
    
    @property
    def is_threaded(self) -> bool:
        """Check if item has threading specification"""
        return bool(self.thread_series is not None or 
                   self.thread_handedness is not None or
                   (self.thread_size and self.thread_size.strip()))
    
    @property
    def dimensions(self) -> Dimensions:
        """Get dimensions as Dimensions object"""
        from decimal import Decimal
        
        def normalize_precision(value):
            """Normalize decimal precision by removing trailing zeros from database fixed-precision values"""
            if value is None:
                return None
            # Convert to string and remove trailing zeros and unnecessary decimal point
            str_value = str(value).rstrip('0').rstrip('.')
            # Handle case where all zeros were stripped (e.g., "0.0000" -> "")
            if not str_value or str_value == '.':
                str_value = '0'
            return Decimal(str_value)
        
        return Dimensions(
            length=normalize_precision(self.length),
            width=normalize_precision(self.width),
            thickness=normalize_precision(self.thickness),
            wall_thickness=normalize_precision(self.wall_thickness),
            weight=normalize_precision(self.weight),
        )
    
    @dimensions.setter
    def dimensions(self, value: Dimensions):
        """Set dimensions from Dimensions object"""
        if value:
            self.length = float(value.length) if value.length is not None else None
            self.width = float(value.width) if value.width is not None else None
            self.thickness = float(value.thickness) if value.thickness is not None else None
            self.wall_thickness = float(value.wall_thickness) if value.wall_thickness is not None else None
            self.weight = float(value.weight) if value.weight is not None else None
    
    @property
    def thread(self) -> Optional[Thread]:
        """Get thread specification as Thread object"""
        # Only create Thread object if we have meaningful thread data
        if not any([self.thread_series, self.thread_handedness, 
                   self.thread_size and self.thread_size.strip()]):
            return None
        
        try:
            return Thread(
                series=self.thread_series_enum,
                handedness=self.thread_handedness_enum,
                size=self.thread_size.strip() if self.thread_size else None,
                original=self.original_thread
            )
        except ValueError:
            # Skip thread creation if validation fails - thread data is malformed
            return None
    
    @thread.setter
    def thread(self, value: Optional[Thread]):
        """Set thread specification from Thread object"""
        if value:
            self.thread_series_enum = value.series
            self.thread_handedness_enum = value.handedness  
            self.thread_size = value.size
            if value.original:
                self.original_thread = value.original
        else:
            self.thread_series = None
            self.thread_handedness = None
            self.thread_size = None
    
    @property
    def estimated_volume(self) -> Optional['Decimal']:
        """Calculate estimated volume using dimensions and shape"""
        return self.dimensions.volume(self.shape_enum) if self.shape_enum else None
    
    def to_dict_enhanced(self) -> Dict[str, Any]:
        """
        Convert to dictionary with enum handling for API responses.
        Enhanced version that includes enum values alongside string values.
        """
        result = self.to_dict()  # Start with existing to_dict()
        
        # Add enum representations
        result.update({
            'item_type_enum': self.item_type_enum.value if self.item_type_enum else None,
            'shape_enum': self.shape_enum.value if self.shape_enum else None,
            'thread_series_enum': self.thread_series_enum.value if self.thread_series_enum else None,
            'thread_handedness_enum': self.thread_handedness_enum.value if self.thread_handedness_enum else None,
            'display_name': self.display_name,
            'is_threaded': self.is_threaded,
        })
        
        return result
    
    @classmethod
    def from_dict_enhanced(cls, data: Dict[str, Any]) -> 'InventoryItem':
        """
        Create InventoryItem from dictionary with enum support.
        Handles both string values and enum objects.
        """
        # Create base item with string values
        item = cls()
        
        # Set basic fields
        for field in ['ja_id', 'material', 'location', 'sub_location',
                     'notes', 'vendor', 'original_material', 'original_thread']:
            if field in data and data[field] is not None:
                setattr(item, field, data[field])

        # Handle vendor_part - accept both vendor_part and vendor_part_number for compatibility
        if 'vendor_part_number' in data and data['vendor_part_number'] is not None:
            item.vendor_part = data['vendor_part_number']
        elif 'vendor_part' in data and data['vendor_part'] is not None:
            item.vendor_part = data['vendor_part']
        
        # Handle enum fields - prefer enum values, fall back to string values
        if 'item_type_enum' in data and data['item_type_enum']:
            try:
                item.item_type_enum = ItemType(data['item_type_enum'])
            except ValueError:
                item.item_type = data.get('item_type', data['item_type_enum'])
        elif 'item_type' in data:
            item.item_type = data['item_type']
        
        if 'shape_enum' in data and data['shape_enum']:
            try:
                item.shape_enum = ItemShape(data['shape_enum'])
            except ValueError:
                item.shape = data.get('shape', data['shape_enum'])
        elif 'shape' in data:
            item.shape = data['shape']
        
        if 'thread_series_enum' in data and data['thread_series_enum']:
            try:
                item.thread_series_enum = ThreadSeries(data['thread_series_enum'])
            except ValueError:
                item.thread_series = data.get('thread_series', data['thread_series_enum'])
        elif 'thread_series' in data:
            item.thread_series = data['thread_series']
        
        if 'thread_handedness_enum' in data and data['thread_handedness_enum']:
            try:
                item.thread_handedness_enum = ThreadHandedness(data['thread_handedness_enum'])
            except ValueError:
                item.thread_handedness = data.get('thread_handedness', data['thread_handedness_enum'])
        elif 'thread_handedness' in data:
            item.thread_handedness = data['thread_handedness']
        
        # Handle numeric fields
        for field in ['length', 'width', 'thickness', 'wall_thickness', 'weight', 'purchase_price']:
            if field in data and data[field] is not None:
                try:
                    setattr(item, field, float(data[field]))
                except (ValueError, TypeError):
                    pass
        
        # Handle thread size
        if 'thread_size' in data:
            item.thread_size = data['thread_size']
        
        # Handle boolean fields
        if 'active' in data:
            item.active = bool(data['active'])
        if 'precision' in data:
            item.precision = bool(data['precision'])
        
        # Handle date fields
        if 'purchase_date' in data and data['purchase_date']:
            try:
                if isinstance(data['purchase_date'], str):
                    item.purchase_date = datetime.fromisoformat(data['purchase_date'].replace('Z', '+00:00'))
                elif hasattr(data['purchase_date'], 'date'):
                    item.purchase_date = data['purchase_date']
            except (ValueError, AttributeError):
                pass
        
        return item
    
    def to_row(self, headers: List[str]) -> List[str]:
        """Convert item to a row format matching given headers for Google Sheets compatibility"""
        row = []
        
        for header in headers:
            # Map headers to data fields
            header_mappings = {
                'Active': 'Yes' if self.active else 'No',
                'JA ID': self.ja_id or '',
                'Length': str(self.length) if self.length else '',
                'Width': str(self.width) if self.width else '',
                'Thickness': str(self.thickness) if self.thickness else '',
                'Wall Thickness': str(self.wall_thickness) if self.wall_thickness else '',
                'Weight': str(self.weight) if self.weight else '',
                'Type': self.item_type or '',
                'Shape': self.shape or '',
                'Material': self.material or '',
                'Thread Series': self.thread_series or '',
                'Thread Handedness': self.thread_handedness or '',
                'Thread Size': self.thread_size or '',
                'Location': self.location or '',
                'Sub-Location': self.sub_location or '',
                'Purchase Date': self.purchase_date.strftime('%Y-%m-%d') if self.purchase_date else '',
                'Purchase Price': str(self.purchase_price) if self.purchase_price else '',
                'Purchase Location': self.purchase_location or '',
                'Notes': self.notes or '',
                'Vendor': self.vendor or '',
                'Vendor Part': self.vendor_part or '',
                'Original Material': self.original_material or '',
                'Original Thread': self.original_thread or '',
                'Date Added': self.date_added.isoformat() if self.date_added else '',
                'Last Modified': self.last_modified.isoformat() if self.last_modified else '',
            }
            
            row.append(header_mappings.get(header, ''))
        
        return row
    
    @classmethod
    def from_row(cls, row: List[str], headers: List[str]) -> 'InventoryItem':
        """Create InventoryItem from row data with given headers"""
        row_dict = dict(zip(headers, row))
        
        # Create new item
        item = cls()
        
        # Set basic string fields
        string_fields = {
            'JA ID': 'ja_id',
            'Type': 'item_type', 
            'Shape': 'shape',
            'Material': 'material',
            'Thread Series': 'thread_series',
            'Thread Handedness': 'thread_handedness',
            'Thread Size': 'thread_size',
            'Location': 'location',
            'Sub-Location': 'sub_location',
            'Purchase Location': 'purchase_location',
            'Vendor': 'vendor',
            'Vendor Part': 'vendor_part',
            'Notes': 'notes',
            'Original Material': 'original_material',
            'Original Thread': 'original_thread',
        }
        
        for header, field_name in string_fields.items():
            value = row_dict.get(header)
            if value and value.strip():
                setattr(item, field_name, value.strip())
        
        # Handle numeric fields
        numeric_fields = ['Length', 'Width', 'Thickness', 'Wall Thickness', 'Weight', 'Purchase Price']
        field_mappings = {
            'Length': 'length',
            'Width': 'width', 
            'Thickness': 'thickness',
            'Wall Thickness': 'wall_thickness',
            'Weight': 'weight',
            'Purchase Price': 'purchase_price'
        }
        
        for header in numeric_fields:
            value = row_dict.get(header)
            if value and str(value).strip():
                try:
                    # Clean currency symbols for price
                    if header == 'Purchase Price':
                        cleaned_value = str(value).strip()
                        cleaned_value = cleaned_value.replace('$', '').replace('€', '').replace('£', '').replace('¥', '')
                        cleaned_value = cleaned_value.replace(',', '').strip()
                        if cleaned_value:
                            setattr(item, field_mappings[header], float(cleaned_value))
                    else:
                        setattr(item, field_mappings[header], float(value))
                except (ValueError, TypeError):
                    pass

        # Handle active status
        active_str = row_dict.get('Active', 'Yes')
        item.active = active_str.lower() in ['yes', 'y', 'true', '1']
        
        # Handle dates
        purchase_date_str = row_dict.get('Purchase Date')
        if purchase_date_str and purchase_date_str.strip():
            try:
                item.purchase_date = datetime.strptime(purchase_date_str.strip(), '%Y-%m-%d')
            except ValueError:
                pass
        
        date_added_str = row_dict.get('Date Added')
        if date_added_str and date_added_str.strip():
            try:
                item.date_added = datetime.fromisoformat(date_added_str.strip().replace('Z', '+00:00'))
            except ValueError:
                pass
        
        last_modified_str = row_dict.get('Last Modified')
        if last_modified_str and last_modified_str.strip():
            try:
                item.last_modified = datetime.fromisoformat(last_modified_str.strip().replace('Z', '+00:00'))
            except ValueError:
                pass
        
        return item
    
    def __repr__(self):
        return f"<InventoryItem(id={self.id}, ja_id='{self.ja_id}', active={self.active}, material='{self.material}')>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'ja_id': self.ja_id,
            'active': self.active,
            'length': float(self.length) if self.length else None,
            'width': float(self.width) if self.width else None,
            'thickness': float(self.thickness) if self.thickness else None,
            'wall_thickness': float(self.wall_thickness) if self.wall_thickness else None,
            'weight': float(self.weight) if self.weight else None,
            'item_type': self.item_type,
            'shape': self.shape,
            'material': self.material,
            'thread_series': self.thread_series,
            'thread_handedness': self.thread_handedness,
            'thread_size': self.thread_size,
            'location': self.location,
            'sub_location': self.sub_location,
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date else None,
            'purchase_price': float(self.purchase_price) if self.purchase_price else None,
            'purchase_location': self.purchase_location,
            'notes': self.notes,
            'vendor': self.vendor,
            'vendor_part_number': self.vendor_part,  # Map database field vendor_part to API field vendor_part_number
            'original_material': self.original_material,
            'original_thread': self.original_thread,
            'precision': self.precision,
            'date_added': self.date_added.isoformat() if self.date_added else None,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
        }

# Note: Enum definitions moved to app.models to maintain single source of truth
# All enums (ItemType, ItemShape, ThreadSeries, ThreadHandedness) are now
# centrally defined in app.models and imported from there throughout the application.


class MaterialTaxonomy(Base):
    """
    Material taxonomy table.
    
    Stores hierarchical material taxonomy with 3 levels:
    1. Category (level 1)
    2. Family (level 2) 
    3. Material (level 3)
    """
    __tablename__ = 'material_taxonomy'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Taxonomy fields
    name = Column(String(100), nullable=False, unique=True, index=True)
    level = Column(Integer, nullable=False, index=True)  # 1=Category, 2=Family, 3=Material
    parent = Column(String(100), nullable=True, index=True)  # Parent material name
    aliases = Column(Text, nullable=True)  # Comma-separated aliases
    active = Column(Boolean, nullable=False, default=True, index=True)
    sort_order = Column(Integer, nullable=False, default=0, index=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    date_added = Column(DateTime, nullable=False, default=func.now())
    last_modified = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Constraints
    __table_args__ = (
        # Ensure valid hierarchy levels
        CheckConstraint('level >= 1 AND level <= 3', name='ck_valid_level'),
        
        # Level 1 (categories) should not have parents
        CheckConstraint('NOT (level = 1 AND parent IS NOT NULL)', name='ck_category_no_parent'),
        
        # Levels 2 and 3 should have parents (in most cases)
        # Note: We'll handle this in business logic rather than DB constraint for flexibility
    )
    
    def __repr__(self):
        return f"<MaterialTaxonomy(id={self.id}, name='{self.name}', level={self.level}, parent='{self.parent}')>"
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'name': self.name,
            'level': self.level,
            'parent': self.parent,
            'aliases': self.aliases.split(',') if self.aliases else [],
            'active': self.active,
            'sort_order': self.sort_order,
            'notes': self.notes,
            'date_added': self.date_added.isoformat() if self.date_added else None,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
        }
    
    @property
    def aliases_list(self) -> list:
        """Get aliases as a list"""
        if not self.aliases:
            return []
        return [alias.strip() for alias in self.aliases.split(',') if alias.strip()]
    
    @aliases_list.setter
    def aliases_list(self, value: list):
        """Set aliases from a list"""
        if value:
            self.aliases = ','.join([alias.strip() for alias in value if alias.strip()])
        else:
            self.aliases = None


class Photo(Base):
    """
    Photos table for storing actual photo data.

    Stores photo BLOB data once, referenced by multiple items via item_photo_associations.
    Each photo is stored in three sizes: thumbnail (~150px), medium (~800px), and original.
    """
    __tablename__ = 'photos'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # File metadata
    filename = Column(String(255), nullable=False)  # Original filename
    content_type = Column(String(100), nullable=False)  # MIME type
    file_size = Column(Integer, nullable=False)  # Original file size in bytes

    # Photo data in three sizes
    # Use MEDIUMBLOB for MySQL/MariaDB, fall back to LargeBinary for SQLite tests
    thumbnail_data = Column(LargeBinary, nullable=False)  # ~150px compressed (BLOB, up to 64KB)
    medium_data = Column(LargeBinary().with_variant(MEDIUMBLOB, 'mysql'), nullable=False)  # ~800px compressed (MEDIUMBLOB on MySQL, up to 16MB)
    original_data = Column(LargeBinary().with_variant(MEDIUMBLOB, 'mysql'), nullable=False)  # Original up to 20MB (MEDIUMBLOB on MySQL, up to 16MB)

    # Optional hash for deduplication
    sha256_hash = Column(String(64), nullable=True, index=True)  # SHA256 hash of original data

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # Constraints
    __table_args__ = (
        # Ensure positive file size
        CheckConstraint('file_size > 0', name='ck_photo_positive_file_size'),

        # Validate supported content types
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')",
            name='ck_photo_valid_content_type'
        ),
    )

    def __repr__(self):
        return f"<Photo(id={self.id}, filename='{self.filename}', content_type='{self.content_type}', size={self.file_size})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses (excludes binary data)"""
        return {
            'id': self.id,
            'filename': self.filename,
            'content_type': self.content_type,
            'file_size': self.file_size,
            'sha256_hash': self.sha256_hash,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def is_image(self) -> bool:
        """Check if the photo is an image (not PDF)"""
        return self.content_type.startswith('image/')

    @property
    def is_pdf(self) -> bool:
        """Check if the photo is a PDF"""
        return self.content_type == 'application/pdf'


class ItemPhotoAssociation(Base):
    """
    Item-photo associations table for many-to-many relationships.

    Links inventory items (via ja_id) to photos, allowing multiple items to share the same photo.
    """
    __tablename__ = 'item_photo_associations'

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to ja_id (not item.id to maintain association across shortening history)
    ja_id = Column(String(10), nullable=False, index=True)

    # Foreign key to photo
    photo_id = Column(Integer, ForeignKey('photos.id', ondelete='CASCADE'), nullable=False, index=True)

    # Display order for this item's photos
    display_order = Column(Integer, nullable=False, default=0)

    # Timestamp
    created_at = Column(DateTime, nullable=False, default=func.now())

    # Relationship to Photo
    photo = relationship('Photo', backref='associations')

    # Constraints
    __table_args__ = (
        # Ensure valid JA ID format
        CheckConstraint("ja_id REGEXP '^JA[0-9]{6}$'", name='ck_assoc_valid_ja_id'),

        # Unique constraint: each photo can appear only once per item at a specific order
        # (ja_id, photo_id, display_order) must be unique
        UniqueConstraint('ja_id', 'photo_id', 'display_order', name='uk_ja_photo_order'),

        # Index for efficient lookups
        Index('ix_item_photo_associations_ja_id_order', 'ja_id', 'display_order'),
    )

    def __repr__(self):
        return f"<ItemPhotoAssociation(id={self.id}, ja_id='{self.ja_id}', photo_id={self.photo_id}, order={self.display_order})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'id': self.id,
            'ja_id': self.ja_id,
            'photo_id': self.photo_id,
            'display_order': self.display_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        # Include photo data if available
        if self.photo:
            result['photo'] = self.photo.to_dict()
        return result

# ===========================================================================
# Product catalogue
#
# Five new tables plus an attachment association. No existing table is modified;
# inventory_items and its JA ID history invariants are untouched. The one
# existing table reused is photos, via ProductAttachment.
# ===========================================================================


class Product(Base):
    """
    A distinct kind of thing the workshop holds.

    Identity is this row's surrogate id and never a vendor's item identifier
    (FR-008): a vendor may reuse an item id for a different product, and the
    catalogue must survive that without merging two products.
    """
    __tablename__ = 'products'

    id = Column(Integer, primary_key=True, autoincrement=True)

    # The operator's authoritative human-readable identity (FR-003), printed on
    # the label.
    description = Column(String(255), nullable=False)

    manufacturer = Column(String(200), nullable=True)
    # Convenience copy; the authoritative form is a ProductIdentifier of type MPN.
    manufacturer_part_number = Column(String(100), nullable=True)

    # Free-form and operator-authored. Never machine-generated.
    specifications = Column(Text, nullable=True)

    # Materialized path, canonical form per app/utils/category.py. NULL means
    # uncategorized, which is an ordinary state and not an error.
    category_path = Column(String(512), nullable=True, index=True)

    location = Column(String(100), nullable=True)

    # Tri-state (FR-022/FR-023): NULL = not tracked, 0 = tracked and none on
    # hand, >0 = a count. New products default to NULL.
    quantity = Column(Integer, nullable=True, default=None)
    # When quantity was last set; drives the relative age display (FR-024).
    quantity_updated_at = Column(DateTime, nullable=True)
    # Only meaningful when quantity is not NULL (FR-026).
    reorder_threshold = Column(Integer, nullable=True)

    # The operator's manual flag (FR-025): NULL, 'low' or 'out'. Independent of
    # quantity.
    stock_status = Column(String(20), nullable=True)

    notes = Column(Text, nullable=True)

    date_added = Column(DateTime, nullable=False, default=func.now())
    last_modified = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    identifiers = relationship(
        'ProductIdentifier',
        back_populates='product',
        cascade='all, delete-orphan',
        passive_deletes=True,
    )
    purchases = relationship(
        'Purchase',
        back_populates='product',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='Purchase.order_date',
    )
    tags = relationship(
        'Tag',
        secondary='product_tags',
        back_populates='products',
    )
    attachments = relationship(
        'ProductAttachment',
        back_populates='product',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='ProductAttachment.display_order',
    )

    __table_args__ = (
        CheckConstraint('quantity IS NULL OR quantity >= 0', name='ck_product_quantity_non_negative'),
        CheckConstraint(
            'reorder_threshold IS NULL OR reorder_threshold >= 0',
            name='ck_product_reorder_threshold_non_negative'
        ),
        CheckConstraint(
            "stock_status IS NULL OR stock_status IN ('low','out')",
            name='ck_product_valid_stock_status'
        ),
        # Search over the description (FR-032).
        Index('ix_products_description', 'description'),
    )

    def __repr__(self):
        return f"<Product(id={self.id}, description='{self.description}')>"

    @property
    def is_tracked(self) -> bool:
        """Whether a quantity is being counted at all (FR-022)"""
        return self.quantity is not None

    @property
    def is_threshold_low(self) -> bool:
        """Tracked, with a threshold, and at or below it (FR-026)"""
        return (
            self.quantity is not None
            and self.reorder_threshold is not None
            and self.quantity <= self.reorder_threshold
        )

    @property
    def is_manually_low(self) -> bool:
        """The operator said so, regardless of any count (FR-025)"""
        return self.stock_status in ('low', 'out')

    @property
    def is_effectively_low(self) -> bool:
        """The reorder view's membership test (FR-027)"""
        return self.is_threshold_low or self.is_manually_low

    @property
    def quantity_age(self) -> Optional[timedelta]:
        """How long ago the quantity was counted (FR-024).

        None when the quantity is not tracked, and also when it is tracked but
        no timestamp was recorded -- an unknown age is not an error, and the
        display renders it as unknown rather than raising.
        """
        if self.quantity is None or self.quantity_updated_at is None:
            return None
        return datetime.now() - self.quantity_updated_at

    @property
    def internal_code(self) -> Optional[str]:
        """This product's own scannable code, assigned at creation (FR-015)"""
        for identifier in self.identifiers:
            if identifier.id_type == 'INTERNAL':
                return identifier.value
        return None

    def to_dict(self, include_related: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'id': self.id,
            'description': self.description,
            'manufacturer': self.manufacturer,
            'manufacturer_part_number': self.manufacturer_part_number,
            'specifications': self.specifications,
            'category_path': self.category_path,
            'location': self.location,
            'quantity': self.quantity,
            'quantity_updated_at': self.quantity_updated_at.isoformat() if self.quantity_updated_at else None,
            'reorder_threshold': self.reorder_threshold,
            'stock_status': self.stock_status,
            'notes': self.notes,
            'internal_code': self.internal_code,
            'is_tracked': self.is_tracked,
            'is_effectively_low': self.is_effectively_low,
            'date_added': self.date_added.isoformat() if self.date_added else None,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
        }

        if include_related:
            result['identifiers'] = [i.to_dict() for i in self.identifiers]
            result['purchases'] = [p.to_dict() for p in self.purchases]
            result['tags'] = [t.name for t in self.tags]

        return result


class Purchase(Base):
    """
    One acquisition of one product.

    There is no status column: received_date IS NULL *is* the outstanding state
    (FR-005), so the two can never disagree.
    """
    __tablename__ = 'purchases'

    id = Column(Integer, primary_key=True, autoincrement=True)

    product_id = Column(
        Integer,
        ForeignKey('products.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    vendor = Column(String(200), nullable=False)
    # The vendor's own identifier (ASIN, part number). Not identity -- FR-008.
    vendor_item_id = Column(String(100), nullable=True, index=True)
    # The raw vendor title captured at order time (FR-020), deliberately
    # distinct from the operator's own products.description.
    listing_title = Column(String(500), nullable=True)

    order_date = Column(DateTime, nullable=True)
    # NULL means outstanding (FR-005). Indexed: the reorder view filters on it.
    received_date = Column(DateTime, nullable=True, index=True)

    quantity = Column(Integer, nullable=True)
    # Decimal, never float (Constitution III).
    unit_price = Column(Numeric(10, 2), nullable=True)

    # Order number; also filled from ECIA K / 1K.
    order_reference = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)

    date_added = Column(DateTime, nullable=False, default=func.now())
    last_modified = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    product = relationship('Product', back_populates='purchases')
    attachments = relationship(
        'ProductAttachment',
        back_populates='purchase',
        cascade='all, delete-orphan',
        passive_deletes=True,
        order_by='ProductAttachment.display_order',
    )

    __table_args__ = (
        CheckConstraint('quantity IS NULL OR quantity > 0', name='ck_purchase_quantity_positive'),
        CheckConstraint('unit_price IS NULL OR unit_price >= 0', name='ck_purchase_price_non_negative'),
        # The purchase-history read (FR-006).
        Index('ix_purchases_product_order_date', 'product_id', 'order_date'),
    )

    def __repr__(self):
        return f"<Purchase(id={self.id}, product_id={self.product_id}, vendor='{self.vendor}')>"

    @property
    def is_outstanding(self) -> bool:
        """Ordered but not yet received (FR-028)"""
        return self.received_date is None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'product_id': self.product_id,
            'vendor': self.vendor,
            'vendor_item_id': self.vendor_item_id,
            'listing_title': self.listing_title,
            'order_date': self.order_date.isoformat() if self.order_date else None,
            'received_date': self.received_date.isoformat() if self.received_date else None,
            'is_outstanding': self.is_outstanding,
            'quantity': self.quantity,
            # str() rather than float() -- a price must not round-trip through
            # binary floating point.
            'unit_price': str(self.unit_price) if self.unit_price is not None else None,
            'order_reference': self.order_reference,
            'notes': self.notes,
            'date_added': self.date_added.isoformat() if self.date_added else None,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
        }


class ProductIdentifier(Base):
    """
    Every coded name for a product, of a stated kind.

    This is the table FR-007, FR-009, FR-014 and FR-018 all turn on.

    ``vendor`` is part of the unique key because a vendor item id is only
    meaningful within its vendor (FR-008). It is NOT NULL with an empty-string
    default rather than nullable: SQL treats NULLs as distinct in a unique index,
    so a nullable column would let two rows carry the same GTIN and FR-009 would
    be a convention rather than a database property -- which is the entire reason
    the constraint exists.
    """
    __tablename__ = 'product_identifiers'

    id = Column(Integer, primary_key=True, autoincrement=True)

    product_id = Column(
        Integer,
        ForeignKey('products.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # IdentifierType: MPN, GTIN, VENDOR, DISTRIBUTOR, INTERNAL.
    id_type = Column(String(20), nullable=False)
    # Stored normalized -- for GTIN this is the 14-digit key.
    value = Column(String(128), nullable=False, index=True)
    # Scope for VENDOR/DISTRIBUTOR. Empty string means "not vendor-scoped".
    vendor = Column(String(200), nullable=False, default='', server_default='')

    # True when the operator deliberately stored a value that failed check-digit
    # validation (FR-010), so the override is visible rather than silent.
    validation_overridden = Column(Boolean, nullable=False, default=False, server_default='0')

    date_added = Column(DateTime, nullable=False, default=func.now())

    product = relationship('Product', back_populates='identifiers')

    __table_args__ = (
        UniqueConstraint('id_type', 'value', 'vendor', name='uq_identifier_type_value_vendor'),
    )

    def __repr__(self):
        return f"<ProductIdentifier(id={self.id}, type='{self.id_type}', value='{self.value}')>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'product_id': self.product_id,
            'id_type': self.id_type,
            'value': self.value,
            'vendor': self.vendor or None,
            'validation_overridden': self.validation_overridden,
            'date_added': self.date_added.isoformat() if self.date_added else None,
        }


class Tag(Base):
    """
    A free-form label cutting across categories (FR-031).

    Tags are created inline the same way categories are. A tag with no products
    left is harmless and is not garbage-collected on a schedule; if unused tags
    ever clutter the filter UI, that clutter is the measurement that justifies
    adding a cleanup.
    """
    __tablename__ = 'tags'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Stored lowercase-normalized.
    name = Column(String(64), nullable=False, unique=True)

    products = relationship(
        'Product',
        secondary='product_tags',
        back_populates='tags',
    )

    def __repr__(self):
        return f"<Tag(id={self.id}, name='{self.name}')>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {'id': self.id, 'name': self.name}


class ProductTag(Base):
    """Association between a product and a tag"""
    __tablename__ = 'product_tags'

    product_id = Column(
        Integer,
        ForeignKey('products.id', ondelete='CASCADE'),
        primary_key=True
    )
    tag_id = Column(
        Integer,
        ForeignKey('tags.id', ondelete='CASCADE'),
        primary_key=True
    )

    def __repr__(self):
        return f"<ProductTag(product_id={self.product_id}, tag_id={self.tag_id})>"


class ProductAttachment(Base):
    """
    A supporting file on a product or a purchase (FR-034).

    The bytes live in the existing photos table, which already stores three
    sizes, enforces a MIME allow-list, and renders PDF thumbnails with PyMuPDF --
    so datasheets work with no second blob store.

    A datasheet belongs to the product; a saved listing belongs to the purchase
    that captured it. Exactly one owner, never both and never neither.
    """
    __tablename__ = 'product_attachments'

    id = Column(Integer, primary_key=True, autoincrement=True)

    photo_id = Column(
        Integer,
        ForeignKey('photos.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    product_id = Column(
        Integer,
        ForeignKey('products.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    purchase_id = Column(
        Integer,
        ForeignKey('purchases.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )

    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=func.now())

    photo = relationship('Photo')
    product = relationship('Product', back_populates='attachments')
    purchase = relationship('Purchase', back_populates='attachments')

    __table_args__ = (
        CheckConstraint(
            '(product_id IS NOT NULL) <> (purchase_id IS NOT NULL)',
            name='ck_attachment_exactly_one_owner'
        ),
    )

    def __repr__(self):
        return (
            f"<ProductAttachment(id={self.id}, photo_id={self.photo_id}, "
            f"product_id={self.product_id}, purchase_id={self.purchase_id})>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        result = {
            'id': self.id,
            'photo_id': self.photo_id,
            'product_id': self.product_id,
            'purchase_id': self.purchase_id,
            'display_order': self.display_order,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
        if self.photo:
            result['photo'] = self.photo.to_dict()
        return result
