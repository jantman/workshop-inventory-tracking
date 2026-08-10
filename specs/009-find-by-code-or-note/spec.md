# Feature Specification: Find By Any Code Or Note

**Feature Branch**: `issues/62`

**Created**: 2026-08-09

**Status**: Draft

**Input**: GitHub issue #62 — "10. Find things by any code on them and anything written about them", and the "Finding things" section of `docs/product-functionality-gap.md`.

## Overview

Identifying the thing in your hand is supposed to take one scan, or failing that one search. The catalogue mostly delivers that: it recognizes the codes this shop prints, the 2D labels DigiKey and Mouser stick on a bag, and a plain retail barcode, and a scan that matches nothing lands in a search rather than dead-ending. Three holes are left, and each one ends the same way — the operator falls back to hunting through the catalogue by hand, which is the exact outcome the feature exists to prevent.

**A manufacturer's own 2D barcode doesn't resolve.** When a manufacturer puts a retail barcode on a box inside a 2D symbol, the standard way to do it is a structured element string that names the number before carrying it. The catalogue reads the bare number and the distributor's envelope, but not that structured form, so the most common manufacturer-printed 2D code on a box degrades to a plain text search — for digits that appear nowhere in the catalogue's text, so the search finds nothing. The number inside is one the catalogue very often already holds. This finding is already paid for: the archived `archive/bmad-product-catalog` branch hit it during its own build and amended its specification for it.

**Notes aren't searched.** Descriptions, specifications, part numbers and every recorded identifier are searched. The notes field — the one place the operator writes free prose about a product, which is exactly where "the ones with the green heads", "left over from the lathe stand" and "these are the metric ones" end up — is invisible to search. A field the operator is invited to write in and can never search is worse than no field, because they believe they recorded something findable.

**The printed code isn't an address.** Every product carries a permanent code that gets printed on its label. The product's address in the application is an internal record number instead, so the code on the label and the way to reach the product are two separate facts to keep in step. Making the printed code resolve as an address collapses them into one, without disturbing the record numbers that already work.

The three share a subject and nothing else — this is one issue's worth of scope, not one mechanism. Each is independently useful and independently testable.

This is deliberately **not** a general structured-barcode parser. One structured form is recognized, for the one field it carries, because that is the form observed on real boxes. Extracting lot codes, expiry dates and serial numbers from the same symbol is a different feature with a different justification.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A manufacturer's 2D barcode finds the product (Priority: P1)

The operator picks up a box of connectors. The manufacturer's own 2D code is on it. They scan it at the catalogue's scan box and land on the product page for the connectors they already have on the shelf — the same page the retail barcode printed on the same box would have reached.

**Why this priority**: It is the only one of the three where the operator does the right thing, gets a wrong-looking answer, and has no way to tell why. The scan lands on an empty search for a string of digits, which reads as "you don't have this" — and they may then create a duplicate product for something already in the catalogue. That is the failure mode that costs the most to undo.

**Independent Test**: Seed a product carrying a known retail barcode, scan the structured form of that same barcode, and verify the scan lands on that product's page rather than on a search.

**Acceptance Scenarios**:

1. **Given** a product recorded with a retail barcode, **When** the operator scans the structured form of that barcode from the manufacturer's 2D symbol, **Then** the catalogue opens that product, identically to scanning the bare retail barcode.
2. **Given** no product carries that retail barcode, **When** the operator scans its structured form, **Then** the catalogue offers to create a product with the barcode already attached — the same offer a bare unrecognized retail barcode produces.
3. **Given** the manufacturer's symbol carries the trade item number followed by further structured fields, **When** it is scanned, **Then** it resolves on the trade item number and the trailing fields are ignored rather than turning the scan into a text search.
4. **Given** the scanner is configured to announce the symbol type before the data, **When** the code is scanned, **Then** it resolves exactly as it would without that announcement.
5. **Given** a structured form whose trade item number fails the check every retail barcode is held to, or that reads as the scanner's no-read value, **When** it is scanned, **Then** it falls through to a text search carrying the raw scan — the same treatment a bad bare barcode gets, and never a silent match on a wrong product.
6. **Given** a scan of any kind the catalogue already recognizes — this shop's own printed code, a distributor's 2D label, a bare retail barcode, a vendor item id, or plain text — **When** it is scanned after this change, **Then** it resolves exactly as it did before.
7. **Given** text that merely resembles the structured form but is not one — the right opening followed by the wrong number of digits, or followed by prose, **When** it is scanned, **Then** it is treated as plain text, not as a barcode.

---

### User Story 2 - What you wrote in the notes is findable (Priority: P2)

The operator remembers writing "left over from the lathe stand" against something, months ago, and cannot remember what the thing is called. They type *lathe stand* into the catalogue's search and the product comes back.

**Why this priority**: It is the widest of the three in everyday use — notes is the field with the operator's own words in it, and their own words are what they search with. It ranks below Story 1 because a search that misses is visibly a search that missed, whereas a scan that lands on an empty search looks like an answer.

**Independent Test**: Seed two products, one with the search term only in its notes and one without it anywhere, search for the term, and verify the first is returned and the second is not.

**Acceptance Scenarios**:

1. **Given** a product whose notes contain a phrase that appears nowhere else on it, **When** the operator searches for that phrase, **Then** the product is in the results.
2. **Given** a product with no notes, **When** the operator searches for a phrase held only in another product's notes, **Then** it is not in the results.
3. **Given** a product whose notes contain the phrase in different letter casing from the search, **When** the operator searches, **Then** it is still found — notes match the way every other searched field matches.
4. **Given** a search term that matches one product by description and a different product by notes, **When** the operator searches, **Then** both are returned once each, with no duplicate rows.
5. **Given** a text search combined with a category, tag, stock or specification filter, **When** a product matches only through its notes, **Then** the other filters still apply to it normally.
6. **Given** the operator is looking at the search screen, **When** they read what the search box says it searches, **Then** notes are named among the fields — a searchable field the operator does not know is searchable buys nothing.

---

### User Story 3 - The code on the label is the way back to the product (Priority: P3)

The operator has a label in front of them with a code printed on it. They put that code into the application's address and arrive at the product. The code on the thing and the location of its record are the same fact.

**Why this priority**: It is the smallest gain of the three and the only one with a working substitute today — scanning or searching the same code already reaches the product. It is worth doing because it makes the printed code self-sufficient, but it fixes an inelegance rather than a failure.

**Independent Test**: Seed a product, read its permanent printed code, request the address formed from that code, and verify the product's page is served.

**Acceptance Scenarios**:

1. **Given** a product and its permanent printed code, **When** the address formed from that code is requested, **Then** that product's page is served.
2. **Given** a well-formed code that belongs to no product, **When** its address is requested, **Then** the operator is told no product carries that code, in the same way the catalogue reports any other missing product.
3. **Given** any existing link, bookmark or reference to a product by its record number, **When** it is followed after this change, **Then** it works exactly as before — the record number stays the product's canonical address.
4. **Given** a product page reached by its code, **When** the operator uses it, **Then** every action on it behaves identically to the same page reached by its record number.

---

### Edge Cases

- **A structured form carrying a trade item number the catalogue does not hold.** Treated as an unrecognized retail barcode: an offer to create a product with the number attached, not a dead end and not a text search.
- **The structured field appearing after some other field rather than first.** Not recognized. Only a scan that *opens* with the trade item number is read as one; anything else is plain text. Reading a number out of the middle of an arbitrary payload is how a wrong match happens.
- **A distributor's 2D label that also happens to contain a trade item number.** The distributor envelope is recognized first and keeps its existing behaviour; this change does not reorder the kinds of scan already recognized ahead of it.
- **This shop's own printed code.** Recognized before anything else, as it is today. A label this shop printed must never resolve to somebody else's trade item.
- **A trade item number that is all zeros.** Refused, as a bare one already is — that is what a scanner emits on a no-read, not a product.
- **A separator or announcement prefix the scanner adds in transmission.** Absorbed. What the operator sees on the box is the same code whether or not their scanner is configured to decorate it.
- **A product whose notes are empty or absent.** Searching never returns it on the strength of an empty field, and never fails because a field is absent.
- **Notes containing the characters the search already treats as wildcards.** Notes inherit whatever the searched fields do with them today. No special handling is added for notes and none is removed from the other fields — one rule, applied everywhere.
- **A very long note.** Searchable throughout; there is no position in a note beyond which text stops being found.
- **A code-formed address with wrong letter casing or surrounding whitespace.** Either resolves to the product or reports it missing; it never serves a *different* product.
- **Two products cannot share a printed code.** Codes are already unique per product, so a code-formed address is never ambiguous.

## Requirements *(mandatory)*

### Functional Requirements

**Resolving a manufacturer's 2D barcode**

- **FR-001**: The catalogue MUST recognize a scan that carries a trade item number in the standard structured form used by manufacturers' 2D symbols, and MUST resolve it to the same product the bare trade item number resolves to.
- **FR-002**: A recognized structured scan MUST be indistinguishable in outcome from a bare retail barcode scan of the same number: the same product, or the same offer to create one with the number attached, or the same fall-through — decided by the same validity rules, with no second set of rules for the structured form.
- **FR-003**: Recognition MUST tolerate the decorations a scanner adds in transmission: a leading field separator, an announcement of the symbol type, both together, and surrounding whitespace.
- **FR-004**: Recognition MUST accept further structured fields appended after the trade item number, whether they abut it or are separated, and MUST ignore their content.
- **FR-005**: Recognition MUST reject anything that only resembles the structured form — a wrong digit count, non-ASCII digits, or a tail that is not another structured field — and such a scan MUST become a plain text search.
- **FR-006**: A structured scan whose trade item number fails validation, including the scanner's all-zero no-read value, MUST fall through to a plain text search carrying the raw scan. It MUST NOT match any product and MUST NOT be offered as a product to create.
- **FR-007**: Only a scan that *opens* with the trade item number is read as one. A payload in which it appears after some other field MUST remain plain text.
- **FR-008**: The kinds of scan the catalogue already recognizes MUST keep their existing precedence and their existing outcomes. No scan that resolves today may resolve differently after this change, except the structured forms this feature exists to recognize.
- **FR-009**: A scan MUST still never dead-end: every scan yields a product, an offer to create one, or a search.

**Searching notes**

- **FR-010**: Free-text product search MUST match against a product's notes, alongside the description, specifications, manufacturer part number, manufacturer and identifier values it already matches.
- **FR-011**: A product matching through its notes MUST appear exactly once in the results, even when it also matches through another field.
- **FR-012**: Notes MUST match on the same terms as the fields already searched — the same substring behaviour and the same case-insensitivity — so the operator has one rule to learn, not two.
- **FR-013**: All other search filters (category, tag, stock state, specification name and value) MUST continue to constrain results that matched through notes, exactly as they constrain any other result.
- **FR-014**: The search screen MUST name notes among the fields its text search covers.

**The printed code as an address**

- **FR-015**: Requesting the address formed from a product's permanent printed code MUST serve that product's page, with the same content and the same available actions as the page reached by its record number.
- **FR-016**: Requesting a code-formed address for a well-formed code that no product carries MUST report that no such product exists, using the catalogue's existing treatment of a missing product.
- **FR-017**: The record-number address MUST remain the product's canonical address and MUST continue to work unchanged. Existing links, bookmarks and references MUST NOT break.
- **FR-018**: A code-formed address MUST never serve a product other than the one carrying that code.

### Key Entities

- **Product**: The catalogue entry. Already carries a description, notes, specifications, identifiers and a record number. Nothing is added to it by this feature.
- **Product identifier**: A typed, recorded code belonging to a product — this shop's own permanent code, a retail barcode, a manufacturer part number, a distributor or vendor item id. The permanent code is the one printed on the label and the one a code-formed address is built from. Nothing is added to it by this feature.
- **Scan**: Text captured from a scanner or typed by hand, classified by shape into a kind and then resolved to an outcome. This feature adds one recognized shape and changes no outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Scanning a manufacturer's 2D barcode for a product already in the catalogue reaches that product's page in one scan, with no typing and no reading of the number by eye.
- **SC-002**: Every transmission form of that barcode a scanner may emit — bare, separator-prefixed, symbol-type-announced, with trailing fields — reaches the same product. None of them lands on a search.
- **SC-003**: No scan that resolves to a product today resolves to a different product, or to no product, after this change.
- **SC-004**: A structured barcode that fails validation is never matched to a product; the operator sees a search, and is therefore never shown a wrong part as though it were right.
- **SC-005**: Any word or phrase the operator has written in a product's notes finds that product from the search box, without them having to remember which field they wrote it in.
- **SC-006**: The list of searched fields the operator is shown on the search screen matches the fields actually searched.
- **SC-007**: A product's page can be reached from nothing but the code printed on its label — no lookup step, no scan, no search.
- **SC-008**: Every existing way of reaching a product still works: no link, bookmark, or reference by record number is broken by this feature.

## Assumptions

- **The structured form is the trade item number's standard element string.** Issue #62 says "the standard structured form a manufacturer uses to carry a retail barcode inside a 2D symbol". That is the GS1 application identifier `01` element string, the same one the archived branch identified and amended its spec for. It is fixed-length, so nothing terminates it and the next field abuts it directly — which is what makes accepting a trailing field (FR-004) and rejecting a prose tail (FR-005) the same rule.
- **One field, not a parser.** Only the trade item number is read. Lot codes, expiry dates, serial numbers and every other application identifier a manufacturer may print in the same symbol are ignored, and no general element-string parser is introduced. Extracting them has no screen to show them on and is not requested here.
- **Notes means the product's own notes.** A purchase also has a notes field. It records circumstances of one order — a delivery, a price, a substitution — rather than facts about the part, and searching it is not what "anything written about them" asks for. Purchase notes stay out of scope.
- **Notes are searched, not filtered.** Notes join the free-text search. There is no separate "search notes only" control and no notes-specific filter; the operator types words into one box, as they do now.
- **The code-formed address is additive.** Confirmed with the operator: the permanent printed code becomes a working, permanent address that reaches the product, and the record number stays the canonical address. Existing links, templates, tests and screenshots that name a product by record number are untouched.
- **Every product already has a permanent code.** One is assigned at creation, so FR-015 has no products to exclude and this feature needs no backfill.
- **No change to what is stored.** All three gaps are read-path changes over data the catalogue already holds. No new field, no new record type, and no data migration.
- **The scan box and the search box are the ones already in the application.** No new entry point, no new screen.

## Out of Scope

- Extracting anything other than the trade item number from a manufacturer's 2D symbol.
- A general structured-barcode grammar, configurable application identifiers, or handling a payload whose fields appear in an arbitrary order.
- Changing what this shop prints on its own labels, including printing a 2D symbol instead of a barcode, or adding a return-to-owner line. Those are the separate "Labels" gaps in `docs/product-functionality-gap.md`.
- Making specifications structured or filterable beyond what already exists.
- Searching purchase notes, attachments, or photo captions.
- Any change to search ranking or result ordering. Notes join what is matched; they do not change what comes first.
- Retiring or redirecting the record-number address.
