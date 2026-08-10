---

description: "Task list for feature 010: Fix Add & Continue With Quantity Greater Than One"
---

# Tasks: Fix Add & Continue With Quantity Greater Than One

**Input**: Design documents from `/specs/010-fix-bulk-add-continue/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/add-item-submission.md), [quickstart.md](./quickstart.md)

**Tests**: **Required, not optional.** FR-012 makes end-to-end coverage of the defective
combination a deliverable, and Constitution IV requires that behavior changes land with tests
covering that behavior. Test tasks come before the implementation they guard.

**Organization**: Tasks are grouped by user story. Note the honest caveat below — these stories
are *sequenced*, not independent.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths appear in every task

## Path Conventions

Server-rendered Flask app, repository root. Production code in `app/`, tests in `tests/unit/` and
`tests/e2e/`. No new directories.

## Read this before starting

**Parallelism here is nearly nil, and pretending otherwise would cause conflicts.** US1 and US2
are successive edits to the same 40 lines of `app/static/js/inventory-add.js`, and their tests are
successive additions to the same `tests/e2e/test_bulk_creation.py`. Only Phase 5 (US3) touches a
disjoint file set and is genuinely parallelizable. The `[P]` marker appears on exactly two tasks
in this file, and both occurrences are real.

**The stories are not independently deliverable in the template's sense.** US2 without US1 would
mean navigating away after a submission that may have created twice what was asked. US1 is the
MVP and ships alone if you stop early; US2 layered on US1 is the complete feature. US3 needs no
production change at all and can be done any time.

**Run tests through `nox`, never bare `pytest`** (Constitution IV). `nox` sessions pin Python
3.13; if the system Python is newer, put pyenv's 3.13 on `PATH` first. Give `nox -s e2e` a
15-minute tool timeout.

---

## Phase 1: Setup

**Purpose**: Make later failures attributable to this change rather than to the environment.

- [X] T001 Activate the repository virtualenv (`venv/`) and confirm the `nox` sessions resolve Python 3.13 — put pyenv's 3.13 ahead of the system Python on `PATH` if `nox -l` reports a missing interpreter
- [X] T002 Record the green baseline: run `nox -s e2e -- tests/e2e/test_bulk_creation.py tests/e2e/test_add_item.py` and confirm all pass **before** any edit, so a later failure in these files is known to be caused by this work

**Checkpoint**: Toolchain resolves and the files this feature touches are green.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Test scaffolding that both US1 and US2 need. Nothing in Phase 3 or 4 can be written
without it.

**⚠️ Both tasks edit `tests/e2e/test_bulk_creation.py` — strictly sequential, no `[P]`.**

- [X] T003 Add `submit_and_continue()` to the `BulkCreationPage` class in `tests/e2e/test_bulk_creation.py`, mirroring the existing `submit_form()` (clear `#toast-container`, set `window.__awaitingSubmit`, click `#submit-and-continue-btn`, then `wait_for_function` settling on document replacement, a toast, or `#bulkLabelPrintingModal.show`) — reuse the existing helper's body rather than inventing a second waiting strategy
- [X] T004 Add a module-level `count_add_posts(page)` helper in `tests/e2e/test_bulk_creation.py` that attaches `page.on("request", ...)` and returns a mutable counter of `POST` requests whose URL ends in `/inventory/add`; document at the call site that this counts requests *dispatched*, which is what FR-001 constrains

**Checkpoint**: A test can drive **Add & Continue** at any quantity and count the resulting POSTs.

---

## Phase 3: User Story 1 — Bulk create without spurious errors or extra items (Priority: P1) 🎯 MVP

**Goal**: One press of **Add & Continue** at quantity *N* produces exactly one request and exactly
*N* items, with no error shown.

**Independent Test**: Fill the Add form, set quantity above 1, press **Add & Continue**, and check
that the inventory gained exactly the requested number of items and that no error message appeared.

### Tests for User Story 1 ⚠️

> **Write these first and watch them FAIL.** T005 fails today with `2 != 1`. T006 is
> nondeterministic today — it fails either on the item count (6 when 3 were asked for) or on the
> error toast (`Failed to create any items`), depending on interleaving. Both outcomes are the
> bug; if T006 passes on the first run, run it again before believing it.

- [X] T005 [US1] Add `test_bulk_add_and_continue_sends_one_request` to `tests/e2e/test_bulk_creation.py`: fill a valid item, set quantity 3, submit via `submit_and_continue()`, wait with `wait_for_modal_shown(page, "bulkLabelPrintingModal")`, then assert the T004 counter equals exactly 1
- [X] T006 [US1] Add `test_bulk_add_and_continue_creates_exact_count` to `tests/e2e/test_bulk_creation.py`: read `len(InventoryService(live_server.storage).get_all_items())` before submitting, set quantity 3, submit via `submit_and_continue()`, wait for the modal, then assert the count delta is exactly 3 and that `#toast-container .toast-body` contains no error text — establish the modal with `wait_for_modal_shown` *before* the negative toast assertion, per the negative-assertion rule in `CLAUDE.md`

### Implementation for User Story 1

- [X] T007 [US1] In `app/templates/inventory/add.html`, add `<input type="hidden" name="submit_type" id="submit-type" value="add">` inside `#add-item-form` (near the existing `csrf_token` field at line 31); leave both submit buttons' `name`/`value` attributes in place so `event.submitter.value` keeps working
- [X] T008 [US1] In `app/static/js/inventory-add.js`, collapse the two submission entry points into one: delete the `#submit-and-continue-btn` click listener (lines 79-81), change `handleSubmit(event, continueAdding = false)` to derive `const continueAdding = event?.submitter?.value === 'continue'`, delete the `document.createElement('input')` block (lines 668-674), and instead assign `document.getElementById('submit-type').value = continueAdding ? 'continue' : 'add'` — see research.md D1 and D3
- [X] T009 [US1] In `app/static/js/inventory-add.js` `handleSubmit()`, add the re-entrancy guard: `if (this.submitting) return;` immediately after `event.preventDefault()` and the validity check, set `this.submitting = true`, and move the button-state restoration into a single `finally` block replacing the duplicated restores in the success and `catch` branches (research.md D2, FR-005)

### Verification for User Story 1

- [X] T010 [US1] Confirm T005 and T006 now pass, then run `nox -s e2e -- tests/e2e/test_bulk_creation.py tests/e2e/test_add_item.py` — the eight pre-existing bulk tests and `test_add_and_continue_carry_forward_workflow` (quantity-1 continue) are the FR-011 regression surface and must be unchanged

**Checkpoint**: The reported defect is fixed and the inventory is trustworthy. **This is a
shippable stopping point** — the button's label is still misleading for bulk, but nothing is
broken.

---

## Phase 4: User Story 2 — Continue into the next entry after a bulk create (Priority: P2)

**Goal**: After a bulk **Add & Continue**, dismissing the label dialog returns the user to a fresh
Add form — the same state the single-item path reaches by server redirect.

**Independent Test**: Complete a bulk **Add & Continue**, dismiss the dialog, and confirm the form
matches what a single-item **Add & Continue** leaves behind.

**Depends on**: Phase 3. These tasks edit the same handler US1 just rewrote.

### Tests for User Story 2 ⚠️

> All three fail before T014: today the page simply stays put after the dialog closes.

- [X] T011 [US2] Add `test_bulk_add_and_continue_returns_to_empty_form` to `tests/e2e/test_bulk_creation.py`: submit quantity 3 via `submit_and_continue()`, `close_modal()`, then `expect(page).to_have_url(re.compile(r"/inventory/add$"))` followed by `expect(page.locator("#ja_id")).not_to_have_value("")` — the second wait is `CLAUDE.md` pattern G, because `autoPopulateJaId()` writes the field only after awaiting `/api/inventory/next-ja-id`; then assert `#notes` and `#length` are empty
- [X] T012 [US2] Add `test_carry_forward_after_bulk_add_and_continue` to `tests/e2e/test_bulk_creation.py`: after the flow in T011, click `#carry-forward-btn`, wait for the toast, and assert material, location, type and shape are restored from the batch just created (FR-008)
- [X] T013 [US2] Add `test_bulk_add_does_not_return_to_empty_form` to `tests/e2e/test_bulk_creation.py`: submit quantity 3 via the **existing** `submit_form()` (plain **Add**), `close_modal()`, and assert the URL did not change and `#material` still holds the submitted value — this is FR-007, the guard against the two buttons collapsing into one, and it is the assertion most easily lost

### Implementation for User Story 2

- [X] T014 [US2] In `app/static/js/inventory-add.js`, set `this.continueAfterBulk = continueAdding` before dispatching the bulk `fetch`, and register a `hidden.bs.modal` listener on `#bulkLabelPrintingModal` that navigates to `/inventory/add` when the flag is set (research.md D4) — register it once during setup, not per submission
- [X] T015 [US2] Delete the dead `clearFormForContinue()` method from `app/static/js/inventory-add.js` (lines 823-846); it is called from nowhere in `app/` or `tests/`, and leaving a method named for exactly what T014 implements — which it does not correctly do, since it never repopulates the JA ID — misleads the next reader (research.md D7)

### Verification for User Story 2

- [X] T016 [US2] Confirm T011-T013 pass and re-run `nox -s e2e -- tests/e2e/test_bulk_creation.py tests/e2e/test_add_item.py`

**Checkpoint**: **Add & Continue** honors its label at every quantity, and **Add** remains
distinct from it.

---

## Phase 5: User Story 3 — Honest reporting when a bulk create does not fully succeed (Priority: P3)

**Goal**: Partial-failure reporting on the *form* path states a count that matches what was
recorded, and this survives the change.

**Independent Test**: Force a bulk creation to fail partway and confirm the reported counts match
the inventory.

**Fully independent of Phases 3 and 4** — different files, no production change. Can be done
first, last, or concurrently.

> **These are characterization tests and should PASS on first run.** The behavior already exists
> at `app/main/routes.py:585-591`; what is missing is coverage. If either test fails, that is a
> real defect in the partial-failure path and is in scope for this feature. A partial failure is
> not reachable through the browser — the server's allocation (`routes.py:314`) starts above the
> current maximum precisely to avoid collisions — so this is verified at the unit level with the
> same `monkeypatch` technique already used by `test_partial_failure_returns_207`
> (`tests/unit/test_routes.py:1511`), not end to end.

- [X] T017 [P] [US3] Add a form-path partial-failure test to `tests/unit/test_routes.py`: monkeypatch `app.main.routes._create_single_item` to fail the second of three items, `POST /inventory/add` with `quantity_to_create=3`, and assert the response is 500 with `success: false`, `count == 2`, and `len(ja_ids) == 2` — the form branch is separate from the JSON API branch already covered at line 1511, and `count`/`ja_ids` are what FR-009's "the count stated matches the inventory" rests on
- [X] T018 [P] [US3] Add a form-path complete-failure test to `tests/unit/test_routes.py`: monkeypatch `_create_single_item` to fail every item, `POST /inventory/add` with `quantity_to_create=2`, and assert 500 with the `Failed to create any items` message and no items recorded

**Checkpoint**: The form path's bulk failure reporting is covered, in the fast suite.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T019 Verify SC-005 by proving the guard bites: stash the T007-T009 changes (`git stash`), run T005 alone, confirm it fails with a request count of 2, then restore (`git stash pop`) — a regression test never seen red is not yet a regression test
- [X] T020 Run `nox -s tests` and confirm the unit suite is green, including the untouched `tests/unit/test_routes.py:123` audit-logging tests for the **Add & Continue** workflow, whose passing unchanged is the evidence that server behavior did not move
- [X] T021 Run the full `nox -s e2e` with a 15-minute tool timeout — the add path is named in Constitution VI, so the active-status, history and multi-row suites are part of this change's regression surface — then confirm `git status` is clean, since an e2e run must not modify tracked files
- [X] T022 Walk the ten-step manual acceptance table in [quickstart.md](./quickstart.md) § 3, which covers the requirements no automated test reaches: Enter-key submission (step 10), double-press (step 9), and the quantity-1 paths (steps 6-7)
- [X] T023 Prepare the PR: confirm new lines satisfy `nox -s lint` without reformatting surrounding code (the session is red at baseline on pre-existing E501 failures and is advisory), and state in the PR description that documentation screenshots were deliberately **not** regenerated because the change alters a hidden input and event wiring, neither of which renders — the `Screenshot Reminder` workflow will comment on this PR regardless and blocks nothing (research.md D6)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies.
- **Phase 2 (Foundational)**: Depends on Phase 1. **Blocks Phases 3 and 4** — both stories' tests
  call the helpers it adds. Does **not** block Phase 5.
- **Phase 3 (US1)**: Depends on Phase 2.
- **Phase 4 (US2)**: Depends on Phase 3 — same handler, same test file.
- **Phase 5 (US3)**: Depends only on Phase 1.
- **Phase 6 (Polish)**: Depends on every phase you intend to ship.

### Story Dependencies

- **US1 (P1)**: The MVP. Ships alone.
- **US2 (P2)**: Requires US1. Navigating away after a submission that might have double-created
  would make the defect harder to notice, not easier.
- **US3 (P3)**: Independent of both. No production code change.

### File Conflict Map

Tasks touching the same file must not be run concurrently:

| File | Tasks |
|------|-------|
| `tests/e2e/test_bulk_creation.py` | T003, T004, T005, T006, T011, T012, T013 |
| `app/static/js/inventory-add.js` | T008, T009, T014, T015 |
| `app/templates/inventory/add.html` | T007 |
| `tests/unit/test_routes.py` | T017, T018 |

### Parallel Opportunities

Two, and only two:

- T017 and T018 carry `[P]` **with respect to Phases 2-4** — `tests/unit/test_routes.py` shares no
  file with the JS or e2e work, and US3 needs no production change. They are not parallel with
  *each other* (same file).
- Nothing else qualifies. Note in particular that T019 must run **alone**: it stashes and restores
  the working tree, so anything running beside it would see a half-applied checkout.

Everything else is a chain. This is a small bug fix in one handler; a task list claiming
widespread parallelism would be describing a different feature.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 → Phase 2 → Phase 3.
2. **STOP and VALIDATE**: T010. The inventory can no longer gain items the user did not ask for,
   and the reported error is gone.
3. Shippable. **Add & Continue** at quantity > 1 now behaves like **Add** — imperfect, but correct.

### Full Feature

4. Phase 4 (US2) → **Add & Continue** honors its label at every quantity.
5. Phase 5 (US3) at any point → closes the coverage gap on the form's bulk failure reporting.
6. Phase 6 → full suites, manual walkthrough, PR.

### Suggested Ordering If Interleaving

Run Phase 5 first if you want a quick green win in the sub-second unit suite before starting on
the browser work; it shares nothing with the rest and its result is informative either way.

---

## Notes

- `[P]` = different files, no dependency. Used on two tasks here, both justified above.
- Every new wait must name an element or a page condition — no `wait_for_timeout`, no
  `time.sleep`, no `networkidle` (Constitution IV). `wait_for_modal_shown` and
  `wait_for_modal_hidden` already exist in `tests/e2e/waits.py`; do not write new ones.
- Before every `count()`, `text_content()`, `is_visible()` or `get_attribute()` in a new test, ask
  what established that region. Against a JS-rendered page they read "empty" rather than waiting.
- Commit after each phase checkpoint rather than after each task; the tasks within a phase are
  fine-grained edits to one file.
- No Alembic revision, no schema change, no new dependency, no new pytest marker.

---

## Implementation notes (2026-08-10)

### The stated root cause did not reproduce

T005 and T006 were written to fail first, per the Phase 3 preamble. **They passed
against the unmodified code.** Measured directly rather than inferred:

| Observation, unmodified code, quantity 3, one press of **Add & Continue** | Predicted | Measured |
|---|---|---|
| `POST /inventory/add` requests dispatched | 2 | **1** |
| `Submit: Submitting form with type: …` console lines | 2 (`continue`, `add`) | **1** (`continue`) |
| Items created | 3 or 6 | **3** |
| Error toast / JS page error | one of them | **none** |

`handleSubmit` sets `continueBtn.disabled = true` synchronously, before its first
`await`. A button's activation behavior returns early when the element is
disabled, and activation runs after the click listeners — so the click's default
form submission was suppressed and the `submit` listener never fired. research.md
carries the same correction at its root-cause section.

**Consequence for SC-005**: T019 as written (stash the fix, watch T005 fail with
a request count of 2) cannot succeed, because the count was never 2. The stash
experiment was run anyway and recorded what actually goes red:

| New test | Against unmodified code |
|---|---|
| `test_bulk_add_and_continue_sends_one_request` | PASSED (characterization) |
| `test_bulk_add_and_continue_creates_exact_count` | PASSED (characterization) |
| `test_bulk_add_and_continue_returns_to_empty_form` | **FAILED** |
| `test_carry_forward_after_bulk_add_and_continue` | **FAILED** |
| `test_plain_add_after_bulk_continue_is_not_a_continue` | **FAILED** |

So SC-005 holds for the defects that were real, and three of the five new e2e
tests have been seen red. The two FR-001/FR-002 tests are characterization
tests: required by FR-012, but they guard a property rather than reproduce a
failure.

### Tests added beyond the task list

- `test_plain_add_after_bulk_continue_is_not_a_continue` — the stale
  `submit_type` defect (research.md D3), the one cross-submission bug that was
  reproducibly broken. Not in the original task list because the plan attributed
  everything to the double submission.
- `test_repeated_submission_creates_one_batch` and
  `test_enter_key_submits_as_plain_add` — T022's manual acceptance table steps 9
  and 10. These cover FR-005 and the keyboard-submission edge case, which no
  automated test reached; they are asserted in the suite rather than walked by
  hand. Steps 1-8 of that table are covered by the tests in this file and in
  `test_add_item.py`.

`test_enter_key_submits_as_plain_add` initially failed for an unrelated reason
worth recording: implicit submission is **silent** when the form is invalid — the
submit event fires, `checkValidity()` returns false, the handler returns, and
nothing observable changes. The test had used a material outside the taxonomy.
It now establishes `is-valid` on `#material` and a populated `#ja_id` before
pressing Enter.

### Not done

- **Screenshots not regenerated**, per research.md D6 — the change is a hidden
  input, a `type` attribute and event wiring, none of which renders.
- **T022 was not walked manually.** Its uncovered steps were automated instead
  (above). Steps requiring a human at a real browser were not performed.
