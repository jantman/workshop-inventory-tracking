# Feature: Add Channel Item Type

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

Please add `Channel` to the list of valid item types. This must be added both in the backend and frontend. Please add e2e tests to ensure that Channel appears and works everywhere that item types are used, i.e. on the `/inventory` Item List "Type" dropdown, on the `/inventory/search` "Item Type" dropdown, in the Add Item and Edit Item forms, and ensure that items added or edited to have `Channel` type are persisted accordingly in the database and viewed properly.

## Implementation Plan

### Analysis Summary

Based on codebase exploration, item types are centrally defined in `app/models.py` as the `ItemType` enum. All frontend templates use Jinja2 loops (`{% for item_type in ItemType %}`) to dynamically render dropdowns, meaning no frontend code changes are required. Type-shape compatibility rules are defined in `app/taxonomy.py`. The database schema uses `VARCHAR(50)` for the `item_type` column, so no database migration is needed.

**User Decision:** Channel items will be compatible with Rectangular and Square shapes.

### Milestone 1: Implement Channel Item Type

**Commit Prefix:** `Add Channel Type`

#### Task 1.1: Add Channel to ItemType enum
- **File:** `app/models.py` (line ~85)
- **Change:** Add `CHANNEL = "Channel"` to the `ItemType` enum after the existing types
- **Impact:** This will automatically make "Channel" appear in all item type dropdowns across the application due to template loops

#### Task 1.2: Define type-shape compatibility rules
- **File:** `app/taxonomy.py` (after line 68)
- **Change:** Add `TypeShapeCompatibility` definition for Channel type
- **Compatible shapes:** Rectangular, Square
- **Required dimensions:** Define appropriate dimensions for channel types (likely length, width, thickness)
- **Optional dimensions:** Define any optional dimensions (e.g., wall_thickness for structural channels)

#### Task 1.3: Add e2e tests for Channel items
- **File:** `tests/e2e/test_add_item.py` or create new test file
- **New tests to add:**
  - Test adding a new item with Channel type (Rectangular shape)
  - Test adding a new item with Channel type (Square shape)
  - Test editing an existing item to change type to Channel
  - Verify Channel items are saved correctly to database
  - Verify Channel items display correctly in inventory list
  - Verify Channel items can be filtered/searched by type
- **Ensure coverage of all UI locations:** Add Item form, Edit Item form, List view filter, Search filter

#### Task 1.4: Run and verify all tests pass
- **Unit tests:** Run `./venv/bin/python -m pytest tests/unit/ --tb=short -v`
  - Verify model tests pass with new enum value
- **E2E tests:** Run `./venv/bin/python -m pytest tests/e2e/ --tb=short` with 15-minute timeout
  - Existing test `test_all_item_types_available_in_dropdown()` will verify Channel appears in dropdown
  - New Channel-specific tests (from Task 1.3) will verify full functionality
  - All existing tests should still pass
- **Fix any failures:** Address any test failures before proceeding

#### Task 1.5: Update documentation
- Review and update if needed:
  - `README.md` - Update if item types are listed
  - `docs/user-manual.md` - Update item type descriptions if present
  - Any other docs mentioning item types

### Verification Checklist

After implementation, verify Channel type works in all locations:
- [ ] `/inventory` - Type filter dropdown includes "Channel"
- [ ] `/inventory` - Can filter to show only Channel items
- [ ] `/inventory/add` - Type dropdown includes "Channel"
- [ ] `/inventory/add` - Can create items with Channel type
- [ ] `/inventory/edit/<id>` - Type dropdown includes "Channel"
- [ ] `/inventory/edit/<id>` - Can edit items to Channel type
- [ ] `/inventory/search` - Item Type dropdown includes "Channel"
- [ ] `/inventory/search` - Can search for Channel items
- [ ] Database - Channel items persist correctly
- [ ] Display - Channel items display correctly in tables/lists

## Implementation Progress

**Status:** Planning complete, awaiting approval to begin implementation

### Milestone 1: Implement Channel Item Type
- [ ] Task 1.1: Add Channel to ItemType enum
- [ ] Task 1.2: Define type-shape compatibility rules
- [ ] Task 1.3: Add e2e tests for Channel items
- [ ] Task 1.4: Run and verify all tests pass
- [ ] Task 1.5: Update documentation
