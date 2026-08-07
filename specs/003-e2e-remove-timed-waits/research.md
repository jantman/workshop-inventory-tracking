# Phase 0: Assessment

**Feature**: `specs/003-e2e-remove-timed-waits` | **Date**: 2026-08-06 | **Satisfies**: FR-005, FR-006

Two questions had to be answered before any test could be edited. Where is the remaining wait time
actually spent? And what can a test observe at the points where `test_move_items_sub_location.py`
and the photo files currently wait on a clock — the question FR-005 requires answered *in writing*
before those files are touched, because the previous attempt answered it by guessing three times.

---

## A. Where the time is

The issue and the prior spec both describe the move file as the biggest single win, on the strength
of its 42 call sites. By site count that is true. By time it is not, and the difference changes the
order the work should be done in.

Literal argument sums, counted from the tree on 2026-08-06:

| Population | Sites | Literal | Share of literal |
|---|---:|---:|---:|
| **A — ordinary in-gate files** (17 files) | 42 | 37.9s | 62% |
| **B1 — `test_move_items_sub_location.py`** | 42 | 10.2s | 17% |
| **B2 — photo upload / copy** (3 files) | 15 | 13.1s | 21% |
| **In-gate total** | **99** | **61.2s** | 100% |
| C — `test_screenshot_generation.py` (excluded from gate) | 28 | 20.0s | n/a |

The gate's literal total is 61.2s but its measured cost is **121.6s across 212 executions** — 99
sites producing 212 executions, a 2.14× amplification that comes entirely from sites living inside
helper methods, which run once per call rather than once per file.

> **Baseline re-confirmed against the current tree (T003, 2026-08-06.)** The probe was rebuilt and
> run over an unchanged tree with `--reruns=0`: `Page.wait_for_timeout` **121.1s across 212
> executions**, suite wall clock **587.66s (9m 47s)**, 362 passed. That is within measurement noise
> of the 121.6s figure above, so every target stated in this feature stands as written. The other
> blocking categories, for context: `Page.goto` 95.7s (n=567), `wait_for_function` 11.0s (n=213),
> `wait_for_load_state` 4.7s (n=567), `wait_for_selector` 0.3s (n=29).
>
> The per-site breakdown confirms the population split by *measured* time, not literal argument:
> Population A ≈ **84.0s**, `test_move_items_sub_location.py` ≈ **10.2s**, the three photo files ≈
> **26.5s**. Population A is 69% of the gate's wait time, and removing it alone lands near 37s —
> under SC-001's 60s target.

### Measured after each change set

| Point | `wait_for_timeout` | Suite wall clock | Criterion |
|---|---|---|---|
| Baseline (T003) | 121.1s, n=212 | 587.66s (9m 47s) | — |
| After C1 — Population A (T024) | **36.9s, n=100** | 575.87s (9m 35s) | SC-001 met |
| After C2–C5 — everything (T057) | **0s, n=0** | **493.73s (8m 13s)** | SC-001 and SC-002 met |

The projection in §A held for wait time — 36.9s measured against ~37s projected — but *not* for
suite runtime at the C1 checkpoint, which barely moved (587.7s → 575.9s) even though 84s of
blocking had been removed. `Page.goto` had absorbed most of it: 95.7s at baseline, 158.1s after C1,
over an unchanged 567 navigations. Work that a fixed delay had been paying for out of its own
budget simply moved into the next navigation. It came back out once the remaining waits went:
`Page.goto` measured 103.9s on the final run, and total blocking time fell from 232.9s to 131.4s.

The lesson for the next person measuring this: **removing a wait does not always show up in the
clock immediately**, because the application still has the same work to do. It shows up when the
test stops asking for the work at a moment the application is not ready for it.

That amplification is not spread evenly, and where it lands matters:

- **`test_move_items_sub_location.py` amplifies at exactly 1.0×.** All 42 of its sites are inline in
  test bodies, one execution each. Its measured cost is therefore ~10.2s — **8% of the gate's wait
  time**, not the dominant share its site count suggests.
- **`test_copy_item_photos.py` amplifies at ~4.5×.** Six of its eight sites are in a helper class at
  the top of the file. Counting actual call sites: `select_item` ×11, `click_copy_photos_button` ×7,
  `click_paste_photos_button` ×4, `wait_for_toast` ×6, `click_options_dropdown` ×4 directly plus 11
  more indirectly. 3.1s of literal argument executes as **~13.9s**.
- **Population A therefore holds the remainder: ~87.5s, roughly 72% of the gate's wait time.**

### The consequence for sequencing

Removing Population A alone takes measured wait time from 121.6s to **~34s — already under SC-001's
60s target** — and suite runtime from ~585s to **~8m 30s, already inside SC-002's 8m 45s**.

Both performance criteria are reachable without touching either file group that was reverted last
time. That does not make the hard files optional: FR-001 and FR-003 require every site addressed,
and SC-003 requires zero unjustified survivors. But it means the risky work is **compliance work,
not performance work**, and it can proceed at whatever pace correctness demands without the
feature's headline numbers hanging on it.

This inverts the issue's implied ordering, which put the move file first as the biggest win.

**Decision**: Population A first, and measure immediately after it. **Rationale**: it is the largest
time win, carries the least risk, and converts the remaining work from "must succeed" to "must be
correct". **Alternative rejected**: move file first, per the issue's framing — it front-loads the
highest-risk work behind the smallest payoff, and a second revert would strand the whole feature.

---

## B. The move page's scan state machine

Source: `app/static/js/inventory-move.js` (751 lines). Observables confirmed against
`app/templates/inventory/move.html`.

### The three states

`currentExpectedInput` takes exactly three values, set synchronously:

| State | Reached by | Accepts |
|---|---|---|
| `ja_id` | initial, `clearAll()`, or a finalize with no override | a JA ID |
| `location` | `handleJaIdInput()` | a location (`M*`, `T*`/`T-*`, or exactly `Other`) |
| `ja_id_or_sub_location` | `handleLocationInput()` | a JA ID (finalises previous), or any other string (sub-location) |

Input is classified by pattern, not by prompt — `classifyInput()` at line 99. Anything that is not a
JA ID and not a location is a sub-location, which is why `Drawer 3` and `Storage Bin A` work.

### What is observable after each transition

This is the mapping FR-006 requires each replacement wait to cite. Four elements carry state, all
present in the template:

| Element | Set by |
|---|---|
| `#scanner-status` | `updateScannerStatus()` — a per-state badge |
| `#status-text` | `updateStatus()` — a sentence naming the value just scanned |
| `#queue-count` | `updateQueueDisplay()` — `"N item(s)"` |
| `#queue-items` | `renderQueueItems()` — one row per queued move |

| Transition | Synchronous? | Readiness signal to wait on |
|---|---|---|
| JA ID scanned, `ja_id` → `location` | **yes** | `#scanner-status` = `Waiting for Location`; `#status-text` contains the JA ID |
| Location scanned, `location` → `ja_id_or_sub_location` | **yes** | `#scanner-status` = `Waiting for JA ID or Sub-Location`; `#status-text` contains the location |
| Sub-location scanned (finalises current move) | **no — awaits `GET /api/items/{ja_id}`** | `#queue-count` reaching N; the `#queue-items` row for that JA ID |
| **JA ID scanned while in `ja_id_or_sub_location`** (finalises *previous*, starts *new*) | **half of each** | **compound — both** `#queue-count` reaching N **and** `#scanner-status` = `Waiting for Location` |
| `>>DONE<<` | depends — see the defect below | `#queue-count` reaching N |

### Why three attempts each surfaced a further race

The two facts that defeat a single-condition answer:

**1. `finalizeCurrentMove()` is `async` and awaits a fetch before it touches the queue.** Lines
295–358: it awaits `GET /api/items/{jaId}` to read the item's current location, and only then pushes
to `moveQueue` and calls `updateUI()`. So the queue is not a readiness signal for anything that
happens *before* that fetch resolves — and the barcode input, which `clearInput()` empties
synchronously, is not a readiness signal for anything that happens *after* it.

Neither of the two conditions the issue names is wrong about the page. They are each correct for a
different half of the transition.

**2. The finalise-previous branch splits one keystroke into two independent completions.** Lines
224–235: scanning a JA ID while in `ja_id_or_sub_location` calls `handleJaIdInput(value)`
*synchronously* — which immediately sets `#scanner-status` to `Waiting for Location` for the **new**
item — and then calls `finalizeCurrentMove(...)` **without awaiting it**, to queue the **previous**
one. The status badge therefore reports readiness for the next scan while the previous scan is still
in flight. A test that waits on `#scanner-status` here races the queue every time, and on a fast
machine wins that race often enough to look correct.

This is the shape US6 must document: *one user action, two completions, only one of them visible in
the obvious place.*

### Defect found: `handleDoneCode()` reads the queue before its own finalise lands

Lines 360–383. When `>>DONE<<` arrives in state `ja_id_or_sub_location`, the handler calls
`this.finalizeCurrentMove(null)` — again without `await` — and then immediately tests
`this.moveQueue.length === 0`. The push has not happened yet, so on a first move the test is true:

- the user sees a spurious **"No items in move queue. Add some items before finishing."** warning;
- the handler `return`s early, so `#scanner-status` never reaches `Done - Ready to Validate`;
- the status line never reports `Scan completed. N items queued`.

It self-corrects a moment later — when the fetch resolves, `updateUI()` runs `updateButtonStates()`,
which re-enables Validate — so the flow works and the current tests pass. They pass because they
assert on the queue table, and because a 200ms delay outlasts a local fetch.

Two live tests take this path today: `test_move_no_sub_to_no_sub` and `test_threaded_location_pattern`
(both scan `>>DONE<<` with one move pending and an empty queue).

**This blocks the natural conversion.** `Done - Ready to Validate` is the obvious thing to wait on
after `>>DONE<<`, and it is unreachable on exactly the path the tests use. A test can work around it
by waiting on `#queue-count` instead — which is what this plan does by default — but the workaround
is waiting for the right thing for the wrong reason, and the spurious warning is a real if minor
user-facing bug.

**Decision**: convert the tests against `#queue-count`, and raise the defect for the maintainer as a
separate, small, behavior-changing fix (`await` the finalise, then test the queue). **Rationale**:
FR-007 permits *additive* affordances, and this is not additive — it removes a wrong warning and
changes a status badge, so it is the maintainer's call, not the plan's. Feature 002 set the
precedent of fixing defects that removed waits exposed, but each of those was fixed in service of a
test that could not otherwise be written; this one has a working alternative. **Alternative
rejected**: fixing it silently as part of the conversion — it would put a user-visible behavior
change inside a commit labelled as test cleanup.

---

## C. The photo flows

Source: `app/static/js/photo-manager.js` (1000 lines).

### Upload — `test_photo_upload.py` (3 sites), `test_photo_upload_bug.py` (4 sites)

The chain from `set_input_files` is: `change` → `processFiles` → `processSingleFile` (per file) →
optional client-side compression → preview generation → `uploadPhoto` → gallery render.

The decisive line is **303**: `processSingleFile` does

```
if (this.currentItemId) { await this.uploadPhoto(photo); }
this.photos.push(photo);
this.addPhotoToGallery(photo);
```

The card is appended to the gallery **after** the upload POST has resolved. On the edit page, where
`currentItemId` is set, **the existence of `.photo-card` already proves the upload completed** —
there is no window in which a rendered card represents an un-uploaded photo. `expect(card)` is a
complete signal, and the 2000ms waits are pure cost.

The `• Uploading...` suffix in `.photo-meta` (line 470, rendered when `!photo.uploaded`) is only
reachable on the **add** page, where `currentItemId` is null and photos are staged locally without
a round trip. Same DOM, opposite meaning, decided by which page you are on — worth documenting,
because a helper shared between the two pages cannot use one rule.

For multi-file uploads the per-file signal is not enough: `hideUploadProgress()` and
`updateGalleryDisplay()` run only after the whole loop (lines 248–249). The batch-complete signal is
`.photo-upload-progress` regaining `d-none`, and `.photo-count` reaching the expected total.

**Decision**: single upload waits on `.photo-card` count; batch upload additionally waits on
`.photo-upload-progress` being hidden. **Alternative rejected**: waiting on `• Uploading...` to
disappear — correct on the add page, vacuous on the edit page, and a helper cannot tell which it is on.

### Copy / paste — `test_copy_item_photos.py` (8 sites)

**This file is not an async-flow problem.** Six of its eight sites are in a local helper class, and
each one has an obvious observable next to it:

| Helper | Wait | Signal available today |
|---|---|---|
| `select_item` | 300ms | `expect(copy_btn).to_be_enabled()` |
| `click_options_dropdown` | 200ms | `expect(menu).to_be_visible()` |
| `click_copy_photos_button` | 500ms | `expect(clipboard_banner).to_be_visible()` |
| `click_paste_photos_button` | 500ms | toast visible with its text |
| `click_clear_clipboard_button` | 300ms | `expect(banner).not_to_be_visible()` |
| `wait_for_toast` | 300ms after a `wait_for_selector` | `expect(toast).to_contain_text(...)` |

What broke it last time is almost certainly not the waits but **Rule 3**: the file asserts through
non-waiting snapshot reads — `assert not list_page.is_copy_photos_button_enabled()`, and
`is_checked()` inside `select_item`. Those return whatever the DOM holds at that instant. With a
300ms cushion in front they are reliable; without one they read stale state and fail. Removing the
wait without converting the read is the documented way to break this file, and matches the reported
symptom of six tests failing at once.

**Decision**: treat this file as Population A work with a Rule 3 pass, not as async-flow research.
Convert the boolean helpers to `expect()`-based assertions in the same change. **Rationale**: the
signals all exist; the defect is the read, not the wait.

---

## D. Screenshot generation

`test_screenshot_generation.py`, 28 sites, 20.0s literal — the largest single-file literal total in
the tree, and outside the gate. Its waits sit after navigation and before capture, so the conversion
is ordinary Rule 1 work against the same page objects the gate tests use.

The one risk is not timing but output: capturing earlier can catch a Bootstrap fade mid-transition.
`nox -s screenshots_verify` exists and is the check.

---

## Summary of decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Population A first, measure immediately after | Holds ~72% of wait time at the lowest risk; meets SC-001 and SC-002 on its own |
| D2 | Move file: per-transition signals, compound wait on the finalise-previous branch | Single conditions are each correct for half a transition; that is why three attempts failed |
| D3 | `handleDoneCode` defect raised, not silently fixed | It changes user-visible behavior; FR-007 covers additive affordances only |
| D4 | Upload waits on `.photo-card`; batch adds the progress container | The card cannot render before the POST resolves — line 303 |
| D5 | `test_copy_item_photos.py` reclassified as Population A + Rule 3 | Its signals all exist; the defect is snapshot reads, not the flow |
| D6 | No application change is required to meet any success criterion | Every needed signal already exists in the DOM |

**D6 is the headline.** FR-007 anticipated that the move page might need an additive readiness
affordance. It does not. `#scanner-status`, `#status-text`, `#queue-count` and `#queue-items` are
sufficient for every transition, provided the right one is used for each — and provided the
finalise-previous branch waits on two of them rather than one.
