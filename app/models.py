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
import json
import logging
import re

logger = logging.getLogger(__name__)

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
    CHANNEL = "Channel"

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
    UNS = "UNS"  # Unified National Special
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




# ---------------------------------------------------------------------------
# Product catalog
#
# Enums and frozen value types for the product catalog feature. The ORM models
# they describe live in app/database.py; the logic that uses them lives in
# app/catalog_service.py.
# ---------------------------------------------------------------------------

class IdentifierType(Enum):
    """Every coded name a product can carry, by kind.

    Values are stored in product_identifiers.id_type.
    """
    MPN = "MPN"                  # Manufacturer part number
    GTIN = "GTIN"                # Retail barcode, stored as the 14-digit key
    VENDOR = "VENDOR"            # A vendor's own item id (e.g. an ASIN); scoped by vendor
    DISTRIBUTOR = "DISTRIBUTOR"  # A distributor's part number; scoped by vendor
    INTERNAL = "INTERNAL"        # This system's own code; generated, never typed


class ScanKind(Enum):
    """What kind of thing a scan turned out to be.

    INTERNAL, ECIA, GTIN and FREE_TEXT are produced by the pure classifier in
    app/utils/scan_router.py. VENDOR is produced by resolution, not by
    classification -- a vendor item id has no distinguishing shape, so it can
    only be recognized by looking it up.
    """
    INTERNAL = "INTERNAL"
    ECIA = "ECIA"
    GTIN = "GTIN"
    VENDOR = "VENDOR"
    FREE_TEXT = "FREE_TEXT"


class StockStatus(Enum):
    """The operator's manual stock flag.

    Independent of the counted quantity. NULL is the third, absent state and has
    no member here.
    """
    LOW = "low"
    OUT = "out"


@dataclass(frozen=True)
class ScanClassification:
    """The structural answer to 'what kind of thing was scanned?'

    Produced by app.utils.scan_router.classify(), which performs no database
    lookup and never raises on a str.
    """
    kind: 'ScanKind'
    value: str                       # Normalized payload; the raw scan when FREE_TEXT
    raw: str                         # Always the scan exactly as captured
    ecia_fields: Dict[str, str] = field(default_factory=dict)  # Empty unless kind is ECIA

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'kind': self.kind.value,
            'value': self.value,
            'raw': self.raw,
            'ecia_fields': dict(self.ecia_fields),
        }


@dataclass(frozen=True)
class ScanResolution:
    """The answer to 'which product is it, and what should happen next?'

    Produced by CatalogService.resolve_scan(). ``outcome`` is one of 'product',
    'create', 'search' or 'receive'.

    **This docstring used to say "three outcomes and no fourth".** Feature 024
    added ``receive``: a bag from a captured DigiKey order is neither "here is
    the product" nor "here is a blank draft", it is the receipt for one line of
    one order, and encoding that as ``product`` plus a hint would make one
    outcome mean two things. The requirements the old wording cited (001 FR-018,
    SC-008) say that *nothing dead-ends*, and a fourth answer does not weaken
    that -- the free-text rule still always matches.

    ``product`` and ``purchases`` are typed loosely because app/models.py must
    not import app/database.py -- the ORM depends on this module, not the other
    way round.
    """
    outcome: str
    classification: 'ScanClassification'
    product: Optional[Any] = None            # Set iff outcome == 'product'
    prefill: Dict[str, str] = field(default_factory=dict)  # For outcome == 'create'
    # For outcome == 'receive': the purchases the label's 1K and P name. May
    # include already-received ones, so the route can tell "already received"
    # apart from "no such line" (024 FR-023).
    purchases: List[Any] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'outcome': self.outcome,
            'classification': self.classification.to_dict(),
            'product': self.product.to_dict() if self.product is not None else None,
            'prefill': dict(self.prefill),
            'purchases': [purchase.to_dict() for purchase in self.purchases],
        }


@dataclass(frozen=True)
class CaptureAssessment:
    """What a capture found that it will not decide on its own.

    Produced by CatalogService.capture_order() and carried out on
    CaptureDecisionRequired. Two questions can be open at once -- a capture can
    be both a probable repeat and a landing on a recycled identifier -- so the
    two halves are independent and neither implies the other.

    Everything here is a plain value rather than an ORM row. Scalars would in
    fact survive -- ``expire_on_commit`` is off -- but a *relationship* not
    eagerly loaded would not, and a display-only object has no business carrying
    that hazard around. Copying the four strings and two ids the warning panels
    render also means ``to_dict`` needs no second shaping step for the JSON
    representation of the capture endpoint.
    """
    # The repeat: a purchase already recorded for this vendor, item and day.
    duplicate_purchase_id: Optional[int] = None
    duplicate_order_date: Optional[datetime] = None
    duplicate_vendor: Optional[str] = None
    # The supplier order number that purchase carries, when it has one (033
    # FR-018). Set only by the widened arm of ``_find_captured_purchase``, which
    # recognizes a purchase an *order* capture wrote whose date the operator has
    # since typed differently -- and naming the order is what tells them which
    # record they are being asked about.
    duplicate_order_reference: Optional[str] = None

    # The recycled identifier: a product this vendor item id already names,
    # whose manufacturer and part number did not corroborate the capture.
    matched_product_id: Optional[int] = None
    matched_product_description: Optional[str] = None
    matched_product_manufacturer: Optional[str] = None
    matched_product_part_number: Optional[str] = None

    @property
    def has_duplicate(self) -> bool:
        """Whether a matching purchase was already recorded"""
        return self.duplicate_purchase_id is not None

    @property
    def has_uncorroborated_match(self) -> bool:
        """Whether the item id names a product the capture did not corroborate"""
        return self.matched_product_id is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'duplicate_purchase_id': self.duplicate_purchase_id,
            'duplicate_order_date': (
                self.duplicate_order_date.isoformat() if self.duplicate_order_date else None
            ),
            'duplicate_vendor': self.duplicate_vendor,
            'duplicate_order_reference': self.duplicate_order_reference,
            'matched_product_id': self.matched_product_id,
            'matched_product_description': self.matched_product_description,
            'matched_product_manufacturer': self.matched_product_manufacturer,
            'matched_product_part_number': self.matched_product_part_number,
            'has_duplicate': self.has_duplicate,
            'has_uncorroborated_match': self.has_uncorroborated_match,
        }


@dataclass
class CapturedBarcode:
    """What became of one barcode-named row a listing carried (016 FR-009).

    Produced by ``CatalogService.describe_captured_barcodes`` and rendered by the
    capture route into the confirmation page's message. Display-only, and a plain
    value object for the same reason :class:`CaptureAssessment` is one.

    **It states what is true of the barcode after the capture, not what this
    capture did** (FR-009a). ``recorded`` therefore means "this product holds it",
    which reads the same on a first capture and a repeat. Distinguishing the two
    would mean carrying the promotion's outcome out of ``capture_order``, which
    costs a signature change at every one of its call sites to save one true
    sentence; see ``specs/016-promote-captured-gtin/research.md`` section 3.

    The four outcomes are exclusive and exhaustive, tested in this order:

    * ``unusable`` -- the value is not a valid barcode, so nobody can hold it.
    * ``recorded`` -- this product holds it.
    * ``taken`` -- another product holds it, named by ``holder_id``.
    * ``not_examined`` -- the merge dropped the row, so the captured value is
      stored nowhere.

    ``kept_as_specification`` is what stops the report claiming the value is on
    the product when it is not. A captured row whose name the product already
    lists is dropped whole, value included -- so an unusable or contested value
    on such a row is not "kept as a specification", and saying it was would be
    the silent loss this report exists to prevent.
    """
    row_name: str
    value: str
    outcome: str
    holder_id: Optional[int] = None
    holder_description: Optional[str] = None
    kept_as_specification: bool = True


@dataclass
class ImageCaptureResult:
    """What the fetcher managed, so the route can tell the operator.

    Plain counts and one flag (FR-017, FR-020, FR-021, FR-022). There is
    deliberately **no per-image error list**: nothing would consume one, because
    the operator's next action is the same whether an image failed on a timeout
    or a 404 -- add it by hand, or capture again.
    """
    stored: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed: int = 0
    cap_reached: bool = False


# The payload shape capture-agent.js produces. There is exactly one version and
# no compatibility machinery: when the shape changes the number goes to 2 and
# from_json stops accepting 1, at which point a stale cached agent degrades to
# today's behaviour on its next use and is replaced on the one after.
LISTING_CAPTURE_VERSION = 1


def normalized_row_name(name: Optional[str]) -> str:
    """A specification row's name, folded for comparison against a fixed list.

    Trims, collapses internal runs of whitespace, and upper-cases, so
    ``mfr  part number`` and ``  Mfr Part Number `` are one name.

    **Shared with the barcode-row matcher** (``_is_barcode_row_name`` in
    ``catalog_service``), which is where this body came from. 019 FR-001
    requires the part-number names to fold exactly as the barcode names already
    do, and the only way to keep that true is for there to be one
    implementation. Two lists that fold differently is the failure this
    prevents.

    Not to be confused with ``catalog_service._fold``, which case-folds and
    trims but deliberately does **not** collapse internal whitespace. That one
    compares two arbitrary operator-supplied strings; this one matches against a
    fixed list of ASCII names. Different questions, different tools.
    """
    return ' '.join((name or '').split()).upper()


# The product-information row names that mean "this value is the manufacturer's
# part number", in **priority order** -- 019 FR-002. Stored already normalized,
# so they compare against normalized_row_name(...) directly.
#
# **A tuple, where BARCODE_ROW_NAMES is a frozenset**, because order is the
# specification here and is not there. A listing publishing both Model Number
# and Mfr Part Number means the second one; membership alone cannot say that.
#
# The order encodes confidence and the bottom of it is deliberately loose. The
# first two say what they are. PART NUMBER may be the vendor's rather than the
# manufacturer's, and the two model names may be a marketing model that is not
# orderable as a part. They earn their place because the operator reviews every
# value this produces and can overrule it -- see ListingCapture's method below.
PART_NUMBER_ROW_NAMES = (
    'MANUFACTURER PART NUMBER',
    'MFR PART NUMBER',
    'PART NUMBER',
    'MODEL NUMBER',
    'ITEM MODEL NUMBER',
)

# Mirrors the String(100) on Product.manufacturer_part_number at
# app/database.py:838.
#
# **Nothing in the stack checks this length**: _clean strips and nothing more,
# and catalog_service validates no field width. So a derived default longer than
# the column would submit, the capture would run, the gallery would be
# retrieved, and only then would the write fail -- an error at the end of a
# fifteen-second operation over a value the operator never typed. A candidate
# that does not fit is passed over instead (019 FR-003), never truncated: a
# truncated part number is a wrong one, and a wrong one corroborates a later
# repeat buy against the wrong product.
MANUFACTURER_PART_NUMBER_MAX_LENGTH = 100


@dataclass
class ListingCapture:
    """What the capture agent read off a vendor's listing.

    Not persisted. It exists between the form field ``listing`` and the two
    services that consume it, and it is built only by :meth:`from_json`.

    **``price`` is a string, deliberately.** JSON's only number type is an IEEE
    double, so ``24.99`` arriving as a JSON number would be a ``float`` before
    any Python here saw it, and Principle III has no exemption for a value in
    transit. It stays a string until ``_validate_price`` turns it into a
    ``Decimal`` -- the same path a hand-typed price already takes.
    """
    source_url: str
    vendor_item_id: Optional[str] = None
    listing_title: Optional[str] = None
    price: Optional[str] = None
    brand: Optional[str] = None
    description_text: Optional[str] = None
    specifications: List[Dict[str, str]] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    # What a pack cost and how many were in it, where the vendor prices by the
    # pack. **Neither is recorded anywhere**: they pre-fill the two fields
    # feature 017 put on the confirmation page, which exist to produce the unit
    # price and to still be there explaining it when the form comes back with a
    # question. There is no pack size in the schema and this is not the
    # beginning of one -- what is stored is a unit price.
    #
    # Strings, like `price` and for the same reason: JSON's only number type is
    # an IEEE double (Constitution III).
    pack_price: Optional[str] = None
    pack_size: Optional[str] = None

    @property
    def unit_price_from_pack(self) -> Optional[str]:
        """The unit price the pack fields imply, or None.

        The confirmation form's ``#unit_price`` is what actually gets recorded,
        and it falls back to this when a vendor priced by the pack and gave no
        unit price of its own -- which is every pack-priced McMaster product.

        **Without it that field renders empty and the purchase records a NULL
        price**, on a page that is plainly showing "$13.23 per pack of 100".
        `pack-unit-price.js` does not fill the gap: it deliberately writes the
        price field only once the operator has *typed* in a pack field, because
        writing on load would discard a price they had typed over the derived
        one before a re-render brought the form back. That guard is right and is
        left alone; this supplies the initial value instead.

        Derived here rather than in the agent because the arithmetic is a
        division: doing it in JavaScript would put a price through a binary
        float before it ever reached Python, and Constitution III has no
        exemption for a value in transit. `Decimal` throughout, quantized by the
        same `price_to_cents` every other price on this path goes through.
        """
        if not self.pack_price or not self.pack_size:
            return None
        try:
            paid = Decimal(self.pack_price)
            size = int(self.pack_size)
        except (InvalidOperation, ValueError, TypeError):
            return None
        if size <= 0 or paid < 0:
            return None
        return str(price_to_cents(paid / size))

    def manufacturer_part_number(self) -> Optional[str]:
        """The part number this listing's own rows name, or None (019).

        **A default for the confirmation form, never an assertion about the
        product.** The operator sees it, and can type over it or empty it before
        capturing; nothing downstream may treat a part number as more
        trustworthy for having come from here. Issue #90: the rows were already
        on the page and the field was still being typed by hand.

        The walk is names-outer, rows-inner, which is what makes FR-002's two
        rules fall out rather than needing to be written: priority is by
        position in ``PART_NUMBER_ROW_NAMES`` and never by position on the
        vendor's page, and among rows sharing a name the first captured wins
        because that is the order the inner walk visits them.

        An unusable value does not end the search, it is passed over -- an empty
        ``Model Number`` cell must not stop a real ``Item model number`` two
        rows down (FR-003).

        **Pure**: no I/O, no request, no mutation. A Jinja template calls this,
        so it has to stay that way.

        Returns:
            The row's value with surrounding whitespace removed, or None when no
            row qualifies. None is the ordinary case -- most listings name no
            part number at all -- and never an error.
        """
        for wanted in PART_NUMBER_ROW_NAMES:
            for entry in self.specifications:
                if normalized_row_name(entry.get('name')) != wanted:
                    continue
                value = (entry.get('value') or '').strip()
                if value and len(value) <= MANUFACTURER_PART_NUMBER_MAX_LENGTH:
                    return value
        return None

    @classmethod
    def from_json(cls, raw: Optional[str]) -> Optional['ListingCapture']:
        """Parse the hidden ``listing`` field, or return None.

        **None is not an error, it is the ordinary case for the other half of
        this feature.** The paste-a-URL form has no agent and sends no payload,
        and FR-007 requires a capture with no extraction to behave exactly as it
        does today. So an absent, empty, unparseable, non-object or
        wrong-version payload yields None and the caller carries on.

        Within a well-formed payload the parsing is lenient for the same reason
        one row further down: a malformed specification entry or an image
        address that is not http(s) is dropped on its own, rather than costing
        the operator the other twenty-four rows and the whole gallery.
        """
        if not raw:
            return None

        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            logger.info("Capture payload is not JSON; capturing without it")
            return None

        if not isinstance(data, dict):
            logger.info("Capture payload is not an object; capturing without it")
            return None

        if data.get('version') != LISTING_CAPTURE_VERSION:
            logger.info(
                f"Capture payload is version {data.get('version')!r}, not "
                f"{LISTING_CAPTURE_VERSION}; capturing without it. A stale cached "
                f"agent is the only way this happens."
            )
            return None

        source_url = _payload_string(data.get('source_url'))
        if not source_url:
            logger.info("Capture payload names no source_url; capturing without it")
            return None

        return cls(
            source_url=source_url,
            vendor_item_id=_payload_string(data.get('vendor_item_id')),
            listing_title=_payload_string(data.get('listing_title')),
            price=_payload_string(data.get('price')),
            brand=_payload_string(data.get('brand')),
            description_text=_payload_string(data.get('description_text')),
            specifications=_payload_specifications(data.get('specifications')),
            images=_payload_images(data.get('images')),
            pack_price=_payload_string(data.get('pack_price')),
            pack_size=_payload_string(data.get('pack_size')),
        )


def _payload_string(value: Any) -> Optional[str]:
    """A trimmed string, or None for anything that is not one.

    A JSON number is refused rather than coerced. The only field where that
    matters is ``price``, and there it is the whole point: an agent that emitted
    ``"price": 24.99`` has already turned the price into a float, and accepting
    it here would carry that float onwards under a str() disguise.
    """
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _payload_specifications(value: Any) -> List[Dict[str, str]]:
    """The ``{name, value}`` pairs that are actually pairs; the rest are dropped"""
    if not isinstance(value, list):
        return []

    entries: List[Dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        name = _payload_string(entry.get('name'))
        text = _payload_string(entry.get('value'))
        if name and text:
            entries.append({'name': name, 'value': text})
    return entries


def _payload_images(value: Any) -> List[str]:
    """The http(s) addresses, in order; anything else is dropped"""
    if not isinstance(value, list):
        return []

    return [
        address for address in (
            _payload_string(item) for item in value
        )
        if address and (
            address.startswith('http://') or address.startswith('https://')
        )
    ]


# ---------------------------------------------------------------------------
# DigiKey order capture (feature 024)
#
# What DigiKey's Order Status and Product Information APIs said, and what a
# review of an order concluded. None of it is persisted: an order becomes
# purchases, and a captured order is derived back from them.
#
# These are the seam. `app/services/digikey.py` builds them and nothing else
# does, so a DigiKey JSON field name appears nowhere past this module -- which
# is what let feature 024 absorb v4 renaming most of its fields between the plan
# and the implementation at the cost of one mapping table.
# ---------------------------------------------------------------------------

# Purchase.unit_price is Numeric(10, 2) and MariaDB rounds silently on write --
# even under STRICT_TRANS_TABLES, which downgrades it to a Note rather than an
# error. So a price has to be rounded deliberately, here, where it is visible.
#
# This is not a DigiKey quirk: feature 017 already established that this catalog
# records prices to the cent and says so on screen when a pack price does not
# divide evenly. What is new is that DigiKey routinely *quotes* sub-cent unit
# prices -- 0.0126 for a passive at volume is ordinary -- so what used to be an
# edge case is now the common one. PR #116 review.
PRICE_EXPONENT = Decimal('0.01')


def price_to_cents(value: Optional[Decimal]) -> Optional[Decimal]:
    """Round a price to the cent, ROUND_HALF_UP (Constitution III).

    Deliberate and lossy: 0.0126 becomes 0.01, which is 20% low on that line.
    The loss is the column's, not this function's -- but doing it here means the
    stored value is one this code chose rather than one the database silently
    imposed, and it means a value read back compares equal to the value written.
    """
    if value is None:
        return None
    return value.quantize(PRICE_EXPONENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class DigiKeyOrderLine:
    """One line of a DigiKey sales order.

    **There is no manufacturer here**, and its absence is not an oversight: a v4
    order line carries the manufacturer's *part number* but never the
    manufacturer's *name*. That, and the category, datasheet, photograph and
    parametric detail, come from a separate part lookup -- which is why capture
    enriches every line (FR-040) rather than taking the order response as the
    whole story.

    ``quantity_shipped`` and ``quantity_backorder`` are display-only. They let
    the review say "4 of 10 shipped, 6 on backorder" without inventing a
    partial-receipt state that ``Purchase`` does not have and this feature does
    not add.
    """
    digikey_part_number: str
    manufacturer_part_number: str = ''
    description: str = ''
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    quantity_shipped: Optional[int] = None
    quantity_backorder: Optional[int] = None
    country_of_origin: str = ''
    line_number: Optional[int] = None

    @property
    def form_key(self) -> str:
        """What names this line in a form, and what a decision is keyed by.

        ``DetailId`` where DigiKey gave one, because **a part number does not
        identify a line**: an order can carry the same part twice, which this
        feature's own spec accounts for. Keying the form by part number gave two
        such lines one shared ``include[]`` / ``description[]`` /
        ``resolution[]``, so neither could be controlled on its own. PR #116
        review.

        Falls back to the part number when there is no DetailId, which restores
        exactly the old behaviour for a response that carries none.
        """
        if self.line_number is not None:
            return str(self.line_number)
        return self.digikey_part_number

    @classmethod
    def from_payload(cls, data: Any) -> Optional['DigiKeyOrderLine']:
        """Build from one element of the response's ``LineItems``.

        Returns None for anything that is not an object naming a DigiKey part
        number -- there is no line without one, since it is half the key a
        scanned bag is matched on.

        **Never raises on a JSON value.** A field DigiKey stops sending costs
        that field and nothing else; the same rule the capture agent follows for
        a vendor's markup.
        """
        if not isinstance(data, dict):
            return None

        digikey_part_number = _digikey_string(data.get('DigiKeyProductNumber'))
        if not digikey_part_number:
            return None

        return cls(
            digikey_part_number=digikey_part_number,
            manufacturer_part_number=_digikey_string(data.get('ManufacturerProductNumber')),
            description=_digikey_string(data.get('Description')),
            quantity=_digikey_int(data.get('QuantityOrdered')),
            unit_price=_digikey_decimal(data.get('UnitPrice')),
            quantity_shipped=_digikey_int(data.get('QuantityShipped')),
            quantity_backorder=_digikey_int(data.get('QuantityBackOrder')),
            country_of_origin=_digikey_string(data.get('CountryOfOrigin')),
            # PoLineItemNumber is null on every v4 response observed; DetailId is
            # the 1-based index that actually identifies the line.
            line_number=_digikey_int(data.get('DetailId')),
        )


@dataclass(frozen=True)
class DigiKeyOrder:
    """One DigiKey sales order, as DigiKey reports it.

    ``sales_order_number`` is a string even though DigiKey sends an integer: it
    is a reference that gets compared and stored, never arithmetic.

    Deliberately absent: the shipping address, the contact and the customer id.
    They are personal details the catalog has no use for, so they are not read
    rather than being read and discarded.
    """
    sales_order_number: str
    purchase_order: str = ''
    order_date: Optional[datetime] = None
    currency: str = ''
    lines: tuple = ()

    @classmethod
    def from_payload(cls, data: Any) -> Optional['DigiKeyOrder']:
        """Build from a ``salesorder`` response body.

        Returns None when the body is not an object or names no sales order --
        which is how a 200 carrying nothing useful becomes "not found" rather
        than an empty order the operator would be invited to capture.
        """
        if not isinstance(data, dict):
            return None

        sales_order_number = _digikey_string(data.get('SalesOrderId'), numbers_ok=True)
        if not sales_order_number:
            return None

        lines = tuple(
            line for line in (
                DigiKeyOrderLine.from_payload(entry)
                for entry in (data.get('LineItems') or [])
            )
            if line is not None
        )

        return cls(
            sales_order_number=sales_order_number,
            purchase_order=_digikey_string(data.get('PurchaseOrder')),
            order_date=_digikey_datetime(data.get('DateEntered')),
            currency=_digikey_string(data.get('Currency')),
            lines=lines,
        )


@dataclass(frozen=True)
class DigiKeyOrderSummary:
    """One row of DigiKey's order listing -- enough to pick an order, no more.

    Feature 031. A backfill starts from nothing, and this is the list.

    **A sales order, not an order.** DigiKey's listing nests one or more
    ``SalesOrders`` inside each ``Orders`` entry, splitting a backorder or a
    second shipment out under the same web order number. The sales order is what
    :meth:`DigiKeyClient.get_order` takes and what a bag label's ``1K`` field
    names, so the listing flattens to one of these per sales order. Reading the
    outer ``OrderNumber`` would produce a listing whose every row 404s
    (verification.md).

    Deliberately absent, exactly as :class:`DigiKeyOrder` is: the contact, the
    shipping address and the customer id. The listing response carries all three
    for every order, and they are not read rather than read and discarded.
    """
    sales_order_number: str
    order_date: Optional[datetime] = None
    purchase_order: str = ''
    status: str = ''
    line_count: int = 0

    @classmethod
    def from_payload(cls, data: Any) -> Optional['DigiKeyOrderSummary']:
        """Build from one ``SalesOrders`` entry of an ``orders`` response.

        Returns None for an entry naming no sales order, so one unreadable row
        costs its own row and not the listing.
        """
        if not isinstance(data, dict):
            return None

        sales_order_number = _digikey_string(data.get('SalesOrderId'), numbers_ok=True)
        if not sales_order_number:
            return None

        status = data.get('Status')
        return cls(
            sales_order_number=sales_order_number,
            order_date=_digikey_datetime(data.get('DateEntered')),
            purchase_order=_digikey_string(data.get('PurchaseOrder')),
            status=(
                _digikey_string(status.get('ShortDescription'))
                if isinstance(status, dict) else ''
            ),
            # Free: the listing already carries the lines. Nothing else in that
            # array is read -- this is a chooser, not a review.
            line_count=len(data.get('LineItems') or []),
        )


@dataclass(frozen=True)
class DigiKeyPart:
    """DigiKey's own detail for one part.

    Used twice: to enrich every line of an order at capture (FR-040), and to
    catalog a single part on its own (FR-027).

    Several of these are nested in the v4 response rather than being the flat
    strings the older shape suggested -- ``Manufacturer.Name``,
    ``Description.ProductDescription``, ``Category.Name``. The nesting is
    absorbed here so that nothing downstream knows about it.
    """
    digikey_part_number: str = ''
    manufacturer_part_number: str = ''
    manufacturer: str = ''
    description: str = ''
    detailed_description: str = ''
    datasheet_url: str = ''
    photo_url: str = ''
    product_url: str = ''
    category_path: str = ''
    unit_price: Optional[Decimal] = None
    parameters: tuple = ()

    @classmethod
    def from_payload(cls, data: Any) -> Optional['DigiKeyPart']:
        """Build from a ``productdetails`` response body.

        Returns None when the body names no product. Every *field* is optional:
        a part with no datasheet is a part with no datasheet, never a failed
        lookup.
        """
        if not isinstance(data, dict):
            return None

        product = data.get('Product')
        if not isinstance(product, dict):
            return None

        description = product.get('Description')
        description = description if isinstance(description, dict) else {}
        manufacturer = product.get('Manufacturer')
        manufacturer = manufacturer if isinstance(manufacturer, dict) else {}
        category = product.get('Category')
        category = category if isinstance(category, dict) else {}

        parameters = tuple(
            (name, value) for name, value in (
                (
                    _digikey_string(entry.get('ParameterText')),
                    _digikey_string(entry.get('ValueText'), numbers_ok=True),
                )
                for entry in (product.get('Parameters') or [])
                if isinstance(entry, dict)
            )
            if name and value
        )

        return cls(
            digikey_part_number=_digikey_variation_number(product.get('ProductVariations')),
            manufacturer_part_number=_digikey_string(product.get('ManufacturerProductNumber')),
            manufacturer=_digikey_string(manufacturer.get('Name')),
            description=_digikey_string(description.get('ProductDescription')),
            detailed_description=_digikey_string(description.get('DetailedDescription')),
            datasheet_url=_digikey_string(product.get('DatasheetUrl')),
            photo_url=_digikey_string(product.get('PhotoUrl')),
            product_url=_digikey_string(product.get('ProductUrl')),
            category_path=_digikey_string(category.get('Name')),
            unit_price=_digikey_decimal(product.get('UnitPrice')),
            parameters=parameters,
        )


def _digikey_string(value: Any, numbers_ok: bool = False) -> str:
    """A trimmed string, or '' for anything that is not usable as one.

    ``numbers_ok`` is for the two fields DigiKey sends as JSON numbers that are
    really identifiers -- ``SalesOrderId``, and the occasional numeric parameter
    value. It is off by default so that a price arriving where a string was
    expected is dropped rather than being stringified out of a float.
    """
    if isinstance(value, str):
        return value.strip()
    if numbers_ok and isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if numbers_ok and isinstance(value, Decimal):
        return str(value)
    return ''


def _digikey_int(value: Any) -> Optional[int]:
    """An int, or None. A bool is not an int here, whatever Python thinks."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except (TypeError, ValueError):
            return None
    return None


def _digikey_decimal(value: Any) -> Optional[Decimal]:
    """A Decimal, or None -- and never by way of a float (Constitution III).

    The client parses with ``json.loads(..., parse_float=Decimal)``, so a price
    arrives here already exact and this is a pass-through. The float branch is
    the guard for a caller that did not: refusing is right, because by then the
    damage is done and a silent ``Decimal(6.9000000000000004)`` is worse than a
    missing price.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except (InvalidOperation, ValueError):
            return None
    if isinstance(value, float):
        logger.warning(
            "DigiKey value arrived as a float, which means json.loads was called "
            "without parse_float=Decimal. Dropping it rather than recording an "
            "inexact price."
        )
    return None


def _naive(value: Optional[datetime]) -> Optional[datetime]:
    """Drop a parsed timestamp's offset, keeping its wall clock.

    **Every datetime a payload parser returns is naive**, because every column
    it can reach is. ``Purchase.order_date`` and ``Purchase.received_date`` are
    naive ``DateTime`` columns, and both SQLAlchemy's SQLite dialect and PyMySQL
    format an aware value by its wall clock and discard the offset -- so an
    aware datetime was never stored as one. What it did instead was travel as
    far as the first comparison and raise there.

    That is not hypothetical: an operator typing an arrival date on a DigiKey
    order review sent a naive datetime into ``_validate_receipt_order`` against
    an aware ``order_date``, and ``TypeError: can't compare offset-naive and
    offset-aware datetimes`` is not a ``ValidationError``, so it went past the
    confirm route's handler as a 500 and lost the whole capture. Found in
    review of PR #128.

    **The offset is dropped, not converted.** Converting would shift new rows
    relative to every row already stored by the behaviour described above, which
    would be a silent data change to fix a crash.
    """
    if value is None or value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)


def _digikey_datetime(value: Any) -> Optional[datetime]:
    """DigiKey's ISO 8601 timestamp, or None.

    Their offsets are real ones ('2026-08-07T17:34:04.332-05:00'), and a 'Z'
    turns up on shipment dates, which ``fromisoformat`` handles from 3.11.

    Naive on the way out; see :func:`_naive` for why the offset cannot survive
    the trip to a column anyway.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _naive(datetime.fromisoformat(value.strip().replace('Z', '+00:00')))
    except ValueError:
        return None


def _digikey_variation_number(value: Any) -> str:
    """The DigiKey part number off the product variations, or ''.

    A part has several variations -- cut tape, tape and reel, digi-reel -- each
    with its own number. The first is taken because this is only a fallback: on
    an order capture the line already carries the number that was actually
    bought, and that one wins.
    """
    if not isinstance(value, list):
        return ''
    for entry in value:
        if not isinstance(entry, dict):
            continue
        number = _digikey_string(entry.get('DigiKeyProductNumber'))
        if number:
            return number
    return ''


# ---------------------------------------------------------------------------
# McMaster-Carr: what the capture agent read off an order page
# ---------------------------------------------------------------------------
#
# These are the payload types for feature 028. They differ from the DigiKey ones
# above in the way that shapes the whole feature: DigiKey's come from a service
# that can be asked again, and these come from a page that was read once and
# cannot be re-read. What the review displayed is what gets written (FR-006).

# The payload shape the agent posts. Anything else is not read, which is what
# makes a stale cached agent harmless rather than a 500.
MCMASTER_PAYLOAD_VERSION = 1

# The vendor the agent must declare for a payload to be treated as a McMaster
# order. Must equal catalog_service.MCMASTER_VENDOR.
MCMASTER_PAYLOAD_VENDOR = 'McMaster-Carr'


def _order_string(value: Any) -> str:
    """A trimmed string, or '' for anything unusable as one.

    Numbers are refused. Every string field on an agent payload is text read out
    of a page, so a number arriving in one means the agent sent something
    unexpected, and '' is the honest answer.

    Shared by every page-read vendor since feature 029 -- these were named for
    McMaster only because it was the first.
    """
    if isinstance(value, str):
        return value.strip()
    return ''


def _order_int(value: Any) -> Optional[int]:
    """A positive int, or None. A bool is not an int here.

    Counts only -- packs and pack sizes. Zero and negatives become None rather
    than being carried: a pack of zero is not a fact about the order, it is a
    misread, and it would divide by zero downstream.
    """
    if isinstance(value, bool):
        return None
    parsed = None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except (TypeError, ValueError):
            return None
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _order_decimal(value: Any) -> Optional[Decimal]:
    """A Decimal, or None -- and never by way of a float (Constitution III).

    **Prices cross this boundary as strings, always.** JSON's only number type
    is an IEEE double, so a price sent as a JSON number is already a float
    before any of this runs. A float here means the agent sent one, and dropping
    it is better than recording an inexact price: by that point the damage is
    done and Decimal(6.9000000000000004) is worse than a blank the operator can
    fill in.

    Negatives are refused for the same reason zero packs are: a price below zero
    is a misread, not a credit this feature knows how to record.
    """
    if isinstance(value, bool):
        return None
    parsed = None
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, int):
        parsed = Decimal(value)
    elif isinstance(value, str):
        try:
            parsed = Decimal(value.strip())
        except (InvalidOperation, ValueError):
            return None
    elif isinstance(value, float):
        logger.warning(
            "A price arrived as a float, which means it was sent as a "
            "JSON number rather than a string. Dropping it rather than "
            "recording an inexact price."
        )
        return None
    if parsed is None or parsed < 0 or not parsed.is_finite():
        return None
    return parsed


# "November 16, 2025" for an order from a previous year; "July 21", with no year
# at all, for one placed this year. Both are what McMaster renders
# (research.md §5), and a reader that handles only the first loses the date on
# every recent order -- which is the majority of the ones anybody re-captures.
_ORDER_DATE_FORMATS = ('%B %d, %Y', '%b %d, %Y', '%Y-%m-%d')
_ORDER_DATE_FORMATS_NO_YEAR = ('%B %d', '%b %d')


def _order_datetime(value: Any, today: Optional[datetime] = None) -> Optional[datetime]:
    """An order date off a vendor's page, or None.

    Lenient by design: an unparseable date is the same as an absent one, and an
    absent one is ordinary (contracts/capture-payload.md §3). Nothing about a
    capture depends on it.

    A date with no year is taken as the current year, because that is precisely
    when McMaster omits it.
    """
    text = _order_string(value)
    if not text:
        return None

    for fmt in _ORDER_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # ISO 8601 with a time on it, should the agent ever send one. Naive on the
    # way out, for the reason :func:`_naive` gives -- this branch is the same
    # latent crash DigiKey's parser actually hit, and it is closed here rather
    # than left for whichever agent change first sends an offset.
    try:
        return _naive(datetime.fromisoformat(text.replace('Z', '+00:00')))
    except ValueError:
        pass

    # The year is appended to the *text* rather than being patched onto a parsed
    # date with .replace(year=...). Parsing a bare day-and-month is deprecated
    # from 3.13 and changes behaviour in 3.15, and it mishandles 29 February --
    # which strptime accepts against its default year 1900, a non-leap year,
    # only to raise. Giving it a real year sidesteps both.
    year = (today or datetime.now()).year
    for fmt in _ORDER_DATE_FORMATS_NO_YEAR:
        try:
            return datetime.strptime(f'{text}, {year}', f'{fmt}, %Y')
        except ValueError:
            continue

    return None


@dataclass(frozen=True)
class McMasterOrderLine:
    """One line of a McMaster order, as the agent read it off the page.

    **Packs, not units.** McMaster states a quantity ("2"), a pack ("Packs of
    100") and a price per pack ("11.51"). What this catalog records is units and
    a unit price, because what gets consumed -- and what a low-stock flag has to
    mean -- is individual screws. The conversion is :attr:`quantity` and
    :attr:`unit_price`, both shown on the review and both editable there
    (FR-020, FR-020a).

    ``pack_size`` of None means the page stated no pack, so one unit is one
    unit. That covers "Each" and it also covers **"Pairs"** -- a unit that is
    plainly not one item but for which McMaster states no count anywhere, so
    none can be derived. Recording a silent 2 there would be inventing data;
    FR-037 says show it as unread and let the operator decide.
    """
    part_number: str = ''
    description: str = ''
    # Only where the page actually stated one. McMaster sells to its own
    # specification and names no manufacturer on the great majority of its
    # goods, so '' is the ordinary value and not a missed selector -- which is
    # exactly why FR-012 writes an MPN identifier only when this is set.
    # Inventing one would collide with a real MPN later, and identifiers are
    # unique.
    manufacturer_part_number: str = ''
    packs: Optional[int] = None
    pack_size: Optional[int] = None
    pack_price: Optional[Decimal] = None
    line_number: Optional[int] = None

    @property
    def units_per_pack(self) -> int:
        """How many units one pack holds. 1 when the page stated no pack."""
        return self.pack_size or 1

    @property
    def quantity(self) -> Optional[int]:
        """The quantity to record, in units rather than packs (FR-020).

        None when the page stated no quantity -- blank and editable on the
        review, not a guessed 1.
        """
        if self.packs is None:
            return None
        return self.packs * self.units_per_pack

    @property
    def exact_unit_price(self) -> Optional[Decimal]:
        """The unit price before it is rounded to the cent.

        Kept apart from :attr:`unit_price` so :attr:`price_rounds` has something
        to compare against. Nothing stores this.
        """
        if self.pack_price is None:
            return None
        return self.pack_price / self.units_per_pack

    @property
    def unit_price(self) -> Optional[Decimal]:
        """What will actually be stored: the pack price divided, then rounded.

        ``price_to_cents`` is the existing ROUND_HALF_UP quantizer, and using it
        here means the stored value is one this code chose rather than one
        MariaDB's Numeric(10, 2) imposed silently.
        """
        return price_to_cents(self.exact_unit_price)

    @property
    def price_rounds(self) -> bool:
        """Whether dividing the pack price loses precision to the cent.

        Said on the review, for the reason feature 017 already says it: 6.66
        across a pack of 100 is 0.0666 a unit and gets stored as 0.07, and the
        operator should learn that now rather than during a reconciliation
        months later.
        """
        exact = self.exact_unit_price
        return exact is not None and price_to_cents(exact) != exact

    @property
    def form_key(self) -> str:
        """What names this line in a form, and what a decision is keyed by.

        The line number McMaster itself displays, because **a part number does
        not identify a line**: an order can carry the same part twice. Keying
        the form by part number gave two such lines one shared ``include[]`` and
        ``description[]``, so neither could be controlled on its own (024,
        PR #116 review). The same trap is reachable here and the same answer
        closes it.

        Falls back to the part number when the page stated no line number, which
        is correct for every order that does not repeat a part.
        """
        if self.line_number is not None:
            return str(self.line_number)
        return self.part_number

    @property
    def is_readable(self) -> bool:
        """Whether there is anything here for the operator to decide about.

        A line with neither a part number nor a description is dropped. A line
        with either one is kept: a part number alone is capturable, and a
        description alone is capturable or excludable (FR-019).
        """
        return bool(self.part_number or self.description)

    @property
    def missing_fields(self) -> tuple:
        """Which fields came back empty, for FR-037.

        A blank price on one line of fifteen is not something the operator
        notices unaided, so the review marks it rather than leaving them to
        spot it.
        """
        missing = []
        if not self.part_number:
            missing.append('part_number')
        if not self.description:
            missing.append('description')
        if self.packs is None:
            missing.append('quantity')
        if self.pack_price is None:
            missing.append('price')
        return tuple(missing)

    @classmethod
    def from_payload(cls, data: Any) -> Optional['McMasterOrderLine']:
        """Build from one element of the payload's ``lines``.

        Returns None only for something that is not an object, or a line
        carrying neither a part number nor a description -- there is nothing to
        decide about that one.

        **Never raises on a JSON value.** A field McMaster stops emitting, or a
        selector that stops matching, costs that field alone (FR-036). Every
        extraction below is independent.
        """
        if not isinstance(data, dict):
            return None

        line = cls(
            part_number=_order_string(data.get('part_number')),
            description=_order_string(data.get('description')),
            manufacturer_part_number=_order_string(
                data.get('manufacturer_part_number')),
            packs=_order_int(data.get('packs')),
            pack_size=_order_int(data.get('pack_size')),
            pack_price=_order_decimal(data.get('pack_price')),
            line_number=_order_int(data.get('line_number')),
        )
        return line if line.is_readable else None


@dataclass(frozen=True)
class McMasterOrder:
    """One McMaster order, as the agent read it off the order-history page.

    **There is no order number.** McMaster shows only the customer's *Purchase
    Order* string, which is what ``order_number`` holds -- editable in place on
    their page, and auto-generated as MMDD+SURNAME when the customer gives none
    (research.md §5). ``order_id`` is the stable, opaque id out of the order's
    URL; it is never displayed and exists only so a re-capture still recognizes
    an order whose Purchase Order string has been renamed (research.md §14).

    Deliberately absent: the delivery name and address, the confirmation email
    and the card. They are on the page and are not read, rather than being read
    and discarded.
    """
    order_number: str
    order_id: str = ''
    order_date: Optional[datetime] = None
    source_url: str = ''
    lines: tuple = ()
    lines_read: int = 0

    @property
    def lines_offered(self) -> int:
        """How many lines the operator is being shown."""
        return len(self.lines)

    @property
    def is_incomplete(self) -> bool:
        """Whether the agent saw more lines than it could use (FR-004).

        Equal counts say nothing; different ones are the difference between
        "your order has three lines" and "I could only read three of your
        fifteen", and those must not look the same.
        """
        return self.lines_read > self.lines_offered

    @classmethod
    def from_payload(cls, data: Any) -> Optional['McMasterOrder']:
        """Build from the hidden ``order`` form field's JSON.

        Returns None -- not an error -- for a payload this code cannot read:

        * not an object;
        * a ``version`` it does not recognize;
        * a ``vendor`` that is not McMaster's;
        * a body naming no order number.

        That is 007 FR-007 and it is what makes a stale cached agent harmless.
        Each of these renders today's ordinary confirmation form rather than a
        500, except the last, which FR-038 renders as "this page yielded no
        order" with a way to enter it by hand.

        An empty ``lines`` with a valid order number is **not** None: it is a
        real order whose lines could not be read, and it must not look like an
        order with no lines.
        """
        if not isinstance(data, dict):
            return None

        if data.get('version') != MCMASTER_PAYLOAD_VERSION:
            logger.info(
                "Ignoring a capture payload with version %r; this server reads "
                "version %s", data.get('version'), MCMASTER_PAYLOAD_VERSION
            )
            return None

        if _order_string(data.get('vendor')) != MCMASTER_PAYLOAD_VENDOR:
            return None

        order_number = _order_string(data.get('order_number'))
        if not order_number:
            return None

        raw_lines = data.get('lines')
        if not isinstance(raw_lines, list):
            raw_lines = []

        lines = tuple(
            line for line in (
                McMasterOrderLine.from_payload(entry) for entry in raw_lines
            )
            if line is not None
        )

        # What the agent *saw*, including line elements it could not use. Only
        # falls back to what survived when the agent said nothing -- taking
        # len(lines) as the count would erase exactly the discrepancy FR-004
        # exists to report. A count below what survived is a malformed claim and
        # is corrected upward for the same reason.
        lines_read = _order_int(data.get('lines_read'))
        if lines_read is None or lines_read < len(lines):
            lines_read = len(lines)

        return cls(
            order_number=order_number,
            order_id=_order_string(data.get('order_id')),
            order_date=_order_datetime(data.get('order_date')),
            source_url=_order_string(data.get('source_url')),
            lines=lines,
            lines_read=lines_read,
        )


# -- Amazon order capture (feature 029) --------------------------------------

AMAZON_PAYLOAD_VERSION = 1

# The vendor the agent must declare for a payload to be treated as an Amazon
# order. Must equal catalog_service.AMAZON_VENDOR.
AMAZON_PAYLOAD_VENDOR = 'Amazon'


@dataclass(frozen=True)
class AmazonOrderLine:
    """One line of an Amazon order, as the agent read it off the order page.

    Modelled on :class:`McMasterOrderLine` rather than on DigiKey's, because both
    are read off a page rather than fetched from a service and share the
    consequences: the read cannot be repeated, and every field is individually
    fallible.

    **No pack arithmetic.** McMaster states a quantity, a pack and a price per
    pack, and this catalog records units. Amazon's order page states a unit price
    and a quantity directly (029 research.md §5), so there is nothing to compute
    and no rounding to warn about. The spec assumed otherwise and was wrong; the
    live-site read settled it.

    ``asin`` may be '' -- FR-019 makes a line capturable on its title alone. That
    happens when the row's item links are missing, which is a per-field failure
    like any other and must not refuse the order.
    """
    asin: str = ''
    title: str = ''
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    line_number: Optional[int] = None

    # Amazon states no manufacturer part number on an order page. Present, and
    # always '', so the shared review can ask every line the same questions --
    # a line that names no MPN can never contradict a product's, which is what
    # `_review_order_line` checks.
    manufacturer_part_number: str = ''

    @property
    def form_key(self) -> str:
        """What names this line in a form, and what a decision is keyed by.

        The row's position, because **Amazon numbers nothing** -- no line number
        anywhere on the page (029 research.md §7). Falls back to the ASIN when
        even that is missing, which is the same fallback both other vendors use.

        An ASIN does not identify a line: an order can carry the same item on two
        lines, and keying by it gave them one shared set of controls so neither
        could be steered on its own. PR #116 review.
        """
        if self.line_number is not None:
            return str(self.line_number)
        return self.asin

    @property
    def description(self) -> str:
        """Amazon's own words for this line.

        Named ``description`` so the shared capture flow can read it the same way
        it reads the other two vendors'. ``title`` is what the agent calls it,
        because that is what the page calls it.
        """
        return self.title

    @property
    def missing_fields(self) -> tuple:
        """Which fields came back empty.

        A blank price on one line of eleven is not something the operator
        notices unaided, so the review marks it rather than leaving them to spot
        it (FR-022).

        **A quantity is never missing.** Amazon renders an empty quantity
        component for a quantity of one, so "no digits" is a value rather than a
        failure -- see :meth:`AmazonOrder.from_payload`.
        """
        missing = []
        if not self.asin:
            missing.append('part_number')
        if not self.title:
            missing.append('description')
        if self.unit_price is None:
            missing.append('price')
        return tuple(missing)

    @classmethod
    def from_payload(cls, data: Any, index: int) -> Optional['AmazonOrderLine']:
        """Build from one element of the payload's ``lines``.

        Returns None only for something that is not an object, or for a row that
        yielded **neither** an ASIN nor a title -- which is not a line, it is a
        row the reader could not make anything of. Everything else is offered,
        however thin, because the operator can see it and decide.

        **Never raises on a JSON value.** A field the agent stops sending costs
        that field and nothing else.
        """
        if not isinstance(data, dict):
            return None

        asin = _order_string(data.get('asin'))
        title = _order_string(data.get('title'))
        if not asin and not title:
            return None

        # An absent or unreadable quantity is 1, not None: Amazon renders the
        # quantity component empty when the quantity is one, so an empty read is
        # the ordinary case rather than a failure (029 research.md §6).
        quantity = _order_int(data.get('quantity')) or 1

        return cls(
            asin=asin,
            title=title,
            quantity=quantity,
            unit_price=_order_decimal(data.get('unit_price')),
            # 1-based, and supplied here rather than trusted from the payload
            # when the agent omits it -- position is the only line identity
            # Amazon offers and it must not be left blank.
            line_number=_order_int(data.get('line_number')) or (index + 1),
        )


@dataclass(frozen=True)
class AmazonOrder:
    """One Amazon order, as the agent read it off its order-details page.

    ``order_number`` is Amazon's own, in their 3-7-7 digit form, and it is
    stable and printed on the page -- so unlike McMaster there is no opaque id to
    carry alongside it and ``purchases.vendor_order_id`` stays NULL for Amazon.

    Deliberately absent: the shipping address, the buyer, the payment method and
    the order total. They are on the page and are **not read**, rather than being
    read and discarded (029 research.md §8).
    """
    order_number: str
    order_date: Optional[datetime] = None
    source_url: str = ''
    lines: tuple = ()
    lines_read: int = 0

    @property
    def lines_offered(self) -> int:
        """How many lines the operator is being shown."""
        return len(self.lines)

    @property
    def is_incomplete(self) -> bool:
        """Whether the agent saw more rows than it could use (FR-004).

        Equal counts say nothing; different ones are the difference between "your
        order has three lines" and "I could only read three of your eleven", and
        those must not look the same.
        """
        return self.lines_read > self.lines_offered

    @classmethod
    def from_payload(cls, data: Any) -> Optional['AmazonOrder']:
        """Build from the hidden ``order`` form field's JSON.

        Returns None -- not an error -- for a payload this code cannot read: not
        an object, an unrecognized ``version``, a ``vendor`` that is not
        Amazon's, or a body naming no order number. That is what makes a stale
        cached agent harmless rather than a 500.

        **An empty ``lines`` with a valid order number is not None**: it is a real
        order whose lines could not be read, and FR-023 requires that not look
        like an order with nothing in it.
        """
        if not isinstance(data, dict):
            return None

        if data.get('version') != AMAZON_PAYLOAD_VERSION:
            logger.info(
                "Ignoring a capture payload with version %r; this server reads "
                "version %s", data.get('version'), AMAZON_PAYLOAD_VERSION
            )
            return None

        if _order_string(data.get('vendor')) != AMAZON_PAYLOAD_VENDOR:
            return None

        order_number = _order_string(data.get('order_number'))
        if not order_number:
            return None

        raw_lines = data.get('lines')
        if not isinstance(raw_lines, list):
            raw_lines = []

        lines = tuple(
            line for line in (
                AmazonOrderLine.from_payload(entry, index)
                for index, entry in enumerate(raw_lines)
            )
            if line is not None
        )

        # What the agent *saw*, including rows it could not use. Only falls back
        # to what survived when the agent said nothing -- taking len(lines) as
        # the count would erase exactly the discrepancy FR-004 exists to report.
        # A count below what survived is a malformed claim and is corrected
        # upward for the same reason.
        lines_read = _order_int(data.get('lines_read'))
        if lines_read is None or lines_read < len(lines):
            lines_read = len(lines)

        return cls(
            order_number=order_number,
            order_date=_order_datetime(data.get('order_date')),
            source_url=_order_string(data.get('source_url')),
            lines=lines,
            lines_read=lines_read,
        )


class OrderLineState(Enum):
    """What a review concluded about one line of a DigiKey order.

    Exclusive and exhaustive, and tested in this order -- CAPTURED first,
    because a line already recorded is not a line to decide anything about.
    """
    CAPTURED = "CAPTURED"    # A purchase already exists for this order and part
    CONFLICT = "CONFLICT"    # The DigiKey part number names a product whose MPN contradicts this line
    MATCHED = "MATCHED"      # A product carries this MPN or DigiKey part number, corroborated
    NEW = "NEW"              # Nothing in the catalog matches


@dataclass(frozen=True)
class CandidatePurchase:
    """A purchase that could be the same physical purchase as an order line.

    Feature 033. Same vendor, same vendor item id, **no supplier order number**,
    and an order date close enough to the order's to be the same event. It is
    offered to the operator on the review, and it is only ever adopted because
    they said so -- nothing here is claimed on the catalog's own judgement.

    Display-only, and a plain value object rather than an ORM row for the reason
    :class:`CaptureAssessment` already documents: a relationship that was not
    eagerly loaded does not survive its session closing, and a thing a template
    renders has no business carrying that hazard.
    """
    # Both required: ``purchases.product_id`` is NOT NULL, so a candidate that
    # could not name its product would be a row that cannot exist. Typing it
    # optional would make every template treat a value that is always there as
    # though it might not be.
    purchase_id: int
    product_id: int
    order_date: Optional[datetime] = None
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    product_description: Optional[str] = None
    # Rendered as a plain statement on the review: adopting a received purchase
    # does not un-receive it, and does not re-run any of receiving's side
    # effects (033 FR-014).
    is_received: bool = False


@dataclass(frozen=True)
class ReviewedLine:
    """One line of an order, with what the catalog knows about it.

    Display-only, and a plain value object rather than an ORM row for the reason
    :class:`CaptureAssessment` already documents: a relationship that was not
    eagerly loaded does not survive its session closing, and a thing a template
    renders has no business carrying that hazard.

    ``part`` being None is an ordinary state, not an error. It means DigiKey
    would not answer for this part, and the line is still capturable on
    everything the order gave (FR-041).
    """
    line: 'DigiKeyOrderLine'
    state: 'OrderLineState'
    part: Optional['DigiKeyPart'] = None
    suggested_description: str = ''
    product_id: Optional[int] = None
    product_description: Optional[str] = None
    product_manufacturer_part_number: Optional[str] = None
    purchase_id: Optional[int] = None
    recorded_quantity: Optional[int] = None
    recorded_unit_price: Optional[Decimal] = None
    # A purchase that may already record this line, recorded by a path that knew
    # nothing about this order -- a single-listing capture, or one entered by
    # hand (033 FR-001). None is the ordinary state.
    candidate: Optional['CandidatePurchase'] = None

    @property
    def has_candidate(self) -> bool:
        """Whether a purchase might already record this line (033 FR-007)"""
        return self.candidate is not None

    @property
    def needs_same_purchase_answer(self) -> bool:
        """Whether the operator must say if the candidate is the same purchase.

        **Never on a CAPTURED line.** A line paired exactly by order number and
        line number is not a line to decide anything else about, and
        ``_assign_candidates`` never offers one a candidate -- this is the
        second statement of that rule, so a template cannot render a question
        the service would not read.
        """
        return self.has_candidate and self.state is not OrderLineState.CAPTURED

    @property
    def is_enriched(self) -> bool:
        """Whether DigiKey's part detail was available for this line"""
        return self.part is not None

    @property
    def price_rounds(self) -> bool:
        """Whether recording this line's price loses precision to the cent.

        Shown on the review for the same reason feature 017 shows it for a pack
        price that does not divide evenly: the operator should learn that the
        stored number differs from the quoted one now, not during a
        reconciliation months later.
        """
        price = self.line.unit_price
        return price is not None and price_to_cents(price) != price

    @property
    def unit_price_as_recorded(self) -> Optional[Decimal]:
        """What will actually be stored for this line."""
        return price_to_cents(self.line.unit_price)

    @property
    def has_change(self) -> bool:
        """Whether the quantity or price differs from what is already recorded.

        Two ways a line can already be recorded, and both ask this question:
        paired exactly to a purchase of this order (**024 FR-014** -- show a
        changed quantity or price against what is recorded, and apply it only if
        the operator confirms), or carrying a candidate a listing capture wrote
        (**033 FR-009**, which reuses that same mechanism rather than inventing a
        second one). The tick that offers to apply the order's values renders on
        this, so a candidate that is silent here is a change the operator is
        never offered.

        Both feature numbers are spelled out because the bare "FR-014" this
        carried before now sits beside 033's requirements, whose FR-014 is about
        something else entirely -- preserving a received purchase's receipt.
        """
        if self.state is OrderLineState.CAPTURED:
            recorded_quantity = self.recorded_quantity
            recorded_unit_price = self.recorded_unit_price
        elif self.candidate is not None:
            recorded_quantity = self.candidate.quantity
            recorded_unit_price = self.candidate.unit_price
        else:
            return False
        # **A value the vendor did not give is not a change.** None means the
        # field was not read -- a selector that stopped matching, or an order
        # response that omitted it -- and it says nothing about whether the line
        # differs from what is recorded. Comparing it anyway reported a change on
        # every degraded line, offered an "Update it?" whose write is then
        # skipped as a no-op, and rendered the reason as "the page now says 1 at
        # None". PR #123 review.
        #
        # Both sides rounded, because the recorded one has been through a
        # Numeric(10, 2) column and the line's has not. Comparing the raw
        # 0.0126 against the stored 0.01 made "Update it?" reappear on every
        # single review of a sub-cent line, with no way to clear it -- applying
        # the change just rewrote a value that rounded identically. PR #116
        # review.
        quantity_changed = (
            self.line.quantity is not None
            and recorded_quantity != self.line.quantity
        )
        price_changed = (
            self.line.unit_price is not None
            and price_to_cents(recorded_unit_price)
            != price_to_cents(self.line.unit_price)
        )
        return quantity_changed or price_changed


@dataclass(frozen=True)
class OrderCaptureReview:
    """A whole order, reviewed against the catalog, with nothing written yet.

    ``orphaned`` is the other direction of FR-013: purchases recorded against
    this sales order whose part the fetched order no longer contains. They are
    **reported and never deleted** -- a purchase the operator can see and cancel
    is better than one that vanishes.
    """
    order: 'DigiKeyOrder'
    lines: tuple = ()
    orphaned: tuple = ()

    @property
    def capturable(self) -> tuple:
        """The lines a confirmation could act on -- everything not already captured"""
        return tuple(
            line for line in self.lines
            if line.state is not OrderLineState.CAPTURED
        )

    @property
    def unenriched(self) -> tuple:
        """The lines DigiKey would not give part detail for (FR-041)"""
        return tuple(line for line in self.lines if not line.is_enriched)


@dataclass(frozen=True)
class CapturedOrder:
    """One captured order, as the orders list shows it (029 FR-033).

    Derived from the purchases carrying its number, never stored -- the same
    invariant an individual order screen rests on. There is no orders table and
    this feature does not add one: an order *is* its purchases, and a table would
    be a second place for the truth to live and a way for the two to disagree.
    """
    vendor: str
    order_number: str
    order_date: Optional[datetime] = None
    line_count: int = 0
    outstanding_count: int = 0

    @property
    def is_complete(self) -> bool:
        """Whether everything on this order has been received.

        Shown so a finished order is distinguishable at a glance from one still
        arriving, which is the whole point of the list.
        """
        return self.outstanding_count == 0


@dataclass(frozen=True)
class OrderCaptureResult:
    """What one confirmed order capture did, whoever the vendor was.

    Counts rather than objects, plus the purchase ids, because the route needs
    to say what happened and then redirect -- not to render the rows it just
    wrote. The order screen reads them back from the database, which is also the
    proof they landed.

    **This was two types until feature 029.** DigiKey's named the lines its part
    lookup would not answer for; McMaster's named the lines the *page* did not
    give up. Those are the same fact -- "these lines came back thin, and they are
    named rather than counted so the operator knows which records to look over"
    -- wearing two names, so they are now one field.

    ``orphaned`` and ``renamed_from`` default to empty for vendors that cannot
    produce them: only McMaster has an order identifier the operator can rename
    on the vendor's side, and only a re-capture reports orphans.
    """
    purchase_ids: tuple = ()
    products_created: int = 0
    products_attached: int = 0
    lines_excluded: int = 0
    lines_already_captured: int = 0
    lines_updated: int = 0
    # Lines recorded as having already arrived, rather than as outstanding.
    # Backfilling a historical order (031 FR-024); zero for an ordinary capture.
    lines_arrived: int = 0
    # The captured lines that came back thin -- whatever "thin" means for this
    # vendor. Named rather than counted.
    lines_incomplete: tuple = ()
    # Purchases recorded against this order that no line of it claims.
    # Reported, never deleted.
    orphaned: tuple = ()
    # The purchases this capture *claimed* rather than created: rows a
    # single-listing capture or a hand entry had already written, which the
    # operator said were the same physical purchase as one of these lines
    # (033 FR-011). Ids rather than a count, because the orphan check needs
    # them -- a claimed row carries this order's number by the time that query
    # runs, and nothing else can tell it apart from a stale one.
    purchases_adopted: tuple = ()
    # The order reference this order was filed under before, when the operator
    # renamed it on the vendor's side and this capture refiled the rows. '' when
    # nothing moved. McMaster only -- see OrderVendor.adopts_renames.
    renamed_from: str = ''

    @property
    def lines_unenriched(self) -> tuple:
        """What DigiKey's half of this used to be called.

        Kept because ``tests/unit/test_digikey_capture.py`` reads it, and that
        suite is feature 029's regression gate: it says what capture *does*, and
        it is not edited to accommodate the refactor. A field rename is not a
        behaviour change, and this is what makes it not become one.
        """
        return self.lines_incomplete

    @property
    def wrote_anything(self) -> bool:
        """Whether this capture changed the database at all.

        The flash leads on this rather than on the purchase count, because a
        capture that only applied a quantity change writes no purchase and
        would otherwise be reported as "nothing new" over the top of a write
        that landed.
        """
        return (
            bool(self.purchase_ids)
            or bool(self.purchases_adopted)
            or self.lines_updated > 0
            or bool(self.renamed_from)
        )


# The names the two flows used before feature 029 merged them. Kept as aliases
# rather than renamed at every call site, because `tests/unit/test_mcmaster_
# routes.py` constructs McMasterCaptureResult by name and that suite is the
# regression gate for this refactor.
DigiKeyCaptureResult = OrderCaptureResult
McMasterCaptureResult = OrderCaptureResult


@dataclass(frozen=True)
class PurchaseDeletion:
    """What one deleted purchase was, reported back after it is gone.

    The route needs to say what it removed (032 FR-008) and to decide where to
    send the operator afterwards, and by then the row does not exist. Reading it
    in the route beforehand would be a second session and a race; handing back
    the deleted ORM instance would be worse, because touching an unloaded
    attribute on a deleted object is undefined. So the service reads what is
    needed inside the transaction and returns this.

    ``supplier_order_reference`` is what decides whether "back to the order" has
    anywhere to go. A hand-recorded or listing-captured purchase carries none,
    and there is no order to return to -- which is a fallback, not an error.
    """
    purchase_id: int
    product_id: int
    vendor: str
    order_date: Optional[datetime] = None
    quantity: Optional[int] = None
    # Decimal, never float (Constitution III). Rendered and echoed, never
    # arithmetic'd -- this feature deliberately does no sums.
    unit_price: Optional[Decimal] = None
    supplier_order_reference: Optional[str] = None
    attachments_deleted: int = 0
