# Feature Specification: Products Table Location Columns and Width

**Feature Branch**: `robot-army/issue-212-products-needs-action-improvements`

**Created**: 2026-10-15

**Status**: Draft

**Input**: User description: "Products Needs Action Improvements (GitHub issue #212). The "Needs Action" Products view (`/products?missing=either`) is confusing because the table does not include location, and therefore it's unclear what action a product needs if it has a category but is missing a location. The products table should be updated (in all views of the products table) to include location and sub-location. We should also scale the width of the products table (and if needed the container it's inside) better; for example, in a browser with a 1920x929 px viewport, the products table is only 1294px wide. If this made better use of the full width of the page, it would be easier to add the extra columns for location and sub-location. Ensure the page still renders on tablets and mobile devices (phones) but these are currently an edge case for the app, so we should optimize for a desktop computer. The primary device currently used for this application is my workshop computer, which has a browser viewport of 1920x915."

## Background

The product list (`/products`, reached as Products → All Products, Products → Needs Action, and every search or filter of it) is one page with one table. That table already carries a "Location" heading, with the sub-location tacked onto the same cell in small muted text. On the operator's workshop screen it does not read that way: the page is held to a fixed maximum width of roughly 1300px on a 1920px screen, the table is allowed to scroll sideways inside that, and long descriptions with tag badges push the columns at the right — Location among them — out of view. The operator does not see a location column at all, so on the Needs Action view a product that has a category gives no clue what it is missing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See location and sub-location for every product in the list (Priority: P1)

The operator opens the product list — in any of its views, and especially Products → Needs Action — and sees for each product its location and its sub-location in their own clearly headed columns, so a product listed as needing action because it has no location is recognizable at a glance by its empty Location cell.

**Why this priority**: This is the confusion the issue reports. Without it the Needs Action view does not say what action is needed.

**Independent Test**: Seed products with a category and location and sub-location, a category and no location, and no category; open each view of the product list and confirm the Location and Sub-location columns are present, headed, and show each product's values (blank where unset).

**Acceptance Scenarios**:

1. **Given** a product with location "Shelf A" and sub-location "Bin 3", **When** the operator opens the product list, **Then** its row shows "Shelf A" under a "Location" heading and "Bin 3" under a separate "Sub-location" heading.
2. **Given** a product with a category but no location, **When** the operator opens Products → Needs Action, **Then** the product is listed with its category shown and its Location cell visibly empty.
3. **Given** a product with a location but no sub-location, **When** the list is shown, **Then** the Location cell shows the location and the Sub-location cell is empty.
4. **Given** any combination of the existing filters (search text, category, tag, stock, specification, missing), **When** the list is shown, **Then** the same Location and Sub-location columns are shown — there is one table, not one per view.
5. **Given** a list with no matching products, **When** it is shown, **Then** the "Nothing here matches." message still spans the whole table.

---

### User Story 2 - The product list uses the width of a desktop screen (Priority: P2)

On the workshop computer (viewport 1920×915) the product list fills most of the screen's width rather than a narrow centered band, so all of its columns — including the new ones — are visible without sideways scrolling.

**Why this priority**: It is what makes room for the extra column and is what actually keeps Location in view; but the columns of Story 1 are the substance.

**Independent Test**: Open the product list in a 1920×915 viewport with products that have long descriptions and several tags; measure the table width and confirm every column header is within the visible area with no horizontal scroll.

**Acceptance Scenarios**:

1. **Given** a 1920×915 viewport, **When** the operator opens the product list, **Then** the product table is at least 1800px wide.
2. **Given** a 1920×915 viewport and products with long descriptions and tags, **When** the list is shown, **Then** the table does not scroll horizontally and the Location, Sub-location and Quantity columns are fully in view.
3. **Given** a tablet-width viewport (about 768px) or a phone-width viewport (about 390px), **When** the operator opens the product list, **Then** the page still renders usably: the filters stack, every column remains reachable (horizontal scrolling of the table is acceptable at these sizes), and the page itself does not overflow sideways.

---

### Edge Cases

- A location or sub-location consisting only of whitespace is shown as blank (as it is treated as missing by the Needs Action filter).
- Very long location or sub-location text wraps within its cell rather than widening the table past the screen on a desktop.
- Other pages that use the shared catalog layout (product detail, orders, categories, etc.) are not changed by this feature unless they render this same product table.
- Selecting rows, Print Labels and Set Category continue to work with the extra column present.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product list table MUST show a "Location" column containing only the product's location.
- **FR-002**: The product list table MUST show a separate "Sub-location" column containing only the product's sub-location.
- **FR-003**: An unset location or sub-location MUST be shown as an empty cell.
- **FR-004**: FR-001–FR-003 MUST hold for every view of the product list: unfiltered, Needs Action, and any combination of search and filters.
- **FR-005**: The "no matching products" row MUST span every column of the table.
- **FR-006**: On a 1920px-wide viewport the product list page's content, including the table, MUST use substantially the full width of the window (table at least 1800px wide).
- **FR-007**: On a 1920×915 viewport the product table MUST NOT need horizontal scrolling to reveal any column for typical catalog content (descriptions with tags, category paths, locations).
- **FR-008**: On tablet and phone widths the product list MUST still render without the page itself overflowing horizontally; the table may scroll horizontally within its own area.
- **FR-009**: The width change MUST be confined to the product list page; other pages keep their current layout.
- **FR-010**: Existing product-list behavior — row selection, Print Labels, Set Category, filters and their persistence — MUST be unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the Needs Action view, the operator can tell for 100% of listed products whether the missing piece is the category, the location, or both, without opening the product.
- **SC-002**: In a 1920×915 viewport the product table is at least 1800px wide (up from about 1294px).
- **SC-003**: In a 1920×915 viewport, all column headers of the product table are visible without horizontal scrolling.
- **SC-004**: At 768px and 390px widths the page shows no horizontal page-level scroll bar.

## Assumptions

- "All views of the products table" means every way of reaching the `/products` list (All Products, Needs Action, and searches/filters of it); it is one template. Other tables that list products for a different purpose (Reorder List, Outstanding Products, order pages) are out of scope.
- Splitting the existing combined Location cell into two columns satisfies "include location and sub-location"; no data or filter changes are needed.
- Desktop at 1920px wide is the optimization target; tablet and phone need only remain usable.
- No sorting, column toggling or column configuration is added.
