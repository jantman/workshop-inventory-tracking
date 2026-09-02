---

description: "Task list for feature 036: manage product identifiers after creation"
---

# Tasks: Manage Product Identifiers After Creation

**Input**: Design documents from `/specs/036-manage-product-identifiers/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/identifiers.md](./contracts/identifiers.md),
[quickstart.md](./quickstart.md)

**Tests**: **Required, not optional.** Constitution IV: "Changes that alter behavior MUST land
with tests covering that behavior," and `nox -s tests` and `nox -s e2e` must pass before merge.
Test tasks are written before the implementation they cover within each phase.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — **different file**, no dependency on an incomplete task
- **[Story]**: US1 / US2 / US3, mapping to the user stories in spec.md

## Path Conventions

Server-rendered Flask app, existing layout kept as-is: `app/` for source, `tests/unit/` and
`tests/e2e/` for tests, `docs/` for the manual. No `src/`, no frontend build.

**Note on `[P]` in this feature**: most of the work lands in four files
(`detail.html`, `product-identifiers.js`, and one test file each side). Tasks touching the same
file are never marked `[P]`, which is why parallelism here is narrow and mostly test-vs-code.

---

## Phase 1: Setup

**Purpose**: Establish the baseline before anything changes.

- [X] T001 Record a green baseline over `tests/unit/`: run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` from the repository root and confirm it passes before editing anything

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The single type vocabulary and the card scaffolding that all three stories build on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Add `OPERATOR_IDENTIFIER_TYPES` to `app/models.py` beside `IdentifierType` (line 402), derived from the enum with `INTERNAL` excluded, with a comment naming why `INTERNAL` is out — it is generated, never typed
- [X] T003 Pass `identifier_types=OPERATOR_IDENTIFIER_TYPES` at the three `render_template` call sites in `app/product/routes.py` — lines 253 and 325 (`product/add.html`) and line 349 (`product/detail.html`) — importing the constant alongside the existing `app.models` imports (depends on T002)
- [X] T004 Replace the hardcoded `['MPN', 'GTIN', 'VENDOR', 'DISTRIBUTOR']` literal at `app/templates/product/add.html:50` with the passed `identifier_types` (depends on T003)
- [X] T005 [P] Add `tests/unit/test_product_identifiers.py` with the first test: `OPERATOR_IDENTIFIER_TYPES` excludes `INTERNAL` and contains every other `IdentifierType` member, so a fifth type added later cannot silently miss the UI (depends on T002)
- [X] T006 [P] Restructure the identifier rows in `app/templates/product/detail.html` (list at line 394): add class `identifier-row` to each `<li>` and `identifier-value` to the value span, and add an empty `<div id="identifier-alerts">` above the list, per the DOM contract in `contracts/identifiers.md`
- [X] T007 Create `app/static/js/product-identifiers.js` with the IIFE skeleton matching `product-stock.js`, a `showAlert(message, extraHtml)` helper writing into `#identifier-alerts`, and a `messageFrom(data)` helper returning `data.error || data.message || <fallback>`; register the file in the `{% block scripts %}` of `app/templates/product/detail.html` (depends on T006)

**Checkpoint**: The card renders with stable hooks, the type list has one source, and the JS module loads. No behavior has changed yet.

---

## Phase 3: User Story 1 - Make an already-cataloged product scannable (Priority: P1) 🎯 MVP

**Goal**: An operator can add an identifier — a `GTIN` above all — to an existing product from
its detail page, and the product is then found by that code.

**Independent Test**: Seed a product with no `GTIN`, add `687117723741` from the Identifiers
card, confirm the card shows `00687117723741`, then type that UPC into the header scan box and
land on that product.

### Tests for User Story 1

- [X] T008 [P] [US1] Extend `tests/unit/test_product_identifiers.py` with the POST contract from `contracts/identifiers.md`: 201 storing the normalized 14-digit key; 400 for a bad check digit; 201 with `override` storing `validation_overridden` true; 400 for an all-zero read **both with and without** `override`; 409 carrying `owning_product_id`; 404 for a missing product asserting the message arrives under the **`message`** key, not `error`; and a repeat add of the same value leaving exactly one row
- [X] T009 [P] [US1] Create `tests/e2e/test_product_identifiers.py` seeding through `live_server.add_test_products`, with the happy path: open the detail page, reveal the form, add a valid UPC as `GTIN`, and `expect` the `.identifier-row` count to rise and `.identifier-value` to read the normalized key
- [X] T010 [US1] Add the scan-back test to `tests/e2e/test_product_identifiers.py`, reusing the `scan()` shape from `tests/e2e/test_wedge_scan.py:33` — type the UPC into `#global-scan-input`, press Enter, and `expect` the URL to be that product's detail page (SC-002) (same file as T009)
- [X] T011 [US1] Add the refusal tests to `tests/e2e/test_product_identifiers.py`: a bad check digit refused with the reason in `#identifier-alerts` and the typed values still in the inputs; the same value accepted with the override ticked and the row showing "Validation overridden"; an all-zero read refused; a value owned by another product refused with that product named and linked (same file as T009, T010)

### Implementation for User Story 1

- [X] T012 [US1] Add the add-identifier form to the Identifiers card in `app/templates/product/detail.html`: `#add-identifier-btn` toggling `#add-identifier-form` with `data-bs-toggle="collapse"` (markup only, no JS toggle), containing `#new-identifier-type` rendered from `identifier_types`, `#new-identifier-value` (`maxlength="128"`), `#new-identifier-vendor` (`maxlength="200"`) with the "Required for vendor and distributor identifiers" hint, `#new-identifier-override`, and `#save-identifier-btn` — laid out so the page does not scroll sideways at 390px
- [X] T013 [US1] Implement the save handler in `app/static/js/product-identifiers.js`: read the four inputs, `csrfFetch` POST to `/api/products/<id>/identifiers`, `window.location.reload()` on success, and on refusal render `messageFrom(data)` into `#identifier-alerts` **without** reloading and without clearing the inputs (depends on T012)
- [X] T014 [US1] Handle the 409 in `app/static/js/product-identifiers.js` by appending a link to `/products/<owning_product_id>` to the alert, so the operator can go and look rather than guess (depends on T013)

**Checkpoint**: US1 is complete and demonstrable on its own. The reported defect in #136 is fixed at this point — the remaining stories add removal and the non-barcode types.

---

## Phase 4: User Story 2 - Remove an identifier that is wrong (Priority: P2)

**Goal**: Each listed identifier can be detached, after a confirmation, without touching the
product.

**Independent Test**: Give a product two identifiers, remove one, confirm the other survives a
reload; remove the last one and confirm the product still exists showing its internal code.

### Tests for User Story 2

- [X] T015 [P] [US2] Extend `tests/unit/test_product_identifiers.py` with the DELETE contract: 204 on the first removal; a repeat removal answering **404 with a JSON body** (the #132 behavior this relies on); 404 when the identifier belongs to a different product; and the product still present with its `internal_code` after its last identifier is removed
- [X] T016 [US2] Add the removal tests to `tests/e2e/test_product_identifiers.py`: removing one of two rows leaves the other; declining the `window.confirm` removes nothing; the last row can be removed and `#internal-code` survives; and the internal code block carries no `.remove-identifier-btn` (same file as T009-T011; establish the list with a positive `expect` before asserting any row is absent)
- [X] T017 [P] [US2] Add the per-row remove control to `app/templates/product/detail.html`: a `.remove-identifier-btn` carrying `data-identifier-id` inside each `.identifier-row`, and none anywhere in the internal-code block
- [X] T018 [US2] Implement the remove handler in `app/static/js/product-identifiers.js`: `window.confirm` first and a decline does nothing at all; `csrfFetch` DELETE; treat `response.ok || response.status === 404` as success and reload, citing the same reasoning as `product-attachments.js:106`; anything else renders an alert without reloading (depends on T017)

**Checkpoint**: Add and remove both work. A mistyped identifier from US1 is now correctable.

---

## Phase 5: User Story 3 - Record an identifier learned after the fact (Priority: P3)

**Goal**: `MPN`, `VENDOR` and `DISTRIBUTOR` identifiers can be added too, with the vendor
requirement enforced and reported.

**Independent Test**: Add an `MPN` and see it listed; attempt a `VENDOR` with no vendor and see
it refused naming the vendor field; supply the vendor and see the row with its vendor beneath.

**Note on implementation tasks**: this story needs **no new implementation** — the form built in
T012 already carries the vendor input and the type select, and the refusal rendering built in
T013 already covers FR-008, because the server enforces all of it (see `data-model.md`, "Rules,
and where each one already lives"). The tasks here are the tests that prove it, plus the
cross-page parity check FR-003 asks for. Inventing implementation work here would mean
duplicating a rule the service already owns.

### Tests for User Story 3

- [X] T019 [P] [US3] Extend `tests/unit/test_product_identifiers.py`: an `MPN` stored as typed; `VENDOR` and `DISTRIBUTOR` refused with 400 naming the vendor field when no vendor is given; the same add with a vendor returning 201 and storing that vendor
- [X] T020 [US3] Add the vendor-scoped tests to `tests/e2e/test_product_identifiers.py`: `#new-identifier-type` offers exactly `MPN`, `GTIN`, `VENDOR`, `DISTRIBUTOR` and not `INTERNAL`; a `VENDOR` add with no vendor refused with the typed values retained; the same add with a vendor listed with its vendor shown beneath the value (same file as T009-T011, T016)
- [X] T021 [US3] Add the FR-003 parity test to `tests/e2e/test_product_identifiers.py`: read the options of `#identifier_type` on `/products/new` and of `#new-identifier-type` on a product detail page and assert the two lists are equal — this is the test that would catch the two lists drifting apart again (same file as T020)

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T022 [P] Update the Product Identifiers section of `docs/user-manual.md` (starting line 947) to say where an identifier is added and removed after creation, and confirm the existing promise at line 1272 — "Add it by hand from the product's **Identifiers** card" — is now true rather than aspirational
- [X] T023 [P] Run `tests/e2e/test_touch_readiness.py` on its own and confirm `test_the_page_does_not_scroll_sideways_on_a_phone` still passes with the new form and buttons in the narrow column
- [X] T024 Run the full unit suite including the new `tests/unit/test_product_identifiers.py`: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`
- [X] T025 Run the e2e suite **detached**, covering the new `tests/e2e/test_product_identifiers.py` — `nohup env PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &` — and poll the log; budget 20 minutes, and do not run it in the foreground where a 10-minute tool cap reports a false timeout on a passing run
- [X] T026 Regenerate screenshots (`venv/bin/nox -s screenshots_headless`), run `venv/bin/nox -s screenshots_verify`, inspect `git status --short docs/images/screenshots/` and commit only genuinely changed captures — `user-manual/product_detail.png` is this card and genuinely changes; the rest churn per run (measured by running the session twice) and are reverted; also confirm `nox -s e2e` left the working tree clean
- [X] T027 [P] Run `venv/bin/nox -s lint` and clear findings in the files this feature touched only — no mass reformatting of existing files
- [ ] T028 Walk the by-hand checks in [quickstart.md](./quickstart.md), including the SC-002 pass on product 4, 6 or 8 that closes the fourth GS1 verification vector inherited from #80 §3

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: no dependencies.
- **Foundational (T002-T007)**: after Setup. **Blocks all user stories** — every story needs the alerts region, the row hooks and the JS module.
- **US1 (T008-T014)**: after Foundational. No dependency on US2 or US3.
- **US2 (T015-T018)**: after Foundational. Independent of US1 in code; its e2e file is created by T009, so run US1's test tasks first if working strictly sequentially.
- **US3 (T019-T021)**: after Foundational **and** T012/T013, because it tests the form and refusal rendering those tasks build. This is the one genuine cross-story dependency and it is stated rather than hidden.
- **Polish (T022-T028)**: after every story to be shipped is done.

### Within Each Story

- Tests are written before the implementation they cover.
- Template hooks before the JS that binds to them (T012 → T013, T017 → T018).
- `contracts/identifiers.md` is the arbiter for every status code and JSON key.

### Parallel Opportunities

Narrow by design — four files carry most of the work:

- **T002 and T006** — `app/models.py` and `app/templates/product/detail.html`, no overlap.
- **T005** with T003/T004 — the new unit test file against the routes and the add form.
- **T008 and T009** — unit file and e2e file, the two sides of US1's tests.
- **T012** with T008/T009 — the form markup while the tests are being written.
- **T015 and T017** — US2's unit tests and its template change.
- **T019** with T020 is *not* parallel-safe with T021 (same e2e file); T019 alone is.
- **T022, T023, T027** — docs, the touch check and lint are mutually independent.

Everything in `tests/e2e/test_product_identifiers.py` (T009, T010, T011, T016, T020, T021) is one
file and must be sequential.

---

## Parallel Example: User Story 1

```bash
# The two test files, written side by side:
Task: "Extend tests/unit/test_product_identifiers.py with the POST contract"   # T008
Task: "Create tests/e2e/test_product_identifiers.py with the happy path"       # T009

# And the markup, which neither test file touches:
Task: "Add the add-identifier form to app/templates/product/detail.html"       # T012
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. T001 — baseline green.
2. T002-T007 — foundational.
3. T008-T014 — US1.
4. **STOP and VALIDATE**: seed a product, add a UPC, scan it back. That is #136's reported
   defect fixed and SC-002 demonstrable.

### Incremental Delivery

1. Foundation → nothing user-visible has changed.
2. **+ US1** → an identifier can be added; a pre-2026-08-17 product can be made scannable. **MVP.**
3. **+ US2** → it can also be removed, so a mistake in US1 is correctable.
4. **+ US3** → the non-barcode types are covered and FR-003 parity is pinned.
5. Polish → docs, screenshots, the full suites, the by-hand pass.

### On working this solo

The Parallel Team Strategy in the template does not apply — this is a single-maintainer project
and the phases are small. Run them in order; the `[P]` markers are there to say what may be
safely interleaved, not to imply staffing.

---

## Notes

- `[P]` = different file, no incomplete dependency.
- **No migration, no schema change, no new service method or route.** If a task seems to need
  one, re-read `data-model.md` — the rule almost certainly already exists in `CatalogService`.
- E2E waits are `expect()` only. No `wait_for_timeout`, no `time.sleep`, no
  `wait_for_load_state("networkidle")`. Both mutating paths end in a reload, so
  `CLAUDE.md` pattern **C** applies: the rendered row cannot predate the completed request.
- Negative e2e assertions ("the row is gone", "no remove button on the internal code") must
  follow a positive `expect()` that establishes the region first, or they pass against a page
  that has not rendered.
- Seed with `live_server.add_test_products`; drive the Add Product form only in T021, where that
  form is the subject.
- Commit per task or per logical group; the branch merges by PR.
