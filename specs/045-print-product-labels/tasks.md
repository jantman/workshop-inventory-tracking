---

description: "Task list for feature 045: print labels for selected products from the All Products view"
---

# Tasks: Print labels for selected products from the All Products view

**Input**: Design documents from `specs/045-print-product-labels/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Required — not optional here. Constitution IV: "Changes that alter behavior MUST land with tests covering that behavior."

**Organization**: Grouped by user story. Phase 2 is a genuine blocker: it extracts the shared dialog that every story below depends on.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: US1 / US2 / US3, mapping to the user stories in spec.md

## Path Conventions

Single project, server-rendered Flask app. Templates in `app/templates/`, browser JS in
`app/static/js/`, tests in `tests/unit/` and `tests/e2e/`. **No backend source file is edited by any
task in this list** — see [research.md](./research.md) Decision 1.

Run everything through nox, from the main checkout's virtualenv, with Python 3.13 on PATH:

```bash
PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" /path/to/main/checkout/venv/bin/nox -s <session>
```

---

## Phase 1: Setup

**Purpose**: Establish the known-good baseline the Phase 2 refactor will be measured against.

- [X] T001 Run `nox -s e2e -- tests/e2e/test_bulk_label_printing_list.py tests/e2e/test_label_print.py` and record that both pass on the unmodified tree. These two modules are the regression net for the extraction; a failure discovered *after* Phase 2 is ambiguous unless it is known to have passed before.
- [X] T002 [P] Read `app/static/js/inventory-list.js` lines 139–300 and 528–630 and `app/templates/inventory/list.html` lines 199–266 together, so the extraction in Phase 2 is a move rather than a rewrite. Note every user-visible string — they are a contract per `contracts/bulk-label-print.md` §3.

**Checkpoint**: baseline green, existing implementation understood.

---

## Phase 2: Foundational — extract the shared bulk print dialog (BLOCKING)

**Purpose**: Turn the inventory list's inline dialog into a shared component, with its behaviour
provably unchanged. Nothing in Phase 3+ can be built until this is done, because the products page
is a *consumer* of what this phase creates.

**⚠️ FR-014 is the constraint on this whole phase**: the inventory list must behave exactly as it
does today, down to its element ids and its user-visible strings.

- [X] T003 Create `app/templates/_bulk_label_modal.html` defining the Jinja macro `bulk_label_modal(modal_id, prefix, noun, noun_plural)`. Emit exactly the element ids listed in `contracts/bulk-label-print.md` §3, each as `{{ prefix }}-...`. Port the markup verbatim from `app/templates/inventory/list.html:199-266`, **including** the comment explaining why `{{ prefix }}-print-errors` sits outside the progress region (a refused count is reported before any run starts).
- [X] T004 Replace the inline modal block in `app/templates/inventory/list.html` (lines 199–266) with `{% from "_bulk_label_modal.html" import bulk_label_modal %}` and `{{ bulk_label_modal('listBulkLabelPrintingModal', 'list-bulk', 'item', 'items') }}`. Diff the rendered HTML before and after — ids, classes and visible text must be identical.
- [X] T005 Create `app/static/js/bulk-label-print.js` defining `class BulkLabelPrintDialog` per `contracts/bulk-label-print.md` §3, assigned to `window.BulkLabelPrintDialog`. A plain global, **not** an ES module — `inventory-list.js` is loaded with `type="module"` and the products script will not be, which is the same reason `label-count.js` documents for itself. Move `init()`, `open(entries)`, `loadLabelTypes()`, `reset()` and `printAll()` across from `inventory-list.js`, parameterizing only: element id prefix, `noun`/`nounPlural` in the strings, `entry.label` as the display text, and `printOne(entry, labelType, labelCount)` as what performs the request.
- [X] T006 In `bulk-label-print.js`, preserve these four invariants from the source, each with the comment that explains it: (a) the count is read via `window.readLabelCount` **before** anything prints, so a refusal prints nothing at all; (b) a stale warning is cleared at the start of every run; (c) a failure never aborts the loop; (d) the reported total is `successCount * labelCount`, because one entry's copies are one `lp` job with one exit code and the total must never claim more labels than emerged.
- [X] T007 In `bulk-label-print.js`'s `reset()`, restore `progress-bar-animated` on the progress bar. `printAll()` removes it at the end of a run and the current `resetBulkPrintModal()` never puts it back, so today a dialog reopened after a run shows a dead bar. This is a one-line fix to a state-reset bug the extraction surfaces; note it in the PR body so it is not mistaken for scope creep.
- [X] T008 Add `<script src="{{ url_for('static', filename='js/bulk-label-print.js') }}"></script>` to `app/templates/inventory/list.html`'s scripts block, **before** the `inventory-list.js` module tag and after `label-count.js`.
- [X] T009 Rewrite the bulk-print section of `app/static/js/inventory-list.js` to delegate: construct one `BulkLabelPrintDialog` with `{modalId: 'listBulkLabelPrintingModal', prefix: 'list-bulk', noun: 'item', nounPlural: 'items', printOne: ...}` whose `printOne` does the existing `fetch('/api/labels/print', {ja_id: entry.id, label_type, label_count})`. Delete the now-duplicated `initializeBulkPrintModal`, `onLabelTypeChange`, `onBulkPrintModalClose`, `showBulkLabelPrintingModal`, `loadLabelTypes`, `resetBulkPrintModal` and `printAllLabels`. Keep `printLabelsForSelected()` — including its empty-selection `alert()` — and have it call `open(jaIds.map(id => ({id, label: id})))`.
- [X] T010 **Gate**: run `nox -s e2e -- tests/e2e/test_bulk_label_printing_list.py` and require a pass with the test file **unedited**. If it needs editing, the extraction changed behaviour — fix `bulk-label-print.js`, not the test.

**Checkpoint**: the inventory list is unchanged to a user, and a reusable dialog now exists.

---

## Phase 3: User Story 1 — print labels for several products in one pass (Priority: P1) 🎯 MVP

**Goal**: Tick product rows, choose a stock and a copy count once, get the labels.

**Independent test**: with several products present, tick two or more rows, open the dialog, choose a
stock, confirm, and verify one label per ticked product carrying that product's own content.

- [X] T011 [US1] In `app/templates/product/search.html`, add a leading `<th>` to the table header holding the select-all checkbox `id="product-select-all"`, and a leading `<td>` to each row holding `<input type="checkbox" class="form-check-input product-checkbox" data-product-id="{{ product.id }}" data-product-label="{{ product.description }}">`. Bump `#no-products`'s `colspan` from 5 to 6.
- [X] T012 [US1] In the same file, add `class="product-description"` to the description `<td>`, so tests and CSS can address it by name rather than by position.
- [X] T013 [US1] In the same file's `page_actions` block, add a **Print Labels** button `id="product-print-labels-btn"`, disabled, carrying a count badge `<span id="product-selected-count">0</span>` (FR-001, FR-004).
- [X] T014 [US1] In the same file, import the macro and call `{{ bulk_label_modal('productBulkLabelPrintingModal', 'product-bulk', 'product', 'products') }}`.
- [X] T015 [US1] In the same file's scripts block, add `label-count.js`, `bulk-label-print.js` and `product-list-labels.js`, in that order. `csrf.js` needs no tag — `base.html` already loads it globally.
- [X] T016 [US1] Create `app/static/js/product-list-labels.js`. On `DOMContentLoaded`, bail out if `#product-table` is absent. Construct a `BulkLabelPrintDialog` with `{modalId: 'productBulkLabelPrintingModal', prefix: 'product-bulk', noun: 'product', nounPlural: 'products'}` and a `printOne` that calls `csrfFetch('/api/products/' + entry.id + '/label', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({label_type: labelType, label_count: labelCount})})`. **`csrfFetch`, not `fetch`** — unlike the item endpoint, this one is not `@csrf.exempt`.
- [X] T017 [US1] In `product-list-labels.js`, derive the selection by reading `input.product-checkbox:checked` from the DOM at the moment it is needed; do not keep a `Set`. Map each to `{id: cb.dataset.productId, label: cb.dataset.productLabel}`. Wire `#product-print-labels-btn` to `open(entries)`. This is also what delivers FR-015 for free: a filtered-out product has no checkbox, so it cannot be selected — record that reasoning in a comment.
- [X] T018 [P] [US1] Update the three column-position selectors broken by the new first column: `tests/e2e/test_product_search.py:46` and `:144`, and `tests/e2e/test_product_specifications.py:57`. Change `#product-table tbody tr td:first-child a` to `#product-table tbody tr td a` — the row has exactly one anchor, and that is the form the suite's other `#product-table` selectors already use.
- [X] T019 [P] [US1] Add a unit test to `tests/unit/test_product_routes.py` asserting that `GET /products` renders the checkbox column, the select-all control, the Print Labels button and the bulk dialog — a cheap guard against a template edit silently removing the entry point.
- [X] T020 [US1] Create `tests/e2e/test_bulk_label_printing_products.py`. Seed products through `live_server.add_test_data([...])`, not the Add Product form — the form costs ~3s per product and is not what is under test. Add a request-capture fixture on `**/api/products/*/label`, modelled on `tests/e2e/test_bulk_label_printing_list.py:448`.
- [X] T021 [US1] In that module, test the happy path: tick two rows, open the dialog, choose a stock, print, and assert one POST per product carrying that product's id. Waits per `quickstart.md` — `waits.wait_for_modal_shown`, `waits.wait_for_select_populated('product-bulk-label-type')`, then `expect(done_btn).to_be_visible()` for completion, because the Done button is revealed only after the loop's last `await`.
- [X] T022 [P] [US1] Test that a copy count of 4 across 3 products produces 12 labels: assert 3 POSTs each carrying `label_count: 4`, and a completion line reading `Complete: 12 labels for 3 products, 0 failed` (SC-002).
- [X] T023 [P] [US1] Test that all six stocks are offered, mirroring the existing assertion in `tests/e2e/test_label_print.py` (FR-005, SC-006).
- [X] T024 [P] [US1] Test that a refused count prints nothing: set the count to `0`, print, then assert **both** that the error region is visible **and** that the progress region is still hidden, and only then that zero requests were captured. The warning alone does not prove nothing printed (FR-007, SC-005).
- [X] T025 [P] [US1] Test that the print action is unavailable with nothing ticked — `expect(btn).to_be_disabled()`, a positive assertion that polls, never `not_to_be_enabled()` on an element the handler has never touched (FR-004).
- [X] T026 [P] [US1] Test that the dialog resets on reopen: after a run, close, reopen, and assert `#product-bulk-label-count` has value `1` and the progress region is hidden (FR-013).

**Checkpoint**: the issue's request is delivered and independently demonstrable.

---

## Phase 4: User Story 2 — select and deselect without losing track (Priority: P2)

**Goal**: A select-all control with a real three-state presentation, and a visible count.

**Independent test**: tick rows individually and via select-all, confirm the count matches, and
confirm clearing empties it. No printing involved.

- [X] T027 [US2] In `app/static/js/product-list-labels.js`, update `#product-selected-count` and the disabled state of `#product-print-labels-btn` on every checkbox `change` (FR-001).
- [X] T028 [US2] In the same file, wire `#product-select-all` to check or uncheck every `input.product-checkbox` (FR-002).
- [X] T029 [US2] In the same file, maintain the select-all control's three states after any change: `checked` when all are ticked, `indeterminate` when some are, neither when none are (FR-003). `indeterminate` is a property, not an attribute — set `el.indeterminate`.
- [X] T030 [P] [US2] In `tests/e2e/test_bulk_label_printing_products.py`, test select-all ticking every listed row and the count matching the row count.
- [X] T031 [P] [US2] Test that select-all on a fully-selected list clears the selection and disables the print action.
- [X] T032 [P] [US2] Test the partially-selected state: tick one of three and assert `#product-select-all` is neither checked nor unchecked but indeterminate, read via `evaluate` on the property.
- [X] T033 [P] [US2] Test FR-015: seed four products, apply a filter that lists two, tick both, and assert the count reads `2` — no unlisted product is selected or counted.
- [X] T034 [P] [US2] Test that a products list with no rows offers nothing to print — establish `#no-products` first, then assert the print action is disabled.

**Checkpoint**: selection behaves like the items list.

---

## Phase 5: User Story 3 — know what happened when a label fails (Priority: P2)

**Goal**: A partial failure is visible and named, and does not take the rest of the run with it.

**Independent test**: make one product's label fail; confirm the dialog names it, reports the reduced
count, and that the others still printed.

The behaviour itself arrives with Phase 2 — this phase proves it on the products page.

- [X] T035 [P] [US3] In `tests/e2e/test_bulk_label_printing_products.py`, test a partial failure: select five products and make one POST fail (Playwright route interception returning a 500 with `{"success": false, "error": ...}`). Assert four successes, the failing product **named by its description** in the error region, and that the other four POSTs were still made (FR-011, FR-012, SC-004).
- [X] T036 [P] [US3] Test the progress line during a run: assert `#product-bulk-print-status` matches `Printing \d+ of 3: ` while the run is in flight, and that above a count of 1 it carries the `(N labels)` suffix (FR-010).
- [X] T037 [P] [US3] Test that a run in which every product fails reports zero labels rather than appearing to succeed — the printer-unavailable edge case.

**Checkpoint**: failures are honest.

---

## Phase 6: Polish & Cross-Cutting

- [X] T038 Add a "printing labels for several products at once" subsection to `docs/user-manual.md` under **Printing Product Labels** (around line 2026, where the 99-copy limit is already described), and cross-reference it from the bulk inventory label section near line 254. Use American spelling — `catalog`, never `catalogue`.
- [X] T039 Run `nox -s tests`. Expect sub-second; no new unit test here is slow.
- [X] T040 Run `nox -s e2e` in full, **detached** — the suite runs ~20 minutes warm and will blow a 10-minute agent bash timeout: `nohup env PATH=... nox -s e2e > /tmp/e2e.log 2>&1 &`, then poll. Confirm the working tree is still clean afterwards; an e2e run that dirties it violates Constitution IV.
- [X] T041 Run `nox -s screenshots_headless` then `nox -s screenshots_verify`. `app/templates/**` and `app/static/js/**` changed, so this is required by the constitution's workflow gates.
- [X] T042 Review the screenshot diff before staging. Screenshots churn between runs for reasons unrelated to any change — commit the products-list image, which legitimately gains a column and a button, and only whatever else this change actually explains.
- [X] T043 [P] Confirm `nox -s lint` is no worse than before on the files touched. Advisory, not a gate; do not mass-reformat existing files, which destroys review signal.
- [X] T044 Re-read the diff against the spec's FR list, and specifically confirm FR-014: `tests/e2e/test_bulk_label_printing_list.py` and `tests/e2e/test_label_print.py` are unedited, and `inventory/add.html`, `inventory/search.html` and `product/detail.html` are untouched.

---

## Dependencies

```
Phase 1 (T001-T002)
   ↓
Phase 2 (T003-T010)  ← BLOCKING: creates what every story below consumes
   ↓
   ├─→ Phase 3 / US1 (T011-T026)  🎯 MVP — ships alone
   │      ↓
   │   Phase 4 / US2 (T027-T034)  — needs US1's checkbox column and JS file
   │      ↓
   │   Phase 5 / US3 (T035-T037)  — needs US1's e2e module and fixtures
   ↓
Phase 6 (T038-T044)
```

**Within Phase 2**: T003 → T004; T005 → T006 → T007 → T009; T008 anywhere before T010; T010 last.

**Within Phase 3**: T011–T015 all edit `product/search.html`, so they are sequential. T016 → T017.
T018 and T019 are independent of everything. T020 must precede T021–T026.

**Story independence**: US1 is a complete, shippable increment on its own — per-row ticking plus the
dialog. US2 and US3 refine it and depend on its files, which is why they are sequenced rather than
parallel. That ordering is a file-level dependency, not a functional one.

## Parallel Opportunities

- **T018 ‖ T019** — different files, no dependency on each other.
- **T022 ‖ T023 ‖ T024 ‖ T025 ‖ T026** — all add independent test functions to the same module once
  T020 has created it and T021 has settled the helper shape.
- **T030 ‖ T031 ‖ T032 ‖ T033 ‖ T034** — likewise.
- **T035 ‖ T036 ‖ T037** — likewise.
- **T038 ‖ T043** — docs and lint touch nothing else.

The build tasks themselves largely are not parallelizable: T011–T015 all edit one template, and
T005–T009 are one continuous extraction.

## Implementation Strategy

**MVP is Phase 2 + Phase 3.** That is the issue's actual request — tick rows, pick a size and a
count, print — and it is shippable without US2 or US3.

**Phase 2 is where the risk lives**, not Phase 3. It moves working, well-tested code; T010 is the
gate that says whether the move was faithful. Do not start Phase 3 until T010 passes with an unedited
test file. If T010 fails, the fault is in `bulk-label-print.js`.

**Phase 3 is nearly all template work** plus one small JS file, because Phase 2 already built the
hard part and the backend was already complete.

**Do not let the shared dialog grow.** Its parameter list is four entries. If a Phase 3 task seems to
need a fifth, that is a signal the products page should adapt to the dialog, not the other way
round — and the three out-of-scope dialogs (`inventory/add.html`, `inventory/search.html`,
`product/detail.html`) stay out of scope regardless.
