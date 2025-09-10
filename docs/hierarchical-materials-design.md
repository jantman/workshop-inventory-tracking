# Hierarchical Materials Design

Based on analysis of 505 inventory items with 73 unique materials.

## Current State Analysis

**Material Distribution:**
- Unknown: 160 items (31.7%) - needs identification
- Carbon Steel: ~80 items (diverse grades: 4140, 12L14, A36, CRS)
- Brass: ~60 items (multiple alloys: 360, C23000, H58)
- Copper: ~30 items (including Beryllium Copper)
- Aluminum: ~30 items (6061, 6063, T6 variants)
- Stainless Steel: ~35 items (15 different grades)

**Data Quality Issues:**
- Inconsistent naming conventions
- Mixed specificity levels (generic "Steel" vs specific "4140 Pre-Hard")
- Uncertainty indicators ("Stainless?", "4140 ?")
- Duplicate/variant entries

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

## Google Sheets Data Model

### Materials Sheet Structure

| Column | Type | Description |
|--------|------|-------------|
| **id** | String | Unique material ID (UUID) |
| **name** | String | Display name (e.g., "4140 Pre-Hard") |
| **category** | String | Top-level category (e.g., "Carbon Steel") |
| **family** | String | Sub-category (e.g., "Medium Carbon Steel") |
| **parent_id** | String | Parent material ID (for sub-materials) |
| **level** | Integer | Hierarchy level (1=Category, 2=Family, 3=Material) |
| **aliases** | String | Comma-separated aliases for matching |
| **properties** | JSON | Material properties (density, strength, etc.) |
| **common_forms** | String | Common shapes/forms available |
| **active** | Boolean | Whether material is active for selection |
| **usage_count** | Integer | Times used in inventory (updated by migration) |
| **created_date** | DateTime | When added to system |
| **notes** | String | Additional notes |

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

## Migration Strategy

### Phase 1: Clean Data Setup
1. Create Materials Google Sheet with hierarchical structure
2. Populate with clean, organized material hierarchy
3. Map existing materials to new hierarchy using aliases

### Phase 2: System Integration  
1. Build MaterialHierarchyService for data access
2. Create hierarchical material selection UI
3. Update material autocomplete to use new hierarchy

### Phase 3: Data Migration
1. Create migration tool to map existing inventory materials
2. Update all existing inventory items to use new material IDs
3. Preserve historical data with old→new material mapping

### Phase 4: Enhanced Features
1. Admin interface for managing material hierarchy
2. Material property display and filtering
3. Usage analytics and reporting

## UI/UX Design Concepts

### Hierarchical Material Selector
- **Expandable tree view** for browsing categories
- **Type-ahead search** across all levels
- **Recent/frequent materials** for quick access  
- **Material properties tooltip** on hover
- **"Add new material"** option for admin users

### Search Behavior
- Search across name, aliases, and family names
- Fuzzy matching for typos and variants
- Category filtering (show only brass, steel, etc.)
- Usage-based relevance scoring

## Benefits

### For Users
- **Organized selection** instead of long flat list
- **Consistent naming** reduces confusion
- **Material properties** help with selection
- **Faster finding** through categorization

### For Data Quality
- **Eliminates duplicates** through normalization
- **Standardized naming** conventions
- **Uncertainty tracking** for unknown materials
- **Usage analytics** for inventory insights

## Implementation Priority

1. **High Priority**: Core hierarchy setup and basic UI
2. **Medium Priority**: Migration tools and data cleanup
3. **Low Priority**: Advanced features and analytics

This design provides a scalable foundation that can grow with your inventory needs while immediately improving the material selection experience.