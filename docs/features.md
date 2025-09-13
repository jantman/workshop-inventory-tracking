# Features

This document outlines a number of features that we need to complete for this project, in priority order. Each feature initially just includes a human-generated explanation; for each feature you (Claude Code, the AI coding assistant) will update this document to include an implementation plan to resolve the feature and then await human approval before proceeding. You are encouraged to solicit human input/feedback during the planning phase for anything you have questions about or do not feel is clear. Once planning is complete, if you get confused or are unable to accomplish a feature without significant issues, please ask for human feedback. You MUST plan one feature at a time, in order, and then implement that feature. As earlier features may inform or change the implementation of later ones, we will work one feature at a time from planning through implementation, completion, and human validation, before moving on to the next.

The following guidelines MUST always be followed:

* Features that are non-trivial in size (i.e. more than a few simple changes) should be broken down into Milestones and Tasks. Those will be given a prefix to be used in commit messages, formatted as `{Feature Name} - {Milestone number}.{Task number}`. Human approval must always be obtained to move from one Milestone to the next.
* At the end of every Milestone and Feature you must (in order):
  1. Ensure that unit and end-to-end (e2e) tests are passing; prior to declaring any Feature complete, you must run the complete unit and e2e test suites (note the e2e test suite can take up to five minutes to run) and ensure that ALL tests are passing. No Feature can be complete without ALL test failures being fixed.
  2. Ensure that all relevant documentation (`README.md`, `docs/deployment-guide.md`, `docs/development-testing-guide.md`, `docs/troubleshooting-guide.md`, and `docs/user-manual.md`) has been updated to account for additions, changes, or removals made during the Milestone or Feature.
  2. Update this document to indicate what progress has been made on the relevant Milestone or Feature.
  2. Commit that along with all changes to git, using a commit message beginning with the Milestone/Task prefix and a one-sentence concise summary of the changes, and then further details.
* If you become confused or unclear on how to proceed, have to make a significant decision not explicitly included in the implementation plan, or find yourself making changes and then undoing them without a clear and certain path forward, you must stop and ask for human guidance.
* From time to time we may identify a new, more pressing issue while implementing a feature; we refer to these as "side quests". When beginning a side quest you must update this document to include detailed information on exactly where we're departing from our feature implementation, such that we could use this document to resume from where we left off in a new session, and then commit that. When the side quest is complete, we will resume our feature work.

## Feature: Google Sheets Cleanup

We have migrated from using Google Sheets for our backend storage to using MySQL/MariaDB; Google Sheets should now only be used for export functionality. We need to identify any code aside from the export functionality that still supports Google Sheets and remove it, making sure that anything that calls this code is migrated to use MariaDB instead. When this is complete, all E2E tests must pass. The Google Sheets export functionality cannot be covered by automated tests, so when you believe that this Feature is complete, we will need human assistance to manually trigger and verify the Google Sheets export.

### Implementation Plan

**Overview:** Remove all non-export Google Sheets code while preserving the export-to-Google-Sheets feature.

**Code Analysis:**
- **KEEP:** `app/google_sheets_export.py`, `app/export_service.py`, `app/export_schemas.py`, export routes in `app/main/routes.py`, `app/templates/admin/export.html`, Google Sheets config in `config.py`
- **REMOVE:** `app/google_sheets_storage.py`, migration scripts, Google Sheets storage factory code, unused imports throughout codebase

**Milestone 1: Remove Core Google Sheets Storage Infrastructure** ✅ COMPLETED
- GSC-1.1: Remove `app/google_sheets_storage.py` file ✅
- GSC-1.2: Remove Google Sheets storage factory methods from `app/storage_factory.py` ✅
- GSC-1.3: Update imports and remove Google Sheets fallback code in `app/inventory_service.py` ✅
- GSC-1.4: Update imports and constructor in `app/materials_service.py` ✅
- GSC-1.5: Update imports and constructor in `app/materials_admin_service.py` ✅

**Milestone 2: Remove Migration Scripts and Legacy Code** ✅ COMPLETED
- GSC-2.1: Remove `scripts/migrate_from_sheets.py` ✅
- GSC-2.2: Remove `scripts/analyze_sheets_data.py` ✅
- GSC-2.3: Remove `migrate_data.py` ✅
- GSC-2.4: Clean up unused Google Sheets imports in `app/admin/routes.py` ✅
- GSC-2.5: Remove Google Sheets references from test files if any ✅

**Milestone 3: Verify Export Functionality and Tests** 🔄 IN PROGRESS
- GSC-3.1: Run full unit test suite and fix any import/reference issues ✅
- GSC-3.2: Run full E2E test suite and ensure all tests pass ✅
- GSC-3.3: Manual verification that Google Sheets export still works ⏳ (Requires human verification)
- GSC-3.4: Update documentation to reflect changes ✅

## Feature: Item Update Failures

Items JA000181 and JA000182 and maybe others are not populating correctly in the Edit view, but show properly in the list view and item details modal. I also cannot edit them, I just get "Failed to update item. Please try again" and no further details. First fix the population issues for these items and then ask me to try editing them again. If that still fails, I will provide you with server logs so we can fix the issue preventing them from being edited. A server running our code (and reloading whenever the code changes) is available at `http://192.168.0.24:5603/`; this is using production data so you must not make any changes to the data without my explicit approval.

## Feature: Remove Some Placeholders

Please get rid of the placeholder values in the Purchase Information and Location fields on the add and edit views; I find them confusing.

## Feature: Label Printing

We would like to add the ability to print a barcode label for the JA ID of an item, from the Add Item or Edit Item views. This should be triggered from a button with a printer icon near to the JA ID form field. Clicking the button should bring up a modal dialog allowing the user to select a label type name from a dropdown and then click a button to trigger printing. The label type names must only exist in one place, in Python code.

Code for printing labels is already written; it exists in the `jantman` branch of `https://github.com/jantman/pt-p710bt-label-maker` - this is not available as a Python package, but must be installed directly from that branch of that git repository.

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

## Feature: Improved Materials Input

On both the Add Item and Edit Item pages, we have a text input for Material with an autocomplete. It only accepts values from our three-tiered hierarchical materials taxonomy. While the current autocomplete is good for a user who knows the exact name in our taxonomy that they want to enter, it doesn't help someone discover the taxonomy. Can you suggest how we can handle this input that both allows a user to quickly type in (with autocomplete) a known string, but also can help a user navigate to the desired entry via the tiered hierarchy?

## Feature: View Item History

`docs/add-history-ui.md` describes an Item History UI for which we've implemented the backend but not the frontend. Our goal for this feature is to implement the frontend. Once we complete planning for this feature, you must delete `docs/add-history-ui.md`.

## Feature: GitHub Actions Tests

The GitHub Actions test workflows are failing. We need to get them to succeed (like the local ones).

## Feature: Documentation Review

Review all documentation in `README.md` and `docs/`; remove anything that is outdated or not longer relevant/accurate. Then, review the current codebase and identify any areas that are lacking in documentation; present these findings for human review and confirmation of what should have additional documentation.

Be sure to review all `/*.py` and `/scripts/` files and any other utilities, and either document them or propose them (to the human user) as no longer needed and candidates for cleanup.

## Feature: Cleanup

Review all `.py` files in the repository and identify any that are no longer needed for proper functioning of the application, such as data migration scripts. Remove them.
