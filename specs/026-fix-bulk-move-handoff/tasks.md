---

description: "Task list for feature 026: Fix the item hand-off into Move and Shorten"
---

# Tasks: Fix the item hand-off into Move and Shorten

**Input**: Design documents from `/specs/026-fix-bulk-move-handoff/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/handoff.md](./contracts/handoff.md), [quickstart.md](./quickstart.md)

**Tests**: Included and mandatory. FR-019 to FR-022 require them, and Principle IV requires any behavior change to land with tests covering that behavior. The absence of exactly these tests is why all five defects shipped — see [research.md](./research.md) R4.

**Organization**: Tasks are grouped by user story. Each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)

## Path Conventions

Existing repository layout, per plan.md. Routes in `app/main/`, page controllers in
`app/static/js/`, shared components in `app/static/js/components/`, helpers in `app/utils/`,
templates in `app/templates/inventory/`, tests in `tests/unit/` and `tests/e2e/`.

**Run everything through nox** (Principle IV), with the venv binaries by path:

```bash
export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
venv/bin/nox -s tests
nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &   # never in the foreground; ~13m45s warm
```

---

## Phase 1: Setup & Reproduction

**Purpose**: Establish a green baseline, and settle issue #107's mechanism before any behavior is changed.

**⚠️ T002 is a gate, not a formality.** Three code paths produce #107's report and research R3 does not settle which. A fix written against the wrong one passes its own test and leaves the user stuck.

- [X] T001 Establish a green baseline: run `venv/bin/nox -s tests` and `nox -s e2e` (detached) on `issues/106` before any edit, and record the pass count and wall-clock in `specs/026-fix-bulk-move-handoff/verification.md`
- [X] T002 Reproduce issue #107 per [quickstart.md](./quickstart.md) Step 0 — 14 JA-ID/location pairs then `>>DONE<<` — recording at each step the `#queue-count` badge text, the `#form-alerts` text, whether `#validate-btn` is enabled, and `moveQueue.length` / `currentExpectedInput` from the console; write the trace to `specs/026-fix-bulk-move-handoff/verification.md`
- [X] T003 Classify the T002 trace against Candidates A, B and C in [research.md](./research.md) R3 and append the conclusion to `specs/026-fix-bulk-move-handoff/research.md`. **If none matches, STOP** and revise User Story 2's acceptance scenarios in `spec.md` before writing any US2 code

**Checkpoint**: Baseline green, #107's mechanism recorded as evidence rather than assumed.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The hand-off plumbing — one convention, one parser, both routes, all four producers. Blocks US1, US3 and US4.

**⚠️ CRITICAL**: US1, US3 and US4 cannot begin until this phase completes. US2 is independent of it and may proceed in parallel.

- [X] T004 [P] Write failing unit tests for the hand-off parsing rules of [contracts/handoff.md](./contracts/handoff.md) §2 — split/trim/discard-empty, `JA[0-9]+` filtering, duplicate collapse preserving first-occurrence order, absent/empty yielding no hand-off — in `tests/unit/test_handoff_parsing.py`
- [X] T005 Implement the hand-off parser in `app/utils/handoff.py`: parse the `ja_id` parameter into an ordered, de-duplicated JA ID list per [contracts/handoff.md](./contracts/handoff.md) §2 steps 1-4, with type hints per the Technology Constraints
- [X] T006 Write failing unit tests for identifier resolution — active row accepted, missing ID rejected as `not_found`, existing-but-inactive row rejected as `inactive` — in `tests/unit/test_handoff_parsing.py`
- [X] T007 Implement resolution against storage in `app/utils/handoff.py`, returning `preselected_items` and `rejected_items` per [data-model.md](./data-model.md) §2, going through the existing `Storage` interface and checking `result.success` (Principle II)
- [X] T008 Wire `inventory_move()` in `app/main/routes.py:986` to parse and resolve the `ja_id` parameter and pass `preselected_items` / `rejected_items` to the template — route stays thin, no ORM query, no raw SQL
- [X] T009 [P] Wire `inventory_shorten()` in `app/main/routes.py:995` the same way, taking the first accepted item per [contracts/handoff.md](./contracts/handoff.md) §2 step 6
- [X] T010 [P] Change `bulkMoveSelected()` in `app/static/js/inventory-list.js:503` to emit `ja_id=` instead of `items=`, retiring the second convention
- [X] T011 [P] Add unit assertions in `tests/unit/test_routes.py` that both row-action hand-off links render with the `ja_id` convention, extending the existing bare-link assertion at `tests/unit/test_routes.py:1123` so it covers the convention and not merely the link's presence (FR-022)

**Checkpoint**: Both routes read what they are handed; all four producers emit one convention. Nothing user-visible yet.

---

## Phase 3: User Story 1 - Move a group of selected items to one place (Priority: P1) 🎯 MVP

**Goal**: Selecting items and choosing Bulk Move Selected — from either the inventory list or Search — opens the Move page holding those items, asks once for a destination, and queues all of them to it.

**Independent Test**: Select three items on `/inventory`, click Bulk Move Selected, scan one location, confirm all three are queued to it and execute successfully. Closes issue #106 on its own.

### Tests for User Story 1 ⚠️

> Write these FIRST and confirm they FAIL against the pre-fix behavior. A US1 test that passes before the fix is navigating directly instead of clicking the control — which is the defect, not the test.

- [X] T012 [P] [US1] Add a page object exposing the inventory list's Options menu and Bulk Move Selected control in `tests/e2e/pages/inventory_list_page.py`
- [X] T013 [P] [US1] Add the equivalent page object for the Search page's Options menu in `tests/e2e/pages/inventory_search_page.py`
- [X] T014 [US1] Write the acceptance e2e test for issue #106 in `tests/e2e/test_bulk_move_handoff.py`: seed three items with `live_server.add_test_data`, select them, **click the real Bulk Move Selected control** (never `page.goto` with a hand-built URL, per FR-019), scan one location, assert all three are queued to it with their own current locations and `#queue-count` reads `3 items`, then validate and execute
- [X] T015 [P] [US1] Write the Search-page equivalent in `tests/e2e/test_bulk_move_handoff.py`, asserting behavior identical to the list page — this is the test that catches a re-split of the parameter convention
- [X] T016 [P] [US1] Write e2e coverage in `tests/e2e/test_bulk_move_handoff.py` for a group sub-location applying to **every** item of the group (FR-009), and for hand-scanning a further item into the same batch afterwards (FR-011)
- [X] T017 [P] [US1] Write e2e coverage for the rejection and edge cases of [quickstart.md](./quickstart.md) Step 7 in `tests/e2e/test_bulk_move_handoff.py` — nonexistent ID, inactive row, all-rejected, duplicate, no-parameter arrival unchanged, sub-location scanned first, `>>DONE<<` with no destination given, clear-queue-after-hand-off

### Implementation for User Story 1

- [X] T018 [US1] Render `preselected_items` and `rejected_items` into `app/templates/inventory/move.html` for the page controller to read on load, and surface rejected items by JA ID with their reason (FR-005)
- [X] T019 [US1] Add the `bulk_location` state to the state machine in `app/static/js/inventory-move.js` per [data-model.md](./data-model.md) §5: entered only when the page loads with preselected items, and stating the count and that the next input is the destination for all of them (FR-007)
- [X] T020 [US1] Build the pending-move list of [data-model.md](./data-model.md) §3 on load in `app/static/js/inventory-move.js`, resolving each item's current location through the existing `GET /api/items/{ja_id}` — reused, not batched, per [contracts/handoff.md](./contracts/handoff.md) §5
- [X] T021 [US1] Implement the `bulk_location` → `ja_id_or_sub_location` transition in `app/static/js/inventory-move.js`: a valid location converts every pending move into an ordinary queued move with that destination (FR-008), leaving the queued-move shape unchanged so validation and execution need no changes (FR-013)
- [X] T022 [US1] Reject non-location input in `bulk_location` with an explanation, and handle `>>DONE<<` there by queueing nothing and saying why (FR-012, and [data-model.md](./data-model.md) §5)
- [X] T023 [US1] Extend the existing sub-location handling in `app/static/js/inventory-move.js` so a sub-location supplied after a group was queued applies to every item of that group, not only the last (FR-009)
- [X] T024 [US1] Make the state machine reach `ja_id` after the group is queued so hand scanning continues into the same batch (FR-011), and confirm clearing the queue leaves the page usable rather than dead

**Checkpoint**: Issue #106 is closed from both entry points. This is the MVP — stop and validate here.

---

## Phase 4: User Story 2 - Finish a long scanning session (Priority: P2)

**Goal**: A long scanning session can always be validated and executed, and no input is discarded silently.

**Independent Test**: Scan 14 JA-ID/location pairs, finish, and confirm validation and execution are reachable with every pair present. Needs nothing from US1.

**⚠️ Depends on T003.** Do not start until #107's mechanism is recorded.

### Tests for User Story 2 ⚠️

- [X] T025 [P] [US2] Write the long-session e2e test in `tests/e2e/test_move_long_session.py`: 14 JA-ID/location pairs then `>>DONE<<`, asserting the 14th pair is queued, `#queue-count` reads `14 items`, `#validate-btn` is enabled, and no spurious input warning is present (FR-014, FR-015, FR-016, FR-020)
- [X] T026 [P] [US2] Write the wedge test in `tests/e2e/test_move_long_session.py`: from the state where a JA ID has been scanned but no location given, scan another JA ID and assert the machine resolves rather than bouncing — no state from which no valid input makes progress ([data-model.md](./data-model.md) §5 invariant)
- [X] T027 [P] [US2] Write the no-trailing-newline test in `tests/e2e/test_move_long_session.py`, driving a full sequence **without** pressing Enter so the 100 ms fallback path executes, asserting the same outcome as the Enter path (FR-017, FR-021) — this path has never been executed by any test
- [X] T028 [US2] Extend `tests/e2e/waits.py` only if T025-T027 need a transition signal it does not already cover, choosing the signal per transition using the patterns in `CLAUDE.md`; any wait that cannot observe its condition MUST carry a written justification at the call site (Principle IV)

### Implementation for User Story 2

- [X] T029 [US2] Fix the state-machine wedge in `app/static/js/inventory-move.js:207-210`: a JA ID arriving in state `location` must resolve the machine rather than warn and leave the state unchanged, since it unambiguously means the previous item's location was missed
- [X] T030 [US2] Make repeated rejections legible in `app/static/js/inventory-move.js`: `showAlert()` currently assigns `this.formAlerts.innerHTML`, so 14 failed scans render as one warning and a stale `warning` never auto-dismisses — accumulate rather than overwrite so a user scanning into a wedged machine can see it
- [X] T031 [US2] Apply the fix indicated by the T003 classification in `app/static/js/inventory-move.js`, bounded per [research.md](./research.md) R3: **no** state-machine rewrite, **no** configurable `scannerDelay`, and **not** simply enabling the buttons whenever the queue is non-empty
- [X] T032 [US2] Suppress the spurious "Please enter a value" warning raised when the scanner's Enter reaches `processInput()` after `handleBarcodeInput()` has already consumed `>>DONE<<` and cleared the field (FR-016)
- [X] T033 [US2] Make the reason evident when validation is unavailable because an item is half-entered (FR-018)

**Checkpoint**: Issue #107 is closed, and the input pipeline can no longer discard a scan silently.

---

## Phase 5: User Story 3 - Move one item straight from its row (Priority: P3)

**Goal**: A row's Move action opens the Move page holding that one item, needing only a destination.

**Independent Test**: Use a row's Move action and confirm the page opens with that item awaiting a destination.

**Note**: mostly delivered by Phase 2 and US1 — a single item is a list of one, so it enters `bulk_location` like any group. These tasks confirm that rather than build it.

### Tests for User Story 3 ⚠️

- [X] T034 [P] [US3] Write the row-action e2e test in `tests/e2e/test_bulk_move_handoff.py`: open a row's dropdown and **click the real Move action** (FR-019), assert the Move page holds that one item awaiting a destination, then scan a location, validate and execute

### Implementation for User Story 3

- [X] T035 [US3] Confirm `showMoveDialog()` in `app/static/js/components/item-actions.js:39` and the row dropdown Move href in `app/static/js/components/inventory-table.js:466` both emit the convention of [contracts/handoff.md](./contracts/handoff.md) §1, and correct them if not
- [X] T036 [US3] Confirm a single-item hand-off presents as one pending move and reads naturally in the `bulk_location` prompt — the wording of FR-007 must not read as though a group arrived when one item did

**Checkpoint**: Single-item Move works from the row action.

---

## Phase 6: User Story 4 - Shorten one item straight from its row (Priority: P4)

**Goal**: A row's Shorten action opens the Shorten page already identifying that item.

**Independent Test**: Use a row's Shorten action and confirm `source_ja_id` is prefilled.

### Tests for User Story 4 ⚠️

- [X] T037 [P] [US4] Write the row-action e2e test in `tests/e2e/test_shorten_handoff.py`: **click the real Shorten action** (FR-019), assert `#source-ja-id` is prefilled with that JA ID, and assert that opening `/inventory/shorten` with no parameter behaves exactly as today (FR-004)

### Implementation for User Story 4

- [X] T038 [US4] Prefill the `source_ja_id` field in `app/templates/inventory/shorten.html:51` from the resolved hand-off, leaving it empty when there is none
- [X] T039 [US4] Consume the prefilled value in `app/static/js/inventory-shorten.js` so the page's own workflow proceeds from it — a prefill, not a mode, per [data-model.md](./data-model.md) §6
- [X] T040 [US4] Confirm `showShortenDialog()` in `app/static/js/components/item-actions.js` and the row dropdown Shorten href in `app/static/js/components/inventory-table.js` emit the convention, and name any rejected item rather than dropping it

**Checkpoint**: All four hand-offs carry the user's items through.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T041 Verify no fixed waits were introduced: `grep -rn "wait_for_timeout\|time.sleep\|networkidle" tests/e2e/` — the suite executes zero today and must still execute zero (Principle IV)
- [X] T042 Run the full gates: `venv/bin/nox -s tests` and `nox -s e2e` detached, confirming the active-status and item-history e2e tests pass (Principle VI is engaged — this touches move and shorten)
- [X] T043 Confirm an e2e run leaves the working tree clean; if it does not, screenshot tests leaked into the session (Principle IV)
- [X] T044 Regenerate documentation screenshots with `venv/bin/nox -s screenshots_headless` and verify with `nox -s screenshots_verify` — `app/templates/**` and `app/static/js/**` changed, so CI blocks on stale screenshots. **Measure the churn before committing any**: screenshots come from two sources and churn every run
- [X] T045 [P] Document the bulk move workflow in `docs/user-manual.md`, which has never mentioned Bulk Move Selected — place it alongside the existing bulk label printing section at `docs/user-manual.md:240`, using American spelling ("catalog", never "catalogue")
- [X] T046 [P] Record in `specs/026-fix-bulk-move-handoff/verification.md` the e2e wall-clock delta from the added tests, against the ~13m45s warm baseline and the 15-minute gate; if the gate is threatened, reduce T025's pair count — never the wait discipline, which has none left to remove
- [X] T047 Walk [quickstart.md](./quickstart.md) Steps 1-8 end to end as final validation
- [X] T048 Open the pull request against `main` from `issues/106`, referencing issues #106 and #107

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup & Reproduction)**: no dependencies. **T003 gates all of Phase 4.**
- **Phase 2 (Foundational)**: after Phase 1. **Blocks US1, US3, US4.** Does not block US2.
- **Phase 3 (US1)**: after Phase 2.
- **Phase 4 (US2)**: after T003 only — independent of Phase 2, so it can run alongside it.
- **Phase 5 (US3)**: after Phase 2; substantially easier after US1 (shares `bulk_location`).
- **Phase 6 (US4)**: after Phase 2. Independent of US1, US2, US3.
- **Phase 7 (Polish)**: after every story to be shipped.

### User Story Dependencies

- **US1 (P1)**: Phase 2 only. No dependency on another story.
- **US2 (P2)**: T003 only. Fully independent — a different defect in the same file.
- **US3 (P3)**: Phase 2; reuses US1's `bulk_location` rather than adding a path.
- **US4 (P4)**: Phase 2. Touches the Shorten page, which no other story touches.

### File-contention warnings

Independent stories, shared files. These cannot be worked simultaneously without conflict:

- `app/static/js/inventory-move.js` — US1 (T019-T024) and US2 (T029-T033). **Sequence these**, or expect conflicts in one file.
- `tests/e2e/test_bulk_move_handoff.py` — US1 (T014-T017) and US3 (T034).
- `app/static/js/components/item-actions.js` and `inventory-table.js` — US3 (T035) and US4 (T040).

### Within Each User Story

- Tests written and failing before implementation.
- Parser before routes; routes before templates; templates before page controllers.
- A US1 test that passes before the fix is testing the wrong thing — see T014.

### Parallel Opportunities

- T004 / T009 / T010 / T011 in Phase 2 — different files.
- T012 / T013 page objects; then T015 / T016 / T017 once T014 establishes the file.
- T025 / T026 / T027 — all in `test_move_long_session.py`, so parallel only if written as one unit.
- US2 (Phase 4) alongside Phase 2, subject to the `inventory-move.js` contention above.
- T045 / T046 in Polish.

---

## Parallel Example: Phase 2 Foundational

```bash
# After T005 and T007 land the parser, these touch different files:
Task: "Wire inventory_shorten() in app/main/routes.py"          # T009
Task: "Change bulkMoveSelected() in inventory-list.js"          # T010
Task: "Extend row-action link assertions in tests/unit/test_routes.py"  # T011
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 — baseline and #107 reproduction.
2. Phase 2 — the hand-off plumbing.
3. Phase 3 — US1.
4. **STOP and VALIDATE**: quickstart Steps 1-3. Issue #106 is closed from both entry points.

### Incremental Delivery

1. Setup + Foundational → plumbing ready, nothing user-visible.
2. US1 → issue #106 closed → **MVP**.
3. US2 → issue #107 closed. The other half of the reported pain, and the highest-value increment after the MVP.
4. US3 → single-item Move. Nearly free once US1 exists.
5. US4 → single-item Shorten. The last dead link.

### If scope must be cut

US1 alone closes the reported issue and is a defensible stopping point. US2 is the one to keep
next — it strands a whole session's manual work. US3 and US4 are the smallest increments and the
easiest to defer, but deferring them leaves dead links that look identical to working ones,
which is the trap this feature exists to remove.

---

## Notes

- Commit after each task or logical group. Non-trivial code change → `issues/106` → PR (Principle: Development Workflow).
- Never run `nox -s e2e` in the foreground: most agent Bash tools cap at 10 minutes and the suite no longer fits. `nohup` and poll.
- No schema change ships with this feature, therefore no Alembic revision. If one seems necessary, the design has drifted — re-read [data-model.md](./data-model.md).
- Match the surrounding file's style; do not refactor working code gratuitously (Technology Constraints).
- American spelling throughout: `catalog`, never `catalogue`.
