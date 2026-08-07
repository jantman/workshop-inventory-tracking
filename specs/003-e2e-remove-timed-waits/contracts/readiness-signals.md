# Contract: Readiness Signals

**Feature**: `specs/003-e2e-remove-timed-waits` | **Date**: 2026-08-06 | **Satisfies**: FR-006, FR-019

The interface this feature depends on is not an API — it is the set of observable properties a test
may treat as proof that an action finished. Every replacement wait must cite a row from this
document (FR-006). Every pattern that survives into the relocated guidance (FR-019) is drawn from it.

Derived from [research.md](../research.md). Two rules govern the whole document:

> **A signal must not be able to be true before the work it certifies has completed.**
> **One user action may have more than one completion. Wait for all of them.**

---

## 1. Move page — `app/static/js/inventory-move.js`

| After the user enters | Wait for | Not this |
|---|---|---|
| A JA ID, from state `ja_id` | `#scanner-status` → `Waiting for Location` | the queue — nothing was queued |
| A location | `#scanner-status` → `Waiting for JA ID or Sub-Location` | the queue — still nothing queued |
| A sub-location | `#queue-count` → `N item(s)`, or the `#queue-items` row for that JA ID | `#scanner-status`, which changed before the fetch resolved |
| **A JA ID, from state `ja_id_or_sub_location`** | **both** `#queue-count` → `N` **and** `#scanner-status` → `Waiting for Location` | either one alone |
| `>>DONE<<` | `#queue-count` → `N` | `Done - Ready to Validate` — unreachable on the one-pending-move path, see the defect note in research.md §B |

The fourth row is the one that matters. That keystroke starts a new move synchronously and finalises
the previous one asynchronously; the status badge reports the first while the second is still in
flight. Waiting on the badge alone passes on a fast machine and fails on a slow one.

**Barcode entry.** `press("Enter")` processes immediately. `fill()` alone leaves a 100ms scanner
debounce (`scannerDelay`) before `processInput()` runs — still observable, since `expect()` polls,
but tests should press Enter as they do today.

**Queue rows are not ordered by scan order** in the finalise-previous case: the previous move is
pushed after its fetch resolves, which can be after a later move's. Assert on the row for a JA ID
(`#queue-items tr:has-text('JA000102')`), never on row index.

---

## 2. Photo upload — `app/static/js/photo-manager.js`

| After | Wait for | Why |
|---|---|---|
| `set_input_files`, one file, **edit page** | `.photo-card` count reaching N | `processSingleFile` awaits the POST *before* appending the card (line 303). A rendered card cannot predate a completed upload. |
| `set_input_files`, multiple files | the above **plus** `.photo-upload-progress` regaining `d-none` | `hideUploadProgress()` runs after the whole loop, not per file |
| `set_input_files`, **add page** (no item id yet) | `.photo-card` count, then `.photo-meta` no longer containing `Uploading...` | No item id means no POST; the card renders immediately with `uploaded: false` |
| Page load with existing photos | `.photo-count` reaching the expected number | `loadExistingPhotos()` is async |

**The same DOM means different things on the two pages.** `• Uploading...` is reachable only where
`currentItemId` is null. A helper shared by both pages must be told which it is on, or must wait on
`.photo-card` — which is correct in both.

## 3. Photo clipboard — copy / paste

| After | Wait for |
|---|---|
| Checking an item's checkbox | `#copy-photos-btn` / `#paste-photos-btn` reaching their expected enabled state |
| Opening the Options dropdown | the menu visible |
| Copy | the clipboard banner visible |
| Paste | the toast visible, asserted by its text |
| Clear clipboard | the banner not visible |

**Button state is the signal, and it must be asserted with `expect()`, not read.**
`assert not page_object.is_copy_photos_button_enabled()` is a snapshot read (Rule 3) — it returns
whatever is true at that instant, which is why these tests needed a cushion in front of them.
Replace with `expect(locator).to_be_disabled()`, which polls.

---

## 4. General patterns

These are the reusable shapes, stated so they can move into the standing guidance under FR-019.

**Pattern A — the awaited-fetch boundary.** When a handler is `async` and awaits a request before
mutating what you can see, everything set *before* the await is useless as a completion signal and
everything set *after* it is valid. Read the handler and find the `await`; signals on the near side
lie.

**Pattern B — one action, two completions.** When a handler starts new work synchronously and
finishes old work asynchronously, no single condition covers the action. Wait for both, in one
`expect()` each. This is `inventory-move.js`'s finalise-previous branch, and it is the failure mode
that survives casual testing because the race is usually won.

**Pattern C — the render-implies-completion shortcut.** When the code appends a DOM node *after*
awaiting the work, the node's existence is a complete signal and nothing further is needed. This is
`photo-manager.js` line 303. It is the cheapest correct wait available; look for it first.

**Pattern D — a state badge is per-transition, not per-action.** A single element that reports "what
the page is waiting for next" is a valid signal for the transitions that set it synchronously and a
trap for those that do not. Map the states before trusting it.

**Pattern E — a cushion in front of a snapshot read is load-bearing.** If a fixed wait sits before
`count()`, `text_content()`, `is_visible()` or a boolean helper wrapping one, the wait is holding the
read up, not the application. Converting the wait without converting the read moves the failure, it
does not fix it.
