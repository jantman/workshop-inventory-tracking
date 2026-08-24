# Phase 0 Research: Fix the item hand-off into Move and Shorten

**Feature**: `specs/026-fix-bulk-move-handoff` | **Date**: 2026-08-24

Three questions had to be answered before the design could be fixed: what the hand-off
convention should be, how a preselected group fits the Move page's existing state machine,
and what actually causes issue #107. The third took the most work and is the least settled.

---

## R1 — Hand-off convention

**Decision**: one query parameter, `ja_id`, carrying a comma-separated list, on both the
Move and Shorten pages. A single item is a list of one. `items` is dropped.

**Rationale**: `ja_id` is already what three of the four call sites use and is the only one
either receiving page could ever plausibly have honored, since it matches the single-item
convention used by the row actions and by the Shorten links asserted in
`tests/unit/test_routes.py:1123`. Choosing `items` would mean changing three call sites and
that unit assertion to save nothing. Neither name is load-bearing today — both are ignored —
so this is a free choice, and the tiebreak is "change the fewest call sites".

Accepting a list under a singular name is mildly ugly. It is still the right trade: one
convention that every entry point and both pages share is worth more than a name that reads
better in the single-item case and forces a second name for the plural one. The alternative
of supporting both names is exactly the speculative generality Principle I prohibits.

**Alternatives considered**:
- *`items` everywhere*: more call-site churn, breaks an existing unit assertion, no benefit.
- *Support both names*: two conventions is the condition that produced this bug.
- *POST a form instead of a link*: the row actions are anchors and the bulk actions are
  `window.location.href` assignments; converting them to forms is a larger change than the
  defect warrants, and a GET-addressable Move page is useful to keep.

**Bounds**: no limit is imposed on list length. The inventory is a hobby workshop's; a
selection large enough to trouble a URL is not a real case, and inventing a cap would be
scale machinery.

---

## R2 — Where a preselected group fits the existing state machine

**Decision**: add one state, `bulk_location`, entered only when the page loads with
preselected items. In it the page accepts a location (and then, via the existing
`ja_id_or_sub_location` state, an optional sub-location) and applies it to the whole group.
After the group is queued the machine lands in `ja_id`, which is its normal resting state,
and everything downstream — validation, execution, further hand scanning — is untouched.

**Rationale**: the existing machine is `ja_id → location → ja_id_or_sub_location → …`, and a
preselected group is precisely that flow with the JA-ID step satisfied for many items at once
instead of one. Modelling it as one additional entry state reuses the location classifier,
the sub-location handling, the queue rendering, the validation path and the execution path
without touching them. The queue entry shape does not change at all: the group produces N
ordinary queued moves that differ from scanned ones only in provenance.

**Consequence for FR-013**: preselected items are validated and executed by the same code as
scanned items because they *become* the same objects. That requirement is satisfied
structurally rather than by discipline.

**Alternatives considered**:
- *Queue the items immediately on load with a null destination and fill it in later*: makes
  every downstream consumer — rendering, validation, execution, the queue count — handle a
  half-built entry that cannot be moved. Spreads the special case across the file.
- *A separate modal that collects the destination before the page is usable*: a second UI
  path to the same outcome, and it blocks the user from mixing preselected and scanned items
  in one batch (FR-011).

**Bounds**: the group's destination is assigned once. Editing an individual row's destination
afterwards is out of scope per the spec, so no per-row edit affordance is added.

---

## R3 — What causes issue #107

**Decision**: treat the root cause as *not established*, fix the class of failure rather than
a single trigger, and make reproduction the first implementation task rather than an
assumption. Three independent paths through the current code produce the reported symptom
exactly; the report does not contain enough detail to distinguish them, and at least two are
worth closing regardless of which one the user hit.

**Why the obvious explanation is wrong**: reading the workflow, `>>DONE<<` *should* work. From
`ja_id_or_sub_location`, `handleDoneCode()` awaits `finalizeCurrentMove(null)`, which resets
`currentExpectedInput` to `ja_id`, and then sets `validateBtn.disabled = false` directly. A
late-resolving in-flight `finalizeCurrentMove` from an earlier scan cannot undo that: it calls
`updateButtonStates()`, which with a non-empty queue and state `ja_id` also enables the button.
So "14 clean pairs, then `>>DONE<<`" does not reproduce the report. Something upstream must
have gone wrong, which is why all three candidates below are about input never landing.

### Candidate A — the queue was empty the whole time

`handleDoneCode()` returns early before enabling anything:

```js
if (this.moveQueue.length === 0) {
    this.showAlert('No items in move queue. Add some items before finishing.', 'warning');
    return;                      // validateBtn stays disabled
}
```

This is the only path where `>>DONE<<` genuinely "doesn't change anything", and it matches the
report verbatim. It requires that not one of the 14 pairs was ever finalized.

### Candidate B — the state machine wedges in `location`

From `currentExpectedInput === 'location'`, a JA ID input is rejected **without a state
change** (`inventory-move.js:207-210`): it warns and clears the field. So one rejected location
leaves the machine expecting a location forever, and every subsequent JA-ID scan bounces off
it. There is no recovery except a valid location, Clear All, or `>>DONE<<`. Nothing is queued
while wedged, which feeds directly into Candidate A.

`isLocation()` accepts `M<digits>…`, `T-?<digits>…`, and exactly `Other`. Anything else — a
lowercase `m4-d`, a location naming scheme that does not start with M or T — is classified as
a sub-location and rejected in this state.

### Candidate C — the untested 100 ms scanner path shreds the input

`handleBarcodeInput()` arms `setTimeout(processInput, this.scannerDelay)` with
`scannerDelay = 100` on every keystroke, as a fallback for scanners that do not send a
newline. Enter cancels it, which is why this never fires in the test suite — every test scans
via `.type()` + `.press("Enter")` (`waits.py:61`, and `simulate_barcode_scan`). But if a
scanner's inter-character delay exceeds 100 ms, the timer fires **mid-barcode**: `processInput()`
runs on a fragment like `J`, classifies it as a sub-location, warns, and calls `clearInput()` —
so the remaining characters land in an emptied field and form garbage. Every scan fails, and
the queue stays empty, arriving again at Candidate A.

The 100 ms figure has no measurement behind it anywhere in the repository's history.

### The property all three share

The input pipeline can discard a scan silently. The only signal is `showAlert()`, which writes
`this.formAlerts.innerHTML = alertHTML` — **each alert replaces the previous one**, so 14 failed
scans display as one warning, and a `warning` never auto-dismisses (only `info` and `success`
do), so a stale message from an earlier failure looks like the current state. The queue badge
does read `0 items` throughout, but nothing draws the eye to it.

**Fix strategy** (bounded, and not a rewrite):
1. Reproduce first, at the reported scale, before changing behavior — otherwise the fix is
   guesswork and the test proves nothing.
2. Make the wedge impossible: a JA ID arriving in state `location` must resolve the machine
   rather than bounce, since it unambiguously means the previous item's location was missed.
3. Make failure legible: repeated rejections must accumulate rather than overwrite, so a user
   scanning into a wedged machine can see it.
4. Cover the no-newline input path in tests (FR-021), which is what let Candidate C hide.

**Explicitly not doing**: replacing the state machine, or making `scannerDelay` configurable.
A knob for a value nobody has measured is the speculative configuration Principle I prohibits;
if the timeout is wrong, the correct move is to find the right behavior, not to expose the
number.

**Alternatives considered**:
- *Just enable the buttons whenever the queue is non-empty*: treats the symptom, leaves the
  input loss that emptied the queue, and would let a user validate a batch missing items they
  believe they scanned. Worse than the bug.
- *Assume Candidate C and rewrite the scanner input handling*: the largest change of the
  three, justified by the least evidence.

---

## R4 — Closing the coverage seam (FR-019 to FR-022)

**Decision**: the hand-off tests drive the real control — select rows, open the Options menu,
click Bulk Move Selected — and assert on the Move page that follows. No test may reach a
receiving page by `page.goto` with a hand-crafted query string.

**Rationale**: navigating directly is precisely how every existing move test avoids the bug
(`test_move_items_basic.py:17`, `test_move_current_location_bug.py:21`, six call sites in
`test_data_loss_prevention.py`). A test that constructs the URL itself is testing the
receiving half against a URL the test author wrote, not against the one the application
produces — which is the exact defect here, where the two call sites disagreed and neither
matched what the page read.

`tests/unit/test_routes.py:1123` asserts a Shorten hand-off link is rendered. It stays, because
after this feature the link works, but it is not sufficient on its own and the e2e coverage
above is what actually holds the behavior.

**Waiting strategy**, per Principle IV and `CLAUDE.md`: the group-queueing action is a
render-implies-completion case (pattern C) — `finalizeCurrentMove` awaits
`GET /api/items/{ja_id}` before pushing, so the queue count reaching N is a complete signal
and no new wait helper is needed beyond what `waits.py` already provides. The arrival state
after the hand-off is server-rendered, so the preselected-item region must be established with
`expect(...)` before any count is read (pattern E).

**Scale test bounds**: FR-020's long session is 14 pairs, matching the report. At roughly the
per-scan cost of the existing move tests this adds well under a minute to a suite already at
~13m 45s against a 15-minute gate. If it measurably threatens the gate, the pair count is the
thing to reduce — not the wait discipline, which has none left to remove.

---

## R3 addendum — the reproduction, and which candidate it was

Added during implementation (task T003). The full trace is in
[verification.md](./verification.md); this is the conclusion it reached.

**Candidate B, feeding Candidate A.** Fourteen clean pairs do *not* reproduce the
report — neither with a trailing newline nor without one — exactly as this
section predicted. What reproduces it is a single missed location: a JA ID
arriving in state `location` is refused **without a state change**, so
`currentExpectedInput` stays `location` and `currentJaId` stays pinned to the
first item. Every later scan bounces off it, nothing is ever queued, and
`>>DONE<<` then takes Candidate A's early return because the queue is empty.

Two masking effects were confirmed at the same time, and they are why the user
could not see what had happened:

- Each refusal *replaced* the previous one, because `showAlert()` assigns
  `formAlerts.innerHTML`. Three refusals rendered as one.
- The scanner's Enter reached `processInput()` after `handleBarcodeInput()` had
  consumed `>>DONE<<` and emptied the field, so **`Please enter a value`**
  overwrote `No items in move queue` — destroying the only message that
  explained anything. This is FR-016's spurious warning, observed rather than
  assumed.

Candidate C's *fragmentation* variant is not implicated: the 100 ms fallback
timer fires once, after the last character, and `processInput()` sees the whole
barcode. What was true of that path is only that no test had ever executed it,
which FR-021 now closes.

All four numbered items of the fix strategy above stand, and none of them grew:
no state-machine rewrite, no configurable `scannerDelay`, and the buttons are
still not enabled merely because the queue is non-empty.
