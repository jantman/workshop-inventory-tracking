# Features

This document outlines a number of features that we need to complete for this project, in priority order. Each feature initially just includes a human-generated explanation; for each feature you (Claude Code, the AI coding assistant) will update this document to include an implementation plan to resolve the feature and then await human approval before proceeding. You are encouraged to solicit human input/feedback during the planning phase for anything you have questions about or do not feel is clear. Once planning is complete, if you get confused or are unable to accomplish a feature without significant issues, please ask for human feedback. You MUST plan one feature at a time, in order, and then implement that feature. As earlier features may inform or change the implementation of later ones, we will work one feature at a time from planning through implementation, completion, and human validation, before moving on to the next.

The following guidelines MUST always be followed:

* Features that are non-trivial in size (i.e. more than a few simple changes) should be broken down into Milestones and Tasks. Those will be given a prefix to be used in commit messages, formatted as `{Feature Name} - {Milestone number}.{Task number}`. Human approval must always be obtained to move from one Milestone to the next.
* At the end of every Milestone and Feature you must (in order):
  1. Ensure that unit and end-to-end (e2e) tests are passing; prior to declaring any Feature complete, you MUST run the complete unit and e2e test suites (note the e2e test suite can take up to fifteen minutes to run) and ensure that ALL tests are passing. No Feature can be complete without ALL test failures being fixed. If the e2e suite times out, then you MUST increase the timeout; this requiredment is NOT satisfied until the e2e suite runs to completion WITHOUT timing out. The fifteen minute timeout MUST be set in your Bash tool so that Claude Code's default 2-minute timeout for bash commands does not terminate the tests early.
  2. Ensure that all relevant documentation (`README.md`, `docs/deployment-guide.md`, `docs/development-testing-guide.md`, `docs/troubleshooting-guide.md`, and `docs/user-manual.md`) has been updated to account for additions, changes, or removals made during the Milestone or Feature.
  2. Update this document to indicate what progress has been made on the relevant Milestone or Feature.
  2. Commit that along with all changes to git, using a commit message beginning with the Milestone/Task prefix and a one-sentence concise summary of the changes, and then further details.
* If you become confused or unclear on how to proceed, have to make a significant decision not explicitly included in the implementation plan, or find yourself making changes and then undoing them without a clear and certain path forward, you must stop and ask for human guidance.
* From time to time we may identify a new, more pressing issue while implementing a feature; we refer to these as "side quests". When beginning a side quest you must update this document to include detailed information on exactly where we're departing from our feature implementation, such that we could use this document to resume from where we left off in a new session, and then commit that. When the side quest is complete, we will resume our feature work.

## Feature: Fix Material Autocomplete Issues

The Material autocomplete field is not populating correctly. This affects the user experience when trying to enter or edit material information for inventory items.

In addition, on both the Add Item and Edit Item pages, we have a text input for Material with an autocomplete. It only accepts values from our three-tiered hierarchical materials taxonomy. While the current autocomplete is good for a user who knows the exact name in our taxonomy that they want to enter, it doesn't help someone discover the taxonomy. Can you suggest how we can handle this input that both allows a user to quickly type in (with autocomplete) a known string, but also can help a user navigate to the desired entry via the tiered hierarchy?

So the goal for this feature is to both fix and improve the Materials autocomplete.

### Implementation Plan

**Analysis Results**: Current material autocomplete system investigation reveals:

**🔍 Current System Architecture:**
- **Database**: 3-level hierarchical taxonomy (Category → Family → Material) in `MaterialTaxonomy` table
- **API**: `/api/materials/suggestions` returns flattened list of material names + aliases via `InventoryService.get_valid_materials()`
- **Frontend**: Basic autocomplete in `material-validation.js` and `inventory-add.js` with debounced input and dropdown
- **Validation**: Materials must exist in taxonomy database, both primary names and aliases accepted

**🎯 Problem Statement:**
1. **Autocomplete Population Issue**: Need to verify if current API is working correctly
2. **Discovery Problem**: Current interface only supports exact string matching - users cannot explore the 3-level taxonomy (Category → Family → Material) to discover available options
3. **User Experience Gap**: Expert users want quick autocomplete, novice users need guided taxonomy exploration

**💡 Solution Approach:**
Implement a **smart progressive disclosure** interface that combines both experiences seamlessly:
1. **Type-ahead + Hierarchy**: Start with empty input showing category list, progressively filter/narrow as user types
2. **Contextual Results**: Show both exact matches AND relevant taxonomy branches in a unified dropdown
3. **Navigation + Search**: Click to navigate taxonomy levels OR type to filter across all levels
4. **No Mode Switching**: Single interface that adapts to user behavior automatically

**Milestone 1: Analyze and Fix Current Autocomplete (FMAI-1)**
- FMAI-1.1: Investigate current autocomplete functionality - verify API responses and frontend behavior
- FMAI-1.2: Identify any bugs in `/api/materials/suggestions` endpoint or `material-validation.js`
- FMAI-1.3: Test material validation and ensure all taxonomy entries are properly returned
- FMAI-1.4: Fix any identified issues with current autocomplete population
- FMAI-1.5: Ensure current autocomplete works correctly before enhancing it

**Milestone 2: Create Enhanced Material Selector Component (FMAI-2)**
- FMAI-2.1: Create new `/api/materials/hierarchy` endpoint returning properly structured taxonomy tree
- FMAI-2.2: Design and implement `MaterialSelector` JavaScript component with progressive disclosure interface
- FMAI-2.3: Implement empty state showing top-level categories for taxonomy discovery
- FMAI-2.4: Implement smart filtering that shows both exact matches and explorable taxonomy branches
- FMAI-2.5: Add click-to-navigate functionality alongside type-to-filter behavior

**Milestone 3: Integrate and Enhance User Experience (FMAI-3)**
- FMAI-3.1: Replace existing material inputs on Add Item page with new MaterialSelector
- FMAI-3.2: Replace existing material inputs on Edit Item page with new MaterialSelector
- FMAI-3.3: Add visual indicators for taxonomy levels (icons, colors) and breadcrumb context
- FMAI-3.4: Implement keyboard navigation (arrow keys, enter, escape) for accessibility
- FMAI-3.5: Add responsive design and mobile-friendly interaction patterns

**Milestone 4: Testing and Documentation (FMAI-4)**
- FMAI-4.1: Create comprehensive unit tests for new MaterialSelector component
- FMAI-4.2: Add E2E tests covering both typing and navigation workflows
- FMAI-4.3: Test accessibility with keyboard navigation and screen readers
- FMAI-4.4: Update user documentation with new material selection interface
- FMAI-4.5: Run complete test suites to ensure no regressions

**🔧 Technical Implementation Details:**

**API Enhancements:**
- **Hierarchy Endpoint**: `/api/materials/hierarchy` returning nested structure: `[{name, level, children: []}]`
- **Enhanced Suggestions**: Modify existing `/api/materials/suggestions` to include taxonomy context and level information

**Frontend Component Architecture:**
- **MaterialSelector Class**: Single intelligent component that adapts behavior based on input state
- **Progressive Disclosure**: Empty input shows categories, typing filters across all levels, clicking navigates
- **Smart Results**: Dropdown shows mix of exact matches + navigable taxonomy branches
- **Auto-initialization**: Component automatically replaces material input fields on page load

**User Interface Behavior:**
- **Empty State**: Shows all top-level categories (Hardware, Fasteners, etc.) as clickable options
- **Typing State**: Real-time filtering shows both exact material matches AND relevant branches to explore  
- **Mixed Results**: Dropdown contains both final materials (selectable) and intermediate categories/families (explorable)
- **Visual Hierarchy**: Color-coded levels with icons: 📁 Categories, 📂 Families, 🔧 Materials
- **Context Breadcrumbs**: Show current location when navigating: "Currently browsing: Hardware › Fasteners"

**Example User Flows:**
1. **Expert User**: Types "stainless" → sees immediate matches like "Stainless Steel", "316 Stainless Steel" 
2. **Discovery User**: Clicks input → sees categories → clicks "Hardware" → sees families → clicks "Fasteners" → sees materials
3. **Hybrid User**: Types "steel" → sees both "Carbon Steel" (direct match) and "Hardware › Fasteners" (explorable branch with steel items)

This approach eliminates mode switching while providing both expert efficiency and discovery guidance in a single, intuitive interface.

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

## Feature: JA ID Lookup Improvement

The `ja-id-lookup` input field in the header of our pages seems to automatically add a `JA` prefix when anything is entered in the field. We must stop doing this as it breaks barcode input. Remove this functionality and any code that is rendered unused after doing so.

## Feature: View Item History

`docs/add-history-ui.md` describes an Item History UI for which we've implemented the backend but not the frontend. Our goal for this feature is to implement the frontend. Once we complete planning for this feature, you must delete `docs/add-history-ui.md`.

## Feature: GitHub Actions Tests

The GitHub Actions test workflows are failing. We need to get them to succeed (like the local ones).

## Feature: Documentation Review

Review all documentation in `README.md` and `docs/`; remove anything that is outdated or not longer relevant/accurate. Then, review the current codebase and identify any areas that are lacking in documentation; present these findings for human review and confirmation of what should have additional documentation.

Be sure to review all `/*.py` and `/scripts/` files and any other utilities, and either document them or propose them (to the human user) as no longer needed and candidates for cleanup.

## Feature: Cleanup

Review all `.py` files in the repository and identify any that are no longer needed for proper functioning of the application, such as data migration scripts. Remove them.

## Feature: Model Architecture Consolidation

Consolidate the duplicate `Item` and `InventoryItem` models into a single model architecture to eliminate maintenance burden and prevent type mismatch bugs.

**Problem Statement:**
Currently we have two models representing the same domain concept:
- `InventoryItem` (database.py): SQLAlchemy ORM model with simple types (String, Boolean, Numeric)
- `Item` (models.py): Business logic dataclass with rich types, enums, and validation

This creates maintenance overhead, requires complex conversion logic, and is prone to bugs like the search functionality issue where enum values are compared against database string columns.

**Goal:**
Create a single model architecture that provides both database persistence and business logic capabilities while maintaining the current design principle of enum-without-migration (adding enum values without database schema changes).

**Proposed Approach:**
Convert to a single `InventoryItem` SQLAlchemy model with:
- String columns in the database (no schema changes required)
- Enum properties that convert to/from database string values automatically
- Validation and business logic methods integrated into the model
- Elimination of the separate `Item` dataclass and all conversion logic

**Success Criteria:**
- Single source of truth for field definitions
- No complex conversion layer between models
- Maintains enum-without-migration capability
- All existing functionality preserved
- Significant reduction in code complexity
