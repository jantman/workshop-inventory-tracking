# Feature: Item Table Unification

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Overview

Currently, the application has two separate pages for displaying inventory items: the Inventory List (`/inventory`) and Advanced Search (`/inventory/search`). While both pages display essentially the same information (lists of items with their properties and available actions), they have diverged in terms of visual appearance, functionality, and underlying code. This creates maintenance burden, user experience inconsistency, and potential for bugs when features are added to one page but not the other.

### Current State

**Inventory List (`/inventory`, `app/templates/inventory/list.html`, `app/static/js/inventory-list.js`):**
- **Template:** ~300+ lines
- **JavaScript:** ~1,154 lines
- **Default Behavior:** Shows all active items by default
- **Search/Filter UI:** Simple filters (Status, Type, Material) and Quick Search field
- **Table Features:**
  - Selection checkboxes for bulk operations
  - Sortable columns (JA ID, Type, Shape, Material, Dimensions, Length, Location, Status)
  - Shows sub-location in addition to location
  - 10 columns total (including checkbox and actions)
- **Bulk Actions:** Move, Deactivate, Print Labels (via Options dropdown)
- **Individual Item Actions:** View History, Edit, Shorten, Move, Duplicate, Print Label
- **Export:** CSV export functionality
- **Other Features:** Refresh button, item count display, pagination

**Advanced Search (`/inventory/search`, `app/templates/inventory/search.html`, `app/static/js/inventory-search.js`):**
- **Template:** ~300+ lines
- **JavaScript:** ~706 lines
- **Default Behavior:** Shows search form, no results until search is executed
- **Search/Filter UI:** Comprehensive form with many fields (JA ID, Location, Notes, Type, Shape, Status, Precision, Material, Dimensions with ranges, Thread info, Purchase info)
- **Table Features:**
  - No selection checkboxes
  - Non-sortable columns (static headers)
  - Does NOT show sub-location
  - 9 columns total (no checkbox, no sub-location)
- **Bulk Actions:** None
- **Individual Item Actions:** View, Edit only
- **Export:** None
- **Other Features:** Bookmark button (copies URL with search params), Reset button, result count display

### Key Differences Summary

| Feature | Inventory List | Advanced Search |
|---------|---------------|-----------------|
| Selection checkboxes | ✅ Yes | ❌ No |
| Sortable columns | ✅ Yes | ❌ No |
| Sub-location column | ✅ Yes | ❌ No |
| Bulk operations | ✅ Yes (Move, Deactivate, Print Labels) | ❌ No |
| Item actions | View History, Edit, Shorten, Move, Duplicate, Print Label | View, Edit only |
| Export to CSV | ✅ Yes | ❌ No |
| Bookmark search | ❌ No | ✅ Yes |
| Search complexity | Simple filters | Comprehensive form |
| Default view | All active items | Empty (requires search) |
| Lines of code | ~1,454 | ~1,006 |

### Problems with Current State

1. **Code Duplication:** Table rendering logic, row generation, action handling, and pagination are duplicated across two files (~2,460 total lines)
2. **Maintenance Burden:** Any change to table display or functionality requires updates in two places
3. **Feature Drift:** Features added to one page (e.g., sub-location, bulk operations) aren't available on the other
4. **User Confusion:** Users expect the same capabilities on both pages but get different functionality
5. **Testing Overhead:** E2E tests must separately test both tables, duplicating test code
6. **Inconsistent UX:** Different visual appearance and interaction patterns for the same data

## Goals

This feature aims to achieve the following:

1. **Unified Visual Interface:** Both pages should display items using identical table structure, styling, and interaction patterns
2. **Unified Functionality:** Both pages should support the same features (selection, sorting, sub-location, bulk actions, all item actions, export)
3. **Common Codebase:** Extract table rendering, sorting, pagination, and action handling into shared, reusable components
4. **Maintainability:** Future changes to the item table should require updates in only one location
5. **Preserve Capabilities:** Don't lose functionality - keep all features from both pages
6. **Architectural Decision:** Determine whether to keep separate `/inventory` and `/inventory/search` pages or merge into a single page with collapsible advanced search
7. **Test Refactoring:** Create shared test utilities and page objects for item table testing

## Desired Behavior

### User-Facing Requirements

**Consistent Table Display:**
- Both pages show the same table with identical columns: Checkbox, JA ID, Type, Shape, Material, Dimensions, Length, Location, Sub-location, Status, Actions
- All columns sortable on both pages
- Selection checkboxes available on both pages
- Identical row styling, hover effects, and visual indicators

**Consistent Functionality:**
- Bulk operations (Move, Deactivate, Print Labels) available on both pages
- Full set of item actions (View History, Edit, Shorten, Move, Duplicate, Print Label) on both pages
- CSV export available on both pages
- Pagination works identically on both pages

**Bookmark Functionality:**
- Add "Bookmark" button to main Inventory List page
- Button copies current URL with all active filters/search params
- Works consistently whether using simple filters or advanced search

**Page Structure (To Be Decided During Planning):**
- **Option A:** Keep separate pages with shared table component
  - `/inventory`: Simple filters + item table
  - `/inventory/search`: Advanced search form + same item table
- **Option B:** Merge into single page
  - `/inventory`: Simple filters + collapsible advanced search panel + item table
  - Deprecate or redirect `/inventory/search` → `/inventory`
- Planning phase will investigate pros/cons of each approach

### Technical Requirements

1. **Shared Table Component:**
   - Create `app/static/js/components/inventory-table.js` (or similar)
   - Encapsulates table rendering, sorting, selection, pagination
   - Accepts configuration: data source, filters, callbacks
   - Emits events for user actions (row selected, action clicked, etc.)
   - Reusable across both pages

2. **Shared Template Partial:**
   - Create `app/templates/inventory/_item_table.html` (or similar)
   - Jinja2 template partial/macro for table HTML structure
   - Parameterized for different contexts (list vs search)
   - Includes all columns with proper Bootstrap styling

3. **Action Handling Module:**
   - Create shared module for item action handlers (view history, edit, shorten, move, duplicate, print label)
   - Both pages use the same action code
   - Centralized error handling and success notifications

4. **Backend API Consistency:**
   - Review `/api/inventory/list` and `/api/inventory/search` endpoints
   - Ensure both return consistent item data structure
   - Consider unifying to single endpoint with flexible filtering

5. **Filter State Management:**
   - Implement URL query parameter handling for all filters
   - Enable deep linking (bookmarking) of any filtered/searched state
   - Preserve filter state across page refreshes
   - Support browser back/forward navigation

6. **Page Architecture Decision (During Planning):**
   - Investigate both options (separate pages vs merged page)
   - Consider factors:
     - URL structure and bookmarkability
     - Code complexity and maintainability
     - User workflow and navigation patterns
     - Migration path and backwards compatibility
   - Document decision rationale in implementation plan

7. **Migration Strategy:**
   - Ensure no functionality is lost during refactoring
   - Maintain backwards compatibility with existing bookmarks/links
   - Plan for graceful deprecation if pages are merged

8. **Search Behavior Investigation:**
   - During planning, analyze differences in search/filter capabilities
   - Determine if Advanced Search has unique operators/syntax
   - Ensure all search capabilities are preserved in unified implementation

### Test Requirements

1. **Shared Test Utilities:**
   - Create `tests/e2e/pages/inventory_table_page.py` (or similar)
   - Page object encapsulating all item table interactions
   - Reusable methods: select items, sort columns, apply filters, trigger actions, verify table state
   - Both list and search tests use this shared page object

2. **Refactored E2E Tests:**
   - Identify duplicate test scenarios across `test_inventory_list.py` and `test_inventory_search.py`
   - Extract common test cases to shared test module
   - Parameterize tests to run against both pages where applicable
   - Reduce overall test code volume while maintaining coverage

3. **Comprehensive Coverage:**
   - Table rendering with various filter combinations
   - Column sorting (all columns, ascending/descending)
   - Row selection (single, multiple, all, none)
   - Bulk operations on selected items
   - All individual item actions
   - Pagination with different result set sizes
   - Export functionality
   - Bookmark/deep linking
   - URL parameter handling
   - Search form interactions (if applicable)

4. **Visual Regression Testing:**
   - Verify tables look identical on both pages
   - Verify responsive behavior is consistent
   - Test across different screen sizes

### Non-Goals

- This feature does NOT aim to change the underlying data model or API contracts (beyond minor consistency improvements)
- This feature does NOT aim to add new search capabilities or filters (preserve existing functionality)
- This feature does NOT aim to change the overall layout or navigation structure of the application (only the item table itself)

## Implementation Considerations

### Code Organization

Current structure:
```
app/
├── static/js/
│   ├── inventory-list.js (1,154 lines)
│   └── inventory-search.js (706 lines)
└── templates/inventory/
    ├── list.html (~300 lines)
    └── search.html (~300 lines)
```

Proposed structure (example):
```
app/
├── static/js/
│   ├── components/
│   │   ├── inventory-table.js (NEW - shared table component)
│   │   └── inventory-actions.js (NEW - shared action handlers)
│   ├── inventory-list.js (REFACTORED - much smaller, uses components)
│   └── inventory-search.js (REFACTORED - much smaller, uses components)
└── templates/inventory/
    ├── _item_table.html (NEW - shared table template)
    ├── list.html (REFACTORED - includes _item_table.html)
    └── search.html (REFACTORED - includes _item_table.html)
```

Or, if pages are merged:
```
app/
├── static/js/
│   ├── components/
│   │   ├── inventory-table.js (NEW - shared table component)
│   │   └── inventory-actions.js (NEW - shared action handlers)
│   └── inventory.js (UNIFIED - combines list + search)
└── templates/inventory/
    ├── _item_table.html (NEW - shared table template)
    ├── _search_form.html (NEW - advanced search panel)
    └── index.html (UNIFIED - single page with both simple and advanced search)
```

### Backwards Compatibility

If pages are merged:
- Redirect `/inventory/search` → `/inventory` with query params preserved
- Ensure existing bookmarks continue to work
- Update all internal links in the application

### Performance Considerations

- Shared component should not negatively impact page load time
- Consider lazy loading for advanced search form if pages are merged
- Maintain current pagination behavior (don't load all items at once)

## Decisions Deferred to Planning Phase

The following architectural and implementation decisions will be made during the planning phase after thorough investigation:

1. **Page Structure:** Determine whether to:
   - Keep `/inventory` and `/inventory/search` as separate pages with shared table component, OR
   - Merge into single `/inventory` page with collapsible advanced search panel
   - Consider: URL structure, bookmarkability, code complexity, user workflows, migration path

2. **Search Behavior Differences:** Investigate and document:
   - Whether Advanced Search has unique search operators or syntax not available on Inventory List
   - How to preserve all search capabilities in unified implementation
   - Whether simple filters can be enhanced to cover all advanced search use cases

3. **Backend API Approach:** Decide whether to:
   - Keep separate `/api/inventory/list` and `/api/inventory/search` endpoints with consistent response format, OR
   - Unify to single flexible endpoint that handles both simple and advanced filtering
   - Ensure consistent data structure regardless of approach

4. **Code Organization Strategy:** Choose specific structure for shared components:
   - File naming conventions for shared modules
   - Whether to use class-based or functional approach for table component
   - How to handle component configuration and customization
   - Directory structure for components vs utilities

5. **Migration Path:** Define strategy for:
   - Order of refactoring (backend first vs frontend first vs parallel)
   - Handling existing bookmarks and deep links during transition
   - Whether to implement feature flags for gradual rollout
   - Rollback plan if issues are discovered

## Implementation Plan

*This section will be completed during the planning phase.*

## Progress

*This section will be updated as milestones and tasks are completed.*
