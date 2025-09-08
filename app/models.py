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
    CUSTOM = "Custom"
    OTHER = "Other"

class ThreadHandedness(Enum):
    """Enumeration of thread handedness"""
    RIGHT = "RH"  # Right-hand thread
    LEFT = "LH"   # Left-hand thread

class ThreadForm(Enum):
    """Enumeration of thread form types"""
    UN = "UN"                # Unified National (default for inch sizes)
    ISO_METRIC = "ISO Metric"  # ISO Metric (default for metric sizes) 
    ACME = "Acme"            # Acme threads
    TRAPEZOIDAL = "Trapezoidal"  # Trapezoidal threads
    NPT = "NPT"              # National Pipe Thread
    BSW = "BSW"              # British Standard Whitworth
    BSF = "BSF"              # British Standard Fine
    SQUARE = "Square"        # Square threads
    BUTTRESS = "Buttress"    # Buttress threads
    CUSTOM = "Custom"        # Custom/specialized forms
    OTHER = "Other"          # Other thread forms

@dataclass
class Thread:
    """Thread specification for threaded items"""
    series: Optional[ThreadSeries] = None
    handedness: Optional[ThreadHandedness] = None
    form: Optional[ThreadForm] = None  # Thread form type (UN, Acme, etc.)
    size: Optional[str] = None  # e.g., "1/2-13", "M12x1.75"
    original: Optional[str] = None  # Original thread specification as entered
    
    def __post_init__(self):
        """Validate thread data after initialization"""
        if self.size and not self._validate_thread_size():
            raise ValueError(f"Invalid thread size format: {self.size}")
        
        # Validate semantic relationship between size and form
        if self.size and self.form and not self._validate_size_form_compatibility():
            raise ValueError(f"Thread size '{self.size}' is not compatible with form '{self.form.value}'")
    
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
    
    def _validate_size_form_compatibility(self) -> bool:
        """Validate that thread size format is compatible with thread form"""
        if not self.size or not self.form:
            return True  # No validation needed if either is missing
        
        size = self.size
        form = self.form
        
        # Metric threads (M prefix) should have ISO Metric form
        if re.match(r'^M\d+', size):
            return form == ThreadForm.ISO_METRIC
        
        # Trapezoidal threads (digit x digit format)
        if re.match(r'^\d+x\d+$', size):
            return form == ThreadForm.TRAPEZOIDAL
        
        # Pipe threads (ends with ")
        if re.match(r'^\d+/\d+"$', size):
            return form == ThreadForm.NPT
        
        # Acme threads - typically fractional or whole number formats
        # But need to be explicitly marked as Acme (can't infer from size alone)
        if form == ThreadForm.ACME:
            # Acme threads can use standard fractional or whole number formats
            return bool(re.match(r'^(\d+/\d+-\d+|\d+-\d+|\d+ \d+/\d+-\d+)$', size))
        
        # UN (Unified National) threads - standard inch formats
        if form == ThreadForm.UN:
            # Standard inch thread formats
            return bool(re.match(r'^(\d+/\d+-\d+|\d+-\d+|#\d+-\d+|\d+ \d+/\d+-\d+)$', size))
        
        # BSW/BSF - British Standard formats (similar to UN)
        if form in [ThreadForm.BSW, ThreadForm.BSF]:
            return bool(re.match(r'^(\d+/\d+-\d+|\d+-\d+)$', size))
        
        # Trapezoidal threads must use digit x digit format
        if form == ThreadForm.TRAPEZOIDAL:
            return bool(re.match(r'^\d+x\d+$', size))
        
        # For other forms (SQUARE, BUTTRESS, CUSTOM, OTHER), allow flexibility
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            'series': self.series.value if self.series else None,
            'handedness': self.handedness.value if self.handedness else None,
            'form': self.form.value if self.form else None,
            'size': self.size,
            'original': self.original
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Thread':
        """Create Thread from dictionary"""
        series = ThreadSeries(data['series']) if data.get('series') else None
        handedness = ThreadHandedness(data['handedness']) if data.get('handedness') else None
        form = ThreadForm(data['form']) if data.get('form') else None
        
        return cls(
            series=series,
            handedness=handedness,
            form=form,
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

@dataclass
class Item:
    """
    Core inventory item model with complete field set and validation
    
    Represents a single material item in the workshop inventory with
    all necessary metadata, dimensions, and tracking information.
    """
    
    # Required fields
    ja_id: str  # JA000001 format
    item_type: ItemType
    shape: ItemShape
    material: str
    
    # Dimensions
    dimensions: Dimensions = field(default_factory=Dimensions)
    
    # Threading (optional)
    thread: Optional[Thread] = None
    
    # Status and quantity
    active: bool = True
    quantity: int = 1
    
    # Location tracking
    location: Optional[str] = None
    sub_location: Optional[str] = None
    
    # Purchase information
    purchase_date: Optional[datetime] = None
    purchase_price: Optional[Decimal] = None
    purchase_location: Optional[str] = None
    vendor: Optional[str] = None
    vendor_part_number: Optional[str] = None
    
    # Additional metadata
    notes: Optional[str] = None
    
    # Original data preservation (for migration audit trail)
    original_material: Optional[str] = None
    original_thread: Optional[str] = None
    
    # System metadata
    date_added: datetime = field(default_factory=datetime.now)
    last_modified: datetime = field(default_factory=datetime.now)
    
    # Parent-child relationships (for shortened items)
    parent_ja_id: Optional[str] = None
    child_ja_ids: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate item data after initialization"""
        self._validate_ja_id()
        self._validate_required_fields()
        self._validate_dimensions()
        
        # Update last_modified timestamp
        self.last_modified = datetime.now()
    
    def _validate_ja_id(self):
        """Validate JA ID format"""
        if not self.ja_id:
            raise ValueError("JA ID is required")
        
        if not re.match(r'^JA\d{6}$', self.ja_id):
            raise ValueError(f"Invalid JA ID format: {self.ja_id}. Expected format: JA######")
    
    def _validate_required_fields(self):
        """Validate required fields based on type and shape"""
        errors = []
        
        # Basic required fields
        if not self.material or not self.material.strip():
            errors.append("Material is required")
        
        # Type and shape-specific dimension requirements
        if self.item_type == ItemType.THREADED_ROD:
            # Threaded rods only need length and thread specification
            if not self.dimensions.length:
                errors.append("Length is required for threaded rods")
            if not self.thread or not self.thread.size:
                errors.append("Thread specification is required for threaded rods")
        elif self.shape == ItemShape.RECTANGULAR:
            if not self.dimensions.length:
                errors.append("Length is required for rectangular items")
            if not self.dimensions.width:
                errors.append("Width is required for rectangular items") 
            if not self.dimensions.thickness:
                errors.append("Thickness is required for rectangular items")
                
        elif self.shape == ItemShape.ROUND:
            if not self.dimensions.length:
                errors.append("Length is required for round items")
            if not self.dimensions.width:  # width = diameter for round items
                errors.append("Diameter (width) is required for round items")
                
        elif self.shape == ItemShape.SQUARE:
            if not self.dimensions.length:
                errors.append("Length is required for square items")
            if not self.dimensions.width:
                errors.append("Width is required for square items")
        
        if errors:
            raise ValueError("Validation errors: " + "; ".join(errors))
    
    def _validate_dimensions(self):
        """Validate dimension values are positive"""
        # Weight is optional and can be empty/None, so exclude it from validation
        dimension_fields = ['length', 'width', 'thickness', 'wall_thickness']
        
        for field_name in dimension_fields:
            value = getattr(self.dimensions, field_name)
            if value is not None and value <= 0:
                raise ValueError(f"{field_name.title()} must be positive")
    
    @property
    def display_name(self) -> str:
        """Generate a human-readable display name"""
        parts = [self.material, self.item_type.value, self.shape.value]
        
        if self.dimensions.length:
            if self.shape == ItemShape.ROUND:
                parts.append(f"⌀{self.dimensions.width} × {self.dimensions.length}")
            elif self.shape == ItemShape.RECTANGULAR:
                parts.append(f"{self.dimensions.width} × {self.dimensions.thickness} × {self.dimensions.length}")
            elif self.shape == ItemShape.SQUARE:
                parts.append(f"{self.dimensions.width} × {self.dimensions.length}")
        
        return " ".join(str(p) for p in parts if p)
    
    @property 
    def is_threaded(self) -> bool:
        """Check if item has threading specification"""
        return self.thread is not None and (
            self.thread.series is not None or 
            self.thread.size is not None
        )
    
    @property
    def estimated_volume(self) -> Optional[Decimal]:
        """Calculate estimated volume"""
        return self.dimensions.volume(self.shape)
    
    def add_child(self, child_ja_id: str):
        """Add a child item (for tracking shortened pieces)"""
        if child_ja_id not in self.child_ja_ids:
            self.child_ja_ids.append(child_ja_id)
            self.last_modified = datetime.now()
    
    def remove_child(self, child_ja_id: str):
        """Remove a child item"""
        if child_ja_id in self.child_ja_ids:
            self.child_ja_ids.remove(child_ja_id)
            self.last_modified = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert item to dictionary representation"""
        return {
            'ja_id': self.ja_id,
            'item_type': self.item_type.value,
            'shape': self.shape.value,
            'material': self.material,
            'dimensions': self.dimensions.to_dict(),
            'thread': self.thread.to_dict() if self.thread else None,
            'active': self.active,
            'quantity': self.quantity,
            'location': self.location,
            'sub_location': self.sub_location,
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date else None,
            'purchase_price': str(self.purchase_price) if self.purchase_price else None,
            'purchase_location': self.purchase_location,
            'vendor': self.vendor,
            'vendor_part_number': self.vendor_part_number,
            'notes': self.notes,
            'original_material': self.original_material,
            'original_thread': self.original_thread,
            'date_added': self.date_added.isoformat(),
            'last_modified': self.last_modified.isoformat(),
            'parent_ja_id': self.parent_ja_id,
            'child_ja_ids': self.child_ja_ids.copy(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Item':
        """Create Item from dictionary representation"""
        # Handle enums
        item_type = ItemType(data['item_type'])
        shape = ItemShape(data['shape'])
        
        # Handle dimensions
        dimensions = Dimensions.from_dict(data.get('dimensions', {}))
        
        # Handle thread
        thread = None
        if data.get('thread'):
            thread = Thread.from_dict(data['thread'])
        
        # Handle dates
        purchase_date = parse_date_value(data.get('purchase_date'))
        date_added = parse_date_value(data['date_added'])
        last_modified = parse_date_value(data['last_modified'])
        
        # date_added and last_modified are required
        if not date_added:
            raise ValueError("date_added is required")
        if not last_modified:
            raise ValueError("last_modified is required")
        
        # Handle purchase price
        purchase_price = None
        if data.get('purchase_price'):
            purchase_price = Decimal(data['purchase_price'])
        
        return cls(
            ja_id=data['ja_id'],
            item_type=item_type,
            shape=shape,
            material=data['material'],
            dimensions=dimensions,
            thread=thread,
            active=data.get('active', True),
            quantity=data.get('quantity', 1),
            location=data.get('location'),
            sub_location=data.get('sub_location'),
            purchase_date=purchase_date,
            purchase_price=purchase_price,
            purchase_location=data.get('purchase_location'),
            vendor=data.get('vendor'),
            vendor_part_number=data.get('vendor_part_number'),
            notes=data.get('notes'),
            original_material=data.get('original_material'),
            original_thread=data.get('original_thread'),
            date_added=date_added,
            last_modified=last_modified,
            parent_ja_id=data.get('parent_ja_id'),
            child_ja_ids=data.get('child_ja_ids', []).copy(),
        )
    
    def to_row(self, headers: List[str]) -> List[str]:
        """Convert item to a row format matching given headers"""
        row = []
        data_dict = self.to_dict()
        
        for header in headers:
            # Map headers to data fields
            header_mappings = {
                'Active': 'Yes' if self.active else 'No',
                'JA ID': self.ja_id,
                'Length': str(self.dimensions.length) if self.dimensions.length else '',
                'Width': str(self.dimensions.width) if self.dimensions.width else '',
                'Thickness': str(self.dimensions.thickness) if self.dimensions.thickness else '',
                'Wall Thickness': str(self.dimensions.wall_thickness) if self.dimensions.wall_thickness else '',
                'Weight': str(self.dimensions.weight) if self.dimensions.weight else '',
                'Type': self.item_type.value,
                'Shape': self.shape.value,
                'Material': self.material,
                'Thread Series': self.thread.series.value if self.thread and self.thread.series else '',
                'Thread Handedness': self.thread.handedness.value if self.thread and self.thread.handedness else '',
                'Thread Form': self.thread.form.value if self.thread and self.thread.form else '',
                'Thread Size': self.thread.size if self.thread and self.thread.size else '',
                'Quantity': str(self.quantity),
                'Location': self.location or '',
                'Sub-Location': self.sub_location or '',
                'Purchase Date': self.purchase_date.strftime('%Y-%m-%d') if self.purchase_date else '',
                'Purchase Price': str(self.purchase_price) if self.purchase_price else '',
                'Purchase Location': self.purchase_location or '',
                'Notes': self.notes or '',
                'Vendor': self.vendor or '',
                'Vendor Part': self.vendor_part_number or '',
                'Original Material': self.original_material or '',
                'Original Thread': self.original_thread or '',
                'Date Added': self.date_added.isoformat(),
                'Last Modified': self.last_modified.isoformat(),
            }
            
            row.append(header_mappings.get(header, ''))
        
        return row
    
    @classmethod
    def from_row(cls, row: List[str], headers: List[str]) -> 'Item':
        """Create Item from row data with given headers"""
        row_dict = dict(zip(headers, row))
        
        # Convert row data to dictionary format expected by from_dict
        data = {
            'ja_id': row_dict.get('JA ID', ''),
            'item_type': row_dict.get('Type', ''),
            'shape': row_dict.get('Shape', ''),
            'material': row_dict.get('Material', ''),
            'dimensions': {
                'length': row_dict.get('Length', ''),
                'width': row_dict.get('Width', ''),
                'thickness': row_dict.get('Thickness', ''),
                'wall_thickness': row_dict.get('Wall Thickness', ''),
                'weight': row_dict.get('Weight', ''),
            },
            'active': row_dict.get('Active', 'Yes').lower() in ['yes', 'y', 'true', '1'],
            'quantity': int(row_dict.get('Quantity', '1') or 1),
            'location': row_dict.get('Location') or None,
            'sub_location': row_dict.get('Sub-Location') or None,
            'purchase_location': row_dict.get('Purchase Location') or None,
            'vendor': row_dict.get('Vendor') or None,
            'vendor_part_number': row_dict.get('Vendor Part') or None,
            'notes': row_dict.get('Notes') or None,
            'original_material': row_dict.get('Original Material') or None,
            'original_thread': row_dict.get('Original Thread') or None,
        }
        
        # Handle thread data
        thread_series = row_dict.get('Thread Series')
        thread_handedness = row_dict.get('Thread Handedness') 
        thread_form = row_dict.get('Thread Form')
        thread_size = row_dict.get('Thread Size')
        
        if any([thread_series, thread_handedness, thread_form, thread_size]):
            data['thread'] = {
                'series': thread_series or None,
                'handedness': thread_handedness or None,
                'form': thread_form or None,
                'size': thread_size or None,
                'original': row_dict.get('Original Thread') or None,
            }
        
        # Handle dates
        purchase_date_str = row_dict.get('Purchase Date')
        if purchase_date_str:
            try:
                data['purchase_date'] = purchase_date_str
            except ValueError:
                pass
        
        # Handle purchase price
        purchase_price_str = row_dict.get('Purchase Price')
        if purchase_price_str:
            try:
                # Clean currency symbols from price string
                cleaned_price = str(purchase_price_str).strip()
                cleaned_price = cleaned_price.replace('$', '').replace('€', '').replace('£', '').replace('¥', '')
                cleaned_price = cleaned_price.replace(',', '').strip()
                
                if cleaned_price:  # Only use if not empty after cleaning
                    data['purchase_price'] = cleaned_price
            except (ValueError, InvalidOperation):
                pass
        
        # Handle system dates
        date_added_str = row_dict.get('Date Added')
        last_modified_str = row_dict.get('Last Modified')
        
        if date_added_str:
            data['date_added'] = date_added_str
        if last_modified_str:
            data['last_modified'] = last_modified_str
        
        return cls.from_dict(data)