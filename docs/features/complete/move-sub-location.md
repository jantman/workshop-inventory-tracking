# Feature: Move Sub-Location Support

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

Currently, the move item functionality (both individual and batch moves via `/inventory/move`) only supports updating an item's location field. This feature will extend the move functionality to optionally support sub-location updates as well.

### Current Behavior

When moving items via the move interface (`/inventory/move`):
- The UI accepts only JA ID and Location inputs
- The backend API (`/api/inventory/batch-move`) only updates the `location` field
- Any existing `sub_location` value on an item is left unchanged during a move

### Desired Behavior

After this feature is implemented:

1. **Sub-location Update Support**: The move functionality will support optional sub-location updates in addition to location updates
2. **Sub-location Clearing**: When an item with an existing sub-location is moved to a new location without specifying a sub-location, the sub-location field should be cleared (set to null/blank)
3. **Complete Test Coverage**: Ensure comprehensive test coverage (both unit and e2e) for:
   - Moving items with no sub-location to a location with no sub-location
   - Moving items with no sub-location to a location with a sub-location
   - Moving items with a sub-location to a location with no sub-location (sub-location should be cleared)
   - Moving items with a sub-location to a location with a different sub-location
   - Moving items with a sub-location to a location with the same sub-location

### Input Parsing Rules

The move UI will parse scanned/typed input using the following rules (in order):

1. **JA ID Pattern**: Strings matching `^JA[0-9]+$` are item IDs (JA IDs)
2. **Location Pattern**: Strings matching one of the following are locations:
   - `^M[0-9]+.*` (Metal stock storage locations)
   - `^T[0-9]+.*` (Threaded stock storage locations)
   - The literal string `Other`
3. **Sub-location Pattern**: Any other string not matching the above patterns is treated as a sub-location

**IMPORTANT**: The location pattern validation logic must be implemented in a single, centralized location with clear comments and documentation explaining the pattern rules. This is critical as we may need to add new location patterns in the future (e.g., for new storage area types).

### Examples

Example input sequences and their interpretation:
- `JA000123` → `M1-A` → Item JA000123 moves to location M1-A with no sub-location (any existing sub-location is cleared)
- `JA000123` → `M2-A` → `Drawer 3` → Item JA000123 moves to location M2-A, sub-location "Drawer 3"
- `JA000456` → `T-5` → `Shelf 2` → Item JA000456 moves to location T-5, sub-location "Shelf 2"
- `JA000789` → `Other` → Item JA000789 moves to location "Other" with no sub-location
- `JA000999` → `Other` → `Storage Bin A` → Item JA000999 moves to location "Other", sub-location "Storage Bin A"

### Technical Requirements

1. **Backend Changes**: Update the `/api/inventory/batch-move` endpoint to accept and process optional `new_sub_location` field
2. **Frontend Changes**: Update the move UI and JavaScript to parse, track, and send sub-location data
3. **Location Pattern Validation**: Implement centralized, well-documented location pattern validation
4. **Audit Logging**: Ensure sub-location changes are properly captured in audit logs
5. **Data Integrity**: Ensure sub-location is always cleared when not specified in a move operation
6. **Test Coverage**: Complete unit and e2e test coverage for all scenarios listed above

## Implementation Plan

Based on code exploration, the database and service layer already fully support sub_location fields. The main work involves:
1. Adding location pattern validation logic (centralized and well-documented)
2. Updating the backend API to handle sub-location parameters
3. Updating the frontend to parse, display, and transmit sub-location data
4. Comprehensive testing of all scenarios

### Milestone 1: Backend Infrastructure
**Commit Prefix**: `Move Sub-Location - M1`

**M1.1: Create centralized location pattern validation utility**
- Create new file `app/utils/location_validator.py` with well-documented pattern validation functions
- Implement `is_ja_id(value)` - checks if string matches JA ID pattern `^JA[0-9]+$`
- Implement `is_location(value)` - checks if string matches location patterns:
  - `^M[0-9]+.*` (Metal stock storage)
  - `^T[0-9]+.*` (Threaded stock storage)
  - Exact match: `Other`
- Add comprehensive docstrings explaining each pattern and why it exists
- Add inline comments for future extensibility

**M1.2: Update batch-move API endpoint to accept new_sub_location**
- Update `/api/inventory/batch-move` endpoint in `app/main/routes.py`
- Accept optional `new_sub_location` field in each move object
- Validate that `new_sub_location` is a string or None/null

**M1.3: Implement sub-location clearing logic**
- When `new_sub_location` is not provided in move request, explicitly set `item.sub_location = None`
- When `new_sub_location` is provided, set `item.sub_location = new_sub_location.strip()`
- Ensure service layer `update_item()` properly saves both location and sub_location

**M1.4: Update audit logging for sub-location changes**
- Update input phase logging to include `new_sub_location` in form_data
- Update success phase logging to track sub_location changes separately
- Include sub_location in before/after state dictionaries
- Update batch operation results to show sub_location changes

**M1.5: Add unit tests for backend changes**
- Add unit tests in `tests/unit/test_location_validator.py` for pattern validation
- Add unit tests in `tests/unit/test_routes.py` for batch-move API:
  - Test move with sub-location provided
  - Test move without sub-location (clearing scenario)
  - Test move with empty string sub-location (should clear)
  - Test validation errors
- Verify audit logging captures sub-location changes

### Milestone 2: Frontend Implementation
**Commit Prefix**: `Move Sub-Location - M2`

**M2.1: Implement input parser with location pattern detection**
- Update `app/static/js/inventory-move.js` class `InventoryMoveManager`
- Import/implement location pattern validation (matching backend patterns)
- Update `processInput()` method to parse three-part sequences:
  - JA ID → Location → (optional Sub-location) → next JA ID or DONE
  - JA ID → Location → next JA ID or DONE (no sub-location)
- Store parsed sub-location in queue items

**M2.2: Update move queue data structure**
- Add `newSubLocation` field to queue item objects
- Initialize to `null` when no sub-location provided
- Track whether sub-location was explicitly cleared vs not provided

**M2.3: Update UI to display sub-location**
- Add "New Sub-Location" column to move queue table in `app/templates/inventory/move.html`
- Display current sub-location (from item data) in queue
- Display new sub-location (or "Cleared" if being removed) in queue
- Update queue display methods in JavaScript to show sub-location info

**M2.4: Update API payload**
- Modify `executeMoves()` method to include `new_sub_location` in API request
- Send `null` when sub-location should be cleared
- Send string value when sub-location is being set

**M2.5: Manual testing of UI**
- Test all example scenarios from feature spec
- Verify input parsing works correctly
- Verify UI displays sub-locations properly
- Verify API calls include correct data

### Milestone 3: Test Coverage
**Commit Prefix**: `Move Sub-Location - M3`

**M3.1: Add unit tests for location pattern validation**
- Test JA ID pattern recognition with valid/invalid inputs
- Test location pattern recognition for M*, T*, and Other
- Test edge cases (empty strings, special characters, etc.)

**M3.2: Add E2E tests for sub-location scenarios**
- Create new file `tests/e2e/test_move_items_sub_location.py`
- Test scenario: No sub-location → No sub-location
- Test scenario: No sub-location → With sub-location
- Test scenario: With sub-location → No sub-location (clearing)
- Test scenario: With sub-location → Different sub-location
- Test scenario: With sub-location → Same sub-location
- Test multiple items in batch with mixed scenarios

**M3.3: Run complete test suite**
- Run full unit test suite: `./venv/bin/python -m pytest tests/unit/ --tb=short -v`
- Run full E2E test suite with 15-minute timeout: `timeout 900 python -m pytest tests/e2e/ --tb=short -v`
- Fix any test failures that arise
- Ensure all tests pass before proceeding

### Milestone 4: Documentation
**Commit Prefix**: `Move Sub-Location - M4`

**M4.1: Update user manual**
- Update `docs/user-manual.md` section on moving items
- Document the three-part input sequence (JA ID → Location → Sub-location)
- Add examples showing how to specify or clear sub-locations
- Explain location pattern recognition rules

**M4.2: Update development/testing guide**
- Update `docs/development-testing-guide.md` if needed
- Document location pattern validation utility
- Note testing considerations for sub-location features

**M4.3: Review other documentation**
- Check `README.md` for any necessary updates
- Check `docs/deployment-guide.md` - likely no changes needed
- Check `docs/troubleshooting-guide.md` - add sub-location related issues if applicable

**M4.4: Update feature document**
- Mark feature as complete in this document
- Update Progress section with completion details
- Move document to `docs/features/complete/` directory

## Progress

### Status: ✅ COMPLETED

**Completion Date**: December 14, 2025

### Implementation Summary

All four milestones completed successfully with full test coverage:

#### Milestone 1: Backend Infrastructure ✅
- **M1.1**: Created centralized location pattern validation utility (`app/utils/location_validator.py`)
- **M1.2**: Updated batch-move API endpoint to accept `new_sub_location` parameter
- **M1.3**: Implemented sub-location clearing logic (explicitly sets to None when not provided)
- **M1.4**: Updated audit logging to capture sub-location changes in all phases
- **M1.5**: Added comprehensive unit tests for backend changes

#### Milestone 2: Frontend Implementation ✅
- **M2.1**: Implemented input parser with location pattern detection in `inventory-move.js`
- **M2.2**: Updated move queue data structure to include `newSubLocation` field
- **M2.3**: Updated UI to display sub-location in move queue table with current and new values
- **M2.4**: Updated API payload to include `new_sub_location` in batch move requests
- **M2.5**: Manual testing completed successfully for all scenarios

#### Milestone 3: Test Coverage ✅
- **M3.1**: Added unit tests for location pattern validation (100% coverage)
- **M3.2**: Added 9 comprehensive E2E tests in `test_move_items_sub_location.py` covering all scenarios
- **M3.3**: Full test suite passing (451 passed, 1 skipped, 0 failed)

#### Milestone 4: Documentation ✅
- **M4.1**: Updated user manual with comprehensive move workflow documentation
- **M4.2**: Reviewed development/testing guide (no updates needed)
- **M4.3**: Reviewed other documentation (README, deployment guide, etc.)
- **M4.4**: Updated this feature document and marking as complete

### Key Decisions Made

1. **Workflow Change (Breaking)**: Implemented Option 2 from the original design - requires explicit finalization with `>>DONE<<` or scanning next JA ID. This provides better control and prevents accidental submissions.

2. **Location Pattern Validation**: Centralized in `app/utils/location_validator.py` for easy future extension (e.g., adding new storage area types).

3. **Sub-location Clearing**: When moving without specifying a sub-location, the existing sub-location is explicitly cleared (set to None). This ensures clean data and prevents orphaned sub-locations.

4. **UI Update Fix**: Fixed a critical bug where the move queue UI wasn't updating when using override parameters during finalization. The fix ensures `updateUI()` is always called to reflect queue changes.

### Test Results

**Final Test Run**: December 14, 2025
- Unit Tests: 203 passed, 1 skipped
- E2E Tests: 248 passed
- **Total: 451 passed, 1 skipped, 0 failed**

### Files Modified

**Backend**:
- `app/utils/location_validator.py` (new)
- `app/main/routes.py`
- `tests/unit/test_location_validator.py` (new)
- `tests/unit/test_routes.py`

**Frontend**:
- `app/static/js/inventory-move.js`
- `app/templates/inventory/move.html`

**Tests**:
- `tests/e2e/test_move_items_sub_location.py` (new)
- `tests/e2e/test_move_items.py` (updated with timing fixes)
- `tests/e2e/test_move_items_with_original_thread.py` (updated with timing fixes)

**Documentation**:
- `docs/user-manual.md` (comprehensive move workflow section added)
- `docs/features/move-sub-location.md` (this file)

### Known Issues

None. All tests passing, feature fully functional.
