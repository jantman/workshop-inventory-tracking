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

*This section will be completed during the planning phase.*

## Progress

*This section will be updated as milestones and tasks are completed.*
