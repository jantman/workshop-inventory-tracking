---

description: "Task list for Label Print Count (issue #86)"
---

# Tasks: Label Print Count

**Input**: Design documents from `/specs/013-label-print-count/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/labels-print-api.md](./contracts/labels-print-api.md), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are **included and not optional here**. Constitution Principle IV: "Changes that
alter behavior MUST land with tests covering that behavior, and `nox -s tests` and `nox -s e2e` MUST
pass before a change is merged." Coverage percentage is explicitly not a target — write the test that
would catch the regression, and stop.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: US1 / US2 / US3, mapping to the user stories in spec.md
- Exact file paths are in every task

## Path Conventions

Existing Flask layout, unchanged: `app/` for source, `tests/unit/` and `tests/e2e/` for tests. No new
directory. One new file (`app/static/js/label-count.js`); everything else is a modification.

**Before any command that needs project dependencies**: `source venv/bin/activate`.

---

## Phase 1: Setup

**Purpose**: Establish the baseline. There is genuinely nothing to scaffold — no new dependency, no
new directory, no schema, no migration.

- [X] T001 Record the pre-change baseline: run `nox -s tests` and confirm green, and confirm `nox -s lint` is already red on pre-existing E501s so its failures are not attributed to this work later

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The endpoint must accept a label count and the shared browser helper must exist before
any dialog can send one.

**⚠️ CRITICAL**: No user story can be completed until this phase is done. All three dialogs post to
the same endpoint and all three call the same helper.

- [X] T002 [P] In `app/services/label_printer.py`, rename the existing `num_copies` parameter of `generate_and_print_label()` to `label_count` (5 references, all within this file), and add `label_count: int = 1` to `print_label_for_ja_id()`, forwarding it into the `label_config` passed to `generate_and_print_label()`. Leave the body's `[image] * n` logic and the test-mode short-circuit exactly as they are — per research.md Decision 1, do **not** switch to `lp -n N`
- [X] T003 [P] Create `app/static/js/label-count.js` exposing `window.readLabelCount(inputId)` returning `{ok: true, value}` / `{ok: false, error}` per the markup contract in `contracts/labels-print-api.md` §3: whole numbers 1–99 accepted, everything else refused with `Label count must be a whole number between 1 and 99`, and a missing element yielding `{ok: true, value: 1}`
- [X] T004 In `app/main/routes.py`, extend `POST /api/labels/print` (line 1774) to read `label_count` from the body, default it to `1` when absent, and reject non-integers and out-of-range values with 400 and the exact messages in `contracts/labels-print-api.md` §1. Run the new validation **after** the existing ja_id and label_type checks. Reject `bool` explicitly — `isinstance(True, int)` is `True` in Python. Pass the count to `print_label_for_ja_id()` and echo it in the success response (depends on T002)
- [X] T005 In `tests/unit/test_label_printer.py`, update `test_print_label_endpoint_success` — its `mock_print.assert_called_once_with('JA123456', 'Sato 1x2')` is positional and will fail once the route passes a count. Updating it is the correct outcome, not a workaround. Then add route tests covering: `label_count` absent → service called with `1`; valid `3` → forwarded and echoed in the response; `0`, `100`, `-1`, `2.5`, `"3"`, `null`, `true` → 400 with the contract's message (depends on T004)
- [X] T006 In `tests/unit/test_label_printer.py`, add service-level tests asserting that `generate_and_print_label(..., label_count=n)` results in exactly one `LpPrinter.print_images()` call receiving a list of length `n`, patching `LpPrinter` as the existing `test_generate_and_print_label_production_mode` does. Add a test that `print_label_for_ja_id(ja_id, label_type, 4)` threads the count through. **No test may reach the real `print_images()`** — it drives hardware (depends on T002, T005)

**Checkpoint**: The endpoint accepts and enforces a label count, the service produces N images, and
the browser helper exists. `nox -s tests` is green. No dialog sends a count yet, and every existing
dialog still works because the field is optional.

---

## Phase 3: User Story 1 - Print several copies of one item's label (Priority: P1) 🎯 MVP

**Goal**: A label count on the single-item print dialog, reachable from both the Add Item and Edit
Item forms.

**Independent Test**: Open the print dialog from the Add Item form, set the count to 3, pick a label
type, print. The request carries `label_count: 3` and the success message names three labels.
Reopening the dialog shows `1` again while the label type is still remembered.

### Implementation for User Story 1

- [X] T007 [US1] In `app/static/js/label-printing-modal.js`, add the label count field to `createModalHTML()` below the label type select: `<input type="number" id="label-count" min="1" max="99" step="1" value="1">` labeled **"Number of labels"** (FR-014), and reset it to `1` in `show()` — the Bootstrap modal is reused rather than recreated, so the markup default only covers the first open (FR-002)
- [X] T008 [US1] In `app/static/js/label-printing-modal.js`, wire `handlePrintLabel()`: call `window.readLabelCount('label-count')` before the fetch, render `error` through the existing `showError()` into `#label-print-alerts` and return without sending when it fails, include `label_count` in the POST body, and word the success message as today's `Label printed successfully for {ja_id}` at a count of 1 and `{n} labels printed successfully for {ja_id}` above 1 (depends on T007)
- [X] T009 [P] [US1] In `app/templates/inventory/add.html`, add `<script src="{{ url_for('static', filename='js/label-count.js') }}"></script>` before the existing `label-printing-modal.js` tag at line 383
- [X] T010 [P] [US1] In `app/templates/inventory/edit.html`, add the same `label-count.js` script tag before the `label-printing-modal.js` tag at line 432
- [X] T011 [US1] In `tests/e2e/test_label_printing.py`, add tests covering spec Story 1 scenarios 1–5: the input defaults to 1; a default-count print still sends one label; a count of 3 reaches the request body as `label_count: 3`; reopening resets to 1 while the label type persists; and `0` / `100` / `2.5` / empty are refused with a visible message and no request sent. Capture the payload with `page.on("request", ...)` and `request.post_data`, extending the pattern in `test_label_printing_test_mode_verification`. Wait on state only — `expect()` on the alert text, never `wait_for_timeout` (depends on T008, T009, T010)

**Checkpoint**: US1 is complete and shippable on its own. The single-item dialog honors a count from
both forms; the two bulk dialogs are untouched and still print one label per item.

---

## Phase 4: User Story 2 - Print several copies of each item's label in a bulk run (Priority: P2)

**Goal**: A label count on the inventory list page's bulk print dialog.

**Independent Test**: Select three items on the inventory list, set the count to 2, pick a label
type, Print All. Six labels' worth of requests go out — three requests each carrying
`label_count: 2` — and the summary reads `Complete: 6 labels for 3 items, 0 failed`.

### Implementation for User Story 2

- [X] T012 [US2] In `app/templates/inventory/list.html`, add the count input to the bulk modal after the `list-bulk-label-type` select (line 224): `<input type="number" id="list-bulk-label-count" min="1" max="99" step="1" value="1">` labeled **"Labels per item"** (FR-014), and add the `label-count.js` script tag before the `inventory-list.js` module tag at line 259
- [X] T013 [US2] In `app/static/js/inventory-list.js`, reset `#list-bulk-label-count` to `1` in `resetBulkPrintModal()`, and in `printAllLabels()` read the count via `window.readLabelCount('list-bulk-label-count')` before the loop starts — on failure render the message into `#list-bulk-print-errors`, leave the label type selection intact, and print nothing (FR-005) — then include `label_count` in each per-item POST body (depends on T012)
- [X] T014 [US2] In `app/static/js/inventory-list.js`, update the reporting: append ` ({n} labels)` to the existing `Printing {i} of {m}: {ja_id}` status line only when the count exceeds 1, and change the completion line to `Complete: {labels} labels for {items} items, {failed} failed` at every count. A failed item contributes `0` labels, never a partial figure (FR-009, research.md Decision 6) (depends on T013)
- [X] T015 [US2] In `tests/e2e/test_bulk_label_printing_list.py`, add tests covering spec Story 2 scenarios 1–7: default of 1; three items at the default producing three single-label requests; three items at 2 producing three requests each carrying `label_count: 2`; the completion summary text; a refused count printing nothing while the dialog stays open; and the count resetting to 1 on reopen. `expect(status).to_contain_text("Complete:")` is a complete wait for the run — it renders only after every request settles (depends on T014)

**Deviation from the literal format string in T014** (raised in review on PR #88): the completion
line pluralizes its nouns, so one item reads `Complete: 1 label for 1 item, 0 failed` rather than
`1 labels ... 1 items`. The `{labels} labels for {items} items` format in research.md Decision 5 and
plan.md was written against a three-item illustration; "1 items" is an unconsidered consequence of it
rather than an intended outcome. Both numbers are still reported at every count, so FR-008 and the
reasoning behind Decision 5 are untouched. `research.md` and `plan.md` are left as written — they are
the frozen record of what was specified, not a description of what shipped.

**Checkpoint**: US1 and US2 both work independently. The post-bulk-Add dialog is still broken — it
was broken before this feature and Phase 5 is where that changes.

---

## Phase 5: User Story 3 - Label a batch of items straight after creating them (Priority: P3)

**Goal**: Repair the print dialog offered after a bulk Add Item creation so it can print at all, then
give it a label count.

**Independent Test**: Create four items through bulk Add Item. In the dialog that follows, the label
type list offers the six real types (not the three invented sizes), and printing at a count of 2
sends four requests each carrying `label_count: 2` with zero failures. Before this phase, every press
of Print All on that dialog returned 400.

**Note**: This phase is a defect repair plus a feature. Keep them legible as separate commits if you
like, but the dialog is not shippable half-repaired.

### Implementation for User Story 3

- [X] T016 [US3] In `app/templates/inventory/add.html`, replace the `<select id="bulk-label-size">` and its three invented options (lines 443–449) with `<select id="bulk-label-type" required>` carrying only the `Select label type...` placeholder, to be populated from the API — matching the list page's markup. Add the count input `<input type="number" id="bulk-label-count" min="1" max="99" step="1" value="1">` labeled **"Labels per item"**, and add the `label-count.js` script tag before the `inventory-add.js` tag at line 384. Nothing in this dialog may read as a label *size*
- [X] T017 [US3] In `app/static/js/inventory-add.js`, populate `#bulk-label-type` from `GET /api/labels/types` when `showBulkLabelPrintingModal()` runs, and disable `#bulk-print-all-btn` until a type is selected — mirroring `initializeBulkPrintModal()` / `onLabelTypeChange()` in `inventory-list.js` (depends on T016)
- [X] T018 [US3] In `app/static/js/inventory-add.js`, fix the payload in `printAllLabels()` (line 868): send `{ja_id, label_type, label_count}` instead of `{ja_id, label_size}`. This is the FR-012 repair — `label_size` is a field the endpoint has no knowledge of, and the omitted `label_type` is why every press has returned 400. Also adopt the list page's error handling: parse `data.error` rather than reporting only `response.statusText`, as `inventory-list.js:231` does (depends on T017)
- [X] T019 [US3] In `app/static/js/inventory-add.js`, reset `#bulk-label-count` to `1` each time the dialog is shown — explicitly **not** seeded from the form's item quantity (Story 3 scenario 4) — read it through `window.readLabelCount('bulk-label-count')`, and apply the same progress and completion wording as T014 so the two bulk dialogs report identically (FR-013) (depends on T018)
- [X] T020 [US3] In `tests/e2e/test_bulk_creation.py`, add tests covering spec Story 3 scenarios 1–5: the label type select offers the real types and none of the old sizes; a default-count print succeeds with zero failures (it could not before); a count of 2 sends one request per created JA ID each carrying `label_count: 2`; the count starts at 1 after creating a batch of 8, not at 8; and dismissing the dialog leaves the created items intact. Use `wait_for_select_populated(page, "bulk-label-type")` — those options now arrive from a fetch rather than the template (depends on T019)
- [X] T021 [US3] Confirm the rest of `tests/e2e/test_bulk_creation.py` still passes untouched, `test_bulk_label_printing_modal_content` in particular — it reads the modal title and item list, which this phase does not change. Creation behavior must be unaffected; the repair touches only the dialog offered afterwards (Constitution VI) (depends on T020)

**Checkpoint**: All three stories work independently. Four surfaces offer a label count; all four
offer the same label types (SC-007).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T022 [P] Update the "Label Printing" section of `docs/user-manual.md` (lines 220–280): document the label count on the single-item and bulk dialogs, the 1–99 range, that it resets to 1 every time while the label type keeps its existing persistence behavior, and that the post-creation dialog can now print. Use American spelling — `catalog`, never `catalogue`
- [X] T023 [P] Verify the inventory search page's bulk dialog is untouched and still inert — no label types, no print action. It is out of scope by decision, not by oversight; `app/static/js/inventory-search.js:356` should still carry its two TODOs
- [X] T024 Regenerate the affected screenshot with `nox -s screenshots` — `bulk_label_printing` in `tests/e2e/screenshot_config.yaml` captures the inventory list bulk modal, whose markup gained an input in T012. Screenshot generation is deliberately excluded from `nox -s e2e`; run it separately and commit the updated image

  **Outcome: ran, nothing to commit.** The task's premise does not hold and the reason is worth
  recording rather than silently skipping:

  1. **No screenshot of any label printing dialog exists.** `docs/images/screenshots/user-manual/`
     contains no `bulk_label_printing.png` and no `label_printing.png`, before or after two full
     `nox -s screenshots` runs.
  2. **The config entry is orphaned.** `screenshot_config.yaml:85` names
     `test_screenshot_bulk_label_printing`, which is not defined anywhere in
     `tests/e2e/test_screenshot_generation.py`. The test that *would* capture the list bulk modal is
     `test_screenshot_label_printing` (line 556), writing `user-manual/label_printing.png` — but its
     capture sits inside a `try/except` that prints "Label printing modal did not appear, skipping
     screenshot" and passes, so it has never produced an image.
  3. **Regeneration is non-deterministic.** Two consecutive runs *with identical code* produced
     different bytes for the same six PNGs (`add_item_form`, `batch_operations_menu`,
     `history_view`, `move_items`, `product_detail`, `search_results`), plus a pure-timestamp diff in
     `metadata.json`. None of those pages can be affected by this feature.

  Committing that churn would have added eight randomly-differing binaries and no information, so it
  was reverted. Capturing the bulk modal at all means fixing the orphaned config entry and the
  swallowed failure in `test_screenshot_label_printing` — a pre-existing gap, and out of scope here.
- [X] T025 Run `nox -s tests` and confirm green
- [X] T026 Run `nox -s e2e` **in the background** — it needs more than the Bash tool's timeout cap allows in the foreground, and takes about 8m15s warm. Confirm green
- [X] T027 Confirm `git status` is clean after the e2e run. A dirty tree means a screenshot test was selected, which the `-m "e2e and not screenshot"` filter exists to prevent (depends on T026)
- [X] T028 Walk the manual scenarios in [quickstart.md](./quickstart.md), including the `curl` check that the route refuses `label_count: 500` independently of the browser

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: blocks all three stories — every dialog posts to the endpoint from T004 and calls the helper from T003
- **US1 (Phase 3)**: needs Phase 2 only
- **US2 (Phase 4)**: needs Phase 2 only — independent of US1
- **US3 (Phase 5)**: needs Phase 2 only — independent of US1 and US2, though T019 mirrors the wording settled in T014, so doing US2 first saves deciding it twice
- **Polish (Phase 6)**: T022–T024 need their respective stories done; T025–T028 need everything

### Within Each Story

The JS files are the serialization point. `label-printing-modal.js` (US1), `inventory-list.js` (US2),
and `inventory-add.js` (US3) each carry several tasks that must land in order because they touch the
same file. Template edits and test files are the parallel opportunities.

### Parallel Opportunities

- **T002 and T003** — the service rename and the new browser helper share nothing
- **T009 and T010** — the same one-line script tag in two different templates
- **T022 and T023** — documentation and a verification check, different files
- **Across stories**: with more than one person, US1 / US2 / US3 can proceed simultaneously once Phase 2 is done. Each owns a different JS file and a different template, so they do not collide. The only shared edit is the pair of script tags, already isolated in T009/T010

### Parallel Example: Phase 2

```bash
# T002 and T003 have no relationship — start both:
Task: "Rename num_copies to label_count and thread it through app/services/label_printer.py"
Task: "Create the shared window.readLabelCount helper in app/static/js/label-count.js"
# T004 then needs T002; T005 needs T004; T006 needs T002 and T005 (same test file as T005).
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Phase 1 → Phase 2 → Phase 3
2. **Stop and validate**: the single-item dialog honors a count from Add and from Edit
3. Shippable. The two bulk dialogs still print one label per item, exactly as they do today — the
   optional `label_count` field is what makes that true rather than a leftover

### Incremental Delivery

1. Phase 2 → foundation ready, nothing user-visible yet
2. + US1 → single-item counts (MVP)
3. + US2 → the bulk surface where the count actually saves presses
4. + US3 → the post-creation dialog prints for the first time, with a count
5. Phase 6 → docs, screenshot, full suites

Each step leaves the application in a working state, because the endpoint treats the count as
optional throughout.

---

## Notes

- **`Decimal` does not apply here.** A label count is a cardinality, not a measurement. `int` is
  correct; Principle III governs physical quantities.
- **No migration.** Nothing is persisted — see [data-model.md](./data-model.md).
- **No test may reach `LpPrinter.print_images()`.** It drives real hardware. The short-circuit at
  `app/services/label_printer.py:92` must stay first in the function.
- **E2E waits on state, never on a duration.** `page.wait_for_timeout` and
  `wait_for_load_state("networkidle")` are prohibited by Constitution IV. The practice for finding
  the right condition is in `CLAUDE.md`.
- **Negative e2e assertions need an established region first.** "The request carried no count" and
  "the old sizes are absent" both pass trivially against a dialog that has not rendered.
- Commit after each task or logical group; stop at any checkpoint to validate a story on its own.
