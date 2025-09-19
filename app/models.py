"""
Data models for Workshop Material Inventory Tracking

These models define the structure and validation rules for inventory items,
including support for different materials, shapes, and threading specifications.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from datetime import datetime, timedelta
from enum import Enum
import re

def parse_date_value(date_value: Union[str, int, float]) -> Optional[datetime]:
    """
    Parse a date value that could be either a string or Excel serial number.
    
    Args:
        date_value: Either a string date or Excel serial number
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_value:
        return None
        
    # If it's already a string, try parsing various formats
    if isinstance(date_value, str):
        # Try ISO format first
        try:
            return datetime.fromisoformat(date_value)
        except ValueError:
            pass
        
        # Try common formats that Google Sheets might use
        formats_to_try = [
            '%Y-%m-%d %H:%M:%S',     # 2025-09-01 9:46:46
            '%Y-%m-%d %H:%M',        # 2025-09-01 9:46
            '%Y-%m-%d',              # 2025-09-01
        ]
        
        for fmt in formats_to_try:
            try:
                return datetime.strptime(date_value, fmt)
            except ValueError:
                continue
        
        return None
    
    # If it's a number, treat as Excel serial date
    if isinstance(date_value, (int, float)):
        try:
            # Excel epoch starts on January 1, 1900, but Excel incorrectly 
            # treats 1900 as a leap year, so we start from 1899-12-30
            excel_epoch = datetime(1899, 12, 30)
            return excel_epoch + timedelta(days=date_value)
        except (ValueError, OverflowError):
            return None
    
    return None

def safe_str(value: Any) -> str:
    """
    Safely convert a value to string, handling None and empty values.
    
    Args:
        value: Any value that needs to be converted to string
        
    Returns:
        String representation, empty string for None/empty values
    """
    if value is None or value == '':
        return ''
    return str(value)

class ItemType(Enum):
    """Enumeration of valid item types"""
    BAR = "Bar"
    PLATE = "Plate"
    SHEET = "Sheet" 
    TUBE = "Tube"
    THREADED_ROD = "Threaded Rod"
    ANGLE = "Angle"

class ItemShape(Enum):
    """Enumeration of valid item shapes"""
    RECTANGULAR = "Rectangular"
    ROUND = "Round"
    SQUARE = "Square"
    HEX = "Hex"

class ThreadSeries(Enum):
    """Enumeration of thread series types"""
    UNC = "UNC"  # Unified National Coarse
    UNF = "UNF"  # Unified National Fine
    UNEF = "UNEF"  # Unified National Extra Fine
    METRIC = "Metric"
    BSW = "BSW"  # British Standard Whitworth
    BSF = "BSF"  # British Standard Fine
    NPT = "NPT"  # National Pipe Thread
    ACME = "Acme"
    TRAPEZOIDAL = "Trapezoidal"  # Trapezoidal threads (merged from ThreadForm)
    SQUARE = "Square"  # Square threads (merged from ThreadForm)
    BUTTRESS = "Buttress"  # Buttress threads (merged from ThreadForm)
    CUSTOM = "Custom"
    OTHER = "Other"

class ThreadHandedness(Enum):
    """Enumeration of thread handedness"""
    RIGHT = "RH"  # Right-hand thread
    LEFT = "LH"   # Left-hand thread


@dataclass
class Thread:
    """Thread specification for threaded items"""
    series: Optional[ThreadSeries] = None
    handedness: Optional[ThreadHandedness] = None
    size: Optional[str] = None  # e.g., "1/2-13", "M12x1.75"
    original: Optional[str] = None  # Original thread specification as entered
    
    def __post_init__(self):
        """Validate thread data after initialization"""
        if self.size and not self._validate_thread_size():
            raise ValueError(f"Invalid thread size format: {self.size}")

        # Validate semantic relationship between size and series
        if self.size and self.series and not self._validate_size_series_compatibility():
            raise ValueError(f"Thread size '{self.size}' is not compatible with series '{self.series.value}'")
    
    def _validate_thread_size(self) -> bool:
        """Validate thread size format"""
        if not self.size:
            return True
        
        # Common thread size patterns
        patterns = [
            # Basic patterns
            r'^\d+/\d+-\d+$',           # Fractional: 1/2-13
            r'^\d+-\d+$',               # Number: 10-24
            r'^#\d+-\d+$',              # Machine screw: #10-24
            r'^M\d+x[\d.]+$',           # Metric: M12x1.75
            r'^M\d+-[\d.]+$',           # Metric with dash: M10-1.5 (to be normalized)
            r'^M\d+$',                  # Metric coarse: M12
            r'^\d+/\d+"$',              # Pipe: 1/2"
            
            # Mixed fractions (>1 inch)
            r'^\d+ \d+/\d+-\d+$',       # Mixed fraction: 1 1/8-8
            
            # Thread forms with specifications
            r'^\d+/\d+-\d+\s+\w+$',     # Fractional with form: 3/4-6 Acme
            r'^\d+-\d+\s+\w+$',         # Number with form: 1-5 Acme  
            r'^\d+ \d+/\d+-\d+\s+\w+$', # Mixed fraction with form: 1 1/8-7 Acme
            r'^\d+x\d+\s+\w+$',         # Metric-like with form: 16x3 Trapezoidal
            r'^\d+x\d+$',               # Trapezoidal without suffix: 16x3
            
            # Handle multiple spaces (normalize later)
            r'^\d+/\d+-\d+\s+\s+\w+$',  # Extra spaces: 1 1/4-5  Acme
        ]
        
        return any(re.match(pattern, self.size) for pattern in patterns)

    def _validate_size_series_compatibility(self) -> bool:
        """Validate that thread size format is compatible with thread series"""
        if not self.size or not self.series:
            return True  # No validation needed if either is missing

        size = self.size
        series = self.series

        # Check format-specific requirements first
        # Metric threads (M prefix) can ONLY be METRIC series
        if re.match(r'^M\d+', size):
            return series == ThreadSeries.METRIC

        # Trapezoidal threads (digit x digit format) can ONLY be TRAPEZOIDAL series
        if re.match(r'^\d+x\d+$', size):
            return series == ThreadSeries.TRAPEZOIDAL

        # Pipe threads (ends with ") can ONLY be NPT series
        if re.match(r'^\d+/\d+"$', size):
            return series == ThreadSeries.NPT

        # Now check series-specific requirements (what formats each series accepts)
        if series == ThreadSeries.METRIC:
            # METRIC series can ONLY accept M-prefix formats
            return bool(re.match(r'^M\d+', size))

        elif series == ThreadSeries.TRAPEZOIDAL:
            # TRAPEZOIDAL series can ONLY accept digit x digit format
            return bool(re.match(r'^\d+x\d+$', size))

        elif series == ThreadSeries.NPT:
            # NPT series can accept pipe formats or standard formats
            return bool(re.match(r'^(\d+/\d+")|\d+/\d+-\d+|\d+-\d+)$', size))

        elif series == ThreadSeries.ACME:
            # Acme threads can use standard fractional or whole number formats
            return bool(re.match(r'^(\d+/\d+-\d+|\d+-\d+|\d+ \d+/\d+-\d+)$', size))

        elif series in [ThreadSeries.UNC, ThreadSeries.UNF, ThreadSeries.UNEF]:
            # Unified National threads - standard inch formats
            return bool(re.match(r'^(\d+/\d+-\d+|\d+-\d+|#\d+-\d+|\d+ \d+/\d+-\d+)$', size))

        elif series in [ThreadSeries.BSW, ThreadSeries.BSF]:
            # British Standard formats (similar to UN)
            return bool(re.match(r'^(\d+/\d+-\d+|\d+-\d+)$', size))

        # For other series (SQUARE, BUTTRESS, CUSTOM, OTHER), allow flexibility
        else:
            return True


    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            'series': self.series.value if self.series else None,
            'handedness': self.handedness.value if self.handedness else None,
            'size': self.size,
            'original': self.original
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Thread':
        """Create Thread from dictionary"""
        series = ThreadSeries(data['series']) if data.get('series') else None
        handedness = ThreadHandedness(data['handedness']) if data.get('handedness') else None

        return cls(
            series=series,
            handedness=handedness,
            size=data.get('size'),
            original=data.get('original')
        )

@dataclass
class Dimensions:
    """Physical dimensions of an item with decimal precision preservation"""
    length: Optional[Decimal] = None
    width: Optional[Decimal] = None  # Also used as diameter for round items
    thickness: Optional[Decimal] = None
    wall_thickness: Optional[Decimal] = None
    weight: Optional[Decimal] = None
    
    def __post_init__(self):
        """Convert string values to Decimal and validate"""
        for field_name in ['length', 'width', 'thickness', 'wall_thickness', 'weight']:
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, Decimal):
                try:
                    # Convert to Decimal, preserving original precision
                    if isinstance(value, str) and value.strip():
                        decimal_value = Decimal(str(value))
                    elif isinstance(value, (int, float)):
                        decimal_value = Decimal(str(value))
                    else:
                        decimal_value = None
                    
                    setattr(self, field_name, decimal_value)
                except (InvalidOperation, ValueError) as e:
                    raise ValueError(f"Invalid {field_name}: {value}") from e
    
    @property
    def diameter(self) -> Optional[Decimal]:
        """Alias for width when dealing with round items"""
        return self.width
    
    @diameter.setter 
    def diameter(self, value: Optional[Decimal]):
        """Set diameter (width) for round items"""
        self.width = value
    
    def volume(self, shape: ItemShape) -> Optional[Decimal]:
        """Calculate approximate volume based on shape"""
        if not self.length:
            return None
            
        try:
            if shape == ItemShape.RECTANGULAR and self.width and self.thickness:
                return self.length * self.width * self.thickness
            elif shape == ItemShape.ROUND and self.width:
                # Cylinder volume: π * r² * h
                radius = self.width / 2
                pi = Decimal('3.14159265359')
                if self.wall_thickness:
                    # Hollow cylinder
                    outer_area = pi * (radius ** 2)
                    inner_radius = radius - self.wall_thickness
                    inner_area = pi * (inner_radius ** 2) if inner_radius > 0 else 0
                    return (outer_area - inner_area) * self.length
                else:
                    # Solid cylinder
                    return pi * (radius ** 2) * self.length
            elif shape == ItemShape.SQUARE and self.width:
                # Square bar
                if self.wall_thickness:
                    # Hollow square
                    outer_area = self.width ** 2
                    inner_side = self.width - (2 * self.wall_thickness)
                    inner_area = inner_side ** 2 if inner_side > 0 else 0
                    return (outer_area - inner_area) * self.length
                else:
                    # Solid square
                    return (self.width ** 2) * self.length
        except (TypeError, InvalidOperation):
            pass
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            'length': str(self.length) if self.length is not None else None,
            'width': str(self.width) if self.width is not None else None,
            'thickness': str(self.thickness) if self.thickness is not None else None,
            'wall_thickness': str(self.wall_thickness) if self.wall_thickness is not None else None,
            'weight': str(self.weight) if self.weight is not None else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Dimensions':
        """Create Dimensions from dictionary"""
        return cls(
            length=Decimal(data['length']) if data.get('length') else None,
            width=Decimal(data['width']) if data.get('width') else None,
            thickness=Decimal(data['thickness']) if data.get('thickness') else None,
            wall_thickness=Decimal(data['wall_thickness']) if data.get('wall_thickness') else None,
            weight=Decimal(data['weight']) if data.get('weight') else None,
        )


