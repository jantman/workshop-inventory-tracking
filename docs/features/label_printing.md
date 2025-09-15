# Feature: Label Printing

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

We would like to add the ability to print a barcode label for the JA ID of an item, from the Add Item or Edit Item views. This should be triggered from a button with a printer icon near to the JA ID form field. Clicking the button should bring up a modal dialog allowing the user to select a label type name from a dropdown and then click a button to trigger printing. The label type names must only exist in one place, in Python code.

Code for printing labels is already written; it exists in the `jantman` branch of `https://github.com/jantman/pt-p710bt-label-maker` - this is not available as a Python package, but must be installed directly from that branch of that git repository.

**VERY IMPORTANT:** Running the code snippets below (and specifically, calling `LpPrinter().print_images()`) WILL cause an actual printer to actually print labels, so it must NEVER be done by any tests. You will need to implement some sort of short-circuit pattern where, if the application is running in test mode (i.e. e2e tests), the `generate_and_print_label()` function exits right after being called, and somehow indicates what parameters it was called with, so that the e2e tests can verify it was called without actually printing labels. The implementation of `generate_and_print_label()` can be verified via unit tests.

As part of your planning process, please explain to me what the UI for label printing (on both Add Item and Edit Item) will look like, so that I can suggest changes prior to implementation.

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

And here is a dictionary mapping label type names (which the user will select in the UI) to the keyword arguments that should be passed to `generate_and_print_label()` for each of them; each of these keyword argument dictionaries expect one more element, `barcode_value`, whose value is the string barcode content (JA ID). On the Add Item form, label type selection should carry forward when that functionality is used. There is no need to persist the label type in the backend/database. **IMPORTANT** these label types must be defined in one and only one place; adding a new label type to this dictionary should fulfill everything required to make that label type usable in the UI and successfully print.

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

When complete, please update `docs/user-manual.md` with user instructions for printing labels.

## Implementation Plan

This feature will be implemented in two milestones:

### Milestone 1: Backend Infrastructure and Core Printing Service ✅ COMPLETED

**Label Printing - 1.1: Install Dependencies and Create Core Service** ✅
- ✅ Install pt-p710bt-label-maker dependency from jantman branch
- ✅ Create backend label printing service (`app/services/label_printer.py`) with:
  - ✅ `LABEL_TYPES` dictionary defining all supported label configurations
  - ✅ `generate_and_print_label()` function implementation
  - ✅ Test mode detection and short-circuit logic for e2e tests
  - ✅ Proper error handling and logging

**Label Printing - 1.2: Add API Endpoint and Backend Integration** ✅
- ✅ Create `/api/labels/print` POST endpoint in Flask routes
- ✅ Create `/api/labels/types` GET endpoint for UI consumption  
- ✅ Implement request validation for JA ID and label type
- ✅ Add proper error responses and JSON formatting
- ✅ Write comprehensive unit tests for the label printing service (19 tests)
- ✅ Write unit tests for the API endpoint

### Milestone 2: Frontend Implementation and Integration

**Label Printing - 2.1: Create Reusable Modal Component**
- Implement shared label printing modal component (`static/js/label-printing-modal.js`)
- Modal includes label type dropdown populated from backend
- Implement API integration for print requests
- Add proper error handling and user feedback
- Include loading states and success/error messages

**Label Printing - 2.2: Integrate UI Components**
- Add printer button to Add Item view JA ID input group
- Add printer button to Edit Item view JA ID input group
- Implement label type persistence in localStorage for Add Item form
- Ensure buttons are properly disabled/enabled based on JA ID validity
- Add tooltips and proper accessibility attributes

**Label Printing - 2.3: Testing and Documentation**
- Write comprehensive e2e tests for label printing workflow
- Verify test mode functionality prevents actual printing during tests
- Test label type persistence on Add Item form
- Test error handling scenarios (invalid JA ID, print failures)
- Update `docs/user-manual.md` with user instructions
- Run complete unit and e2e test suites with 10-minute timeout for e2e tests
- **CRITICAL**: ALL (100%) unit and e2e tests MUST pass - no exceptions
- Disabling or deleting any failing tests requires explicit human approval

## UI Design Summary

### Button Placement
- **Add Item View**: Printer button added to JA ID input group (alongside existing barcode scan button)
- **Edit Item View**: Printer button added to JA ID input group (alongside existing generate JA ID button)

### Modal Design
- **Title**: "Print Label for [JA_ID]"
- **Content**: Dropdown selector populated dynamically from the single LABEL_TYPES dictionary in Python (no hard-coding in UI)
- **Actions**: Cancel and Print Label buttons
- **Persistence**: Label type selection persists in Add Item form using localStorage

### Technical Requirements
- All label types defined in single location (`LABEL_TYPES` dictionary)
- Test mode short-circuit to prevent actual printing during tests
- Proper error handling and user feedback
- API endpoint accessible without CSRF protection for script/curl usage
- Comprehensive unit and e2e test coverage
