# Feature: Activate Item Bug

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

I am trying to re-activate an item but cannot. If I type the item ID in the search box at the top right of the pages, I just get an "Item not found" error; the same thing happens if I try to manually go to the `/item/edit/JAxxxxxx` URL. If I do a search for inactive items or filter the item list view to inactive items, and then use the "Activate Item" option from the dropdown, nothing seems to happen and in my browser console I see `search:1 Uncaught ReferenceError: toggleItemStatus is not defined`. Furthermore, and only slightly related, if I use the `/inventory/search?active=false` endpoint it returns 58 results for inactive items, but the `/inventory` list with filtering to `Inactive Only` only returns 25 results and shows no indication of any additional results. Please FIRST create e2e tests to reproduce each of these four bugs (these tests should initially be failing, confirming that the tests identify the bugs), commit that work, and then fix the bugs so that the tests pass.

## Implementation Plan

### Bugs Identified

1. **Bug 1**: Cannot edit inactive items via search box - returns "Item not found" error
2. **Bug 2**: Cannot edit inactive items via manual URL (`/inventory/edit/JAxxxxxx`) - returns "Item not found" error
3. **Bug 3**: "Activate Item" dropdown shows `toggleItemStatus is not defined` JavaScript error
4. **Bug 4**: Pagination not visible when filtering to inactive items - only shows 25 of 58 results with no indication of more

### Root Causes

**Bugs 1 & 2**: The `service.get_item(ja_id)` method in `app/mariadb_inventory_service.py` (lines 556-558) only returns active items by calling `get_active_item()` which filters by `active == True` (line 171). The edit route uses this method, preventing access to inactive items.

**Bug 3**: The `toggleItemStatus` function exists in `app/static/js/components/item-actions.js` as an ES6 module export but is not exposed globally. Additionally, the function calls a non-existent API endpoint `/api/inventory/<ja_id>/status`.

**Bug 4**: The pagination container in `app/templates/inventory/list.html` has the `d-none` class by default (line 154), and the InventoryTable component doesn't manage pagination visibility based on filtered results.

### Milestones and Tasks

#### Milestone 1: Create E2E Tests (Failing)
**Prefix**: `Inactive Item Bugs - 1.X`

Create comprehensive e2e tests to reproduce all four bugs:
- `tests/e2e/test_edit_inactive_item_via_search.py` - Tests for bugs 1 & 2
- `tests/e2e/test_toggle_item_status.py` - Tests for bug 3
- `tests/e2e/test_inactive_item_pagination.py` - Tests for bug 4

Commit all failing tests together.

#### Milestone 2: Fix Bugs 1 & 2 - Allow Editing Inactive Items
**Prefix**: `Inactive Item Bugs - 2.X`

Add `get_item_any_status()` method to `MariaDBInventoryService` that retrieves items regardless of active status. Update the edit route to use this method.

**Files to modify**:
- `app/mariadb_inventory_service.py` - Add new method, update `update_item()`
- `app/main/routes.py` - Update edit route to use `get_item_any_status()`
- `tests/unit/test_mariadb_inventory_service.py` - Add unit tests

#### Milestone 3: Fix Bug 3 - toggleItemStatus Not Defined
**Prefix**: `Inactive Item Bugs - 3.X`

Create the missing API endpoint and expose `toggleItemStatus` to global scope.

**Files to modify**:
- `app/main/routes.py` - Add `PATCH /api/inventory/<ja_id>/status` endpoint
- `app/static/js/inventory-list.js` - Import and expose function globally
- `tests/unit/test_routes.py` - Add unit tests for new endpoint

#### Milestone 4: Fix Bug 4 - Pagination Visibility
**Prefix**: `Inactive Item Bugs - 4.X`

Add pagination rendering logic to InventoryTable component.

**Files to modify**:
- `app/static/js/components/inventory-table.js` - Add pagination control methods
- `app/static/js/inventory-list.js` - Remove pagination hiding logic

#### Milestone 5: Final Testing and Documentation
**Prefix**: `Inactive Item Bugs - 5.X`

- Run complete unit and e2e test suites
- Update all relevant documentation
- Update this feature file with implementation summary

### Implementation Status

**Status**: Planning complete, ready to begin Milestone 1
