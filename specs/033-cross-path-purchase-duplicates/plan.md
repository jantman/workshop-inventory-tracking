# Implementation Plan: Recognize a Listing Capture and an Order Line as One Purchase

**Branch**: `033-cross-path-purchase-duplicates` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/033-cross-path-purchase-duplicates/spec.md`

## Summary

Stop the two capture paths writing two purchases for one physical purchase, in both directions,
for all three vendors — by widening what each path can *see*, not by adding a heuristic to
either.

The approach in one line: **one new vendor-agnostic query, one new radio button on a review that
already asks two other questions, and one extra arm on the single-listing duplicate lookup.**

Five findings from reading the code make this much smaller than twenty-three requirements
suggest:

1. **The order path is missing an input, not an algorithm.** `_recorded_order_lines`
   (`app/catalog_service.py:2186`) already has a pass that claims a purchase by item id when it
   carries no line number — written for "one recorded by hand against the same order". It is
   never handed a listing-captured row, because every vendor's `order_purchases` filters on
   `supplier_order_reference` and a listing capture leaves that NULL. research.md §1.
2. **The candidate query needs nothing from the vendor.** Vendor name, item id and order date
   are written identically by both paths, and the line's item id is already
   `vendor.item_id_of(line)`. So FR-021 — all three vendors — is satisfied by one shared helper
   rather than three edits, and `OrderVendor` is not touched at all. research.md §2.
3. **Adoption is a decision on top of the existing line state, not a fifth state.**
   `OrderLineState` is exclusive and exhaustive and a line answered "separate" is whatever it
   already was, so inserting a state would throw that away and force a second answer. A
   `candidate` field plus one new form input costs less and interacts correctly with CONFLICT,
   which can be open on the same line. research.md §3.
4. **`OrderVendor`'s existing `order_fields` / `line_fields` split *is* the rule for what
   claiming writes.** The order's fields become the purchase's, because it is now a line of that
   order; the line's stay the operator's, changed only through the "Update it?" tick that
   already exists. research.md §4.
5. **No schema change.** Every column is already there and already written by both paths. Third
   consecutive order feature to ship no Alembic revision. research.md §12.

**The one thing that will bite if it is forgotten**: an adopted purchase is stamped with the
order reference *inside the capture's own session*, so `_orphaned_order_purchases`' re-query
returns it while `paired` — built before the loop — does not. Its ids must join `also_claimed`
or every adoption is flashed back to the operator as a stale line. The docstring at
`app/catalog_service.py:2465` records this going wrong once already. research.md §8.

**Order of work is not the story priority order.** US2 (the reverse direction, P2) is the
smallest and most independent piece — one extra arm on one query plus one assessment field — and
it lands first as a self-contained slice. US1 (P1) is the larger one and depends on nothing US2
does. US3 (P3) is two tests, because the query is already shared.

## Technical Context

**Language/Version**: Python 3.13 (server), Jinja2 templates. Roughly ten lines of new inline
template markup and **no new browser JavaScript** — the review's only script is the arrival
checkbox convenience and it is untouched. The capture agent and bookmarklet are untouched.

**Primary Dependencies**: Flask, SQLAlchemy, Jinja2 — all present. **No new dependency**, and
nothing removed.

**Storage**: MariaDB via `MariaDBStorage`; SQLite through the same interface under unit test.
**No schema change and no Alembic revision** — research.md §12.

**Testing**: pytest through `nox` (`tests`, `e2e`, `lint`); Playwright for e2e. **No new pytest
marker**, so `pytest.ini` is untouched under `--strict-markers`. One new unit file
(`tests/unit/test_cross_path_duplicates.py`), two new e2e journeys in the existing
`tests/e2e/test_amazon_order.py`.

**Target Platform**: Flask app on the LAN, no login, single operator.

**Project Type**: Server-rendered Flask web application. No SPA, no build pipeline.

**Performance Goals**: none new. The candidate lookup is one indexed query per review or capture
— `purchases.vendor_item_id` is already indexed and the `IN` list is the order's line count,
typically under twenty-five. Per Constitution I, no caching and no index work without a
measurement.

**Constraints**: nothing may be written before the operator confirms; the whole order writes or
none of it does; a received purchase must not be un-received or have its side effects re-run;
existing tests must pass unedited (FR-022), which research.md §11 establishes is achievable.

**Scale/Scope**: one operator, a few thousand purchase rows. Three production files gain code
(`app/catalog_service.py`, `app/models.py`, `app/product/routes.py`), two templates gain markup
(`order_review.html`, `capture.html`), one documentation section is written. No file is created
in `app/`.

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1 design. No violations; Complexity
Tracking is therefore omitted.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | **Pass.** No new abstraction: `OrderVendor` gains no member (research.md §2), no new `OrderLineState`, no new route, no new table, no configuration knob — the 90-day window is a module constant because there is one operator with one answer (research.md §10). The feature is one query, one form input and one extra arm on an existing query. It also *removes* a hazard rather than adding machinery. |
| **II. Layered Architecture Boundaries** | **Pass.** All logic lands in `CatalogService`; the routes gain one form key in `_order_decisions` and nothing else. No raw SQL or ORM query in a route. `CandidatePurchase` is a frozen dataclass in `app/models.py`, matching `ReviewedLine` and `CaptureAssessment` — a template never holds an ORM row across a closed session. |
| **III. Exact Numerics** | **Pass.** No arithmetic on money is introduced. `unit_price` is carried and compared as `Decimal`; the one comparison (`has_change`) reuses the existing `price_to_cents` rounding guard verbatim rather than re-deriving it. Date comparison is `timedelta`, not float days. |
| **IV. Test Discipline Through Nox** | **Pass.** Everything runs through `nox`. FR-023 requires the regression test **confirmed red before the fix**. No new marker. New e2e waits on observable state only — quickstart.md names the pattern for each and flags the negative assertion as the dangerous one. Screenshot tests are untouched, so an e2e run still leaves the tree clean. |
| **V. MariaDB Is the Source of Truth** | **Pass.** No schema change, so no migration and nothing to reverse. Every write is through the existing session in `capture_order_lines`, inside its all-or-nothing transaction. Google Sheets is not touched. |
| **VI. Item Lifecycle and History Invariants** | **Not applicable, and checked rather than assumed.** This feature touches `purchases` only. No JA ID, no active-row filtering, no parent-child relationship and no shortening path is reached. It does honor the neighbouring purchase invariants deliberately: a received purchase stays received, no tracked count moves, no manual low flag clears (FR-014), and `_validate_receipt_order`'s "nothing arrives before it is ordered" is respected by the `order_date` stamp (research.md §5). |

**Post-design re-check**: unchanged. The Phase 1 design added no abstraction, no dependency and
no persistent state; the one thing it added to the constitution's surface is the
`_validate_receipt_order` guard, which strengthens V rather than straining it.

## Project Structure

### Documentation (this feature)

```text
specs/033-cross-path-purchase-duplicates/
├── plan.md                            # This file
├── research.md                        # Phase 0 — twelve findings from the code
├── data-model.md                      # Phase 1 — no schema change; the in-memory model
├── quickstart.md                      # Phase 1 — how to prove it, red first
├── contracts/
│   └── adopting-a-purchase.md         # Phase 1 — the form, the service methods, what claiming writes
├── spec.md
├── checklists/requirements.md
└── tasks.md                           # /speckit-tasks — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── catalog_service.py       # CHANGED
│   ├── CANDIDATE_WINDOW                  new module constant (research.md §10)
│   ├── _candidate_order_purchases        new; vendor-agnostic (research.md §2)
│   ├── _assign_candidates                new; one candidate per line (research.md §6)
│   ├── _review_order_line                carries the candidate onto ReviewedLine
│   ├── review_order                      builds the candidate map for the review
│   ├── capture_order_lines               adopt / separate / refuse; adopted ids into also_claimed
│   ├── _claim_purchase                   new; what claiming writes (contracts §5)
│   └── _find_captured_purchase           second arm for the reverse direction (research.md §7)
├── models.py                # CHANGED
│   ├── CandidatePurchase                 new frozen dataclass
│   ├── ReviewedLine                      candidate field; has_change widened
│   ├── OrderCaptureResult                purchases_adopted; wrote_anything
│   └── CaptureAssessment                 duplicate_order_reference (+ to_dict)
├── product/routes.py        # CHANGED
│   ├── _order_decisions                  reads same_purchase[...]
│   └── _order_capture_summary            names adoptions above the fallback
└── templates/product/
    ├── order_review.html    # CHANGED — the adopt/separate radios and the candidate's figures
    └── capture.html         # CHANGED — the duplicate panel names the order

tests/
├── unit/test_cross_path_duplicates.py    # NEW — the whole matrix, both directions, three vendors
├── unit/test_mcmaster_routes.py          # one parametrize case added (research.md §9)
└── e2e/test_amazon_order.py              # two journeys added: adopt, and refuse-unanswered

docs/user-manual.md          # CHANGED — what the review now asks, and what adopting does
migrations/                  # UNCHANGED — nothing to migrate
```

**Structure Decision**: the existing four-layer structure is kept exactly. This feature adds no
module and no package; every change lands in a file that already owns the behavior it extends.
The one judgement call is that the candidate lookup lives on `CatalogService` rather than on
`OrderVendor` — justified in research.md §2 by the fact that nothing about it differs per vendor,
and load-bearing for FR-021.

## Implementation Order

Four slices, each independently testable, each leaving the suite green.

1. **US2 — the reverse direction.** `_find_captured_purchase`'s second arm, `CANDIDATE_WINDOW`,
   `CaptureAssessment.duplicate_order_reference` and its `to_dict`, the wording in
   `capture.html`. Smallest slice, no dependency on anything below.
2. **US1a — recognition, read-only.** `_candidate_order_purchases`, `_assign_candidates`,
   `CandidatePurchase`, `ReviewedLine.candidate`, `has_change` widened, and the review template.
   `review_order` writes nothing, so this slice is provably safe to land on its own: the review
   shows the question and confirming still behaves exactly as it does today.
3. **US1b — the decision and the write.** `same_purchase` through `_order_decisions`,
   `_claim_purchase`, the refusal, `purchases_adopted`, `also_claimed`, `wrote_anything` and the
   flash. This is the slice that closes the issue.
4. **US3 + docs.** The McMaster and DigiKey tests (which need no production code), the e2e
   journeys, and the user-manual section.

The FR-023 regression test is written and **confirmed red** before slice 3, per Constitution IV
and the issue's own instruction.
