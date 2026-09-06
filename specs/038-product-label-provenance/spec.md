# Feature Specification: Product label provenance — identity, per-unit price, copy count

**Feature Branch**: `robot-army/issue-141-a-product-label-omits-manufacturer-and`

**Created**: 2026-09-06

**Status**: Draft

**Input**: GitHub issue #141 — "A product label omits manufacturer and part number, and its price does not say it is per unit"

## Context

A printed product label carries the product description, a scannable code, the human-readable
form of that code, and a single provenance line built from the product's most recent purchase:
vendor, order date, price.

Two things are wrong with what that line says, and one thing is missing from how labels are
requested.

1. **The price does not say what it is a price for.** It is the *unit* price, printed without
   qualification onto a bag that may hold five of the thing. A bag reading `$6.50` that holds
   $32.50 of parts is a wrong answer to the question the label exists to answer. A screen can be
   re-read against the record; a label in a drawer is consulted precisely so that nobody has to.
2. **The two fields needed to re-order or identify the part are absent.** The product record
   carries a manufacturer and a manufacturer part number. Neither reaches the label. Once the bag
   is open and the box is gone, those are what identify the part — arguably more useful than the
   order date that *is* printed.
3. **Product labels can only be printed one at a time.** Item labels accept a count of 1–99. The
   product label path offers no count, so printing five means clicking through the dialog five
   times.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read the price on a bag and know what it means (Priority: P1)

The operator prints a label for a product bought at $6.50 each and sticks it on a bag of five.
Months later they pick the bag up and read the label. The printed price is marked as a per-unit
price, so the operator knows the bag holds five times that, not $6.50 of parts.

**Why this priority**: This is the ambiguity that makes an already-printed label actively
misleading. It costs three characters and removes a wrong answer from a durable artifact.

**Independent Test**: Print (or compose) a label for a product whose most recent purchase has a
unit price, and read the provenance text. It names the price as a per-unit figure. Delivers value
on its own: every label printed after this change is unambiguous, with no other change needed.

**Acceptance Scenarios**:

1. **Given** a product whose most recent purchase has a unit price of 6.50, **When** a label is
   composed for it, **Then** the provenance text presents that price marked as per-unit (`$6.50 ea`)
   rather than as a bare `$6.50`.
2. **Given** a product whose most recent purchase has no unit price recorded, **When** a label is
   composed for it, **Then** no price and no per-unit marker appear, and the rest of the provenance
   is unaffected.
3. **Given** a product with no purchases at all, **When** a label is composed for it, **Then** the
   label prints with description and code only, exactly as it does today.

---

### User Story 2 - Identify and re-order a part from the label alone (Priority: P1)

The operator opens a bag, uses part of it, and the original packaging is long gone. They read the
label and find the manufacturer and the manufacturer part number, which is what they need to search
for a replacement or confirm they have the right thing.

**Why this priority**: This is the issue's substantive request. Without it the label answers
"where did this come from" but not "what is it", which is the question asked more often once the
box is discarded.

**Independent Test**: Compose a label for a product carrying a manufacturer and part number and
confirm both appear in the label's text. Delivers value on its own.

**Acceptance Scenarios**:

1. **Given** a product with manufacturer `MEAN WELL` and part number `IRM-05-5`, **When** a label is
   composed, **Then** both values appear in the label's provenance text.
2. **Given** a product with a manufacturer but no part number, **When** a label is composed,
   **Then** the manufacturer appears and nothing is left blank, dangling, or separated by an empty
   field.
3. **Given** a product with a part number but no manufacturer, **When** a label is composed,
   **Then** the part number appears and nothing is left blank or dangling.
4. **Given** a product with neither manufacturer nor part number but with a purchase, **When** a
   label is composed, **Then** the purchase provenance appears exactly as it would have before this
   change (apart from the per-unit price marker).
5. **Given** a product with a manufacturer and part number but no purchases at all, **When** a label
   is composed, **Then** the manufacturer and part number still appear — provenance is no longer
   conditional on a purchase existing.
6. **Given** any product for which a label is composed, **When** the label is inspected, **Then**
   the scannable code and its human-readable text occupy no less of the label than they did before
   this change. The description gives up space first; the code never does.

---

### User Story 3 - Print several copies of a product label in one go (Priority: P3)

The operator has five bags to label with the same product code and asks for five copies in the
print dialog rather than repeating the dialog five times.

**Why this priority**: A convenience, not a correctness problem, and the smallest of the three. The
label is already correct without it. Listed last so the first two can ship independently.

**Independent Test**: Request a product label with a copy count and confirm that many labels are
sent to the printer. Independently testable and independently shippable.

**Acceptance Scenarios**:

1. **Given** the product label print dialog, **When** the operator sets a copy count of 5 and
   confirms, **Then** five identical labels are produced.
2. **Given** the print dialog, **When** the operator does not touch the copy count, **Then** one
   label is produced — the existing behaviour is the default.
3. **Given** a request carrying a copy count outside the accepted range (below 1, above 99, or not a
   whole number), **When** it is submitted, **Then** it is rejected with a message naming the
   accepted range, and nothing is printed.

---

### Edge Cases

- **A product with no purchases and no manufacturer or part number.** Nothing to say: the label
  prints description and code only, as today.
- **A manufacturer or part number long enough to overflow the line.** The text is shortened to fit
  and visibly marked as shortened, the same way an over-long description already is. It never pushes
  the code off the label.
- **A very long description competing with a longer provenance.** The description is what gives up
  space. The code's share of the label is fixed.
- **A part number that looks like a price or a date.** No inference is made from the value; each
  field is presented in its own position with its own separator so a reader can tell them apart.
- **Values with leading or trailing whitespace, or that are empty strings rather than absent.** These
  are treated as absent, not printed as an empty field with separators around it.
- **A purchase whose unit price is zero.** Zero is a recorded price and prints as one, marked per-unit
  like any other.
- **A copy count that is a boolean, a string, or a fractional number.** Rejected as not a whole
  number rather than coerced.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A product label MUST present the product's manufacturer and manufacturer part number
  when the product record carries them.
- **FR-002**: A product label MUST present a unit price with an explicit per-unit marker, so that the
  figure cannot be read as the value of the labelled package.
- **FR-003**: Provenance MUST degrade gracefully field by field. Any absent, empty, or
  whitespace-only field is omitted along with its separator; no label shows a blank field, a doubled
  separator, or a trailing separator.
- **FR-004**: A product with no purchase history MUST still receive manufacturer and part number on
  its label. Provenance MUST NOT be conditional on a purchase existing.
- **FR-005**: A product with neither manufacturer, part number, nor purchase MUST print exactly as it
  does today — description and code only, with no empty provenance area reserved.
- **FR-006**: The scannable code and its human-readable text MUST NOT be reduced, shortened, or given
  less of the label to make room for the added provenance. This is the existing durability rule
  (FR-012 of the product-label feature) and it is unchanged: the description truncates first.
- **FR-007**: Provenance text that does not fit MUST be shortened and visibly marked as shortened,
  the same way over-long text on the label already is, rather than overflowing or being silently cut.
- **FR-008**: The label MUST continue to be composed from the stored record at print time, so a
  reprint after an edited manufacturer, part number, or purchase reflects the edit.
- **FR-009**: Prices MUST be presented without passing through inexact arithmetic — the printed
  figure MUST be exactly the recorded figure.
- **FR-010**: The product label print request MUST accept a copy count, and MUST produce that many
  identical labels.
- **FR-011**: The copy count MUST default to 1 when not supplied, preserving current behaviour for
  any existing caller.
- **FR-012**: The copy count MUST be validated as a whole number between 1 and 99 inclusive, matching
  the range the item label path already accepts. A request outside that range MUST be rejected with a
  message naming the range, and MUST print nothing.
- **FR-013**: The product label print dialog MUST offer the operator a copy count, consistent with
  how the item label dialog offers one.

### Key Entities

- **Product**: The catalog record being labelled. Carries a description, an internal code, and
  optionally a manufacturer and a manufacturer part number. Both optional fields may be absent
  independently.
- **Purchase**: A record of the product having been bought. Carries a vendor, an optional order date,
  and an optional unit price — a price *per unit*, not per package. The most recent purchase is the
  one whose details reach the label; a product may have none.
- **Product label**: The printed artifact. Carries, in fixed vertical order: the description, the
  provenance, the scannable code, and the human-readable form of that code. Its space budget is
  fixed; what varies is which content yields when the content exceeds it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given only a printed label for a product that has a manufacturer and part number
  recorded, a reader can name the manufacturer and the part number without consulting the
  application. Today this is impossible for 100% of such products; after the change it succeeds for
  100% of them.
- **SC-002**: Given only a printed label showing a price, a reader can correctly say whether the
  figure is per unit or for the whole package, with no other information. Today the label supports no
  such determination.
- **SC-003**: Every combination of present and absent manufacturer, part number, and purchase — eight
  combinations in total — produces a label with no blank field, no doubled separator, and no trailing
  separator.
- **SC-004**: For every label stock offered, the scannable code and its human-readable text occupy at
  least as much of the label after the change as before it, verified against every stock.
- **SC-005**: An operator needing N copies of a product label completes the task in one pass through
  the print dialog for any N from 1 to 99, rather than N passes.
- **SC-006**: A product with no purchase history and no manufacturer or part number produces a label
  byte-for-byte identical to the one it produces today.

## Assumptions

- **Provenance becomes up to two lines rather than one reflowed line.** The issue offers either. Two
  short lines are preferred because they group by question — "what is it" (manufacturer, part number)
  and "where did it come from" (vendor, date, price) — and because two short lines fit at a larger,
  more durable type size than one long line does. The identity line is placed first, on the reasoning
  the issue gives: it answers the question asked more often once the packaging is gone. The space for
  the second line comes from the description's share, never the code's.
- **The per-unit marker is the suffix `ea`**, as the issue suggests: three characters, unambiguous,
  and already the convention on the purchase screens.
- **The order date stays on the label.** The issue observes that manufacturer and part number are
  "arguably more useful than the order date" but does not ask for the date's removal, and removing
  printed information is a separate decision from adding some.
- **Manufacturer and part number come from the product record, not from a purchase.** They are
  attributes of the thing, not of the transaction, and a product with no purchases still has them.
- **The copy count is delivered as part of this feature rather than split out**, per the issue's own
  framing — same file, same trip. It is prioritised P3 so it can be dropped without affecting the
  label content work.
- **The copy count range is 1–99 with a default of 1**, matching the item label path exactly rather
  than inventing a second convention.
- **No change to the printing mechanism, the label stocks, or the label dimensions.** This feature
  changes what the composed label says and how many are requested, not how one is transmitted to the
  printer.
- **No new product fields and no schema change.** Manufacturer and manufacturer part number already
  exist on the product record.
