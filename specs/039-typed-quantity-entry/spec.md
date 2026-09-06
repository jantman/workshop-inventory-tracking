# Feature Specification: Type a tracked count instead of clicking to it

**Feature Branch**: `robot-army/issue-139-a-tracked-count-can-only-be-changed-one`

**Created**: 2026-09-06

**Status**: Draft

**Input**: GitHub issue #139 — "A tracked count can only be changed one click at a time: no way to type a quantity"

## Context

A product's on-hand count has three states the operator must be able to reach: a number, zero,
and "not tracked". The Stock card on the product page reaches all three, but it can only *move*
a count by one at a time. There is a minus button, a plus button, and — when nothing is being
counted — a "Start counting this" button that begins at zero.

So the operator who has just counted forty resistors into a drawer has one route to recording
forty: press plus forty times.

Two things make this worse than it first looks.

1. **The count that has to be typed is usually not small.** The friction is proportional to the
   number, and the numbers that need entering by hand are exactly the ones nobody wants to
   click to. Counting is a periodic re-verification, not a nudge; the steppers were built for
   the nudge ("I just used one") and became the only route to both.
2. **Receiving does not fill the gap for an untracked product.** Receiving a purchase adds the
   whole purchase quantity to the count in one step, but only when the product is already
   tracked. Receive a hundred of something untracked, then decide to start counting it, and the
   count starts at zero with two buttons — the same wall, reached by the more common road.

The recording capability is already there. What the plus and minus buttons ultimately do is
record an absolute count, so the system already accepts "forty" as readily as "one more than
thirty-nine". What is missing is a way for the operator to say forty.

One constraint shapes the answer. The Stock card was deliberately built so that every action on
it is a button large enough for a thumb, because the product page is used from a handheld at the
shelf as well as from a workbench. A control that requires a physical keyboard does not exist on
that device. So a typed entry is an **addition** to the steppers, never a replacement for them,
and it must be operable by touch alone.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record a count that was just taken (Priority: P1)

The operator has counted the drawer. It holds forty. They open the product page, type 40 into the
on-hand field, commit it, and the count reads 40 with a fresh count date.

**Why this priority**: This is the defect. Every other story here is a refinement of it, and
without it the feature does not exist.

**Independent Test**: On a product that is already being counted, type a number different from
the current one, commit, and confirm the displayed count and its age both update. Delivers the
whole of the reported value on its own.

**Acceptance Scenarios**:

1. **Given** a product tracked at 3, **When** the operator enters 40 in the on-hand field and
   commits it, **Then** the product's count is 40 and its count date is now.
2. **Given** a product tracked at 40, **When** the operator enters 0 and commits it, **Then** the
   product reads as having none on hand and is still being counted — it does **not** become
   untracked.
3. **Given** a product tracked at 40, **When** the operator commits the field without having
   changed it, **Then** the count is still 40 and its count date is refreshed, because the
   operator has just re-verified it.
4. **Given** a product tracked at 40, **When** the operator presses the minus button, **Then** it
   reads 39 exactly as it does today, and the typed field reflects the new value.

---

### User Story 2 - Start counting something at the number it is actually at (Priority: P1)

The operator decides to start tracking a product that has never been counted. They are holding
the bag. It has twelve in it. They start the count at twelve, in one action, without passing
through zero and clicking twelve times.

**Why this priority**: Beginning a count is when a non-zero number is most likely to be known and
most expensive to click to. Starting every count at zero is what forces the forty clicks in the
first place.

**Independent Test**: On an untracked product, begin counting with a stated starting number and
confirm the product becomes tracked at that number. Independently valuable: it fixes the entry
path even if an existing count could still only be stepped.

**Acceptance Scenarios**:

1. **Given** an untracked product, **When** the operator starts counting it with a starting count
   of 12, **Then** the product is tracked at 12 with a count date of now.
2. **Given** an untracked product, **When** the operator starts counting it without naming a
   number, **Then** the product is tracked at 0, exactly as "Start counting this" does today.
3. **Given** a product tracked at 12, **When** the operator stops counting it, **Then** it becomes
   untracked, and the typed field no longer offers to change a count that does not exist.

---

### User Story 3 - Be told what was already received (Priority: P2)

The operator receives an order of a hundred into a product that is not being counted, so nothing
is added to any count. Later they decide to start counting it. The page tells them that a hundred
have been received for this product, so they can start the count there — or at whatever the shelf
actually holds — rather than reconstructing it from the order history.

**Why this priority**: This is the path the issue calls the more likely way to meet the problem,
and the information needed to answer it is already recorded against the product. It is a
convenience on top of Story 2 rather than a fix in its own right, so it ranks below it.

**Independent Test**: Receive a purchase into an untracked product, open the product page, and
confirm the received total is stated where the starting count is entered. Testable without any
change to how the number is committed.

**Acceptance Scenarios**:

1. **Given** an untracked product with received purchases totalling 100, **When** the operator
   views the Stock card, **Then** the total received is stated alongside the starting-count entry.
2. **Given** an untracked product with received purchases totalling 100, **When** the operator
   starts counting it, **Then** the count that is stored is the one the operator entered — the
   stated total is advisory and is never committed on the operator's behalf.
3. **Given** an untracked product with no received purchases, **When** the operator views the
   Stock card, **Then** no received total is stated and the card is otherwise unchanged.
4. **Given** a product that is already being counted, **When** the operator views the Stock card,
   **Then** no received total is stated, because receiving already adds to that count and
   repeating it would invite double-counting.

---

### Edge Cases

- **The field is left empty and committed on a tracked product.** An empty on-hand entry is not
  an instruction to stop counting. It MUST be refused with a message, not silently interpreted —
  the difference between "no number" and "stop tracking this" is the difference between two of the
  three states, and stopping tracking has its own explicit control.
- **The field is left empty when beginning a count.** The count begins at zero, exactly as it does
  today. The two cases differ because the controls differ: one says "set this count", the other
  says "start counting this".
- **A negative or fractional number is entered.** Refused with a message the operator can act on;
  the stored count is unchanged. Counts of discrete parts are whole and non-negative.
- **Text that is not a number is entered.** Refused the same way. Nothing is stored.
- **A refused entry.** The count on the page is left as it was, and the operator can correct the
  entry and commit again without reloading the page.
- **Stepping below zero.** The minus button continues to stop at zero rather than going negative,
  as it does today.
- **Received purchases with no recorded quantity.** They contribute nothing to the stated total;
  they are neither counted as zero-error nor allowed to suppress the total from purchases that do
  carry a quantity.
- **A product whose received purchases total zero or which has none.** Nothing is stated. An
  advisory line reading "0 received" is noise.
- **No physical keyboard.** The typed entry must be reachable and completable from a touchscreen
  alone, and the existing stepper buttons must remain, unchanged in size and behavior, for the
  handheld case where typing is the wrong tool.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Stock card MUST offer the operator a way to enter an exact on-hand count for a
  product and commit it in a single action.
- **FR-002**: Committing an entered count MUST set the product's count to exactly that number,
  not add it to or subtract it from the existing count.
- **FR-003**: Committing an entered count MUST record the moment it was committed as the count's
  date, including when the committed number equals the number already stored — re-entering the
  same count is the operator saying they have just looked again.
- **FR-004**: The operator MUST be able to enter a starting count when beginning to count a
  product that is not currently tracked, and beginning with no number named MUST continue to
  start the count at zero.
- **FR-005**: Entering 0 and committing it MUST leave the product tracked with none on hand. It
  MUST NOT stop tracking the product.
- **FR-006**: Committing an empty entry against a product that is **already being counted** MUST
  be refused with a message and MUST NOT be treated as an instruction to stop tracking. (Beginning
  a count with an empty entry is governed by FR-004 and starts at zero: there, an empty field is
  the absence of an entry rather than an entry of nothing, and the control the operator pressed
  says which count it is starting.)
- **FR-007**: An entry that is not a whole number of zero or more MUST be refused with a message
  naming what is wrong, and the stored count MUST be left unchanged.
- **FR-008**: After a refused entry the operator MUST be able to correct it and commit again on
  the same page, without losing the displayed count.
- **FR-009**: The increment and decrement buttons MUST remain, with their present behavior and
  present size, and MUST remain the only controls needed to adjust a count by one.
- **FR-010**: The typed entry MUST be operable on a touchscreen with no physical keyboard.
- **FR-011**: The typed entry MUST be unavailable, or plainly inert, on a product that is not
  being counted — except as the starting-count entry described in FR-004 — so that it cannot be
  confused with the control that begins a count.
- **FR-012**: When a product is not being counted and has purchases that have been received, the
  Stock card MUST state the total quantity received for that product where the starting count is
  entered.
- **FR-013**: The total in FR-012 MUST be advisory only: it MUST NOT be written to the product's
  count unless the operator commits it, and MUST NOT be stated for a product that is already
  being counted.
- **FR-014**: The total in FR-012 MUST sum only received purchases that carry a recorded
  quantity, and MUST NOT be stated at all when that sum is zero or there are no such purchases.
- **FR-015**: Stopping counting MUST remain a distinct, explicitly labelled action, unchanged by
  this feature.

### Key Entities

- **Product on-hand count**: the number of a product currently held, or the absence of any count.
  Carries the date it was last established. Three reachable states: a positive number, zero, and
  not tracked.
- **Purchase**: a recorded order line for a product, carrying a quantity and the date it was
  received, if it has been. A purchase with a received date is what FR-012 totals.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Recording a counted quantity of any size takes one entry and one commit — the
  number of actions required does not grow with the number being recorded.
- **SC-002**: Setting a starting count of forty on a previously untracked product takes fewer
  than five actions, against forty-one today.
- **SC-003**: All three count states — a number, zero, and not tracked — remain reachable from
  the product page, and each is reachable by a control that says which one it produces.
- **SC-004**: Every count-adjusting action on the Stock card remains completable on a touchscreen
  device with no physical keyboard.
- **SC-005**: No entry that is rejected changes the stored count, and every rejection tells the
  operator what was wrong with what they typed.
- **SC-006**: An operator beginning a count on a product that has had stock received into it
  while untracked can see the received total without leaving the product page.

## Assumptions

- **The received total is shown, not applied.** The issue leaves open whether a received total
  should be *offered as a starting suggestion*. It is offered as a stated figure next to the
  entry rather than pre-filled into it. A product may have been received years ago and consumed
  since; a pre-filled number that the operator commits without reading would write a count nobody
  verified, which is worse than the clicking this feature exists to remove. Stating it costs the
  operator three keystrokes and keeps the committed number one the operator chose.
- **The total is over all received purchases for the product**, with no cut-off date and no
  attempt to subtract consumption, because nothing in the record says what has been consumed. It
  is presented as what it is — the quantity received — and not as an estimate of what is on hand.
- **Counts are whole and non-negative.** This is what the existing count already enforces; this
  feature does not change it. Fractional or measured stock is out of scope.
- **No change to how receiving affects a count.** Receiving into a tracked product continues to
  add the purchase quantity; receiving into an untracked product continues to move nothing. This
  feature makes the resulting gap easy to close by hand, and deliberately does not make receiving
  start a count on the operator's behalf.
- **No change to the stored shape of a count.** The three states and their storage are unchanged;
  this feature adds a way to reach them.
- **The manual low/out flag and the reorder threshold are untouched.**
- **Only the product detail page is in scope.** Bulk count entry, count entry from search results,
  and count entry from the item (JA ID) side of the application are not part of this.

## Out of Scope

- Making receiving start a count automatically on an untracked product.
- Any change to the low/out flagging controls or to the reorder threshold.
- Editing counts anywhere other than the product detail page.
- History or an audit trail of count changes beyond the single count date already stored.
