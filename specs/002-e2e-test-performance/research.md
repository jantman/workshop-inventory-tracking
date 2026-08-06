# Phase 0 Research: E2E Test Suite Performance Assessment

**Feature**: `specs/002-e2e-test-performance` | **Date**: 2026-08-05 | **Satisfies**: FR-001, FR-002, FR-003, FR-009

This is the measured assessment the spec requires before any change is proposed. Every number
below came from a run on this machine, not from reading the code. Where static inspection and
measurement disagreed, measurement won — and it disagreed twice, materially.

## How the measurements were taken

| Run | Command | Purpose |
|---|---|---|
| Baseline | `nox -s e2e -- --durations=0 --reruns=0` | True per-phase cost, retries disabled |
| Subset probe | same + `-p tests.e2e._probe` on 6 files | Attribute test-body time to blocking calls |
| Pilot A subset | subset with change C1 applied | Measure C1's saving and breakage |
| Pilot B subset | subset with C1 + blanket wait removal | Find the ceiling and the risk |
| **Pilot A full** | full suite with C1 applied | **Authoritative full-suite saving** |

`tests/e2e/_probe.py` was a temporary pytest plugin that wrapped the Playwright `Page` methods
that block (`wait_for_timeout`, `wait_for_load_state`, `goto`, `wait_for_selector`,
`wait_for_function`) and accumulated wall clock per category. It has been removed from the repo;
a copy is retained in the session scratchpad. `--reruns=0` was used throughout so that retries
could not distort the timings.

All runs were warm: dependencies installed, Playwright browsers present, MariaDB image pulled.

## Finding 1 — The baseline is 22m 27s, not ~18m

```
376 passed, 1 skipped, 807 deselected in 1347.58s (0:22:27)
```

The issue reports ~18 minutes. On this machine, with retries disabled, it is **1347.58s**. The
gap is probably machine load or a warmer prior run; it does not change the analysis, but every
target below is stated against the measured 1347.58s so that before/after is comparable.

## Finding 2 — 92.5% of the time is inside test bodies, not setup

| Phase | Total | Share | Per-test mean |
|---|---|---|---|
| `call` (test bodies) | **1245.7s** | **92.5%** | 3.313s |
| `setup` | 90.8s | 6.7% | 0.242s |
| `teardown` | 6.4s | 0.5% | 0.020s |

Setup decomposes further:

- **45.94s one-time** — the first test's setup, covering MariaDB testcontainer start, Flask
  server start, and Playwright browser launch. Paid once per run.
- **44.9s total across the other 375 tests** — mean **0.120s** per test.

That 44.9s figure is the per-test database reset (`E2ETestServer.clear_test_data()`: ten table
deletes plus a 21-row taxonomy reseed, before every test).

**This overturns the spec's framing.** The spec's Current Baseline table called out the per-test
reset as a headline cost because it repeats 371 times. Measured, it is **3.3% of the run**.
Optimizing it — the transactional-rollback or seed-once scheme that looked obvious from reading
the code — could save at most ~45s and would put every test's isolation at risk to do it.
Constitution Principle I says optimization requires an observed problem. There isn't one here.
**Rejected.** See C4.

## Finding 3 — Over half of test-body time is spent blocking on the clock

Probe over a 6-file, 67-test subset (296.2s of call time, 23.8% of the suite's):

| Blocking call | Time | Calls | Mean | Share of subset call time |
|---|---|---|---|---|
| `wait_for_timeout(...)` | 101.9s | 116 | 0.879s | **34.4%** |
| `wait_for_load_state("networkidle")` | 53.7s | 115 | 0.467s | **18.1%** |
| `goto(...)` | 49.6s | 88 | 0.564s | 16.8% |
| `wait_for_selector` | 2.8s | 170 | 0.017s | 0.9% |
| `wait_for_function` | 0.1s | 5 | 0.022s | <0.1% |

`wait_for_timeout` + `networkidle` = **155.6s, or 52.5% of test-body time**, spent waiting on a
clock rather than on an observable condition. `goto` is real navigation and is irreducible.
`wait_for_selector` and `wait_for_function` — the condition-based idioms — cost almost nothing,
which is the whole point.

Two structural sources, both in shared infrastructure:

- `BasePage.wait_for_page_load()` ran `wait_for_load_state("networkidle")` after **every**
  navigation. Playwright's own documentation marks `networkidle` as discouraged for testing. It
  waits for a 500ms window of network silence, so it costs ≥0.5s every time even when the page
  was ready immediately.
- `BasePage.click_and_wait()` slept 0.5s and `BasePage.fill_and_wait()` slept 0.2s on every
  call, unconditionally, after operations Playwright already auto-waits for.

The suite is not short of the right idiom — it uses `expect()` 742 times. The clock-blocking is
concentrated in the page-object layer and in ad-hoc waits sprinkled through test bodies.

## Finding 4 — Static counting understates the real cost by 2.2×

The spec recorded ~192.1s of `wait_for_timeout`, obtained by summing the literal arguments at all
~220 call sites. Measured on the full suite, the actual cost is **423.9s across 479 executions**.

The discrepancy is call sites inside helpers: `AddItemPage.submit_form()` contains one
`wait_for_timeout(1000)` but runs once per item created, across dozens of tests. In the subset the
effect was starker still — 8.8s of static budget produced 101.9s of measured waiting.

Consequence: **the spec's 192.1s baseline and the SC-008 target derived from it are wrong** and
need restating against executions rather than call sites. This is exactly the failure mode the
"measured evidence rather than assertion" requirement exists to catch.

## Finding 5 — Removing the waits works, and the breakage is small and bounded

**Change C1** — replace `networkidle` with `domcontentloaded` suite-wide, delete the two
unconditional sleeps in `BasePage`, and fix the readiness gaps that exposes.

Measured on the full suite:

| | Baseline | After C1 | Δ |
|---|---|---|---|
| Wall clock | 1347.58s (22m27s) | **981.83s (16m21s)** | **−27.1%** |
| `call` | 1245.7s | 887.9s | −28.7% |
| Result | 376 pass / 1 skip | 370 pass / **6 fail** / 1 skip | 6 regressions |

The 6 failures are the important part. Every one is the same defect:

```
AssertionError: Locator expected to be visible
Actual value: None
Error: element(s) not found
```

- `test_admin_materials.py::test_material_status_toggle`
- `test_bulk_label_printing_list.py::test_bulk_label_printing_select_and_open_modal`
- `test_material_field_validation.py::test_edit_form_rejects_invalid_material`
- `test_material_field_validation.py::test_edit_form_accepts_valid_taxonomy_materials`
- `test_reorder_view.py::test_the_manual_flag_is_set_and_cleared_by_button`
- `test_touch_readiness.py::test_stock_status_is_settable_by_tapping`

These are assertions that read JavaScript-rendered content the instant the page loads.
`networkidle` was incidentally covering a real readiness gap — the spec's "a wait that was doing
real work" edge case, confirmed and quantified at **6 sites out of 377 tests**.

A seventh was found and fixed during the pilot: `InventoryTableMixin.assert_item_visible()` called
`get_table_items()`, which does a non-waiting `rows.count()` snapshot of a JS-populated table. It
broke 6 subset tests at once; replacing it with an auto-waiting `expect()` on the row locator
fixed all 6. This is the template for the remaining fixes — the cost is one small edit per site,
not a rewrite.

## Finding 6 — `wait_for_timeout` is the remaining lever, worth 423.9s

Full-suite probe **after** C1, showing what is left:

| Blocking call | Time | Calls | Mean | Share of remaining call time (887.9s) |
|---|---|---|---|---|
| `wait_for_timeout` | **423.9s** | 479 | 0.885s | **47.7%** |
| `goto` | 138.8s | 580 | 0.239s | 15.6% |
| `wait_for_load_state("domcontentloaded")` | 6.9s | 603 | 0.011s | 0.8% |
| `wait_for_selector` | 6.8s | 80 | 0.085s | 0.8% |
| `wait_for_function` | 0.8s | 43 | 0.020s | 0.1% |

Note `goto`'s mean dropped from 0.564s to 0.239s — removing `networkidle` sped up navigation
itself, not just the wait after it.

**Change C2** — replace each `wait_for_timeout` with a condition-based wait. The ceiling is the
full 423.9s.

Pilot B measured that ceiling by deleting the 34 standalone `wait_for_timeout` lines in the subset
wholesale:

| | Subset call time | Result |
|---|---|---|
| Baseline | 296.2s | 67 pass |
| C1 | 195.5s (−34.0%) | 67 pass |
| C1 + blanket deletion | **78.6s (−73.5%)** | **26 of 67 fail** |

So the time is genuinely recoverable — but **blanket deletion is not viable**. The 26 failures
clustered in `test_search.py` (6), `test_duplicate_item.py` (12), and `test_add_item.py` (2): JS
table population, modal open/close, and autocomplete debounce. Each removed wait needs its own
replacement condition. C2 is ~220 individual judgements, not a `sed` command.

## Finding 7 — The e2e gate runs the screenshot generator and dirties the working tree

The 16 tests in `test_screenshot_generation.py` carry both `@pytest.mark.screenshot` and
`@pytest.mark.e2e`, so `nox -s e2e` (which selects `-m e2e`) runs them. They are also run by the
dedicated `screenshots` and `screenshots_headless` sessions — the e2e gate is doing the work twice.

Worse, they write PNGs. After the baseline run:

```
 M docs/images/screenshots/metadata.json
 M docs/images/screenshots/user-manual/history_view.png
 M docs/images/screenshots/user-manual/search_results.png
```

**Running the test suite modifies tracked files.** That is a correctness problem independent of
speed. **Change C3** — select `-m "e2e and not screenshot"` in the `e2e` nox session. Cost: one
line. Saves 36.1s of call time plus per-test setup, and stops the pollution.

## Finding 8 — Run-to-run variance is real

`test_move_page_loads` took 0.89s at baseline and 30.21s in one pilot run; re-run in isolation it
took **0.42s**. Nothing about it changed. Individual outliers of this size mean single-test
comparisons prove nothing, and it is a standing argument for judging results on whole-suite wall
clock. It may also be what the existing `--reruns=3` is quietly absorbing.

## Decision: concurrency is not needed (resolves FR-009)

**Decision**: Keep the suite strictly serial. Do not introduce parallel execution.

**Rationale**: FR-009 requires concurrency to be recommended only if the serial-only changes fall
short of the target. They do not.

| Step | Basis | Projected wall clock |
|---|---|---|
| Baseline | measured | 1347.6s (22m27s) |
| after C1 | **measured, full suite** | 981.8s (16m21s) |
| after C2 at full ceiling | −423.9s (measured) | 557.9s (9m18s) — **−58.6%** |
| after C3 | −~40s (measured) | **~518s (8m38s) — −61.5%** |
| Conservative: C2 at 75% of ceiling | −318s | ~624s (10m24s) — **−53.7%** |

Both the optimistic and the conservative path clear the spec's 50% target, and the optimistic path
clears the ≤9-minute SC-001 target. Concurrency would add per-worker database isolation, a
harder-to-read failure report, and infrastructure that Principle I would otherwise reject —
to buy something already in hand.

**Alternatives considered**:

- *`pytest-xdist` with a schema per worker* — highest ceiling (a further 60–75%), but needs
  per-worker database provisioning, a per-worker Flask server or request routing, and a new
  dependency. Rejected: unnecessary given C1–C3, and it weakens User Story 2's failure
  localization, which the spec treats as co-equal with speed.
- *Reusing one browser context across tests* — would save part of the per-test context creation,
  but that is inside the 0.120s setup mean and therefore worth ≤45s total, at the cost of
  cookie/storage bleed between tests. Rejected: same reasoning as C4.
- *Reducing the 60s default page timeout* — affects only failing tests, so it cannot speed up a
  green run. Rejected as a performance measure; may still be worth revisiting for faster failure
  reporting, but that is not this feature.

## Corrections this assessment forces on the spec

1. **The per-test reset is not a headline cost.** It is 44.9s / 3.3%. The Current Baseline table
   implies otherwise. C4 rejects optimizing it.
2. **SC-008 is wrong.** It targets reducing "~192 seconds" of fixed waiting to under 20s. The real
   figure is **423.9s over 479 executions**, and the useful target is stated in executions, not the
   summed literal arguments. SC-008 needs restating.
3. **SC-003's "all 371 end-to-end test functions"** should read 377 collected (376 passing, 1
   skipped) — the spec's count came from a `grep` for `def test_`, which missed parametrization
   and class-based tests.
4. **SC-001's ≤9-minute target is achievable but has little slack** (~8m38s optimistic, ~10m24s
   conservative). Worth accepting as-is with the conservative figure understood, or relaxing to
   ≤10m for margin.
