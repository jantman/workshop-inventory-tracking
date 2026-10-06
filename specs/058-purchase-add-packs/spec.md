# Feature Specification: Pack Quantity on Record a Purchase

**Feature Branch**: `robot-army/issue-191-add-a-purchase-pack-quantity`

**Created**: 2026-10-06

**Status**: Draft

**Input**: User description: "Add a Purchase pack quantity (issue #191): For Products, capturing from an order can record either a quantity and unit price, or a count per pack and number of packs. However, manually using Add a Purchase does not have a way to input count per pack/number of packs, only quantity and unit price. Fix this so Add a Purchase has the same functionality in terms of packs as capturing a purchase."

## Background

A product's purchase history can be added to in two ways. **Capturing** an order (the
capture page, reached from a vendor listing or the browser extension) asks how many packs
were bought, what one pack cost and how many units were in it; it works out the item
quantity and the price of one item from those, leaves both editable, and records the
vendor's pack size and pack price on the purchase beside the item quantity and unit price.

**Record a Purchase** — the manual form on a product's page — asks only for a quantity and
a unit price. An owner recording a box of 100 screws bought as two packs has to multiply
and divide by hand, and the vendor's pack price (which cannot be recovered once it has been
divided down and rounded to the cent) is lost.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record a pack purchase by hand (Priority: P1)

The owner bought 2 packs of 100 screws at $13.23 a pack from a vendor that has no capture
support. On the product's Record a Purchase form they enter Packs Bought 2, Paid for the
Pack 13.23 and Units in the Pack 100. Quantity fills in as 200 and Unit Price as 0.13, with
a note that the unit price is rounded. They save; the purchase records 200 items at $0.13
and, as the vendor's line, packs of 100 at $13.23 each.

**Why this priority**: This is the whole of the issue.

**Independent Test**: Open Record a Purchase for a product, fill the three pack fields,
save, and check the recorded purchase's quantity, unit price, pack size and pack price.

**Acceptance Scenarios**:

1. **Given** the Record a Purchase form, **When** the owner enters 2 packs of 100 at 13.23,
   **Then** Quantity shows 200 and Unit Price shows 0.13 with a rounding note, before saving.
2. **Given** those values, **When** the owner saves, **Then** the purchase records quantity
   200, unit price 0.13, pack size 100 and pack price 13.23.
3. **Given** derived values, **When** the owner overtypes Quantity or Unit Price and saves,
   **Then** the typed values are recorded, not the derived ones.
4. **Given** the same pack entry submitted from a browser without scripting, **When** the
   Quantity and Unit Price fields are left empty, **Then** the recorded quantity and unit
   price are still 200 and 0.13.

---

### User Story 2 - Recording a single item is unchanged (Priority: P2)

The owner records an ordinary purchase — 5 items at $2.00 — by typing only Quantity and Unit
Price, leaving the pack fields at their defaults.

**Why this priority**: The existing path must keep working exactly as it does.

**Independent Test**: Submit the form with only Quantity and Unit Price filled; the purchase
records them, and no pack size or pack price.

**Acceptance Scenarios**:

1. **Given** the pack fields at their defaults (1 pack, 1 unit per pack, no pack price),
   **When** the owner saves with Quantity 5 and Unit Price 2.00, **Then** the purchase
   records 5 at 2.00 and no pack size or pack price.
2. **Given** a pack size of 1 and a pack price entered, **When** saved, **Then** no pack
   size or pack price is recorded (a pack of one is not a pack).

---

### Edge Cases

- A validation error elsewhere on the form (e.g. a received date before the order date)
  re-displays the form with every pack field and the overtyped Quantity/Unit Price as the
  owner left them, and the page does not overwrite them on load.
- A non-numeric pack price or a pack size below 1 is refused with a clear message; nothing
  is recorded.
- A pack size above 1 with no pack price: quantity is still derived from packs × pack size;
  no unit price is derived, and no pack line is recorded (both or neither).
- Packs Bought left blank with a pack size above 1 counts as one pack.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Record a Purchase MUST offer Packs Bought, Paid for the Pack and Units in the
  Pack, labelled and defaulted as on the capture page (1 pack, 1 unit per pack).
- **FR-002**: As the owner edits the pack fields, Quantity MUST become packs × units per pack
  and Unit Price MUST become pack price ÷ units per pack rounded to the cent, with the same
  rounding note and error messages as the capture page.
- **FR-003**: Quantity and Unit Price MUST remain editable, and a value the owner typed MUST
  win over the derived one.
- **FR-004**: When the pack fields describe a pack of more than one unit and Quantity or Unit
  Price is submitted empty, the system MUST derive the empty value from the pack fields on
  saving, so the result does not depend on the browser running scripts.
- **FR-005**: When the units per pack is 2 or more and a pack price is given, the purchase
  MUST record the vendor's pack size and pack price, by the same rule the capture path uses
  (both or neither; never a pack of one).
- **FR-006**: A purchase recorded with the pack fields at their defaults MUST be recorded
  exactly as it is today.
- **FR-007**: Invalid pack values MUST be refused with the same messages the capture page
  gives, the form re-displayed as entered, and nothing recorded.

### Key Entities

- **Purchase**: gains no new attributes. Its existing vendor pack size and pack price, until
  now written only by capture paths, may now also be written from Record a Purchase when
  the owner states a pack.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A pack purchase can be recorded by hand without the owner doing any
  arithmetic: entering three pack values produces the correct item quantity and unit price.
- **SC-002**: A purchase recorded by hand from a pack keeps the vendor's pack price exactly
  as entered (e.g. $13.23, not $0.13 × 100 = $13.00).
- **SC-003**: Every purchase recordable by hand before this change is recorded identically
  after it.

## Assumptions

- "The same functionality as capturing" means the same three pack fields, the same live
  derivation and overrides, and the same stored vendor pack line — not the capture page's
  listing-specific behaviour (pre-filling from a vendor page, duplicate questions).
- The purchase-pack-fields contract from feature 046 stated that a hand-recorded purchase
  holds no pack line. That rule existed so a pack is never *inferred*; a pack the owner
  explicitly states on this form is stated, not inferred, so this feature adds Record a
  Purchase as a writer rather than breaking that intent.
- No change to the receive screen or to editing an existing purchase.
