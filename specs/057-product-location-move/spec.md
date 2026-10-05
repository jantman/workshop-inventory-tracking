# Feature Specification: Move Products Between Locations by Scanning

**Feature Branch**: `robot-army/issue-188-location-set-move-for-products`

**Created**: 2026-10-05

**Status**: Draft

**Input**: User description: "Location set / move for products. Inventory items have a dedicated UI (`/inventory/move`) and process for changing their locations, optimized for rapid use with a barcode scanner. We need to develop something similar for Products, taking into account that locations are optional for Products and they may not have an initial location. It should support a similar workflow to the item move UI - scan a product identifier, a location, optionally a sub-location. This gets added to a queue. Validate and preview and then execute. Where possible, refactor existing code for item moves to reduce duplication. (GitHub issue #188)"

## Background

Inventory items (stock identified by a `JA######` label) have a Move page built for a
barcode scanner: scan an item, scan a location, optionally scan a sub-location, repeat; the
moves pile up in a queue, are validated and previewed, and are then applied together.

Products (catalog entries for supplies, identified on their printed label by an internal
product code beginning `WIT`) have a location and a sub-location too, but both are optional,
many products have never been given one, and the only way to change them today is the
product's full edit form, one product at a time. Shelving a box of newly labelled products
means opening and saving that form for each one.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Shelve products by scanning (Priority: P1)

The owner has a handful of labelled products to put away — some new and never located,
some being moved. On the product Move page they scan a product label, scan the location
label, optionally scan or type a sub-location, and go on to the next product. Each product
joins a queue showing where it is now and where it is going. When done, they validate the
queue, check the preview, and apply it; every product's location is updated at once.

**Why this priority**: This is the whole feature. Without it the owner has to open the edit
form for every product.

**Independent Test**: Seed two products, one with a location and one without. On the
product Move page, scan product A, a location and a sub-location; scan product B and a
location; validate and execute. Both products show their new location and sub-location on
their detail pages.

**Acceptance Scenarios**:

1. **Given** a product with no location, **When** the owner scans its code then `M1-A`,
   then finishes the queue, **Then** the queue shows its current location as "none" (not an
   error and not "Unknown") and its new location as `M1-A`.
2. **Given** a product at `M2` / `Bin 4`, **When** the owner scans its code, `T-3`, and
   `Drawer 1`, **Then** the queue shows current `M2` / `Bin 4` and new `T-3` / `Drawer 1`.
3. **Given** a queue of moves, **When** the owner validates, **Then** every entry is checked
   against the current catalog and marked valid or with the reason it is not.
4. **Given** a validated queue, **When** the owner executes it and confirms, **Then** each
   valid product's location and sub-location are replaced by the queued values and the page
   reports how many moved and which, if any, failed.
5. **Given** a queued move with no sub-location scanned, **When** it is executed, **Then**
   the product's previous sub-location is cleared, and the queue shows this before
   execution.

---

### User Story 2 - Scanner mistakes are caught before anything changes (Priority: P2)

The owner works fast and the scanner misreads, double-scans, or the owner scans labels in
the wrong order. The page refuses input that doesn't fit the current step, says why, and
never applies a move until the owner validates and confirms.

**Why this priority**: A wrong location recorded silently is worse than no location — the
product becomes unfindable. The item Move page already learned these lessons; products
should not relearn them.

**Independent Test**: On the product Move page, scan a location first, scan an unknown
product code, scan the same product twice, and scan a product then another product; each is
refused or handled with a visible message, and the queue holds only what was intended.

**Acceptance Scenarios**:

1. **Given** the page is waiting for a product, **When** a location is scanned, **Then** it
   is refused with a message and nothing is queued.
2. **Given** a product code that matches no product, **When** the queue is validated,
   **Then** that entry is marked "not found" and Execute stays unavailable until it is
   removed — exactly as an unknown item is handled on the item Move page.
3. **Given** a product already in the queue, **When** it is scanned again, **Then** it is
   refused as a duplicate.
4. **Given** a product has been scanned but no location yet, **When** another product is
   scanned, **Then** the first is abandoned with a warning and the second becomes current.
5. **Given** a product and location are scanned, **When** a second location is scanned,
   **Then** it is refused ("two locations in a row").
6. **Given** a move is half-entered, **Then** Validate stays disabled and the page says what
   is missing.
7. **Given** a queue entry is wrong, **When** the owner removes it or clears the queue,
   **Then** it is gone and will not be applied.
8. **Given** a product queued and then deleted from the catalog before execution, **When**
   the queue is validated or executed, **Then** that entry fails with "not found" and the
   rest still move.

---

### User Story 3 - Start a move from a product's page (Priority: P3)

Looking at a product's detail page, the owner can jump straight to the product Move page
with that product already scanned, so only the location remains to scan.

**Why this priority**: Convenient, but the scanning workflow stands alone without it.

**Independent Test**: From a product detail page, follow its Move action; the Move page
opens waiting for a location with that product current.

**Acceptance Scenarios**:

1. **Given** a product detail page, **When** the owner follows its Move action, **Then** the
   product Move page opens with that product current and the page waiting for a location.

---

### Edge Cases

- A product whose location is empty but sub-location is set: shown as current location
  "none" with its sub-location; moving it replaces both.
- Scanning a product's code in lower case or with surrounding whitespace: treated as the
  same code.
- Scanning an inventory item's `JA` label on the product Move page: refused with a message
  pointing to the item Move page; it is never taken as a sub-location.
- Moving a product to the location it is already at with a different sub-location: allowed;
  only the sub-location changes.
- The scanner's terminating `>>DONE<<` code and its trailing Enter behave exactly as on the
  item Move page.
- A scan typed by hand in manual-entry mode is processed on Enter, as on the item Move page.
- Executing a queue where every entry failed validation: nothing is sent and the owner is
  told.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The application MUST provide a product Move page, reachable from the Products
  navigation menu, that takes input from a keyboard-wedge barcode scanner or the keyboard.
- **FR-002**: The page MUST recognize a product by its internal product code (the `WIT` code
  printed on its label), case- and whitespace-insensitively.
- **FR-003**: The page MUST recognize location labels by the same rules as the item Move page,
  and treat any other input in the sub-location step as a sub-location.
- **FR-004**: The scan sequence MUST be: product, location, then optionally a sub-location;
  scanning the next product completes the previous move without a sub-location.
- **FR-005**: Each completed scan sequence MUST add an entry to a queue showing the product's
  description and code, its current location and sub-location (shown as "none" when unset),
  and its new location and sub-location, with a visible marker when an existing sub-location
  will be cleared.
- **FR-006**: The page MUST refuse, with a visible message, input that does not fit the
  current step (location before product, two locations in a row, a sub-location before a
  location), an inventory item label, and a product already queued. A well-formed product
  code that matches no product MUST be caught at validation and marked not found.
- **FR-007**: The owner MUST be able to remove a single queue entry and clear the whole queue.
- **FR-008**: Validation MUST re-check every queued product against the catalog and mark each
  entry valid or failed with a reason; Validate MUST stay disabled while a move is
  half-entered.
- **FR-009**: Execution MUST require confirmation, MUST apply only validated entries, MUST set
  each product's location to the queued location and its sub-location to the queued
  sub-location (clearing it when none was queued), and MUST report the number moved and each
  failure with its reason. A failure of one entry MUST NOT prevent the others.
- **FR-010**: Execution MUST NOT change any product attribute other than location and
  sub-location.
- **FR-011**: Each product detail page MUST offer a Move action opening the product Move page
  with that product already current.
- **FR-012**: The item Move page's behavior MUST be unchanged by this feature, except that
  validation MUST keep the item's real current location and name rather than replacing them
  with "Unknown" and the JA ID (an existing defect the shared code would otherwise carry into
  the product page).
- **FR-013**: The scanning, queue, validation and execution behavior common to both pages
  MUST be implemented once and shared, with only what genuinely differs (how the thing being
  moved is recognized, looked up, labelled and saved) supplied separately for items and for
  products.

### Key Entities

- **Product**: a catalog entry; identified on its label by an internal product code; has an
  optional location and an optional sub-location, both free text.
- **Product move (queue entry)**: a product, its current location and sub-location at the
  time of scanning, the destination location and optional sub-location, and a status
  (pending, validated, failed with reason).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The owner can shelve ten labelled products — scan, validate, execute — without
  opening any product's edit form, in no more scans than one product label, one location
  label, and an optional sub-location per product, plus one finish.
- **SC-002**: A product with no prior location can be given one through this page on the
  first attempt, with no error shown.
- **SC-003**: None of the refused-input cases in User Story 2 changes any product's stored
  location.
- **SC-004**: Every existing automated test of the item Move page still passes with its
  assertions about what the owner sees unchanged; only references to the page's internal
  state names may be updated.
- **SC-005**: The logic shared between item and product moves exists in one place: a change
  to the scan state machine or queue behavior is made once and takes effect on both pages.

## Assumptions

- The product identifier scanned is the internal `WIT` product code, because that is what the
  application prints on product labels. Manufacturer part numbers, GTINs and vendor codes are
  not accepted on this page: they cannot be told apart from a free-text sub-location, which
  would make the scan sequence ambiguous.
- Location labels follow the same patterns the item Move page uses; there is no registry of
  locations to check against, matching current item behavior.
- Moving a product replaces its sub-location, exactly as moving an item does. Clearing a
  product's location entirely (back to none) is not a goal; the edit form already does that.
- Bulk hand-off from the product search results (selecting many products and moving them
  together) is out of scope for this feature; the single-product hand-off in User Story 3 is
  in scope.
- Products have no history or audit trail today; this feature does not add one. A move
  updates the product in place, as the edit form does.
- No schema change is needed: products already store an optional location and sub-location.
