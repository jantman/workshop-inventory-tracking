# Feature Specification: Capture Reads the "About this item" Bullets

**Feature Branch**: `issues/92`

**Created**: 2026-08-19

**Status**: Draft

**Input**: GitHub issue #92 — "Capture never reads the \"About this item\" bullets": *From the #80 verification pass, comment items 7 and 10. On `B01N4OSKWE`, all of the relevant information — dimensions and specifications — lives in the listing's About this item section, and none of it was captured. Same on `B0FX4PDW6M`: "important information in About this item was not captured". For a listing like `B01N4OSKWE` this is the difference between a useful catalog record and an empty one. The bullets are prose, not name/value pairs, so the existing row reader's two shapes do not fit. Capture them as one specification row named `About this item` whose value is the bullets, one per line; it must fold under the existing first-occurrence-wins merge rather than duplicating on re-capture. Watch the shape: the bullet list includes a hidden "See more product details" item on some listings.*

## Terminology

- **Capture** — recording a purchase from a vendor listing by way of the bookmarklet, which reads
  the listing's page and hands the reading to this application. The reading arrives at the
  confirmation form and the write happens when the operator submits it.
- **Bullet list** — the listing's own **About this item** section: a short list of prose bullets the
  vendor writes about the product, displayed near the top of the page, above the product-details
  tables. It is what the shopper actually reads.
- **Bullet** — one item of that list, as shown to the shopper. Prose, not a name/value pair.
- **Specification row** — one `name` / `value` pair stored on the product and shown in the product's
  specification list. Product information read out of the listing's detail tables is stored this
  way; this feature adds one more row of the same kind.
- **The bullets row** — the single specification row this feature produces, named `About this item`,
  whose value is the listing's bullets one per line.
- **First-occurrence-wins merge** — the existing rule that decides what a capture adds. It runs in
  two independent places and both apply here: the reading folds the listing's own containers against
  each other, and the write folds the captured names against the rows the product already carries,
  dropping a captured name the product already has. Together they are what makes re-capture
  idempotent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The listing's own description of the product survives the capture (Priority: P1)

The operator captures a listing whose real content — dimensions, capacities, materials, what fits
what — is written in the About this item bullets rather than in a product-details table. The saved
product carries that content, readable, as part of its specifications.

**Why this priority**: This is the whole feature, and on some listings it is the difference between
a catalog record and an empty shell. `B01N4OSKWE` publishes *all* of its dimensions and
specifications in the bullets and nothing in a detail table; today's capture reads the tables, finds
them empty, and stores a product that says nothing about the thing that was bought. The bullets are
also the one part of a listing written in plain language, so they are what makes a record legible a
year later when the listing is gone.

**Independent Test**: Capture a listing whose About this item section carries content that appears
nowhere in its product-details tables. Confirm the saved product has a specification row named
`About this item` whose value holds every bullet the shopper sees, and that the previously-captured
fields are unchanged.

**Acceptance Scenarios**:

1. **Given** a listing with a non-empty About this item section, **When** the operator completes a
   capture, **Then** the saved product carries a specification row named `About this item`.
2. **Given** that row, **When** the operator looks at it, **Then** its value contains the text of
   every bullet the listing shows, in the order the listing shows them.
3. **Given** that row, **When** the operator looks at it, **Then** each bullet occupies its own line
   — no two bullets run together into one line, and no single bullet is split across lines it did
   not have.
4. **Given** a listing whose dimensions appear only in the bullets, **When** the capture completes,
   **Then** those dimensions are present in the product's specification list.
5. **Given** the same capture, **When** it completes, **Then** the product's description, price,
   brand, gallery images and product-information rows are exactly what they would have been before
   this feature — the bullets row is added to the reading, not substituted for any of it.

---

### User Story 2 - Re-capturing does not accumulate copies (Priority: P1)

The operator captures the same listing a second time — a repeat purchase, or a first attempt that
was interrupted. The product ends up with one `About this item` row, not two.

**Why this priority**: Inseparable from US1. The bullets row is large, and a duplicate of it is the
most visible kind of clutter a product's specification list can acquire. The rule already exists for
every other captured row; this one has to fold under it rather than around it, and the only way to
know it does is to state it and test it.

**Independent Test**: Capture a listing, then capture the same listing again onto the same product.
Confirm exactly one `About this item` row exists and that its value is the one from the first
capture.

**Acceptance Scenarios**:

1. **Given** a product that already carries an `About this item` row, **When** a capture of the same
   listing completes, **Then** the product still carries exactly one such row.
2. **Given** that second capture, **When** it completes, **Then** the existing row's value is
   unchanged — including a value the operator had edited by hand, which is not overwritten.
3. **Given** a listing that publishes a product-details row of its own named `About this item` as
   well as a bullet list, **When** the capture completes, **Then** the product carries exactly one
   row of that name.
4. **Given** a product whose `About this item` row the operator deleted, **When** a later capture of
   the same listing completes, **Then** the row is added back — deletion is not remembered, exactly
   as it is not for any other captured row.

---

### User Story 3 - What the shopper cannot see is not captured (Priority: P2)

Some listings hang extra items off the bullet list that the page never displays — a "See more
product details" link, fitment placeholders, decorative fragments. None of them reach the catalog.

**Why this priority**: Lower than the first two because its failure is visible rather than silent —
a stray line in the row is obvious and one edit removes it. It is still a requirement: the value of
the bullets row is that it reads like the listing, and a navigational fragment quoted as though it
were a product fact undermines exactly that. It also guards a real trap in the source markup, which
is why it is called out rather than assumed.

**Independent Test**: Capture a listing whose bullet list carries a hidden item alongside the
displayed ones. Confirm the row's value holds the displayed bullets and not the hidden one.

**Acceptance Scenarios**:

1. **Given** a bullet list containing an item the listing hides from the shopper, **When** the
   capture completes, **Then** that item's text does not appear in the bullets row.
2. **Given** a bullet whose visible text is empty — decoration, an image with no caption,
   whitespace only — **When** the capture completes, **Then** it contributes no line, and no blank
   line, to the row's value.
3. **Given** a bullet list in which every item is hidden or empty, **When** the capture completes,
   **Then** no `About this item` row is created at all.

---

### User Story 4 - A listing with no bullets captures exactly as it does today (Priority: P2)

Many listings have no About this item section. Those captures behave the way they always have.

**Why this priority**: The safety half. Capture reads a page that is not a contract, and the
governing rule for every reading step is that a step which stops working costs its own field and
nothing else. A new reader that could fail the whole capture would be a worse trade than the
information it recovers.

**Independent Test**: Capture a listing with no About this item section. Confirm no `About this
item` row is created, no empty row is created, and every other captured field is what it was before
this feature.

**Acceptance Scenarios**:

1. **Given** a listing with no About this item section, **When** the capture completes, **Then** no
   `About this item` row exists and the capture is otherwise unchanged.
2. **Given** a listing whose About this item section is present but holds no readable text, **When**
   the capture completes, **Then** no `About this item` row is created — an empty row is never
   offered. (It would not fail the capture: `_payload_specifications` drops a nameless or valueless
   entry before validation ever sees it. It would fail *silently*, which is why the row must not be
   emitted rather than merely tolerated. See `research.md` §4.)
3. **Given** a listing whose markup has changed such that the bullet list cannot be found at all,
   **When** the capture completes, **Then** every other field is captured normally and the capture
   reports no error.

---

### Edge Cases

- **A hidden trailing item.** The bullet list on some listings ends with an item the page does not
  display, such as "See more product details". It must not become a line. (US3)
- **A bullet list that is absent, empty, or entirely hidden.** No row, no empty row, no error. (US4)
- **Nested structure inside a bullet.** A bullet containing its own sub-list or several block
  elements is still one bullet; its internal line structure is preserved but it does not become
  several bullets, and it does not collapse into the bullet after it.
- **A bullet that reads like a name/value pair** — "Material: Stainless Steel". It is captured as a
  line of the bullets row exactly as written. This feature does not attempt to split bullets into
  rows; a bullet is prose that sometimes contains a colon.
- **Bullets that repeat the description.** Some listings say the same thing twice. Both are captured;
  no de-duplication is attempted between the description and the bullets row.
- **A very long bullet list.** Some listings run to a dozen long bullets. The value is stored whole;
  nothing is truncated. (Specification values already carry A+ descriptions many times this size.)
- **A single bullet.** One line, one row — not a special case, and not a reason to skip the row.
- **A product-details table that also publishes an `About this item` row.** One row of that name
  survives, by the merge rule that already governs every captured name. (US2)
- **A bullet carrying non-prose content** — a stylesheet, a script — must not be reported as text,
  the same as everywhere else the capture reads prose.
- **Editing the row afterwards.** The value has newlines in it; the product's edit form must let the
  operator change it without silently flattening those lines, and the product page must display them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The capture MUST read the listing's About this item bullet list and report it as one
  specification row.
- **FR-002**: That row's name MUST be `About this item`.
- **FR-003**: That row's value MUST hold the text of each displayed bullet, one bullet per line, in
  the order the listing displays them.
- **FR-004**: A bullet's own internal line structure MUST be preserved within its lines, by the same
  rules that already govern captured prose; and consecutive bullets MUST NOT run together into a
  single line.
- **FR-005**: A bullet the listing does not display to the shopper MUST NOT contribute a line.
- **FR-006**: A bullet whose readable text is empty MUST NOT contribute a line, and MUST NOT
  contribute a blank line.
- **FR-007**: Content that was never prose — stylesheets, scripts and their kin — MUST NOT appear in
  the row's value, consistent with how the capture reads every other block of text.
- **FR-008**: If the bullet list is absent, or yields no readable bullet, the capture MUST report no
  row at all rather than a row with an empty value.
- **FR-009**: The bullets row MUST fold under the existing first-occurrence-wins merge in both of the
  places that merge runs, so that: a name collision within one reading keeps the first occurrence,
  and a capture landing on a product that already carries an `About this item` row adds nothing and
  changes nothing.
- **FR-010**: The bullets row MUST occupy a defined, stable position in the reported rows, so two
  captures of the same listing report the rows in the same order.
- **FR-011**: Reading the bullets MUST NOT be able to fail the capture. If the bullet list cannot be
  found or cannot be read, the capture MUST lose that row alone and complete normally, reporting no
  error.
- **FR-012**: Adding the bullets row MUST NOT change any other captured field — description, price,
  brand, title, gallery, identifiers or the product-information rows — for any listing.
- **FR-013**: Wherever a specification value is displayed, the bullets row MUST render with each
  bullet on its own line; and wherever it is edited, the operator MUST be able to change it without
  the line structure being lost.
- **FR-014**: The end-to-end test fixtures MUST include an About this item section whose markup is
  taken from a real listing, including the hidden-item shape FR-005 guards against, so the reader is
  exercised against the thing it has to survive rather than against an idealization of it.

### Key Entities

- **Bullets row**: one specification row on a product. Name `About this item`, value the listing's
  bullets one per line. Stored, merged, displayed, edited and deleted exactly like every other
  specification row — this feature adds a source for a row, not a new kind of row.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Re-capturing `B01N4OSKWE` produces a catalog record that states the product's
  dimensions and specifications, where today's record states none of them.
- **SC-002**: Re-capturing `B0FX4PDW6M` produces a record whose About this item content is present
  and readable.
- **SC-003**: For any listing with an About this item section, 100% of the bullets a shopper sees are
  present in the saved record, each on its own line, and no line is present that the shopper did not
  see.
- **SC-004**: Capturing the same listing twice onto the same product leaves exactly one
  `About this item` row, with the value from the first capture.
- **SC-005**: For listings with no About this item section, every captured field is byte-for-byte
  what it was before this feature, and no new row appears.
- **SC-006**: A listing whose bullet-list markup has changed beyond recognition still captures every
  other field and reports no error.

## Assumptions

- **The bullets become a specification row, not an appendix to the description.** Issue #92 offers
  both and favors this one; it is adopted. A named row stays addressable — findable by name,
  editable and deletable on its own — where text appended to the description is neither, and the
  description on an A+ listing is already long enough that burying the bullets in it would hide
  them. This is the decision most worth revisiting if the row proves awkward in use.
- **`About this item` is the row name**, matching the heading the listing itself uses. It is short
  enough to be well within the specification-name limit.
- **Line-structured specification values already work.** Issue #91 landed the prose reader that
  preserves line breaks and the display that renders them, so "one bullet per line" is a use of
  existing behavior rather than a new capability. FR-013 is a statement of what must remain true,
  not new display work — though the edit form's handling of a multi-line value is worth confirming
  rather than assuming.
- **No filtering by content.** As with the product-information rows, nothing is dropped for being
  marketing copy, boilerplate or a repeat of the description. An unwanted row is one click to
  delete; a physical fact lost to a filter rule is unrecoverable once the listing is gone.
- **Bullets are not parsed into fields.** No attempt is made to extract dimensions, part numbers or
  anything else out of the bullet text into their own rows or form fields. That is a separate
  question and a much harder one.
- **The vendor is Amazon.** The capture reads Amazon listings; "About this item" is Amazon's own
  heading for this section. No other vendor is in scope.
- **The current markup needs confirming against real listings.** The bullet-list shape and the
  hidden-item problem come from earlier probing, not from `B01N4OSKWE` and `B0FX4PDW6M` as they
  stand today. Confirming it against the live listings — driving the owner's browser, as issues #94
  and #95 are being handled — is expected during implementation, and what is found belongs back in
  the hand-written fixture as real markup (FR-014).
- **Verification is a re-capture of the two named listings**, per the issue: `B01N4OSKWE` and
  `B0FX4PDW6M`, with `B01N4OSKWE`'s dimensions as the specific thing to look for.
