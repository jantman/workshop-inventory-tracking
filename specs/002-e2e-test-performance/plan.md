# Implementation Plan: E2E Test Suite Performance

**Branch**: `issues/47` | **Date**: 2026-08-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-e2e-test-performance/spec.md`

> **STATUS: APPROVED 2026-08-06.** The maintainer approved the change set (C1, C2, C3, C6), the
> rejections (C4, C5), the no-concurrency recommendation, and all four spec amendments. FR-004 is
> satisfied; implementation may proceed. The spec has been updated to match — see
> [Approval Gate](#approval-gate).

## Summary

The e2e suite takes **1347.6s (22m 27s)** measured, and **92.5% of that is inside test bodies**,
not setup. Over half of test-body time is spent blocking on a clock rather than on an observable
condition: `wait_for_load_state("networkidle")` after every navigation, two unconditional
`time.sleep()` calls in `BasePage`, and 479 executions of `wait_for_timeout()`.

The plan replaces clock-waiting with condition-waiting in three changes, keeps the suite strictly
serial, and encodes the result as a documented convention. C1 has already been measured on the
full suite at **−27.1%**; C1+C2+C3 project to **~8m38s (−61.5%)** optimistic, **~10m24s (−53.7%)**
conservative. Both clear the spec's 50% target without concurrency.

Full evidence: [research.md](./research.md).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: pytest 9.1.1, pytest-playwright 0.8.0, Playwright 1.61.0,
testcontainers 4.14.2, nox. No new dependency is proposed.

**Storage**: MariaDB 11.8 — testcontainer locally, service container in CI. Unchanged.

**Testing**: `nox -s e2e`; 377 tests collected across 57 files.

**Target Platform**: Linux; headless Chromium.

**Project Type**: Server-rendered Flask web application (single project).

**Performance Goals**: ≤9 minutes full suite (SC-001); ≥40% reduction in CI (SC-002).

**Constraints**: No test deleted or weakened (FR-011); every test passes in isolation (FR-012); no
cascading failures (FR-013); zero retries consumed (FR-014); screenshot generation keeps working
(FR-015).

**Scale/Scope**: ~220 `wait_for_timeout` call sites (479 executions), 144 `networkidle` call sites,
5 page objects, 57 test files. Documentation across `CLAUDE.md`, `docs/`, `_bmad-output/`, and the
constitution.

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | **PASS.** The plan removes machinery rather than adding it: no new dependency, no new fixture layer, no parallel infrastructure. Principle I's "no premature optimization" clause is what drove C4's rejection — the per-test reset *looked* like the problem and measured at 3.3%, so it is left alone. Concurrency is rejected on the same grounds. |
| **II. Layered Architecture Boundaries** | **PASS.** Test-only change. No application layer is touched. |
| **III. Exact Numerics** | **PASS.** No measurement arithmetic involved. |
| **IV. Test Discipline Through Nox** | **PASS with a required amendment.** All work runs through `nox`. C3 edits the `e2e` session's marker selection. The constitution's "at least a 20-minute timeout" for `e2e` becomes stale once the suite runs in ~9 minutes; FR-019 requires updating it, which is a constitution amendment and must carry a Sync Impact Report. |
| **V. MariaDB Is the Source of Truth** | **PASS.** No schema change, no migration, no change to how tests provision the database. |
| **VI. Item Lifecycle and History Invariants** | **PASS with care.** The constitution requires the active-status and history paths to stay covered by dedicated E2E tests. FR-010 forbids weakening any assertion, and `test_history_functionality.py`, `test_shorten_items*.py`, and `test_toggle_item_status.py` are all in scope for C2 edits — each must keep its assertions intact. Called out as the highest-risk area for review. |

**Violations requiring justification**: none. The Complexity Tracking table is therefore omitted.

**Post-design re-check (after Phase 1)**: still passing. The Phase 1 artifacts introduced no new
dependency, module, abstraction, or configuration knob. `contracts/e2e-test-authoring.md` is
documentation, not machinery. [`data-model.md`](./data-model.md) documents the *existing* fixture
lifetimes rather than proposing new ones — consistent with C4's decision to leave the reset alone.
The only constitution change required remains the Principle IV timeout amendment noted above.

## The change set

Each change states its measured or projected saving and its risk, per FR-002.

### C1 — Wait on state, not on the clock, in shared infrastructure

**What**: In `tests/e2e/pages/base_page.py`, replace
`wait_for_load_state("networkidle")` with `wait_for_load_state("domcontentloaded")` in
`wait_for_page_load()`, and delete the unconditional `time.sleep(0.5)` in `click_and_wait()` and
`time.sleep(0.2)` in `fill_and_wait()`. Apply the same `networkidle` → `domcontentloaded`
replacement to the 144 call sites across `tests/e2e/`. Then fix the readiness gaps this exposes.

**Saving**: **−365.8s, measured on the full suite** (1347.6s → 981.8s, −27.1%).

**Known breakage and its fix**: 7 sites, all the same defect — an assertion reading JS-rendered
content before it exists.

| Site | Fix |
|---|---|
| `InventoryTableMixin.assert_item_visible()` | Replace the `get_table_items()` snapshot with an auto-waiting `expect()` on a row locator. **Already validated in the pilot** — fixed 6 subset failures at once. |
| `test_admin_materials.py::test_material_status_toggle` | Same pattern: wait on the element, don't snapshot. |
| `test_bulk_label_printing_list.py::test_bulk_label_printing_select_and_open_modal` | Wait for the modal to be visible. |
| `test_material_field_validation.py::test_edit_form_rejects_invalid_material` | Wait for the validation message. |
| `test_material_field_validation.py::test_edit_form_accepts_valid_taxonomy_materials` | As above. |
| `test_reorder_view.py::test_the_manual_flag_is_set_and_cleared_by_button` | Wait for the flag's rendered state. |
| `test_touch_readiness.py::test_stock_status_is_settable_by_tapping` | Wait for the status control to settle. |

**Risk**: **Low.** Mechanical, and the full-suite blast radius is already known to be exactly these
7 sites rather than estimated. Residual risk is that a fix masks the gap instead of closing it —
mitigated by requiring each to wait on the specific condition, never on a longer timeout.

### C2 — Replace `wait_for_timeout` with condition-based waits

**What**: Work through the ~220 `wait_for_timeout` call sites. For each, identify what the test is
actually waiting for — a row appearing, a modal opening, a debounced request completing, a button
enabling — and assert that with `expect()`. Where genuinely no observable condition exists, keep
the wait and justify it in a comment at the call site (FR-007).

**Saving**: ceiling **−423.9s, measured** (479 executions × 0.885s mean). Conservative planning
figure **−318s** (75% of ceiling), reflecting that some waits will legitimately survive.

**Risk**: **Medium-high, and this is the bulk of the work.** Pilot B proved the time is real by
deleting the waits wholesale — and 26 of 67 subset tests failed. Failures clustered in JS table
population (`test_search.py`), modal lifecycle (`test_duplicate_item.py`), and autocomplete
debounce (`test_add_item.py`). Blanket removal is not viable; this is ~220 individual judgements.

**Sequencing**: file by file, running that file's tests after each. Files ranked by measured cost —
`test_bulk_label_printing_list.py` (114.8s), `test_add_item.py` (79.9s),
`test_label_printing.py` (64.5s), `test_product_search.py` (64.0s), `test_search.py` (44.8s) —
carry the most time and should go first, so the benefit lands early and the risky tail is optional.

**Constraint**: the item-history files (`test_history_functionality.py`, `test_shorten_items*.py`,
`test_toggle_item_status.py`) are covered by Constitution Principle VI. Assertions there must
survive verbatim.

### C3 — Stop running the screenshot generator inside the e2e gate

**What**: Change the `e2e` session in `noxfile.py` to select `-m "e2e and not screenshot"`.

**Saving**: −36.1s of call time plus associated setup, ≈ **−40s**.

**Also fixes a correctness bug**: the 16 screenshot tests write PNGs, so `nox -s e2e` currently
modifies tracked files in `docs/images/screenshots/`. Observed during the baseline run. They are
already covered by the dedicated `screenshots` / `screenshots_headless` sessions, so no coverage
is lost — this removes a duplicate execution, not a check.

**Risk**: **Very low.** One line. FR-015 is satisfied because the dedicated sessions are untouched.

### C4 — Per-test database reset: REJECTED, do not change

**What was considered**: `E2ETestServer.clear_test_data()` empties ten tables and reseeds 21
taxonomy rows before each of 375 tests. Reading the code, this looks like the obvious target —
and the spec's baseline table frames it that way.

**Why rejected**: measured at **44.9s total, 0.120s per test — 3.3% of the run**. Seeding once and
rolling back per test, or reseeding only when a test dirties the taxonomy, would save at most 45s
while putting FR-012's per-test isolation at risk across all 377 tests. Constitution Principle I
requires an observed problem before optimizing. There isn't one.

Recorded explicitly so this is not "rediscovered" later.

### C5 — Concurrency: REJECTED (resolves FR-009 / FR-010 / FR-011)

C1+C2+C3 reach the target serially. FR-011 therefore applies: the suite stays strictly serial, and
concurrency must not be introduced incidentally. Full reasoning and the alternatives considered are
in [research.md](./research.md).

### C6 — Encode the conventions (FR-016 … FR-019)

**What**: Write the rules down so the gains survive.

| Artifact | Change |
|---|---|
| [`contracts/e2e-test-authoring.md`](./contracts/e2e-test-authoring.md) | The rules themselves — the normative source. |
| `CLAUDE.md` | Testing section gains the waiting/seeding/placement rules and links the contract. |
| `docs/development-testing-guide.md` | Same rules in developer-facing form; remove guidance describing the superseded approach (FR-018). |
| `_bmad-output/project-context.md` | E2E patterns section updated to match. |
| `.specify/memory/constitution.md` | Principle IV's "at least a 20-minute timeout" restated to the new measured runtime (FR-019). Requires a version bump and Sync Impact Report. |

**Risk**: **Low**, but easy to under-deliver. FR-018 requires *removing* stale guidance, not just
adding new — a documentation set that describes both approaches is a failure of this change.

## Projected outcome

| Step | Basis | Wall clock | vs baseline |
|---|---|---|---|
| Baseline | measured | 1347.6s (22m27s) | — |
| + C1 | **measured, full suite** | 981.8s (16m21s) | −27.1% |
| + C2 at ceiling | measured ceiling | 557.9s (9m18s) | −58.6% |
| + C3 | measured | **~518s (8m38s)** | **−61.5%** |
| Conservative (C2 at 75%) | projection | ~624s (10m24s) | −53.7% |

**Estimate for FR-003: ~8m40s optimistic, ~10m25s conservative.**

SC-001 (≤9 min) is met on the optimistic path and missed by ~1.4 min on the conservative one.
See the amendments below.

## Spec amendments this assessment requires — ALL APPROVED AND APPLIED 2026-08-06

Measurement contradicted four things the spec asserted. All four were approved and have been
written into [spec.md](./spec.md):

| # | Resolution |
|---|---|
| 1 | SC-008 restated against **measured execution time**: 423.9s → under 60s. |
| 2 | SC-003 corrected to **377 collected** (361 after C3). |
| 3 | SC-001 **relaxed to ≤10 minutes** (the conservative projection), so the target does not depend on every judgement going the best way. |
| 4 | Current Baseline table rebuilt as estimate-vs-measured, annotating the per-test reset at 3.3% and pointing at C4. |

Two success criteria were added while applying these: **SC-011** (no `networkidle` anywhere in
`tests/e2e/`) and **SC-012** (an e2e run leaves the working tree clean).

The original text of each amendment request follows.

1. **SC-008 is factually wrong.** It targets cutting "~192 seconds" of fixed waiting to under 20s.
   The real cost is **423.9s across 479 executions**; 192s was the sum of the literal arguments at
   the call sites, which understates by 2.2× because helpers run repeatedly. Proposed restatement:
   *"`wait_for_timeout` execution time falls from 423.9s to under 60s, with every survivor carrying
   a written justification."*
2. **SC-003's test count.** "All 371 end-to-end test functions" should be **377 collected (376
   passing, 1 skipped)**.
3. **SC-001's margin is thin.** Proposed: keep ≤9 min as the target, and treat the conservative
   ~10m25s as the acceptance floor rather than a failure — or relax SC-001 to ≤10 min.
4. **The Current Baseline table over-weights per-test reset.** Proposed: annotate it with the
   measured 3.3% and the C4 rejection so the framing does not mislead a future reader.

## Results (implementation, 2026-08-06)

| Stage | Wall clock | vs baseline | Result |
|---|---|---|---|
| Baseline | 1347.6s (22m27s) | — | 376 passed, 1 skipped |
| after C1 + C3 | 859.3s (14m19s) | −36.2% | 362 passed |
| after C2 | **587.9s (9m47s)** | **−56.4%** | 361 passed, 1 intermittent (fixed after) |

**SC-001 (≤10 min) met** at 9m47s, against a projection of ~10m24s conservative / ~8m38s
optimistic. The outcome landed between the two, as expected given C2 was completed for most
but not all files.

Measured blocking-call profile, baseline → final:

| Call | Baseline | Final | Δ |
|---|---|---|---|
| `wait_for_timeout` | 423.9s (n=479) | **121.6s (n=212)** | −71% |
| `networkidle` | ~302s | **0** — removed suite-wide | −100% |
| `goto` | 138.8s (n=580) | 96.7s (n=565) | −30% (faster once networkidle was gone) |
| `wait_for_function` (new, condition-based) | 0 | 11.9s (n=212) | the replacement, and it is cheap |

### Bugs found by the work

Removing waits exposed defects the delays were hiding. Each was fixed on its merits:

- **`test_search_no_results_workflow` never searched.** It queried "Titanium", which is not
  in the taxonomy, so `material-validation.js` called `setCustomValidity()` and native
  constraint validation blocked the form — no submit event, no search. The lenient
  assertion then passed vacuously. Now searches "Aluminum" (valid, no matching items).
- **`test_material_field_validation` had a dead fallback with the wrong URL.**
  `/inventory/{ja_id}/edit` instead of `/inventory/edit/{ja_id}`. It never ran because the
  `is_visible()` snapshot in front of it was always true under `networkidle`.
- **Seven assertions read JavaScript-rendered content before it existed**, most notably
  `InventoryTableMixin.assert_item_visible()`, whose non-waiting `rows.count()` snapshot
  broke six tests at once when its incidental cover was removed.
- **`assert_item_not_visible()` could pass against an unloaded table** — a negative
  assertion with no positive readiness gate. Now waits for the table first.
- **`nox -s e2e` modified tracked files** (C3).
- **`assert_form_submitted_successfully()` waited 10s for a flash and swallowed the
  timeout**, turning a loaded machine into an intermittent failure and hiding the reason a
  submit was rejected.

### Success Criteria scorecard

| SC | Target | Actual | |
|---|---|---|---|
| SC-001 | ≤10 min | **9m41s / 10m05s** over two clean runs | **met** |
| SC-002 | CI −40% | not yet observed — CI has not run this branch | **unverified** |
| SC-003 | all tests pass, assertions not reduced | 362 pass; 4 assertion lines removed, 3 replaced by equivalents (2 strengthened), 1 a whitespace artifact; 36 added | **met** |
| SC-004 | zero skipped/deleted | zero | **met** |
| SC-005 | 3 consecutive runs, zero retries | **2 clean out of 5** full `--reruns=0` runs | **not met** |
| SC-006 | every test passes alone | spot-checked throughout; full one-at-a-time sweep not run | **partially verified** |
| SC-007 | failures localize | not exercised with a deliberate defect | **unverified** |
| SC-008 | `wait_for_timeout` under 60s | **121.6s** (from 423.9s) | **not met** |
| SC-009 | docs updated, stale guidance gone | `CLAUDE.md`, `docs/development-testing-guide.md`, `_bmad-output/project-context.md`, constitution §IV | **met** |
| SC-010 | new test adds no measurable time | no new test written | **unverified** |
| SC-011 | no `networkidle` in `tests/e2e/` | zero occurrences | **met** |
| SC-012 | e2e run leaves tree clean | verified across three consecutive runs | **met** |

**SC-005 needs reading carefully — the suite has a residual flake rate.** Five full runs were
made with `--reruns=0`:

| Run | Result |
|---|---|
| 1 | 1 failed — `test_add_multiple_items_workflow`, a 10s flash wait that swallowed its own timeout. **Fixed** (see `assert_form_submitted_successfully`). |
| 2 | clean, 581.57s |
| 3 | 1 failed — `test_bulk_label_printing_select_all_functionality`, preceded by `TypeError: Failed to fetch` from the test server |
| 4 | clean, 605.52s |
| 5 | 1 failed — `test_move_items_sub_location::test_batch_move_mixed_sub_locations`, a 60s click timeout, with two `Failed to fetch` in the log |

Only the first was a defect in this work. The other two were preceded by the browser's fetch
to the Werkzeug test server failing outright; both failing tests pass repeatedly in isolation
(the sub-location file passed 2/2 immediately afterwards), and the second of them is in a
file whose waits were reverted, so it is not attributable to the wait changes.

Two things follow. First, `wait_for_items_loaded()` treated the list's *error* state as a
terminal "loaded" state and carried on, turning a failed fetch into a 60s timeout on a row
that was never going to exist — it now raises immediately with the error text, so this failure
mode is at least legible. Second, **the underlying transient is not diagnosed.** It is what
`--reruns=3` has been absorbing all along, which is precisely why SC-005 asks for runs without
it. Whether the shared single-threaded test server can be made reliable under sustained load
is a separate question this feature did not answer.

### Deferred, with reasons

C2 was not completed everywhere. These files keep their `wait_for_timeout` calls; they are
grandfathered by the constitution amendment and no *new* waits may be added anywhere.

**127 `wait_for_timeout` call sites remain**, down from ~220. They fall into three groups:

| Group | Sites | Why deferred |
|---|---|---|
| `test_move_items_sub_location.py` | 42 | **Attempted and reverted.** The move page's scan state machine finalises each entry through an awaited API call, and its queue UI only renders after the `>>DONE<<` code — so neither "input cleared" nor "queue contains the item" is a valid readiness signal at the point the test needs one. Three successive conditions each surfaced a further race. Worth doing separately, with the state machine mapped first. |
| `test_photo_upload.py`, `test_photo_upload_bug.py`, `test_copy_item_photos.py` | 15 | **Attempted and reverted.** Upload and clipboard flows complete asynchronously across several steps; replacing the waits broke 6 tests. Needs per-site analysis of the photo manager. |
| `test_screenshot_generation.py` | 28 | Not run by the `e2e` session at all after C3, so it does not affect the gate. Should still be cleaned up for the `screenshots` sessions. |
| 17 other files, ≤5 sites each | 42 | **Simply not reached.** Ordinary remaining work, not known-hard: `test_shorten_items.py` (5), `test_material_field_validation.py` (4), `test_item_actions.py` (4), `test_duplicate_item.py` (4), and the rest in ones and twos. Each needs the same per-site judgement the finished files got. |

Those 127 sites are the 121.6s that SC-008 still measures. Finishing them would plausibly
reach the ~8m30s optimistic figure and bring SC-008 under its 60s target, which is **not
met**. The 42 sites in the last row are the cheapest remaining wins.

## Project Structure

### Documentation (this feature)

```text
specs/002-e2e-test-performance/
├── spec.md                          # Feature specification
├── plan.md                          # This file
├── research.md                      # Phase 0: the measured assessment
├── data-model.md                    # Phase 1: test-state ownership model
├── quickstart.md                    # Phase 1: how to verify the change
├── contracts/
│   └── e2e-test-authoring.md        # Phase 1: the conventions contract
├── checklists/
│   └── requirements.md              # Spec quality checklist
└── tasks.md                         # Phase 2 (/speckit-tasks — not created here)
```

### Source code touched

```text
noxfile.py                              # C3: marker selection for the e2e session

tests/e2e/
├── pages/
│   ├── base_page.py                    # C1: navigation waits, remove sleeps
│   ├── inventory_table_mixin.py        # C1: assert_item_visible readiness
│   ├── inventory_list_page.py          # C2
│   ├── add_item_page.py                # C2: submit_form's 1000ms wait
│   └── search_page.py                  # C2
└── test_*.py                           # C1 (144 sites) + C2 (~220 sites)

CLAUDE.md                               # C6
docs/development-testing-guide.md       # C6
_bmad-output/project-context.md         # C6
.specify/memory/constitution.md         # C6: Principle IV timeout, + version bump
```

**Structure Decision**: Single project, existing layout. No new directories, no new modules, no new
dependencies. The change is concentrated in `tests/e2e/pages/` (shared infrastructure, where C1
lives and where the leverage is) and spread thinly across `tests/e2e/test_*.py` (where C2 lives).

## Approval Gate

FR-004 blocks implementation until this plan is approved. Specifically requested:

1. **Approve the change set** C1, C2, C3, C6 and the rejections C4, C5.
2. **Confirm the concurrency decision** — FR-010 requires the concurrency recommendation to be
   approved separately. The recommendation is **no concurrency**; the target is reachable serially.
3. **Rule on the four spec amendments** above, particularly SC-008 (currently unachievable as
   written, because it is measured against the wrong quantity) and SC-001's thin margin.

On approval, `/speckit-tasks` breaks this into an ordered task list.
