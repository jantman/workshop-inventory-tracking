# Feature Specification: Unit Price From a Multi-Pack

**Feature Branch**: `017-unit-price-from-pack`

**Created**: 2026-08-17

**Status**: Draft

**Input**: User description: "issue #97 on this repo" — Work out the unit price from a multi-pack on the capture confirmation page (GitHub issue #97, from the #80 verification pass, comment item 4).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record a multi-pack without reaching for a calculator (Priority: P1)

The operator captures a listing that is sold as a pack — `B0CKXJLP4B` is a 3-pack. The
listing yields one price, and that price is what the *pack* cost, but the purchase record
wants the price of *one unit*. On the capture confirmation page the operator states what was
paid and how many units came in the pack, and the unit price appears, already worked out. It
is an ordinary field: the operator can read it, disagree with it, and type over it before
capturing.

**Why this priority**: This is the whole of issue #97. Without it the operator either does
the arithmetic in their head or in another window, and a purchase whose price was computed
somewhere unrecorded is a purchase whose price history nobody can check.

**Independent Test**: Open the capture page, enter an amount paid and a pack size, and read
the unit price off the form before submitting. Delivers the entire value of the feature on
its own.

**Acceptance Scenarios**:

1. **Given** the capture page with an amount paid of `29.97`, **When** the operator states
   the pack holds 3 units, **Then** the unit price reads `9.99`.
2. **Given** the capture page with a unit price worked out from a pack, **When** the operator
   types a different unit price over it and captures, **Then** the purchase records the price
   the operator typed, not the computed one.
3. **Given** an amount paid and a pack size that yield a unit price, **When** the operator
   changes either the amount paid or the pack size, **Then** the unit price is worked out
   again from the two current values — never from the previously displayed unit price.
4. **Given** a listing captured from a vendor page whose extracted price is `17.99`, **When**
   the operator opens the confirmation page, **Then** the amount paid is already `17.99` and
   the pack size is one unit, so a single-unit purchase behaves exactly as it does today.

---

### User Story 2 - See when the division did not come out even (Priority: P2)

$17.99 for a 3-pack is $5.996666… a unit, and a price is recorded to the cent. The operator
is shown the rounded unit price and told, on the page, that this unit price multiplied back
by the pack size does not equal what was paid.

**Why this priority**: The rounding is silent otherwise. An operator who later reconciles
3 × $6.00 = $18.00 against a $17.99 charge needs to have been told where the penny went,
rather than suspecting the wrong price was recorded. It is a separate slice because US1 is
useful without it.

**Independent Test**: Enter `17.99` and a pack of 3, and read both the unit price and the
statement of inexactness off the page without submitting.

**Acceptance Scenarios**:

1. **Given** an amount paid of `17.99` and a pack of 3, **When** the unit price is worked
   out, **Then** it reads `6.00` and the page states that the pack size times this unit price
   does not come back to `17.99`.
2. **Given** an amount paid of `29.97` and a pack of 3, **When** the unit price is worked
   out, **Then** it reads `9.99` and no statement of inexactness is shown.
3. **Given** an inexact result is being shown, **When** the operator changes the pack size to
   one that divides evenly, **Then** the statement of inexactness goes away.

---

### User Story 3 - The pack inputs survive a question (Priority: P3)

Capturing can come back with a question — a suspected duplicate order, or a vendor item
number that already names a different product. The page re-renders with the operator's
answer still to give. The amount paid and the pack size are still there when it does, so the
displayed unit price still has a visible derivation and the operator does not re-enter them.

**Why this priority**: The confirmation page already preserves every other typed field across
these re-renders; two new fields that silently empty themselves would be a regression in a
path the operator hits regularly. Lower priority only because the unit price itself is
already preserved by the existing mechanism, so nothing is lost — only the explanation of it.

**Independent Test**: Capture a listing that triggers the duplicate warning after entering an
amount paid and a pack size, and confirm both values are still on the re-rendered page.

**Acceptance Scenarios**:

1. **Given** an amount paid of `29.97` and a pack of 3 entered on the capture form, **When**
   the capture comes back asking about a suspected duplicate, **Then** the re-rendered page
   still shows `29.97`, the pack of 3, and the unit price `9.99`.

---

### Edge Cases

- **Pack size of one, or left blank**: the unit price is the amount paid, unrounded and
  unchanged. This is the ordinary single-unit purchase and it must not be made to feel like a
  special case.
- **Pack size of zero, negative, or not a whole number**: nothing is divided and the unit
  price already on the form is left exactly as it is. The operator is told the pack size is
  not usable rather than being handed a wrong price or an emptied field.
- **Amount paid blank, or not a price**: nothing is divided and the unit price is left as it
  is. An operator who has typed a unit price directly and never touches the pack fields must
  not have it cleared by this feature.
- **A result that rounds to zero**: `0.01` across a pack of 3 gives `0.00` a unit. The zero
  is recorded (a price of zero is already accepted) and the inexactness is stated, because
  this is exactly the case where a silent `0.00` would look like a bug.
- **A very large pack size**: the division is still performed and rounded; there is no cap
  beyond the pack size being a positive whole number.
- **A capture with no extracted listing** (the paste-a-URL path, or the form filled in by
  hand): the pack fields work identically. They are not tied to the extraction.
- **An operator who overrides the unit price and then changes a pack input**: the recomputed
  value replaces the override. The two inputs are the stated source of the number; whichever
  the operator touched last is what the page reflects.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The capture confirmation page MUST let the operator state the amount paid for
  the pack, as a price.
- **FR-002**: The capture confirmation page MUST let the operator state how many units came
  in the pack, as a positive whole number.
- **FR-003**: The system MUST work out the unit price as the amount paid divided by the pack
  size, and present it as the purchase's unit price before anything is captured.
- **FR-004**: The presented unit price MUST remain editable, and a value the operator types
  MUST be the value captured.
- **FR-005**: The unit price MUST be worked out again whenever either the amount paid or the
  pack size changes, from those two values only — a previously displayed or overridden unit
  price MUST NOT be used as an input to a later computation.
- **FR-006**: A unit price that does not divide evenly MUST be rounded to two decimal places,
  half away from zero, matching the precision at which a purchase price is recorded.
- **FR-007**: Every price on this path MUST be handled as an exact decimal value from the
  moment the operator states it to the moment it is recorded, with the single rounding of
  FR-006 the only place precision is lost. No value may be carried or divided in a form that
  introduces its own rounding error, at rest or in transit (Constitution Principle III).
- **FR-008**: When the rounded unit price multiplied by the pack size does not equal the
  amount paid, the page MUST say so, in place, before capture.
- **FR-009**: When the division is exact, the page MUST NOT show a statement of inexactness.
- **FR-010**: A pack size that is absent, or is one, MUST leave the unit price equal to the
  amount paid with no rounding applied.
- **FR-011**: A pack size that is not a positive whole number, or an amount paid that is not
  a price, MUST leave the existing unit price untouched and MUST tell the operator which
  input is unusable.
- **FR-012**: The amount paid and the pack size MUST survive a capture that re-renders the
  form to ask the operator a question, alongside the fields that already survive it.
- **FR-013**: Where the capture extracts a price from a listing, that price MUST be presented
  as the amount paid for the pack, since that is what the listing states.
- **FR-014**: Neither the amount paid nor the pack size may be recorded against the product
  or the purchase. They exist only to produce the unit price on this page; there is no pack
  concept in the stored data.
- **FR-015**: A capture in which the operator never touches either pack input MUST record
  exactly what it records today.

### Key Entities

No stored entity changes. The two new values — amount paid for the pack, and units in the
pack — are inputs to the confirmation page only. The purchase continues to record a unit
price and a quantity, and nothing else about the pack is retained.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator recording a multi-pack purchase completes it without leaving the
  capture page and without a calculator — zero external tools in the flow.
- **SC-002**: For every combination of a valid amount paid and a valid pack size, the unit
  price presented equals the amount paid divided by the pack size, rounded to the cent, with
  no rounding error introduced beyond that single rounding step.
- **SC-003**: In 100% of cases where the rounded unit price does not multiply back to the
  amount paid, the operator is told so on the page before capturing.
- **SC-004**: Recording a multi-pack purchase takes no more than one additional input
  (the pack size) compared with recording a single-unit purchase.
- **SC-005**: Captures that do not involve a pack are unchanged: the same fields are recorded
  with the same values as before this feature.

## Assumptions

- **The rounding decision is: round to the cent, and say so.** Issue #97 requires this to be
  decided and stated. A purchase price is recorded to two decimal places, so keeping more
  precision than currency has would mean widening stored precision — a schema change the
  issue explicitly rules out of scope for a feature it describes as small and self-contained.
  The consequence, that unit price × pack size no longer equals what was paid, is therefore
  accepted and made visible (FR-008) rather than hidden.
- **The pack size does not touch the Quantity field.** Quantity is the number of units the
  purchase brings in and stays the operator's to state. The issue asks only for the unit
  price; making pack size drive quantity as well is a second behavior with its own failure
  modes and is out of scope here.
- **Rounding is half away from zero**, consistent with the `ROUND_HALF_UP` normalization the
  project applies to every other exact quantity.
- **Currency is a single, unstated one.** The application records prices as bare decimals
  with no currency, and this feature does not introduce one.
- **The extracted listing price is the pack price.** This is what issue #97 states and what
  the vendor page shows; there is no attempt to detect a pack size from the listing.
- **The feature applies only to the capture confirmation page.** The receive screen and the
  purchase-editing paths keep their existing unit price fields untouched.
