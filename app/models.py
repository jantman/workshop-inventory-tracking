"""
Data models for Workshop Material Inventory Tracking

These models define the structure and validation rules for inventory items,
including support for different materials, shapes, and threading specifications.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Union
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from datetime import datetime, timedelta
from enum import Enum
from types import MappingProxyType
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


class IdentifierType(Enum):
    """
    Closed set of product identifier types (Story 2.1, FR7). Stored as the
    string value (== the member name) in a plain String column, NOT a DB ENUM,
    so later stories can extend the set without a migration.
    """
    GTIN = "GTIN"
    # Quarantine namespace (Story 2.2, FR10, AD-7): a value that fails GTIN
    # check-digit validation may be retained here. It is GLOBAL (see
    # VENDOR_SCOPED_IDENTIFIER_TYPES below) and stored exactly as entered —
    # never normalized — so it shares no key space with GTIN and can never
    # block a later valid GTIN.
    GTIN_UNVALIDATED = "GTIN_UNVALIDATED"
    ASIN = "ASIN"
    FNSKU = "FNSKU"
    MPN = "MPN"
    VENDOR_SKU = "VENDOR_SKU"
    INTERNAL = "INTERNAL"


class ScanKind(Enum):
    """
    The four structural kinds a captured scan can be classified as (Story 4.2,
    FR36). Exhaustive and ordered: `app/utils/scan_router.py` tries them in the
    order below and `FREE_TEXT` always matches, so every scan gets exactly one
    kind and no scan dead-ends.

    Unlike `IdentifierType` above, these values are lowercase and are NEVER
    persisted. A `ScanKind` is a wire value: Story 4.5's JSON response and Epic
    7's capture path serialize it beside the existing lowercase
    `outcome: 'unrouted'` (`app/main/routes.py`), and AD-15 spells the four
    kinds lowercase.

    Members:
        INTERNAL: A label this system printed — a GS1 element string under the
            configured AI + token grammar, recognized by `app/utils/gs1.py`.
        ECIA: An ISO/IEC 15434 format-06 distributor envelope (DigiKey,
            Mouser) whose records `app/utils/ecia.py` could read at least one
            recognized data identifier out of; they arrive on `ecia_fields`. An
            envelope with a valid header but nothing readable inside it is
            deliberately NOT this kind — it degrades to `FREE_TEXT` carrying
            the raw scan (AD-5, NFR8), because this kind exists so a consumer
            can pre-fill a form from named fields.
        GTIN: A bare manufacturer trade-item number in any of the four accepted
            forms, validated and normalized by `app/utils/gtin.py`.
        FREE_TEXT: Anything else. The fallthrough, never an error.
    """
    INTERNAL = "internal"
    ECIA = "ecia"
    GTIN = "gtin"
    FREE_TEXT = "free_text"


# Scoping authority (AD-9): these types are vendor-scoped for uniqueness;
# every other IdentifierType is global (vendor_scope == '').
VENDOR_SCOPED_IDENTIFIER_TYPES = frozenset({
    IdentifierType.VENDOR_SKU,
    IdentifierType.ASIN,
    IdentifierType.FNSKU,
})


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


# The two scan kinds that name a canonical form and therefore must carry one
# (Story 4.2, AD-15). `ECIA` and `FREE_TEXT` normalize to nothing: an
# envelope's content lives in `ecia_fields` and free text is searched as it
# arrived, via `raw`.
_KINDS_CARRYING_A_NORMALIZED_VALUE = frozenset({ScanKind.INTERNAL, ScanKind.GTIN})


@dataclass(frozen=True)
class ScanClassification:
    """
    The structural verdict on one captured scan (Story 4.2, FR36, AD-15).

    Produced by `app/utils/scan_router.classify()` and by nothing else. This is
    the frozen contract every scan consumer depends on — Story 4.3's
    `resolve_scan`, Story 4.5's UI routing, Epic 7's order-time capture and
    Epic 9's scan-result view — so it is deliberately small, has no behavior,
    and carries no reference to a Product, a session, or a request.

    Frozen so a classification can be passed around without defensive copying:
    a consumer that needs a different verdict must classify again, not mutate
    this one. All four fields are required and none has a default, so no call
    site can construct a half-populated classification and every construction
    states the kind's contract explicitly.

    `frozen=True` alone would be a shallow promise, and `ecia_fields` is the
    one field that will ever hold a mutable object: `dataclass` blocks
    rebinding the attribute but not `c.ecia_fields['P'] = ...` through it, so
    the parser's dict would be shared and writable by every consumer while the
    docstring claimed otherwise. `__post_init__` therefore
    copies any mapping and wraps the copy in a `MappingProxyType` — a
    read-only view — so the no-defensive-copying promise is true for all four
    fields rather than three. The copy is unconditional, including when the
    caller already passed a proxy: a proxy is a *view*, so accepting one
    as-is would leave the dict behind it a live write channel into a
    supposedly frozen classification.

    Two consequences of holding a mapping, both of which are now reachable from
    anything `classify()` returns for an envelope, and both pinned by tests:

    1. A classification carrying `ecia_fields` is NOT hashable (a mapping is
       not), so do not put one in a set or use it as a dict key.
       Classifications with `ecia_fields=None` hash normally.
    2. `dataclasses.asdict()` and `copy.deepcopy()` both raise `TypeError:
       cannot pickle 'mappingproxy' object` on one. That matters because
       `asdict` is the obvious route from this frozen dataclass to the JSON
       Story 4.5 serializes: a serializer must build its payload field by
       field, converting `ecia_fields` with `dict(...)` itself.

    Beyond freezing, `__post_init__` enforces every structural invariant this
    docstring asserts of the CLASS, and that set is closed: each field's own
    type, plus the two cross-field rules that tie `normalized_value` and
    `ecia_fields` to `kind`. Statements below about what a given `kind` carries
    in practice are properties of `classify()`, the sole producer, and are
    labelled as such where they appear — `ecia_fields` has one. Requiring all four fields stops a call site building a
    half-populated classification; these stop it building a self-contradictory
    one — a `GTIN` with nothing to look up, an `ECIA` carrying a normalized
    value it says it does not have — which is the failure mode Stories
    4.3/4.5/7/9 would actually hit. Partial enforcement would be the worst of
    the three options: it reads as "validated" at the call site while leaving
    the highest-consequence hole open.

    Attributes:
        kind: Which FR36 rule matched. Always set. There are more rules than
            there are kinds since DW-70 — rule 3 reads a manufacturer's AI-01
            element string and hands its digits to the GTIN rule, so it
            produces no kind of its own and an AI-01 scan is a `GTIN`
            classification indistinguishable from a bare one except by `raw`.
        normalized_value: The canonical form of what was scanned, in the shape
            the matching kind defines:

            - `INTERNAL`: the token-stripped internal id — exactly the string
              `gs1.decode()` returns as `InternalPayload.internal_id`, which is
              exactly what Story 2.4 stored in `product_identifiers`. A
              resolver must not strip it again.
            - `GTIN`: the canonical 14-digit, left-zero-padded key from
              `gtin.normalize_gtin()`. Lookup is against that namespace, so all
              four GTIN forms of one product resolve to one row.
            - `ECIA` and `FREE_TEXT`: `None`. There is nothing to normalize —
              an ECIA envelope's content lives in `ecia_fields` and free text
              is searched as it arrived, via `raw`.
        ecia_fields: The MH10.8.2 data identifiers parsed out of an ECIA
            envelope, keyed exactly `P`, `1P`, `Q`, `K`, `1K`, `9D`, `10D` —
            a subset of those seven, since a label carries only the ones it
            prints. `classify()` populates it by delegating to
            `app/utils/ecia.py`, and every value is the string as scanned: no
            date parsing, no quantity coercion, no trimming (Epic 7 and Story
            4.5 interpret, this shape only carries). Because the classifier is
            the only producer and it degrades a readable-header/unreadable-body
            envelope to `FREE_TEXT`, every `ECIA` classification IN PRACTICE
            carries a non-empty mapping. That is a property of `classify()`,
            NOT an invariant of this class and not one `__post_init__` checks:
            constructed directly, `ECIA` with `{}` and `ECIA` with `None` are
            both accepted. So a consumer reading it defensively
            (`classification.ecia_fields or {}`, which covers both) is reading
            the contract, not distrusting the classifier. It is `None` for
            every non-`ECIA` kind, permanently.
        raw: The scan exactly as `classify()` received it — including any AIM
            symbology prefix, which is stripped only to choose a rule and never
            removed from this field. UNTRUSTED, in the same sense as
            `gs1.InternalPayload.raw`: it is arbitrary scanner output, is not
            character-filtered, and may carry control characters. Escape it
            (`repr` / `!r`) before writing it to a log — interpolating it raw
            is a log-forging vector — and never interpolate it into SQL or
            markup.
    """

    kind: ScanKind
    normalized_value: Optional[str]
    ecia_fields: Optional[Mapping[str, str]]
    raw: str

    def __post_init__(self):
        """Validate the shape, then make `ecia_fields` genuinely read-only.

        Type faults raise `TypeError` and combination faults raise
        `ValueError`, and the type check always runs first so the message names
        what is actually wrong: a non-mapping is a non-mapping whatever `kind`
        says.

        `object.__setattr__` is how a frozen dataclass normalizes a field —
        plain assignment would raise `FrozenInstanceError` against its own
        `__setattr__`.
        """
        if not isinstance(self.kind, ScanKind):
            raise TypeError(
                f'kind must be a ScanKind, got {type(self.kind).__name__}: '
                f'{self.kind!r}.')

        # `raw` is what a consumer searches, logs and re-parses. `classify()`
        # rejects a non-str scan at its own door, but it is not the only way to
        # reach this constructor, and a non-str here surfaces as an
        # AttributeError deep inside Story 4.3 or 4.4 rather than at the build.
        if not isinstance(self.raw, str):
            raise TypeError(
                f'raw must be a str, got {type(self.raw).__name__}.')

        value = self.normalized_value
        if value is not None and not isinstance(value, str):
            raise TypeError(
                f'normalized_value must be a str or None, got '
                f'{type(value).__name__}.')
        # The Attributes block above says INTERNAL and GTIN each name a
        # canonical form and ECIA and FREE_TEXT normalize to nothing. Both
        # halves are load-bearing: a GTIN with no normalized_value is a lookup
        # keyed on None in Story 4.3, and a FREE_TEXT carrying one invites a
        # resolver to prefer it over the search `raw` is meant to drive.
        if value is None and self.kind in _KINDS_CARRYING_A_NORMALIZED_VALUE:
            raise ValueError(
                f'kind={self.kind.name} names a canonical form, so '
                f'normalized_value is required; got None.')
        if value is not None and self.kind not in _KINDS_CARRYING_A_NORMALIZED_VALUE:
            raise ValueError(
                f'kind={self.kind.name} normalizes to nothing, so '
                f'normalized_value must be None.')

        fields = self.ecia_fields
        # Checked before `dict(fields)`, which would otherwise coerce a
        # sequence of pairs (`['ab', 'cd']` -> `{'a': 'b', 'c': 'd'}`) into a
        # silently wrong classification, or leak `dict()`'s own message for a
        # str/int and never name the field that was wrong.
        if fields is not None and not isinstance(fields, Mapping):
            raise TypeError(
                f'ecia_fields must be a mapping of MH10.8.2 data identifiers '
                f'or None, got {type(fields).__name__}.')
        if fields is not None and self.kind is not ScanKind.ECIA:
            raise ValueError(
                f'ecia_fields is only meaningful for ScanKind.ECIA; got '
                f'kind={self.kind.name} with ecia_fields set.')
        if fields is None:
            return

        # `Mapping[str, str]` is the declared type and the Attributes block
        # names the seven legal keys, so the container check alone was not the
        # contract. A non-str key lands in Story 4.5's JSON as something
        # `json.dumps` either rejects or silently stringifies, and a mutable
        # value would leave the read-only promise false one level down —
        # `c.ecia_fields['P'].append(...)` still reaching through the proxy.
        for key, item in fields.items():
            if not isinstance(key, str) or not isinstance(item, str):
                raise TypeError(
                    f'ecia_fields must map str data identifiers to str '
                    f'values, got {type(key).__name__} -> '
                    f'{type(item).__name__}.')

        # Copied unconditionally — see the class docstring on why an incoming
        # MappingProxyType is not trusted as-is.
        object.__setattr__(self, 'ecia_fields', MappingProxyType(dict(fields)))


@dataclass(frozen=True)
class ScanResolution:
    """
    What one classified scan resolved to in the catalog (Story 4.3, FR36,
    AD-15).

    The second of AD-15's two frozen shapes and the counterpart of
    `ScanClassification` above: that one says *what was scanned*, this one says
    *what it turned out to be*. Produced by
    `mariadb_catalog_service.CatalogService.resolve_scan()` and by nothing else,
    and — like the classification it carries — it is the contract Story 4.5's
    UI routing, Epic 7's order-time capture and Epic 9's scan-result view are
    written against, so it is deliberately small and has no behavior.

    All three fields are required and none has a default, matching the posture
    `ScanClassification` sets: no call site can build a half-populated
    resolution, and every construction states the outcome explicitly rather
    than letting an omitted field mean "no match".

    FR36's no-dead-end rule is what the three fields together express. Exactly
    one of two things is true of any resolution: either the scan matched a
    record (`product` set, `free_text_hits` empty), or it did not (`product`
    None, `free_text_hits` holding whatever the free-text fallthrough found —
    possibly nothing). "Matched *and* searched" is not a state a resolution can
    represent, and `__post_init__` rejects it, because a consumer shown both
    would have to invent a precedence rule the requirements never state. Both
    "no product and no hits" and "no product and some hits" are legal terminal
    states: Story 4.5 renders the first as a pre-filled create form (FR40) and
    the second as search results.

    Attributes:
        classification: The `ScanClassification` this resolution answers —
            always set, always the verdict `classify()` returned for this exact
            scan, so a consumer never has to re-classify to learn the kind or
            recover the raw text.
        product: The matched Product, or None. It holds an
            `app.database.Product` ORM row that is **detached** — `resolve_scan`
            is read-only and closes its session before returning, so the row's
            scalar columns stay readable but touching a relationship attribute
            (e.g. `.purchases`) raises `DetachedInstanceError`. There is
            deliberately no `isinstance` check on it: `app/models.py` is a leaf
            module that imports nothing from `app.` (pinned by
            `test_models_stays_a_leaf_module`), and importing `Product` here
            would close the `models` -> `database` -> `models` cycle that test
            exists to forbid. The annotation is therefore loose and this
            docstring is the contract. What CAN be checked without that import
            is checked: a `str`, `bytes`, `Mapping` or `Sequence` is refused,
            which catches the swapped-argument case (the hits list handed to
            this field) that no other guard would see.
        free_text_hits: The products the AD-17 free-text search returned for
            this scan, oldest id first, as a tuple. Same detached-row rule as
            `product`. Empty whenever `product` is set — a resolution that
            matched did not search — and legitimately empty when it is not,
            which is the "nothing matched anything" terminal state above. The
            annotation names the post-normalization type: the constructor
            accepts an ordered sequence that is not a `str`/`bytes`/`Mapping`
            and copies it into a tuple, so the list a caller passed in can be
            mutated afterwards without changing the resolution. A set or a
            generator is refused rather than copied, because neither can carry
            the order this attribute promises.

    Two consequences worth stating, both inherited from what the fields hold:

    1. A resolution is not usefully comparable — it holds ORM rows, whose
       `__eq__` is identity, so two resolutions built from separate queries for
       the same product are unequal. Do not use one as a dict key or set member
       either, but not because hashing reliably fails: `frozen=True`
       synthesizes `__hash__` over the fields, so a resolution hashes fine
       whenever its classification's `ecia_fields` is None — every non-`ECIA`
       kind, permanently — and the value it returns is built from the ORM rows'
       identity hashes, so it says nothing about what was resolved. Since
       Story 4.4 populates `ecia_fields`, the SAME call raises `TypeError:
       unhashable type: 'dict'` for a distributor-label scan (the mapping rule
       `ScanClassification` already documents). That is a live hazard rather
       than a future one: a key that works until one arm of a four-way branch
       is exercised is worse than one that never works.
    2. `dataclasses.asdict()` and `copy.deepcopy()` do not work on one. `asdict`
       recurses into the nested `ScanClassification`, which raises `TypeError:
       cannot pickle 'mappingproxy' object` for an `ECIA` resolution now that
       Story 4.4 populates `ecia_fields`, and both would in any case try to
       copy detached ORM rows. A serializer must build its payload field by
       field.
    """

    classification: ScanClassification
    product: Optional[Any]
    free_text_hits: Tuple[Any, ...]

    def __post_init__(self):
        """Validate the shape, then make `free_text_hits` a private tuple.

        Same taxonomy as `ScanClassification.__post_init__` above, and for the
        same reasons: `TypeError` for a wrong type, `ValueError` for an illegal
        combination, every message naming the field and the offending
        `type(x).__name__`, and the type checks running first so a message
        describes what is actually wrong rather than which cross-field rule it
        happened to trip.
        """
        if not isinstance(self.classification, ScanClassification):
            raise TypeError(
                f'classification must be a ScanClassification, got '
                f'{type(self.classification).__name__}.')

        # `product` cannot be checked POSITIVELY (no `Product` import here —
        # see the class docstring), but it can be checked negatively, and the
        # obvious wrong values are worth refusing rather than freezing into a
        # shape Stories 4.4/4.5 and Epics 7/8/9 dereference as a row. The
        # realistic producer error is the arguments swapped — the hits list
        # passed as `product` — which every check below would otherwise wave
        # through, since the combination rule only looks at `free_text_hits`.
        # A `Product` is not a Sequence, Mapping, str or bytes, so nothing this
        # field is meant to hold lands here.
        if isinstance(self.product, (str, bytes, bytearray, Mapping, Sequence)):
            raise TypeError(
                f'product must be a single matched product or None, got '
                f'{type(self.product).__name__} — a sequence here is the hits '
                f'list passed to the wrong field.')

        hits = self.free_text_hits
        # Rejected before `tuple(hits)`, which would otherwise explode a string
        # into its characters and a mapping into its keys — the same coercion
        # trap `ecia_fields` guards against one class up. A single product
        # passed where a sequence was meant is the realistic caller error, and
        # a `Product` is not a Sequence, so it lands on the branch below rather
        # than silently becoming a one-element anything.
        if isinstance(hits, (str, bytes, bytearray, Mapping)):
            raise TypeError(
                f'free_text_hits must be a sequence of products, not a '
                f'{type(hits).__name__} — a string or mapping would be '
                f'exploded into elements.')
        # A Sequence, not merely an Iterable: the attribute documents an order
        # ("oldest id first") and only an ordered container can honor it. A set
        # is iterable and would be accepted by a looser check, then copied into
        # a tuple in whatever order the hash table happened to yield — an order
        # that varies per process. So would a one-shot generator, which reads
        # as a sequence at the call site but cannot be re-read by the producer
        # afterwards. Both are rejected here rather than silently producing a
        # resolution whose stated ordering is false.
        if not isinstance(hits, Sequence):
            raise TypeError(
                f'free_text_hits must be a sequence of products (its order is '
                f'part of the contract), got {type(hits).__name__}.')

        # Copied unconditionally, including when the caller already passed a
        # tuple: `search_products` returns a list, and holding that list would
        # leave the caller a live write channel into a supposedly frozen
        # resolution (the aliasing lesson `ecia_fields` learned one class up).
        object.__setattr__(self, 'free_text_hits', tuple(hits))

        # Checked against the COPY, not the argument, so a one-shot iterator is
        # judged on what was actually kept. A resolution cannot both match and
        # fall through: FR36 falls through only when the lookup missed, so the
        # two being set together means the producer conflated the arms.
        if self.product is not None and self.free_text_hits:
            raise ValueError(
                f'a resolution that matched a product did not fall through to '
                f'search, so free_text_hits must be empty; got '
                f'{len(self.free_text_hits)} hits alongside a product.')
