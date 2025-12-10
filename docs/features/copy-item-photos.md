# Feature: Copy Item Photos

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

Currently, there is no way to copy photos from one inventory item to other items. When duplicating items or creating multiple similar items, photos must be manually re-uploaded for each item. This feature will add the ability to copy photos between items, both manually through the item list interface and automatically during item duplication.

### Current Behavior

**Photo Management:**
- Photos are stored in the `item_photos` table with three sizes: thumbnail, medium, and original
- Each photo is linked to an item via `ja_id`
- The PhotoService (`app/photo_service.py`) handles photo operations
- Items can have multiple photos associated with them

**Item Duplication:**
- When duplicating an item (Edit page → Duplicate button), all item fields are copied except:
  - JA ID (new sequential ID assigned)
  - Photos (not copied - see app/main/routes.py:575)
  - History (new item starts fresh)

**Current Limitation:**
- No mechanism exists to copy photos from one item to another
- When duplicating items, photos must be re-uploaded manually

### Desired Behavior

This feature will add two related capabilities:

#### 1. Manual Photo Copying from Item List (Primary Use Case)

Users will be able to copy photos from one item to one or more other items using a two-step workflow from the item list page (`/inventory`):

**Step 1: Copy Photos**
1. User selects a single item from the list (the source item with photos)
2. User clicks a new Options menu item: "Copy Photos From This Item"
3. UI enters "photo copy mode" showing a visual indicator of which item's photos will be copied
4. The selection is cleared, ready for target selection

**Step 2: Paste Photos**
1. User selects one or more target items from the list (items to receive the photos)
2. User clicks a new Options menu item: "Paste Photos To Selected"
3. System copies all photos from the source item to each selected target item
4. Photos are **appended** to any existing photos on the target items (not replaced)
5. UI exits "photo copy mode" and shows success notification with count of items updated

**Additional Requirements:**
- If the source item has no photos, show an error message when attempting to copy
- If target items are selected but no source is in the clipboard, "Paste Photos" should be disabled
- Users should be able to cancel out of "photo copy mode" (clear the clipboard)
- The photo clipboard should persist across page navigation within the same session
- After pasting, the user should see a summary: "Copied N photos to M items"

#### 2. Automatic Photo Copying During Item Duplication

When duplicating an item or creating multiple items from the Add/Edit pages:

**Single Item Duplication (Edit Page):**
- When using the "Duplicate" button on the edit page, automatically copy all photos from the source item to the new duplicate item
- Show in the success message: "Item duplicated as [JA ID]. N photos copied."

**Bulk Item Creation (Add Page - "Create Multiple" workflow):**
- When creating multiple items, if the source item has photos, automatically copy those photos to all newly created items
- Show in the success message: "Created M items ([JA ID range]). N photos copied to each item."

### Database Schema Refactoring (Foundational Change)

**Current Schema Problem:**
The current `item_photos` table stores photo data (thumbnail_data, medium_data, original_data BLOBs) directly associated with a single `ja_id`. This design is inefficient for photo copying because it would require duplicating potentially large BLOB data every time photos are copied to another item, resulting in significant storage waste.

**Proposed Solution:**
Refactor the schema to separate photo storage from item-photo associations using a many-to-many relationship pattern:

**New `photos` Table (stores actual photo data once):**
```sql
CREATE TABLE photos (
    id INT PRIMARY KEY AUTO_INCREMENT,
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_size INT NOT NULL,
    thumbnail_data MEDIUMBLOB NOT NULL,
    medium_data MEDIUMBLOB NOT NULL,
    original_data MEDIUMBLOB NOT NULL,
    sha256_hash VARCHAR(64) NULL,  -- Optional: for deduplication
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT ck_photo_positive_file_size CHECK (file_size > 0),
    CONSTRAINT ck_photo_valid_content_type CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp', 'application/pdf')),
    INDEX idx_sha256_hash (sha256_hash)
);
```

**New `item_photo_associations` Table (many-to-many relationships):**
```sql
CREATE TABLE item_photo_associations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    ja_id VARCHAR(10) NOT NULL,
    photo_id INT NOT NULL,
    display_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    CONSTRAINT ck_assoc_valid_ja_id CHECK (ja_id REGEXP '^JA[0-9]{6}$'),
    FOREIGN KEY (photo_id) REFERENCES photos(id) ON DELETE CASCADE,
    INDEX idx_ja_id (ja_id),
    INDEX idx_photo_id (photo_id),
    INDEX idx_ja_id_order (ja_id, display_order),
    UNIQUE KEY uk_ja_photo_order (ja_id, photo_id, display_order)
);
```

**Benefits of This Architecture:**
- **Storage Efficiency:** Photo data stored once, referenced by multiple items
- **Fast Copy Operations:** Copying photos = creating new association rows (no BLOB duplication)
- **Orphan Photo Cleanup:** Can identify and clean up photos with no associations
- **Optional Deduplication:** sha256_hash enables detecting duplicate photo uploads
- **Display Order:** Supports ordering photos consistently across items that share them

**Migration Strategy:**
1. Create new `photos` and `item_photo_associations` tables
2. Migrate existing data from `item_photos` to new schema:
   - Insert each photo into `photos` table
   - Create corresponding association in `item_photo_associations`
   - Preserve display order based on original `created_at` timestamps
3. Verify data integrity (all associations point to valid photos)
4. Drop old `item_photos` table after successful migration
5. Update all code to use new schema

### Technical Requirements

1. **Database Migration:**
   - Create Alembic migration for schema changes
   - Implement data migration with transaction safety
   - Add rollback capability in case of migration failure
   - Verify zero data loss during migration
   - Performance consideration: migration may take time with many photos

2. **Backend API Endpoints:**
   - New endpoint: `POST /api/photos/copy`
     - Request: `{ "source_ja_id": "JA000123", "target_ja_ids": ["JA000456", "JA000789"] }`
     - Response: `{ "success": true, "photos_copied": 3, "items_updated": 2, "details": [...] }`
   - Endpoint should handle copying photos to multiple targets efficiently
   - Should handle errors gracefully (source item not found, target item not found, no photos to copy, etc.)

3. **PhotoService Updates:**
   - **Refactor all methods** to work with new `photos` and `item_photo_associations` tables
   - Add `copy_photos(source_ja_id, target_ja_id)` method:
     - Creates new association records (does NOT duplicate photo data)
     - Preserves display order from source item
     - Returns count of associations created
   - Update `upload_photo()` to check for duplicate photos via sha256_hash (optional optimization)
   - Update `get_photos(ja_id)` to join associations with photos table
   - Update `delete_photo()` to:
     - Delete association record
     - Delete photo from `photos` table ONLY if no other associations exist
   - Add `cleanup_orphaned_photos()` utility method for maintenance

4. **Frontend State Management:**
   - Add "photo clipboard" to track the source JA ID in session/localStorage
   - Update Options dropdown to show/hide "Copy Photos" and "Paste Photos" based on context
   - Visual indicator when in "photo copy mode" (e.g., banner showing "Photos from JA000123 ready to paste")

5. **Item List UI Changes:**
   - Add "Copy Photos From This Item" to Options dropdown (enabled when exactly 1 item selected)
   - Add "Paste Photos To Selected" to Options dropdown (enabled when items selected AND photo clipboard has source)
   - Add "Clear Photo Clipboard" option (enabled when photo clipboard has source)
   - Visual feedback for photo copy mode

6. **Duplication Logic Updates:**
   - Update `duplicate_item()` route (app/main/routes.py:~575) to call PhotoService to copy photos
   - Update bulk creation logic to copy photos when creating multiple items
   - Update success messages to indicate photo copying occurred

7. **Audit Logging:**
   - Log photo copy operations to audit log
   - Record: timestamp, source JA ID, target JA ID(s), number of photos copied, user (if auth is implemented)

8. **Error Handling:**
   - Source item has no photos → Clear error message
   - Source item doesn't exist → Error message
   - Target item doesn't exist → Skip that target, show warning
   - Photo copy fails for some items → Partial success, show which succeeded/failed
   - Database/storage errors → Rollback and show error

### Test Coverage Requirements

Comprehensive unit and e2e tests must cover:

**Database Schema and Migration:**
- Migration successfully creates new `photos` and `item_photo_associations` tables
- All existing photo data migrated from `item_photos` to new schema without loss
- Verify association records correctly reference photo IDs
- Verify display_order preserved from original created_at timestamps
- Rollback capability works if migration fails
- Old `item_photos` table removed after successful migration

**Storage Efficiency (Critical):**
- **VERIFY NO DATA DUPLICATION:** When copying photos to multiple items, confirm that:
  - Only association records are created (no new rows in `photos` table)
  - BLOB data (thumbnail_data, medium_data, original_data) is NOT duplicated
  - Photo count in `photos` table remains constant when copying
  - Association count in `item_photo_associations` increases by expected amount
- Database storage size doesn't grow proportionally to number of copy operations
- Multiple items can reference the same photo_id

**Manual Photo Copying:**
- Copy photos from item with 1 photo to item with 0 photos
- Copy photos from item with multiple photos to item with 0 photos
- Copy photos from item with photos to item that already has photos (verify append behavior)
- Copy photos to multiple target items at once (1 source → N targets)
- Verify source and target items share the same photo_id references (no duplication)
- Error: Attempt to copy from item with no photos
- Error: Attempt to copy from non-existent item
- Error: Attempt to paste to non-existent item
- UI: Copy/paste workflow in item list
- UI: Photo clipboard visual indicator
- UI: Clear clipboard functionality

**Automatic Photo Copying During Duplication:**
- Duplicate item with 0 photos → new item has 0 photos
- Duplicate item with 1 photo → new item has 1 photo (shares photo_id, no BLOB duplication)
- Duplicate item with multiple photos → new item has all photos (shares photo_ids)
- Create multiple items from source with photos → all new items reference same photos
- Verify `photos` table row count unchanged after duplication operations

**Photo Deletion (Important with Shared Photos):**
- Delete photo from item that is the only one referencing it → photo removed from `photos` table
- Delete photo from item when other items also reference it → association deleted, photo retained
- Verify orphaned photo cleanup works correctly

**PhotoService:**
- Unit test: `copy_photos()` creates association records only (no BLOB duplication)
- Unit test: Copied associations reference correct photo_id
- Unit test: `delete_photo()` properly handles reference counting
- Unit test: `cleanup_orphaned_photos()` identifies and removes unreferenced photos
- Unit test: Display order preserved when copying
- Unit test: Error handling for invalid ja_ids
- Unit test: Optional sha256_hash deduplication on upload

### Example Workflow

**Scenario:** User has just created 5 new metal rod items (JA000550-JA000554) and wants to copy the photos from an existing similar item (JA000123):

1. Navigate to `/inventory` (item list page)
2. Search/filter to find item JA000123
3. Select JA000123 (checkbox)
4. Click Options → "Copy Photos From This Item"
   - UI shows banner: "📋 3 photos from JA000123 ready to paste. Select target items and click 'Paste Photos To Selected'."
   - Selection cleared
5. Filter/search for the new items JA000550-JA000554
6. Select all 5 items (checkboxes)
7. Click Options → "Paste Photos To Selected"
8. System copies 3 photos to each of the 5 items
9. Success message: "✓ Copied 3 photos to 5 items (JA000550, JA000551, JA000552, JA000553, JA000554)"
10. Photo clipboard cleared, UI returns to normal mode

**What Happens Under the Hood:**
- JA000123 has 3 associations: (JA000123, photo_id: 101), (JA000123, photo_id: 102), (JA000123, photo_id: 103)
- After paste operation, 15 new association records created (3 photos × 5 items):
  - JA000550 → photo_ids: 101, 102, 103
  - JA000551 → photo_ids: 101, 102, 103
  - JA000552 → photo_ids: 101, 102, 103
  - JA000553 → photo_ids: 101, 102, 103
  - JA000554 → photo_ids: 101, 102, 103
- **Zero BLOB duplication:** The `photos` table still has only 3 rows (101, 102, 103)
- **Storage saved:** ~15MB of photo data NOT duplicated (assuming ~1MB per photo × 3 photos × 5 duplicate copies avoided)

## Implementation Plan

The feature is broken down into 8 milestones, each requiring human approval before proceeding to the next:

### Milestone 1: Database Schema Refactoring & Migration
**Prefix: `Copy Item Photos - M1`**

- **M1.1**: Create Alembic migration (new tables: `photos`, `item_photo_associations`, data migration, verification, drop old table)
- **M1.2**: Update database models (create `Photo` and `ItemPhotoAssociation` classes in `app/database.py`)
- **M1.3**: Run migration and verify (test migration, verify data integrity, run full test suites)

### Milestone 2: PhotoService Refactoring
**Prefix: `Copy Item Photos - M2`**

- **M2.1**: Refactor core PhotoService methods for new schema
- **M2.2**: Add `copy_photos(source_ja_id, target_ja_id)` method
- **M2.3**: Update PhotoService unit tests

### Milestone 3: Automatic Photo Copying During Duplication
**Prefix: `Copy Item Photos - M3`**

- **M3.1**: Update duplicate item endpoint to copy photos automatically
- **M3.2**: Add E2E tests for duplication with photos

### Milestone 4: Backend API for Manual Photo Copying
**Prefix: `Copy Item Photos - M4`**

- **M4.1**: Create `POST /api/photos/copy` endpoint
- **M4.2**: Add unit tests for API endpoint

### Milestone 5: Frontend Photo Clipboard State Management
**Prefix: `Copy Item Photos - M5`**

- **M5.1**: Implement photo clipboard in JavaScript
- **M5.2**: Add visual indicator banner
- **M5.3**: Update CSS/styling

### Milestone 6: Frontend Options Dropdown Integration
**Prefix: `Copy Item Photos - M6`**

- **M6.1**: Add Options menu items (Copy/Paste/Clear)
- **M6.2**: Wire up event handlers
- **M6.3**: Add toast notifications

### Milestone 7: E2E Tests & Final Validation
**Prefix: `Copy Item Photos - M7`**

- **M7.1**: Create E2E tests for manual photo copying
- **M7.2**: Update existing E2E tests
- **M7.3**: Run complete test suites

### Milestone 8: Documentation & Final Polish
**Prefix: `Copy Item Photos - M8`**

- **M8.1**: Update user documentation
- **M8.2**: Update technical documentation
- **M8.3**: Update feature documentation
- **M8.4**: Final testing & validation

**Dependencies**: M1 → M2 → M3 (sequential); M1 → M2 → M4 → M5 → M6 (sequential); M7 depends on M3 and M6; M8 depends on M7

**Implementation Notes**:
- Photo copying only applies to the duplicate endpoint (which supports quantity > 1)
- The "Create Multiple" workflow creates brand new items (no source to copy from)
- SHA256 deduplication column included in schema but implementation deferred as optional

## Progress

### Completed Milestones

**✅ Milestone 1: Database Schema Refactoring & Migration** (Complete)
- M1.1: ✅ Created Alembic migration for schema refactoring
- M1.2: ✅ Updated database models (Photo and ItemPhotoAssociation)
- M1.3: ✅ Ran migration successfully - 34 photos migrated, data integrity verified

**✅ Milestone 2: PhotoService Refactoring** (Complete)
- M2.1: ✅ Refactored all core PhotoService methods for new schema
- M2.2: ✅ Added `copy_photos(source_ja_id, target_ja_id)` method
- M2.3: ✅ Updated PhotoService unit tests (152/152 passing)

**✅ Milestone 3: Automatic Photo Copying During Duplication** (Complete)
- M3.1: ✅ Updated duplicate_item endpoint to automatically copy photos after each duplicate
- M3.2: ✅ Added comprehensive E2E tests for photo duplication (all pass in isolation)
- Photos automatically copied during both single and bulk duplication
- Success messages updated to include photo counts
- **Verified**: BLOB data NOT duplicated - only association records created
- Fixed audit logging to use correct parameter name (form_data)

**✅ Milestone 4: Backend API for Manual Photo Copying** (Complete)
- M4.1: ✅ Created POST /api/photos/copy endpoint with full error handling
- M4.2: ✅ Added 9 comprehensive unit tests for API endpoint (all passing)
- Endpoint supports copying from 1 source to multiple targets
- Returns appropriate status codes: 200 (success), 207 (partial), 400 (bad request), 500 (error)
- Validates source has photos before attempting copy
- Provides detailed per-item results in response
- Audit logging for all photo copy operations

**✅ Milestone 5: Frontend Photo Clipboard State Management** (Complete)
- M5.1: ✅ Implemented photo clipboard in JavaScript
- M5.2: ✅ Added visual indicator banner with info text and clear button
- M5.3: ✅ Updated CSS/styling with custom banner styling and animations
- Photo clipboard state persists across page navigation via sessionStorage
- Banner shows/hides automatically based on clipboard state
- Methods implemented: loadPhotoClipboard(), savePhotoClipboard(), copyPhotosFromSelected(), pastePhotosToSelected(), clearPhotoClipboard(), updatePhotoClipboardUI()
- UI updates dynamically based on selection and clipboard state

**✅ Milestone 6: Frontend Options Dropdown Integration** (Complete)
- M6.1: ✅ Added Options menu items (completed in M5.2)
  - "Copy Photos From This Item" button added to dropdown
  - "Paste Photos To Selected" button added to dropdown
  - Both start disabled, enabled by JavaScript based on state
- M6.2: ✅ Wired up event handlers (completed in M5.1)
  - Event listeners bound in bindEvents() method
  - copyPhotosBtn → copyPhotosFromSelected()
  - pastePhotosBtn → pastePhotosToSelected()
  - clearPhotoClipboardBtn → clearPhotoClipboard()
- M6.3: ✅ Toast notifications implemented
  - Updated showToast() to support 'warning' type
  - All photo clipboard operations show appropriate notifications
  - Success, error, warning, and info messages implemented

### In Progress

**Milestone 7: E2E Tests & Final Validation** (Next)
- M7.1: Pending - Create E2E tests for manual photo copying
- M7.2: Pending - Update existing E2E tests
- M7.3: Pending - Run complete test suites

### Remaining Milestones

- M7: E2E Tests & Final Validation
- M8: Documentation & Final Polish
