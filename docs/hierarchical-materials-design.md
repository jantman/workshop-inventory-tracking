# Hierarchical Materials Design (Revised)

Based on analysis of 505 inventory items with 73 unique materials.

## Revised Architecture Approach

**Key Design Principles:**
1. **Separation of Concerns**: Materials taxonomy in dedicated Materials sheet, inventory data stays in Metal sheet
2. **Flexible Specificity**: Material values can be any hierarchy level (Category/Family/Specific)
3. **Minimal Disruption**: Only update Material column values in existing Metal sheet
4. **Progressive Enhancement**: Users can be as specific or generic as their knowledge allows

## Current State Analysis

**Material Distribution:**
- Unknown: 160 items (31.7%) - can be categorized at appropriate specificity level
- Carbon Steel: ~80 items (diverse grades: 4140, 12L14, A36, CRS)
- Brass: ~60 items (multiple alloys: 360, C23000, H58)
- Copper: ~30 items (including Beryllium Copper)
- Aluminum: ~30 items (6061, 6063, T6 variants)
- Stainless Steel: ~35 items (15 different grades)

**Data Quality Strategy:**
- Replace inconsistent names with taxonomy values
- Allow generic categories for uncertain items (e.g., "Carbon Steel" instead of "Steel")
- Preserve specificity where known (e.g., "4140 Pre-Hard")
- Eliminate uncertainty indicators through proper categorization

## Proposed Hierarchical Structure

### 3-Level Hierarchy: Category → Family → Material

```
Category (Top Level)
├── Family (Sub-Category)
    ├── Material (Specific Alloy/Grade)
    └── Material (Specific Alloy/Grade)
```

### Material Categories

#### 1. **Carbon Steel**
- **Low Carbon Steel**: 1018, 1020, A36, CRS, HRS
- **Medium Carbon Steel**: 4140, 4140 Pre-Hard, 4140 Steel
- **Free Machining Steel**: 12L14, 1215
- **High Strength Steel**: 300M Alloy Steel, A500, A513
- **Unknown/Generic**: Steel, Mystery Steel

#### 2. **Stainless Steel**
- **Austenitic (300 Series)**: 304, 304L, 316, 316L, 321, RA330
- **Martensitic (400 Series)**: 410, 440
- **Precipitation Hardening**: 15-5, 17-4
- **Specialty Grades**: A269, T-304, T-316
- **Unknown/Generic**: Stainless, Stainless Steel, Stainless?

#### 3. **Aluminum**
- **6000 Series**: 6061-T6, 6061-T6511, 6063-T52
- **Generic**: Aluminum
- **Annealed**: T-304 Annealed, T-316 Annealed

#### 4. **Brass**
- **Free Machining**: Brass 360, Brass 360-H02
- **Red Brass**: C23000 red brass
- **High Strength**: Brass H58, Brass H58-330
- **Specialty**: Brass C272, Brass C385-H02, Brass C693, 353 Brass
- **Generic**: Brass

#### 5. **Copper**
- **Pure Copper**: Copper, C10100 Copper
- **Copper Alloys**: Beryllium Copper TPE3
- **Bronze**: Bronze??

#### 6. **Tool Steel**
- **Oil Hardening**: O1 Tool Steel
- **Air Hardening**: A-2
- **Hot Work**: H11 Tool Steel
- **Shock Resistant**: L6 Tool Steel
- **Generic**: Tool Steel RC 35-40

#### 7. **Other Metals**
- **Specialty Alloys**: 96% Nickel
- **Naval/Marine**: Naval Brass

#### 8. **Unknown/Uncategorized**
- Materials requiring identification or specialty classification

## Data Model

### Materials Sheet (Taxonomy Only)

The Materials sheet contains ONLY the taxonomy structure - no item data.

| Column | Type | Description |
|--------|------|-------------|
| **name** | String | Canonical name for this taxonomy entry |
| **level** | Integer | Hierarchy level (1=Category, 2=Family, 3=Specific) |
| **parent** | String | Parent name (empty for top-level categories) |
| **aliases** | String | Comma-separated alternative names |
| **active** | Boolean | Available for selection |
| **sort_order** | Integer | Display order within parent |
| **created_date** | DateTime | When added |
| **notes** | String | Additional information |

### Metal Sheet (Inventory Data - Unchanged Structure)

The existing Metal sheet structure remains exactly the same. Only the **Material** column values will be updated to reference taxonomy entries.

**Key Change**: Material column values can now be:
- Category level: `"Carbon Steel"` (for uncertain items)
- Family level: `"Medium Carbon Steel"` (when subfamily is known)
- Specific level: `"4140 Pre-Hard"` (when exact material is known)

### Example Hierarchy Structure

```
Carbon Steel (Category, Level 1)
├── Medium Carbon Steel (Family, Level 2)
    ├── 4140 (Material, Level 3)
    ├── 4140 Pre-Hard (Material, Level 3)
    └── 4140 Steel (Material, Level 3)
├── Free Machining Steel (Family, Level 2)
    ├── 12L14 (Material, Level 3)
    └── 1215 (Material, Level 3)
```

## Migration Strategy (Revised)

### Phase 1: Taxonomy Setup
1. Create Materials sheet with taxonomy structure only
2. Populate with hierarchical material taxonomy
3. Create mapping from existing material names to taxonomy entries

### Phase 2: Data Migration  
1. Build migration tool to update Metal sheet Material column
2. Map existing materials to appropriate taxonomy level:
   - Specific materials: `"Steel"` → `"Carbon Steel"` or specific grade if identifiable  
   - Keep specific materials: `"4140 Pre-Hard"` → `"4140 Pre-Hard"`
   - Generic materials: `"Stainless?"` → `"Stainless Steel"`
3. **No structural changes** to Metal sheet

### Phase 3: System Integration
1. Build MaterialHierarchyService for taxonomy access
2. Update material autocomplete to use hierarchical taxonomy
3. Allow selection at any hierarchy level

### Phase 4: Enhanced Features & Cleanup
1. Admin interface for managing taxonomy
2. Usage analytics across hierarchy levels
3. Remove material properties from existing codebase (taxonomy.py, etc.)
4. Clean up unused property-related code

## Implementation Benefits

### Flexible Specificity Examples
```
Current → New (at appropriate specificity level)
"Steel" → "Carbon Steel" (category level - when unsure of type)
"Stainless?" → "Stainless Steel" (category level - when unsure of grade) 
"4140 Pre-Hard" → "4140 Pre-Hard" (specific level - when exactly known)
"Unknown" → "Carbon Steel" (category level - after research/identification)
```

### Data Quality Improvements
- **Eliminates uncertainty markers**: No more "?" or "Unknown"
- **Consistent naming**: All materials reference taxonomy entries
- **Preserves knowledge**: Can be specific where known, generic where uncertain  
- **Progressive enhancement**: Can upgrade specificity over time

## UI/UX Design Concepts

### Hierarchical Material Selector
- **Expandable tree view** for browsing categories
- **Type-ahead search** across all levels
- **Recent/frequent materials** for quick access  
- **"Add new material"** option for admin users

### Search Behavior
- Search across name, aliases, and family names
- Fuzzy matching for typos and variants
- Category filtering (show only brass, steel, etc.)
- Usage-based relevance scoring

## Benefits

### For Users
- **Flexible specificity**: Choose level of detail appropriate to knowledge
- **Organized selection**: Browse categories or search across all levels
- **Consistent naming**: All materials reference clean taxonomy
- **Progressive enhancement**: Can upgrade specificity over time

### For Data Quality  
- **No structural disruption**: Existing Metal sheet unchanged
- **Eliminates uncertainty markers**: Proper categorization instead of "?"
- **Preserves knowledge**: Maintains current specificity levels
- **Clean taxonomy**: Centralized material definitions

## Implementation Priority

1. **High Priority**: Core hierarchy setup and basic UI
2. **Medium Priority**: Migration tools and data cleanup
3. **Low Priority**: Advanced features and analytics

This design provides a scalable foundation that can grow with your inventory needs while immediately improving the material selection experience.

---

## Implementation Status & Resumption Guide

### ✅ Completed Work
1. **Analysis Phase**: Analyzed 505 inventory items with 73 unique materials
2. **Design Refinement**: Updated architecture based on feedback:
   - Materials sheet = taxonomy only (no item data)
   - Metal sheet = unchanged structure, only Material column values updated
   - Flexible specificity levels (Category/Family/Specific)
   - Removed all material properties (simplified approach)
3. **Technical Fixes**: Fixed bugs in GoogleSheetsStorage `_retry_request` method calls
4. **Documentation**: Complete design specification ready for implementation

### 🔧 Current Issues to Resolve
1. **Google Sheets API Issue**: Sheet creation succeeds but writing data fails
   - Error: "Unable to parse range: Materials" 
   - Workaround: May need to manually create Materials sheet tab first
   - Root cause: Timing issue between sheet creation and data writing

### 📋 Next Implementation Steps (In Priority Order)

#### Phase 1: Foundation Setup
1. **Create Materials Sheet** (currently blocked)
   - Headers: name, level, parent, aliases, active, sort_order, created_date, notes
   - Contains taxonomy structure from analysis (7 categories, ~20 families, ~50 specifics)
   - Alternative: Manually create sheet tab, then populate with script

2. **Build MaterialHierarchyService**
   - Data access layer for Materials sheet
   - Methods: get_all_materials(), get_by_level(), get_children(), search()
   - Replace current material suggestions endpoint

#### Phase 2: System Integration  
3. **Update Material Autocomplete UI**
   - Support hierarchical browsing and search
   - Allow selection at any level (Category/Family/Specific)
   - Maintain backward compatibility

4. **Create Migration Tool**
   - Map existing 73 materials to taxonomy entries
   - Update Material column in Metal sheet (505 items)
   - Preserve data integrity, no structural changes

#### Phase 3: Enhancement & Cleanup
5. **Admin Interface** - Manage taxonomy through UI
6. **Remove Properties Code** - Clean up taxonomy.py and related files  
7. **E2E Testing** - Comprehensive test coverage

### 🗂️ Key Data Mappings (For Migration Reference)
```
High Priority Mappings (by usage count):
"Unknown" (160x) → Research and categorize appropriately
"Steel" (52x) → "Carbon Steel" 
"Brass" (50x) → "Brass"
"Copper" (30x) → "Copper"
"Aluminum" (24x) → "Aluminum"
"321 Stainless" (17x) → "321" (specific level)
"12L14" (10x) → "12L14" (already specific)
"Stainless?" (9x) → "Stainless Steel" (category level)
"4140 Pre-Hard" (4x) → "4140 Pre-Hard" (already specific)
```

### 🏗️ Architecture Decisions Made
- **Separation of Concerns**: Taxonomy separate from inventory data
- **Flexible Specificity**: Material values can be any hierarchy level
- **No Properties**: Removed all material property references
- **Minimal Disruption**: Only Material column values change in Metal sheet
- **Progressive Enhancement**: Can upgrade specificity over time

### 🔍 Files Modified
- `docs/hierarchical-materials-design.md` - Complete specification
- `app/google_sheets_storage.py` - Fixed `_retry_request` bugs in `create_sheet`/`rename_sheet`

### 🚀 Quick Resumption Checklist
1. Manually create "Materials" sheet tab in Google Sheets (if script still fails)
2. Build MaterialHierarchyService class in `app/materials_service.py`
3. Update `/api/materials/suggestions` endpoint to use taxonomy
4. Test with existing UI to ensure backward compatibility
5. Build migration tool to update Material column values

This foundation is ready for implementation - all architectural decisions are documented and the path forward is clear.