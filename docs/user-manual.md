# Workshop Inventory Tracking - User Manual

## Table of Contents
1. [Getting Started](#getting-started)
2. [Overview](#overview)
3. [Adding New Inventory](#adding-new-inventory)
4. [Label Printing](#label-printing)
5. [Managing Existing Inventory](#managing-existing-inventory)
6. [Advanced Search](#advanced-search)
7. [Batch Operations](#batch-operations)
8. [Data Export](#data-export)
9. [Keyboard Shortcuts](#keyboard-shortcuts)
10. [Tips and Best Practices](#tips-and-best-practices)
11. [Troubleshooting](#troubleshooting)

## Getting Started

### System Requirements
- Modern web browser (Chrome, Firefox, Safari, Edge)
- Internet connection for Google Sheets access
- Barcode scanner (optional, keyboard wedge type recommended)

### First Time Setup
1. Open your web browser and navigate to the application URL
2. The application will automatically connect to your Google Sheets inventory
3. If prompted, ensure you have access to the configured Google Sheet

### Main Navigation
- **Home** - Dashboard with application overview and quick actions
- **Add Item** - Add new inventory items
- **Search** - Advanced search and filtering
- **Inventory List** - View and manage all inventory
- **Move Items** - Batch move operations
- **Shorten Items** - Cut materials to length

## Overview

The Workshop Inventory Tracking system helps you manage metal stock, hardware, and other workshop materials. The system tracks:

- **Physical Properties**: Length, width, thickness, weight
- **Material Information**: Type, shape, material composition
- **Threading Details**: Series, handedness, size, form
- **Location Tracking**: Current location and sub-location
- **Purchase Information**: Date, price, vendor details
- **Status**: Active/inactive, quantity available

## Adding New Inventory

### Using the Add Item Form

1. **Navigate**: Click "Add Item" or press `Ctrl+A`
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
- **Auto-complete**: Previous entries suggest values as you type
- **Auto-save**: Form data is preserved if page refreshes
- **Validation**: Real-time feedback on field formats

### Streamlined Data Entry

#### Carry Forward Button
The **Carry Forward** button (located in the top-right header) allows you to copy common field values from the previously added item into the current form. This is useful when adding multiple similar items.

**Fields copied forward:**
- Type, Shape, Material, Quantity
- Location and Sub-Location
- Vendor and Purchase Location  
- Thread Series and Handedness

**Fields NOT copied (remain blank):**
- JA ID (you'll need to enter unique ID)
- Dimensions (length, width, thickness, etc.)
- Thread Size, Notes, Vendor Part Number
- Purchase Date and Price

**How to use:**
1. Add your first item normally
2. On the next add form, click **Carry Forward** to populate common fields
3. Enter the unique JA ID and dimensions for the new item
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

The system can print barcode labels for any JA ID using connected label printers. Labels can be printed from both the Add Item and Edit Item forms.

### Accessing Label Printing

#### From Add Item Form
1. Enter a valid JA ID (format: JA######)
2. The printer button (📄) will become enabled next to the JA ID field
3. Click the printer button to open the label printing dialog

#### From Edit Item Form
1. The printer button is always enabled since the JA ID already exists
2. Click the printer button next to the JA ID field
3. The label printing dialog will open

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

### Viewing Inventory
1. **Inventory List**: View all items with sorting and filtering
2. **Search Results**: View items matching search criteria
3. **Item Details**: Click any item to view complete information

### Updating Items
- Currently done through Google Sheets directly
- Future versions will include web-based editing

### Item Status
- **Active**: Available for use
- **Inactive**: Used up, cut down, or removed

### Parent-Child Relationships & Item History
- When items are shortened, complete history is tracked
- Original item becomes inactive while maintaining full record
- New item references parent item for traceability

#### Viewing Item History

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
Access via "Search" menu or press `Ctrl+F`

### Filter Categories

#### 1. Basic Filters
- **Status**: Active/inactive items
- **Type**: Rod, tube, sheet, hardware, etc.
- **Shape**: Round, square, rectangular, etc.
- **Material**: Steel, aluminum, brass, etc.

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

### Search Tips
- **Multiple Filters**: Combine filters for precise results
- **Range Queries**: Use min/max for dimensions
- **Partial Matches**: Text searches support partial matches
- **Export Results**: Download search results as CSV
- **Bookmark Searches**: Save frequently used search URLs

## Batch Operations

### Moving Items
1. **Navigate**: "Move Items" menu or press `Alt+M`
2. **Scan Method**: Alternate between item ID and location
3. **Submit**: Scan ">>DONE<<" or click submit
4. **Confirmation**: Review moves before finalizing

### Shortening Items
1. **Navigate**: "Shorten Items" menu or press `Alt+S`
2. **Item Selection**: Enter or scan item JA ID
3. **New Length**: Specify remaining length after cut
4. **New ID**: Assign new JA ID for shortened piece
5. **Automatic**: Original item becomes inactive, new item created

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

## Keyboard Shortcuts

### Navigation
- `Ctrl+H` - Home page
- `Ctrl+A` - Add Item
- `Ctrl+F` - Search/Find
- `Ctrl+L` - Inventory List

### Quick Actions  
- `Alt+M` - Move Items
- `Alt+S` - Shorten Items
- `Ctrl+S` - Submit current form
- `/` - Focus search field
- `Escape` - Close modals/cancel

### Help
- `F1` or `Shift+/` - Show keyboard shortcuts help
- `?` - Context help (when available)

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
- Press `F1` for keyboard shortcuts
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
1. **Add Item**: `Ctrl+A` → Fill required fields → `Ctrl+S`
2. **Find Item**: `Ctrl+F` → Enter search criteria → View results
3. **Move Items**: `Alt+M` → Scan item/location pairs → Submit
4. **List All**: `Ctrl+L` → Use filters as needed

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