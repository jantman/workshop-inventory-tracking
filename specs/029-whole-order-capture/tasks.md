---
description: "Task list for 029-whole-order-capture"
---

# Tasks: Whole-Order Capture for Every Vendor

**Input**: Design documents from `/specs/029-whole-order-capture/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **Included, and not optional here.** Constitution IV requires that changes altering
behavior land with tests covering that behavior, and `nox -s tests` / `nox -s e2e` must pass
before merge. The regression suites additionally *are* the specification of the behaviour being
consolidated (research.md §14).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story the task serves (US1, US2, US3)
- Every task names the exact file it touches

## Path Conventions

Server-rendered Flask application, existing layout kept exactly (plan.md → Structure Decision):
`app/` for source, `tests/unit/` and `tests/e2e/` for tests. No new directory.

## A note on story-to-phase mapping

**US3 spans two phases, deliberately.** Its non-visible half — one order flow instead of three —
is a blocking prerequisite for everything else, so it is **Phase 2 (Foundational)** and its tasks
carry no story label, per the format rule. Its user-visible half — the captured-orders list — is
**Phase 5** and is labelled `[US3]`.

This is the plan's stated sequencing: the story priorities order by *value*, the phases order by
*dependency*. Building Amazon as a third copy and then merging three copies is strictly more work
than merging two and extending the result.

---

## Phase 1: Gate — the Amazon fixtures

**Purpose**: No Amazon selector can be tested until a real order page exists as a fixture. This
phase blocks Phase 3 only — **Phase 2 does not depend on it**, so the two run concurrently.

- [X] T001 Save a real multi-line Amazon order-details page as `tests/e2e/fixtures/amazon_order.html`, **scrubbed** of shipping address, buyer name, payment method and the real order number before it is committed
- [X] T002 [P] Verify `tests/e2e/fixtures/amazon_order.html` retains realistic recommendation markup — a 4-line order page carries ~26 `/dp/` links across ~9 ASINs, and a stripped fixture stops catching the trap in research.md §4
- [X] T003 [P] Derive `tests/e2e/fixtures/amazon_order_unreadable.html` — a page from which no row can be read, for FR-023
- [X] T004 [P] Derive `tests/e2e/fixtures/amazon_order_partial.html` — one row missing its ASIN, one with an unparseable price, for FR-019 and FR-021
- [ ] T005 [P] **DEFERRED — no qualifying order exists.** Close the one open input: read `[data-component="quantity"]` on a real order containing a line with quantity ≥ 2 and record the rendering in `specs/029-whole-order-capture/research.md` §6

**On T005**: no order in the ten most recent had such a line. **If no such order exists yet, this
task is deferred, not blocking** — the reader takes any digits it finds and falls back to 1,
which is correct for the confirmed case and safe for the other, because the quantity is on the
review and editable before anything is written.

**Checkpoint**: Every Amazon selector now has something to be written against.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Collapse the two shipped order captures onto one flow. **No user-visible change.**

**⚠️ CRITICAL**: No user story work begins until T019 passes. This is US3's non-visible half.

### The regression baseline — establish it first

- [X] T006 Record the pre-refactor baseline by running `venv/bin/nox -s tests` and the detached `venv/bin/nox -s e2e`, saving results for comparison
- [X] T007 [P] Write the seam's own unit tests in `tests/unit/test_order_vendors.py` — one `OrderVendor` per vendor, asserting the field values in `contracts/order-vendor.md`

### The seam

- [X] T008 Create the `OrderVendor` frozen dataclass and the DigiKey and McMaster values in `app/services/order_vendors.py` per `contracts/order-vendor.md`
- [X] T009 Merge `DigiKeyCaptureResult` and `McMasterCaptureResult` into one `OrderCaptureResult` in `app/models.py`, collapsing `lines_unenriched` and `lines_incomplete` into a single `lines_incomplete`

### The shared flow

- [X] T010 Collapse `_recorded_digikey_lines` and `_recorded_mcmaster_lines` into one vendor-parameterized pairing helper in `app/catalog_service.py`, preserving both passes — by `order_line_number` first, then by item id for purchases carrying none
- [X] T011 Collapse `_orphaned_digikey_purchases` and `_orphaned_mcmaster_purchases` into one helper in `app/catalog_service.py`; orphans stay **reported and never deleted**
- [X] T012 Collapse `_review_digikey_line` and `_review_mcmaster_line` into one per-line review in `app/catalog_service.py`, keeping the state order `CAPTURED → CONFLICT → MATCHED → NEW`
- [X] T013 Collapse `review_digikey_order` and `review_mcmaster_order` into `review_order(order, vendor)` in `app/catalog_service.py`
- [X] T014 Collapse `capture_digikey_order` and `capture_mcmaster_order` into one confirmation orchestration in `app/catalog_service.py`, keeping the whole-order write in **one session**
- [X] T015 Verify in `app/catalog_service.py` that enrichment is called **before** the write session opens, on both the review and the capture path — this ordering has been broken by a refactor once already (PR #116)
- [X] T016 Collapse `_apply_digikey_change` and `_apply_mcmaster_change` into one in `app/catalog_service.py`, keeping McMaster's operator-override behaviour and its changed/unchanged return

### Routes and templates

- [X] T017 Merge `app/templates/product/digikey_order_review.html` and `mcmaster_order_review.html` into `app/templates/product/order_review.html`, driven by `review_columns`
- [X] T018 Merge `app/templates/product/digikey_order.html` and `mcmaster_order.html` into `app/templates/product/order.html`
- [X] T019 Collapse `_digikey_decisions`/`_mcmaster_decisions` and `_digikey_capture_summary`/`_mcmaster_capture_summary` into one of each in `app/product/routes.py`
- [X] T020 Converge the two order-detail routes onto `GET /products/orders/<vendor>/<number>` in `app/product/routes.py`, redirecting the old DigiKey and McMaster addresses so FR-044 holds
- [X] T021 State the receiving rule once in `_receive_url` in `app/product/routes.py` per `contracts/routes.md`, **keeping DigiKey's existing landing exactly as it is**

### The gate

- [X] T022 Run the regression gate: `tests/unit/test_digikey_capture.py`, `test_digikey_receive.py`, `test_digikey_failures.py`, `test_digikey_client.py`, `test_mcmaster_capture.py`, `test_mcmaster_receive.py`, `test_mcmaster_routes.py`, `test_mcmaster_payload.py` must pass **unedited**
- [X] T023 Run the six existing e2e order files unedited — `tests/e2e/test_digikey_order.py`, `test_digikey_part.py`, `test_digikey_receive.py`, `test_mcmaster_order.py`, `test_mcmaster_product.py`, `test_mcmaster_receive.py`

**If T022 or T023 requires editing a test, stop.** The seam is in the wrong place; re-cut it
rather than adjusting the test (research.md §14, SC-011).

**Checkpoint**: One order flow, three vendors' worth of behaviour unchanged, nothing user-visible
moved.

---

## Phase 3: User Story 1 — Capture a whole Amazon order (Priority: P1) 🎯 MVP

**Goal**: One bookmarklet click on an Amazon order page captures every line as an outstanding
purchase, after a review that writes nothing.

**Independent Test**: Capture a known Amazon order from its order page, confirm the review, and
verify every included line became one outstanding purchase against a product carrying that line's
ASIN, with the quantity, unit price, order number and order date the page stated.

### Tests for User Story 1

- [ ] T024 [P] [US1] Payload parsing tests in `tests/unit/test_amazon_payload.py` — a good payload, a bad `version`, a wrong `vendor`, no order number, and **an empty `lines` with a valid order number, which must not be `None`**
- [ ] T025 [P] [US1] Capture tests in `tests/unit/test_amazon_capture.py` — one purchase per included line, exclusions, matched vs new products, re-capture writing nothing, and **two lines carrying the same ASIN pairing to their own purchases** (SC-005)
- [ ] T026 [P] [US1] E2E test in `tests/e2e/test_amazon_order.py` asserting the review lists **exactly the ordered lines** against `tests/e2e/fixtures/amazon_order.html` — the row count, not merely that some lines were read (research.md §4)
- [ ] T027 [P] [US1] E2E degraded tests in `tests/e2e/test_amazon_degraded.py` against the `amazon_order_unreadable.html` and `amazon_order_partial.html` fixtures, for FR-019, FR-021, FR-022 and FR-023

### Implementation for User Story 1

- [ ] T028 [US1] Change `pageKind` in `app/static/js/capture-agent.js` to take the location rather than `location.pathname`, updating every existing caller without changing any existing return value
- [ ] T029 [US1] Add the `amazon-order` dispatch case to `app/static/js/capture-agent.js` for path `/your-orders/order-details` carrying `orderID=`, and confirm `/your-orders/orders` does not match
- [ ] T030 [US1] Write the Amazon order reader in `app/static/js/capture-agent.js` per `contracts/capture-payload.md` — rows from `[data-component="purchasedItemsRightGrid"]`, **every field scoped to the row**, price from `.a-offscreen`, empty quantity meaning 1, `line_number` as the 1-based row index
- [ ] T031 [US1] Ensure no extraction step in the Amazon reader can throw, so a dead selector costs one field only (FR-021), and report `lines_read` so FR-004 can say "4 of 11"
- [ ] T032 [P] [US1] Add `AmazonOrder` and `AmazonOrderLine` to `app/models.py` per data-model.md §3, with `unit_price` parsed to `Decimal` and never `float`
- [ ] T033 [US1] Add the Amazon `OrderVendor` value to `app/services/order_vendors.py` — ASIN identifier, title as the suggested description, no enrichment, no line arithmetic, choice-page landing
- [ ] T034 [US1] Add the Amazon-order branch to `api_capture()` in `app/product/routes.py`, rendering the shared review and **writing nothing**
- [ ] T035 [US1] Add `POST /products/amazon/orders/capture` to `app/product/routes.py` — CSRF-protected, carrying the payload through the confirmation because there is nothing to re-read (FR-006)
- [ ] T036 [US1] Show on the review, in `app/templates/product/order_review.html`, that an Amazon line records only what the order page stated (FR-026)
- [ ] T037 [US1] Carry the incomplete-line report into the post-capture summary in `app/product/routes.py`, so the operator knows which records to look over after leaving the review (FR-022)

**Checkpoint**: An eleven-line Amazon order is captured in one click plus the descriptions. This
is the MVP — the issue's actual complaint is answered here.

---

## Phase 4: User Story 2 — Receive an Amazon order as the boxes turn up (Priority: P2)

**Goal**: Receive a captured order line by line from its order screen, since an Amazon package
names neither the order nor the line.

**Independent Test**: Capture an Amazon order, receive three of its lines from the order screen,
and verify each purchase is received with the quantity entered, the counted products' quantities
rose accordingly, and the screen reports the remainder as outstanding.

### Tests for User Story 2

- [ ] T038 [P] [US2] E2E test in `tests/e2e/test_amazon_receive.py` — receive from the order screen, amend a quantity, confirm a received line cannot be received twice
- [ ] T039 [P] [US2] Unit test in `tests/unit/test_order_receive.py` that receiving from the order screen has the same effect as receiving by any other route — quantity rises by the **received** amount, manual low/out flag cleared

### Implementation for User Story 2

- [ ] T040 [US2] Add a receive action per outstanding line to `app/templates/product/order.html`, with an editable quantity
- [ ] T041 [US2] Wire that action in `app/product/routes.py` to the existing `receive_purchase` service call — no second receiving implementation
- [ ] T042 [US2] Show the outstanding count and distinguish received from outstanding lines in `app/templates/product/order.html` (FR-028, FR-029)
- [ ] T043 [US2] Render an uncaptured order number as "not captured" with a way forward in `app/product/routes.py`, never a 404 (FR-032)

**Checkpoint**: A four-box Amazon order can be unpacked over a week, and what is still on its way
is visible throughout.

---

## Phase 5: User Story 3 — One place that lists what is on its way (Priority: P3)

**Goal**: The user-visible half of US3 — every captured order, across every vendor, on one
screen. (The other half was Phase 2.)

**Independent Test**: Capture one order from each vendor, open the list, and verify all three
appear with vendor, number, date and outstanding count, each opening an order screen that behaves
identically.

### Tests for User Story 3

- [ ] T044 [P] [US3] E2E test in `tests/e2e/test_orders_list.py` — orders from all three vendors listed, most recent first, a fully-received order visibly distinct from one with outstanding lines
- [X] T045 [P] [US3] Unit test in `tests/unit/test_orders_list.py` for the derived query — grouping, counts, and that a purchase with no `supplier_order_reference` appears in no order

### Implementation for User Story 3

- [X] T046 [US3] Add the derived captured-orders query to `app/catalog_service.py` per data-model.md §5 — grouped by `(vendor, supplier_order_reference)`, **no new table**
- [X] T047 [US3] Add `GET /products/orders` to `app/product/routes.py`
- [X] T048 [US3] Create `app/templates/product/orders.html` showing vendor, number, date, line count and outstanding count
- [X] T049 [US3] Add the list to the Products navigation dropdown in `app/templates/base.html` (FR-034)

**Checkpoint**: All three stories independently functional. Three vendors' open orders visible
from one screen without typing an order number.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T050 Regenerate documentation screenshots with `venv/bin/nox -s screenshots_headless`, then `screenshots_verify` — templates changed, and CI blocks merge on stale screenshots
- [ ] T051 Review the screenshot churn before committing; screenshots change every run, so commit what actually differs
- [ ] T052 [P] Update `README.md` and `docs/` to describe whole-order capture for all three vendors and the captured-orders list
- [ ] T053 [P] Confirm American spelling holds: `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing
- [ ] T054 [P] Confirm no `float` entered any price or quantity path introduced by this feature (Constitution III)
- [ ] T055 Run `venv/bin/nox -s tests` — full unit suite
- [ ] T056 Run `venv/bin/nox -s e2e` **detached** (`nohup … &` and poll) — it takes ~13m45s warm and exceeds the 10-minute bash cap
- [ ] T057 [P] Run `venv/bin/nox -s lint` — advisory; satisfy it for new code without reformatting existing files
- [ ] T058 Confirm `nox -s e2e` left the working tree clean
- [ ] T059 Walk `quickstart.md` end to end against a real Amazon order, a real DigiKey order and a real McMaster order
- [ ] T060 Record the outcome in `specs/029-whole-order-capture/verification.md`, including whether T005 was closed or deferred

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (fixtures)**: no dependencies. **Runs concurrently with Phase 2** — the consolidation needs no Amazon fixture.
- **Phase 2 (foundational)**: no dependencies. **Blocks Phases 3, 4 and 5** at T022/T023.
- **Phase 3 (US1)**: needs Phase 1 and Phase 2.
- **Phase 4 (US2)**: needs Phase 2; needs Phase 3 for an Amazon order to receive, though the order screen itself is vendor-neutral and testable against a DigiKey or McMaster order first.
- **Phase 5 (US3)**: needs Phase 2 only. **Independent of Phases 3 and 4** — it lists whatever orders exist.
- **Phase 6 (polish)**: needs every phase being shipped.

### Story dependencies

- **US1 (P1)**: after Phase 2. Independent of US2 and US3.
- **US2 (P2)**: after Phase 2. Fully demonstrable once US1 exists.
- **US3 (P3)**: its blocking half *is* Phase 2; its list half needs nothing further.

### Within each story

- Tests before implementation.
- Payload types before the service that consumes them.
- Service before route; route before template wiring.

### Parallel opportunities

- **T002–T005** — all fixture derivation, different files.
- **Phase 1 entirely in parallel with Phase 2**, which is the largest saving available here.
- **T007** alongside T006.
- **T024–T027** — all four US1 test files, different files.
- **T038/T039**, **T044/T045** — the US2 and US3 test pairs.
- **Phase 5 in parallel with Phases 3 and 4** once Phase 2 is green.
- **T052, T053, T054, T057** in polish.

Not parallel: **T010–T016** all edit `app/catalog_service.py`; **T028–T031** all edit
`app/static/js/capture-agent.js`; **T034, T035, T037** all edit `app/product/routes.py`.

---

## Parallel Example: Phase 1 alongside Phase 2

```
Developer A:  T001 → T002, T003, T004, T005      (fixtures; needs a browser)
Developer B:  T006 → T008 → T010…T016 → T017…T021 → T022, T023   (the consolidation)
```

## Parallel Example: User Story 1 tests

```
T024  tests/unit/test_amazon_payload.py
T025  tests/unit/test_amazon_capture.py
T026  tests/e2e/test_amazon_order.py
T027  tests/e2e/test_amazon_degraded.py
```

---

## Implementation Strategy

### MVP: Phases 1 + 2 + 3

Phase 2 delivers nothing visible but cannot be skipped without writing the third copy this
feature exists to avoid. Phase 3 is where the issue's complaint is actually answered — an
eleven-line Amazon order in one click instead of eleven captures.

### Incremental delivery

1. **Phases 1 + 2** — one order flow, no behaviour change. Shippable and worth shipping: it is a
   defect-surface reduction on code already in production.
2. **+ Phase 3** — Amazon capture. The MVP.
3. **+ Phase 4** — receiving, which makes the captured order useful rather than merely recorded.
4. **+ Phase 5** — the list, which is what makes three vendors manageable at once.

### If T005 cannot be closed

Ship anyway. The fallback is correct for quantity 1 and safe for anything else, because the
number is on the review and editable before a row is written. Record it as deferred in
`verification.md` and close it the next time a multi-quantity order is placed.

---

## Notes

- **T022/T023 is the load-bearing gate of this whole feature.** Two of the defects fixed in review of PR #123 were the McMaster copy of behaviour the DigiKey copy had already had corrected; the consolidation exists to make that impossible, and the existing tests are how we know it did not break anything on the way.
- **No Alembic revision.** Every column Amazon needs already exists (research.md §13). If a task seems to need one, re-read data-model.md §1 before writing it.
- **The row-scoping rule is the single most important line of the Amazon reader.** A document-wide ASIN sweep invents order lines out of Amazon's recommendations.
