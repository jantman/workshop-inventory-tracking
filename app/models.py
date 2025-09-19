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


# Thread size to series mapping for auto-population
THREAD_SIZE_SERIES_MAPPING = {
    "UNC": ["#0-80", "#1-64", "#2-56", "#3-48", "#4-40", "#5-40", "#6-32", "#8-32", "#10-24", "#12-24",
            "1/4-20", "5/16-18", "3/8-16", "7/16-14", "1/2-13", "9/16-12", "5/8-11", "3/4-10", "7/8-9",
            "1-8", "1 1/8-7", "1 1/4-7", "1 3/8-6", "1 1/2-6"],
    "UNF": ["#0-80", "#1-72", "#2-64", "#3-56", "#4-48", "#5-44", "#6-40", "#8-36", "#10-32", "#12-28",
            "1/4-28", "5/16-24", "3/8-24", "7/16-20", "1/2-20", "9/16-18", "5/8-18", "3/4-16", "7/8-14",
            "1-12", "1 1/8-12", "1 1/4-12", "1 3/8-12", "1 1/2-12"],
    "UNEF": ["#12-32", "1/4-32", "5/16-32", "3/8-32", "7/16-28", "1/2-28", "9/16-24", "5/8-24", "11/16-24",
             "3/4-20", "13/16-20", "7/8-20", "15/16-20", "1-20"],
    "Metric": ["M1x0.25", "M1.2x0.25", "M1.4x0.3", "M1.6x0.35", "M1.8x0.35", "M2x0.4", "M2.5x0.45",
               "M3x0.5", "M3.5x0.6", "M4x0.7", "M5x0.8", "M6x1", "M7x1", "M8x1.25", "M10x1.5", "M12x1.75",
               "M14x2", "M16x2", "M18x2.5", "M20x2.5", "M22x2.5", "M24x3", "M27x3", "M30x3.5", "M33x3.5",
               "M36x4", "M39x4", "M42x4.5", "M3x0.35", "M4x0.5", "M5x0.5", "M6x0.75", "M7x0.75", "M8x1",
               "M10x1.25", "M12x1.25", "M14x1.5", "M16x1.5", "M18x2", "M20x2", "M22x2", "M24x2", "M27x2",
               "M30x3", "M33x3", "M36x3", "M39x3", "M42x3", "M3x0.2", "M4x0.35", "M5x0.35", "M6x0.5",
               "M8x0.75", "M10x1", "M12x1", "M14x1.25", "M16x1.25", "M18x1.5", "M20x1.5"],
    "BSW": ["1/8", "5/32", "3/16", "7/32", "1/4", "9/32", "5/16", "3/8", "7/16", "1/2", "9/16", "5/8",
            "11/16", "3/4", "13/16", "7/8", "15/16", "1", "1 1/8", "1 1/4", "1 3/8", "1 1/2"],
    "BSF": ["1/8", "5/32", "3/16", "7/32", "1/4", "9/32", "5/16", "3/8", "7/16", "1/2", "9/16", "5/8",
            "11/16", "3/4", "13/16", "7/8", "15/16", "1", "1 1/8", "1 1/4"],
    "NPT": ["1/16", "1/8", "1/4", "3/8", "1/2", "3/4", "1", "1 1/4", "1 1/2", "2", "2 1/2", "3", "3 1/2", "4"],
    "Trapezoidal": ["Tr8x1.5", "Tr10x2", "Tr12x3", "Tr14x3", "Tr16x4", "Tr18x4", "Tr20x4", "Tr22x5",
                    "Tr24x5", "Tr26x5", "Tr28x5", "Tr30x6"],
    "Acme": ["1/4-16", "5/16-14", "3/8-12", "7/16-12", "1/2-10", "5/8-8", "3/4-6", "7/8-6", "1-5", "1 1/4-5", "1 1/2-4", "1 3/4-4", "2-4"]
}


def lookup_thread_series(thread_size: str) -> Optional[str]:
    """
    Look up the most likely thread series for a given thread size.

    Args:
        thread_size: Thread size string (e.g., "1/2-13", "M8x1.25")

    Returns:
        Thread series string or None if no match found
    """
    if not thread_size:
        return None

    # Normalize input - case insensitive, strip whitespace
    normalized_size = thread_size.strip().upper()

    # Check each series for a match
    for series, sizes in THREAD_SIZE_SERIES_MAPPING.items():
        for size in sizes:
            if normalized_size == size.upper():
                return series

    return None


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


