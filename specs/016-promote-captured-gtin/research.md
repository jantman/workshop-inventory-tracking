# Phase 0 Research: A Captured Barcode Becomes a Scannable Identifier

Decisions taken before any code, each with what was rejected. The spec had no open
`[NEEDS CLARIFICATION]` markers — both were settled with the owner during `/speckit-specify` — so
this is design research rather than requirements research, with one exception: §3 found that one of
those settled answers was more expensive than it looked, and amended the spec rather than paying for
it.

## 1. Reuse of the existing GTIN validation

**Decision**: Call `app.utils.gtin.normalize_and_validate(value)` and treat `None` as "not a
barcode". Nothing else.

**Rationale**: That function is exactly the classifier's entry point already — "a scan is a GTIN
when, and only when, this returns a key" (its own docstring). It enforces the accepted lengths
(8/12/13/14), ASCII digits only, the GS1 mod-10 check digit, and the all-zero no-read refusal, and
it returns the 14-digit key that `product_identifiers.value` stores. Issue #93 asks for reuse in as
many words, and FR-002 makes it a requirement.

**Alternatives considered**:

- *A capture-specific validator, more lenient about punctuation.* Rejected. Two validators means two
  answers to "is this a barcode", and the lenient one would be the unattended one — the worst place
  to relax a rule.
- *Calling `add_identifier` and letting it validate.* Partly adopted: `add_identifier` **is** how the
  write happens, and it validates through the same module. But promotion also needs to *classify*
  without writing (for the report in §4), so the pure function is called directly there.

## 2. Where promotion happens: inside the merge, not after it

**Decision**: Promotion runs inside `_apply_listing`, over the rows `merge_specifications` reports
it added. `merge_specifications` changes its return value from a count to the list of validated
entries it appended.

**Rationale**: The owner's settled answer is "only surviving rows" — only rows this capture actually
added to the specification list are promoted. "Was this row added?" is knowable at exactly one
moment, inside the merge, because the merge is what decides it (a captured row whose folded name the
product already carries is dropped whole). Returning the added rows makes that knowledge available
without a second implementation of the drop rule. `len()` of the new return value is the old return
value, so the change costs two assertions in `tests/unit/test_capture.py` and nothing else.

**Alternatives considered**:

- *Compute the pre-merge name set in `_apply_listing` and re-derive which rows will be added.*
  Rejected: two implementations of "the product already has a row of that name", one of which
  (`merge_specifications`) is documented as the authority and folds in Python for a stated
  cross-backend reason. They would drift.
- *Promote from the product's post-merge specification list.* Rejected — this is the semantics the
  owner explicitly did **not** choose. It would promote a value that a pre-existing row holds,
  which is the "surviving rows, plus the retained row's own value" option from the specify pass.
- *Promote in the route, after `capture_order` returns.* Rejected: the route cannot tell an added row
  from a dropped one, and building the merge's entry list (which includes the synthesized
  `Description` row) in a route would put business logic in the presentation layer, against
  Principle II.

## 3. How the confirmation page learns what happened — and the spec amendment that came out of it

**Decision**: The route calls a new **read-only** service method after `capture_order` returns and
builds the message from the catalog's final state. The report therefore describes the barcode's
**state** ("recorded on this product") rather than this capture's **action** ("recorded just now").
`spec.md` was amended to match: FR-009 and FR-010 are now state-shaped, and SC-003 no longer requires
silence on a repeat capture.

**Rationale**: This is the one place the design was pulled toward complexity, so it is worth stating
plainly.

Promotion happens inside `capture_order`, which returns a `Purchase`. For the route to report what
promotion *did*, that information has to travel out of `capture_order` — and every channel for it is
expensive or ugly:

| Channel | Cost |
|---|---|
| Return a `CaptureResult(purchase, barcodes)` dataclass | ~80 `capture_order(` call sites in `tests/unit/test_capture.py`, ~55 of which use the return value, plus both route call sites. A mechanical 55-line test diff attached to a feature whose application diff is under 80 lines. |
| An out-parameter the caller passes in and the service fills | One line at the call site and no churn, but out-parameters are not idiomatic Python; a reader stumbles, and "prefer boring, obvious code" cuts against it. |
| Set a transient attribute on the returned ORM `Purchase` | Cheapest, and the worst: a reader seeing `purchase.captured_barcodes` looks for a column that does not exist. |
| Move the listing merge out of `capture_order` so the route drives both steps | Rewrites ~16 service-level tests, deletes a deliberate design property documented at length in `capture_order`'s docstring, and pushes entry-building into the route. |

Against that, what the state-derived report actually loses: on a **repeat** capture of a listing
whose barcode is already on the product, the page says the barcode is recorded rather than saying
nothing. That statement is true, useful, and arguably better than silence. Every other outcome —
unusable value, collision with another product, a row the merge did not examine — is derived exactly,
because none of them wrote anything to be ambiguous about.

The constitution says a change may be rejected purely for being larger than the problem. Paying a
55-site refactor to avoid one redundant true sentence is that. So the requirement moved.

**Alternatives considered**: all four rows of the table above, plus *reporting nothing on success*
(rejected — the owner chose "everything that happened", and a silent success is how the operator
learns nothing about a feature that mostly works invisibly), and *timestamp comparison against
`ProductIdentifier.date_added`* (rejected: inferring causality from clock values, to save a
sentence).

## 4. The report's four outcomes are derived, not flagged

**Decision**: `describe_captured_barcodes(product_id, listing)` classifies each barcode-named row
into exactly one of `unusable`, `recorded`, `taken`, `not_examined`, from the value and the catalog's
final state, in that order of test.

**Rationale**: The four are mutually exclusive and exhaustive, which makes the matrix directly
testable and leaves no "other" branch to rot. `not_examined` is the interesting one: it is an
*inference* — a valid barcode that no product holds can only be a row the merge dropped, because
every added row was either promoted (so this product holds it) or collided (so another product
does). That inference is why no flag has to be threaded from the write path to the read path.

**Alternatives considered**:

- *Return the outcomes from the write path as structured data.* Same channel problem as §3.
- *A fifth `already_recorded` outcome.* That is precisely the distinction §3 declined to buy.

## 5. Recognized names: a frozenset and a whole-name fold

**Decision**: A module-level `frozenset` of the six names from the issue, compared against
`' '.join(name.split()).upper()`.

**Rationale**: FR-001's list is closed and short. Folding case and collapsing whitespace covers
`upc`, `UPC ` and `Upc`; comparing the *whole* folded name — not a substring — keeps
`Manufacturer UPC` and `UPC Code` out, because a feature that promised six names should promote six
names. Adding a seventh later is a one-line change, which is why no configuration knob is warranted
(Principle I).

**Alternatives considered**:

- *A regular expression, or substring matching.* Rejected: strictly more permissive, in a path where
  nobody is watching.
- *A settings entry or database table of recognized names.* Rejected outright — speculative
  generality for a list that has changed zero times.

## 6. Collisions lean on the database, not on a Python pre-check

**Decision**: Call `add_identifier` and catch `DuplicateItemError`.

**Rationale**: `uq_identifier_type_value_vendor` is what makes "one product per barcode" a property
of the data rather than a convention, and `_add_identifier` already distinguishes the two cases
correctly: the *same* product returns the existing row (FR-007 needs no code), a *different* product
raises `DuplicateItemError` carrying that product's id (FR-006's message has what it needs). A
pre-check would duplicate that and still have to handle the exception.

**Alternatives considered**: *Query first, then insert.* Rejected as duplicate logic. (The
check-then-act race that would normally argue for it does not exist here — one user, one request.)

## 7. Deduplicate the report by normalized key

**Decision**: Two barcode-named rows whose values normalize to the same 14-digit key produce one
report line.

**Rationale**: A listing that publishes both a 12-digit `UPC` and its 13-digit `EAN` form is
publishing one barcode; normalization is what makes them one identifier, and the message should
agree with the catalog. Two lines saying the same key was recorded reads as two barcodes.

## 8. No retrofit, and what that means for verifying the issue

**Decision**: No sweep over existing products, and this is called out in the spec's Assumptions.

**Rationale**: Principle I, and the fact that a sweep is a second unattended write path over data
nobody is looking at. The consequence, already recorded in SC-001 and worth repeating where the
implementer will see it: **`B01N4OSKWE` already carries a `UPC` specification row**, so re-capturing
it promotes nothing (§2). Verifying the issue by hand means capturing onto a product without that
row, or deleting the row first. The confirmation page will say `not examined` in exactly that case,
which is the signal that the rule fired rather than that the feature is broken.

## 9. Test placement and the shared E2E fixture

**Decision**: Unit tests join `tests/unit/test_capture.py`; E2E joins
`tests/e2e/test_product_page_capture.py`; the `UPC` row goes into the **shared**
`tests/e2e/fixtures/amazon_listing.html` rather than a new fixture file.

**Rationale**: A vendor listing fixture with no barcode row is no longer representative of the case
this feature exists for, and every existing capture test then exercises the new path incidentally.
The risk of disturbing those tests was checked rather than assumed: their assertions use
`to_contain_text` and filtered counts, not exact row lists, so a seventh row does not break them.
The whole file still gets re-run.

**Alternatives considered**: *A fourth fixture file (`amazon_listing_upc.html`).* There is precedent
(`amazon_listing_aplus.html`, `amazon_listing_markup_only.html`), but those exist to vary page
*structure*, which this does not. Duplicating a 200-line fixture for one `<tr>` is the more
expensive option.
