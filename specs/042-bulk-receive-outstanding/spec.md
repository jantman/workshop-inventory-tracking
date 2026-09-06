# Feature Specification: Bulk-Receiving Outstanding Purchases from a Backfill

**Feature Branch**: `robot-army/issue-140-no-way-to-bulk-receive-already-captured`

**Created**: 2026-09-06

**Status**: Draft

**Input**: GitHub issue #140 — "No way to bulk-receive already-captured outstanding orders during a historical backfill", raised during the #80 verification pass.

## Overview

Capturing an order records every line as **outstanding** — a purchase with no receipt date.
That is right for an order placed this week and wrong for one placed in 2023, so feature 031
added an "this order has already arrived" tick to the review screen: one click marks every line
of a backfilled order received, dated from the order itself rather than from today.

That covers the backfill done from here on. It does not cover what is already in the database.
An order captured before that tick existed, or one where the operator forgot it, sits
outstanding for ever with no retroactive equivalent — the reorder list keeps reporting a
two-year-old delivery as on the way, and the captured-orders list keeps reporting the order as
incomplete. The only route back today is to open each purchase's receive screen one at a time,
which for a backfill of any size is not a route at all.

So this feature adds one management command that does retroactively what the capture-time tick
does at capture: mark outstanding purchases received, dated from their own order date.

Two things bound it, and they are the whole design:

**It is the backfill receipt, not the receiving-desk receipt.** Feature 031 drew this
distinction deliberately (031 FR-028): a delivery from two years ago has already been consumed,
so recording its arrival must not raise a counted on-hand quantity, must not touch that count's
age, and must not clear a low-stock flag somebody set last month about today's shelf. The
capture path satisfies this by writing the receipt date and nothing else. This command does the
same thing for the same reason — **one rule, not two.**

**It is a one-time backfill tool, so it gets no UI.** A command run a handful of times during a
historical import does not deserve a screen, and the per-purchase receive screen already exists
for the ordinary case.

The command is deliberately blunt: it selects by vendor and by an order-date cutoff, shows
exactly what it would touch, and asks before writing. There is no per-line selection, because
per-line handling is what the existing screens are for and this exists precisely to avoid going
line by line.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Closing out a backfill that was captured as outstanding (Priority: P1)

The operator has backfilled four years of DigiKey orders. Every line went in outstanding,
because the orders were captured before the "already arrived" tick existed. The reorder list
now claims 300 parts are on the way. They run the command for DigiKey with a cutoff of the
start of this year, read the list of what it would touch, confirm, and the whole backlog is
marked received — each line dated from its own order.

**Why this priority**: It is the feature. Without it there is nothing here.

**Independent Test**: Seed several outstanding purchases with order dates spread over past
years, run the command against them, and verify each becomes received with a receipt date equal
to its own order date.

**Acceptance Scenarios**:

1. **Given** several outstanding purchases for a vendor with order dates before the cutoff,
   **When** the command is run for that vendor and cutoff and confirmed, **Then** every one of
   them is recorded as received.
2. **Given** such a purchase ordered on a stated date, **When** it is received by this command,
   **Then** its recorded receipt date is that same order date, not today's date.
3. **Given** the orders those purchases belong to, **When** the command has run, **Then** the
   captured-orders list reports each order as having no outstanding lines.
4. **Given** the products those purchases are for, **When** the command has run, **Then** the
   reorder list no longer reports any of them as being on the way on account of those
   purchases.

---

### User Story 2 - Seeing exactly what would happen before anything happens (Priority: P1)

Before committing, the operator runs the same command with `--dry-run`. It prints every
purchase it would touch — vendor, order number, order date, product, quantity — and a summary,
and writes nothing. They spot one line for a part that genuinely has not arrived, narrow the
cutoff, and run again.

**Why this priority**: It ranks alongside Story 1, not below it. A bulk receipt is not
individually reversible: undoing one means deleting the purchase and re-capturing it, which
during a backfill means redoing work. The operator has to be able to see the blast radius
before it goes off, and that is the only control this command offers for a mixed order.

**Independent Test**: Run the command with `--dry-run` against seeded outstanding purchases and
verify each one is named in the output and that every purchase is still outstanding afterwards.

**Acceptance Scenarios**:

1. **Given** outstanding purchases matching the filters, **When** the command is run with
   `--dry-run`, **Then** each matching purchase is listed with enough detail to identify it and
   nothing is written.
2. **Given** the same state, **When** the command is run without `--dry-run`, **Then** it lists
   the same purchases and asks for confirmation before writing.
3. **Given** that confirmation prompt, **When** the operator declines, **Then** nothing is
   written and the command says so.
4. **Given** filters that match no outstanding purchase, **When** the command is run, **Then**
   it says so plainly, writes nothing, and does not ask for confirmation.

---

### User Story 3 - A backfill receipt is not a receiving-desk receipt (Priority: P1)

A product whose stock is counted has 4 on the shelf, counted in January. A 2023 order for 100
of them is swept up by this command. The product still reads 4, still counted in January — the
hundred were used years ago, and nobody has looked in the drawer.

**Why this priority**: This is the invariant feature 031 established and the one thing this
command could quietly get wrong at scale. Getting it wrong across a whole backfill would
inflate every counted quantity in the catalog by years of consumed stock, and the operator
would have no way to tell which numbers were wrong.

**Independent Test**: Seed a product with a tracked count, an age, and a manually set low-stock
flag; sweep an outstanding purchase for it; verify the count, its age, and the flag are all
unchanged and only the receipt date moved.

**Acceptance Scenarios**:

1. **Given** a product with a tracked on-hand count, **When** a purchase for it is received by
   this command, **Then** the count is unchanged.
2. **Given** a product whose count carries an age, **When** a purchase for it is received by
   this command, **Then** that age is unchanged.
3. **Given** a product with a manually set low-stock flag, **When** a purchase for it is
   received by this command, **Then** the flag is still set.
4. **Given** a product with no tracked count, **When** a purchase for it is received by this
   command, **Then** no count is created.

---

### User Story 4 - Leaving alone what it cannot honestly date (Priority: P2)

Some purchases carry no order date at all — the vendor showed none. The command cannot say when
those arrived, and today is the one answer that is certainly wrong. It leaves them outstanding
and reports how many it left.

**Why this priority**: It is a small population and the outcome is "nothing happened", which is
safe. It is stated because silence would be worse than the skip: an operator who thinks the
sweep was total will not go looking for the remainder.

**Independent Test**: Seed an outstanding purchase with no order date alongside dated ones, run
the command, and verify the dated ones are received, the undated one is not, and the output
accounts for it.

**Acceptance Scenarios**:

1. **Given** an outstanding purchase with no order date, **When** the command is run, **Then**
   that purchase is left outstanding.
2. **Given** the same run, **When** it reports its results, **Then** it states how many
   purchases it skipped for having no order date.

---

### Edge Cases

- **A purchase already received** is not selected. Only outstanding purchases are candidates,
  and an existing receipt date is never overwritten.
- **A mixed order** — most lines delivered long ago, one genuinely still on order — has no
  per-line control here. The operator's tools are the cutoff date and the dry run; where those
  cannot separate the lines, the per-purchase receive screen is still the answer for that
  order. The command does not pretend otherwise.
- **A vendor name typed in the wrong case** still matches, because the stored vendor names are
  fixed strings the operator is recalling rather than reading.
- **A vendor that matches nothing** produces the same "nothing to do" outcome as an empty
  match, not an error.
- **An unparseable or absurd cutoff date** is refused before anything is read, with the
  offending value named.
- **A run interrupted part way** must not leave half a sweep applied; the sweep either lands
  whole or not at all.
- **Running the command twice** with the same arguments is safe: the second run finds nothing
  outstanding and says so.

## Requirements *(mandatory)*

### Functional Requirements

**Selection**

- **FR-001**: The operator MUST be able to mark every outstanding purchase matching a stated
  set of filters as received, in one action, from the command line.
- **FR-002**: Only purchases with no recorded receipt date MUST be selected. An already-received
  purchase MUST NOT be selected and its receipt date MUST NOT be altered.
- **FR-003**: The operator MUST be able to restrict the selection to a single vendor. Vendor
  matching MUST ignore case and surrounding whitespace.
- **FR-004**: The operator MUST state a cutoff date, and only purchases ordered strictly before
  it MUST be selected. The cutoff is mandatory: an unbounded sweep of every outstanding purchase
  is not offered.
- **FR-005**: When no vendor is stated, purchases from every vendor MUST be eligible, subject to
  the cutoff.
- **FR-006**: A purchase with no order date MUST NOT be selected, whatever the filters, because
  there is no date from which to derive its arrival and no date to compare against the cutoff.
  The count of such purchases MUST be reported.
- **FR-007**: Selection MUST NOT depend on how the purchase was recorded. A hand-recorded
  outstanding purchase from 2023 is the same problem as a captured one and MUST be eligible.

**What receiving means here**

- **FR-008**: The receipt date recorded for each selected purchase MUST be that purchase's own
  order date. It MUST NOT be today's date. This is the rule feature 031 already established for
  a backfilled arrival (031 FR-026), reused rather than restated.
- **FR-009**: Receiving through this command MUST NOT change any product's on-hand count.
- **FR-010**: Receiving through this command MUST NOT change the age of any product's on-hand
  count.
- **FR-011**: Receiving through this command MUST NOT clear or change any product's manually set
  stock status.
- **FR-012**: Receiving through this command MUST NOT change any purchase's quantity, price,
  notes, or the product's description.
- **FR-013**: After the command has run, the captured-orders list and the reorder list MUST
  reflect the new receipts exactly as they would had each purchase been marked arrived at
  capture time.

**Showing and confirming**

- **FR-014**: The command MUST, before writing anything, list every purchase it has selected,
  identifying each by at least its vendor, order number, order date, product, and quantity.
- **FR-015**: The command MUST offer a mode that produces that listing and writes nothing.
- **FR-016**: When not in that mode, the command MUST ask the operator to confirm after showing
  the listing and before writing. Declining MUST write nothing and MUST say that nothing was
  written.
- **FR-017**: When the selection is empty, the command MUST say so, write nothing, and MUST NOT
  ask for confirmation.
- **FR-018**: After writing, the command MUST report how many purchases were received and how
  many were skipped for having no order date.
- **FR-019**: An invalid cutoff date or an otherwise unusable argument MUST be refused before
  any purchase is read or written, naming what was wrong.
- **FR-020**: The whole sweep MUST be applied as one unit: either every selected purchase is
  received or none is.

### Key Entities

- **Purchase**: one acquisition of one product. Carries the vendor, the order it came from, its
  order date, and its receipt date. Having no receipt date *is* being outstanding — there is no
  separate status to keep in step.
- **Product**: what was purchased. Carries the on-hand count, that count's age, and a manual
  stock flag — all three of which this feature deliberately leaves alone.
- **Sweep result**: what one run did — the purchases it received, and the ones it skipped for
  having no order date. Reported, not stored.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can clear an entire backfill's worth of wrongly-outstanding purchases
  in a single command, in place of one receive screen per purchase.
- **SC-002**: Every purchase the command receives is dated from its own order, so a delivery
  from 2023 is recorded as having arrived in 2023 and not on the day the command was run.
- **SC-003**: Running the command changes no product's on-hand count, no count age, and no
  manual stock flag — verifiable by comparing every product's stock figures before and after a
  sweep.
- **SC-004**: The operator can see the complete list of purchases a run would affect without
  that run changing anything.
- **SC-005**: After a sweep, no order it fully covered is reported as having outstanding lines,
  and no product is reported as being on the way on account of a swept purchase.

## Assumptions

- **The receipt date question raised in the issue is answered by reusing 031 FR-026's rule**:
  the purchase's own order date. It is the best answer available, and keeping one rule rather
  than two is worth more than any refinement. Where 031 falls back to "now" for an order the
  vendor never dated, this feature skips the purchase instead (FR-006) — 031's fallback exists
  so that a capture can still complete, and there is no capture here to complete.
- **The cutoff is required and the vendor is not.** The cutoff is the safety rail: an order
  placed before it and still outstanding is almost certainly one that arrived and was never
  marked. The vendor filter only narrows further, so leaving it out is a strictly smaller rule
  than requiring it.
- **The issue's premise that a wrong receipt cannot be undone no longer holds**: feature 032
  shipped purchase deletion (issue #130), so a wrongly-received purchase can be deleted and
  re-captured. That route is heavy enough that the dry run and the confirmation are still worth
  their keep, so both remain requirements — but the command is not designed around the receipt
  being irreversible.
- **The capture-time path is already in place.** The issue asks that it be built first; feature
  031 shipped it. This feature is the residue that path cannot reach, and it does not change
  that path.
- **No screen is added.** The existing per-purchase receive screen covers the ordinary case and
  the per-line arrival boxes cover capture time; this is a one-time backfill tool.
- **The command lives beside the existing order backfill helper**, in the same management
  command group as the Amazon order-URL helper, because it belongs to the same one-time job.

## Out of Scope

- Per-line or per-order selection within a run. The cutoff date and the dry run are the controls
  offered; anything finer is what the existing per-purchase screens are for.
- Un-receiving a purchase, in bulk or otherwise.
- Any change to the capture-time "this order has already arrived" path, to the per-purchase
  receive screen, or to what an ordinary receipt does to a count.
- Amending quantity, price, notes, or description while sweeping.
