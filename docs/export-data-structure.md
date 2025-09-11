# Export Data Structure Design

This document defines the export data format for converting MariaDB data back to Google Sheets format.

## Inventory Items Export Structure

### Target Sheet: `Metal_Export`

The export should match the original Google Sheets `Metal` sheet structure with all 27 columns:

| Column # | Google Sheets Header | Database Field | Notes |
|----------|---------------------|----------------|-------|
| 1 | Active | active | Convert boolean to "Yes"/"No" |
| 2 | JA ID | ja_id | Direct mapping |
| 3 | Length | length | Format to 4 decimal places |
| 4 | Width | width | Format to 4 decimal places |
| 5 | Thickness | thickness | Format to 4 decimal places |
| 6 | Wall Thickness | wall_thickness | Format to 4 decimal places |
| 7 | Weight | weight | Format to 2 decimal places |
| 8 | Type | item_type | Direct mapping |
| 9 | Shape | shape | Direct mapping |
| 10 | Material | material | Direct mapping |
| 11 | Thread Series | thread_series | Direct mapping |
| 12 | Thread Handedness | thread_handedness | Direct mapping |
| 13 | Thread Form | (skip) | Not in database - leave empty |
| 14 | Thread Size | thread_size | Direct mapping |
| 15 | Quantity | quantity | Direct mapping |
| 16 | Location | location | Direct mapping |
| 17 | Sub-Location | sub_location | Direct mapping |
| 18 | Purchase Date | purchase_date | Format as YYYY-MM-DD |
| 19 | Purchase Price | purchase_price | Format to 2 decimal places |
| 20 | Purchase Location | purchase_location | Direct mapping |
| 21 | Notes | notes | Direct mapping |
| 22 | Vendor | vendor | Direct mapping |
| 23 | Vendor Part | vendor_part | Direct mapping |
| 24 | Original Material | original_material | Direct mapping |
| 25 | Original Thread | original_thread | Direct mapping |
| 26 | Date Added | date_added | Format as YYYY-MM-DD HH:MM:SS |
| 27 | Last Modified | last_modified | Format as YYYY-MM-DD HH:MM:SS |

### Export Options for Inventory Items:
- **All Items**: Export both active and inactive rows (full history)
- **Active Only**: Export only currently active items 
- **Order**: Sort by JA ID, then by active status (active first), then by date_added

## Materials Taxonomy Export Structure

### Target Sheet: `Materials_Export`

The export should match the original `Materials` sheet structure:

| Column # | Google Sheets Header | Database Field | Notes |
|----------|---------------------|----------------|-------|
| 1 | Name | name | Direct mapping |
| 2 | Level | level | Direct mapping (1, 2, or 3) |
| 3 | Parent | parent | Direct mapping (empty for level 1) |

### Export Options for Materials Taxonomy:
- **Order**: Sort by level, then by sort_order, then by name
- **Filter**: Only export active materials (active = true)

## Data Formatting Rules

### Boolean Values
- Database `true` → Google Sheets `"Yes"`
- Database `false` → Google Sheets `"No"` 
- Database `NULL` → Google Sheets `""`

### Numeric Values
- Decimal fields: Format to specified precision, remove trailing zeros
- NULL values: Export as empty string `""`
- Zero values: Export as `"0"` or `"0.00"` based on precision

### Date/DateTime Values
- Dates: Format as `YYYY-MM-DD` (e.g., "2022-08-11")
- DateTimes: Format as `YYYY-MM-DD HH:MM:SS` (e.g., "2025-09-01 09:46:46")
- NULL values: Export as empty string `""`

### String Values
- Direct mapping, preserve all text
- NULL values: Export as empty string `""`
- Escape special characters if needed for CSV compatibility

## Export File Structure

### Inventory Export
```
Header Row: ["Active", "JA ID", "Length", ..., "Last Modified"]
Data Rows: [
    ["Yes", "JA000001", "5.5400", ..., "2025-09-01 09:46:46"],
    ["No", "JA000001", "5.7100", ..., "2025-09-01 09:46:46"],
    ...
]
```

### Materials Taxonomy Export
```
Header Row: ["Name", "Level", "Parent"]
Data Rows: [
    ["Metal", "1", ""],
    ["Steel", "2", "Metal"],
    ["4140 Pre-Hard", "3", "Steel"],
    ...
]
```

## Performance Considerations

### Batch Processing
- Process exports in batches of 1000 rows to avoid memory issues
- Use database pagination with LIMIT/OFFSET for large datasets

### Memory Management
- Stream data directly to Google Sheets API rather than loading all in memory
- Clear intermediate data structures between batches

### Error Handling
- Validate data types before export
- Handle Google Sheets API rate limits with exponential backoff
- Provide detailed error messages for debugging

## Export Metadata

Each export should include metadata:
- Export timestamp
- Number of records exported
- Database version/migration state
- Export options used (all vs active only)
- Any data quality issues or warnings