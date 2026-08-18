# Feature Specification: The Captured Listing Fills In the Manufacturer Part Number

**Feature Branch**: `issues/90`

**Created**: 2026-08-18

**Status**: Draft

**Input**: GitHub issue #90 — "Capture: Manufacturer Part Number is left empty when the listing names one": *From the #80 verification pass, comment items 2 and 10. On `B0CZ72JRHP` and again on `B0FX4PDW6M`, the captured product-information rows include `Model Number` and `Mfr Part Number`, but the Manufacturer Part Number field on the confirmation page comes up blank and has to be typed in by hand. Derive a default for the field from the captured rows, matching on a small list of names, case- and whitespace-insensitive, in priority order — something like `Manufacturer Part Number`, `Mfr Part Number`, `Part Number`, `Model Number`, `Item model number`. First match wins; the row itself stays in the specification list either way. It is a default, not an assertion — the operator must still be able to clear or change it before capturing, and re-capture must not overwrite an edited value.*

## Terminology

- **Capture** — recording a purchase from a vendor listing, either through the bookmarklet (which
  reads the vendor's page and hands the reading to this application) or by pasting the listing's
  address into the capture form. Both paths end at the same confirmation form, and the write
  happens when the operator submits it.
- **Product information row** — one `name` / `value` pair the capture read out of the vendor's
  product-details table. Stored on the product as a **specification row** and shown in the
  product's specification list.
- **Confirmation form** — the capture form the operator lands on with the listing's readings already
  filled in, reviews, amends, and submits. It is where the capture is committed.
- **Part-number-named row** — a product information row whose *name* is one of the recognized
  part-number names listed in FR-001. Being part-number-named says nothing about whether the
  *value* is usable.
- **Derived default** — a value the application puts into a confirmation-form field because the
  listing named it, rather than because the operator typed it. The existing Manufacturer and Unit
  Price fields already work this way; this feature adds a third.
- **Fills the blanks, never overwrites** — the rule the existing derived defaults follow: a value
  the operator supplied wins over one the listing supplied, and a field the operator *cleared*
  counts as supplied.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The part number the listing published is already in the field (Priority: P1)

The operator captures a vendor listing whose product information names the manufacturer's part
number. They land on the confirmation form and the Manufacturer Part Number field already holds it.
They do not retype what the listing just told the application.

**Why this priority**: This is the whole feature. The part number is the second half of the pair
that lets a repeat buy attach to the existing product without asking, so a capture that leaves it
blank costs a decision on every later purchase of the same thing — and it leaves it blank while
displaying the answer two inches further down the page.

**Independent Test**: Capture a listing whose product information carries a `Mfr Part Number` row.
Confirm the Manufacturer Part Number field arrives holding that row's value, submit without touching
it, and confirm the saved product carries it.

**Acceptance Scenarios**:

1. **Given** a listing whose product information includes a row named `Manufacturer Part Number`
   with a non-empty value, **When** the operator reaches the confirmation form, **Then** the
   Manufacturer Part Number field holds that value.
2. **Given** a listing whose product information includes a row named `Mfr Part Number`,
   `Part Number`, `Model Number` or `Item model number` and no higher-priority name, **When** the
   operator reaches the confirmation form, **Then** the Manufacturer Part Number field holds that
   row's value.
3. **Given** a listing carrying both `Model Number` and `Mfr Part Number`, **When** the operator
   reaches the confirmation form, **Then** the field holds the `Mfr Part Number` value, because it
   is higher in the priority order — regardless of which row came first on the vendor's page.
4. **Given** a row name that differs only in letter case or surrounding whitespace from a recognized
   name, **When** the operator reaches the confirmation form, **Then** it matches exactly as the
   canonical spelling would.
5. **Given** any of the above, **When** the operator submits, **Then** every captured row —
   including the one the default came from — is still present in the product's specification list,
   unchanged.
6. **Given** a listing with no part-number-named row, **When** the operator reaches the confirmation
   form, **Then** the field is empty and the capture behaves exactly as it does today.

---

### User Story 2 - The operator overrules the listing (Priority: P1)

The listing's `Model Number` is the marketing model, not the manufacturer's part number, or the
vendor simply has it wrong. The operator types the right one over it, or empties the field because
there isn't one. What they decided is what gets captured.

**Why this priority**: Equal in priority to US1 and inseparable from it. A default that cannot be
overruled is an assertion, and an assertion built out of a name-guessing list will be wrong often
enough to poison the field it was meant to fill — a wrong part number corroborates a repeat buy
against the wrong product, which is worse than an empty one. The feature is only safe to ship with
this half in place.

**Independent Test**: Capture a listing that produces a derived default, replace the value with a
different one, submit, and confirm the product carries the typed value. Repeat, clearing the field
instead, and confirm the product carries no part number.

**Acceptance Scenarios**:

1. **Given** a confirmation form whose Manufacturer Part Number holds a derived default, **When**
   the operator replaces it and submits, **Then** the product carries the operator's value and the
   derived one appears nowhere but the specification row it came from.
2. **Given** the same form, **When** the operator clears the field and submits, **Then** the product
   carries no manufacturer part number — the derived default is not silently restored.
3. **Given** the operator has replaced or cleared the field, **When** the capture comes back with a
   question attached rather than completing, **Then** the field still shows what the operator
   decided, not the derived default a second time.
4. **Given** a submission that carries the listing but no Manufacturer Part Number field at all,
   **When** the capture completes, **Then** the derived default is used — an absent field is not a
   decision, and this is the same distinction the Manufacturer and Unit Price fields already draw.

---

### User Story 3 - A useless candidate is passed over (Priority: P3)

Vendors put empty cells, whitespace and occasionally a paragraph into their product-details tables.
A candidate that cannot be a part number is skipped rather than offered.

**Why this priority**: Rare, and mostly its failure is visible rather than silent — but one of its
forms is neither. A value longer than the manufacturer part number field's storage does **not** stop
the form: the field's length attribute constrains typing, not a value the server rendered into it,
so the over-long value submits, the capture does its work — including retrieving the gallery, which
takes eight to fifteen seconds — and only then does the write fail on the column. The operator gets
an error at the end of a long operation, over a value they never typed.

**Independent Test**: Capture a listing whose highest-priority part-number-named row has an empty
value and whose next one has a real value. Confirm the field holds the second.

**Acceptance Scenarios**:

1. **Given** a part-number-named row whose value is empty or only whitespace, **When** the operator
   reaches the confirmation form, **Then** that row supplies no default and the search continues to
   the next recognized name.
2. **Given** a part-number-named row whose value is longer than the Manufacturer Part Number field
   can store, **When** the operator reaches the confirmation form, **Then** that row supplies no
   default, the search continues to the next recognized name, the capture completes, and the value
   is still present as a specification row.
3. **Given** a value with surrounding whitespace, **When** it becomes the default, **Then** the
   whitespace is not carried into the field.

---

### Edge Cases

- **The capture attaches to an existing product.** Capture does not write the manufacturer or the
  part number onto a product that already exists — a mismatch there is the evidence the
  recycled-identifier question depends on. So the derived default may be filled in, reviewed and
  then not stored. That is correct and unchanged by this feature; the field is still worth filling
  because the operator does not know at that moment which case they are in.
- **Two rows with the same recognized name.** Deduplicated before this feature sees them on the
  bookmarklet path; where a duplicate name does survive, the first one in the captured order wins.
- **A row that names the vendor's part number rather than the manufacturer's.** `Part Number` is
  ambiguous on some listings. It stays on the list because the operator reviews every default; see
  the Assumptions.
- **A listing that publishes only `Item model number`.** Amazon's usual name. It is last in the
  order precisely because it is the loosest match, so any of the other four displaces it.
- **A capture with no product information rows at all** — the pasted-address path, or a listing
  whose details table the reading did not find. Nothing to derive from; the field is empty and
  nothing about the capture changes.
- **A capture that never completes.** Nothing is written, derived default included. The default
  lives on the form, not in the catalog.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST recognize a product information row as part-number-named when its
  name, compared case-insensitively and ignoring surrounding whitespace, is one of, in this priority
  order: `Manufacturer Part Number`, `Mfr Part Number`, `Part Number`, `Model Number`,
  `Item model number`. This MUST use the same name-folding rule the recognized barcode names
  already use; a second folding implementation MUST NOT be introduced.
- **FR-002**: When the operator has not supplied a manufacturer part number, the system MUST offer
  the value of the highest-priority usable part-number-named row as the field's default. Priority is
  by position in the FR-001 list, not by the row's position on the vendor's page. Where two rows
  share the same recognized name, the first in captured order wins.
- **FR-003**: A part-number-named row MUST be treated as usable only when its value, with
  surrounding whitespace removed, is non-empty and no longer than the manufacturer part number can
  be stored. An unusable row MUST be passed over and the search MUST continue down the FR-001 list.
  The system MUST NOT offer a default it cannot store, and MUST NOT truncate one to fit.
- **FR-004**: The system MUST store the derived default with surrounding whitespace removed, and
  MUST NOT otherwise alter the row's value.
- **FR-005**: A manufacturer part number the operator supplied MUST win over the derived default. An
  **empty** submitted field counts as supplied — the operator cleared it — and MUST NOT be replaced
  by the derived default. An **absent** field does not, and MUST fall back to the derived default.
  This is the same absent-versus-empty rule the Manufacturer and Unit Price fields already follow.
- **FR-006**: When a capture returns to the confirmation form with a question or a refusal rather
  than completing, the field MUST redisplay what the operator last submitted — including an empty
  field they cleared — and MUST NOT re-apply the derived default over it.
- **FR-007**: The derived default MUST apply to both capture paths by a single shared rule, so that
  any capture carrying product information rows gets it regardless of how the rows arrived.
- **FR-008**: The system MUST leave every part-number-named row's ordinary handling untouched: no
  row is filtered, hidden, moved or removed from the specification list on account of its name or
  its use as a default.
- **FR-009**: Deriving the default MUST NOT add any external request to a capture, MUST NOT fail a
  capture, and MUST NOT change what is written when no part-number-named row is present.
- **FR-010**: The derived default MUST apply to the capture confirmation form only. A part-number-
  named row typed into the ordinary product create or edit form MUST NOT populate that form's
  Manufacturer Part Number field.

### Key Entities

- **Product information row (specification row)**: a `name` / `value` pair read off a vendor listing
  and stored on the product. Its handling is unchanged by this feature; it is the input to the
  default, not the thing the default modifies.
- **Manufacturer part number**: a field on the product, filled by the operator on the confirmation
  form. This feature changes only what the field arrives holding — not where it is stored, not what
  it means, and not the rule that capture never writes it onto an already-existing product.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Capturing `B0CZ72JRHP` and `B0FX4PDW6M` — the two listings that prompted the issue —
  produces a confirmation form whose Manufacturer Part Number field is already filled from the
  listing's own rows, with zero keystrokes typed into it.
- **SC-002**: For a listing carrying a part-number-named row, the number of confirmation-form fields
  the operator must fill by hand to record a manufacturer part number drops from one to zero.
- **SC-003**: A capture whose Manufacturer Part Number the operator cleared stores no part number,
  on the first submission and after a capture question, in 100% of cases.
- **SC-004**: A capture whose Manufacturer Part Number the operator typed over stores the typed
  value, not the derived one, in 100% of cases.
- **SC-005**: Every captured row remains visible in the product's specification list after capture,
  including the row a default was derived from, in all of the above cases.
- **SC-006**: A capture carrying no part-number-named row completes exactly as it does today, with
  no change to what is stored.
- **SC-007**: Deriving the default adds no measurable time to a capture — no listing is read twice
  and no request is made.

## Assumptions

- **The recognized-name list is exactly the five names in the issue, in the issue's order.** No
  other name is treated as a part number, however part-number-shaped its value. Adding a name later
  is a one-line change and does not need to be anticipated now.
- **The order encodes confidence, and the list is deliberately loose at the bottom.** `Manufacturer
  Part Number` and `Mfr Part Number` say what they are. `Part Number` may be the vendor's rather
  than the manufacturer's, and `Model Number` / `Item model number` may be a marketing model that is
  not orderable as a part. They are on the list because a default the operator reviews and can
  overrule is worth more than an empty field, and off the top of the list because when a listing
  publishes both, the specific one is right.
- **This is a default, never an assertion.** Nothing downstream may treat a manufacturer part number
  as more trustworthy for having been derived, and nothing may re-apply it after the operator has
  had the field in front of them.
- **Nothing is reported about the derivation.** The field simply arrives filled, exactly as the
  Manufacturer field already does from the listing's byline. A note saying where the value came from
  is deliberately not part of this feature: the row it came from is visible on the same page, and
  the capture's existing reporting is reserved for what the capture *did to the catalog*, which this
  does not.
- **The pasted-address path carries no product information rows today, so nothing changes for it.**
  Pasting a listing's address does not read the vendor's page; only the bookmarklet does. FR-007 is
  written as "a single shared rule" rather than "both paths behave the same" because the shared rule
  is what makes the benefit automatic if that ever changes — the issue's stated preference for
  putting the rule on the rendering side rather than in the page-reading agent. Its immediate,
  testable value is that the rule can be exercised without a browser.
- **The existing capture merge, specification handling and part-number storage are reused as they
  are.** This feature adds no storage, no validation and no new field.
- **Nothing is retrofitted.** Products captured before this change do not gain a part number on
  their own. Fixing one means editing it, or re-capturing and accepting the default — and
  re-capturing onto an existing product will not write it, so editing is the remedy.
- **The Manufacturer and Unit Price fields are not in scope.** FR-006 asks for redisplay behavior
  that those two fields do not have today. Bringing them into line is a separate change against a
  separate issue; this feature must not silently alter them.
