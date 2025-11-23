"""
SQLAlchemy database models for Workshop Material Inventory Tracking

This module defines the database schema using SQLAlchemy ORM models.
The schema supports multiple rows per JA ID for maintaining shortening history,
with proper constraints to ensure data integrity.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, UniqueConstraint, CheckConstraint, LargeBinary
from sqlalchemy.sql.sqltypes import Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import func
from datetime import datetime
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
    quantity = Column(Integer, nullable=False, default=1)
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
        CheckConstraint('quantity > 0', name='ck_positive_quantity'),
        
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
        
        # Validate quantity
        if self.quantity is not None and self.quantity <= 0:
            errors.append("Quantity must be positive")
        
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
        for field in ['ja_id', 'material', 'quantity', 'location', 'sub_location',
                     'notes', 'vendor', 'vendor_part', 'original_material', 'original_thread']:
            if field in data and data[field] is not None:
                setattr(item, field, data[field])
        
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
                'Quantity': str(self.quantity) if self.quantity else '',
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
        
        # Handle quantity
        quantity_str = row_dict.get('Quantity')
        if quantity_str:
            try:
                item.quantity = int(quantity_str)
            except (ValueError, TypeError):
                item.quantity = 1
        
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
            'quantity': self.quantity,
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


class ItemPhoto(Base):
    """
    Item photos table.
    
    Stores photos associated with inventory items via ja_id.
    Each photo is stored in three sizes: thumbnail (~150px), medium (~800px), and original.
    """
    __tablename__ = 'item_photos'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign key to ja_id (not item.id to maintain association across shortening history)
    ja_id = Column(String(10), nullable=False, index=True)
    
    # File metadata
    filename = Column(String(255), nullable=False)  # Original filename
    content_type = Column(String(100), nullable=False)  # MIME type
    file_size = Column(Integer, nullable=False)  # Original file size in bytes
    
    # Photo data in three sizes
    thumbnail_data = Column(LargeBinary, nullable=False)  # ~150px compressed
    medium_data = Column(LargeBinary, nullable=False)  # ~800px compressed  
    original_data = Column(LargeBinary, nullable=False)  # Original up to 20MB
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Constraints
    __table_args__ = (
        # Ensure valid JA ID format
        CheckConstraint("ja_id REGEXP '^JA[0-9]{6}$'", name='ck_photo_valid_ja_id_format'),
        
        # Ensure positive file size
        CheckConstraint('file_size > 0', name='ck_photo_positive_file_size'),
        
        # Validate supported content types
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')", 
            name='ck_photo_valid_content_type'
        ),
    )
    
    def __repr__(self):
        return f"<ItemPhoto(id={self.id}, ja_id='{self.ja_id}', filename='{self.filename}', content_type='{self.content_type}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses (excludes binary data)"""
        return {
            'id': self.id,
            'ja_id': self.ja_id,
            'filename': self.filename,
            'content_type': self.content_type,
            'file_size': self.file_size,
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