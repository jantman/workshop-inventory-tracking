"""
SQLAlchemy database models for Workshop Material Inventory Tracking

This module defines the database schema using SQLAlchemy ORM models.
The schema supports multiple rows per JA ID for maintaining shortening history,
with proper constraints to ensure data integrity.
"""

from sqlalchemy import Column, Integer, String, Decimal, DateTime, Boolean, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional
import enum

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
    length = Column(Decimal(10, 4), nullable=True)  # inches, supports fractions
    width = Column(Decimal(10, 4), nullable=True)   # inches
    thickness = Column(Decimal(10, 4), nullable=True)  # inches 
    wall_thickness = Column(Decimal(10, 4), nullable=True)  # inches
    weight = Column(Decimal(10, 2), nullable=True)  # pounds
    
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
    purchase_price = Column(Decimal(10, 2), nullable=True)
    purchase_location = Column(String(200), nullable=True)
    
    # Additional information
    notes = Column(Text, nullable=True)
    vendor = Column(String(200), nullable=True)
    vendor_part = Column(String(100), nullable=True)
    original_material = Column(String(100), nullable=True)  # For tracking material changes
    original_thread = Column(String(50), nullable=True)  # For tracking thread changes
    
    # Timestamps
    date_added = Column(DateTime, nullable=False, default=func.now())
    last_modified = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Constraints
    __table_args__ = (
        # Ensure only one active row per JA ID
        UniqueConstraint('ja_id', 'active', name='uq_ja_id_active', 
                        sqlite_where="active = 1", mysql_where="active = 1"),
        
        # Ensure positive dimensions
        CheckConstraint('length IS NULL OR length > 0', name='ck_positive_length'),
        CheckConstraint('width IS NULL OR width > 0', name='ck_positive_width'),
        CheckConstraint('thickness IS NULL OR thickness > 0', name='ck_positive_thickness'),
        CheckConstraint('wall_thickness IS NULL OR wall_thickness > 0', name='ck_positive_wall_thickness'),
        CheckConstraint('weight IS NULL OR weight > 0', name='ck_positive_weight'),
        CheckConstraint('quantity > 0', name='ck_positive_quantity'),
        
        # Ensure valid JA ID format
        CheckConstraint("ja_id REGEXP '^JA[0-9]{6}$'", name='ck_valid_ja_id_format'),
    )
    
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
            'vendor_part': self.vendor_part,
            'original_material': self.original_material,
            'original_thread': self.original_thread,
            'date_added': self.date_added.isoformat() if self.date_added else None,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None,
        }

# For backwards compatibility with existing models.py enums
class ItemType(enum.Enum):
    """Enumeration of valid item types"""
    BAR = "Bar"
    PLATE = "Plate"
    SHEET = "Sheet" 
    TUBE = "Tube"
    THREADED_ROD = "Threaded Rod"
    ANGLE = "Angle"

class ItemShape(enum.Enum):
    """Enumeration of valid item shapes"""
    RECTANGULAR = "Rectangular"
    ROUND = "Round"
    SQUARE = "Square"
    HEX = "Hex"

class ThreadSeries(enum.Enum):
    """Enumeration of thread series types"""
    UNC = "UNC"  # Unified National Coarse
    UNF = "UNF"  # Unified National Fine
    UNEF = "UNEF"  # Unified National Extra Fine
    METRIC = "Metric"
    BSW = "BSW"  # British Standard Whitworth
    BSF = "BSF"  # British Standard Fine

class ThreadHandedness(enum.Enum):
    """Enumeration of thread handedness"""
    RIGHT_HAND = "RH"
    LEFT_HAND = "LH"