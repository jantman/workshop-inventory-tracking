---
description: "Task list for 033-cross-path-purchase-duplicates"
---

# Tasks: Recognize a Listing Capture and an Order Line as One Purchase

**Input**: Design documents from `/specs/033-cross-path-purchase-duplicates/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/adopting-a-purchase.md), [quickstart.md](./quickstart.md)

**Tests**: **Included, and not optional.** Constitution IV requires a behavior change to land with
tests covering it, and FR-023 goes further: the regression test must be **confirmed red before the
fix**. Most of this feature is statements about what does *not* happen — a second purchase is not
written, a received row is not un-received, a purchase 100 days away is not claimed, an adopted row
is not reported as orphaned — and nothing in the code keeps those true on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: Which user story the task serves (US1, US2, US3)
- Every task names the exact file it touches

## Path Conventions

Server-rendered Flask application; existing layout kept exactly (plan.md → Structure Decision).
`app/` for source, `app/templates/product/` for views, `tests/unit/` and `tests/e2e/` for tests,
`docs/` for the manual. **No new directory, no new module in `app/`, no migration.**

## A note on the phase order

**There is no Setup phase.** No dependency, directory, migration or configuration changes, so the
template's Phase 1 would be make-work. Phase 1 is one shared constant; the two directions are then
independent phases.

**The two directions do not touch each other.** US1 lives entirely in the order-capture path
(`review_order`, `capture_order_lines`, `order_review.html`); US2 lives entirely in the
single-listing path (`_find_captured_purchase`, `CaptureAssessment`, `capture.html`). They share
only `CANDIDATE_WINDOW` from Phase 1. **Phases are ordered by spec priority here, so US1 is the
MVP** — but plan.md's build order puts US2 first because it is the smaller slice and reaches green
sooner, and swapping Phase 2 and Phase 3 costs nothing. Either order is correct.

**Where the risk is**: T016–T019. Claiming a row, and the fact that claiming stamps the order
reference *inside the session the orphan re-query runs in*. Everything else is a form field, a
dataclass field and a sentence of copy.

---

## Phase 1: Foundational — the shared window (blocking prerequisite)

**Purpose**: The one value both directions compare dates against.

**⚠️ Blocks both US1 and US2.** Each reads it; neither owns it.

- [X] T001 Add the module constant `CANDIDATE_WINDOW = timedelta(days=90)` to `app/catalog_service.py`, beside the other capture constants, carrying research.md §10's reasoning in a comment: it is the range within which the operator is *asked*, not a range within which anything is merged, and it is a constant rather than configuration because Constitution I forbids a knob for a future that has not arrived

**Checkpoint**: both direction phases can now begin, in either order.

---

## Phase 2: User Story 1 — an order capture recognizes a listing capture (Priority: P1) 🎯 MVP

**Goal**: An order review shows a line whose product already carries a listing-captured purchase,
asks whether it is the same physical purchase, and — when the operator says yes — adopts that row
instead of writing a second one.

**Independent Test**: Capture a product from a listing, then capture an order containing that item,
answer "same purchase", and confirm the catalog holds one purchase carrying the order's number and
line number. Nothing in US2 or US3 is needed for this to be true.

### Tests for User Story 1 (write first, confirm RED)

- [X] T002 [US1] Create `tests/unit/test_cross_path_duplicates.py` with the FR-023 regression test built on the existing `catalog` fixture: `capture_order(vendor='Amazon', vendor_item_id='B0G43FCHFX', order_date=27 Jul)`, then `capture_order_lines` on an order dated 23 Jul carrying that ASIN with `{'include': True, 'same_purchase': 'adopt'}`, asserting **one** purchase for the product, carrying the order's `supplier_order_reference` and the line's `order_line_number` (FR-012, FR-013). **Run `venv/bin/nox -s tests -- tests/unit/test_cross_path_duplicates.py` and confirm it fails with two purchases** — a test that passes before the fix is testing something else
- [X] T003 [P] [US1] Add to `tests/unit/test_cross_path_duplicates.py` the other two answers: `same_purchase='separate'` records a second purchase and leaves the first byte-for-byte unchanged; `same_purchase` absent on an **included** line raises `ValidationError` with `field == f'same_purchase[{form_key}]'` and writes **nothing at all**, including the order's other lines (FR-008a, FR-016)
- [X] T004 [P] [US1] Add to `tests/unit/test_cross_path_duplicates.py` the candidate boundary tests: a purchase 100 days from the order's date is not offered and a second purchase is recorded with no question (FR-003); a purchase already carrying a *different* order's number is never offered (FR-002); a purchase with `order_date IS NULL`, and an order with no date, produce no candidates (FR-006)
- [X] T005 [P] [US1] Add to `tests/unit/test_cross_path_duplicates.py` the one-candidate-per-line tests: an order carrying the same item id on two lines, against a single candidate, offers it to exactly one line — adopting writes one row and creates one (FR-004); and a line already paired exactly by order number and line number is never offered a candidate (FR-005)
- [X] T006 [P] [US1] Add to `tests/unit/test_cross_path_duplicates.py` the preservation tests: adopting an already-received candidate leaves `received_date`, `quantity` and `product_id` unchanged, moves no tracked count on the product and clears no manual low flag (FR-014, FR-015); and where stamping the order's `order_date` would place it after a recorded `received_date`, the purchase keeps the date it had (research.md §5)
- [X] T007 [P] [US1] Add to `tests/unit/test_cross_path_duplicates.py` the after-effects tests: re-reviewing the same order after an adoption shows the line as `CAPTURED` with no question and a re-capture writes nothing (SC-004); and an adopt-only capture returns `orphaned == ()` — the trap in research.md §8, which is the assertion that catches it
- [X] T008 [P] [US1] Add to `tests/unit/test_cross_path_duplicates.py` the remaining write rules: an excluded line needs no answer and leaves its candidate untouched (FR-008b); `apply_change` on an adopted line takes the order's quantity and unit price and counts into `lines_updated` (FR-009); and `listing_url`, `vendor_order_id` and `order_reference` are gap-filled only — a listing capture's `/dp/...` address survives adoption rather than being overwritten by Amazon's order-page address (contracts §5)

### Implementation for User Story 1

- [X] T009 [P] [US1] Add the `CandidatePurchase` frozen dataclass to `app/models.py` beside `ReviewedLine`, with data-model.md's seven fields (`purchase_id`, `order_date`, `quantity`, `unit_price`, `product_id`, `product_description`, `is_received`); `unit_price` is `Optional[Decimal]` and is never converted to `float` (Constitution III). Document why it is a plain value rather than an ORM row, as `ReviewedLine` and `CaptureAssessment` already do
- [X] T010 [US1] Extend `ReviewedLine` in `app/models.py`: add `candidate: Optional[CandidatePurchase] = None` and the `has_candidate` / `needs_same_purchase_answer` properties, and widen `has_change` (`app/models.py:1967`) so it also fires for a line with a candidate, comparing the order's values against the candidate's. **Keep both existing guards verbatim** — the "a value the vendor did not give is not a change" guard and the `price_to_cents` rounding on both sides are two separate PR-review fixes and must not be re-derived
- [X] T011 [US1] Add `_candidate_order_purchases(session, order, vendor, order_date)` to `app/catalog_service.py`: `vendor == vendor.name`, `vendor_item_id IN` the order's item ids, `supplier_order_reference IS NULL`, `order_date` within `CANDIDATE_WINDOW`, ordered by id. Document research.md §2 at the call site — this is deliberately **not** an `OrderVendor` member, because nothing about it differs per vendor, and that is what makes FR-021 free
- [X] T012 [US1] Add `_assign_candidates(session, order, vendor, order_date, recorded)` to `app/catalog_service.py`, returning `Dict[form_key, CandidatePurchase]`: walk `order.lines` in order, skip any line already in `recorded` (CAPTURED), and give each remaining line the matching row closest in date to the order's, ties broken by lowest id, removing it from the pool. Mirror the shape of `_recorded_order_lines`' pass two (`app/catalog_service.py:2236`) so the two read alike
- [X] T013 [US1] Wire candidates into the read path in `app/catalog_service.py`: `review_order` builds the assignment inside its existing session and passes it to `_review_order_line`, which attaches the line's `CandidatePurchase` to the `ReviewedLine` it returns. **The four states are not touched** — research.md §3
- [X] T014 [US1] Render the question in `app/templates/product/order_review.html`: on every line where `reviewed.needs_same_purchase_answer`, show the candidate's order date, quantity, unit price and product description beside the order's figures, a plain sentence where `candidate.is_received`, and a `same_purchase[{key}]` radio pair (`adopt` / `separate`) with **no default selected**, restored from `form_data` on a re-render the way `resolution[...]` already is. Also relax the `apply_change` tick's condition so it renders for an adoptable line (FR-007, FR-009)
- [X] T015 [US1] Add `'same_purchase': form.get(f'same_purchase[{key}]') or ''` to `_order_decisions` in `app/product/routes.py:1366`, read for every vendor and ignored by lines with no candidate — exactly as `resolution` already is, with no branch
- [X] T016 [US1] Add `_claim_purchase(purchase, order, line, vendor)` to `app/catalog_service.py` implementing contracts §5 in order: stamp `supplier_order_reference` and `order_line_number` unconditionally; set `order_date` to the order's **unless** that would put it after a recorded `received_date`; write every other `vendor.order_fields(order)` key only where the purchase holds NULL. Never touch `product_id`, `received_date`, `notes` or `listing_title`
- [X] T017 [US1] Branch on the candidate in `capture_order_lines` in `app/catalog_service.py`, after the CAPTURED `continue` and the include gate: `adopt` calls `_claim_purchase`, **skips `_product_for_order_line` entirely** and adds no `Purchase` — so `products_created` and `products_attached` do not move; `separate` runs today's path untouched; anything else raises `ValidationError` inside the session so the whole order rolls back
- [X] T018 [US1] In the same method in `app/catalog_service.py`, pass the adopted ids to `_orphaned_order_purchases(..., also_claimed=purchase_ids + adopted_ids)`. **This is the one that will bite**: claiming stamps the order reference inside this session, so the orphan re-query returns the adopted row while `paired` — built before the loop — does not. The docstring at `app/catalog_service.py:2465` records this going wrong once already
- [X] T019 [US1] Add `purchases_adopted: tuple = ()` to `OrderCaptureResult` in `app/models.py`, populate it from `capture_order_lines`, and add `or bool(self.purchases_adopted)` to `wrote_anything`. `purchase_ids` keeps meaning **created** — an adopted line must not inflate "Captured N line(s)"
- [X] T020 [US1] Add the adoption clause to `_order_capture_summary` in `app/product/routes.py:1402`, **above** the "Nothing new to capture" fallback and inside the same block as the other write outcomes, so the fallback keeps meaning "none of the above happened" by construction rather than by a condition someone has to remember
- [X] T021 [US1] Add a `purchases_adopted`-only case to the parametrize list of `test_the_fallback_agrees_with_wrote_anything` in `tests/unit/test_mcmaster_routes.py:600`. This is an added case, not an edited assertion — that test exists precisely to catch a new kind of write taught to one of the pair and not the other
- [X] T022 [US1] Run `venv/bin/nox -s tests` and confirm the whole unit suite is green, including the T002 regression test that was red

**Checkpoint**: User Story 1 is complete and independently demonstrable. Issue #129's reported failure no longer reproduces.

---

## Phase 3: User Story 2 — a listing capture recognizes an order capture (Priority: P2)

**Goal**: Capturing a listing for an item already recorded by an order capture raises the existing
duplicate question, even when the operator's typed date and the vendor's differ by days.

**Independent Test**: Capture an order, then capture one of its items from its listing page with an
order date four days off, and confirm the question is raised and names the order. Needs nothing
from Phase 2.

### Tests for User Story 2 (write first, confirm RED)

- [X] T023 [P] [US2] Add to `tests/unit/test_cross_path_duplicates.py` the reverse-direction tests: after an order capture, a `capture_order` for the same vendor and item id dated four days away raises `CaptureDecisionRequired` whose assessment names the purchase **and its `duplicate_order_reference`** (FR-017, FR-018); passing that id as `acknowledged_duplicate_of` records a second purchase (FR-019); a purchase carrying **no** order number is still only recognized same-day, so two listing captures months apart record two purchases with no question (FR-020, research.md §7); and a hit 100 days away is not recognized. **Confirm red before T025**

### Implementation for User Story 2

- [X] T024 [P] [US2] Add `duplicate_order_reference: Optional[str] = None` to `CaptureAssessment` in `app/models.py:501` and to its `to_dict()`, beside the other `duplicate_*` keys — additive, so no existing key changes name, type or meaning
- [X] T025 [US2] Add the second arm to `_find_captured_purchase` in `app/catalog_service.py:1465`: keep the existing same-day query **verbatim** and try again only when it returns nothing — same vendor, same `vendor_item_id`, `supplier_order_reference IS NOT NULL`, `order_date` within `CANDIDATE_WINDOW`, nearest by date and ties by lowest id. **Do not widen the `listing_url` fallback**: an Amazon order capture writes the order-page address there, never the listing's, so there is nothing for it to match (research.md §7)
- [X] T026 [US2] Populate `duplicate_order_reference` at the `CaptureDecisionRequired` raise site in `capture_order` (`app/catalog_service.py:1197`), beside the existing `duplicate_purchase_id` / `duplicate_order_date` / `duplicate_vendor` assignments
- [X] T027 [US2] Name the order in the duplicate panel of `app/templates/product/capture.html:27`: where `assessment.duplicate_order_reference` is set, say which order the recorded purchase belongs to. The panel, its "Open the one already recorded" link and its "This is a separate order — record it anyway" checkbox are unchanged — this is wording, not a new flow
- [X] T028 [P] [US2] Add a route-level test to `tests/unit/test_cross_path_duplicates.py` asserting that `/api/capture` answers 409 and its JSON `assessment` carries `duplicate_order_reference` for a listing captured against an item already recorded by an order capture. It goes in the new file rather than beside `test_the_json_representation_answers_409_when_it_needs_a_decision` in `tests/unit/test_capture.py`, so that file stays untouched for T031

**Checkpoint**: both directions are closed. The reported defect cannot be produced in either order.

---

## Phase 4: User Story 3 — the same protection on McMaster and DigiKey (Priority: P3)

**Goal**: Prove the recognition is genuinely vendor-agnostic rather than Amazon-shaped.

**Independent Test**: The same adopt journey against a McMaster order and a DigiKey order, with no
production code added for either.

**Note**: this phase should add **no production code**. If it does, research.md §2 was wrong and the
lookup has become vendor-specific — stop and re-cut it rather than branching.

- [X] T029 [P] [US3] Add the McMaster case to `tests/unit/test_cross_path_duplicates.py`: a product-page capture recorded against `McMaster-Carr` with a part number, then an order carrying that part, adopted — one purchase, order number and line number stamped (FR-021)
- [X] T030 [P] [US3] Add the DigiKey case to `tests/unit/test_cross_path_duplicates.py`, same shape against a DigiKey part number, with the part lookup stubbed as the existing DigiKey tests do
- [X] T031 [US3] Verify FR-022 by inspection: `git diff --stat` must show **no** change to `tests/unit/test_order_vendors.py`, `tests/unit/test_digikey_capture.py`, `tests/unit/test_mcmaster_capture.py`, `tests/unit/test_amazon_capture.py` or `tests/unit/test_capture.py`. The only pre-existing test files that may change at all are `tests/unit/test_mcmaster_routes.py` (the added parametrize case, T021) and `tests/e2e/test_amazon_order.py` (two added journeys, T032-T033) — and in both the change must be an addition, never an edited assertion

**Checkpoint**: all three vendors covered, by tests rather than by three copies of the code.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T032 [P] Add the adopt journey to `tests/e2e/test_amazon_order.py`: seed a listing-captured purchase with `live_server.add_test_data`, drive the existing Amazon order fixture to its review, assert the line shows the recorded purchase, choose *Same purchase*, confirm, and assert the product page shows **one** purchase row carrying the order number. Wait on the destination page's own content (pattern C) — no `wait_for_timeout`, no `networkidle`
- [X] T033 [P] Add the refusal journey to `tests/e2e/test_amazon_order.py`: confirm the review with the question unanswered, assert the review re-renders with the error flashed, and assert the product page still shows one purchase. **This is the dangerous assertion** — establish the purchase-history table with `expect(...)` before counting rows, or it passes against a table that has not rendered
- [X] T034 [P] Update `docs/user-manual.md`: in the shared order-capture section, say what the review now asks when a line matches something already recorded from its listing page, what adopting does to that row (it gains the order's number, line number and date; its quantity and price change only if you tick "Update it?"; a received purchase stays received), and that a purchase adopted in error is removed with the delete flow documented under "Removing a Purchase Recorded in Error"
- [X] T035 [P] Update the standing note in `app/templates/product/order_review.html` that tells the operator to "capture the item's own listing page afterwards; it will attach to the same product rather than making a second one" — that sentence was true of the *product* only, and this feature makes it true of the purchase as well. Say so
- [X] T036 Run `venv/bin/nox -s lint` and clear anything it reports
- [X] T037 Run the e2e suite detached and poll — `nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &`, budget 15 minutes warm and 20 cold — and confirm it passes **and leaves the working tree clean** (Constitution IV)
- [X] T038 Confirm `migrations/versions/` is untouched and `git status` shows no migration — research.md §12; the third consecutive order feature to ship none
- [X] T039 Record the two manual checks in a new `specs/033-cross-path-purchase-duplicates/verification.md`, per quickstart.md: re-run the exact Amazon case that found this (listing then order), and the reverse with mismatched dates. Note that product 10's purchases 10 and 11 are the ready-made fixture, and that cleaning them up is feature 032's delete rather than this feature's job

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Foundational)**: no dependencies; blocks Phase 2 and Phase 3, which both read `CANDIDATE_WINDOW`
- **Phase 2 (US1)** and **Phase 3 (US2)**: independent of each other. They share no function, no template and no test beyond the file `tests/unit/test_cross_path_duplicates.py`, which each appends to
- **Phase 4 (US3)**: depends on Phase 2 (it exercises the adopt path); adds no production code
- **Phase 5 (Polish)**: T032–T033 depend on Phase 2; T034–T035 depend on Phases 2 and 3; T036–T039 are the merge gate and depend on everything

### Within User Story 1

T002 is written and **confirmed red** before any of T009–T021. Then: models (T009, T010) → the read
path (T011–T014) → the decision (T015) → the write (T016–T018) → reporting (T019–T021) → the suite
(T022). T014 needs T010 to exist for `needs_same_purchase_answer`; T017 needs T016; T018 needs T017.

### Within User Story 2

T023 red first, then T024 → T025 → T026 → T027. T028 needs T024.

### Parallel opportunities

- **T003–T008** are one file each appending a class, and can be written together once T002 has established the fixture shape
- **T009** is parallel with T011 (different files)
- **T024** is parallel with T023 (different files)
- **T029 and T030** are independent of each other
- **T032–T035** are four different files and are fully parallel
- **Phase 2 and Phase 3 as wholes** can be worked in parallel or in either order

---

## Parallel Example: User Story 1 tests

```bash
# After T002 has established the fixture shape and been confirmed red,
# these five append independent test classes to the same new file:
Task: "T003 — the other two answers (separate, unanswered)"
Task: "T004 — candidate boundaries (window, other order's number, no date)"
Task: "T005 — one candidate per line, and CAPTURED takes none"
Task: "T006 — received candidate preserved, order_date guard"
Task: "T007 — re-capture reads CAPTURED, orphaned is empty"
Task: "T008 — excluded line, apply_change, gap-fill only"
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1 — one constant
2. Phase 2 — write T002, **watch it fail**, then build until it passes and the suite is green
3. **STOP and validate**: capture a listing, capture the order, one purchase
4. This alone closes issue #129's reported failure

### Incremental delivery

1. Phase 1 → both directions unblocked
2. Phase 2 → the reported defect is fixed (MVP)
3. Phase 3 → the direction `specs/029-whole-order-capture/spec.md:103` wrongly claimed was covered is covered
4. Phase 4 → the same guarantee proven for McMaster and DigiKey
5. Phase 5 → e2e, docs, and the two checks a person has to make

### The smaller-first alternative

plan.md builds US2 before US1: it is one query arm, one dataclass field and a sentence of copy, and
it reaches green in a fraction of the work. Swap Phase 2 and Phase 3 if a quick first landing
matters more than delivering the P1 story first. Nothing depends on the order.
