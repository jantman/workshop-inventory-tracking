# Feature: Inactive Item List

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

Inactive items are not showing up on the `/inventory` endpoint all items list, even if the "Status" dropdown is changed to "Inactive Only" or "All Items". First, add end-to-end tests to confirm this bug (should initially be failing). Then, fix the bug such that the new e2e regression tests pass and all existing tests also pass. Ensure that the "Active Only" status dropdown option remains the default and only shows active items in the list.

## Problem Analysis

### Root Cause
The inventory list page has a status filter dropdown in the frontend (`app/templates/inventory/list.html:30-35`) with three options: "All Items", "Active Only" (default), and "Inactive Only". The frontend JavaScript (`app/static/js/inventory-list.js:182-212`) implements filtering logic for these options.

However, the backend API endpoint `/api/inventory/list` (`app/main/routes.py:1456-1512`) always returns only active items because:
1. It calls `service.get_all_items()`
2. This method is overridden in `app/mariadb_inventory_service.py:560-562` to call `get_all_active_items()`
3. `get_all_active_items()` filters to `InventoryItem.active == True` only

This means inactive items are never sent to the frontend, making the "Inactive Only" and "All Items" filter options non-functional.

### Current State
- ✓ Frontend UI has status filter dropdown
- ✓ Frontend JavaScript has filtering logic implemented
- ✓ Item model has `active` boolean field
- ✗ Backend API endpoint doesn't support status filtering
- ✗ Backend service method hardcoded to return active items only
- ✗ No e2e tests for status filter in inventory list view

### Similar Working Implementation
The Advanced Search feature (`api_advanced_search` in `app/main/routes.py`) uses `search_active_items()` which properly supports filtering by active status. We can use this as a reference for the fix.

## Implementation Plan

### Milestone 1: Add E2E Tests to Confirm Bug
**Commit Prefix:** `Inactive Item List - 1.{task_number}`

**Tasks:**
1. Add e2e test for "Active Only" status filter (should pass - this already works)
2. Add e2e test for "Inactive Only" status filter (should fail - this is the bug)
3. Add e2e test for "All Items" status filter (should fail - this is the bug)
4. Verify the tests fail as expected for inactive items

**Implementation Details:**
- Create new test file `tests/e2e/test_list_view_status_filter.py`
- Set up test fixtures with both active and inactive items
- Test each filter option and verify correct items are displayed
- Ensure "Active Only" remains the default selection

### Milestone 2: Fix Backend to Support Status Filtering
**Commit Prefix:** `Inactive Item List - 2.{task_number}`

**Tasks:**
1. Modify `/api/inventory/list` endpoint to accept a `status` query parameter
2. Update service layer to support filtering by active/inactive/all status
3. Ensure "Active Only" remains the default when no parameter is provided
4. Run all tests (unit + e2e) and verify they pass
5. Update relevant documentation if needed

**Implementation Details:**
- Modify `app/main/routes.py` `/api/inventory/list` endpoint to:
  - Accept optional `status` query parameter (values: "active", "inactive", "all")
  - Default to "active" when not provided
  - Call appropriate service method based on status parameter
- Update `app/mariadb_inventory_service.py`:
  - Add new method or modify existing to support status filtering
  - Follow pattern from `search_active_items()` which already supports this
- Frontend already sends the filter value, so no frontend changes should be needed
- Run complete test suite including e2e tests (with 15+ minute timeout)
- Update documentation if API changes are significant

## Progress

### Milestone 1: COMPLETE ✅
- ✅ Task 1.1-1.3: Added comprehensive e2e tests for status filter in `tests/e2e/test_list_view_status_filter.py`
- ✅ Task 1.4: Ran tests - confirmed 2 tests fail as expected (inactive and all items filters), 2 tests pass (active only and default)

Tests confirm the bug: Backend API only returns active items regardless of filter selection.

### Milestone 2: In Progress
Currently working on backend fixes to support status filtering.
