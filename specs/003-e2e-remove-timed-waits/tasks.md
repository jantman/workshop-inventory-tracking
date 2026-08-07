---

description: "Task list for finishing the removal of time-based waits from the e2e suite"
---

# Tasks: Finish Removing Time-Based Waits from the E2E Suite

**Input**: Design documents from `/specs/003-e2e-remove-timed-waits/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/readiness-signals.md](./contracts/readiness-signals.md)

**Branch**: `issues/65`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- Every task names the exact file it touches

## Conventions for every conversion task

These apply to T006–T045 and are not repeated per task:

1. Replace each fixed wait with an `expect()` on the condition the *next* line depends on, citing a row from [contracts/readiness-signals.md](./contracts/readiness-signals.md) where one applies (FR-006).
2. A wait may survive only with a call-site comment naming the condition that cannot be observed (FR-001). Record every survivor in the ledger from T005.
3. Never leave a snapshot read (`count()`, `text_content()`, `is_visible()`, or a boolean helper wrapping one) where a removed wait used to hold it up — Pattern E. Convert the read too.
4. No assertion may be removed or weakened (FR-009). If an assertion has to move, it moves verbatim.
5. Run the file alone before moving on: `nox -s e2e -- tests/e2e/<file> --reruns=0`.

**Tests**: no separate test tasks. The test suite *is* the artifact under change; each conversion task is verified by running the file it converts.

---

## Phase 1: Setup — rebuild the instrument (C0)

**Purpose**: SC-001 cannot be measured until the probe exists. Nothing else can be evaluated first.

- [X] T001 Verify the environment: `export PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`, `source venv/bin/activate`, `docker ps` — per [quickstart.md](./quickstart.md)
- [X] T002 Rebuild the blocking-call probe at `tests/e2e/_probe.py` as a pytest plugin wrapping `wait_for_timeout`, `wait_for_load_state`, `goto`, `wait_for_selector` and `wait_for_function`, accumulating wall clock per category and printing a `BLOCKING-CALL PROBE` summary at session end. Do **not** commit it; only a stale `.pyc` of the original survives under `tests/e2e/__pycache__/`
- [X] T003 Re-confirm the baseline against the current tree: `nox -s e2e -- -p tests.e2e._probe --reruns=0 --durations=0`, expecting the `wait_for_timeout` line near **121.6s across 212 executions**. Record the actual figure in [research.md](./research.md) §A; if it has moved, restate every target below against what you measured

**Checkpoint**: the instrument works and the baseline is confirmed. `rm tests/e2e/_probe.py` after each use.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: capture what must be preserved, before anything is changed.

- [X] T004 Capture the pre-change assertion inventory for SC-005: `git diff main -- tests/e2e/ | grep -E "^-.*(assert |expect\()"` must stay empty-or-accounted-for throughout. Record the current collected count (`nox -s e2e -- --collect-only -q --reruns=0 | tail -3`, expecting **362 passing, 0 skipped**) in the ledger
- [X] T005 Create the survivor ledger as a working file at `/tmp/claude-1000/-home-jantman-scratch-rm-me-workshop-inventory-tracking/7c7d24f0-0d38-49d2-a0e6-f2e29fb91908/scratchpad/survivors.md`, tracking every one of the 127 sites with disposition `converted` / `justified` / `open` per [data-model.md](./data-model.md). It supplies SC-004's list and the final commit message

**Checkpoint**: what "no coverage lost" means is written down and measurable.

---

## Phase 3: User Story 1 — Ordinary in-gate files (Priority: P1) 🎯 MVP

**Goal**: convert 42 sites across 17 files — ~87.5s, about 72% of the gate's wait time.

**Independent test**: convert any one file, run it alone and in the full gate; the file passes, its assertions are unchanged, measured wait time drops by that file's contribution.

**⚠️ Constitution §VI guard**: T006, T013 and T021 touch files protecting the item lifecycle and history invariants. Change *how* they wait; never *what* they assert (FR-010).

- [X] T006 [P] [US1] Convert 5 sites in `tests/e2e/test_shorten_items.py` (lines 41, 310, 367, 409, 414) — **§VI guarded**, 5.2s literal, the largest single file in this story
- [X] T007 [P] [US1] Convert 4 sites in `tests/e2e/test_material_field_validation.py` (lines 100, 206, 225, 252) — the material validator marks the field invalid until its taxonomy loads; wait on the validator accepting the material, not on a delay
- [X] T008 [P] [US1] Convert 4 sites in `tests/e2e/test_item_actions.py` (lines 57, 211, 222, 322) — 4.5s literal
- [X] T009 [P] [US1] Convert 4 sites in `tests/e2e/test_duplicate_item.py` (lines 24, 42, 68, 619)
- [X] T010 [P] [US1] Convert 3 sites in `tests/e2e/test_move_items_with_original_thread.py` (lines 30, 177, 185) — move page; use [contracts/readiness-signals.md](./contracts/readiness-signals.md) §1
- [X] T011 [P] [US1] Convert 3 sites in `tests/e2e/test_label_print.py` (lines 25, 28, 38)
- [X] T012 [P] [US1] Convert 3 sites in `tests/e2e/test_bulk_creation.py` (lines 43, 56, 84) — genuinely slow behavior; do not make the test shallower to save time
- [X] T013 [P] [US1] Convert 2 sites in `tests/e2e/test_toggle_item_status.py` (lines 45, 135) — **§VI guarded**
- [X] T014 [P] [US1] Convert 2 sites in `tests/e2e/test_required_location.py` (lines 93, 132)
- [X] T015 [P] [US1] Convert 2 sites in `tests/e2e/test_multi_row_ja_id.py` (lines 53, 112) — 3.0s literal
- [X] T016 [P] [US1] Convert 2 sites in `tests/e2e/test_list_view_status_filter.py` (lines 152, 230)
- [X] T017 [P] [US1] Convert 2 sites in `tests/e2e/test_inactive_item_pagination.py` (lines 215, 230)
- [X] T018 [P] [US1] Convert 2 sites in `tests/e2e/test_add_item.py` (lines 345, 676) — form is the subject here, so drive the form (Rule 4 exemption)
- [X] T019 [P] [US1] Convert 1 site in `tests/e2e/test_product_search.py` (line 151)
- [X] T020 [P] [US1] Convert 1 site in `tests/e2e/test_move_items_basic.py` (line 91) — move page; use §1 of the signals contract
- [X] T021 [P] [US1] Convert 1 site in `tests/e2e/test_history_functionality.py` (line 141) — **§VI guarded**, 2.0s literal
- [X] T022 [P] [US1] Convert 1 site in `tests/e2e/test_admin_materials.py` (line 421)
- [X] T023 [US1] Run the full gate and confirm 362 pass with `--reruns=0`; run it three times per SC-006
- [X] T024 [US1] **Measure and stop to look**: re-run the probe (`nox -s e2e -- -p tests.e2e._probe --reruns=0 --durations=0`). Expect wait time near **~34s (SC-001 met)** and runtime near **~8m 30s (SC-002 met)**. Record both in [research.md](./research.md). If the projection holds, every remaining story is compliance work rather than performance work

**Checkpoint**: SC-001 and SC-002 should both be met here, with the two risky file groups untouched. This is the MVP.

---

## Phase 4: User Story 2 — The move page's scan flow (Priority: P1)

**Goal**: convert 42 sites in one file — the largest concentration, reverted once already.

**Independent test**: the file passes **ten** consecutive runs with zero retries (SC-007). A single green run is not evidence; the previous attempt's failure mode was intermittent.

**The mapping is already written** — [contracts/readiness-signals.md](./contracts/readiness-signals.md) §1 satisfies FR-005. Each wait must cite a row from it (FR-006).

- [X] T025 [US2] Convert **one** test only — `test_move_no_sub_to_no_sub` in `tests/e2e/test_move_items_sub_location.py` (lines 54, 58, 63, 80) — using `#scanner-status` for the two synchronous transitions and `#queue-count` after `>>DONE<<`. Do not proceed until T026 passes
- [X] T026 [US2] Run that one test ten times: `for i in $(seq 10); do nox -s e2e -- tests/e2e/test_move_items_sub_location.py::TestMoveItemsSubLocation::test_move_no_sub_to_no_sub --reruns=0 -q; done`. Any failure means the mapping is wrong — fix the map in the contract before writing more tests
- [X] T027 [US2] Convert the remaining single-move tests in `tests/e2e/test_move_items_sub_location.py`: `test_move_no_sub_to_with_sub`, `test_move_with_sub_to_no_sub_clears`, and the pattern tests at lines 366–453, using the sub-location row (`#queue-count`) and the two synchronous rows
- [X] T028 [US2] Convert the batch test at lines 290–364 in `tests/e2e/test_move_items_sub_location.py` — this is the **only** test exercising the finalise-previous branch (`JA000103` scanned while in `ja_id_or_sub_location`, line 320). It requires the **compound** wait: both `#queue-count` reaching N **and** `#scanner-status` returning to `Waiting for Location`. Assert queue rows by JA ID, never by index — the previous move can land after a later one
- [X] T029 [US2] Convert the 5 post-execution sites (`wait_for_timeout(500)` at lines 80, 131, 179, 231, 278, 348 commented "wait for database transaction to commit") — wait on the success alert or the cleared queue, not on the database
- [X] T030 [US2] Run `tests/e2e/test_move_items_sub_location.py` ten consecutive times with `--reruns=0` per SC-007
- [X] T031 [US2] Run the full gate three times (`for i in 1 2 3; do nox -s e2e -- --reruns=0 -q; done`); confirm no regression in the files T006–T022 touched

**Checkpoint**: the file that was reverted once now holds across ten runs.

---

## Phase 5: User Story 3 — Photo upload and clipboard (Priority: P2)

**Goal**: convert 15 sites across 3 files — ~23.9s, of which ~13.9s is helper amplification.

**Independent test**: all three files pass ten consecutive runs. The six tests that broke last time are the regression to watch.

- [X] T032 [P] [US3] Convert the 6 helper-resident sites in the page-object class at the top of `tests/e2e/test_copy_item_photos.py` (lines 32, 42, 48, 54, 59, 81) per §3 of the signals contract — these amplify ~4.5×, so this single task is most of the story's saving
- [X] T033 [US3] **Pattern E pass** on `tests/e2e/test_copy_item_photos.py`: convert every snapshot read the removed cushions were holding up — `is_copy_photos_button_enabled()`, `is_paste_photos_button_enabled()`, `is_clipboard_banner_visible()`, and the `is_checked()` assert inside `select_item` — to `expect()`-based assertions. **This, not the waits, is what broke this file last time**; T032 without T033 reproduces the failure
- [X] T034 [US3] Convert the 2 remaining inline sites in `tests/e2e/test_copy_item_photos.py` (lines 555, 565, both commented "wait for button state to update") to `expect(btn).to_be_enabled()` / `to_be_disabled()`
- [X] T035 [P] [US3] Convert 3 sites in `tests/e2e/test_photo_upload.py` (lines 80, 94, 268) — on the edit page `.photo-card` appearing already proves the POST resolved (`photo-manager.js:303`), so the 2000ms waits are pure cost
- [X] T036 [P] [US3] Convert 4 sites in `tests/e2e/test_photo_upload_bug.py` (lines 144, 163, 187, 217) — same signal; line 217 waits for existing photos to load, so use `.photo-count` reaching the expected number
- [X] T037 [US3] Confirm no helper in either photo file is shared between the add page and the edit page under a single rule — `• Uploading...` is reachable only where `currentItemId` is null. Wait on `.photo-card`, which is correct on both
- [X] T038 [US3] Run all four photo/copy files ten consecutive times with `--reruns=0` per SC-007
- [X] T039 [US3] Run the full gate three times (`for i in 1 2 3; do nox -s e2e -- --reruns=0 -q; done`), then re-measure with `nox -s e2e -- -p tests.e2e._probe --reruns=0` and record the figure in [research.md](./research.md)

**Checkpoint**: every in-gate site is now converted or justified.

---

## Phase 6: User Story 4 — Screenshot generation (Priority: P3)

**Goal**: convert 28 sites, 20.0s literal — the largest single-file total, outside the gate.

**Independent test**: `nox -s screenshots_headless` is faster and the images it produces are substantively equivalent to those committed.

- [X] T040 [US4] Convert all 28 sites in `tests/e2e/test_screenshot_generation.py` — ordinary Rule 1 work against the same page objects the gate tests use
- [X] T041 [US4] Run `nox -s screenshots_headless` then `nox -s screenshots_verify`; the risk is capturing a Bootstrap fade mid-transition, and `screenshots_verify` is the guard
- [X] T042 [US4] Confirm `git status --porcelain docs/images/screenshots/` is empty before and after `nox -s e2e` (SC-009); discard regenerated images with `git checkout -- docs/images/screenshots/` if unchanged in substance
- [X] T043 [US4] Confirm zero unjustified sites remain anywhere: `grep -rn -B3 "wait_for_timeout\|time\.sleep" tests/e2e/` — every hit either gone or preceded by a justification. `tests/e2e/test_server.py`'s polling loop is out of scope (FR-004)

**Checkpoint**: SC-003 met — the count of unjustified sites is zero, down from 127.

---

## Phase 7: User Story 5 — Retire the grandfather clause (Priority: P3)

**Goal**: remove guidance that has become false.

**Independent test**: nothing in the documentation set describes existing time-based waits as tolerated; feature 002's record no longer reports SC-008 as outstanding.

- [X] T044 [P] [US5] Remove the grandfathering caveat from `.specify/memory/constitution.md` §IV (lines 130–134), retaining only the exception for genuinely unobservable conditions. Bump the constitution version with a Sync Impact Report, as the 002 change did
- [X] T045 [P] [US5] Remove grandfathering language from `CLAUDE.md`'s "Writing e2e tests" section (line 24 onward)
- [X] T046 [P] [US5] Correct feature 002's record: `specs/002-e2e-test-performance/spec.md` SC-008 and `specs/002-e2e-test-performance/quickstart.md` lines 76–80, which currently report the criterion as unmet at 121.6s. State the achieved figure and reference this feature
- [X] T047 [US5] Verify: `grep -rni "grandfather" CLAUDE.md .specify/memory/constitution.md docs/ _bmad-output/` returns nothing (SC-011)

---

## Phase 8: User Story 6 — Encode what was learned, and move it (Priority: P3, final)

**Goal**: add guidance that has become true, and give it one home.

**⚠️ Gated on proof, not completion** (FR-020): begin only once T030, T038 and T023 have produced their evidence. Guidance written from the plan rather than the finished conversion records an expectation, and expectations here have been wrong twice.

**Independent test**: someone unfamiliar writes a new e2e test against a multi-step async flow using only `CLAUDE.md` and the constitution, with the old contract path unavailable.

- [X] T048 [US6] Move the practical guidance into `CLAUDE.md`, making it the normative source: the condition table, worked examples, the review checklist, and Patterns A–E from [contracts/readiness-signals.md](./contracts/readiness-signals.md) §4. Each pattern must name the situation it applies to and the observable condition it resolves to (FR-019)
- [X] T049 [US6] Confirm every pattern in `CLAUDE.md` traces to a real call site converted by T006–T040 (SC-012). A pattern with no call site behind it was invented rather than learned — delete it
- [X] T050 [US6] Reduce `.specify/memory/constitution.md` §IV to the governing rule only — the prohibition, its one exception, the justify-in-writing requirement — and point at `CLAUDE.md` for practice. No sentence may appear in both (FR-022, SC-015)
- [X] T051 [P] [US6] Repoint `docs/development-testing-guide.md:359` from the 002 contract to `CLAUDE.md`, keeping its summary
- [X] T052 [P] [US6] Repoint `_bmad-output/project-context.md:65` from the 002 contract to `CLAUDE.md`, keeping its summary
- [X] T053 [P] [US6] Repoint the docstring at `tests/e2e/waits.py:6` — **a source file, which a Markdown-only sweep misses**
- [X] T054 [US6] Supersede `specs/002-e2e-test-performance/contracts/e2e-test-authoring.md` so no maintainable second copy of the rules survives (FR-024). Git history preserves the original text, so the smallest option that leaves no followable stale rules is the right one
- [X] T055 [US6] Verify SC-014: `grep -rn "e2e-test-authoring" CLAUDE.md docs/ _bmad-output/ tests/ .specify/memory/` returns no hits pointing at the 002 path — all five live references repointed
- [X] T056 [US6] Verify SC-016: `grep -rn "002-e2e-test-performance" docs/development-testing-guide.md .specify/memory/constitution.md` still shows the historical citations at `docs/development-testing-guide.md:74` and `.specify/memory/constitution.md:14`. The move removed pointers to a source of rules, not the record of why the rules exist

---

## Phase 9: Polish & Cross-Cutting

- [X] T057 Final probe measurement per [quickstart.md](./quickstart.md); record the figure and the count of surviving justified waits (SC-001, SC-004). `rm tests/e2e/_probe.py`
- [X] T058 Three consecutive clean full-gate runs with `--reruns=0` (SC-006)
- [X] T059 Isolation sweep — every test alone against a clean environment (SC-008), using the `while read -r t` loop in [quickstart.md](./quickstart.md). Slow, well over an hour; run once before merge
- [X] T060 Confirm `grep -rn "networkidle" tests/e2e/ | wc -l` is still 0 (SC-010)
- [X] T061 Review the assertion diff one last time — `git diff main -- tests/e2e/ | grep -E "^-.*(assert |expect\()"` — with specific attention to `tests/e2e/test_shorten_items.py`, `tests/e2e/test_toggle_item_status.py` and `tests/e2e/test_history_functionality.py` (SC-005)
- [X] T062 Write the survivor list from T005's `survivors.md` into the final commit message, each entry naming the file, line and the condition that cannot be observed (SC-004)

---

## Dependencies

```text
Phase 1 (T001-T003)  ── the probe must exist before anything can be measured
        │
Phase 2 (T004-T005)  ── capture what must be preserved
        │
        ├─→ Phase 3  US1  (T006-T024)   P1  ← MVP; meets SC-001 and SC-002 alone
        │        │
        │        ├─→ Phase 4  US2  (T025-T031)   P1
        │        ├─→ Phase 5  US3  (T032-T039)   P2
        │        └─→ Phase 6  US4  (T040-T043)   P3
        │
        ├─→ Phase 7  US5  (T044-T047)   P3  ← independent of the conversions
        │
        └─→ Phase 8  US6  (T048-T056)   P3  ← GATED on T023, T030, T038 evidence
                 │
                 └─→ Phase 9  Polish (T057-T062)
```

**Story independence**: US1–US4 touch disjoint file sets and can be done in any order or concurrently. US5 touches only documentation and is independent of all of them. **US6 is the only story with a hard prerequisite** — its content is an output of US1–US4, so FR-020 forbids starting it early.

**Not a dependency**: [#67](https://github.com/jantman/workshop-inventory-tracking/issues/67), the `handleDoneCode()` ordering defect. T025–T029 wait on `#queue-count`, which is correct whether or not that bug is fixed.

## Parallel Execution

**Phase 3 is almost entirely parallel** — T006 through T022 are 17 different files with no shared state:

```bash
# All seventeen can proceed concurrently; each is verified by running its own file
nox -s e2e -- tests/e2e/test_shorten_items.py --reruns=0
```

**Phase 5**: T032 and T035/T036 are different files and parallel; T033 and T034 must follow T032 in the same file.

**Phase 8**: T051, T052 and T053 are three different files and parallel; T048 and T050 must be done together to satisfy the no-duplication rule.

**Phase 4 is deliberately serial.** T025 → T026 → T027/T028 exists to stop a second open-ended trial-and-error loop: prove the mapping on one test across ten runs before writing thirty more against it.

## Implementation Strategy

**MVP = Phase 1 + Phase 2 + Phase 3.** That is 24 of the 62 tasks and, per [research.md](./research.md) §A, it meets both SC-001 (~34s against a 60s target) and SC-002 (~8m 30s against 8m 45s) without touching either file group that was reverted last time.

Stop at T024 and measure. Everything after it is compliance work — required by FR-001 and SC-003, but no longer carrying the feature's headline numbers. That is what makes a second revert of the move file survivable.

**Suggested order after the MVP**: US3 before US2. US3 delivers ~24s against US2's ~10s, and its main risk (Pattern E snapshot reads) is now understood, whereas US2's is a race that has already defeated three attempts. The spec ranks US2 higher because it holds more *sites*; by time and by risk, US3 is the better next move.

## Task Summary

| Phase | Story | Tasks | Sites |
|---|---|---:|---:|
| 1 — Setup | — | T001–T003 (3) | — |
| 2 — Foundational | — | T004–T005 (2) | — |
| 3 | US1 (P1) | T006–T024 (19) | 42 |
| 4 | US2 (P1) | T025–T031 (7) | 42 |
| 5 | US3 (P2) | T032–T039 (8) | 15 |
| 6 | US4 (P3) | T040–T043 (4) | 28 |
| 7 | US5 (P3) | T044–T047 (4) | — |
| 8 | US6 (P3) | T048–T056 (9) | — |
| 9 — Polish | — | T057–T062 (6) | — |
| **Total** | | **62** | **127** |
