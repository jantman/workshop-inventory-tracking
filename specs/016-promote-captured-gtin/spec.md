# Feature Specification: A Captured Barcode Becomes a Scannable Identifier

**Feature Branch**: `016-promote-captured-gtin`

**Created**: 2026-08-17

**Status**: Draft

**Input**: GitHub issue #93 — "A captured UPC row is stored as a specification, never as an identifier": *From the #80 verification pass, comment item 7. `B01N4OSKWE` carries a `UPC` row in its product information. It was stored as an ordinary specification. No identifier was created, so scanning that product's barcode off the box will not find it. Decided (owner's call, 2026-08-16): promote it, with check-digit validation. On capture, a product-information row whose name folds (case- and whitespace-insensitive) to one of `UPC`, `EAN`, `GTIN`, `ISBN`, `GTIN-13`, `UPC-A` and whose value is a plausible GTIN becomes a `GTIN` identifier on the product. Reuse #82's check-digit validation rather than writing a second one. A value that fails its check digit is not promoted and stays a specification row — no override, because nobody typed it and an unattended override is how a wrong identifier becomes permanent. The row itself stays in the specification list either way; nothing is filtered by name. A collision doesn't guess: if the value already exists as an identifier on a different product, leave it as a specification and say so on the confirmation page. Re-capturing the same product onto its own existing identifier is a no-op, not a duplicate.*

## Terminology

- **Capture** — recording a purchase from a vendor listing, either through the bookmarklet (which
  reads the vendor's page and hands the reading to this application) or by pasting the listing's
  address into the capture form. Both paths end at the same confirmation form, and the write happens
  when the operator submits it.
- **Product information row** — one `name` / `value` pair the capture read out of the vendor's
  product-details table. Stored on the product as a **specification row** and shown in the product's
  specification list.
- **Identifier** — a coded name attached to a product that a scan or a typed code can resolve to it.
  Identifiers have kinds; the kind at issue here is the retail barcode, **GTIN**.
- **Barcode-named row** — a product information row whose *name* is one of the recognized barcode
  names listed in FR-001. Being barcode-named says nothing about whether the *value* is usable.
- **Promotion** — creating a GTIN identifier on the product from a barcode-named row's value. The
  specification row is not consumed by this; promotion adds, it does not move.
- **Added row** — a captured row that the capture actually appended to the product's specification
  list. A captured row whose *name* the product already carries is dropped whole by the existing
  merge rule ("the operator's row wins") and is therefore **not** an added row. Promotion acts on
  added rows only; see FR-003 and the Assumptions.
- **Confirmation page** — the page the operator lands on after submitting a capture, where the
  application already reports what the capture did (for example, how many listing images it stored).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A captured barcode is scannable off the box (Priority: P1)

The operator captures a vendor listing that publishes the product's UPC. Later the box arrives, they
scan the barcode printed on it, and they land on that product — without anyone having typed the
barcode in.

**Why this priority**: This is the whole feature. The machinery that resolves a scanned barcode to a
product already exists; what is missing is that a capture which was *handed* the barcode for free
throws it away. Every capture between now and this change produces a product that is unfindable by
its own barcode.

**Independent Test**: Capture a listing whose product information carries a valid UPC. Confirm the
product now holds a GTIN identifier, then find the product by scanning or typing that barcode.

**Acceptance Scenarios**:

1. **Given** a vendor listing whose product information includes a row named `UPC` with a valid
   barcode value, **When** the operator confirms the capture, **Then** the resulting product carries
   a GTIN identifier for that barcode.
2. **Given** a product that gained a GTIN identifier through capture, **When** that barcode is
   scanned or typed into the find-by-code path, **Then** the operator lands on that product.
3. **Given** the same listing captured a second time onto the same product, **When** the operator
   confirms the capture, **Then** the product still carries exactly one GTIN identifier for that
   barcode, no error is shown, and the barcode is reported as recorded (FR-009a).
4. **Given** a product that already carries a specification row named `UPC` whose value is not on
   any product as an identifier, **When** a capture supplies its own `UPC` row, **Then** the captured
   row is dropped as it is today, no identifier is created, and the confirmation page says the row
   was not examined (FR-010).
5. **Given** a listing whose product information includes a row named `EAN`, `GTIN`, `ISBN`,
   `GTIN-13` or `UPC-A` with a valid barcode value, **When** the operator confirms the capture,
   **Then** the row is promoted exactly as a `UPC` row would be.
6. **Given** a listing with no barcode-named row, **When** the operator confirms the capture,
   **Then** the capture behaves exactly as it does today and no identifier is added.

---

### User Story 2 - A wrong barcode is never recorded unattended (Priority: P2)

A vendor's product-details table is typed by a human and scraped by a selector; either can be wrong.
When the value in a barcode-named row is not a valid barcode, the capture records nothing rather
than recording something wrong.

**Why this priority**: A wrong identifier is worse than a missing one. A missing identifier is
visibly missing and one scan fixes it; a wrong identifier silently claims a barcode, resolves a
future scan to the wrong product, and nothing in the interface reveals it. Nobody is watching a
capture closely enough to catch it, so the refusal has to be automatic.

**Independent Test**: Capture a listing whose `UPC` row has one digit altered so the check digit no
longer agrees. Confirm no identifier was created and the specification row is present.

**Acceptance Scenarios**:

1. **Given** a barcode-named row whose value has a bad check digit, **When** the operator confirms
   the capture, **Then** no identifier is created and the value appears only as a specification row.
2. **Given** a barcode-named row whose value is not a plausible barcode at all — wrong length, not
   all digits, or all zeros — **When** the operator confirms the capture, **Then** no identifier is
   created and the value appears only as a specification row.
3. **Given** any refused value, **When** the capture completes, **Then** the refusal is never
   overridable from the capture flow: there is no prompt and no setting that stores it anyway.
4. **Given** a barcode-named row that was refused, **When** the capture completes, **Then** the rest
   of the capture — the purchase, the other specification rows, the description and the images — is
   unaffected.

---

### User Story 3 - A barcode another product already holds is left alone (Priority: P3)

Two listings can publish the same barcode, and a vendor can publish the wrong one. When the value
already names a *different* product, the capture does not move it, does not duplicate it, and does
not guess which product is right — it leaves the value as a specification row and tells the
operator.

**Why this priority**: Rarer than the first two, but the failure mode is the one the operator cannot
recover from without knowing it happened. It matters most that it is *reported*; the non-action is
the easy half.

**Independent Test**: Give an existing product a GTIN identifier, then capture a different listing
carrying the same barcode. Confirm the barcode still belongs to the first product, the second
product has no GTIN identifier, and the confirmation page says so.

**Acceptance Scenarios**:

1. **Given** a barcode already held as an identifier by another product, **When** the operator
   confirms a capture carrying that barcode, **Then** no identifier is created on the captured
   product and the first product keeps the barcode unchanged.
2. **Given** that collision, **When** the capture completes, **Then** the confirmation page states
   that the barcode was not recorded and identifies the product that already holds it.
3. **Given** that collision, **When** the operator looks at the captured product, **Then** the
   barcode is present as an ordinary specification row, exactly as it would have been before this
   feature existed.

---

### Edge Cases

- **A row the merge dropped.** A captured row whose *name* the product already carries is dropped
  whole today — the operator's row wins — and a dropped row is not promoted (FR-003). So a product
  that already has a `UPC` specification row does **not** gain the identifier by being re-captured.
  This is a deliberate choice (owner's call, 2026-08-17): what is in the specification list is what
  was promoted, and no identifier can contradict a row the operator can see. Its cost is stated in
  the Assumptions — products captured before this change are fixed by hand, not by re-capture.
- **A row with an empty value.** Nothing to promote; treated as a value that is not a plausible
  barcode.
- **Two barcode-named rows naming the same trade item.** A listing carrying both `UPC` (12 digits)
  and `EAN` (the same code with a leading zero) resolves to one identifier, not two, because
  equivalent barcode forms normalize to the same stored value.
- **Two barcode-named rows with genuinely different valid barcodes.** Each is evaluated on its own;
  both are promoted.
- **A row that holds more than one barcode.** Some vendors put several space-separated codes in a
  single `UPC` row. That value is not a plausible barcode and is not promoted (see Assumptions).
- **An ISBN-10.** Ten digits, sometimes ending in `X`, and checked with a different arithmetic than
  a barcode. It is not a plausible GTIN and is not promoted, even though `ISBN` is a recognized
  name. An ISBN-13 is a valid GTIN and promotes normally.
- **The capture attaches to an existing product.** Promotion applies to whichever product the
  capture finally resolved to, after the duplicate-purchase and recycled-identifier questions have
  been answered — never to a product the operator declined to attach to.
- **The capture never completes.** A capture that stops to ask the operator a question writes
  nothing at all, promotion included.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST recognize a product information row as barcode-named when its name,
  compared case-insensitively and ignoring surrounding whitespace, is one of: `UPC`, `EAN`, `GTIN`,
  `ISBN`, `GTIN-13`, `UPC-A`.
- **FR-002**: The system MUST accept a barcode-named row's value as promotable only when it passes
  the *same* barcode validation the application already applies to a hand-entered barcode
  identifier — the same accepted lengths, the same check-digit arithmetic, the same refusal of an
  all-zero no-read — and MUST store it in the same normalized form. A second validation
  implementation MUST NOT be introduced.
- **FR-003**: On a capture that completes, the system MUST create a GTIN identifier on the resolved
  product for each promotable barcode-named row **that the capture added to the product's
  specification list**. A captured row the merge dropped — because the product already carries a row
  of that name — MUST NOT be promoted.
- **FR-004**: The system MUST NOT store a value that fails validation, and MUST NOT offer any
  override, prompt or setting that stores it anyway.
- **FR-005**: The system MUST leave every barcode-named row's ordinary handling untouched, whatever
  the promotion outcome: no row is filtered, hidden, moved or removed from the specification list on
  account of its name or its promotion.
- **FR-006**: When a promotable value is already held as an identifier by a *different* product, the
  system MUST create nothing, MUST leave the other product's identifier unchanged, and MUST report
  the fact to the operator.
- **FR-007**: When a promotable value is already held by the product the capture resolved to, the
  system MUST treat it as a no-op: no duplicate row, no error, and nothing reported as a problem.
- **FR-008**: The system MUST evaluate promotion against the product the capture finally resolved
  to, after the duplicate-purchase and recycled-identifier decisions are settled, and MUST write
  nothing when the capture does not complete.
- **FR-009**: The system MUST report the outcome to the operator on the confirmation page, in the
  same place and manner the capture already reports what it did. For every barcode-named row the
  listing carried, the report MUST say which of exactly four things is true of it: the barcode is
  recorded on this product; it was not recorded because the value is not a valid barcode; it was not
  recorded because another product already holds it, and which; or the row was not examined. Two
  rows whose values are equivalent barcode forms MUST produce one line, not two. A capture with no
  barcode-named row MUST report nothing on this subject.
- **FR-009a**: The report states **what is true of the barcode after the capture**, not what this
  particular capture did. So a listing captured a second time reports its barcode as recorded, the
  same as the first time, rather than falling silent — the statement is true either way, and
  distinguishing the two would cost a change out of all proportion to the sentence. See
  [research.md](./research.md) §3, which is where this was decided and priced.
- **FR-010**: A barcode-named row that was dropped by the merge (FR-003) MUST be reported as not
  examined, naming the row. This is what keeps the chosen rule from being silent exactly where it
  surprises: a capture that looks like it should have produced an identifier and did not. A dropped
  row whose value the product already holds as an identifier falls under "recorded" by FR-009a, and
  needs no separate treatment.
- **FR-011**: A refused or collided promotion MUST NOT fail the capture: the purchase, the
  specification rows, the description and the images all land regardless.
- **FR-012**: The system MUST evaluate each barcode-named row independently, so one unusable value
  costs only itself.
- **FR-013**: A capture carrying no barcode-named row MUST behave exactly as it does today.

### Key Entities

- **Product information row (specification row)**: a `name` / `value` pair read off a vendor
  listing and stored on the product. Its handling is unchanged by this feature; it is the input to
  promotion, not the thing promotion modifies.
- **GTIN identifier**: a retail barcode attached to a product, stored in a single normalized form so
  that equivalent barcode forms are one value. This is what promotion creates, and what the
  find-by-code path already resolves.
- **Product**: gains at most a new identifier. Nothing else about it changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Capturing `B01N4OSKWE` **onto a product that does not already list a `UPC` row**
  produces a product carrying a GTIN identifier for the UPC published on that listing, with zero
  manual identifier entry, and scanning or typing that barcode through the find-by-code path lands
  on that product. (The existing `B01N4OSKWE` product in the live catalog already carries that row,
  so verifying against it means removing the row first — see the Assumptions.)
- **SC-002**: A capture of the same listing with one digit of the UPC altered produces zero
  identifiers, and the altered value is present as a specification row.
- **SC-003**: Capturing the same listing twice yields exactly one GTIN identifier on the product and
  no error on the second capture. Both captures report the barcode as recorded (FR-009a).
- **SC-004**: When the barcode already belongs to another product, both products end the capture
  with the identifiers they started with, and the operator is told on the confirmation page without
  having to look anywhere else.
- **SC-005**: Every barcode-named row's value is still visible in the product's specification list
  after capture, in all of the above cases.
- **SC-006**: Promotion adds no external request to a capture, so capture time is unchanged.

## Assumptions

- **The recognized-name list is exactly the six names in the issue.** No other name is treated as a
  barcode, however barcode-shaped its value. Adding names later is a one-line change and does not
  need to be anticipated now.
- **A promotable value is a single barcode and nothing else.** Whitespace around it is trimmed;
  anything further — separators inside the digits, a label prefix, or several codes in one value —
  makes the value not a plausible barcode, and it is not promoted. Splitting a multi-value row is
  guesswork of exactly the kind this feature refuses to do unattended; the operator can still add
  the identifier by hand.
- **`ISBN` earns its place in the list only through ISBN-13**, which is a valid GTIN. ISBN-10 will
  simply never validate, which is the correct outcome and needs no special handling.
- **The existing barcode validation and the existing find-by-code resolution are reused as they
  are.** This feature adds no validation, no normalization and no lookup of its own. It depends on
  the identifier machinery built for issue #82 already being in place, which it is.
- **This applies to the capture path only.** Barcode-named rows typed into the product edit form by
  hand are not promoted; the operator typing a row is already in front of the identifier controls.
- **Nothing is retrofitted, and re-capture is not the remedy.** Products captured before this
  change do not gain identifiers on their own, and because a captured row whose name the product
  already carries is dropped before promotion can see it (FR-003), re-capturing such a product does
  not fix it either. Fixing an already-captured product means either adding the identifier by hand
  from its detail page, or deleting the existing barcode-named specification row and re-capturing.
  The confirmation page says which case the operator is in (FR-010). **This applies to
  `B01N4OSKWE`, the product that prompted the issue** — it already carries a `UPC` specification
  row, so the issue's stated verification ("capture `B01N4OSKWE`, confirm a `GTIN` identifier
  exists") must be run against a product without that row, or after removing it. A one-off sweep
  that promotes barcode-named rows on existing products is deliberately out of scope; there is one
  operator and a small catalog, and a sweep is a second, unattended write path over data nobody is
  looking at.
