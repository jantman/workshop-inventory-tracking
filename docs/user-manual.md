# Workshop Inventory Tracking - User Manual

## Table of Contents
1. [Getting Started](#getting-started)
2. [Overview](#overview)
3. [Adding New Inventory](#adding-new-inventory)
4. [Managing Existing Inventory](#managing-existing-inventory)
5. [Advanced Search](#advanced-search)
6. [Batch Operations](#batch-operations)
7. [Keyboard Shortcuts](#keyboard-shortcuts)
8. [Tips and Best Practices](#tips-and-best-practices)
9. [Troubleshooting](#troubleshooting)

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
- **Carry Forward**: Click "Continue Adding" to keep common values
- **Auto-save**: Form data is preserved if page refreshes
- **Validation**: Real-time feedback on field formats

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

### Parent-Child Relationships
- When items are shortened, relationships are tracked
- Original item becomes inactive
- New item references parent item

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