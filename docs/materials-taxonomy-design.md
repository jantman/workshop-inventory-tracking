# Materials Taxonomy Design

## Overview

The Workshop Inventory Tracking system uses a hierarchical materials taxonomy to organize and categorize materials. This document describes the design principles and implementation details of the materials taxonomy system.

## Taxonomy Structure

The materials taxonomy is implemented as a 3-level hierarchy stored in the `MaterialTaxonomy` table:

### Level 1: Categories
- **Purpose**: High-level material categories
- **Examples**: "Carbon Steel", "Aluminum", "Brass", "Stainless Steel"
- **Parent**: None (top-level entries)

### Level 2: Families
- **Purpose**: Material families within categories
- **Examples**: "Low Carbon Steel", "6061-T6", "360 Brass"
- **Parent**: References a Level 1 category name

### Level 3: Specific Materials
- **Purpose**: Specific material designations and alloys
- **Examples**: "A36", "1018", "4140", "6061-T6511"
- **Parent**: References a Level 2 family name

## Key Design Principles

### 1. Multi-Level Validity
**IMPORTANT**: Inventory items can be associated with materials at ANY level of the taxonomy hierarchy. All of the following are equally valid material assignments for inventory items:

- **Level 1 (Category)**: "Carbon Steel" - for general/unknown carbon steel items
- **Level 2 (Family)**: "Low Carbon Steel" - when family is known but specific alloy is not
- **Level 3 (Specific)**: "A36" - when exact material specification is known

### 2. Flexible Granularity
The system supports varying levels of material specification detail:
- Use Level 1 when only general material type is known
- Use Level 2 when material family is identified but specific alloy is unclear
- Use Level 3 when exact material specification is available

### 3. Aliases Support
Each taxonomy entry can have aliases (comma-separated) to handle:
- Alternative naming conventions
- Common abbreviations
- Historical or vendor-specific names

## Database Schema

```sql
CREATE TABLE material_taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    level INTEGER NOT NULL,  -- 1=Category, 2=Family, 3=Material
    parent VARCHAR(100),     -- Parent material name, NULL for level 1
    aliases TEXT,            -- Comma-separated aliases
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    date_added DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_modified DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## Example Taxonomy Hierarchy

```
Carbon Steel (Level 1)
├── Low Carbon Steel (Level 2)
│   ├── 1018 (Level 3)
│   ├── 1020 (Level 3)
│   ├── A36 (Level 3)
│   ├── CRS (Level 3)
│   └── HRS (Level 3)
├── Medium Carbon Steel (Level 2)
│   ├── 4140 (Level 3)
│   └── 4140 Pre-Hard (Level 3)
├── Free Machining Steel (Level 2)
│   ├── 12L14 (Level 3)
│   └── 1215 (Level 3)
└── High Strength Steel (Level 2)
    ├── 300M (Level 3)
    ├── A500 (Level 3)
    └── A513 (Level 3)
```

## Implementation Notes

### Audit Scripts
When implementing audit scripts or validation logic, remember to check against ALL active taxonomy levels, not just Level 3. The materials audit script should consider any active taxonomy entry as valid, regardless of level.

### User Interface
The material selection interface should support:
- Browsing the hierarchy
- Selecting materials at any level
- Searching across all levels and aliases

### Data Entry
Users should be encouraged but not required to use the most specific level available. Sometimes only general categorization is possible or appropriate.

## Common Misunderstandings

### ❌ Incorrect Assumption
"Only Level 3 materials are valid for inventory items"

### ✅ Correct Understanding
"Materials at any level (1, 2, or 3) are valid for inventory items, providing flexibility based on available information"

## Migration and Data Cleanup

When cleaning up existing inventory data:
1. Items with non-taxonomy materials should be evaluated case-by-case
2. Consider whether to add new taxonomy entries or update item materials
3. Maintain the principle that any taxonomy level is acceptable
4. Focus on consistency and utility rather than forcing specific granularity

## Future Development Notes

- Consider this design when adding new features that interact with materials
- Audit and validation scripts must account for all taxonomy levels
- Report generation should respect the hierarchical nature while accepting all levels
- Material-based filtering and searching should work across all levels

## Related Files

- `app/database.py` - MaterialTaxonomy model definition
- `app/mariadb_materials_admin_service.py` - Taxonomy management service
- `manage.py` - Audit materials command implementation
- `docs/deployment-guide.md` - Materials audit documentation