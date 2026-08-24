# Verification: Fix the item hand-off into Move and Shorten

**Feature**: `specs/026-fix-bulk-move-handoff` | **Branch**: `issues/106`

The evidence tasks T001, T002, T003 and T046 asked for, recorded as they were taken.

---

## T001 — Green baseline, before any edit

Taken on `issues/106` at `efb22c5`, with no source file modified.

| Gate | Result | Wall clock |
|---|---|---|
| `venv/bin/nox -s tests` | **1683 passed**, 638 deselected, 49 warnings | 30.39s (65s including venv setup) |
| `venv/bin/nox -s e2e` | **615 passed**, 1706 deselected, 229 warnings | **770.29s (12:50)**; 791s including venv setup |

The e2e figure is consistent with the ~13m45s in `CLAUDE.md`. The slowest entry is
47.45s of *setup* on the first test (container start plus Playwright), not a slow
test; the slowest actual call is 11.77s and everything below the top three is
under four seconds.

The working tree was clean after the run — no screenshot test leaked into the
session (Principle IV).

---

## T002 — Reproducing issue #107

Driven through the real page by `tests/e2e/test_repro_107.py`, a temporary
diagnostic deleted once this record was written. Three sequences were run,
because [research.md](./research.md) R3 lists three code paths that produce the
report and the report itself does not distinguish them. Every step recorded the
queue badge, the `#form-alerts` text, whether `#validate-btn` was enabled, and
`moveQueue.length` / `currentExpectedInput` from the page.

### Sequence 1 — quickstart Step 0 verbatim: 14 pairs, each terminated by Enter

**Does not reproduce.** The session completes cleanly.

| Step | queue | badge | state | validate | alert |
|---|---|---|---|---|---|
| load | 0 | 0 items | `ja_id` | disabled | — |
| pair 1: `JA100001` | 0 | 0 items | `location` | disabled | — |
| pair 1: `M1-A` | 0 | 0 items | `ja_id_or_sub_location` | disabled | — |
| … | | | | | |
| pair 14: `M14-A` | 12 | 12 items | `ja_id_or_sub_location` | disabled | — |
| `>>DONE<<` | **14** | **14 items** | `ja_id` | **enabled** | `Finalized last entry without sub-location.` |

This is what R3 predicted: reading the workflow, `>>DONE<<` *should* work, and it
does. The queue trails the scan by up to two because `finalizeCurrentMove()`
pushes on the far side of a fetch, which is expected and harmless.

### Sequence 2 — the same 14 pairs with **no** trailing newline (Candidate C)

**Does not reproduce.** Identical outcome: 14 queued, `#validate-btn` enabled.

The 100 ms fallback timer fires once per scan, after the last character, and
`processInput()` sees the complete barcode. Candidate C's *fragmentation* variant
needs an inter-character gap longer than 100 ms, which a keyboard-wedge scanner
does not produce and which a test could only create with a fixed delay. So the
fallback path itself is sound; what was true is that no test had ever executed
it. `test_move_long_session.py` now does (FR-021).

### Sequence 3 — a JA ID arriving while a location is expected (Candidate B)

**Reproduces the report exactly.**

| Step | queue | badge | state | `currentJaId` | validate | alert |
|---|---|---|---|---|---|---|
| `JA100001` | 0 | 0 items | `location` | JA100001 | disabled | — |
| `JA100002` | 0 | 0 items | **`location`** | **JA100001** | disabled | `Expected location but received JA ID…` |
| `JA100003` | 0 | 0 items | **`location`** | **JA100001** | disabled | `Expected location but received JA ID…` |
| `>>DONE<<` | 0 | 0 items | `ja_id` | null | **disabled** | **`Please enter a value`** |

Three things are visible here, and together they are issue #107:

1. **The machine wedges.** `inventory-move.js:207-210` warns and returns without
   changing state, so `currentExpectedInput` stays `location` and
   `currentJaId` stays on the *first* item forever. Every subsequent JA-ID scan
   bounces off it. Nothing is ever queued — which is how Candidate B feeds
   Candidate A.
2. **Repeated refusals are invisible.** `showAlert()` assigns
   `formAlerts.innerHTML`, so the second and third refusals replace the first
   rather than accumulating. Fourteen failed scans look exactly like one.
3. **The one message that explained anything is destroyed.** `>>DONE<<` reaches
   `handleDoneCode()`, which says `Partial entry cleared…` and then
   `No items in move queue. Add some items before finishing.` — and then the
   scanner's Enter arrives at `processInput()` with a field
   `handleBarcodeInput()` has already emptied, and overwrites both with
   **`Please enter a value`**. That is the last thing the user sees after
   scanning `>>DONE<<`, and it is the spurious warning FR-016 names.

So the user's report — "`>>DONE<<` doesn't change anything" — is accurate, and
the reason it changes nothing is that there was nothing to change: the queue was
empty from the first missed location onward, and every message that would have
said so was overwritten by the next one.

### T003 — Classification

**Candidate B, feeding Candidate A, with the alert-overwrite property masking
both and Candidate C's Enter-after-`>>DONE<<` path overwriting the last
explanation.** Candidate C's fragmentation variant is not implicated.

No revision of User Story 2's acceptance scenarios is required: all five hold
against this trace. Every numbered item of R3's bounded fix strategy is
warranted by the evidence above, and each maps to a task —

| Evidence | Fix | Task |
|---|---|---|
| State unchanged at `inventory-move.js:207-210` | Resolve rather than bounce | T029 |
| Second and third refusals replaced the first | Accumulate alerts | T030 |
| `Please enter a value` after `>>DONE<<` | Suppress the spurious warning | T032 |
| Button disabled with no stated reason | Say why validation is unavailable | T033 |

T031 asked for "the fix indicated by the classification, bounded". The
classification indicates the wedge, which is T029; T031 therefore adds nothing
beyond it and is marked complete by T029's implementation rather than by a
separate change. No state-machine rewrite, no configurable `scannerDelay`, and
the buttons are still **not** enabled merely because the queue is non-empty —
`updateButtonStates()` continues to require that nothing is half-entered.

---

## T042 / T046 — the gates after the change, and the e2e delta

| Run | Result | Wall clock |
|---|---|---|
| `nox -s tests`, baseline | 1683 passed | 30.39s |
| `nox -s tests`, after | **1713 passed** (+30) | 27.10s |
| `nox -s e2e`, baseline | 615 passed | 770.29s (12:50) |
| `nox -s e2e`, after | **637 passed** (+22), 0 reruns | **819.81s (13:39)** |

**+22 tests, +49.5s.** Roughly 2.25s per added test, which is the suite's own
average — the added tests are not slow, there are simply more of them. That
leaves about 80 seconds of margin against the 15-minute figure in `CLAUDE.md`,
so T025's fourteen-pair count did not need reducing. It is the thing to reduce
first if that margin is ever threatened; the wait discipline is not, because
there is none left to remove.

The active-status and item-history e2e tests pass (Principle VI is engaged —
this touches move and shorten), and no test needed a rerun.

## T041 / T043 — wait discipline and a clean tree

```console
$ grep -rn "wait_for_timeout\|time\.sleep\|networkidle" tests/e2e/
tests/e2e/test_server.py:125:                time.sleep(0.1)
```

One match, unmodified by this feature and not a test wait: it is the poll
interval inside `LiveServer._wait_for_server()`, which retries `GET /health`
until the fixture's server answers. No `wait_for_timeout`, no `networkidle`, and
no new fixed wait anywhere. The suite still executes zero.

`git status` after the e2e run showed only this feature's own edits — no
screenshot leaked into the session.

## T044 — documentation screenshots: churn measured, none committed

`app/templates/**` and `app/static/js/**` changed, so the screenshots were
regenerated with `nox -s screenshots_headless` (22 passed, 1 skipped) and
verified with `nox -s screenshots_verify` (all 22 under the 500KB limit, all
valid RGB PNGs).

Nineteen files then showed as modified. Regenerating a **second** time, with no
code change in between, changed eight of those nineteen again — including both
of the pages this feature touches. So the churn was quantified directly:

| Comparison | Differing pixels |
|---|---|
| `move_items.png`: committed vs regenerated | 3976 / 2073600 (0.19%) |
| `move_items.png`: regenerated vs regenerated again | 3910 / 2073600 (0.19%) |
| `shorten_items.png`: committed vs regenerated | 2814 / 2073600 (0.14%) |
| `shorten_items.png`: regenerated vs regenerated again | 2748 / 2073600 (0.13%) |

The difference attributable to this feature is indistinguishable from the
difference between two identical runs: it is font rasterization, not content.
That is expected — the preselected-items card only renders when items are handed
over, and the validate hint is empty text until an item is half-entered, so
neither page looks different in the state the screenshots capture.

**No screenshot was committed.** Nothing blocks on staleness: the CI job that
diffed regenerated screenshots was replaced with an informational reminder in
issue #77 for exactly this nondeterminism. Committing nineteen binary files, of
which eight are pure noise and none carries a visible change, would add diff
weight and no information.

## T047 — quickstart walked end to end

Every step of [quickstart.md](./quickstart.md) is now driven by a test that runs
in `nox -s e2e`, rather than by a one-off manual pass that nothing preserves.

| Quickstart step | Covered by |
|---|---|
| 0 — reproduce #107 | recorded above; the diagnostic harness has been removed |
| 1 — bulk move from the inventory list | `test_bulk_move_from_list_carries_every_selected_item` |
| 2 — the same from Search | `test_bulk_move_from_search_behaves_identically` |
| 3 — mixing, and sub-locations | `test_hand_scanning_continues_into_the_same_batch`, `test_group_sub_location_applies_to_every_item` |
| 4 — long scanning session, and the wedge | `test_fourteen_pairs_can_be_validated_and_executed`, `test_a_ja_id_while_a_location_is_expected_resolves_the_machine` |
| 5 — scanner without a trailing newline | `test_a_scanner_without_a_trailing_newline_behaves_identically` |
| 6 — single-item row actions | `test_row_move_action_hands_off_one_item`, `test_row_shorten_action_identifies_the_item` |
| 7 — rejections and edge cases | the eight tests from `test_a_nonexistent_id_is_named_and_the_rest_proceed` to `test_clearing_the_queue_after_a_hand_off_leaves_the_page_usable` |
| 8 — regression and gates | T041, T042, T043, T044 above |

Steps 1, 2 and 6 operate the real control (FR-019). The three tests under step 7
that build a URL do so deliberately and say why at the call site: they exercise
the receiving page's rejection reporting, a state no sequence of clicks can
produce, and the convention itself is pinned separately by
`test_the_hand_off_url_uses_the_one_convention`, which drives both bulk
producers and asserts on the URL each one emits.
