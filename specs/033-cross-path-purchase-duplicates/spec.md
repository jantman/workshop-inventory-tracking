# Feature Specification: Recognize a Listing Capture and an Order Line as One Purchase

**Feature Branch**: `033-cross-path-purchase-duplicates`

**Created**: 2026-09-01

**Status**: Draft

**Input**: User description: "issue #129 on this repo — Capturing an order writes a duplicate purchase for a product already captured from its listing"

## User Scenarios & Testing *(mandatory)*

The operator is the only user. Everything below is one person capturing the same physical
purchase twice — once from the product's listing page, once from the order that product
came on — and the application having to notice that those two captures describe one event.

### User Story 1 - An order capture recognizes a purchase already captured from the listing (Priority: P1)

The operator captures a product from its Amazon listing page while deciding to buy it, and
a purchase is recorded. Days later the order arrives in their order history and they
capture the whole order from `/your-orders/order-details`. One line of that order is the
product they already captured. The review tells them so, naming the purchase already
recorded and what it says, and the capture does not silently write a second purchase for
the same physical purchase.

**Why this priority**: This is the reported defect, confirmed live on product 10 (ASIN
`B0G43FCHFX`, order `111-9281973-9357866`), and it is the direction that actually happened.
It corrupts spend, quantity-on-order and the reorder list, and until feature 032 shipped
there was no way to undo it. On its own it is a complete fix for the observed failure.

**Independent Test**: Capture a product from a listing, then capture an order containing
that same item, and confirm the catalog holds one purchase for it rather than two — or that
the operator was asked and got what they chose.

**Acceptance Scenarios**:

1. **Given** a purchase recorded from a listing capture for vendor V and item id X, with no
   order number on it, **When** the operator reviews an order from vendor V containing a
   line for item X ordered within 90 days of it, **Then** the review states that a purchase
   for this line is already recorded, shows its date, quantity and unit price beside the
   order's, offers the choice between adopting it and recording a separate purchase, and
   does not present the line as new.
2. **Given** that review, **When** the operator answers "same purchase" and confirms,
   **Then** the catalog holds exactly one purchase for that line, carrying the order's
   number and its line number.
3. **Given** that review, **When** the operator answers "a separate purchase" and confirms,
   **Then** a second purchase is recorded for the line and the earlier one is left exactly
   as it was.
4. **Given** that review, **When** the operator confirms with the line included but the
   question unanswered, **Then** the capture is refused and nothing at all is written.
5. **Given** that same line, **When** the order's quantity or unit price differs from what
   the listing capture recorded, **Then** the difference is shown and the operator can
   choose to apply the order's values, using the same mechanism a re-captured line already
   uses.
6. **Given** the listing-captured purchase was already marked received, **When** the order
   capture claims it, **Then** it stays received with its received date and quantity intact.
7. **Given** an order line for an item the operator bought more than 90 days before this
   order's date — an earlier purchase for the same vendor and item that is not part of this
   order — **When** the order is reviewed, **Then** that older purchase is not offered as a
   candidate, no question is raised, and the line is captured as its own purchase.
8. **Given** an order carrying two lines for the same item id, **When** one
   listing-captured purchase exists for that item, **Then** at most one of those lines
   claims it and the other is captured as its own purchase.

---

### User Story 2 - A listing capture recognizes a purchase already captured from an order (Priority: P2)

The operator captures a whole order, then later — reading about the product, or reordering
it — clicks the single-listing bookmarklet on one of its listing pages. The dates disagree,
because the operator types the date they remember and the vendor states its own. The
application still recognizes that this is a purchase it already holds and asks rather than
recording a second one.

**Why this priority**: `specs/029-whole-order-capture/spec.md:103` claims this direction is
already covered by the existing duplicate handling. It is not: that handling requires the
two purchases to fall on the same calendar day, and an operator-typed date is exactly the
value least likely to match the vendor's — in the reported case the two rows were four days
apart. The direction is less likely than User Story 1 but produces the identical corruption.

**Independent Test**: Capture an order, then capture one of its items from its listing page
with a deliberately different order date, and confirm the operator is asked rather than a
second purchase appearing unannounced.

**Acceptance Scenarios**:

1. **Given** a purchase recorded by an order capture for vendor V and item id X, **When**
   the operator captures item X from its listing page for vendor V and states an order date
   that differs from the order's by a few days, **Then** the existing duplicate question is
   raised, naming the recorded purchase and the order it belongs to.
2. **Given** that question, **When** the operator says it is the same purchase, **Then** no
   second purchase is written, and the existing purchase keeps its order number and line
   number.
3. **Given** that question, **When** the operator says it is a genuinely separate purchase,
   **Then** a second purchase is recorded, as the existing acknowledged-duplicate path
   already does.
4. **Given** no purchase exists for that vendor and item, **When** the operator captures the
   listing, **Then** no question is raised and the capture proceeds exactly as it does today.

---

### User Story 3 - The same protection on McMaster and DigiKey orders (Priority: P3)

The operator captures a McMaster part or a DigiKey part from its product page, then captures
the order it came on. The same recognition applies.

**Why this priority**: The blind spot is in shared code — every vendor's order capture pairs
lines only against purchases that already carry that order's number — so all three vendors
have it. It is listed separately because it is less likely to have bitten: a DigiKey part is
rarely captured from a listing page first. Doing it for one vendor and not the others leaves
the same defect standing under a different name.

**Independent Test**: Capture a McMaster part from its product page, then capture an order
containing it, and confirm the same single-purchase outcome as User Story 1.

**Acceptance Scenarios**:

1. **Given** a purchase recorded from a McMaster product-page capture, **When** an order
   containing that part number is reviewed and confirmed, **Then** the outcome matches User
   Story 1 for Amazon.
2. **Given** the same for a DigiKey part number, **When** an order containing it is reviewed
   and confirmed, **Then** the outcome matches User Story 1.
3. **Given** every existing capture, review, order-screen, receiving and scanning behavior,
   **When** this feature is complete, **Then** all of it behaves as it did before,
   demonstrated by the existing tests passing unchanged.

---

### Edge Cases

- **A purchase recorded by hand against the same order.** Already claimed today, by the
  existing pass that matches on item id where no line number is recorded. Whatever claims a
  listing-captured purchase must not take that case away from it, and must not let both
  passes claim the same row twice.
- **The operator has bought the same item repeatedly.** Two listing-captured purchases for
  the same vendor and item, both inside the 90-day window, and an order that contains it
  once. At most one can be the order's; the rest must be left alone, and the operator must be
  able to tell them apart from what the review shows.
- **A repeat purchase just outside the window.** The same item bought again 100 days later
  is two purchases with no question raised — the window is what makes that so, and it is a
  deliberate trade: a duplicate that far apart goes unnoticed rather than the operator being
  asked about every staple they reorder.
- **The same item on two lines of one order.** Amazon states no line number on the page and
  an order can carry the same item twice. A single candidate purchase must not be claimed by
  both lines, and must not merge them.
- **The candidate purchase belongs to a different order.** A purchase already carrying an
  order number is not a candidate for a different order, whatever its dates say.
- **The candidate was already received.** Claiming it must not undo the receipt, move a
  tracked count, or clear a manual low flag — that state was recorded by a person holding the
  goods.
- **The order line is excluded from the capture.** Nothing is claimed and the existing
  purchase is untouched.
- **A purchase is claimed and the capture then fails on a later line.** The whole order
  writes in one transaction or none of it does; a claim must roll back with everything else.
- **The order date is unknown.** A vendor page that stated no order date, or a listing
  capture with none — a candidate cannot be dated against a date that does not exist.
- **The already-duplicated data that exists today.** Product 10 carries purchases 10 and 11
  for one physical purchase. This feature does not clean that up; feature 032 (deleting a
  purchase) is how it is corrected. That pair is a fixture for confirming the fix behaves
  sensibly against data that already went wrong.

## Requirements *(mandatory)*

### Recognizing the same physical purchase

- **FR-001**: When reviewing an order, the system MUST consider, as a candidate for a line,
  any purchase for the same vendor and the same vendor item id that carries no supplier order
  number — not only purchases already carrying this order's number.
- **FR-002**: A purchase that already carries a supplier order number MUST NOT be considered
  a candidate for a different order.
- **FR-003**: A candidate's order date MUST fall within 90 days of the order's own date.
  Two purchases for the same item placed further apart than that are two purchases and MUST
  NOT be offered as one. The window is deliberately generous: it is the range within which
  the operator is *asked*, not the range within which anything is merged, and the reported
  case was four days.
- **FR-004**: Each candidate purchase MUST be claimable by at most one line of an order, and
  a line that already matched an exactly-recorded purchase (by order number and line number)
  MUST NOT also claim a candidate.
- **FR-005**: Candidate recognition MUST NOT displace the existing pairing rules: pairing by
  order number and line number MUST still run first and win, and a hand-recorded purchase
  carrying this order's number MUST still be claimed as it is today.
- **FR-006**: A purchase whose order date cannot be compared — either side missing a date —
  MUST NOT be treated as a candidate.

### What the operator sees and decides

- **FR-007**: The order review MUST state, for a line with a candidate purchase, that a
  purchase for this item is already recorded and MUST show what it records — its date, its
  quantity and its unit price — beside what the order states.
- **FR-008**: The operator MUST decide, per line, whether the candidate is the same physical
  purchase — adopting it into this order — or a genuinely separate one, which records a new
  purchase as the capture does today. The system MUST NOT decide this on its own.
- **FR-008a**: An included line carrying a candidate MUST NOT be captured without that answer.
  A confirmation that omits it MUST be refused with nothing written, the way a conflicted line
  with no resolution already is.
- **FR-008b**: A line the operator excludes needs no answer, and excluding it MUST leave the
  candidate purchase untouched.
- **FR-009**: Where the order's quantity or unit price differs from the claimed purchase's,
  the difference MUST be shown, and applying the order's values MUST be the operator's
  choice — the same choice a re-captured line already offers.
- **FR-010**: Nothing MUST be written until the operator confirms the review. An abandoned
  review MUST leave the candidate purchase exactly as it was.
- **FR-011**: The result of a confirmed capture MUST distinguish purchases it claimed from
  purchases it created, so the operator can see that no new row was written for a claimed
  line.

### What claiming a purchase does to it

- **FR-012**: Claiming a purchase MUST stamp it with the order's supplier order number and
  the line's line number, so that a later re-capture of the same order pairs to it exactly
  and raises no question a second time.
- **FR-013**: Claiming a purchase MUST NOT create a second purchase for that line.
- **FR-014**: Claiming a purchase MUST preserve its received state: a received purchase stays
  received with its received date, and no tracked count moves and no manual low flag clears
  as a result of the claim.
- **FR-015**: Claiming a purchase MUST NOT change the product it is attached to. Where the
  order line's own product resolution names a different product, that is the existing
  contradicted-identifier decision and MUST be raised as such rather than silently rerouting
  the purchase.
- **FR-016**: Every write a claim performs MUST be part of the order capture's single
  transaction: the whole order is captured or none of it is.

### The reverse direction — capturing a listing after the order

- **FR-017**: A single-listing capture MUST recognize an existing purchase for the same
  vendor and item id that carries a supplier order number, even when the two order dates fall
  on different calendar days, within the same 90-day tolerance FR-003 states.
- **FR-018**: Recognizing one MUST raise the existing duplicate question, naming the recorded
  purchase and the supplier order number it carries, and MUST write nothing until the
  operator answers.
- **FR-019**: The operator MUST be able to answer that it is the same purchase — recording
  nothing further — or that it is a separate one, which records a second purchase as the
  existing acknowledged-duplicate path already does.
- **FR-020**: Where no such purchase exists, the single-listing capture MUST behave exactly
  as it does today, including its existing same-day duplicate recognition.

### Scope across vendors

- **FR-021**: FR-001 through FR-016 MUST apply to every vendor whose orders can be captured —
  Amazon, McMaster-Carr and DigiKey — not to Amazon alone.
- **FR-022**: All existing capture, review, order-screen, receiving and scanning behavior MUST
  be unchanged, demonstrated by the existing test suites passing without being edited to
  accommodate this feature.
- **FR-023**: A regression test reproducing the reported failure — capture a listing, then
  capture an order containing it, assert one purchase — MUST exist and MUST be confirmed
  failing before the fix and passing after it.

### Key Entities

- **Purchase**: One acquisition of one product. Carries the vendor, the vendor's item id, an
  order date, an optional received date, a quantity and a unit price, and optionally the
  supplier's order number and the line number within it. The absence of a supplier order
  number is what makes a purchase a candidate for adoption by an order.
- **Order**: Not stored. An order *is* the purchases carrying its number; this feature does
  not add a table for one.
- **Order line**: One item on an order, identified by the vendor's item id and its position
  on the order. A vendor item id does not identify a line — an order can carry the same item
  twice.
- **Candidate**: A purchase that could be the same physical purchase as an order line —
  same vendor, same item id, no supplier order number, order date close enough to the
  order's.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Capturing a product from its listing page and then capturing the order it came
  on leaves exactly one purchase for that product, in 100% of cases where the operator
  indicates they are the same purchase.
- **SC-002**: The reported case reproduces green: the exact sequence that produced purchases
  10 and 11 produces one purchase.
- **SC-003**: Capturing an order and then capturing one of its items from its listing page
  with an order date differing by several days raises a question rather than silently
  recording a second purchase, in 100% of attempts.
- **SC-004**: A second capture of the same order after a claim asks nothing and writes
  nothing new — the claimed purchase reads as an ordinary already-captured line.
- **SC-005**: Two genuinely separate purchases of the same item are never merged without the
  operator saying so — 0 automatic claims across the test cases covering repeat purchases,
  purchases more than 90 days apart, and orders carrying an item twice.
- **SC-006**: Product spend, quantity-on-order and the reorder list report each physical
  purchase once after both capture paths have been used on it.
- **SC-007**: Every existing test in the unit and E2E suites passes unedited.

## Assumptions

- **The operator's intent is what settles an ambiguous case.** Where the application cannot
  know whether two records describe one purchase, it asks rather than deciding — the posture
  `capture_order` already takes for a same-day duplicate and a recycled identifier. This is
  the answer to FR-008: the review is where the operator already decides everything else
  about a line, so the decision belongs there rather than in an automatic merge they would
  discover afterwards.
- **A 90-day window is a question, not a merge.** Nothing is joined without an answer, so the
  window being generous costs an occasional question about a repeat purchase and buys never
  missing a real duplicate that the operator's typed date put weeks away from the vendor's.
- **The vendor's order page is the authority on order facts.** Its date, quantity, unit price
  and order number are better than an operator's recollection typed days earlier — but they
  are applied to a claimed purchase only through the existing "apply this change" choice, not
  silently.
- **The receipt is the operator's, not the vendor's.** A received date already recorded
  survives any claim, and claiming never performs the side effects of receiving.
- **Cleaning up data already duplicated is out of scope.** Feature 032 supplies deletion; this
  feature stops new duplicates being created.
- **No new stored state is needed to recognize a candidate.** Vendor, item id, order date and
  the presence or absence of a supplier order number are all already recorded.
- **The single-listing capture's existing same-day duplicate rule stays.** FR-017 widens what
  it can see for one specific case; it does not replace the rule for captures that have
  nothing to do with an order.
- **Both capture paths continue to exist.** Nothing here proposes retiring the single-listing
  bookmarklet in favor of order capture.

## Dependencies

- Feature 032 (deleting a purchase) is the recovery path for the duplicates already recorded,
  and is referenced by the edge cases above. It is merged; this feature does not depend on it
  for its own behavior.
- Feature 029 (whole-order capture) supplies the review-and-confirm flow, the line states and
  the pairing rules that this feature extends. Its `spec.md:103` claim about the reverse
  direction is corrected by User Story 2.
- Issue #129 is the source of record for the observed failure, including the live data that
  demonstrates it.
