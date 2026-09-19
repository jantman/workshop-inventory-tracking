# Feature Specification: Packs Recorded as Units, and What a Pack Was Kept

**Feature Branch**: `speckit/046-pack-quantity-order-lines`

**Created**: 2026-09-19

**Status**: Draft

**Input**: User description: <https://github.com/jantman/workshop-inventory-tracking/issues/137#issuecomment-5745370182>
— *"I tried capturing order 111-1533738-5610601 from the order details page. I get all 4 lines from
the order… but each of these was a multi-item pack and there's no field for that, only quantity and
unit price."*

Plus three decisions settled with the issue's author before specifying, recorded under
*Decisions agreed before specifying* below.

## Background

An Amazon order page states, per line, **how many of the listing** were bought and **what one of
the listing cost**. When the listing is a multi-item pack — a bag of 100 screws, a five-pack of
power supplies — those two numbers are packs and a price per pack. What this catalog records, and
what a stock count and a low-stock threshold have to mean, is **individual items**.

The Amazon order review offers exactly two editable numbers per line, Qty and Unit price, and
labels them *"as Amazon stated them"*. Confirming the reported order therefore recorded four
purchases of one item each, at the price of a whole pack, when the shelf actually gained four
packs' worth of items. The stock the operator then counts will not match the stock the purchase
implies, and every later per-item price — the label's `$x.xx ea`, a reorder decision — is wrong by
the pack size.

The operator can already repair this by hand: both fields are editable, so they can type the
multiplied quantity and the divided price themselves. That is the workaround, not the feature. It
asks for decimal division on every pack line, offers nowhere to say what the pack size was, and
leaves nothing on the page showing the arithmetic was done — so a line that was *not* corrected is
indistinguishable from one that needed no correction.

### The same idea exists three times, and disagrees with itself

- **McMaster order capture** states packs, a pack size and a price per pack, converts to units and
  a unit price on the review, warns when the division does not land on a whole cent, and leaves
  both editable (`specs/028-mcmaster-order-capture/spec.md` FR-020, FR-020a). **What the pack was
  is then discarded.**
- **The single-listing capture confirmation page** has *Paid for the Pack* and *Units in the Pack*,
  which feed *Unit Price* — but its **Quantity** field is left to the operator, so capturing one
  pack of 100 records **1 item at $0.13**. That is the reported defect in a second place. The user
  manual already asserts the rule this page breaks: *"Units in the Pack is not Quantity… Quantity
  is how many units the order brings in."*
- **Amazon order capture** has none of it, on the explicit finding that Amazon's order page states
  a unit price and a quantity directly (`specs/029-whole-order-capture/research.md` §5). That
  finding is true of what the page *states* and false of what the operator *bought*: the page's
  "unit" is the listing, and a listing can be a pack.

So the catalog has one rule — **quantity is items, price is per item** — enforced in one place,
half-enforced in another, and absent in the third. This feature makes it true everywhere, and
stops throwing away the fact that made it necessary.

### Decisions agreed before specifying

These were settled with the issue's author and are requirements, not open questions:

- **A. Every capture path, not just Amazon** (Q1). The Amazon order review gains a pack size, and
  the single-listing confirmation page's Quantity becomes derived from its pack fields the same
  way its Unit Price already is. McMaster's order review already converts and stays as it is.
- **B. A pack size is suggested from the listing, including from its title** (Q2). Amazon states
  pack counts in free text — `(Pack of 100)`, `100 Pcs`, `5-Pack` — and a suggestion read from
  there is offered pre-filled and **marked as a guess**, never silently applied.
- **C. What the pack was is stored** (Q3). The purchase retains the pack size and what one pack
  cost, so a captured order can be reconciled against the vendor's own invoice. **This deliberately
  reverses the standing rule stated in the McMaster review, the capture confirmation page and the
  user manual — "neither pack field is stored", "there is no pack size in the schema and this is
  not the beginning of one".** All three capture paths must store it consistently, and every
  document asserting the old rule must be corrected.

## User Scenarios & Testing *(mandatory)*

The operator is the only user. Every scenario is one person bringing a real purchase into the
catalog and wanting it recorded in the same units the shelf is counted in.

### User Story 1 - State a pack size on an Amazon order line and have the purchase recorded in items (Priority: P1)

The operator captures an Amazon order in which one line is a pack of 100 screws bought once at
$13.23. The review shows the line with a place to say how many items came in one of them. They
enter 100. The line's recorded quantity becomes 100 and its recorded price becomes $0.13 per item,
both still editable and both plainly shown as derived. They confirm, and the catalog holds one
purchase of 100 items at $0.13 each.

**Why this priority**: This is the reported defect. Without it, every pack bought on Amazon enters
the catalog with a quantity and a price that are both wrong, and nothing on the screen says so.

**Independent Test**: Capture an order containing one pack line, set its pack size, confirm, and
read the resulting purchase. Delivers the reported fix on its own, with no schema change and no
change to any other page.

**Acceptance Scenarios**:

1. **Given** a captured order line stating a quantity of 1 at $13.23, **When** the operator sets
   that line's pack size to 100, **Then** the line's quantity reads 100 and its unit price reads
   $0.13, before anything is confirmed.
2. **Given** the same line where the order states a quantity of 2, **When** the pack size is set to
   100, **Then** the quantity reads 200 and the unit price is still $0.13 — the pack size
   multiplies the packs bought, it does not replace them.
3. **Given** a line whose pack size is left at its default, **When** the operator confirms,
   **Then** the purchase records exactly what the order page stated, identical to today.
4. **Given** a line whose pack price does not divide evenly — $6.66 across 100 — **When** the pack
   size is entered, **Then** the page says so in words before confirmation, and the recorded price
   is rounded to the cent by this application rather than silently by the database.
5. **Given** a line with a pack size set and derived values shown, **When** the operator types over
   either derived value, **Then** what they typed is what gets recorded.
6. **Given** a review that comes back with a question about some other line, **When** the page
   re-renders, **Then** every pack size already entered is still there.

---

### User Story 2 - See which lines were treated as packs (Priority: P2)

The operator is reviewing a four-line order, three of which are packs. Before confirming, they can
see at a glance which lines have been converted and which are being recorded as the order page
stated them, so a pack line they have not got to yet cannot be mistaken for one that needed no
change.

**Why this priority**: Correcting the arithmetic is worthless if a missed line looks the same as a
finished one. This is what makes a multi-line pack order reviewable rather than merely repairable,
and it is what makes a *suggested* pack size (US3) safe enough to offer.

**Independent Test**: Capture an order with a mix of pack and single lines, set pack sizes on some,
and confirm the review distinguishes them without re-reading the vendor's page.

**Acceptance Scenarios**:

1. **Given** a review with four lines, **When** the operator has set a pack size on two, **Then**
   those two are visibly marked as converted and state the arithmetic performed — packs × pack
   size, pack price ÷ pack size.
2. **Given** a line recorded as the order stated it, **When** the review is read, **Then** nothing
   claims a conversion happened on it.
3. **Given** any converted line, **When** the review is read, **Then** the vendor's own numbers are
   still visible beside the catalog's, so both can be checked against the page and the box.

---

### User Story 3 - Have a pack size offered, and know it is a guess (Priority: P3)

The operator captures an order whose lines' listings were read as part of the capture. Where a
listing states or names a pack count — in a structured field, or in the title, as Amazon does —
the review offers that number already filled in and **marked as read from the listing rather than
stated by the order**. The operator accepts it, changes it, or clears it.

**Why this priority**: It removes the typing from the common case, which is the difference between
a four-line pack order taking two minutes and taking four. It sits below US2 because a suggestion
that is accepted without looking is only safe on a review that already shows plainly which lines
were converted.

**Independent Test**: Capture an order whose listing titles name pack counts; confirm the field
arrives filled, is marked as a guess, and can be overruled.

**Acceptance Scenarios**:

1. **Given** a line whose listing states a pack count in a structured field, **When** the review
   renders, **Then** that line's pack size is pre-filled with it and marked as coming from the
   listing.
2. **Given** a line whose listing title names a pack count in any of the common forms — `Pack of
   100`, `100 Pcs`, `5-Pack`, `Set of 10` — **When** the review renders, **Then** the pack size is
   pre-filled with it and marked as a guess read from the title.
3. **Given** a line whose listing was not read, or names no pack count, **When** the review
   renders, **Then** the pack size is the default and nothing is claimed about a pack.
4. **Given** a pre-filled pack size, **When** the operator changes or clears it, **Then** their
   value is used, it is no longer marked as a guess, and the suggestion is not reapplied on any
   later re-render.
5. **Given** a title naming a count that is plainly not a pack — a part number, a dimension, a
   voltage — **When** the review renders, **Then** it is not offered as a pack size.

---

### User Story 4 - Capture a single pack listing and get the items, not the pack (Priority: P2)

The operator opens a listing for a 100-pack of screws and clicks the bookmarklet. The confirmation
page fills *Paid for the Pack* and *Units in the Pack* as it does today — and now **Quantity**
follows from them too, so buying one pack shows a Quantity of 100 and a Unit Price of $0.13. They
confirm, and the product's purchase is 100 items, matching what they will count on the shelf.

**Why this priority**: This is the same defect as US1 on the page the operator reaches most often,
and it is currently *documented as working the way it does not*. It is P2 rather than P1 only
because the reported order came through the order path.

**Independent Test**: Capture a single pack listing with no order involved; read the resulting
purchase's quantity and price.

**Acceptance Scenarios**:

1. **Given** a listing for a pack of 100 at $13.23, **When** the confirmation page renders,
   **Then** Quantity reads 100 and Unit Price reads $0.13.
2. **Given** the operator bought two of that pack, **When** they state that, **Then** Quantity
   reads 200 and Unit Price is unchanged at $0.13.
3. **Given** a pack size of 1, or no pack at all, **When** the page renders, **Then** it behaves
   exactly as it does today.
4. **Given** a derived Quantity, **When** the operator types over it, **Then** their value is what
   is recorded, as is already true of Unit Price.
5. **Given** the page comes back with a question, **When** it re-renders, **Then** the pack fields
   and the quantity the operator arrived at are all still there.

---

### User Story 5 - Reconcile a captured order against the vendor's invoice (Priority: P3)

Months later the operator is checking a credit-card statement against the catalog. They open a
captured order and see, per line, both what the vendor charged — *1 pack of 100 at $13.23* — and
what the catalog holds — *100 at $0.13*. The two views agree, and the line reconciles without
opening the vendor's site.

**Why this priority**: This is the payoff for storing the pack, and the reason storing it was
chosen over recomputing it. It is P3 because the catalog is already *correct* without it; this
makes it *checkable*.

**Independent Test**: Capture a pack line through each of the three paths, then read the purchase
back and confirm the vendor's own line can be restated from what was stored.

**Acceptance Scenarios**:

1. **Given** a purchase captured from a pack line, **When** the operator views the order it came
   from, **Then** the vendor's own quantity, pack size and pack price are shown beside the
   catalog's items and per-item price.
2. **Given** a purchase captured before this feature, or one with no pack, **When** it is viewed,
   **Then** it reads exactly as it does today and claims nothing about a pack.
3. **Given** a McMaster order line of 2 packs of 100 at $6.00, **When** it is captured, **Then**
   the pack it came from is retained — the same as an Amazon or a single-listing pack capture, and
   unlike today, where McMaster converts and forgets.
4. **Given** a pack size that was a guess read from a title (US3), **When** the purchase is viewed
   later, **Then** the pack it was recorded against is visible, so a wrong guess can be found and
   corrected rather than being invisible in a per-item price.

---

### Edge Cases

- **Pack size of 1.** The default everywhere. Behaves exactly as today: no conversion, no
  conversion marking, no rounding notice, and nothing stored about a pack.
- **Pack size of 0, blank, negative or fractional.** Refused with a message naming the line, with
  every entry on the page preserved. Nothing is written for any line of a refused review.
- **Unread quantity or unread price.** An Amazon order page sometimes yields neither. A pack size
  against a line with no quantity cannot produce one, and against a line with no price cannot
  produce one; the line stays marked unread for that field. Entering a pack size must not invent a
  quantity of 1 or a price of 0.
- **Very large pack size.** A pack of 10,000 is legitimate — resistors, washers. The derived
  per-item price may round to $0.00. That is a real outcome: state it, do not refuse it.
- **The same item on two lines.** An order can carry one ASIN twice. A pack size set on one line
  must not move to the other; lines are steered by position, as every other per-line control on
  this page already is.
- **Repeat purchase against an existing product.** The review's *"you have N at $x, this order says
  M at $y — update it?"* question must compare the **converted** numbers. Otherwise every pack line
  reports a discrepancy that does not exist.
- **Receiving a pack purchase.** "I counted the shelf" at receipt (feature 041) adds the purchase's
  quantity to the count. That is now items, which is what makes it right — no new behavior, but it
  is the reason the quantity has to be correct.
- **A line excluded from the capture.** A pack size entered on a line the operator then excludes is
  discarded with the line; re-including it does not silently resurrect a stale value.
- **A purchase edited by hand after capture.** Editing a captured purchase's quantity or price must
  not leave stored pack values that contradict it. Either they are kept consistent or they are
  cleared; a purchase must never state a pack arithmetic that does not produce its own numbers.
- **Purchases recorded before this feature.** They hold no pack data and none is inferred. No
  backfill, no migration of values, and no page may imply a pack size of 1 was *stated* where
  nothing was stated at all.
- **A hand-recorded purchase.** Recording a purchase by hand without any capture states no pack,
  and must not be made to.

## Requirements *(mandatory)*

### Functional Requirements

#### A. The pack field on the Amazon order review *(US1)*

- **FR-001**: The order review MUST offer, for each line of an Amazon order, a way for the operator
  to state how many individual items one of that line's units contains.
- **FR-002**: The pack size MUST default to 1, so a review the operator does not touch confirms
  exactly what it confirms today.
- **FR-003**: The field MUST be labelled so it cannot be confused with how many were ordered — it
  is how many came in one, not how many were bought.
- **FR-004**: Each line's pack size MUST be independent of every other line's, including two lines
  carrying the same item.

#### B. The conversion *(US1)*

- **FR-005**: The recorded quantity for a line MUST be the quantity the vendor stated multiplied by
  the pack size.
- **FR-006**: The recorded unit price MUST be the price the vendor stated divided by the pack size,
  rounded to the cent by this application rather than by the database.
- **FR-007**: Both derived values MUST be shown before anything is confirmed, and both MUST remain
  editable; a value the operator types over is the value recorded.
- **FR-008**: Where the division does not land exactly on a cent, the page MUST say so in words on
  that line, as the McMaster review already does.
- **FR-009**: A pack size MUST NOT create a quantity or a price where the vendor supplied none. A
  line with an unread quantity or price stays marked unread for that field.
- **FR-010**: Every comparison the review makes against an existing product's recorded purchase
  MUST use the converted quantity and price, not the vendor's stated ones.

#### C. Refusals and re-renders *(US1)*

- **FR-011**: A pack size that is not a whole number of at least 1 MUST be refused with a message
  naming the line, and MUST NOT be silently coerced to 1.
- **FR-012**: A refused page MUST come back with every pack size, quantity, price and per-line
  decision the operator entered still present.
- **FR-013**: Nothing MUST be written for any line of an order whose review carries a refused pack
  size.

#### D. Showing the conversion *(US2)*

- **FR-014**: The review MUST distinguish, per line, a quantity and price converted from a pack
  from ones recorded as the vendor stated them.
- **FR-015**: A converted line MUST state the arithmetic it performed, so it can be checked against
  the box in the operator's hands and against the vendor's page.
- **FR-016**: A converted line MUST keep the vendor's own numbers visible beside the catalog's.
- **FR-017**: The review's standing note that quantities and prices are *"as Amazon stated them"*
  MUST no longer be asserted of a converted line.

#### E. Suggesting a pack size *(US3)*

- **FR-018**: Where a line's listing was read during capture and states a pack count in a
  structured field, the review MUST offer that number as the line's pack size.
- **FR-019**: Where a listing title names a pack count in a common form — `Pack of N`, `N Pcs`,
  `N-Pack`, `Set of N` and their ordinary variations — the review MUST offer that number.
- **FR-020**: A suggested pack size MUST be marked as read from the listing, distinguishably from
  one the operator entered, from the moment the review renders until it is confirmed.
- **FR-021**: A suggestion MUST be overrulable; a value the operator sets MUST NOT be replaced by
  the suggestion on any later re-render, and MUST no longer be marked as a guess.
- **FR-022**: A listing that was not read, states no pack count, or names a number that is not a
  pack count MUST leave the default of 1 and MUST NOT cause a guess.

#### F. The single-listing confirmation page *(US4)*

- **FR-023**: The confirmation page's Quantity MUST be derived from the pack fields the same way
  its Unit Price already is — how many packs were bought, multiplied by how many came in one.
- **FR-024**: The operator MUST be able to state how many packs they bought, distinctly from how
  many items that makes.
- **FR-025**: A derived Quantity MUST remain editable, and a typed value MUST be what is recorded.
- **FR-026**: With a pack size of 1, or no pack stated, the page MUST behave exactly as it does
  today.
- **FR-027**: The page's help text MUST be corrected so Quantity and the pack fields say what they
  now do.

#### G. Keeping what the pack was *(US5)*

- **FR-028**: A purchase captured from a pack line MUST retain how many items were in one pack and
  what one pack cost.
- **FR-029**: What is retained MUST be sufficient to restate the vendor's own line — how many packs
  at what price per pack — beside the catalog's items and per-item price.
- **FR-030**: **All three capture paths MUST retain it consistently**: the Amazon order review, the
  McMaster order review — which today converts and discards — and the single-listing confirmation
  page.
- **FR-031**: A purchase with no pack, one recorded by hand, and one recorded before this feature
  MUST retain nothing about a pack and MUST NOT be shown as a pack of 1.
- **FR-032**: Existing purchases MUST NOT be altered or backfilled. What they hold now is what they
  hold afterwards.
- **FR-033**: A stored pack MUST never contradict the purchase's own quantity and price. Editing a
  captured purchase's quantity or price MUST leave the two consistent or clear the pack values; it
  MUST NOT leave arithmetic that does not produce the stored numbers.
- **FR-034**: Where a purchase carries a pack, the page showing that order MUST show both views.

#### H. Documentation *(US5, and decision C)*

- **FR-035**: Every document asserting that pack values are not stored MUST be corrected — at
  minimum the user manual's *"Neither pack field is stored — they exist to work the unit price out
  and are forgotten the moment you capture"*.
- **FR-036**: The user manual MUST describe the Amazon order review's pack size, including that a
  suggested one is a guess the operator is responsible for checking.
- **FR-037**: The user manual's account of the single-listing confirmation page MUST match FR-023
  — it currently tells the operator Quantity is items while the page treats it as packs.
- **FR-038**: The user manual's McMaster chapters MUST say that the pack is now kept, not
  discarded.

#### I. Scope boundaries

- **FR-039**: McMaster's *conversion* MUST be unchanged — it already produces units and a unit
  price correctly. Only the retention in FR-030 is added to it.
- **FR-040**: DigiKey order capture MUST be unchanged. Its quantities come from a service already
  in items, and its review is not editable.
- **FR-041**: The product label MUST be unchanged. Its `$x.xx ea` is a per-item price, which this
  feature makes correct rather than changing.
- **FR-042**: Stock counts, low-stock thresholds and the reorder list MUST be unchanged. They
  already work in items; this feature only stops feeding them wrong ones.

### Key Entities

- **Order line (under review, not persisted)**: one row of a captured order. Today it carries what
  the vendor's page stated — an item number, a description, a quantity and a price — plus, since
  feature 044, whatever its own listing said. This feature adds how many items are in one of its
  units, where that number came from, and the quantity and price it implies.
- **Purchase (persisted)**: what the catalog records for one line once confirmed. Its quantity and
  unit price are in individual items — already the contract every other part of the catalog reads
  it by. This feature makes Amazon's meet that contract, and adds what the pack was, so the
  vendor's own line can be restated.
- **Pack**: how many items came in one of what the vendor sold, and what one of those cost. Not a
  product attribute and not a stock unit — a property of one purchase, because the same product can
  be bought loose one time and in a pack of 100 the next.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Capturing the reported four-line order of packs records, for every line, a quantity
  equal to the items actually received and a price per individual item — with no arithmetic done
  outside the application.
- **SC-002**: For a pack line whose listing names its count, the operator supplies **no** number to
  get a correct purchase; for one whose listing does not, they supply exactly one.
- **SC-003**: A four-line order of packs is reviewed and confirmed in under two minutes, against
  roughly four minutes for today's workaround — a division and two field edits per line, done
  off-screen.
- **SC-004**: Reading a review of a mixed order, the operator can name which lines were converted,
  which were guessed at, and which were recorded as stated, without consulting the vendor's page.
- **SC-005**: An order or listing with no pack produces records identical to what today's capture
  produces — the change costs nothing when it is not needed.
- **SC-006**: No recorded per-item price is ever off by a factor of the pack size on any line the
  operator stated or accepted a pack size for.
- **SC-007**: Every pack purchase captured through any of the three paths can be reconciled against
  the vendor's invoice from the catalog alone, with no visit to the vendor's site.
- **SC-008**: No purchase recorded before this feature changes in any respect.
- **SC-009**: No document tells the operator that pack values are discarded.

## Assumptions

- **The pack size is the operator's to state, not the application's to determine.** Amazon puts
  pack counts in free-text titles with no reliable field, so anything read from there is a
  suggestion the operator is answerable for. Decision B accepts that a pre-filled guess left
  untouched takes effect; US2's marking is what makes that acceptable, which is why US2 outranks
  US3.
- **Prices stay exact.** Every value on this path is a decimal quantity end to end. The division is
  performed and rounded where the rest of the application's price arithmetic is — never in the
  browser and never through a binary floating-point value, in transit or otherwise (Constitution
  III).
- **Nothing is written before confirmation.** A review is still a page the operator can close with
  no record made, and a refusal still writes nothing for any line.
- **The manual route survives.** Every derived value stays editable, and an operator who prefers to
  type both numbers directly loses nothing.
- **Storing the pack reverses a standing decision, deliberately.** Three places in the code and one
  in the manual currently assert that pack values are not kept. That was the right call while the
  pack was only a calculator; it stops being right once a captured order has to reconcile against
  an invoice and once a pack size can be a guess that needs auditing. The reversal is the author's
  decision (C), not an oversight to be re-litigated during planning — but it does mean a schema
  change and a migration, under Constitution V.
- **Pack is a property of a purchase, not of a product.** The same screw can be bought loose once
  and in a bag of 100 the next time, so nothing about a pack belongs on the product.
- **Existing captured purchases stay wrong.** Orders already captured with pack lines hold wrong
  quantities. Correcting them is the operator's to do by editing those purchases, and is not part
  of this feature.
