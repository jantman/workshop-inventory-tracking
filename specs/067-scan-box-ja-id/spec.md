# Feature Specification: JA IDs in the Header Scan Box

**Feature Branch**: `robot-army/issue-215-add-ja-id-support-to-the-header-scan`

**Created**: 2026-10-22

**Status**: Draft

**Input**: GitHub issue #215: "Add JA ID support to the header scan box and remove the JA ID Quick Lookup box"

## Context

The header carries two input boxes side by side. The **scan box** accepts anything the
product catalog can recognize (internal codes, distributor 2D labels, retail barcodes, vendor
item ids, free text) and always ends at a product, a draft, a receipt or a search. The **JA ID
Quick Lookup** box predates the catalog; it accepts only a JA ID and opens that inventory
item's edit page.

No spec records a decision to keep two boxes. Today a JA ID entered in the scan box is treated
as free text and ends up in a product search, so the operator has to know which box to use.
This feature makes the scan box the one place to scan or type a code, and removes the second
box.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scan a JA ID into the header scan box (Priority: P1)

The operator, on any page, scans an inventory item's JA ID label (or types the JA ID and
presses Enter) into the header scan box, and lands on that item's edit page — the same place
the JA ID Quick Lookup box used to take them.

**Why this priority**: This is the behavior that must exist before the old box can be removed;
without it, removing the box loses a capability.

**Independent Test**: Seed an inventory item, enter its JA ID in the header scan box, and
confirm the item's edit page opens.

**Acceptance Scenarios**:

1. **Given** an active inventory item `JA200001`, **When** the operator enters `JA200001` in
   the header scan box and presses Enter, **Then** the edit page for `JA200001` opens.
2. **Given** an inactive (historical) item `JA300002` with no active row, **When** the operator
   enters `JA300002`, **Then** the edit page for `JA300002` opens, as it did from the old box.
3. **Given** no item `JA999999` exists, **When** the operator enters `JA999999`, **Then** they
   are told the item was not found (the same answer the old box gave), not sent to a product
   search.
4. **Given** the operator types `ja200001` in lowercase, **When** they press Enter, **Then**
   the edit page for `JA200001` opens.

---

### User Story 2 - One box in the header (Priority: P2)

The header shows a single scan box. The JA ID Quick Lookup box, its styling and its handler
are gone, and nothing in the user documentation or keyboard-shortcut help mentions it.

**Why this priority**: The cleanup only makes sense after Story 1 lands, and on its own it
removes a capability.

**Independent Test**: Load any page and confirm the header contains the scan box and no JA ID
lookup box.

**Acceptance Scenarios**:

1. **Given** any page, **When** it renders, **Then** the header contains the scan box and does
   not contain the JA ID Quick Lookup box.
2. **Given** the user manual, **When** the operator reads the scanning section, **Then** it
   says that a JA ID scanned in the header opens that item.

---

### Edge Cases

- A JA ID with surrounding whitespace (a scanner terminator) still opens the item.
- Something that only looks like a JA ID — wrong digit count (`JA12345`, `JA1234567`), or extra
  text (`JA000123 bolt`) — is not a JA ID and keeps today's behavior (a search, or whatever
  other rule matches).
- Every existing scan type (internal code, distributor label, retail barcode, vendor id, free
  text) resolves exactly as before; JA IDs do not overlap any of their shapes.
- Scan-path consumers that assumed every resolution ends at a product (the scan API's response
  shape, its tests, the scan contract) are updated to the new answer rather than broken by it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The header scan box MUST recognize a JA ID — `JA` followed by exactly six digits,
  ignoring case and surrounding whitespace — and send the operator to that inventory item's
  edit page.
- **FR-002**: JA ID recognition MUST NOT change how any other scan resolves.
- **FR-003**: A JA ID that matches no item MUST produce the same "not found" answer the old
  lookup box produced; it MUST NOT fall through to a product search.
- **FR-004**: A JA ID for an item that has only inactive history MUST open that item's edit
  page, as the old lookup box did.
- **FR-005**: The JA ID Quick Lookup box MUST be removed from the header, together with the
  code, styling and tests that exist only to serve it.
- **FR-006**: The scan API's documented answer MUST describe the new outcome, so the contract
  no longer claims every resolution ends at a product.
- **FR-007**: The user manual MUST describe JA IDs in the scan section and MUST NOT mention the
  removed box.

### Key Entities

- **Scan resolution**: the answer to a scan. Gains one new outcome, "inventory item", carrying
  the normalized JA ID.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From any page, an operator reaches an item's edit page from its JA ID in one scan
  or one typed entry, with no choice of box to make.
- **SC-002**: The header has exactly one code-entry box.
- **SC-003**: Every scan type that resolved before this feature resolves to the same place
  after it (all existing scan tests pass unchanged except where they asserted the removed box).
- **SC-004**: No reference to the JA ID Quick Lookup box remains in the application, its tests
  or its user documentation.

## Assumptions

- The old box navigated straight to the edit page without checking that the item exists, and
  the edit page already answers a missing item with a "not found" message. Keeping that path
  satisfies FR-003 and FR-004 without a new lookup.
- Lowercase acceptance is carried over from the old box, which uppercased its input.
- The scan box's visible width and placeholder may change slightly to signal that it now takes
  JA IDs; no other header layout change is in scope.
- Frozen specs under `specs/` are not rewritten except where this feature's own contract
  supersedes them.
