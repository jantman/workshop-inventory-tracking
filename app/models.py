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
    'create' or 'search'; every well-formed scan gets one of the three, so no
    scan dead-ends (FR-018, SC-008).

    ``product`` is typed loosely because app/models.py must not import
    app/database.py -- the ORM depends on this module, not the other way round.
    """
    outcome: str
    classification: 'ScanClassification'
    product: Optional[Any] = None            # Set iff outcome == 'product'
    prefill: Dict[str, str] = field(default_factory=dict)  # For outcome == 'create'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            'outcome': self.outcome,
            'classification': self.classification.to_dict(),
            'product': self.product.to_dict() if self.product is not None else None,
            'prefill': dict(self.prefill),
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
