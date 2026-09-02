# Feature Specification: Manage Product Identifiers After Creation

**Feature Branch**: `speckit/036-manage-product-identifiers`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "issue #136 on this repo"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Make an already-cataloged product scannable (Priority: P1)

The operator is holding a product whose barcode the catalog does not recognize. Scanning it
falls through to a free-text search, so the app appears not to know about the product at all.
Opening that product's detail page, the operator adds the barcode as a `GTIN` identifier
directly on the Identifiers card and the identifier appears in the list without leaving the
page. Scanning or typing that code afterwards lands on the product.

**Why this priority**: This is the reported defect. Three cataloged products today carry a
valid UPC recorded as a specification row and no `GTIN` identifier, and there is currently no
way to fix that short of hand-crafting an API call. Everything else in this feature is an
extension of the same control.

**Independent Test**: Take a cataloged product with no `GTIN` identifier, add one of the three
recorded UPCs through the detail page, then look the product up by that code and confirm it is
found. Delivers the whole of the reported value on its own.

**Acceptance Scenarios**:

1. **Given** a cataloged product with no `GTIN` identifier, **When** the operator adds a valid
   barcode as a `GTIN` on the product's detail page, **Then** the identifier appears in the
   Identifiers card with its type and stored value, and is still there after a page reload.
2. **Given** the identifier from scenario 1, **When** that code is scanned or typed into the
   catalog lookup, **Then** the lookup lands on that product.
3. **Given** a barcode whose check digit does not pass, **When** the operator adds it without
   asking to store it anyway, **Then** it is refused with a message naming the reason and
   nothing is stored.
4. **Given** the same failing barcode, **When** the operator explicitly asks to store it
   anyway, **Then** it is stored and the card shows it as validation-overridden.
5. **Given** a barcode that reads as all zeros, **When** the operator tries to add it —
   with or without asking to store it anyway — **Then** it is refused as a scanner no-read.
6. **Given** a value that already belongs to a different product, **When** the operator adds
   it, **Then** it is refused with a message naming the product that already claims it, and
   that product is reachable from the message.

---

### User Story 2 - Remove an identifier that is wrong (Priority: P2)

The operator sees an identifier on a product that does not belong there — mistyped at
creation, captured from the wrong label, or belonging to a product that has since been split.
Each listed identifier carries a remove control; using it detaches the identifier after a
confirmation, and the product itself is untouched.

**Why this priority**: Without removal, a wrong identifier is permanent and a mistyped add
from User Story 1 cannot be undone. It is second only because a product with a wrong extra
identifier is still findable, whereas one with no identifier is not.

**Independent Test**: Add an identifier to a product, remove it, and confirm it is gone from
the card, gone after a reload, and that the product still exists with its internal code.

**Acceptance Scenarios**:

1. **Given** a product with two non-internal identifiers, **When** the operator removes one
   and confirms, **Then** that row disappears from the card and the other remains.
2. **Given** a product whose only non-internal identifier is removed, **When** the page is
   reloaded, **Then** the product is still in the catalog, still shows its internal code, and
   the card reports that there are no other identifiers.
3. **Given** the remove control, **When** the operator declines the confirmation, **Then**
   nothing is removed.
4. **Given** an identifier already removed in another browser tab, **When** the operator
   removes it here, **Then** the outcome is reported as a successful removal rather than an
   error — the requested state is the state that holds.
5. **Given** the internal code, **When** the operator looks at the card, **Then** there is no
   remove control for it.

---

### User Story 3 - Record an identifier learned after the fact (Priority: P3)

A manufacturer part number turns up on a datasheet, or a second vendor's item number turns up
on an invoice, months after the product was cataloged. The operator adds it with the right
type, supplying the vendor where the type requires one, so a later scan or search from either
source finds the same product.

**Why this priority**: Real, and the reason this is not purely a backfill fix, but less
pressing than the barcode case: these codes are usually searched by hand rather than scanned.
It is a distinct slice because the vendor-scoped types carry a requirement the barcode case
does not.

**Independent Test**: Add a `VENDOR` identifier with a vendor to an existing product and
confirm it is listed with its vendor shown; attempt the same without a vendor and confirm it
is refused.

**Acceptance Scenarios**:

1. **Given** an existing product, **When** the operator adds an `MPN` identifier, **Then** it
   is stored and listed with its type badge.
2. **Given** an existing product, **When** the operator adds a `VENDOR` or `DISTRIBUTOR`
   identifier without a vendor, **Then** it is refused with a message saying a vendor is
   required for that type, and nothing is stored.
3. **Given** the same add with a vendor supplied, **When** it is submitted, **Then** it is
   stored and the card shows the vendor beneath the value.
4. **Given** the type chooser, **When** the operator opens it, **Then** it offers the same
   types the Add Product form offers and does not offer the internal type.

---

### Edge Cases

- **The value is already on this same product.** Adding a value the product already carries
  must leave the product with one such identifier, not two, and must not read as a failure.
- **The stored value differs from what was typed.** A barcode is normalized before storage, so
  the card may show a longer key than the operator entered. The card shows what is stored.
- **Empty or whitespace-only value.** Refused; nothing is stored and the form stays open with
  what was entered.
- **The product was deleted in another tab.** An add against a product that no longer exists
  reports that the product was not found rather than appearing to succeed.
- **A refusal must not lose the operator's typing.** After any refusal the entered type, value
  and vendor are still in the form to correct.
- **Removing every identifier.** Allowed. Identity is the product row, never one of its names.
- **The internal code.** Neither removable nor offerable as a type to add.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product detail view MUST offer a control to add an identifier to that
  product, alongside the existing list of its identifiers.
- **FR-002**: The add control MUST accept an identifier type, a value, an optional vendor, and
  an explicit opt-in to store a barcode that fails validation.
- **FR-003**: The type choices offered MUST be the same set the Add Product form offers, and
  MUST NOT include the internal type.
- **FR-004**: An identifier added after creation MUST be subject to exactly the same
  validation, normalization and duplicate rules as one supplied at creation — there is one
  rule set, not two.
- **FR-005**: A barcode whose check digit passes MUST be stored in its normalized form and not
  marked as overridden.
- **FR-006**: A barcode whose check digit fails MUST be refused unless the operator explicitly
  opted in, and MUST be marked as validation-overridden when stored under that opt-in.
- **FR-007**: A barcode reading as all zeros MUST be refused regardless of the opt-in.
- **FR-008**: A vendor-scoped identifier type MUST be refused when no vendor is given.
- **FR-009**: A value that already belongs to a different product MUST be refused, and the
  refusal MUST name that product and let the operator reach it.
- **FR-010**: Adding a value the same product already carries MUST leave exactly one such
  identifier and MUST NOT be reported as a failure.
- **FR-011**: Every refusal MUST state why in terms the operator can act on, and MUST leave
  the entered values in place for correction.
- **FR-012**: A successful add MUST show the new identifier in the list immediately, without
  the operator reloading the page, and the shown list MUST match what is stored.
- **FR-013**: Each listed non-internal identifier MUST offer a control to remove it.
- **FR-014**: The internal code MUST NOT offer a remove control.
- **FR-015**: Removal MUST require a confirmation, and declining MUST leave the identifier in
  place.
- **FR-016**: A confirmed removal MUST detach the identifier from the product and remove its
  row from the displayed list without a page reload.
- **FR-017**: Removing an identifier MUST NOT delete or otherwise alter the product; a product
  with no remaining non-internal identifiers MUST stay in the catalog with its internal code.
- **FR-018**: A removal of an identifier that is already gone MUST be reported as a successful
  removal.
- **FR-019**: An add or removal against a product that does not exist MUST report that
  plainly rather than appearing to succeed.
- **FR-020**: An identifier added through this control MUST be findable by catalog lookup on
  its value in the same way as one supplied at creation.

### Key Entities

- **Product**: The cataloged thing. Owns an internal code and zero or more other identifiers.
  Its identity is the product record itself, never one of its identifiers.
- **Product Identifier**: One coded name for a product — a type, a value as stored, an
  optional vendor, and whether validation was overridden when it was accepted. The internal
  type is generated by the system and is not operator-managed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can add an identifier to an already-cataloged product from that
  product's page in under 30 seconds, without leaving the page and without using anything
  other than the app's own interface.
- **SC-002**: All three products carrying a valid UPC only as a specification row can be made
  scannable by that UPC, and each is then found by looking up that code — closing the fourth
  GS1 verification vector carried over from the earlier manual verification pass.
- **SC-003**: 100% of refused adds tell the operator the specific reason, and every refusal
  caused by another product's claim on the value identifies that product.
- **SC-004**: 100% of successful adds and removals leave the on-screen list identical to what
  a fresh page load shows.
- **SC-005**: Removing every identifier from a product leaves the product findable by its
  internal code in 100% of cases.
- **SC-006**: An identifier corrected by removing the wrong value and adding the right one
  takes under a minute end to end, with no path that leaves the product carrying both.

## Assumptions

- **Add and remove only; no in-place edit.** Correcting an identifier means removing it and
  adding the replacement. This matches the operations the catalog already supports and keeps
  one code path for validation. An edit affordance is not part of this feature.
- **The controls live on the product detail page's existing Identifiers card.** That is where
  identifiers are already displayed and where the operator is when the problem is noticed.
- **The opt-in to store a failing barcode is presented the same way the Add Product form
  presents it** — an explicit checkbox alongside the value — rather than as a second prompt
  after a refusal. Mirroring the existing form is the simpler of the two and keeps the two
  places consistent.
- **Removal is confirmed with the same style of confirmation the app already uses** for
  deleting attachments and photos.
- **Backfilling existing UPC specification rows into `GTIN` identifiers is out of scope.**
  Only products captured in a two-day window are affected, and with an add control the
  operator can correct the three by hand in about a minute. A migration would cost more than
  it saves. The specification rows themselves are left alone.
- **No change to how identifiers are validated, normalized, stored or looked up.** This
  feature exposes existing behavior through the interface; it does not redefine it.
- **Single operator on a LAN-only app.** Concurrency handling extends no further than the
  two-tab cases named in the edge cases — the second tab's stale action is reported honestly,
  and nothing more elaborate is warranted.

## Dependencies

- The catalog's existing identifier add and remove operations, including their validation,
  normalization, duplicate detection and vendor requirements.
- The correction that makes a failed request report its failure to the page that made it,
  rather than silently reading as success (issue #132, closed 2026-09-02). Without it, a
  removal of an already-removed identifier cannot be told apart from a real success, and
  FR-018 would hold by accident rather than by design.
- The rule that a captured barcode is promoted to a `GTIN` identifier at capture time, which
  this feature complements for records captured before that rule existed.

## Out of Scope

- Editing an identifier's value, type or vendor in place.
- A data migration promoting existing UPC specification rows to `GTIN` identifiers.
- Managing the internal code — generating, changing or removing it.
- Any change to scanning, lookup or search behavior beyond the effect of the identifiers the
  operator adds.
- Bulk identifier management across multiple products.
