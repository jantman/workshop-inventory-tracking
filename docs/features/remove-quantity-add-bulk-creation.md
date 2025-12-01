# Feature: Remove Quantity Field and Add Bulk Item Creation

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

The inventory system currently has a `quantity` field on items that was intended to track multiple identical items under a single JA ID. However, this design conflicts with the shortening operation, which always creates a new item with `quantity=1`. This feature removes the quantity field entirely and replaces it with proper bulk creation workflows that create individual items with unique JA IDs.

## Problem Statement

### Current Issues
1. **Quantity field conflicts with shortening logic**: When an item with `quantity > 1` is shortened, the system creates a new item with `quantity=1`, losing track of the remaining items.
2. **Incomplete quantity tracking**: There's no workflow to decrement quantity when items are used or removed.
3. **Physical reality mismatch**: Each physical item needs its own barcode/JA ID to be tracked through its lifecycle (shortening, moving, etc.).

### Real-World Scenario
User receives 6 identical steel bars in a single order. Currently they might set `quantity=6` with one JA ID, but this breaks down when:
- One bar is shortened (other 5 are lost from tracking)
- Bars are stored in different locations
- Individual bars need to be tracked through their lifecycle

## Current State

### Quantity Field Usage
The `quantity` field currently appears in:
- Database: `inventory_items.quantity` column (Integer, nullable=False, min=1)
- Add form: Input field for quantity (`app/templates/inventory/add.html:106-107`)
- Edit form: Input field for quantity (`app/templates/inventory/edit.html:112-114`)
- Shorten page: Display only (`app/templates/inventory/shorten.html:81`)
- Item list: Display in detail popover (`app/static/js/inventory-list.js:806-807`)
- Export: CSV/Excel export column (`app/export_schemas.py:86, 130`)
- Shortening: Hardcoded to 1 in `shorten_item()` (`app/mariadb_inventory_service.py:492`)
- Tests: Extensive usage throughout unit and e2e tests

### Existing Infrastructure
- JA ID auto-generation: `/api/inventory/next-ja-id` endpoint
- Label printing: `/api/labels/print` endpoint with size selection
- Add form: "Add & Continue" feature for rapid sequential entry
- Item duplication: None (to be created)

## Goals

### Primary Objectives
1. **Remove quantity field**: Complete removal from database, models, forms, UI, exports, and tests
2. **Migration for existing data**: Split 9 existing items (quantity 2-5) into individual items with unique JA IDs
3. **Bulk creation on add**: "Quantity to Create" field that creates N items with sequential JA IDs
4. **Duplicate functionality**: "Duplicate" button on edit form to create copies with new JA IDs
5. **Label printing integration**: Streamlined label printing for bulk-created items
6. **Comprehensive testing**: Full e2e test coverage for all new functionality

### Design Principles
- **One JA ID = One physical item**: Each item gets its own unique identifier
- **Identical copies**: All fields copied except JA ID (including dimensions, purchase info, notes)
- **No photo duplication**: Photos stay with original item only
- **History isolation**: Duplicates don't inherit shortening history

## Implementation Plan

### Milestone 1: Database Migration and Quantity Removal (RQBC - 1.1 - 1.5)
**Prefix: RQBC - 1**

**Task 1.1: Remove Quantity from Database Model**
- Update `InventoryItem` class in `app/database.py`:
  - Remove `quantity` column definition
  - Remove quantity validation in `validate()` method
  - Update `to_dict()` and `from_dict_enhanced()` methods
- **Files**: `app/database.py`
- **Note**: This must be done first so auto-migration can detect the schema change

**Task 1.2: Generate and Customize Database Migration**
- Generate migration using Alembic:
  ```bash
  python manage.py db migrate -m "Remove quantity field and split multi-quantity items"
  ```
- Manually edit the generated migration file to add custom upgrade logic BEFORE dropping quantity column:
  1. Query all items with `quantity > 1` (ordered by JA ID)
  2. For each item:
     - Get next N-1 available JA IDs (where N = quantity)
     - Create N-1 new rows with all fields identical except:
       - `ja_id`: New sequential JA IDs
       - `quantity`: 1
       - `date_added`: Current timestamp (using `op.inline_literal()`)
       - `last_modified`: Current timestamp (using `op.inline_literal()`)
       - `notes`: Append "This item was created via database migration as a duplicate of {original_ja_id} with an original quantity of {N}."
     - Update original item: Set `quantity=1`
  3. Print summary: Total items processed, new JA IDs created
  4. Then allow auto-generated code to drop `quantity` column
- Migration should use Alembic's batch mode for transactional safety
- Log all actions (original JA ID → new JA IDs created) to stdout during migration
- **Files**: `migrations/versions/XXXXX_remove_quantity_split_items.py`

**Task 1.3: Remove Quantity from Service Layer**
- Update `MariaDBInventoryService` in `app/mariadb_inventory_service.py`:
  - Remove quantity handling in `add_item()`
  - Remove quantity from `update_item()`
  - Remove quantity from `shorten_item()` (already hardcoded to 1, just remove the parameter)
- Update `MariaDBStorage` in `app/mariadb_storage.py`:
  - Remove quantity handling from all methods
- **Files**: `app/mariadb_inventory_service.py`, `app/mariadb_storage.py`

**Task 1.4: Remove Quantity from Forms and Templates**
- Remove quantity input from add form (`app/templates/inventory/add.html:106-107`)
- Remove quantity input from edit form (`app/templates/inventory/edit.html:112-114`)
- Remove quantity display from shorten page (`app/templates/inventory/shorten.html:81`)
- Update JavaScript files:
  - `app/static/js/inventory-add.js`: Remove quantity handling
  - `app/static/js/inventory-list.js`: Remove quantity from detail popover (lines 806-807)
  - `app/static/js/inventory-shorten.js`: Remove quantity display
- **Files**: Multiple template and JS files

**Task 1.5: Remove Quantity from Routes and Export**
- Remove quantity from form processing in `app/main/routes.py`:
  - `inventory_add()` POST handler
  - `inventory_edit()` POST handler
  - Any other routes that reference quantity
- Remove quantity from export schemas (`app/export_schemas.py:86, 130`)
- **Files**: `app/main/routes.py`, `app/export_schemas.py`

**Completion Criteria:**
- Migration runs successfully, creating individual items for all quantity > 1 cases
- Quantity field completely removed from codebase
- All existing functionality works without quantity field
- Unit tests pass (after updating in Milestone 4)

---

### Milestone 2: Bulk Creation - "Quantity to Create" (RQBC - 2.1 - 2.4)
**Prefix: RQBC - 2**

**Task 2.1: Add "Quantity to Create" Field to Add Form**
- Add number input field to add form after JA ID field:
  - Label: "Quantity to Create"
  - ID: `quantity_to_create`
  - Type: `number`
  - Min: 1
  - Max: 100
  - Default: 1
  - Help text: "Number of identical items to create (each with unique JA ID)"
- Add JavaScript validation to show/hide bulk creation info
- When value > 1, show info message: "This will create {N} items with sequential JA IDs starting from {current_ja_id}"
- **Files**: `app/templates/inventory/add.html`, `app/static/js/inventory-add.js`

**Task 2.2: Implement Backend Bulk Creation Logic**
- Update `POST /inventory/add` route in `app/main/routes.py`:
  - Accept `quantity_to_create` parameter (default: 1)
  - If quantity_to_create == 1: Use existing single-item logic
  - If quantity_to_create > 1:
    1. Validate all item fields (material, dimensions, etc.)
    2. Get next N available JA IDs sequentially
    3. Create N items with identical data except JA ID
    4. All items get current timestamp for `date_added` and `last_modified`
    5. Return success response with array of created JA IDs: `["JA000101", "JA000102", ...]`
- Add validation: quantity_to_create must be 1-100
- Transaction-safe: All N items created or none (rollback on error)
- **Files**: `app/main/routes.py`

**Task 2.3: Update Frontend to Handle Bulk Creation Response**
- Update `app/static/js/inventory-add.js`:
  - Handle successful bulk creation response
  - Show success toast: "Successfully created {N} items: {first_ja_id} - {last_ja_id}"
  - Store created JA IDs for label printing
  - Enable "Print Labels" button
- **Files**: `app/static/js/inventory-add.js`

**Task 2.4: Add Bulk Label Printing Modal**
- Create modal component for bulk label printing:
  - Title: "Print Labels for {N} Items"
  - Show list of JA IDs to be printed
  - Label size selector (using existing label sizes)
  - Buttons: "Cancel", "Print All Labels"
- Implement bulk print functionality:
  - Call existing `/api/labels/print` endpoint for each JA ID sequentially
  - Show progress indicator during printing
  - Handle partial failures gracefully (show which labels succeeded/failed)
  - Success message: "Printed {N} labels successfully"
- Modal triggered automatically after bulk creation (if quantity > 1)
- Modal can also be triggered manually from success message
- **Files**: `app/templates/inventory/add.html`, `app/static/js/inventory-add.js`

**Completion Criteria:**
- Users can create multiple identical items with one form submission
- Each item gets unique sequential JA ID
- Label printing integration works smoothly
- Success/error messages are clear and helpful

---

### Milestone 3: Duplicate Button Functionality (RQBC - 3.1 - 3.4)
**Prefix: RQBC - 3**

**Task 3.1: Add Duplicate Button Component**
- Create reusable duplicate button component:
  - Can be included in any page via template partial or JavaScript
  - Takes item JA ID as parameter
  - Styled consistently with existing buttons
  - Icon: "copy" or "duplicate" Bootstrap icon
- Add duplicate button to edit form header:
  - Location: Next to "View History" button
  - Label: "Duplicate Item"
  - Tooltip: "Create copies of this item with new JA IDs"
- **Files**: `app/templates/inventory/edit.html`, `app/static/js/` (new component file)

**Task 3.2: Create Duplicate Modal UI**
- Modal with the following elements:
  - Title: "Duplicate Item {ja_id}"
  - Item summary: Display name, material, dimensions
  - Quantity input: "Number of copies to create" (min: 1, max: 100, default: 1)
  - Preview: "This will create {N} new items with JA IDs: {range}"
  - Warning if unsaved changes: "You have unsaved changes. Choose an option:"
    - Radio buttons: "Save changes and duplicate", "Discard changes and duplicate"
  - Buttons: "Cancel", "Create Duplicates"
- **Files**: `app/templates/inventory/edit.html`

**Task 3.3: Implement Duplicate Backend Endpoint**
- Create new API endpoint: `POST /api/items/<ja_id>/duplicate`
- Request body: `{"quantity": N, "save_changes": bool, "updated_fields": {...}}`
- Logic:
  1. Fetch active item for ja_id
  2. If save_changes=true: Update original item with updated_fields first
  3. Get next N available JA IDs
  4. Create N new items copying all fields from source item except:
     - `ja_id`: New sequential JA IDs
     - `date_added`: Current timestamp
     - `last_modified`: Current timestamp
     - History: Don't copy inactive predecessor rows
     - Photos: Don't copy photo records
  5. Return array of created JA IDs
- Transaction-safe: All operations succeed or rollback
- **Files**: `app/main/routes.py`, `app/mariadb_inventory_service.py` (add `duplicate_item()` method)

**Task 3.4: Implement Duplicate Frontend Logic**
- Update `app/static/js/` to handle duplicate workflow:
  1. User clicks "Duplicate" button
  2. Check for unsaved changes in form (compare current form values to loaded item data)
  3. Show duplicate modal with appropriate warning if needed
  4. User selects quantity and save/discard option
  5. Show preview of JA IDs that will be created
  6. On confirm: Call duplicate API endpoint
  7. Show success message: "Created {N} duplicates: {first_ja_id} - {last_ja_id}"
  8. Provide link to view duplicated items
- No automatic label printing for duplicates (user prints manually)
- **Files**: `app/static/js/` (new or updated duplicate handler)

**Completion Criteria:**
- Duplicate button accessible from edit form
- Modal provides clear preview and options
- Unsaved changes handling works correctly
- Backend safely creates duplicate items
- Success feedback is clear

---

### Milestone 4: Testing - Unit and E2E Tests (RQBC - 4.1 - 4.3)
**Prefix: RQBC - 4**

**Task 4.1: Update All Existing Tests to Remove Quantity**
- Update unit tests:
  - `tests/unit/test_database.py`: Remove quantity assertions
  - `tests/unit/test_inventory_service.py`: Remove quantity handling
  - `tests/unit/test_mariadb_inventory_service.py`: Remove quantity tests
  - `tests/unit/test_audit_logging.py`: Remove quantity from audit tests
  - `tests/test_database.py`: Remove quantity validations
- Update e2e tests:
  - `tests/e2e/test_server.py`: Remove quantity from test data
  - `tests/e2e/test_search.py`: Remove quantity checks
  - `tests/e2e/test_search_thread.py`: Remove quantity
  - `tests/e2e/test_shorten_items.py`: Remove quantity assertions and update expectations
  - `tests/e2e/test_move_items.py`: Remove quantity
  - `tests/e2e/test_move_items_with_original_thread.py`: Remove quantity
- Ensure all existing tests pass after quantity removal
- **Files**: Multiple test files

**Task 4.2: Add E2E Tests for Bulk Creation**
- Create new test file: `tests/e2e/test_bulk_creation.py`
- Test cases:
  - **Test: Create single item (quantity=1)**: Verify normal behavior
  - **Test: Create multiple items (quantity=5)**: Verify sequential JA IDs
  - **Test: JA ID sequence correctness**: Verify no gaps or duplicates
  - **Test: Field copying**: Verify all fields identical except JA ID and timestamps
  - **Test: Label printing modal appears**: After bulk creation with quantity > 1
  - **Test: Label printing workflow**: Select size and print all labels
  - **Test: Validation limits**: Test min=1, max=100 enforcement
  - **Test: Transaction rollback**: Partial failure doesn't leave partial data
  - **Test: Add & Continue with bulk**: Verify carry-forward works with bulk creation
- Mock label printer responses for testing
- **Files**: `tests/e2e/test_bulk_creation.py`

**Task 4.3: Add E2E Tests for Duplicate Functionality**
- Create new test file: `tests/e2e/test_duplicate_items.py`
- Test cases:
  - **Test: Duplicate button visibility**: Button appears on edit form
  - **Test: Duplicate modal opens**: Modal displays correctly with item info
  - **Test: Duplicate single item**: Create 1 duplicate successfully
  - **Test: Duplicate multiple items**: Create N duplicates with sequential JA IDs
  - **Test: Field copying accuracy**: All fields copied correctly
  - **Test: Photos not duplicated**: Original photos stay with source item only
  - **Test: History not copied**: Duplicates don't have shortening history
  - **Test: Unsaved changes - save option**: Changes saved before duplication
  - **Test: Unsaved changes - discard option**: Changes discarded before duplication
  - **Test: No unsaved changes**: Duplication works without warning
  - **Test: Validation limits**: Test min=1, max=100 enforcement
  - **Test: Transaction safety**: All duplicates created or none
  - **Test: Success feedback**: Clear messaging with JA ID range
- **Files**: `tests/e2e/test_duplicate_items.py`

**Completion Criteria:**
- All existing tests updated and passing
- Comprehensive e2e test coverage for bulk creation (>90% code coverage)
- Comprehensive e2e test coverage for duplicate functionality (>90% code coverage)
- All edge cases and error conditions tested
- Tests follow existing patterns and conventions

---

### Milestone 5: Documentation and Final Validation (RQBC - 5.1 - 5.2)
**Prefix: RQBC - 5**

**Task 5.1: Update All Documentation**
- Update `docs/user-manual.md`:
  - Remove references to quantity field
  - Add section on "Creating Multiple Identical Items"
  - Add section on "Duplicating Existing Items"
  - Add section on "Bulk Label Printing"
  - Include screenshots and examples
- Update `docs/development-testing-guide.md`:
  - Document new bulk creation and duplicate APIs
  - Document database migration process
  - Update data model documentation (remove quantity)
- Update `README.md`:
  - Update features list (remove quantity, add bulk creation/duplicate)
  - Update any screenshots showing quantity field
- **Files**: `docs/user-manual.md`, `docs/development-testing-guide.md`, `README.md`

**Task 5.2: Final Testing and Validation**
- Run complete unit test suite: `python -m pytest tests/unit/`
- Run complete e2e test suite with 15-minute timeout: `timeout 900 python -m pytest tests/e2e/ --tb=short`
- Verify all tests pass
- Manual testing checklist:
  - Migration runs successfully on test database
  - Bulk creation works for 1, 5, 50, 100 items
  - Duplicate works from edit form with various quantities
  - Label printing integration works smoothly
  - Unsaved changes detection works correctly
  - All forms and pages render correctly without quantity field
  - CSV/Excel export works without quantity column
  - Search and list views display correctly
- Document any issues found and resolve before completion
- **Files**: N/A (testing and validation)

**Completion Criteria:**
- All documentation updated and accurate
- All tests passing (unit and e2e)
- Manual testing checklist completed
- Feature ready for production use

---

## Technical Architecture

### Database Schema Changes
```sql
-- Migration: Remove quantity column
ALTER TABLE inventory_items DROP COLUMN quantity;

-- Note: Migration first splits items with quantity > 1 before dropping column
```

### New API Endpoints
```
POST /api/items/<ja_id>/duplicate
  Request: {"quantity": int, "save_changes": bool, "updated_fields": {...}}
  Response: {"success": bool, "ja_ids": ["JA000101", ...], "count": int}
```

### Modified API Endpoints
```
POST /inventory/add
  Added parameter: quantity_to_create (int, default: 1, range: 1-100)
  Response (when quantity > 1): {"success": bool, "ja_ids": [...], "count": int}
```

### Files to Create
- `migrations/versions/XXXXX_remove_quantity_split_items.py` - Database migration
- `tests/e2e/test_bulk_creation.py` - E2E tests for bulk creation
- `tests/e2e/test_duplicate_items.py` - E2E tests for duplicate functionality
- `app/static/js/duplicate-handler.js` (optional) - Reusable duplicate component

### Files to Modify (Major Changes)
- `app/database.py` - Remove quantity column and validation
- `app/mariadb_inventory_service.py` - Remove quantity, add `duplicate_item()` method
- `app/main/routes.py` - Update add route, add duplicate endpoint
- `app/templates/inventory/add.html` - Add quantity_to_create field, bulk label modal
- `app/templates/inventory/edit.html` - Add duplicate button and modal
- `app/static/js/inventory-add.js` - Handle bulk creation and label printing
- Multiple test files - Remove quantity assertions and expectations

### Files to Modify (Minor Changes)
- `app/export_schemas.py` - Remove quantity column
- `app/mariadb_storage.py` - Remove quantity handling
- `app/templates/inventory/edit.html` - Remove quantity input
- `app/templates/inventory/shorten.html` - Remove quantity display
- `app/static/js/inventory-list.js` - Remove quantity from detail popover
- `app/static/js/inventory-shorten.js` - Remove quantity display

### Design Decisions

**1. Migration Approach**
- Split items before dropping column (preserve data)
- Add explanatory note to duplicated items
- Transactional to ensure data integrity

**2. Bulk Creation vs Duplicate**
- **Bulk creation**: At item creation time, perfect for new orders
- **Duplicate**: After item exists, perfect for "need more of these"
- Both serve different workflows, both valuable

**3. Label Printing Integration**
- Bulk creation: Automatic modal (user expects to print)
- Duplicate: Manual (user may just be preparing inventory)

**4. Field Copying**
- Copy ALL fields except JA ID (including timestamps adjusted)
- Don't copy photos (storage optimization)
- Don't copy history (duplicates are new items)

**5. Unsaved Changes Handling**
- Detect changes by comparing form values to loaded data
- Give user explicit choice: save or discard
- Prevents accidental loss of work

**6. Transaction Safety**
- All bulk operations in transactions
- All N items created or none (no partial failures)
- Clear error messages if something fails

## Testing Requirements

### Unit Tests
- Database model validation without quantity
- Service layer bulk creation logic
- Service layer duplicate logic
- JA ID sequence generation for bulk operations

### E2E Tests
- Migration validation (split items correctly)
- Bulk creation workflow (add form)
- Duplicate workflow (edit form)
- Label printing integration
- Unsaved changes detection and handling
- Validation and error conditions
- Edge cases (quantity=1, quantity=100, failures)

### Manual Testing
- Migration on copy of production data
- Bulk creation with label printer
- Duplicate with various quantities
- All forms render correctly
- No broken references to quantity field

## Success Criteria

- [ ] Quantity field completely removed from codebase
- [ ] Existing items with quantity > 1 successfully migrated to individual items
- [ ] Users can create multiple identical items via "Quantity to Create" field
- [ ] Users can duplicate existing items via "Duplicate" button
- [ ] Bulk label printing integration works smoothly
- [ ] All fields copied correctly (except JA ID, photos, history)
- [ ] Unsaved changes detection works correctly
- [ ] Transaction safety: All bulk operations atomic
- [ ] All unit tests passing
- [ ] All e2e tests passing (with 15-minute timeout)
- [ ] Comprehensive test coverage for new functionality (>90%)
- [ ] All documentation updated
- [ ] Manual testing checklist completed
- [ ] Feature ready for production use

## Migration Plan for Production

### Pre-Migration
1. Backup database
2. Identify items with quantity > 1 (currently 9 items)
3. Review migration script logic
4. Test migration on copy of production data

### Migration Execution
1. Put application in maintenance mode (optional)
2. Run database migration: `alembic upgrade head`
3. Verify migration log output
4. Check that all items split correctly
5. Verify quantity column dropped
6. Run quick smoke test

### Post-Migration
1. Print new labels for all newly created JA IDs
2. Apply labels to physical items
3. Verify application works correctly
4. Remove maintenance mode
5. Monitor for any issues

### Rollback Plan
- If migration fails: Database transaction will rollback automatically
- If migration succeeds but issues found: Restore from backup (destructive)
- Best practice: Test thoroughly before running in production

## Notes

### Why Remove Quantity Field?
The quantity field seemed useful initially, but conflicts with the core shortening workflow. Since each physical item can be modified independently (shortened, moved, etc.), each needs its own unique identifier. The bulk creation and duplicate features provide better solutions that align with the physical reality of inventory management.

### Why Both Bulk Creation and Duplicate?
These serve different workflows:
- **Bulk creation**: "I'm ordering 10 identical bars from the supplier"
- **Duplicate**: "I have this bar in inventory, I need 5 more just like it"

Both are valuable and complement each other.

### Why No Photo Duplication?
Photos show what the item looks like. Since duplicates are identical, they look the same - one set of photos applies to all copies. This saves storage space and keeps the system simpler.

### Why No History Duplication?
Shortening history represents the lifecycle of a specific physical item. Duplicates are new items with their own future lifecycles. Copying history would be confusing and inaccurate.

## Progress Updates

### ✅ Milestone 1: Database Migration and Quantity Removal - COMPLETED
**Implementation Date**: 2025-12-01

**Completed Tasks:**
- **RQBC - 1.1**: ✅ Removed quantity column from InventoryItem database model
- **RQBC - 1.2**: ✅ Generated and customized Alembic migration with item splitting logic
- **RQBC - 1.3**: ✅ Removed quantity from service layer (MariaDB service and storage)
- **RQBC - 1.4**: ✅ Removed quantity from all forms, templates, and JavaScript
- **RQBC - 1.5**: ✅ Removed quantity from routes and export schemas

**Implementation Details:**
- Created migration `56dc95692b79_remove_quantity_field_and_split_multi_.py`
- Migration splits items with quantity > 1 into individual items with sequential JA IDs
- Migration adds explanatory notes to duplicated items
- Removed quantity field from all code locations (model, services, forms, UI, routes, export)
- Complete logging and summary output during migration
- Downgrade includes warning about irreversibility

**Files Modified:**
- `app/database.py` - Removed quantity column and validation
- `migrations/versions/56dc95692b79_remove_quantity_field_and_split_multi_.py` - Created
- `app/mariadb_inventory_service.py` - Removed quantity handling
- `app/mariadb_storage.py` - Removed quantity from headers and field lists
- `app/templates/inventory/add.html` - Removed quantity input
- `app/templates/inventory/edit.html` - Removed quantity input
- `app/templates/inventory/shorten.html` - Removed quantity display
- `app/static/js/inventory-list.js` - Removed quantity from detail popover
- `app/static/js/inventory-shorten.js` - Removed quantity references
- `app/static/js/inventory-add.js` - Removed quantity from field lists
- `app/main/routes.py` - Removed quantity from serialization and form parsing
- `app/export_schemas.py` - Removed quantity column from export

**Migration Status**: Ready to run (will be applied during deployment)

---

**Feature Status**: 🚧 In Progress - Milestone 1 Complete, Moving to Milestone 2

**Created**: 2025-12-01
**Last Updated**: 2025-12-01
