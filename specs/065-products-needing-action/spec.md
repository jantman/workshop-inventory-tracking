# Feature Specification: Products Needing Action

**Feature Branch**: `robot-army/issue-209-products-needing-action-page`

**Created**: 2026-10-13

**Status**: Draft

**Input**: User description: "Products Needing Action page (GitHub issue #209). Add filter options to the `/products` view to filter to products that have no category set and/or have no location set. Then, add a "Needs Action" link to the Products top navbar menu that navigates to the `/products` page filtered to products that are missing a category and/or location. The purpose of this is to make it easy to locate products that need to have their category and/or location set, and then for the user to provide that information (using existing methods)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Filter the product list to products missing a category or location (Priority: P1)

Products arrive in the catalog by many routes (order captures, DigiKey captures, scans) and many of them land without a category or without a location. The operator wants to narrow the product list to just those products so they can fill the gaps in, instead of scrolling the whole catalog looking for blank cells.

**Why this priority**: This is the capability the whole feature rests on; the navbar link in Story 2 is a shortcut to it.

**Independent Test**: With a catalog containing products that have both, only a category, only a location, and neither, choose each option of the new filter on the product list and confirm exactly the expected products are listed.

**Acceptance Scenarios**:

1. **Given** products A (category and location), B (no category), C (no location) and D (neither), **When** the operator filters to "no category", **Then** B and D are listed and A and C are not.
2. **Given** the same products, **When** the operator filters to "no location", **Then** C and D are listed and A and B are not.
3. **Given** the same products, **When** the operator filters to "missing category or location", **Then** B, C and D are listed and A is not.
4. **Given** the filter is set, **When** the operator also applies another existing filter (search text, category, tag, stock, specification), **Then** both filters apply together and the new filter's selection stays shown on the page.
5. **Given** the filter is set to "Any" (the default), **When** the list is shown, **Then** it is exactly what the list showed before this feature.

---

### User Story 2 - "Needs Action" shortcut in the Products menu (Priority: P2)

From anywhere in the app, the operator opens the Products menu and picks "Needs Action", landing on the product list already filtered to products missing a category or a location.

**Why this priority**: Makes the triage list one click away, which is the point of the issue, but it depends on Story 1.

**Independent Test**: Click Products → Needs Action from any page and confirm the product list opens with the "missing category or location" filter selected and only such products shown.

**Acceptance Scenarios**:

1. **Given** any page, **When** the operator opens the Products menu, **Then** a "Needs Action" entry is present.
2. **Given** products A–D above, **When** the operator picks "Needs Action", **Then** the product list opens showing B, C and D, with the filter visibly set to "missing category or location".

---

### User Story 3 - Fix the gaps with existing tools and watch the list shrink (Priority: P3)

From the filtered list the operator sets the missing information using the methods that already exist (the bulk "Set Category" action on the list, editing a product, or moving products to a location). When the list is shown again, the products that were fixed are no longer on it.

**Why this priority**: No new editing capability is introduced; this story only confirms the filter composes with the existing ones.

**Independent Test**: On the "no category" filtered list, select products, use Set Category, and reload; the categorized products are gone from the list.

**Acceptance Scenarios**:

1. **Given** the list filtered to "no category", **When** the operator sets a category on some listed products with the existing bulk action and the list is shown again, **Then** those products no longer appear and the filter is still applied.
2. **Given** a product listed under "no location", **When** the operator gives it a location by an existing method, **Then** it no longer appears under that filter.

### Edge Cases

- A category or location that is blank (empty or whitespace only) is treated the same as not set.
- A product with a sub-location but no location counts as having no location.
- An unrecognized value for the new filter shows a message naming the valid choices and an empty list, the same way the existing Stock filter treats an unknown value.
- When no product needs action, the list shows the existing empty-list message.
- Combining "no category" with the existing Category filter yields an empty list; that is correct and needs no special handling.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product list MUST offer a filter for missing information with the choices: Any (default), No category, No location, and Missing category or location.
- **FR-002**: "No category" MUST list exactly the products whose category is not set or blank.
- **FR-003**: "No location" MUST list exactly the products whose location is not set or blank, regardless of sub-location.
- **FR-004**: "Missing category or location" MUST list exactly the products that match "No category" or "No location" (or both).
- **FR-005**: The new filter MUST combine with every existing product-list filter (all applied together), and "Any" MUST leave the list unchanged from current behavior.
- **FR-006**: The chosen filter MUST be reflected in the page address so the filtered list can be linked to, bookmarked and reloaded, and MUST remain selected in the filter controls after the list is shown.
- **FR-007**: The Products navigation menu MUST contain a "Needs Action" entry that opens the product list filtered to "Missing category or location".
- **FR-008**: An unrecognized filter value MUST produce a message naming the valid values (not a crash), consistent with the existing Stock filter.
- **FR-009**: The existing bulk actions on the product list (Print Labels, Set Category) MUST continue to work on the filtered list.

### Key Entities

- **Product**: A catalog entry. Relevant attributes: category (optional), location (optional), sub-location (optional).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From any page, the operator reaches the list of products needing a category or location in one menu selection.
- **SC-002**: For any mix of products, each filter choice lists 100% of the matching products and none that do not match.
- **SC-003**: After a listed product's missing information is supplied, it is absent from the list the next time the list is shown.
- **SC-004**: With the filter at its default, the product list is unchanged from before this feature.

## Assumptions

- "Needs action" means exactly "missing a category or a location"; no other criteria (e.g., missing photos, quantities) are included.
- A single choice filter with an explicit "or" option is used rather than two independent checkboxes, so it is never ambiguous whether two selections mean "both" or "either". A "missing both" choice is not offered; the issue does not call for it.
- No new page or editing capability is introduced; supplying the missing information uses the existing bulk Set Category action, the product edit page, and Move Products.
- The product list's existing result limit applies to the filtered list as well.
