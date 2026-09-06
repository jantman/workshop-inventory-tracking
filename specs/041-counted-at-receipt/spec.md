# Feature Specification: An Explicit "I Counted the Shelf" at Receipt

**Feature Branch**: `robot-army/issue-149-explicit-i-counted-the-shelf-option`

**Created**: 2026-09-06

**Status**: Draft

**Input**: GitHub issue #149 — "Explicit 'I counted the shelf' option when receiving a purchase", which records the decision taken in #135 (option 2).

## Overview

Feature 008 took a deliberate position: receiving a purchase adds what arrived to a tracked
count but does **not** refresh the count's age, because adding a packing slip's number to a
stored number is arithmetic and not a verification. The age means one thing — the last time a
person looked at the stock — and letting a delivery reset it made the screen say "counted just
now" when nobody had counted anything.

That position is right and it stays. What it left out is the case where the operator *did*
look. Very often the shelf is right there while the box is being unpacked, and the natural
thing to do is check the drawer. Today there is no way to say so from the receive screen: the
operator has to finish receiving, open the product, and re-enter a count they have already
established, purely to move a date.

So this feature adds one control to the receive screen — off by default — that lets the
operator say "I counted what is on the shelf". Ticking it makes the receipt refresh the count's
age as well as the count. Leaving it alone changes nothing at all.

The distinction the feature preserves is the one 008 drew: **the machine never asserts a
verification, and the operator always may.** A packing slip does not become evidence because it
was added up correctly. An operator saying they counted is exactly the evidence the age was
always meant to record, and it is no less trustworthy for being given on the receive screen
than on the product page.

This is not a new way to enter a count. The control asserts that the number the receipt
arrives at is the number on the shelf; it does not ask for a number, and it does not create,
change or stop a count. If what the operator counted differs from what the arithmetic
produced, the product page's existing count entry is still the way to say so.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receiving a box and checking the drawer at the same time (Priority: P1)

The operator has a tracked count of 4 M3 standoffs, counted back in January. A bag of 100
arrives in August. While unpacking they open the drawer, see the four that were there, and tip
the bag in. On the receive screen they tick "I counted what is on the shelf" and submit. The
product now reads 104, counted just now — because it was.

**Why this priority**: It is the whole feature. Without it there is nothing here.

**Independent Test**: Seed a product with a tracked count whose age is several months old,
receive an outstanding purchase against it with the control ticked, and verify both that the
count rose by the received quantity and that its displayed age reset to just now.

**Acceptance Scenarios**:

1. **Given** a product with a tracked count last counted three months ago, **When** an
   outstanding purchase for it is received with the control ticked, **Then** the count rises by
   the received quantity and the screen reports the count as counted just now.
2. **Given** the same product, **When** the purchase is received with the control left alone,
   **Then** the count rises by the received quantity and the screen still reports the count as
   three months old.
3. **Given** the receive screen for a product with a tracked count, **When** it is opened,
   **Then** the control is present and not ticked.
4. **Given** a product with a tracked count that has never been counted, **When** a purchase is
   received with the control ticked, **Then** the screen reports the count as counted just now.
5. **Given** a purchase recorded with no quantity, **When** it is received with the control
   ticked against a product with a tracked count, **Then** the count is unchanged and its age
   is reset to just now, because the operator looked whether or not the number moved.

---

### User Story 2 - The default is still the honest one (Priority: P1)

The operator receives a delivery from the sofa, having not been near the shelf. They fill in
the quantity and submit without touching the new control. Nothing about the count's age moves,
exactly as it has since feature 008 shipped.

**Why this priority**: An opt-in that is easy to leave opted-in by accident would reintroduce
the untruth 008 removed. The unticked path is the one that must be provably unchanged, and it
ranks alongside Story 1 rather than below it.

**Independent Test**: Run the existing feature 008 receive behaviour end to end without
touching the new control and verify every one of its outcomes is unchanged.

**Acceptance Scenarios**:

1. **Given** a product with a tracked count, **When** a purchase is received without the
   control ticked, **Then** the count's age is unchanged.
2. **Given** a receive submitted with the control ticked, **When** the operator returns to the
   receive screen for another purchase, **Then** the control is not ticked; the choice is not
   remembered.
3. **Given** a receive that is refused because some field failed validation, **When** the form
   is redisplayed, **Then** the control shows the state the operator submitted it in, and no
   count age has been recorded.
4. **Given** a product whose count is not tracked, **When** a purchase for it is received with
   or without the control, **Then** no count is created and no counted age is recorded.

---

### User Story 3 - The control is not offered where it would do nothing (Priority: P2)

The operator receives a purchase for a product whose count is not tracked. The receive screen
does not offer to record a count age, because there is no count for an age to belong to.

**Why this priority**: It keeps the screen honest about what it can do. A tick-box that
silently does nothing teaches the operator that ticking it is meaningless, which is corrosive
to the one control whose entire value is that it is believed. It is P2 because the outcome —
nothing recorded — is correct either way.

**Independent Test**: Open the receive screen for a purchase against a product with no tracked
count and verify the control is absent.

**Acceptance Scenarios**:

1. **Given** a product with no tracked count, **When** the receive screen is opened for one of
   its purchases, **Then** the control is not shown.
2. **Given** a product with a tracked count of zero, **When** the receive screen is opened,
   **Then** the control is shown, because zero is a counted number and not an absence.

---

### Edge Cases

- **An already-received purchase submitted again.** The received date and the count both stay
  put, as they do today. The control, if ticked, still records the count age: it asserts that
  the operator has looked at the shelf, which is true or false independently of whether this
  submission moved any number. The screen's existing note about what a second submission does
  and does not touch says so.
- **A receipt whose received date is backdated.** The count's age is the moment the operator
  said they counted — now — not the day the box is recorded as having arrived. The received
  date is a day off a packing slip; the count age is an instant the application recorded, and
  the two are not interchangeable.
- **The control ticked against a purchase with no quantity.** Nothing is added, and the age is
  still recorded. The assertion is about the shelf, not about the delivery.
- **The control ticked against a product with no tracked count.** Not reachable, because the
  control is not offered; and if it arrives anyway, nothing is created — receiving never begins
  tracking a count.
- **A count that has never been counted, on a tracked product.** Ticking gives it its first
  age. This is the operator counting, which is exactly what the age is for.
- **The operator counts and finds a different number from the arithmetic.** Out of scope for
  this control, which records no number. The product page's count entry is unchanged and is
  still the way to correct a count.
- **The manual low/out flag.** Unchanged. Receiving clears it and discards its date, ticked or
  not; the flag is a separate assertion from the count.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The receive-purchase screen MUST offer the operator a way to assert that they
  have counted what is on the shelf.
- **FR-002**: That control MUST default to not asserted every time the screen is opened, and
  MUST NOT carry a previous receipt's choice forward.
- **FR-003**: When the assertion is made, receiving a purchase MUST record that moment as the
  product's count age.
- **FR-004**: When the assertion is not made, receiving a purchase MUST leave the product's
  count age exactly as it was, which is the behaviour in place today.
- **FR-005**: The assertion MUST NOT change what the count becomes. Receiving continues to add
  the received quantity to a tracked count, and adds nothing else.
- **FR-006**: The assertion MUST NOT create a count, and MUST NOT record a count age, for a
  product whose count is not tracked.
- **FR-007**: The control MUST NOT be offered on the receive screen when the product's count is
  not tracked, because there is nothing for it to act on.
- **FR-008**: The moment recorded MUST be the moment the operator makes the assertion, not the
  purchase's received date, which the operator may have backdated.
- **FR-009**: When a receive submission is refused for a validation error, the redisplayed form
  MUST show the assertion in the state the operator submitted it in, and MUST NOT have recorded
  any count age.
- **FR-010**: The assertion MUST apply to a purchase being received a second time as it does to
  a first receipt: nothing else about that submission changes, and the count age is recorded
  because the operator says they looked.
- **FR-011**: The assertion MUST NOT affect the manual low/out flag or its date, which
  receiving continues to clear as it does today.
- **FR-012**: The control's wording MUST state what it asserts in the operator's terms — that
  they counted the stock — and MUST NOT be phrased as an instruction to the system about a
  date.

### Key Entities

- **Purchase**: Unchanged in what it stores. Nothing records whether a receipt carried the
  assertion; what it produces is a count age on the product, which is where the evidence
  belongs.
- **Product**: Unchanged in what it stores. Its count age gains one further way to be written —
  an operator asserting at receipt time that they counted — and that way is still an operator
  act, not machinery acting on their behalf.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Receiving a purchase without the assertion never changes the reported age of a
  count. Measured by comparing the displayed age immediately before and after a receipt.
- **SC-002**: Receiving a purchase with the assertion always reports the count as counted just
  now, for every product with a tracked count.
- **SC-003**: The operator can receive a delivery and record that they counted the shelf in one
  submission, without visiting the product page.
- **SC-004**: Every path that writes a count age is an operator act: entering a count,
  adjusting one at the shelf, or asserting at receipt that they counted. No path writes one
  without the operator having said they looked.
- **SC-005**: The count still carries exactly one age. No screen gains a second date beside it.
- **SC-006**: `specs/008-trustworthy-stock-age/` and the application agree about what receiving
  is allowed to assert, with no requirement in either contradicted by the other.

## Assumptions

- The assertion is a plain opt-in tick on the existing receive form, not a separate screen, a
  confirmation step, or a second submit button. The receive screen already exists to let the
  operator correct what arrived against what was ordered; this is one more thing they know that
  the packing slip does not.
- The assertion records no number. Issue #149 asks for an option meaning "I counted what is on
  the shelf", not a count entry field, and adding one would duplicate the product page's count
  entry on a screen that already has a quantity field meaning something else. If the shelf
  disagrees with the arithmetic, that is a count correction and belongs where count corrections
  already live.
- Nothing records, per purchase, whether its receipt carried the assertion. The evidence
  produced is the count's age, and a second stored fact about how the age came to be would be a
  fact nothing displays and every future write path would have to maintain.
- The receive screen is the only place a purchase is received. Recording an already-arrived
  purchase through order capture or backfill sets an arrival date without ever moving a count,
  and is untouched by this feature.
- `specs/008-trustworthy-stock-age/` is amended rather than superseded. Its FR-008 carve-out —
  that receiving must not make a count present itself as more recently counted than it was —
  stands as the default, with this explicit operator override named as its one exception. The
  same applies to that feature's SC-001 and SC-003.
- No new screen, no change to the reorder list, and no change to how an age is worded or
  rendered anywhere.
