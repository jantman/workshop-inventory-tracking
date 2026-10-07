# Feature Specification: Free-Text Locations on the Product Move Page

**Feature Branch**: `robot-army/issue-195-fix-for-189-product-locations-are-free`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Issue #195 — Fix for #189 - Product locations are free-form text. #189 implemented scan-to-move support for Products similar to Items. However, while Item storage locations are `M*`, `T*`, or `Other`, Product storage locations are free-form strings. So I try to move a product (either via bulk move or via the \"Move\" button on the product view) and scan a location barcode such as `WoodshopShelf` or `eShop Shelf3` and I get a warning box reading, `1 product is waiting for a destination, and a sub-location is not one. Please scan the location they are going to (M*, T*, or Other).`"

## Background

Feature 057 (#188, PR #189) gave products the same scan-driven Move page as inventory items.
The page decides what a scan *is* by its shape: a JA ID or product code is the thing being
moved, `M…`, `T…` or `Other` is a location, and anything else is a sub-location. That rule is
right for inventory items, whose storage locations follow that convention. A product's
location is free text — `WoodshopShelf`, `eShop Shelf3` — so on the product page a real
product location is taken for a sub-location and refused wherever a location is expected.
Both ways onto the page are affected: scanning a product code by hand, and arriving with
products already chosen (the Move button on a product, or a bulk selection).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Move chosen products to a free-text location (Priority: P1)

The owner opens a product, presses Move, and scans the `WoodshopShelf` barcode. The product
is queued for `WoodshopShelf`. The same holds for several products chosen together from the
product list.

**Why this priority**: This is the path the issue reports failing, and it fails with no
workaround — no free-text location is ever accepted.

**Independent Test**: Open the Move page with one product preselected, scan
`eShop Shelf3`, finish, validate and execute; the product's location reads `eShop Shelf3`.

**Acceptance Scenarios**:

1. **Given** the Move page with one product preselected and waiting for a destination,
   **When** the owner scans `WoodshopShelf`, **Then** the product is queued with new location
   `WoodshopShelf` and no warning is shown.
2. **Given** that product queued, **When** the owner then scans `Top Bin`, **Then** `Top Bin`
   becomes its new sub-location.
3. **Given** two products preselected, **When** the owner scans `eShop Shelf3`, **Then** both
   are queued for `eShop Shelf3`.

---

### User Story 2 - Scan products by hand to a free-text location (Priority: P1)

On the product Move page with nothing preselected, the owner scans a product code, then
`WoodshopShelf`, then optionally `Drawer 2`, then the next product code.

**Why this priority**: The same defect on the page's other entry path.

**Independent Test**: Scan code, `WoodshopShelf`, `Drawer 2`, `>>DONE<<`; the queued row reads
`WoodshopShelf` / `Drawer 2`, and executing the move records both.

**Acceptance Scenarios**:

1. **Given** a product code has just been scanned, **When** the owner scans `WoodshopShelf`,
   **Then** it is taken as that product's new location.
2. **Given** a location has just been scanned, **When** the owner scans `Drawer 2`, **Then**
   it is taken as the sub-location, as today.
3. **Given** a location has just been scanned, **When** the owner scans the next product
   code, **Then** the first move is queued with no sub-location, as today.

---

### User Story 3 - The inventory item Move page is unchanged (Priority: P2)

Inventory items keep their location convention: on the item Move page, `WoodshopShelf` where a
location is expected is still refused, and `M1-A`, `T-5` and `Other` are still locations.

**Why this priority**: The fix must not loosen the item page, where the convention is what
catches a mis-scan.

**Independent Test**: The existing item Move page tests pass unchanged.

**Acceptance Scenarios**:

1. **Given** the item Move page waiting for a location, **When** `WoodshopShelf` is scanned,
   **Then** it is refused as a sub-location exactly as before.

### Edge Cases

- On the product page, a scan shaped like an item location (`M1-A`, `T-3`, `Other`) is still
  a location, so scanning one where a sub-location could go still reports "two locations in
  a row" as it does today.
- On the product page, free text while waiting for a product code (before any product is
  scanned) is still refused: there is nothing for it to be the location of.
- A JA ID on the product page is still refused in every state, never taken as a location.
- Prompts and warnings on the product page do not tell the owner to scan `M*, T*, or Other`;
  that convention is the item page's.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: On the product Move page, when the page is waiting for a location — after a
  product code, or for a preselected group — any scan that is not a product code, a JA ID or
  `>>DONE<<` MUST be accepted as the location, whatever its shape.
- **FR-002**: On the product Move page, when the page is waiting for a sub-location or the
  next product code, free text MUST be taken as the sub-location (unchanged), and a scan
  shaped like an item location (`M…`, `T…`, `Other`) MUST still be reported as two locations
  in a row (unchanged).
- **FR-003**: On the product Move page, free text while waiting for a product code MUST still
  be refused (unchanged).
- **FR-004**: The product Move page's instructions, status lines and warnings MUST NOT
  describe locations as `M*, T*, or Other`; they MUST describe a location as free text.
- **FR-005**: The inventory item Move page's classification, wording and behavior MUST be
  unchanged.

### Key Entities

- **Product location / sub-location**: free text on a product; no format is imposed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Both scans in the issue — `WoodshopShelf` and `eShop Shelf3` — are accepted as a
  product's new location from both entry paths (preselected and hand-scanned), and the
  executed move records them.
- **SC-002**: No warning on the product Move page mentions `M*, T*, or Other`.
- **SC-003**: Every existing item and product Move page test still passes.

## Assumptions

- What a scan means on the product page is decided by what the page is waiting for, not by
  the scan's shape, except that product codes, JA IDs, `>>DONE<<` and item-shaped locations
  keep their existing meaning. No list of known product locations is consulted: a new
  location must be usable the first time it is scanned.
- One consequence is accepted: on the product page, a free-text location cannot be corrected
  by scanning a second location straight after it — the second is taken as the sub-location.
  The queue's Remove button corrects it, as for any other mistaken move.
- The server already accepts any non-empty location for products; no server change is needed.
