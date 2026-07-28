# Workshop Inventory Tracking - User Manual

## Table of Contents
1. [Getting Started](#getting-started)
2. [Overview](#overview)
3. [Adding New Inventory](#adding-new-inventory)
4. [Label Printing](#label-printing)
5. [Managing Existing Inventory](#managing-existing-inventory)
   - [Photo Management](#photo-management)
6. [Advanced Search](#advanced-search)
7. [Batch Operations](#batch-operations)
8. [Products and Catalog](#products-and-catalog)
9. [Data Export](#data-export)
10. [REST API](#rest-api)
11. [Help and Utilities](#help-and-utilities)
12. [Tips and Best Practices](#tips-and-best-practices)
13. [Troubleshooting](#troubleshooting)

## Getting Started

### System Requirements
- Modern web browser (Chrome, Firefox, Safari, Edge)
- Internet connection for database access
- Barcode scanner (optional, keyboard wedge type recommended)

### First Time Setup
1. Open your web browser and navigate to the application URL
2. The application will automatically connect to the database
3. For data export functionality, ensure Google Sheets credentials are configured (optional)

### Main Navigation
- **Home** - Dashboard with application overview and quick actions
- **Add Item** - Add new inventory items
- **Search** - Advanced search and filtering
- **Inventory List** - View and manage all inventory
- **Move Items** - Batch move operations
- **Shorten Items** - Cut materials to length
- **Products** - Catalog menu with three entries: **Add Product**
  (`/products/add`), **Manage Categories** (`/products/categories`) and
  **Browse Tags** (`/products/tags`). See
  [Products and Catalog](#products-and-catalog).
- **Scan barcode** - A scan field sitting in the navbar of every page. Scan or
  type a barcode and press Enter, and the system takes you wherever that scan
  belongs. See [Scanning](#scanning).

## Overview

The Workshop Inventory Tracking system helps you manage metal stock, hardware, and other workshop materials. The system tracks:

- **Physical Properties**: Length, width, thickness, weight
- **Material Information**: Type, shape, material composition
- **Threading Details**: Series, handedness, size, form
- **Location Tracking**: Current location and sub-location
- **Purchase Information**: Date, price, vendor details
- **Status**: Active/inactive status for each item

## Adding New Inventory

### Using the Add Item Form

![Add Item Form](images/screenshots/user-manual/add_item_form.png)
*Add item interface showing all available fields for tracking materials*

1. **Navigate**: Click "Add Item"
2. **Required Fields** (marked with *):
   - **JA ID**: Unique identifier (e.g., "JA12345")
   - **Type**: Rod, Tube, Sheet, Hardware, etc.
   - **Shape**: Round, Square, Rectangular, etc.
   - **Material**: Steel, Aluminum, Brass, etc.

3. **Dimensions**: Enter measurements in inches
   - Length, width, thickness (as applicable)
   - Use fractions (e.g., "1 1/8") or decimals (e.g., "1.125")
   - Wall thickness for tubes

4. **Threading** (if applicable):
   - Series: UNC, UNF, M (metric), NPT, etc.
   - Handedness: Right or Left
   - Size: e.g., "1/4-20", "M10x1.5", "3/4-16"
   - Form: UN, ISO Metric, Acme, Trapezoidal, etc.

5. **Location Information**:
   - Location: Main storage area
   - Sub-Location: Specific bin, shelf, or section

6. **Purchase Details** (optional):
   - Purchase date, price, location
   - Vendor and part number

7. **Notes**: Additional information or special handling requirements

### Barcode Scanning
- **JA ID Field**: Scan barcode to automatically fill
- **Location Field**: Scan location barcode for consistency
- **Submit Code**: Scan ">>DONE<<" barcode to submit form

### Form Features
- **Auto-complete**: Previous entries suggest values as you type. The
  Thread Size, Purchase Location, Vendor, Location, and Sub-Location
  fields show database-backed suggestions in a dropdown when focused
  or typed into. Sub-Location suggestions are scoped to the currently
  entered Location. Material has its own taxonomy-backed selector.
  Programmatic clients can pull the same lists via the
  [`/api/inventory/field-suggestions/<field>`](#get-apiinventoryfield-suggestionsfield)
  endpoint.
- **Auto-save**: Form data is preserved if page refreshes
- **Validation**: Real-time feedback on field formats

### Streamlined Data Entry

#### Bulk Creation ("Quantity to Create")

![Bulk Creation Preview](images/screenshots/user-manual/bulk_creation_preview.png)
*Bulk creation preview showing sequential JA IDs that will be created*

The **Quantity to Create** field allows you to create multiple identical items with sequential JA IDs in a single form submission. This is ideal when you have multiple pieces of the same material that need individual tracking.

**How to use:**
1. Fill out the add item form completely with all item details
2. Set **Quantity to Create** to the number of items you want (1-100)
   - Default is 1 (single item)
   - For multiple items, a preview shows the JA ID range that will be created
3. Submit the form
4. For bulk creation (quantity > 1):
   - A modal appears showing all created JA IDs
   - You can print labels for all items from the modal
   - All items are identical except for their unique JA IDs

**What gets copied:**
- ALL fields: type, shape, material, dimensions, location, notes, vendor info, etc.
- Sequential JA IDs are automatically assigned starting from the next available number

**What doesn't get copied:**
- History (each item is a fresh record)

**Note:** Photos are not automatically copied during bulk creation. However, you can manually copy photos after creation using the photo copying feature (see [Photo Management](#photo-management)).

**Example use case:**
You receive 10 identical steel bars from a supplier. Instead of creating 10 separate entries, fill out the form once with all details and set "Quantity to Create" to 10. The system creates JA000001 through JA000010 (or whatever the next available numbers are) with identical specifications.

#### Carry Forward Button
The **Carry Forward** button (located in the top-right header) allows you to copy common field values from the previously added item into the current form. This is useful when adding multiple similar items.

**Fields copied forward:**
- Type, Shape, Material
- Location and Sub-Location
- Dimensions (length, width, thickness, wall thickness, weight)
- Thread Size, Series, and Handedness
- Vendor, Vendor Part Number, Purchase Location, and Purchase Date
- Notes

**Fields NOT copied (remain blank):**
- JA ID (you'll need to enter unique ID)
- Purchase Price
- Photos

**How to use:**
1. Add your first item normally
2. On the next add form, click **Carry Forward** to populate common fields
3. Enter the unique JA ID (and modify any fields as needed for the new item)
4. Submit as normal

#### Add & Continue Button
The **Add & Continue** button (green button next to "Add Item") submits the current item and immediately returns to a fresh add form, streamlining bulk entry workflows.

**How to use:**
1. Fill out the add item form completely
2. Click **Add & Continue** instead of **Add Item**
3. The item is saved and you're returned to a blank add form
4. Repeat for additional items
5. Use **Add Item** (blue button) for your final item to return to the inventory list

**When to use each:**
- **Carry Forward**: Adding multiple similar items (same material, location, etc.)
- **Add & Continue**: Adding multiple different items in sequence
- **Combined approach**: Use Add & Continue, then Carry Forward for maximum efficiency

## Label Printing

The system can print barcode labels for any JA ID using connected label printers. Labels can be printed from the Add Item form, Edit Item form, or in bulk from the Inventory List.

### Accessing Label Printing

#### From Add Item Form
1. Enter a valid JA ID (format: JA######)
2. The printer button (📄) will become enabled next to the JA ID field
3. Click the printer button to open the label printing dialog

#### From Edit Item Form
1. The printer button is always enabled since the JA ID already exists
2. Click the printer button next to the JA ID field
3. The label printing dialog will open

#### From Inventory List (Bulk Printing)
1. Navigate to the Inventory List page
2. Select one or more items using the checkboxes in the leftmost column
   - You can select items individually by clicking their checkboxes
   - Or use the "Select All" option from the Options dropdown to select all visible items
3. Click the "Options" dropdown button in the top-right corner
4. Select "Print Labels" from the dropdown menu
5. The bulk label printing dialog will open showing all selected items

### Using the Label Printing Dialog

1. **Select Label Type**: Choose from available label types:
   - **Sato 1x2**: Standard 1" × 2" labels
   - **Sato 1x2 Flag**: 1" × 2" labels with flag mode (rotated barcodes)
   - **Sato 2x4**: Larger 2" × 4" labels
   - **Sato 2x4 Flag**: 2" × 4" labels with flag mode
   - **Sato 4x6**: Large 4" × 6" labels
   - **Sato 4x6 Flag**: 4" × 6" labels with flag mode

2. **Print Label**: Click "Print Label" to send the job to the printer
3. **Success Confirmation**: A green success message will appear when printing completes
4. **Auto-close**: The dialog automatically closes after successful printing

### Label Type Selection

#### Add Item Form
- Label type selection is **remembered** between uses
- Your last selected label type will be pre-selected the next time you print
- This helps speed up workflows when printing many similar labels

#### Edit Item Form
- Label type selection is **not remembered**
- You must select the label type each time
- This prevents confusion when editing different items

#### Inventory List (Bulk Printing)
- Label type selection is **not remembered** between sessions
- You must select the label type each time you open the bulk printing dialog
- All selected items will be printed with the same label type

### Using the Bulk Label Printing Dialog

When printing labels for multiple items from the Inventory List:

1. **Review Selected Items**: The dialog displays all selected items with their JA IDs
2. **Select Label Type**: Choose the label type to use for all selected items
   - The same label type will be used for all items in the batch
3. **Print All Labels**: Click "Print All Labels" to start the batch printing process
4. **Monitor Progress**: A progress bar shows the printing status
   - Current item being printed
   - Number of items completed
   - Percentage complete
5. **Review Results**: After completion, the dialog shows:
   - Number of labels printed successfully
   - Number of failures (if any)
   - Detailed error messages for any failed prints
6. **Close or Retry**: Click "Done" to close the dialog
   - Your item selection remains unchanged for convenience
   - You can retry printing if needed

**Tips for Bulk Printing:**
- Print labels in batches of similar sizes to ensure label consistency
- Review the selected items list before printing to avoid mistakes
- If some labels fail to print, the dialog will show which ones need to be retried
- The progress bar helps monitor large batch jobs

### Supported Printers

The system supports Sato label printers with the following configurations:
- **sato2**: 1" × 2" label printer
- **sato3**: 2" × 4" label printer  
- **SatoM48Pro2**: 4" × 6" label printer

### Flag Mode Labels

Flag mode creates labels with rotated barcodes at both ends, making them easier to read when wrapped around cylindrical objects like rods or tubes.

### Troubleshooting Label Printing

#### Printer Not Responding
- Verify the printer is powered on and connected
- Check that the correct printer driver is installed
- Ensure the printer name matches the system configuration

#### Label Format Issues
- Verify you selected the correct label type for your printer
- Check that labels are loaded correctly in the printer
- Ensure label size matches the selected type

#### Barcode Scanning Issues
- Use high contrast settings if barcodes appear faint
- Verify label material is compatible with your scanner
- Clean scanner lens if having reading difficulties

## Managing Existing Inventory

![Edit Item Form](images/screenshots/user-manual/edit_item_form.png)
*Edit interface with complete item details, photo management, and history access*

### Viewing Inventory
1. **Inventory List**: View all items with sorting and filtering
2. **Search Results**: View items matching search criteria
3. **Item Details**: Click any item to view complete information

#### Inventory List Filters
The inventory list page provides several filters to help you find items:

- **Status**: Filter by item status
  - **Active Only** (default): Shows only active/available items
  - **Inactive Only**: Shows only inactive/used items
  - **All Items**: Shows both active and inactive items
- **Type**: Filter by item type (Bar, Sheet, Tube, Channel, etc.)
- **Material**: Search/filter by material name
- **Search**: Search across JA ID, location, and notes fields

All filtering happens instantly as you type or change selections. You can also click column headers to sort the results.

### Updating Items
- Edit items directly through the web interface
- Navigate to any item's edit page from inventory list or search results
- All fields can be updated except JA ID (which identifies the item)

### Duplicating Items
The **Duplicate** button on the edit page allows you to create copies of existing items with new sequential JA IDs. This is useful when you acquire more of the same item.

**How to use:**
1. Navigate to the edit page for the item you want to duplicate
2. Click the **Duplicate Item** button in the page header
3. In the modal that appears:
   - View a summary of the item being duplicated
   - Set the quantity (1-100) of duplicates to create
   - Preview shows the JA ID range that will be created
4. If you have unsaved changes on the edit form:
   - Choose whether to **Save changes** (apply edits to source and duplicates) or **Discard changes** (use original values)
5. Click **Create Duplicates**
6. Success message confirms creation

**What gets duplicated:**
- ALL fields: type, shape, material, dimensions, threading, location, vendor info, notes, etc.
- **Photos**: ALL photos are automatically copied from the source item to each duplicate
- Sequential JA IDs are automatically assigned

**What doesn't get duplicated:**
- History (duplicates have no modification history)
- Timestamps (duplicates get current date/time)

**Photo Copying:** When duplicating items, all photos from the source item are automatically copied to each new duplicate. The system uses efficient storage - photo data is shared between items rather than duplicated, saving storage space.

**Example use case:**
You have an item JA000050 (a 36" steel bar) and acquire 5 more identical bars. Open JA000050's edit page, click Duplicate, set quantity to 5, and create. The system creates JA000051 through JA000055 with identical specifications.

### Photo Management

The system allows you to attach photos to inventory items and copy photos between items. Photos can be automatically copied during item duplication or manually copied between any items.

#### Uploading Photos

![Photo Upload Interface](images/screenshots/user-manual/photo_upload.png)
*Photo upload interface for attaching images to inventory items*

Photos can be uploaded when adding or editing items:
1. Navigate to the Add Item or Edit Item page
2. Scroll to the **Photos** section
3. Click **Choose Files** or drag and drop images
4. Supported formats: JPEG, PNG, WebP, PDF
5. Multiple photos can be uploaded at once
6. Photos are automatically resized to three sizes: thumbnail, medium, and original

#### Viewing Photos

![Photo Gallery](images/screenshots/user-manual/photo_gallery.png)
*Gallery view showing multiple photos attached to an item*

- **Inventory List**: Photo count displayed in the table (e.g., "📷 3" indicates 3 photos)
- **Item Details Modal**: Click any item to view full-size photos in a gallery
- **Edit Page**: View and manage all photos for an item

#### Copying Photos Between Items

There are two ways to copy photos between items:

##### 1. Automatic Photo Copying (During Duplication)

When duplicating items, photos are **automatically copied** to all new duplicates:
- Navigate to the edit page for an item with photos
- Click **Duplicate Item**
- Set the quantity of duplicates to create
- Click **Create Duplicates**
- All photos from the source item are copied to each new duplicate
- Success message shows: "Item duplicated as [JA ID]. N photos copied."

**Storage Efficiency:** The system uses smart storage - photo data is shared between items rather than duplicated, saving disk space.

##### 2. Manual Photo Copying (From Inventory List)

For copying photos between existing items, use the photo clipboard workflow from the Inventory List page:

**Step 1: Copy Photos**
1. Navigate to **Inventory List** (`/inventory`)
2. Select **one item** that has photos (the source item)
   - The "Copy Photos From This Item" option is only enabled when:
     - Exactly one item is selected, AND
     - That item has at least one photo
3. Click **Options** dropdown → **Copy Photos From This Item**
4. A banner appears showing: "📋 N photo(s) from [JA ID] ready to paste. Select target items and click 'Paste Photos'."
5. The selection is automatically cleared, ready for you to select target items

**Step 2: Paste Photos**
1. Select **one or more target items** (items that will receive the photos)
2. Click **Options** dropdown → **Paste Photos To Selected**
3. Confirm the paste operation
4. Photos are **appended** to any existing photos on the target items (not replaced)
5. Success message shows: "Copied N photo(s) to M item(s)"
6. Photo clipboard is automatically cleared

**Additional Options:**
- **Clear Photo Clipboard**: Cancel the copy operation without pasting
- The photo clipboard persists across page navigation within the same browser session

**Example Workflow:**
You just created 5 new metal rod items (JA000550-JA000554) and want to copy photos from an existing similar item (JA000123):
1. Go to Inventory List
2. Find and select item JA000123
3. Click Options → "Copy Photos From This Item"
4. Search/filter for items JA000550-JA000554
5. Select all 5 new items
6. Click Options → "Paste Photos To Selected"
7. Confirm the operation
8. All 3 photos from JA000123 are now on each of the 5 new items

**Photo Copying Rules:**
- Photos are **appended** to existing photos (not replaced)
- If a target item already has 2 photos and you paste 3 photos, it will have 5 photos total
- The display order is preserved from the source item
- Source item's photos remain unchanged
- Storage is efficient - photo data is shared, not duplicated

#### Deleting Photos

To delete a photo from an item:
1. Navigate to the Edit Item page
2. Find the photo in the Photos section
3. Click the **Delete** button next to the photo
4. Confirm the deletion
5. If other items share the same photo, only the association is removed (photo data remains for other items)
6. If no other items use the photo, it is completely removed from the system

### Item Status
- **Active**: Available for use
- **Inactive**: Used up, cut down, or removed

### Parent-Child Relationships & Item History
- When items are shortened, complete history is tracked
- Original item becomes inactive while maintaining full record
- New item references parent item for traceability

#### Viewing Item History

![Item History View](images/screenshots/user-manual/history_view.png)
*History modal showing complete modification timeline for an item*

**Multiple Access Points:**
- **📋 Inventory List**: Clock icon (🕒) in the Actions column of any item
- **🔍 Search Results**: Clock icon (🕒) in the Actions column of search results
- **👁️ Item Details Modal**: "View History" button in modal footer (both list and search views)
- **✏️ Edit Form**: "View History" button in the page header

**History Modal Features:**
- **Timeline Display**: 
  - Most recent changes at the top
  - Visual indicators for active (green) vs inactive (gray) entries
  - Complete dimension changes and modification notes
  - Timestamps for when each version was created/modified
- **Summary Information**: Total versions, active items, and inactive items count
- **Easy Navigation**: Seamlessly transitions between details and history views

#### Technical Details
- **Item History API**: Access complete modification history via `/api/items/{JA_ID}/history`
  - Returns chronological list of all versions of an item
  - Shows active/inactive status for each version
  - Includes dimensions, dates, and modification details
- **Multi-Row Support**: System properly handles multiple database entries per JA ID
  - UI always displays current active item data
  - Historical versions remain accessible via API and History UI
  - Search and filtering only return active items by default

## Advanced Search

### Search Interface

![Advanced Search Form](images/screenshots/user-manual/search_form.png)
*Advanced search interface with range queries, filters, and multiple criteria*

Access via "Search" menu

![Search Results](images/screenshots/user-manual/search_results.png)
*Search results displaying matching items with all relevant details*

### Filter Categories

#### 1. Basic Filters
- **Status**: Active/inactive items
- **Type**: Rod, tube, sheet, hardware, etc.
- **Shape**: Round, square, rectangular, etc.
- **Material**: Hierarchical material search with autocomplete (see below)

#### 2. Dimension Ranges
- **Length**: Min and max values
- **Width**: Min and max values  
- **Thickness**: Min and max values
- **Wall Thickness**: Min and max values
- **Weight**: Min and max values

#### 3. Threading
- **Thread Series**: UNC, UNF, M, NPT, etc.
- **Thread Handedness**: Right/left
- **Thread Size**: Specific size patterns
- **Thread Form**: UN, ISO Metric, Acme, etc.

#### 4. Location
- **Location**: Main storage areas
- **Sub-Location**: Specific locations

#### 5. Purchase Information
- **Purchase Date Range**: Date range filters
- **Vendor**: Specific suppliers
- **Price Range**: Cost filters

#### 6. Text Search
- **Notes**: Search within notes field
- **Vendor Part**: Search part numbers

### Hierarchical Material Search

The material search field features intelligent autocomplete and hierarchical matching:

**Autocomplete Features:**
- **Progressive Disclosure**: Shows top-level material categories when empty
- **Smart Filtering**: Type to filter across all taxonomy levels
- **Navigation Mode**: Browse through categories → families → specific materials
- **Keyboard Support**: Navigate suggestions with arrow keys, select with Enter

**Hierarchical Matching:**
When you search for a material, the system automatically includes all sub-materials in the hierarchy:
- Searching for **"Aluminum"** (category) returns items made of:
  - "Aluminum" (exact match)
  - "6000 Series Aluminum" (family)
  - "6061-T6", "6063-T5" (specific alloys)
  - All other aluminum sub-materials
- Searching for **"6000 Series Aluminum"** (family) returns items made of:
  - "6000 Series Aluminum" (exact match)
  - "6061-T6", "6063-T5", etc. (specific alloys in this family)
- Searching for **"6061-T6"** (specific material) returns:
  - Only items made of "6061-T6" (leaf materials have no children)

This hierarchical search makes it easy to find all items of a general material type without needing to remember every specific alloy or variant.

### Search Tips
- **Multiple Filters**: Combine filters for precise results
- **Range Queries**: Use min/max for dimensions
- **Hierarchical Materials**: Search broad categories to find all variants
- **Export Results**: Download search results as CSV
- **Bookmark Searches**: Save frequently used search URLs

## Batch Operations

![Batch Operations Menu](images/screenshots/user-manual/batch_operations_menu.png)
*Dropdown menu showing available bulk operations for selected items*

### Moving Items

![Move Items Interface](images/screenshots/user-manual/move_items.png)
*Batch move interface for relocating multiple items efficiently*

The Move Items feature allows you to efficiently relocate multiple inventory items in a single batch operation. The system supports moving items to both primary locations and optional sub-locations.

#### Move Workflow

1. **Navigate**: Click "Move Items" in the main menu
2. **Scan Pattern**: Follow this sequence for each item:
   - **Scan JA ID**: Scan or enter the item's barcode (e.g., JA000123)
   - **Scan Location**: Scan or enter the new primary location (e.g., M1-A, T-5, Other)
   - **Scan Sub-Location** (optional): Scan or enter the sub-location (e.g., Bin-3, Shelf-B)
     - Sub-locations can be any text format
     - If no sub-location is needed, skip this step
   - **Next Item or Finalize**:
     - Scan the next item's JA ID to finalize the current move and start a new one
     - OR scan ">>DONE<<" to finalize the current move

3. **Review Queue**:
   - All queued moves appear in the table with item details
   - Each row shows: JA ID, current location, new location, and new sub-location (if specified)
   - Items remain in the queue until you execute the batch

4. **Validate Moves**:
   - Click "Validate & Preview" to check all queued moves
   - System verifies that all JA IDs exist in the database
   - Any issues are highlighted for correction

5. **Execute Moves**:
   - Click "Execute Moves" to apply all changes
   - Confirm the operation when prompted
   - All items are updated simultaneously
   - Success message confirms completion

#### Location Patterns

The system recognizes these location patterns:
- **M-locations**: M1, M2-B, M15-ZZ (materials storage)
- **T-locations**: T1, T-5, T10 (tool/temporary storage)
- **Other**: For non-standard locations
- **Sub-locations**: Any text format for specific bin, shelf, or section

#### Moving Without Sub-Location

When moving an item to a new location without specifying a sub-location, the system **clears any existing sub-location** for that item. This ensures location data stays clean and accurate.

**Example:**
- Item JA000100 is currently at "M1-A / Bin-3"
- You move it to "M2-B" (without specifying sub-location)
- Result: Item is now at "M2-B" with no sub-location (Bin-3 is cleared)

#### Workflow Examples

**Example 1: Simple Move (No Sub-Location)**
```
Scan: JA000100
Scan: M2-B
Scan: >>DONE<<
```
Result: JA000100 moved to M2-B (sub-location cleared if it had one)

**Example 2: Move with Sub-Location**
```
Scan: JA000200
Scan: M3-C
Scan: Shelf-A
Scan: >>DONE<<
```
Result: JA000200 moved to M3-C / Shelf-A

**Example 3: Batch Move Multiple Items**
```
Scan: JA000300
Scan: M4-D
Scan: Bin-1
Scan: JA000301      (this finalizes JA000300's move)
Scan: M4-D
Scan: Bin-2
Scan: JA000302      (this finalizes JA000301's move)
Scan: M5-E
Scan: >>DONE<<      (this finalizes JA000302's move)
```
Result: Three items moved - JA000300 to M4-D/Bin-1, JA000301 to M4-D/Bin-2, JA000302 to M5-E

#### Tips for Efficient Moving

- **Barcode Scanner**: Use a keyboard wedge barcode scanner for fastest data entry
- **Batch Related Items**: Group items going to the same location to minimize scanning
- **Review Before Execute**: Always validate the queue before executing to catch errors
- **Clear Sub-Locations**: When reorganizing, move items without sub-locations first to clear old data
- **Manual Entry Mode**: Check the "Manual Entry Mode" checkbox if you need to type values instead of scanning

### Shortening Items

![Shorten Items Interface](images/screenshots/user-manual/shorten_items.png)
*Interface for cutting materials to length and creating child items*

1. **Navigate**: "Shorten Items" menu
2. **Item Selection**: Enter or scan item JA ID
3. **New Length**: Specify remaining length after cut
4. **New ID**: Assign new JA ID for shortened piece
5. **Automatic**: Original item becomes inactive, new item created

## Products and Catalog

Products are the catalog half of the system, and they are separate from
inventory items. An inventory item is one physical piece of stock with a JA ID;
a **product** is the catalogued thing you buy — its description, manufacturer,
part number, category, tags, purchase history and documents. Creating a product
does not create an inventory item, and nothing in this chapter changes JA IDs.

### What a Product Is

Every product carries the same core fields, shown on the **Product Information**
card of both the add and the edit form:

| Field | Required | Limit |
|-------|----------|-------|
| **Label Description** | Yes | 255 characters |
| **Manufacturer** | No | 255 characters |
| **Manufacturer Part Number (MPN)** | No | 255 characters |
| **Category** | No | 512 characters, counted on the *stored* path |
| **Tags** | No | 64 characters per tag, 50 tags per product |
| **Notes** | No | Free text |

The **Label Description** is what you will recognise the product by; it is also
the heading of the product's own page. Every other field is optional, and a
product with nothing but a description is perfectly valid.

Each product also gets an **Internal ID** when it is created. You do not type
it — the system generates it, it is the value this shop's own product labels are
designed to encode, and it is one of the values the catalog search looks at. It
is *not* shown on the product's own page; the search results table is where you
will see it. A product page may additionally show a **Specifications** card, but
only when the product carries attributes; there is no field for them on either
form.

#### Reaching the Product Pages

The **Products** menu in the navbar has exactly three entries:

- **Add Product** - the create form, at `/products/add`
- **Manage Categories** - the category tree, at `/products/categories`
- **Browse Tags** - the tag vocabulary, at `/products/tags`

There is deliberately no "all products" listing. A product's own page and the
catalog search page are reached by scanning something, by searching, by
following a tag filter, or by going to the URL directly (`/products/<id>`).
**Browse Tags** will list every product carrying a tag. **Manage Categories**
will not do the same for a category — it reports how many products sit at each
path, but there is no page that lists them.

### Adding a Product

1. **Navigate**: **Products** → **Add Product**, or arrive here from a scan
   that matched nothing (see [Scanning](#scanning)).
2. **Fill in Product Information**: **Label Description** is required — it is
   the one field marked `*`; the rest is optional. Leaving it blank is refused
   with `Label Description is required.`, shown under the field.
3. **Category** (optional): start typing, or just click into the empty field —
   either way a dropdown of existing category paths appears. See
   [Categories](#categories).
4. **Tags** (optional): type them separated by commas. The help under the field
   reads "Separate tags with commas. Tags are stored lowercase." See
   [Tags](#tags).
5. **First Receipt** (optional): fill this in if you are cataloguing something
   that just arrived. A **Quantity** or an **Order Number** is what actually
   records the purchase — the other three fields are saved alongside one of
   those and dropped without one. See below.
6. **Submit**: click **Add Product**. **Cancel** abandons the form and returns
   you to the dashboard — not to wherever you came from, and without asking, so
   on a scan-routed form it throws away everything the scan pre-filled.

On success you land on the new product's page and see
`Product created successfully!`. If the write does not land you stay on the
form with `Failed to create product. Please try again.`, or
`An error occurred while creating the product. Please try again.` when the
failure was unexpected — in neither case was a product created.

**Long values are cut off, not refused, in the browser.** **Label Description**,
**Manufacturer** and **MPN** carry their limit on the input itself, so typing
simply stops at the limit — and **a value you paste is silently shortened to
fit, with no warning.** Check anything you paste into those three. The server
enforces the same limits and refuses an over-long value with a message naming
the field and its limit (`MPN must be 255 characters or fewer.`), but because
the input stops you first, those messages come from a scan pre-fill rather than
from anything you typed.

**Category** is the exception: nothing is cut off, and the server has the only
say. Its 512-character limit is on the path as *stored* — after the tidying in
[How a Category Is Stored](#how-a-category-is-stored) — which can come out
shorter or longer than what you typed, so the browser has no way to cut the
value off in the right place. An over-long path is refused beside the field with
`Category path is too long: N characters (max 512).`, where `N` is the stored
length; it need not match what you count on screen.

#### The First Receipt Block

The **First Receipt (optional)** card records the purchase the product arrived
on, so you do not have to create the product and then immediately add a
purchase to it. It has five fields — **Quantity**, **Order Number**, **Vendor**,
**Unit Price** and **Vendor SKU** — and its help text reads "A Quantity or an
Order Number records one purchase, with Vendor, Unit Price and Vendor SKU saved
alongside it. Leave both blank and no purchase is recorded — including when a
scan filled in the Vendor SKU for you. Unit Price is what one item cost: a plain
decimal number, no currency symbol, at most two decimal places."

- Fill in **Quantity** or **Order Number** — either one, or both — and exactly
  one purchase row is recorded. Whatever you put in **Vendor**, **Unit Price**
  and **Vendor SKU** is saved onto that same row.
- Leave **both** of those blank and no purchase is created at all, no matter what
  the other three hold. **Vendor**, **Unit Price** and **Vendor SKU** are saved
  only *alongside* a **Quantity** or an **Order Number**; on their own they are
  dropped silently rather than refused. If you meant to record what arrived, add
  whichever of those two you know.
- There is no order date on this block; the recorded purchase is dated today.
- **A scan may have filled this block for you.** A distributor envelope can put
  its quantity, order number and vendor SKU onto the form — not always, and not
  necessarily all three (see [Scanning](#scanning)). A scanned **Vendor SKU** on
  its own records nothing, and that is the point: a distributor label states its
  own part number whether or not anything arrived, so a scan-and-save used just
  to catalogue a part no longer books a purchase you never entered. A scanned
  **Quantity** or **Order Number** *does* record one — those describe a shipment
  rather than a part — and the rule does not care that the scan, rather than you,
  filled them in. Check the block before saving, and clear it if what the label
  states is not what actually arrived.

**Quantity** must be a whole number greater than zero and no larger than
2147483647; anything else is refused with
`Quantity must be a whole number greater than zero and no more than 2147483647.`

**Unit Price** follows exactly the same rules — and gives exactly the same
messages — as the **Unit Price** on the purchase form; see
[Purchases and Attachments](#purchases-and-attachments). Nothing at all is
created when it is refused: neither the product nor the purchase. It is checked
whether or not it is going to be recorded, so a price the server cannot store is
still refused when **Quantity** and **Order Number** are both blank — even though
a storable one in that same position would simply be dropped. The same goes for
length: an over-long **Vendor** or **Vendor SKU** is refused with its own message
even when there is no **Quantity** or **Order Number** for it to be saved
alongside, so occasionally you must shorten a value the system was going to
discard anyway.

The product is saved before the receipt is written, so the two can come apart.
If that happens the product still exists and you are told so:
`The product was saved, but its first receipt was not recorded. Add the purchase from the product page.`
Use the **Add a purchase** button on the product page to finish the job — do
not re-submit the form, which would create a second product.

#### The Scanned Identifier Card

When you reach the add form from a scan that carried an identifier, the form
grows a **Scanned Identifier** card. It is not shown otherwise.

- **Type \*** is a dropdown, starting with "Select a type…", offering
  `GTIN`, `GTIN_UNVALIDATED`, `ASIN`, `FNSKU`, `MPN` and `VENDOR_SKU`.
- **Value** holds what the scan carried, up to 255 characters.
- **Vendor Scope** is the vendor this identifier belongs to, up to 255
  characters. It is required for `ASIN`, `FNSKU` and `VENDOR_SKU`, which are
  unique *per vendor* rather than across the catalog, and it is ignored for
  every other type. It is **not** the **Vendor** field in the First Receipt
  card below — neither one fills the other in, so two vendors can each carry
  the same `VENDOR_SKU` without colliding.

All three are editable before you save. Pick `GTIN_UNVALIDATED` rather than `GTIN`
when you want to keep a barcode that does not pass its check digit — a value
typed or edited into a `GTIN` is check-digit validated before the product is
created, and the refusal names `GTIN_UNVALIDATED` as the way to keep it anyway.

**A `GTIN` that fails its check digit is refused before anything is saved.**
You get `GTIN check digit is invalid: expected N, got M in '…'. Choose the
GTIN_UNVALIDATED type to keep the value exactly as entered, without check-digit
validation.` on the **Value** field, with the form still filled in as you
submitted it: correct the digit, or change **Type** to `GTIN_UNVALIDATED` and
save again. Nothing was created, so re-submitting is the right move. The same
message shape covers a `GTIN` that is not 8, 12, 13 or 14 digits, or that
contains anything other than plain ASCII digits.

The help text reads "Attached to the product
when you save it. Clear the value to create the product without it." Leaving a
value in place with no type selected is refused with
`Choose the type of the scanned identifier, or clear its value.`; a type the
system does not recognise gets `Choose a valid identifier type.`, and a value
longer than the limit gets `Identifier must be 255 characters or fewer.`
Choosing `ASIN`, `FNSKU` or `VENDOR_SKU` with the **Vendor Scope** box empty is
refused with `VENDOR_SKU identifiers are unique per vendor, so Vendor Scope is
required. It is this identifier's own vendor, not the First Receipt block's
Vendor.` (naming whichever type you chose), and a scope longer than the
limit gets `Vendor Scope must be 255 characters or fewer.` Those five and the
check-digit rule above are all checked before anything is written, so the
product is not created.

An identifier is unique within its scope — across the whole catalog for `GTIN`,
`GTIN_UNVALIDATED` and `MPN`, and per **Vendor Scope** for `ASIN`, `FNSKU` and
`VENDOR_SKU` — so an attach can fail even though the product saved. You are told
plainly:
`The product was saved, but the scanned identifier was not attached: <reason>`
or, when the failure was not a validation refusal,
`The product was saved, but the scanned identifier was not attached. Note the identifier — it must be added by hand once a product can be given one.`

#### Confirming a Duplicate

A scan that matches a product takes you to *that product*, never to this form
(see [Scanning](#scanning)). You reach the create form from there by clicking
**Create a separate product instead** in the arrival banner — and when you do,
the form opens with a warning headed **This scan already matched a product**, a
link to that product, and a checkbox reading
**Yes, create a separate product anyway.**
Nothing is written until you tick it — submitting without it is refused with
`This scan already matched an existing product. Confirm below that you want to create a separate product anyway.`

When the scan carried an identifier, the warning gains one more sentence: "The
scanned identifier stays with that product — an identifier is unique within its
scope, so the same one cannot be attached here as well under the same scope."

A distributor-label scan carries its **Quantity**, **Order Number** and **Vendor
SKU** onto this form too, so the **First Receipt** card can be populated here
before you touch it. The rule is the one described in
[The First Receipt Block](#the-first-receipt-block): a pre-filled **Quantity** or
**Order Number** records a purchase against the *new* product when you save, a
pre-filled **Vendor SKU** on its own records nothing. Check that card before
ticking the confirmation box.

Only a **GTIN** scan carries an identifier onto this form, so only that path
shows a **Scanned Identifier** card here at all — arrive from an internal or
distributor-label banner and there is none. Where the card is present, its help
text changes to say what will actually happen, which depends on the **Type** now
selected. `GTIN` — the type the scan put there — is unique across the whole
catalog, so it reads "This identifier already belongs to the product above, and
outside the vendor-scoped types an identifier is unique across the whole catalog
— saving will report that it could not be attached. Clear the value to create the
product without it." Change the **Type** to `ASIN`, `FNSKU` or `VENDOR_SKU` and it
reads "This identifier already belongs to the product above, and an identifier is
unique within its scope — saving will report that it could not be attached unless
you give it a Vendor Scope that product does not hold it under. Clear the value to
create the product without it."

### Categories

A category is a single `/`-separated path stored on the product — for example
`electronics/power/regulators`. Depth is unlimited; the only limit is 512
characters for the whole path, counted after the tidying below rather than on
what you type. There is no category table and no setup step:
the tree is exactly the set of paths that products are actually filed under, so
it accretes purely from use and shrinks again when the last product leaves a
path.

#### Typing a Category

The **Category** field on the add and edit forms is an autocomplete. Click into
it — even while it is empty — and the first ten existing paths appear in
alphabetical order; keep typing and the list narrows about a fifth of a second
after you stop. Once you have typed something, matches are offered exact first,
then starts-with, then contains, all case-insensitively.

Only paths some product is already filed under are offered. Filing a product at
`a/b/c` makes `a/b/c` offerable, but not the bare `a` on its own.

When what you have typed is not already in the list, the dropdown offers one
extra entry labelled `+ Create "<path>"`, showing the canonical form of what you
typed. **Choosing it creates nothing.** It only writes that canonical string
into the field; the path comes into existence when you save a product carrying
it, and not before.

#### How a Category Is Stored

Whatever you type is canonicalized before it is stored: the path is split on
`/`, each segment is trimmed, empty segments are dropped, the segments are
rejoined with single slashes, and the result is lowercased.

- `Electronics/Power/` is stored and redisplayed as `electronics/power`
- `  /Electronics // Power/DC-DC Converters/ ` becomes
  `electronics/power/dc-dc converters`

Nothing else is rewritten. Spaces inside a segment are kept as typed — there is
no slugging and no hyphenation. A blank field, a bare `/`, or whitespace alone
all mean "no category" and are not an error. The same rule runs on create, on
update and on a category rename, so every path written from these forms is
canonical. Older rows can still hold a non-canonical path; **Manage Categories**
flags those, and they cannot be renamed until their products are re-saved (see
below).

#### Manage Categories

**Products** → **Manage Categories** (`/products/categories`) shows the
**Assigned Category Paths** card: a flat table, not an indented tree, with
columns **Category**, **Filed here**, **In subtree** and **Actions**. Rows are
sorted so children sit beneath their parents, and interior nodes that no product
is filed at directly are listed too (with a **Filed here** count of 0), because
they are real, renameable nodes.

Rows are not clickable. The only action is **Rename**. A legacy row that is not
stored in canonical form shows a **Not canonical** warning badge instead — refile
its products from the product form to clean it up.

With no categories at all the card reads "No categories yet. Categories are
created by typing one on the product form — the tree accretes purely from use."

#### Renaming a Category

1. **Navigate**: **Manage Categories**, then **Rename** on the row you want.
2. **Read the preview**: the **What Will Move** card names the **Category**, the
   number of **Products affected**, and every path at or under it. The note
   underneath reads "Every path listed above moves under the new path, and every
   product filed under them is refiled in one transaction." This preview *is*
   the confirmation step.
3. **Type the destination** into **New Category Path \***. Nothing is cut off as
   you type — the 512-character limit is on the stored path, so only the server
   can judge it. This field deliberately has no autocomplete: the destination
   must not already exist. It is canonicalized exactly as the product form's
   **Category** field is, so you need not type it already-lowercased — the help
   under it reads "Normalized the same way as the product form: lowercase,
   `/`-separated, no leading or trailing slash. The path must not already
   exist."
4. **Submit**: click **Rename Category**, or **Cancel** to back out.

Descendants are matched on segment boundaries, so renaming `thermal/heat` never
catches `thermal/heatgun-parts`. Every descendant keeps its own suffix under the
new root, and all the rows are rewritten in one transaction. On success you are
returned to the listing with
`Renamed category "old" to "new" — N product(s) updated.`

A rename can be refused, and when it is, nothing at all is written:

- `Enter the new category path.` — the destination was left blank.
- `Select a category to rename.` — the submission named no source path. (Note
  the wording: the guard that fires *before* the form is shown says "Pick a
  category to rename." instead.)
- `'x' is already this category's path — nothing to rename.`
- `No products are filed under category 'x'.`
- `Category 'y' already exists and holds N product(s). Rename it or pick another path — merging two branches is not supported.`
- `Cannot rename: product(s) 1, 2 carry a non-canonical category path that overlaps this rename. Fix those products first.`
- `Category path is too long: N characters (max 512).` — normally the
  destination you typed. It names the *source* instead when the category you
  chose to rename is itself unstorable, which only a hand-edited `?path=` or a
  product filed under a non-canonical path can produce; the field marked in red
  tells you which one it is. `N` is the length once stored, so it need not match
  what you typed.
- A path-too-long refusal naming the product whose rewritten path would exceed
  512 characters. Every rewrite is computed before any is applied, so one
  over-length descendant stops the whole rename.
- `An error occurred while renaming the category. Please try again.` — the
  rename did not run at all. On this one the form comes back with **Products
  affected** reading `unknown` and the note "The category could not be read, so
  what would move is unknown," because the preview could not be rebuilt either.

Merging two branches is refused outright. Promoting `a/b` up to `a` is allowed
only while nothing *else* is already filed under `a` — otherwise it is a merge
and is refused like any other. Renaming a path down into a subtree of itself
(`a` → `a/b`) is never a merge — but it lengthens every descendant, so it can
still be stopped by the 512-character limit above.

Three guards fire before the form is even shown, each sending you back to the
listing: `Pick a category to rename.` when no path was given,
`Category "X" is not stored in canonical form, so it cannot be renamed here — refile its products from the product form instead.`
for a legacy row, and `No products are filed under category "X".` when the path
holds nothing.

### Tags

Tags cut across the category tree: a product sits in exactly one category but
can carry up to 50 tags. Like categories, there is no vocabulary to set up — the
vocabulary is the set of tags products actually carry, and a tag vanishes when
the last product drops it.

#### Entering Tags

Tags live in one comma-separated text field. It autocompletes the same way the
category field does, with three differences: only the comma-separated fragment
your cursor is sitting in is looked up, choosing a suggestion replaces just that
fragment, and tags already in the field are left out of the dropdown.

Each tag is normalized before it is stored: trimmed, runs of internal whitespace
collapsed to a single space, and lowercased. `  SSR  Relay ` becomes
`ssr relay`. Blank entries are dropped and duplicates are collapsed once
normalized.

The field is **replace-all**. There is no per-tag chip to remove; what you
submit becomes the product's complete tag set, and clearing the field removes
every tag.

A tag cannot contain a comma, because the comma is the separator — typing
`1,000 lb rated` gives you two tags, not one — the field never reports a comma
as an error, it just splits there. All of the limits are checked before
anything is written:

- `Tag is too long: N characters (max 64).`
- `Too many tags: N (max 50 per product).`
- `The tag field is too long: N characters (max 3600). At most 50 tags of 64 characters each are allowed.`

The database compares tags with accents folded, so `café` and `cafe` collide.
Which message you get depends on where the collision is:

- Between two tags in the list you just submitted:
  `These tags cannot be saved together: the database treats two of 'a', 'b' as the same tag. Remove one of them.`
  A long list is named in part, ending "(and N more)".
- Between a new tag and one the product already carries:
  `Tag 'x' conflicts with 'y', which this product already carries — the database treats them as the same tag.`
- Neither — someone else saved the same tag at the same instant:
  `Another save added 'x' to this product at the same time, so these tags were not written.`
  That one is worth simply submitting again; nothing about your list was wrong.

Tags are written after the product itself, so the two can come apart. If they
do, the product exists and you are told to enter the tags again:
`The product was saved, but its tags were not: <reason> Edit the product and enter its tags again.`
When the problem is one that re-submitting cannot fix, the advice changes to
"… enter different tags." A failure that was not a refusal at all names no
reason: `The product was saved, but its tags were not. Edit the product and enter its tags again.`
In every case nothing kept what you typed — retype the tags on the edit form
rather than just saving again.

#### Browse Tags

**Products** → **Browse Tags** (`/products/tags`) shows the **Assigned Tags**
card with columns **Tag**, **Products** and **Actions**. Every row offers two
actions: **View products**, which takes you to
`/products/tags/filter?tag=<tag>`, and **Rename** (see below). Unlike **Manage
Categories** there is no "not canonical" row here — the tag table is only ever
written through something that normalizes first (the product form, and the
rename below), so every stored tag is already canonical and every row can be
renamed.

The filter page is headed **Tag: `<tag>`** and lists **Tagged Products** with
columns **Description**, **Manufacturer / MPN** and **Category**.

Tags on a product's own page are clickable badges pointing at the same filter.

Empty states say what an empty result actually means: "No tags yet. Tags are
created by typing one on the product form — the vocabulary accretes purely from
use." and "No products are tagged "x". A tag exists only while some product
carries it."

Two guards send you back to the tag list: `Pick a tag to filter by.` when no tag
was given, and "That is not a usable tag, so nothing could carry it. Pick one
from the list." for a tag no product could ever hold.

#### Renaming a Tag

Renaming a tag fixes a typo, or standardizes two spellings, across every product
carrying it at once — without opening a single product form.

1. **Navigate**: **Browse Tags**, then **Rename** on the row you want.
2. **Read the preview**: the **What Will Change** card names the **Tag** and how
   many **Products affected** carry it, over the note "Every product carrying
   this tag is retagged in one transaction. If a product already carries the new
   tag, the two are merged — it keeps one copy of the new tag and loses none of
   its other tags." This preview *is* the confirmation step. It cannot show what
   the *destination* side will look like, because you have not typed the
   destination yet — that is what the merge note is stating instead.
3. **Type the destination** into **New Tag \***. Nothing is cut off as you type
   — the 64-character limit is on the stored tag, and normalization trims what
   you type before measuring it. This field deliberately has no autocomplete:
   an existing tag *is* a legal destination here, so offering the vocabulary
   would invite a merge you never meant. The help under it reads "Normalized the
   same way as the product form: trimmed, internal whitespace collapsed,
   lowercased, no `,`. An existing tag is allowed here — the two are merged."
4. **Submit**: click **Rename Tag**, or **Cancel** to back out.

**Renaming onto an existing tag merges the two.** This is the deliberate
opposite of the category rename, which refuses a merge outright. A product sits
in one category, so folding two branches together would have to throw one away;
a product carries many tags, so the union of two tag sets loses nothing. A
product that already carries the destination simply drops its copy of the old
tag — it ends up with *one* copy of the new one, and every other tag it carries
is left alone.

**A merge cannot be undone by renaming back.** Once `ssr` is merged into
`relay`, nothing records which products arrived that way, so renaming `relay`
back to `ssr` moves every product carrying `relay` — including the ones that
only ever carried it.

On success you are returned to the listing with
`Renamed tag "old" to "new" — N product(s) updated.` When something merged, a
second sentence follows:
`M product(s) already carried "new", so their "old" was merged into it.` The two
counts are reported separately on purpose: a merged product's tag count goes
*down*, so a single total would overstate what the listing then shows. When
*every* carrying product already held the destination, nothing was rewritten at
all and the message says so in one sentence instead:
`Merged tag "old" into "new" — all M product(s) carrying it already carried "new", so their "old" was dropped rather than rewritten.`

A rename can be refused, and nothing at all is written when it is. Where you
land afterwards depends on which of the two values was refused: a refusal that
names the **destination** brings the form straight back with your typed value
intact and that field marked, while a refusal that names the **source** sends
you back to the listing with the message. The source is a hidden field on that
form — there would be nothing on the page to correct, and re-submitting would
reproduce the same refusal forever.

- `Enter the new tag.` — the destination was left blank.
- `Select a tag to rename.` — the submission named no source tag. (Note the
  wording: the guard that fires *before* the form is shown says "Pick a tag to
  rename." instead.)
- `'x' is already this tag — nothing to rename.` — the two normalize to the same
  value, so `ssr` → `SSR` is refused rather than silently doing nothing.
- `No products carry tag 'x'.`
- `Tag is too long: N characters (max 64).` and
  `A tag cannot contain ',' — that is the separator between tags.` — the same
  two rules the product form applies, judged on whichever of the two values you
  gave; if it was the destination, the field marked in red tells you so.
- `The tag to rename contains characters that cannot be stored or matched.` /
  `The new tag contains characters that cannot be stored or matched.` — only a
  hand-edited value can produce this.
- `Cannot rename to 'cafe': product(s) 1, 2 already carry 'café', which the database treats as the same tag. Rename those first, or pick another destination.`
  The database compares tags with accents and case folded (the same rule the
  [Tags](#tags) section describes), so a product carrying *both* spellings
  cannot take this rename — one of the two would have to be discarded, and
  neither is yours to discard. Long lists are named in part and end
  `, ... (N in total)`.
- `Another change added 'x' to one of these products at the same time, so nothing was renamed.`
  Worth simply submitting again; nothing about the rename was wrong. This is the
  one destination refusal that leaves **New Tag** *unmarked* — the value you
  typed was never the problem.
- `An error occurred while renaming the tag. Please try again.` — the rename did
  not run at all. On this one the form comes back with **Products affected**
  reading `unknown` and the note "The tag could not be read, so how many
  products carry it is unknown," because the preview could not be rebuilt
  either.

Three guards fire before the form is even shown, each sending you back to the
listing: `Pick a tag to rename.` when no tag was given, "That is not a usable
tag, so nothing could carry it. Pick one from the list." when the link carried
something no tag could ever be (over-length, or containing a `,` — only a
truncated or hand-edited link produces it), and `No products carry tag "X".`
when nothing carries it.

There is deliberately no way to **delete** a tag from every product at once.
Removing a tag everywhere is destructive in a way a rename is not, and it would
want its own confirmation step; clear tags one product at a time on the product
form instead.

### Finding a Product

There are four ways to a product page: scan it, search for it, follow a tag
filter, or go straight to `/products/<id>`.

#### The Search Page — A Deliberate First Cut

`/products/search?q=…` exists primarily as the landing place for a scan that
did not resolve to one record. It is headed **Search: `<query>`**, offers a
**Create a new product** button, a refine box (**Search products** / **Search**)
and a **Matching Products** card with columns **Internal ID**, **Description**,
**Manufacturer / MPN** and **Category**.

**Create a new product** is not a blank form when a scan brought you here. It
carries the scan's pre-fill onto the add form — the part number, the identifier,
and whatever receipt values the label stated — and the refine box carries them
too, so narrowing the search does not throw them away. That includes
**Quantity** and **Order Number**, which record a purchase when you save it; see
[The First Receipt Block](#the-first-receipt-block).

**Know its limits before you rely on it.** Richer search — filters, facets,
paging and relevance ranking — is future work and is *not* available today:

- **50 rows, hard cap.** There is no paging, no result total and no truncation
  notice, so the page cannot tell you it is showing 50 of 61.
- **Oldest first.** Results come back in the order the products were created,
  which is also the rule deciding which matches survive the cap — so the
  products cut first are the ones added most recently. (This is creation order,
  not the **Internal ID** column: internal IDs are generated randomly and sort
  arbitrarily.)
- **Contiguous substring matching only, case-insensitive.** There is no
  tokenization: `RES 0805` does **not** match a product described
  `RES 10K 0805 1%`. In production the database also folds accents, so `cafe`
  finds `café` — the same folding the [Tags](#tags) section describes.
- **Six columns are searched**: internal id, description, notes, manufacturer,
  MPN, and identifier values. Category path, specifications and tags are **not**
  searched. Notes and identifier values are searched but not shown in the
  results table, so a row can match for a reason you cannot see.

Empty states: "No products match "X". Create one, or search for something else."
for a query with no hits, and "Type something to search the catalog." for a
blank query.

If the search itself cannot run you get the flash
`Search is unavailable right now. The scan was not lost — create the product, or try the search again.`
and the page says "The search did not run, so nothing can be said about what
matches. Try again, or create the product." That wording is deliberate: a failed
search cannot claim the catalog holds nothing.

### Scanning

Every page carries a **Scan barcode** field in the navbar. The only thing that
fires it is pressing Enter while that field has focus — there is no timing
trick, and no prefix or suffix barcode is required. A scan may be up to 4096
characters. An AIM symbology prefix such as `]d1` is tolerated and stripped, but
never required.

#### What Happens to a Scan

The system classifies the scan by five rules, in order:

1. A GS1 element string carrying this system's configured application
   identifier and token — a product label this shop printed — is looked up
   directly by its internal identifier. Both come from configuration and default
   to application identifier `96` with the token `WIT`; a deployment that sets
   `GS1_INTERNAL_AI` or `GS1_INTERNAL_TOKEN` uses those instead. Note that
   **there is as yet no way to print one of these product labels**:
   [Label Printing](#label-printing) covers JA IDs on inventory items, not
   products. The system reads them; nothing here writes them.
2. An ISO/IEC 15434 format-06 envelope (the header `[)>`, a record separator,
   then `06`) is parsed as a distributor ECIA label.
3. A scan that *starts* with a GS1 element string carrying application
   identifier `01` — how a manufacturer encodes a product number on a box, in a
   2D DataMatrix or in a striped GS1-128 alike — has its 14-digit product
   number read out, and that number is then handled by rule 4. Anything the
   barcode carries after the product number (a batch, a date, a serial) is
   ignored, so long as it *starts* like something a GS1 barcode would carry.
   Only the two characters right after the product number are checked: if they
   are digits, the rest is ignored whatever it is, and if they are not, the
   whole scan is refused and searched as free text by rule 5. So a `01`
   barcode followed by ` RES 10K` is searched as text — the space is not the
   start of anything a GS1 barcode carries — while the same barcode followed
   by `17 RES 10K` is read as a product number, because `17` could be the
   start of a date field, and the text after it is dropped. The `01` has to come
   first, too — if the product number is buried behind a batch or a date, the
   system does not go looking for it.
4. An all-digit value of length 8 or 12-14 that passes the GTIN check digit is
   normalized to 14 digits and looked up as a GTIN.
5. Anything else is searched as free text across identifiers, descriptions and
   MPNs.

A GTIN that passes its check digit but matches no product does not dead-end: it
falls through to the free-text search within the same scan. ASIN is *not*
scan-recognized — it exists only as a type you can pick by hand on the
**Scanned Identifier** card — so a scanned ASIN is handled by rule 5. A valid
envelope with nothing readable in it degrades to free text.

Rule 3 is why scanning the manufacturer's own GS1 barcode is treated exactly
like scanning a plain retail barcode: the product number inside it is pulled
out and handled by rule 4, so the same number reaches the same place by either
route. If the number inside that barcode fails its check digit — or is the run
of zeros a scanner emits when it did not really read anything — it falls
through to the free-text search, as the bare number would. One difference to
know about on that fallthrough: what gets searched is what you scanned, so a
scan of the whole GS1 barcode searches for the whole barcode's text — `01`,
product number, batch and all — which is unlikely to match anything. If a
manufacturer's barcode comes back empty-handed, try the printed number beside
it before concluding the product is not in the system.

One thing to watch: the GS1 barcode on an outer carton or a multi-pack often
carries a *different* product number from the retail barcode on the item inside
it — same product, different packaging level, and the packaging level is part
of the number. Scanning the two therefore gets you two records unless you
attach both numbers to one product by hand. Whichever you scan first is the one
the create form fills in.

#### Where a Scan Lands

Those five rules are how a scan is *classified*. What you actually see is one of
three landings, decided by whether anything was found:

1. **A record matched** → the product's own page, carrying a blue banner headed
   **Scanned: this product** whose body reads "The `<kind>` scan matched this
   product." (the kind is `internal`, `ecia` or `gtin`; a free-text scan never
   resolves to a single record, so it never produces this banner). A GTIN scan
   adds the identifier type and value in parentheses after that sentence. The
   banner offers **Add a purchase** and **Create a separate product instead**.
2. **No record, but free-text hits** → the search results page,
   `/products/search?q=…`. Its **Create a new product** button carries the
   scan's pre-fill onward, so the add form reached that way arrives filled in
   just as landing 3 would have filled it — **Quantity** and **Order Number**
   included. The warning under landing 3 applies here too: check the **First
   Receipt** card before saving.
3. **No record and no hits** → the add form, pre-filled. *What* is pre-filled
   depends on the kind of scan, and only some kinds fill **Label Description**:
   - A **GTIN** scan fills the **Scanned Identifier** card, and nothing else.
   - A **distributor envelope naming a part number** fills **Manufacturer Part
     Number (MPN)** and leaves **Label Description** *blank*. Type a description
     of your own: it is the one required field, and the part number is what the
     scan preserved. **Order Number** is filled whenever the label carried one.
     Two are fussier than they look: **Vendor SKU** is filled only when the label
     states a customer part number *different* from the one used for the MPN, and
     **Quantity** only when the label's quantity is a plain whole number — a `0`
     or a scaled `1.5K` is deliberately left blank rather than handed to you as a
     validation error on a field you never typed. Mind that **Quantity** and
     **Order Number** are the two fields that record a purchase when you save
     (see [The First Receipt Block](#the-first-receipt-block)): a label that
     pre-fills either will book one on a form you only meant to catalogue with,
     so clear them if nothing actually arrived. A pre-filled **Vendor SKU** never
     books anything on its own.
   - A **distributor envelope naming no part number** fills whatever else it
     carried *and* drops the raw label text into **Label Description**. "Whatever
     else" includes **Quantity** and **Order Number**, so the same warning
     applies: this form can arrive ready to book a purchase without your having
     typed anything at all.
   - **Anything else** — a shop-printed internal label, free text — goes into
     **Label Description**. Not quite verbatim: control characters become spaces
     and the text is cut to the field's 255 characters, so a very long scan
     arrives shortened. Overtype it with something you will recognise before
     saving.

   No date is ever pre-filled. A distributor label states a `YYWW` week rather
   than a day, so nothing is written into a date field from one.

**A scan never dead-ends** — one of those three always applies.

#### Scan Messages

On success the scan field clears and the browser follows the destination — so
long as you have not moved to another field in the meantime. One case is
entirely silent: if you clear the field or type something unrelated into it
while the scan is still in flight, the answer is discarded with no navigation
and no message. Otherwise anything out of the ordinary raises a short pop-up
message:

| Message | What it means |
|---------|---------------|
| `Previous scan still in progress - rescan this item.` | A second scan arrived while the first was still in flight. |
| `That text was two scans run together and was not sent - scan again. Discarded: <text>` | The field held two runs of scan text; nothing was sent. |
| `Scan timed out - the server may or may not have received it.` | The browser waited ten seconds for an answer and gave up. Check before rescanning. |
| `Scan failed: could not reach the server.` | The scan text is kept in the field for retry. |
| `Scan status unknown - check before rescanning.` | The client could not tell what happened. |
| `Scan accepted. The field now holds two scans run together - scan the next item again.` | The scan was captured, but the field is contaminated. |
| `Scan accepted: <text>. It had no usable destination - find the product from the menu.` | Captured, but with nowhere to go. |
| `Scan accepted: <text>. You had moved to another field, so it was not followed.` | Captured; you had clicked elsewhere, so you were not navigated away. |
| `Scan failed: <reason>` | The server would not resolve the scan. Usually a refusal of the scan itself — an empty one, or one over the 4096-character limit — but a backend fault reads the same way: `Scan failed: Failed to resolve scan` means the database or the scan configuration is broken, not that your barcode was bad. |
| `Scan failed. The scanned text has been kept for retry.` | The server failed with no usable reason. The text stays in the field. |

The four messages that put your text back in the field for retry — the timeout,
`could not reach the server`, `Scan failed: <reason>` and
`Scan failed. The scanned text has been kept for retry.` — may instead end with
`Unrestored scan: <text>`. That means a later scan was already typing into the
field, so the failed text could not be put back; copy it from the message
before rescanning. `Scan status unknown - check before rescanning.` never
touches the field at all, so it neither restores your text nor carries it.

### Purchases and Attachments

A product's page shows a **Purchases** card with **Last paid: $x** in its
header, an **Add a purchase** button, and a table of **Order Date**,
**Vendor**, **Unit Price** and **Received**. With no history it reads "No
purchases recorded."

To record one:

1. Click **Add a purchase** on the product page (or **Add a purchase** in a
   scan arrival banner, which pre-fills what the scanned label carried).
2. Fill in **Purchase Details**: **Vendor**, **Vendor SKU**, **Order Date**
   (`YYYY-MM-DD`, "Defaults to today when left blank."), **Received Date**
   ("Blank means the order is still on its way."), **Quantity**, **Unit
   Price**, **Order Number** and **Source URL**.
3. Click **Record Purchase**. **Cancel** returns to the product.

Both dates must be written `YYYY-MM-DD`; anything else is refused with
`<Field> must be an ISO date (YYYY-MM-DD).` **Unit Price** takes a plain
decimal number — no currency symbol, no thousands separator, not negative, at
most two decimal places, and below 100000000 — each rule having its own message
(`Unit Price must be a decimal number.`, `Unit Price must not be negative.`,
`Unit Price must have at most two decimal places.`,
`Unit Price must be less than 100000000.`).

You get `Purchase recorded.` on success and
`Failed to record the purchase. Please try again.` if the write did not land.

The **Attachments** card lists each file with its type and size in KB and links
it — the link opens the file in a new tab rather than downloading it — and
carries an upload form. With nothing attached it reads "No attachments." Its help
reads "PDF or image (JPEG, PNG, WebP, GIF), up to 16 MB." Uploads report
`Attachment uploaded.`, `No file selected.`,
`Unsupported attachment type: <ct>.`,
`Attachment exceeds the maximum size of 16 MB.`, `Attachment content is empty.`
for a zero-byte file, `Filename is too long (max 255 characters).`, or
`An error occurred while uploading the attachment.` when the failure was
unexpected.

The foot of the page carries the product's **Created** and **Updated**
timestamps.

### Editing a Product

1. **Navigate**: open the product page and click **Edit**.
2. **Change what you need**: the **Edit Product** form carries the same
   six-field **Product Information** card, with the same labels, help text and
   limits as the add form.
3. **Submit**: click **Update Product**, or **Cancel** to return to the product
   page unchanged.

Success flashes `Product updated successfully!`; a failed write flashes
`Failed to update product. Please try again.`, or
`An error occurred while updating the product. Please try again.` when the
failure was unexpected.

One outcome is easy to misread: if the fields save but the tags do not, you are
returned to the product page with **only the tag error and no success message**,
even though every other change was saved. Do not re-submit the form on that
message — the edit landed; only the tags need fixing.

The edit form has no **Scanned Identifier** card, no **First Receipt** block and
no duplicate-confirmation block — those belong to creation only. Clearing a
field clears the stored value, which is how you remove a category or all of a
product's tags. (The form always submits every field, so there is no way to omit
one and have it keep its stored value — that distinction only matters to the
[REST API](#rest-api).)

### Troubleshooting Products

| What you see | What to do |
|--------------|------------|
| `Label Description is required.` | Every product needs a description; it is the only required field. |
| `MPN must be 255 characters or fewer.` (or the same message for another bounded field) | Shorten the value. You will normally meet this on a scan-routed form, since the input itself stops you typing past the limit — and silently shortens anything you paste. |
| `Category path is too long: N characters (max 512).` | Shorten the path. `N` is the length of the path as it would be *stored*, so it need not match what you typed — see [How a Category Is Stored](#how-a-category-is-stored). This field is not capped in the browser, so you can meet it on anything you type or paste. |
| `Quantity must be a whole number greater than zero and no more than 2147483647.` | Enter plain ASCII digits — no signs, separators or decimals. |
| `Unit Price must be a decimal number.` | Type the price as plain digits and at most one point — no currency symbol, no thousands separator. You will see this on the First Receipt block and on the purchase form alike. |
| `Unit Price must not be negative.` | Prices are what you paid, not a credit. Drop the minus sign. |
| `Unit Price must have at most two decimal places.` | Round to cents yourself; the stored column keeps two places and will not round for you. |
| `Unit Price must be less than 100000000.` | The price of **one** item is stored, not the order total, and it must be under 100000000. |
| `The product was saved, but its first receipt was not recorded. Add the purchase from the product page.` | The product exists. Use **Add a purchase** on it; do not re-submit the create form. |
| `The product was saved, but its tags were not: …` | The product exists. Open **Edit** and enter the tags again (or different ones, if the message says so). |
| `GTIN check digit is invalid: … Choose the GTIN_UNVALIDATED type to keep the value exactly as entered, without check-digit validation.` | Nothing was saved. Fix the value, or change **Type** to `GTIN_UNVALIDATED`, and submit again. You will also see this wording for a `GTIN` of the wrong length or one carrying anything but plain ASCII digits. |
| `The product was saved, but the scanned identifier was not attached: …` | A uniqueness clash — the identifier still belongs to the product that already holds it. The product exists and there is no page for attaching an identifier to it, so note the barcode down; do not re-submit the create form. |
| `This scan already matched an existing product. Confirm below that you want to create a separate product anyway.` | Follow the link in the warning first. Only tick the box if you genuinely want a second product. |
| A rename refused because the destination "already exists and holds N product(s)" | Pick a destination path that does not exist yet; merging two branches is not supported. |
| A rename refused because products "carry a non-canonical category path" | Open each named product and re-save its category from the product form, then retry the rename. |
| `Search is unavailable right now. The scan was not lost — create the product, or try the search again.` | The search backend did not answer. The page makes no claim about what exists — retry, or create the product. |
| A search that "misses" something you know exists | The search matches contiguous substrings only, caps at 50 rows oldest-first, and does not look at categories or tags. See [Finding a Product](#finding-a-product). |
| The product you want is not in any menu | There is no product list page. Scan it, search for it, filter by one of its tags, or go to `/products/<id>`. |

## Data Export

The system provides comprehensive data export functionality to backup your inventory data and materials taxonomy to Google Sheets or download as JSON data. This feature is essential for data backup, reporting, and integration with other systems.

### Export Types

#### 1. Inventory Export
Exports all inventory items with complete details including:
- Item identification (JA ID, type, shape, material)
- Physical dimensions (length, width, thickness, wall thickness, weight)
- Threading information (series, handedness, size, form)
- Location tracking (location, sub-location)
- Purchase details (date, price, vendor, part numbers)
- Status and history (active/inactive, dates, notes)

#### 2. Materials Taxonomy Export
Exports the hierarchical materials classification system:
- Material names and categories
- Hierarchy levels (1=Category, 2=Family, 3=Material)
- Parent-child relationships
- Example: Metal → Steel → 4140 Pre-Hard

#### 3. Combined Export
Exports both inventory and materials data in a single operation for complete backup.

### Export Destinations

#### JSON Format
- **Use Case**: API integration, data processing, development
- **Format**: Structured JSON with metadata, headers, and row data
- **Response**: Direct API response with immediate download
- **Benefits**: Machine-readable, preserves data types, includes export metadata

#### Google Sheets Upload
- **Use Case**: Backup, manual review, sharing with stakeholders
- **Format**: Direct upload to Google Sheets with proper formatting
- **Target Sheets**: `Metal_Export` (inventory), `Materials_Export` (materials)
- **Benefits**: Human-readable, accessible via web browser, collaborative editing

### Using the Web Interface

#### Admin Export Page
1. Navigate to `/admin/export` (admin access required)
2. Select export type: Inventory, Materials, or Combined
3. Choose destination: JSON Download or Google Sheets Upload
4. Configure options:
   - Include inactive items (inventory only)
   - Batch size for processing
   - Enable progress logging
5. Click "Export" to start the process
6. Monitor progress and download results

### API Access

#### Export to JSON
```bash
# Export inventory data only
curl -X POST http://localhost:5000/api/admin/export \
  -H "Content-Type: application/json" \
  -d '{
    "type": "inventory",
    "destination": "json",
    "options": {
      "include_inactive": true,
      "batch_size": 1000
    }
  }' | jq '.'

# Export materials taxonomy only
curl -X POST http://localhost:5000/api/admin/export \
  -H "Content-Type: application/json" \
  -d '{
    "type": "materials",
    "destination": "json",
    "options": {
      "materials_active_only": true,
      "batch_size": 1000
    }
  }' | jq '.'

# Export combined data
curl -X POST http://localhost:5000/api/admin/export \
  -H "Content-Type: application/json" \
  -d '{
    "type": "combined",
    "destination": "json",
    "options": {
      "include_inactive": false,
      "materials_active_only": true,
      "batch_size": 1000
    }
  }' | jq '.'
```

#### Export to Google Sheets
```bash
# Upload inventory data to Google Sheets
curl -X POST http://localhost:5000/api/admin/export \
  -H "Content-Type: application/json" \
  -d '{
    "type": "inventory",
    "destination": "sheets",
    "options": {
      "include_inactive": true,
      "batch_size": 1000,
      "enable_progress_logging": true
    }
  }' | jq '.'

# Upload materials taxonomy to Google Sheets
curl -X POST http://localhost:5000/api/admin/export \
  -H "Content-Type: application/json" \
  -d '{
    "type": "materials", 
    "destination": "sheets",
    "options": {
      "materials_active_only": true,
      "batch_size": 1000
    }
  }' | jq '.'

# Upload both datasets to Google Sheets
curl -X POST http://localhost:5000/api/admin/export \
  -H "Content-Type: application/json" \
  -d '{
    "type": "combined",
    "destination": "sheets",
    "options": {
      "include_inactive": false,
      "materials_active_only": true,
      "batch_size": 1000,
      "enable_progress_logging": true
    }
  }' | jq '.'
```

#### Data Validation
```bash
# Validate export data before uploading
curl -X POST http://localhost:5000/api/admin/export/validate \
  -H "Content-Type: application/json" \
  -d '{
    "export_data": {
      "inventory": {
        "headers": ["Active", "JA ID", "Length", "..."],
        "rows": [["Yes", "JA000001", "5.5400", "..."]]
      },
      "materials": {
        "headers": ["Name", "Level", "Parent"],
        "rows": [["Steel", "2", "Metal"]]
      }
    }
  }' | jq '.'
```

### Export Options

#### Inventory Options
- **include_inactive**: Include inactive/historical items (default: true)
- **inventory_sort_order**: Sort order for results (default: "ja_id, active DESC, date_added")
- **batch_size**: Records per processing batch (default: 1000)

#### Materials Options  
- **materials_active_only**: Export only active materials (default: true)
- **materials_sort_order**: Sort order (default: "level, sort_order, name")
- **batch_size**: Records per processing batch (default: 1000)

#### General Options
- **enable_progress_logging**: Show detailed progress logs (default: true)
- **export_generated_by**: Attribution text for export metadata

### Response Format

#### Success Response (JSON)
```json
{
  "success": true,
  "export_data": {
    "type": "inventory",
    "headers": ["Active", "JA ID", "Length", "..."],
    "rows": [
      ["Yes", "JA000001", "5.5400", "..."],
      ["No", "JA000002", "3.2500", "..."]
    ],
    "metadata": {
      "export_type": "inventory",
      "timestamp": "2025-09-11T17:30:00.000Z",
      "records_exported": 476,
      "success": true,
      "errors": [],
      "warnings": []
    }
  },
  "export_type": "inventory",
  "timestamp": "2025-09-11T17:30:00.000Z"
}
```

#### Success Response (Google Sheets)
```json
{
  "success": true,
  "message": "Export to Google Sheets completed successfully",
  "export_type": "inventory",
  "upload_details": {
    "success": true,
    "rows_uploaded": 476,
    "sheets_updated": ["Metal_Export"],
    "upload_type": "inventory"
  }
}
```

#### Error Response
```json
{
  "success": false,
  "error": "Export operation failed: Invalid export type"
}
```

### Automated Backups

#### Scheduled Exports via Cron
```bash
# Daily backup at 2 AM - inventory and materials to Google Sheets
0 2 * * * curl -X POST http://localhost:5000/api/admin/export \
  -H "Content-Type: application/json" \
  -d '{"type": "combined", "destination": "sheets", "options": {"include_inactive": true}}'

# Weekly backup to JSON files  
0 3 * * 0 curl -X POST http://localhost:5000/api/admin/export \
  -H "Content-Type: application/json" \
  -d '{"type": "combined", "destination": "json"}' \
  > "/backups/inventory_$(date +%Y%m%d).json"
```

### Best Practices

#### Performance
- Use appropriate batch sizes (1000 is optimal for most cases)
- Schedule large exports during low-usage periods
- Enable progress logging for monitoring long-running exports

#### Data Quality
- Validate exports regularly using the validation endpoint
- Compare record counts between source and destination
- Review export metadata for errors and warnings

#### Security
- Restrict admin export access to authorized users only
- Use HTTPS for all API communications
- Rotate Google Sheets credentials regularly
- Monitor export logs for unusual activity

#### Backup Strategy
- Regular automated backups to Google Sheets for accessibility
- Periodic JSON exports for long-term archival
- Test restore procedures using exported data
- Keep multiple backup versions for point-in-time recovery

### Troubleshooting Export Issues

#### Common Problems
- **"Google Sheets connection failed"**: Check credentials and sheet permissions
- **"Sheet not found"**: Ensure target sheets exist in the Google Sheets document
- **"Rate limit exceeded"**: Reduce batch size or add delays between operations
- **"Export timeout"**: Break large exports into smaller chunks or increase timeout

#### Performance Tuning
- Adjust batch_size based on dataset size and performance
- Use include_inactive=false for faster inventory exports
- Monitor system resources during large exports
- Consider off-peak hours for major backup operations

## REST API

The application exposes a small set of JSON endpoints intended for
programmatic clients (scripts, integrations, or the bundled Python
client described below). The endpoints are served from the same Flask
application as the web UI and share its database. They are exempt from
CSRF and have no built-in authentication; protect them at the network
layer if exposed beyond the local host.

### `POST /api/inventory/items`

Create one or more inventory items.

Request body: a JSON object. Unknown top-level keys are rejected with
a 400 so typos surface immediately. **The server allocates JA IDs
itself — do not send a `ja_id` field. Sending one is treated as an
unknown field and the request is rejected with 400.** The allocated
JA ID(s) come back in the response's `created_ja_ids` list.

The full set of accepted fields follows.

#### Required fields

| Field       | Type   | Description |
|-------------|--------|-------------|
| `item_type` | string | One of: `"Bar"`, `"Plate"`, `"Sheet"`, `"Tube"`, `"Threaded Rod"`, `"Angle"`, `"Channel"`. |
| `shape`     | string | One of: `"Rectangular"`, `"Round"`, `"Square"`, `"Hex"`. |
| `material`  | string | Material name. Validated against the materials taxonomy when one is configured; pass a name or alias from the taxonomy (e.g. `"Steel"`, `"4140"`, `"6061-T6"`, `"316"`). When the taxonomy is empty the field is accepted as-is. |
| `location`  | string | Physical location label (e.g. `"Shelf A"`). Free-form. |

#### Optional dimension fields (inches, except `weight` in pounds)

| Field            | Type             | Description |
|------------------|------------------|-------------|
| `length`         | string \| number | Length in inches. Strings may be decimal (`"12.5"`), simple fraction (`"3/4"`), or mixed number (`"1 1/2"`). Numbers are coerced to string before parsing. |
| `width`          | string \| number | Width / outer diameter in inches. Same parsing rules as `length`. |
| `thickness`      | string \| number | Thickness in inches. Same parsing rules. |
| `wall_thickness` | string \| number | Wall thickness for tubular shapes, in inches. Same parsing rules. |
| `weight`         | string \| number | Weight in pounds. Same parsing rules. |

An unparseable dimension (e.g. `"abc"`) returns 400 with the field
name in the error message.

#### Optional threading fields

| Field               | Type   | Description |
|---------------------|--------|-------------|
| `thread_series`     | string | One of: `"UNC"`, `"UNF"`, `"UNEF"`, `"UNS"`, `"Metric"`, `"BSW"`, `"BSF"`, `"NPT"`, `"Acme"`, `"Trapezoidal"`, `"Square"`, `"Buttress"`, `"Custom"`, `"Other"`. Case-insensitive (uppercased before storage). The literal string `"None"` is treated as not provided, matching the HTML form. |
| `thread_handedness` | string | `"RH"` (right-hand, the default if `thread_series` is set) or `"LH"` (left-hand). Case-insensitive. |
| `thread_size`       | string | Thread designation, e.g. `"1/4-20"`, `"M10x1.5"`, `"3/8-16"`. |

#### Optional location, purchase, and metadata fields

| Field                | Type             | Description |
|----------------------|------------------|-------------|
| `sub_location`       | string           | Sub-location within the primary location. |
| `purchase_date`      | string           | Date the item was purchased. Accepts ISO `YYYY-MM-DD`, US `MM/DD/YYYY`, or dotted `MM.DD.YYYY`. Unparseable values are silently stored as null (matching form behavior). |
| `purchase_price`     | string \| number | Purchase price. Stored as-supplied. |
| `purchase_location`  | string           | Where the item was purchased (vendor location, store name, etc.). |
| `vendor`             | string           | Vendor name. |
| `vendor_part_number` | string           | Vendor's part number. (This is the JSON field name; it is stored internally as `vendor_part`.) |
| `notes`              | string           | Free-form notes. |

#### Optional flags

| Field       | Type    | Description |
|-------------|---------|-------------|
| `active`    | boolean | Whether the item is active. **JSON booleans only** (`true` / `false`); string values like `"on"`, `"true"`, `"yes"` are rejected with a 400. Defaults to `false` when omitted, matching the HTML form's unchecked-checkbox semantics — pass `true` explicitly to create an active item. |
| `precision` | boolean | Whether the item carries precision dimensions. Same rules as `active`. Defaults to `false`. |

#### Bulk creation

| Field                | Type    | Description |
|----------------------|---------|-------------|
| `quantity_to_create` | integer | Number of items to create with sequential JA IDs (1-100). Defaults to 1. The server allocates the next free JA ID and assigns it to the first item, then increments for each subsequent item. The provided field values are applied to every created item. |

#### Response

Always JSON:

```json
{
  "success": true,
  "created_ja_ids": ["JA000123"],
  "errors": [],
  "message": "Item added successfully"
}
```

Each entry in `errors` has the shape
`{"index": <1-based attempt position>, "ja_id": <the JA ID that was attempted, may be null>, "message": "..."}`.
The `index` is 1-based — `index: 2` means "the second item the bulk
request tried to create." For single-item requests it is `0`.

#### Status codes

- `200 OK` — all requested items were created.
- `207 Multi-Status` — bulk request succeeded for some items but not
  all. `created_ja_ids` lists the ones that persisted; `errors` lists
  the failures.
- `400 Bad Request` — request-level validation problem: missing
  required field, unknown JSON key, malformed body, invalid enum
  value, unparseable dimension, invalid material, etc. Nothing was
  created. Also returned when every item in a bulk request failed
  for a parse-time validation reason.
- `500 Internal Server Error` — unexpected backend failure (e.g. DB
  unreachable). Nothing was created (or, in a bulk request, no items
  succeeded and at least one failure was a non-validation error).

#### Example: minimal single-item request

Request:

```json
{
  "item_type": "Bar",
  "shape": "Round",
  "material": "Steel",
  "location": "Shelf A",
  "active": true
}
```

Response (the JA ID was allocated by the server):

```json
{
  "success": true,
  "created_ja_ids": ["JA000123"],
  "errors": [],
  "message": "Item added successfully"
}
```

#### Example: fully-populated bulk request

```json
{
  "item_type": "Threaded Rod",
  "shape": "Round",
  "material": "316",
  "location": "Rack 3",
  "sub_location": "Bin 7",
  "length": "36",
  "width": "1/4",
  "thread_series": "UNC",
  "thread_handedness": "RH",
  "thread_size": "1/4-20",
  "purchase_date": "2024-09-15",
  "purchase_price": "8.95",
  "purchase_location": "McMaster-Carr",
  "vendor": "McMaster-Carr",
  "vendor_part_number": "98990A030",
  "notes": "Stocked for fixture builds.",
  "active": true,
  "precision": false,
  "quantity_to_create": 5
}
```

The five JA IDs the server allocates are returned in
`created_ja_ids` (e.g. `["JA000200", "JA000201", "JA000202",
"JA000203", "JA000204"]`).

### `POST /api/items/<ja_id>/photos`

Upload a photo for an existing item. Send a `multipart/form-data`
request with the file in either a `file` or `photo` field. Returns
`{success, photo, message}` on success; 400 on bad input; 500 on
storage failure.

### `GET /api/inventory/field-suggestions/<field>`

Return distinct existing values currently recorded for a free-form
field. Powers the database-backed autocomplete on the Add and Edit
Item forms and on the product form's Category and Tags fields;
available for programmatic clients too.

One endpoint serves two sources. For the item fields, suggestions are
pulled from **all rows** in `inventory_items`, including inactive
(history) rows, so deactivated items still seed suggestions. For
`category_path`, they are pulled from the `products` table — the
category tree *is* the set of paths products are filed under, so a path
is offered only once some product uses it. For `tags`, they come from
the `product_tags` table, which likewise *is* the tag vocabulary: a tag
is offered only once some product carries it, and it disappears when the
last product drops it. Empty/whitespace values are excluded.
Comparisons are case-insensitive throughout.

For how these suggestions behave on screen — the `+ Create "…"` entry, category
canonicalization, and the comma-separated tag field — see
[Products and Catalog](#products-and-catalog).

#### Path parameter — `<field>`

Must be one of the following whitelisted field names. Any other value
returns 400.

| Field               | Description |
|---------------------|-------------|
| `thread_size`       | Thread designation (e.g. `1/4-20`, `M10x1.5`). |
| `purchase_location` | Where items were purchased (vendor location, store name). |
| `vendor`            | Vendor name. |
| `location`          | Physical location label. |
| `sub_location`      | Sub-location within a location. |
| `category_path`     | Product category path (e.g. `electronics/power/regulators`). Sourced from `products`, not `inventory_items`. |
| `tags`              | Product tag (e.g. `ssr`). Sourced from `product_tags`, not `inventory_items`. Canonical form is lowercase with internal whitespace collapsed; a tag never contains a comma. |

Material is intentionally excluded — it has its own taxonomy-backed
endpoint at `/api/materials/suggestions`.

#### Query parameters

| Parameter  | Type    | Description |
|------------|---------|-------------|
| `q`        | string  | Optional case-insensitive substring filter. When omitted, returns distinct values in alphabetical order up to `limit`. |
| `limit`    | integer | Maximum number of suggestions. Clamped to `[1, 50]`; defaults to 10. |
| `location` | string  | Only meaningful when `<field>` is `sub_location`. Restricts results to sub-locations recorded under the given location (case-insensitive). Ignored for other fields. |

#### Ordering

Returned in this priority order:

1. Exact case-insensitive match (at most one entry).
2. Starts-with matches, alphabetized.
3. Substring matches, alphabetized.

When `q` is omitted, results are alphabetized.

#### Response

```json
{
  "success": true,
  "field": "vendor",
  "suggestions": ["Grainger", "McMaster-Carr", "Online Metals"]
}
```

For the product-sourced fields (`category_path` and `tags`) only, the
body carries one extra key, `normalized` — the canonical form of `q`,
i.e. the exact value that would be stored if the operator created it.
For `category_path` that is lowercase, `/`-separated, with no leading,
trailing or repeated separators; for `tags` it is lowercase with
surrounding whitespace trimmed and internal runs collapsed to one space.
It is `null` when `q` is omitted or carries no value at all (e.g. `/` or
whitespace for a path, blank for a tag), and also when `q` could never
be stored — a canonicalized path longer than 512 characters, or a tag
longer than 64 characters or containing a comma — in which case
`suggestions` is an empty list rather than the unfiltered vocabulary.
Item fields never include this key.

```json
{
  "success": true,
  "field": "category_path",
  "suggestions": ["electronics/power/regulators"],
  "normalized": "electronics/power"
}
```

#### Status codes

- `200 OK` — suggestions returned (possibly empty list when nothing matches).
- `400 Bad Request` — `<field>` is not whitelisted.
- `500 Internal Server Error` — unexpected backend failure.

#### Example

```
GET /api/inventory/field-suggestions/sub_location?location=Shelf%20A&limit=5
```

Returns sub-locations currently recorded under Location "Shelf A":

```json
{
  "success": true,
  "field": "sub_location",
  "suggestions": ["Bottom Bin", "Top Bin"]
}
```

### `GET /api/taxonomy`

Return the full hierarchical materials taxonomy as a nested tree. This
is the general-purpose endpoint for programmatic clients that need the
materials taxonomy (the material names and aliases accepted by the
`material` field on `POST /api/inventory/items`).

The taxonomy has three levels: **Category** (level 1) → **Family**
(level 2) → **Material** (level 3). Each level's nodes are returned
under the `children` key of their parent.

#### Query parameters

| Parameter          | Type    | Description |
|--------------------|---------|-------------|
| `include_inactive` | boolean | When `true`, inactive taxonomy entries are included. Defaults to `false` (active entries only). |

#### Response

```json
{
  "success": true,
  "taxonomy": [
    {
      "id": 1,
      "name": "Steel",
      "level": 1,
      "active": true,
      "notes": "",
      "sort_order": 0,
      "children": [
        {
          "id": 5,
          "name": "Alloy Steel",
          "level": 2,
          "parent": "Steel",
          "active": true,
          "notes": "",
          "sort_order": 0,
          "children": [
            {
              "id": 9,
              "name": "4140",
              "level": 3,
              "parent": "Alloy Steel",
              "active": true,
              "aliases": ["41400"],
              "notes": "",
              "sort_order": 0
            }
          ]
        }
      ]
    }
  ]
}
```

Node fields:

| Field        | Levels        | Description |
|--------------|---------------|-------------|
| `id`         | all           | Database id of the taxonomy entry. |
| `name`       | all           | The taxonomy name (used as the parent reference of child nodes). |
| `level`      | all           | `1` = Category, `2` = Family, `3` = Material. |
| `active`     | all           | Whether the entry is active. |
| `notes`      | all           | Free-form notes (empty string if none). |
| `sort_order` | all           | Ordering hint within the parent. |
| `children`   | 1, 2          | List of child nodes (families under a category, materials under a family). |
| `parent`     | 2, 3          | `name` of the parent node. |
| `aliases`    | 3             | List of alias names for the material. |

#### Status codes

- `200 OK` — taxonomy returned (possibly an empty list when the
  taxonomy is unconfigured).
- `500 Internal Server Error` — unexpected backend failure.

### Python client

A standalone Python client lives at `app/api_client.py`. It depends
only on the `requests` library and exposes a `WorkshopInventoryClient`
class with `create_item(...)`, `upload_photo(...)`,
`get_field_suggestions(...)`, and `get_taxonomy(...)` methods. The client can be copied or
vendored into other projects without pulling in any of the
application's runtime dependencies.

```python
from app.api_client import WorkshopInventoryClient

client = WorkshopInventoryClient("http://localhost:5000")

result = client.create_item({
    "item_type": "Bar",
    "shape": "Round",
    "material": "Steel",
    "location": "Shelf A",
    "length": 12.5,
    "active": True,
})
# The server allocates JA IDs; read them back from the result.
print(result.created_ja_ids, result.errors)

ja_id = result.created_ja_ids[0]
photo = client.upload_photo(ja_id, file_path="part.jpg")

# Field-suggestion autocomplete:
vendors = client.get_field_suggestions("vendor", query="mc")
print(vendors.suggestions)  # e.g. ["McMaster-Carr"]

# Sub-location scoped to a Location:
subs = client.get_field_suggestions(
    "sub_location", location="Shelf A", limit=20
)
print(subs.suggestions)

# Full materials taxonomy tree:
taxonomy = client.get_taxonomy()
for category in taxonomy.taxonomy:
    print(category["name"], "->", [f["name"] for f in category["children"]])
```

`create_item`, `upload_photo`, `get_field_suggestions`, and
`get_taxonomy` return frozen dataclasses (`CreateItemResult`,
`UploadPhotoResult`, `FieldSuggestionsResult`, `TaxonomyResult`)
carrying the parsed response. Network errors raise
`requests.RequestException`; HTTP errors (4xx/5xx) populate the
result's `errors` list and set `success=False` rather than raising.

The constant `SUGGESTABLE_FIELDS` (a tuple of the whitelisted field
names) is exported alongside the client for callers who want to
validate field names before issuing a request.

## Help and Utilities

### Quick Search
- `/` - Focus search field from anywhere in the application
- Use this to quickly jump to the search input without clicking

### Built-in Help
- `F1` or `Shift+/` - Show available help and shortcuts
- Hover over field labels for tooltips and guidance
- Check validation messages for field-specific help

### Barcode Scanner Support
- Most input fields support barcode scanning
- Ensure your scanner is configured as a "keyboard wedge"
- Test scanner functionality in any text editor first

### Context-Sensitive Features
- Form fields provide real-time validation feedback
- Auto-complete suggestions appear as you type
- Error messages guide you to correct formatting

## Tips and Best Practices

### ID Management
- Use consistent ID format (e.g., JA + 5 digits)
- Sequential numbering helps tracking
- Consider material codes in IDs

### Measurements
- Always use same units (inches recommended)
- Fractions preferred for common sizes
- Document measurement method in notes

### Threading
- Use standard nomenclature
- Include thread form for specialty threads
- Note if threads are damaged or modified

### Location Tracking
- Establish consistent location naming
- Use sublocation for precise placement
- Update locations promptly after moves

### Data Quality
- Complete all applicable fields
- Use notes for special conditions
- Regular data cleanup maintains accuracy

### Performance
- Search filters improve response time
- Batch operations when possible
- Regular browser cache clearing if slow

## Troubleshooting

### Common Issues

#### "Cannot connect to Google Sheets"
- **Check**: Internet connection
- **Verify**: Google Sheets permissions
- **Solution**: Refresh page, check credentials

#### "Item not found"
- **Check**: JA ID spelling/format
- **Verify**: Item still active
- **Solution**: Use search to locate similar items

#### "Duplicate item ID"
- **Check**: Existing item with same ID
- **Solution**: Use different ID or update existing

#### "Form validation errors"
- **Check**: Required fields completed
- **Verify**: Correct data formats
- **Solution**: Follow field help text

#### "Barcode scanner not working"
- **Check**: Scanner configured as keyboard wedge
- **Test**: Scanner in text editor
- **Solution**: Reconfigure scanner settings

#### "Search returns too many results"
- **Solution**: Add more specific filters
- **Tip**: Use range filters for dimensions
- **Export**: Download results for offline review

#### "Performance is slow"
- **Clear**: Browser cache and cookies
- **Check**: Internet connection speed
- **Reduce**: Number of active browser tabs

### Getting Help

#### Built-in Help
- Press `F1` for help and available shortcuts
- Hover over field labels for tooltips
- Check validation messages for guidance

#### Data Issues
- Verify entries in Google Sheets directly
- Check for formatting consistency
- Contact administrator for access issues

#### Technical Problems
- Clear browser cache
- Try different browser
- Check browser JavaScript enabled
- Ensure pop-ups allowed for application domain

### Performance Optimization
- Use search filters to limit results
- Close unused browser tabs
- Regular browser maintenance
- Consider wired connection for barcode scanners

---

## Quick Reference Card

### Most Common Operations
1. **Add Item**: Navigate to "Add Item" → Fill required fields → Submit
2. **Find Item**: Navigate to "Search" → Enter search criteria → View results
3. **Move Items**: Navigate to "Move Items" → Scan item/location pairs → Submit
4. **List All**: Navigate to "Inventory List" → Use filters as needed

### Required Fields for New Items
- JA ID, Type, Shape, Material

### Measurement Format
- Inches preferred: "1 1/4" or "1.25"
- Consistency is key

### Thread Format Examples
- Inch: "1/4-20", "3/8-16 UNC"
- Metric: "M10x1.5", "M6x1.0"
- Special: "3/4-6 Acme", "1/2-14 NPT"

This user manual provides comprehensive guidance for using the Workshop Inventory Tracking system efficiently and effectively.