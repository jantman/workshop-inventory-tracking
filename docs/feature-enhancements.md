# Feature Enhancements

## Implementation Plan

**Recommended Phase Order:**
1. **JA ID Assignment** - Foundation feature (easiest implementation)
2. **Hierarchical Materials** - Core data organization (moderate complexity) 
3. **Label Printing** - Dependent on clean data structure (integration complexity)

**Storage Backend Decision:** Defer SQLite upgrade. Current Google Sheets integration is well-architected and stable.

---

## Phase 1: JA ID Assignment

**Goal:** Automatically assign the next sequential JA ID to new items.

**Implementation Notes:**
- Current model only validates JA ID format (`app/models.py:402`) - no auto-generation exists
- Need to implement auto-generation logic in `app/inventory_service.py`
- Auto-discover current highest JA ID by querying Google Sheet data
- Update add item workflow in `app/main/routes.py` to call auto-generation
- Consider thread-safe ID generation for concurrent requests

---

## Phase 2: Hierarchical Materials

**Goal:** Create hierarchical taxonomy for materials and migrate existing flat structure.

**Current State:** 
- Long unorganized list including `Steel`, `Stainless` (and `Stainless??`), `4140`, `12L14`, `O1 Tool Steel`, etc.
- Foundation exists in `app/taxonomy.py`

**Proposed Structure:**
- Top-level: `Steel`, `Stainless`, `Aluminum`, `Brass`, `Copper`
- Sub-materials: Specific alloys (4140, 12L14) or groupings (Tool Steel → O1, W1)
- Support unlimited nesting depth

**Requirements:**
- Hierarchical material selection UI with search/filter
- Admin form for adding new materials at any level
- Migration tool for existing ~200 materials
- Maintain backward compatibility during transition

**Storage Solution:** New "Materials" Google Sheet tab with columns: `Name`, `Parent`, `Level`, `Category`

**Migration Strategy:**
1. Extract all unique material values from current inventory data
2. Clean ambiguous materials (strip question marks, etc.)
3. Generate proposed hierarchical taxonomy mapping
4. Present for user review and adjustment
5. Create manual verification list for remaining ambiguous materials
6. Populate Materials sheet with approved taxonomy

**Current State Analysis:**
- `app/taxonomy.py` is actively used for material normalization and type/shape validation
- All taxonomy data is currently in-memory/hardcoded - no persistent storage
- Current system only normalizes material names, no hierarchy enforcement

---

## Phase 3: Label Printing

**Goal:** Optional label printing for newly added items during the add item process, and for existing items using a button/link to print the label.

**Integration:**
- External Python class in separate package  
- Different keyword arguments for different label sizes/types
- Integrate into add item workflow

**Implementation Notes:**
- Need to add dependency on the `jantman` branch of `https://github.com/jantman/pt-p710bt-label-maker` - this is not available as a Python package, but must be installed directly from that branch of that git repository.
- https://github.com/jantman/pt-p710bt-label-maker/blob/jantman/pt_p710bt_label_maker/barcode_label.py is a command line variant of the barcode label printer that we want to implement

Here is a code snippet with a reusable function that can be called to print labels:

```python
from pt_p710bt_label_maker.barcode_label import BarcodeLabelGenerator, FlagModeGenerator
from pt_p710bt_label_maker.lp_printer import LpPrinter
from typing import Union, List
from io import BytesIO

def generate_and_print_label(
    barcode_value: str,
    lp_options: str,
    maxlen_inches: float,
    lp_width_px: int,
    fixed_len_px: int,
    flag_mode: bool = False,
    lp_dpi: int = 305,
    num_copies: int = 1
) -> None:
    """
    Generate and print a barcode label equivalent to pt-barcode-label commands.
    
    Args:
        barcode_value: The text/value for the barcode
        lp_options: LP printer options string (e.g., "-d printer_name -o option=value")
        maxlen_inches: Maximum label length in inches
        lp_width_px: Width in pixels for LP printing (height of the label)
        fixed_len_px: Fixed length in pixels for the final image
        flag_mode: Whether to use flag mode (rotated barcodes at ends)
        lp_dpi: DPI for LP printing (default: 305)
        num_copies: Number of copies to print (default: 1)
    """
    # Calculate maxlen_px from inches
    maxlen_px: int = int(maxlen_inches * lp_dpi)
    
    # Generate the appropriate label type
    generator: Union[BarcodeLabelGenerator, FlagModeGenerator]
    if flag_mode:
        generator = FlagModeGenerator(
            value=barcode_value,
            height_px=lp_width_px,
            maxlen_px=maxlen_px,
            fixed_len_px=fixed_len_px,
            show_text=True
        )
    else:
        generator = BarcodeLabelGenerator(
            value=barcode_value,
            height_px=lp_width_px,
            maxlen_px=maxlen_px,
            fixed_len_px=fixed_len_px,
            show_text=True
        )
    
    # Print using lp
    printer: LpPrinter = LpPrinter(lp_options)
    images: List[BytesIO] = [generator.file_obj] * num_copies if num_copies > 1 else [generator.file_obj]
    printer.print_images(images)
```

And here is a dictionary mapping label type names (which the user will select in the UI) to the keyword arguments that should be passed to `generate_and_print_label()` for each of them; each of these keyword argument dictionaries expect one more element, `barcode_value`, whose value is the string barcode content (JA ID):

```python
LABEL_TYPES: Dict[str, dict] = {
    'Sato 1x2': {
        "lp_options": "-d sato2 -o PageSize=w144h72 -o Level=B -o Darkness=5",
        "maxlen_inches": 2.0,
        "lp_width_px": 305,
        "fixed_len_px": 610,
        "lp_dpi": 305
    },
    'Sato 1x2 Flag': {
        "lp_options": "-d sato2 -o PageSize=w144h72 -o Level=B -o Darkness=5",
        "maxlen_inches": 2.0,
        "lp_width_px": 305,
        "fixed_len_px": 610,
        "flag_mode": True,
        "lp_dpi": 305
    },
    'Sato 2x4': {
        "lp_options": "-d sato3 -o PageSize=w288h144 -o Level=B -o Darkness=5",
        "maxlen_inches": 4.0,
        "lp_width_px": 610,
        "fixed_len_px": 1220,
        "lp_dpi": 305
    },
    'Sato 2x4 Flag': {
        "lp_options": "-d sato3 -o PageSize=w288h144 -o Level=B -o Darkness=5",
        "maxlen_inches": 4.0,
        "lp_width_px": 610,
        "fixed_len_px": 1220,
        "flag_mode": True,
        "lp_dpi": 305
    },
    'Sato 4x6': {
        "lp_options": "-d SatoM48Pro2 -o PageSize=w400h600 -o Level=B -o Darkness=5 -o landscape",
        "maxlen_inches": 6.0,
        "lp_width_px": 1218,
        "fixed_len_px": 2436,
        "lp_dpi": 203
    },
    'Sato 4x6 Flag': {
        "lp_options": "-d SatoM48Pro2 -o PageSize=w400h600 -o Level=B -o Darkness=5 -o landscape",
        "maxlen_inches": 6.0,
        "lp_width_px": 1218,
        "fixed_len_px": 2436,
        "flag_mode": True,
        "lp_dpi": 203
    }
}
```

---

## Storage Backend Upgrade (Deferred)

**Analysis:** Current Google Sheets backend is production-ready with:
- Clean storage abstraction (`app/storage.py`, `app/google_sheets_storage.py`)
- Comprehensive error handling, retry logic, and circuit breakers  
- Authentication management

**Decision:** Defer SQLite upgrade. The existing architecture supports future migration without blocking current enhancements.

**Future Considerations:** If migrated, would need Google Sheets sync mechanism (on-demand endpoint or post-save hooks).
