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
