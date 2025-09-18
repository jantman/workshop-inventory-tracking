# Feature: Photo Upload

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Requirements

Please implement functionality to upload photos of Items using the following guidance:

* Photos should be able to be uploaded during the Item Add or Item Edit processes. Uploaded photos should also be able to be deleted from these processes (i.e the user should be able to upload two photos and then delete one of them, as part of one add or edit operation).
* Photos should be stored in the database as blobs, using a new table to store them. Assume that photos can be up to approximately 20MB in size.
* Photos should be displayed in the UI as small thumbnails that can be clicked to show them larger/full size (also include a download option); the larger/full size view should be clickable to dismiss it. This photo display functionality should exist in the Add Item and Edit Item views, as well as the Item Details modal.
* Photo display should use a common library, not bespoke code.
* e2e tests should be added for all of the above user interactions, to verify proper functionality.
* Photos should not be required; they are optional and we can assume that in actual usage they will be uploaded for only a small portion of items.

## Additional Requirements (Clarified)

* Maximum 10 photos per item (typically 4 or fewer expected)
* Support JPEG, PNG, WebP, and PDF formats
* Hard-delete photos when removed (no soft-delete needed)
* Use Yet Another React Lightbox (YARL) for photo display
* Implement client-side image compression before upload

## Implementation Plan

### Milestone 1: Database Schema and Backend API
**Commit Prefix:** `Photo Upload - 1.1`, `Photo Upload - 1.2`, etc.

#### Task 1.1: Create Photo Database Schema
- Create `item_photos` table with columns:
  - `id` (primary key)
  - `ja_id` (foreign key to items table, to maintain association when items are shortened)
  - `filename` (original filename)
  - `content_type` (MIME type)
  - `file_size` (bytes)
  - `thumbnail_data` (blob, compressed ~150px)
  - `medium_data` (blob, compressed ~800px) 
  - `original_data` (blob, original up to 20MB)
  - `created_at`, `updated_at` (timestamps)
- Add database migration
- Update database models/entities

#### Task 1.2: Backend Photo Upload API
- Create POST `/api/items/{id}/photos` endpoint for uploading photos (resolve item ID to ja_id)
- Create GET `/api/items/{id}/photos` endpoint for listing photos (resolve item ID to ja_id)
- Create GET `/api/photos/{id}` endpoint for serving photo data (with size parameter)
- Create DELETE `/api/photos/{id}` endpoint for deleting photos
- Implement server-side image processing:
  - Generate thumbnail (150px) and medium (800px) versions
  - Validate file types (JPEG, PNG, WebP, PDF)
  - Enforce 10 photo limit per ja_id
  - Enforce 20MB file size limit

#### Task 1.3: Backend Photo Integration
- Update item retrieval endpoints to include photo count/thumbnails (query by ja_id)
- Add photo cleanup when ja_id is no longer referenced by any items
- Add error handling and validation

### Milestone 2: Frontend Photo Components and Library Integration
**Commit Prefix:** `Photo Upload - 2.1`, `Photo Upload - 2.2`, etc.

#### Task 2.1: Install and Configure Dependencies
- Install `yet-another-react-lightbox` and required plugins
- Install `browser-image-compression` for client-side compression
- Configure TypeScript types if needed

#### Task 2.2: Create Photo Upload Component
- Create reusable `PhotoUpload` component with:
  - Drag & drop file upload area
  - File selection button
  - Client-side compression before upload
  - Upload progress indication
  - File type and size validation
  - Preview of selected files before upload

#### Task 2.3: Create Photo Display Component
- Create reusable `PhotoGallery` component with:
  - Thumbnail grid display
  - YARL lightbox integration for full-size viewing
  - Download functionality
  - Delete functionality (when in edit mode)
  - Support for both images and PDFs

#### Task 2.4: Create Photo Management Component
- Create `PhotoManager` component that combines upload and display:
  - Handles photo state management
  - Coordinates between upload and gallery components
  - Manages API calls for CRUD operations
  - Handles loading states and error messages

### Milestone 3: UI Integration
**Commit Prefix:** `Photo Upload - 3.1`, `Photo Upload - 3.2`, etc.

#### Task 3.1: Integrate with Add Item Form
- Add `PhotoManager` component to Add Item form
- Handle photo upload as part of item creation flow
- Update form validation and submission logic
- Handle temporary photo storage during form completion

#### Task 3.2: Integrate with Edit Item Form
- Add `PhotoManager` component to Edit Item form
- Load existing photos when editing
- Handle photo changes (add/delete) during edit flow
- Update form submission to handle photo changes

#### Task 3.3: Integrate with Item Details Modal
- Add read-only `PhotoGallery` component to Item Details modal
- Display photo thumbnails with view/download functionality
- Handle cases where items have no photos

### Milestone 4: Testing and Documentation
**Commit Prefix:** `Photo Upload - 4.1`, `Photo Upload - 4.2`, etc.

#### Task 4.1: Unit Tests
- Write unit tests for photo upload/compression utilities
- Write unit tests for photo components
- Write unit tests for backend API endpoints
- Write unit tests for database operations

#### Task 4.2: End-to-End Tests
- Test photo upload during item creation
- Test photo upload/deletion during item editing
- Test photo viewing in item details modal
- Test photo lightbox functionality (view/download)
- Test file type validation and error handling
- Test maximum photo limit enforcement

#### Task 4.3: Documentation Updates
- Update `README.md` with photo upload feature information
- Update `docs/development-testing-guide.md` with photo testing procedures
- Update `docs/user-manual.md` with photo upload instructions
- Update `docs/deployment-guide.md` if needed for storage considerations
- Update `docs/troubleshooting-guide.md` with common photo upload issues

## Technical Decisions

- **Photo Library:** Yet Another React Lightbox (YARL) for modern React integration and extensibility
- **Compression:** Client-side compression using `browser-image-compression` to reduce server load
- **Storage Strategy:** Three versions per photo (thumbnail, medium, original) for optimal performance
- **File Support:** JPEG, PNG, WebP, PDF with server-side validation
- **Database:** Store as blobs in dedicated `item_photos` table with foreign key to items

## Status

- [x] Milestone 1: Database Schema and Backend API
  - [x] Task 1.1: Create Photo Database Schema
  - [x] Task 1.2: Backend Photo Upload API  
  - [x] Task 1.3: Backend Photo Integration
- [ ] Milestone 2: Frontend Photo Components and Library Integration  
- [ ] Milestone 3: UI Integration
- [ ] Milestone 4: Testing and Documentation

## Milestone 1 Completion Summary

### Completed Tasks:

**Task 1.1: Create Photo Database Schema**
- ✅ Created `item_photos` table with all required columns (id, ja_id, filename, content_type, file_size, thumbnail_data, medium_data, original_data, timestamps)
- ✅ Added proper constraints for JA ID format, file size validation, and content type validation
- ✅ Added database indexes for performance optimization
- ✅ Created SQLAlchemy `ItemPhoto` model with all necessary properties and methods
- ✅ Successfully executed database migration

**Task 1.2: Backend Photo Upload API**
- ✅ Created comprehensive `PhotoService` class with Pillow-based image processing
- ✅ Implemented server-side image processing (thumbnail ~150px, medium ~800px, original up to 20MB)
- ✅ Added support for JPEG, PNG, WebP, and PDF formats with validation
- ✅ Enforced 10 photo limit per ja_id and 20MB file size limit
- ✅ Created all required API endpoints:
  - `POST /api/items/{id}/photos` - Upload photos 
  - `GET /api/items/{id}/photos` - List photos for item
  - `GET /api/photos/{id}` - Serve photo data with size parameter
  - `GET /api/photos/{id}/download` - Download photos
  - `DELETE /api/photos/{id}` - Delete photos

**Task 1.3: Backend Photo Integration**
- ✅ Updated item retrieval endpoints to include photo count/thumbnails (query by ja_id)
- ✅ Added efficient bulk photo count queries for inventory list performance
- ✅ Implemented photo cleanup functionality for orphaned photos (`/api/admin/photos/cleanup`)
- ✅ Added comprehensive error handling and validation throughout
- ✅ Integrated photo information into existing item detail and inventory list APIs

### Technical Implementation:
- Database table stores photos in three sizes for optimal performance
- Client-side compression will be handled in Milestone 2 frontend development
- All validation constraints are enforced at both application and database levels
- Efficient bulk queries prevent N+1 problems when loading inventory lists
- Comprehensive error handling with proper HTTP status codes
- Photo cleanup prevents orphaned data when items are removed

### Files Modified/Created:
- **Database Migration**: `migrations/versions/649ff0d93d25_add_item_photos_table.py`
- **Database Model**: `app/database.py` (added `ItemPhoto` class)
- **Photo Service**: `app/photo_service.py` (new file - complete photo management service)
- **API Routes**: `app/main/routes.py` (added photo endpoints and integration)
- **Dependencies**: `requirements.txt` (added Pillow>=11.0.0)

### API Endpoints Created:
- `POST /api/items/{ja_id}/photos` - Upload photo for item
- `GET /api/items/{ja_id}/photos` - List all photos for item  
- `GET /api/photos/{photo_id}?size={thumbnail|medium|original}` - Serve photo data
- `GET /api/photos/{photo_id}/download` - Download photo as attachment
- `DELETE /api/photos/{photo_id}` - Delete photo
- `POST /api/admin/photos/cleanup` - Remove orphaned photos

### Integration Points:
- `GET /api/items/{ja_id}` - Now includes photo information
- `GET /api/inventory/list` - Now includes photo counts for each item

## Next Steps for Milestone 2:

When resuming development, the next milestone will focus on frontend components:

1. **Install Dependencies** (`Task 2.1`):
   - Install `yet-another-react-lightbox` and required plugins
   - Install `browser-image-compression` for client-side compression
   - Configure TypeScript types if needed

2. **Create Photo Upload Component** (`Task 2.2`):
   - Drag & drop file upload area
   - File selection button with validation
   - Client-side compression before upload
   - Upload progress indication
   - Preview of selected files

3. **Create Photo Display Component** (`Task 2.3`):
   - Thumbnail grid display using existing API
   - YARL lightbox integration for full-size viewing
   - Download and delete functionality
   - Support for both images and PDFs

4. **Create Photo Management Component** (`Task 2.4`):
   - Combined upload and display functionality
   - State management for photo operations
   - API integration with error handling

### Current Status Notes:
- Backend API is fully functional and tested manually
- Database schema is complete and migrated
- All image processing (thumbnail, medium, original) works correctly
- Photo counts are efficiently integrated into inventory listings
- Validation and error handling are comprehensive
- Ready to begin frontend development in Milestone 2
