# Phase 0 Research: Fix Add & Continue With Quantity Greater Than One

The spec deliberately says nothing about mechanism. This file records what the code actually does
today and the seven decisions that follow from it.

## Root cause, established

`app/templates/inventory/add.html:349` declares the continue button inside the form:

```html
<button type="submit" name="submit_type" value="continue" id="submit-and-continue-btn">
```

`app/static/js/inventory-add.js:76-81` wires two independent entry points to the same handler:

```js
this.form.addEventListener('submit', (e) => this.handleSubmit(e));
document.getElementById('submit-and-continue-btn').addEventListener('click', () => {
    this.handleSubmit(null, true);          // event is null
});
```

`handleSubmit` begins `if (event) { event.preventDefault(); }` (line 655). With `null` passed, the
click's default action is never suppressed, so pressing **Add & Continue** runs `handleSubmit`
**twice**: once from the click listener with `continueAdding = true`, then once from the `submit`
listener with `continueAdding = false`.

What each pass does depends on the quantity, checked at line 707:

| Quantity | Pass 1 (click, `continue`) | Pass 2 (submit) | Result |
|----------|---------------------------|-----------------|--------|
| 1 | appends `submit_type=continue`, calls `form.submit()` **synchronously** | navigation already underway | Works. The duplication is invisible **and load-bearing** — pass 1 is what makes continue work at all. |
| > 1 | `await fetch(...)` — POST #1 dispatched, handler yields | reaches the same branch, POST #2 dispatched | **Two concurrent bulk creations.** |

Both POSTs enter `_process_item_creation` (`app/main/routes.py:222`), which computes its starting
ID at line 314 as `service.get_max_ja_id_number() + 1`. There is no reservation between the read
and the writes, so the outcome depends on interleaving:

- **Collide** — both compute the same start, the loser fails every insert, the route returns 500
  with `Failed to create any items`, and the browser shows an error toast *next to* pass 1's
  success dialog. This is the error in issue #52.
- **Serialize** — pass 2 reads the max after pass 1 commits and creates a second full batch. No
  error at all, and the inventory silently gains 2N items. This is the worse outcome and the
  reason the spec leads with count correctness rather than with the error message.

Pressing plain **Add** does not reproduce it: `#submit-btn` has no click listener, so the `submit`
listener fires once. That asymmetry is the whole defect.

---

## D1 — One submission per user action: derive the button from `event.submitter`

**Decision**: Delete the click listener entirely. Keep both buttons as `type="submit"`. Read
which one was pressed from `event.submitter` inside the single `submit` listener:

```js
this.form.addEventListener('submit', (e) => this.handleSubmit(e));
// inside handleSubmit:
const continueAdding = event?.submitter?.value === 'continue';
```

**Rationale**: One listener on one event cannot double-fire — the failure mode is removed
structurally rather than patched. It also deletes code rather than adding it, which is what
Principle I asks for. `event.submitter` is the platform's own answer to "which button submitted
this form" and has been baseline in every major browser since 2021; the app targets one desktop
Chrome and the test suite runs Playwright's bundled Chromium.

Implicit submission (pressing Enter in a text field) sets `submitter` to the form's first submit
button, which is `#submit-btn` — so Enter means **Add**, which is the sensible default and matches
today's behavior.

**Alternatives considered**:
- *Pass the event through and `preventDefault()` in the click handler.* Fixes this instance but
  leaves two listeners racing for one action, so the next person to touch either one re-opens it.
- *Re-entrancy guard alone.* Insufficient on its own and subtly wrong: the `submit` listener would
  have to `preventDefault()` **before** hitting the guard, otherwise the early return lets the
  browser navigate natively and abort the in-flight `fetch`. Ordering that correctly is exactly
  the kind of non-obvious code the constitution warns against. Kept as a *second* line of defense
  (D2), not as the fix.
- *`type="button"` on the continue button.* Works, and was the first candidate. Rejected in favor
  of `event.submitter` because it leaves two handlers where one will do, and because a form whose
  buttons are not submit buttons loses implicit-submission semantics for no gain.

## D2 — Re-entrancy guard for repeated presses

**Decision**: Add an instance flag, set after `preventDefault()` and cleared in a `finally`:

```js
if (this.submitting) return;
this.submitting = true;
try { ... } finally { this.submitting = false; }
```

**Rationale**: D1 removes the *structural* double-fire, but a user can still press a button twice
before the first response lands. The buttons are disabled during flight (existing behavior at
lines 684-685), and a disabled button cannot be clicked — but Enter-key submission still reaches
the form even while its buttons are disabled. The spec calls for this explicitly under Edge Cases
("repeated presses", "keyboard submission") and FR-005. Four lines.

The `finally` also satisfies FR-005's "restored… success, failure, or error" more honestly than
today's arrangement, which restores the buttons in the success branch and again in the `catch`
branch — two copies of the same cleanup that can drift apart.

**Alternatives considered**: *Debounce or throttle.* Rejected — timing-based, and this is a state
question, not a rate question. Same reasoning the constitution applies to test waits.

## D3 — Carry the submit type in a persistent hidden field

**Decision**: Add `<input type="hidden" name="submit_type" id="submit-type" value="add">` to
`add.html`, and set `.value` from `event.submitter` at submission time. Remove the runtime
`document.createElement('input')` append at `inventory-add.js:669-673`.

**Rationale**: The quantity-1 path submits with `this.form.submit()`, which is *programmatic* and
therefore carries **no submitter** — so the button's own `name="submit_type" value="continue"` is
never transmitted on that path. That is precisely why the current code appends a hidden input by
hand. A field that always exists and whose value is assigned is more obvious than one conjured
per submission, and it fixes a latent accumulation bug: today, a bulk submission that fails
(which does not navigate away) leaves its appended input behind, and a subsequent press appends
another. `request.form.get()` returns the first, so a later plain **Add** would be read as a
`continue`.

**Alternatives considered**:
- *Skip `preventDefault()` for quantity 1 and let the native submission carry the submitter.*
  Fewest lines, but the resulting handler reads as "sometimes we prevent the default and sometimes
  we mysteriously do not." Rejected on readability.
- *`form.requestSubmit(submitter)`.* Re-fires the `submit` event — infinite recursion.

## D4 — Continue after a bulk creation: navigate when the dialog closes

**Decision**: Listen for `hidden.bs.modal` on `#bulkLabelPrintingModal`. If the submission that
opened it was a continue, `window.location.href = '/inventory/add'`.

**Rationale**: This produces byte-for-byte the same end state as the single-item continue path,
which is a server redirect to the same URL (`routes.py:607`) — a fresh server-rendered form with
`autoPopulateJaId()` having fetched the next free JA ID. FR-006 asks for the state to *match* the
single-item path, and re-rendering it is the only way to guarantee that rather than approximate it.

Carry-forward (FR-008) needs nothing extra: `handleSubmit` already writes the submitted values to
`sessionStorage` before submitting (lines 692-697) and `initializeCarryForwardData()` reads them
back on load (line 620), which is how carry-forward already survives the single-item redirect.

`hidden.bs.modal` is the right event because it fires after Bootstrap tears down the backdrop —
the same reason `tests/e2e/waits.py:wait_for_modal_hidden` waits on the backdrop rather than the
`show` class.

**Alternatives considered**:
- *Call the existing `clearFormForContinue()`.* Rejected, and see D7 — it is dead code that only
  half-does the job: it blanks a fixed list of fields but never repopulates the JA ID, so the next
  entry would start with an empty required field where the single-item path pre-fills it.
- *Have the server redirect.* Impossible on this path — the bulk response is JSON consumed by
  `fetch`; the browser does not navigate on it.
- *Reset the form in place without navigating.* Would have to replicate page-load initialization
  (JA ID allocation, material taxonomy state, photo manager) by hand. More code, more drift.

## D5 — No server-side change

**Decision**: `app/main/routes.py` is not modified.

**Rationale**: With exactly one request per action (D1/D2), the existing sequential allocation at
`routes.py:314-329` already yields distinct, non-colliding JA IDs — FR-004 holds. The bulk branch
at `routes.py:577` returns JSON before it ever reads `submit_type`, so "continue" has no
server-side meaning above quantity 1; under D4 the client owns that navigation, so it does not
need one. Partial-failure reporting (FR-009) is already implemented at `routes.py:363-378` and is
untouched.

Adding an ID reservation, a uniqueness retry, or an idempotency key would be scale machinery for
a problem this feature removes at its source, on a single-user LAN application whose spec puts
cross-session concurrency out of scope. Principle I forbids it.

**Alternatives considered**: *Make the server reject a second identical submission.* Rejected as
speculative generality — it defends against a client that, after this change, does not exist.

## D6 — Screenshots are not regenerated

**Decision**: Do not run `nox -s screenshots`. State the reason in the PR.

**Rationale**: The change is a `type` attribute, a hidden input, and JavaScript event wiring. None
of it renders. `.github/workflows/screenshots.yml` is informational by design — its header records
that CI-side diffing was removed because font rasterization differs between machines (issue #77),
and the comment it posts says "Nothing here blocks the merge" and warns that regeneration is not
reproducible. Regenerating would commit byte-different PNGs representing zero visual change, which
is diff noise of exactly the kind the constitution's anti-reformatting rule exists to prevent.

**Alternatives considered**: *Regenerate anyway to satisfy the letter of the constitution.*
Rejected; the constitution's own text on this point ("CI blocks merge on stale screenshots") is
stale relative to the workflow, and the plan flags that separately rather than acting on it.

## D7 — Remove `clearFormForContinue()`

**Decision**: Delete `inventory-add.js:823-846`.

**Rationale**: It is dead — defined once, called nowhere (verified across `app/`). Leaving a
function named for the exact behavior D4 implements, which does *not* implement it correctly,
is a trap for whoever reads this file next looking for how continue works.

## Test strategy

**Where**: `tests/e2e/test_bulk_creation.py`. Bulk-through-the-form already lives there with a
`BulkCreationPage` object; the new cases reuse it rather than starting a parallel page object.

**The sharpest guard is a request count.** Attaching `page.on("request", ...)` and asserting
exactly one `POST /inventory/add` fails today with 2 and passes after the fix. It tests FR-001
directly rather than inferring it from a symptom, and it cannot be satisfied by accident.

**Second guard: an absolute item count.** Reading `len(InventoryService(...).get_all_items())`
before and after and asserting the delta equals the requested quantity catches the silent-doubling
interleaving, which the request count would also catch but which deserves its own assertion
because it is the outcome that corrupts the inventory (FR-002).

**Waiting discipline** (`CLAUDE.md`, Constitution IV):

| What is awaited | Signal | Why it is valid |
|-----------------|--------|-----------------|
| Bulk POST resolved | `wait_for_modal_shown(page, "bulkLabelPrintingModal")` | Pattern C. `showBulkLabelPrintingModal()` is called only after `await fetch(...)` resolves, so an open modal cannot predate a completed response. Already used by the existing bulk tests. |
| Dialog dismissed | `wait_for_modal_hidden(...)` | Existing helper; waits for backdrop teardown, not the `show` class. |
| Continue navigation landed | `expect(page).to_have_url(re.compile(r"/inventory/add$"))` then `expect(ja_id_field).not_to_have_value("")` | `expect` polls. The second wait is CLAUDE.md pattern G — `autoPopulateJaId()` writes the field *after* awaiting `/api/inventory/next-ja-id`, so the form is not actually ready until that write lands. |
| No error was shown | Clear `#toast-container` before submitting, then assert absence *after* the modal is established | CLAUDE.md's negative-assertion rule: "the toast is absent" passes trivially against a page that has not rendered. The modal being open is what establishes the region. |

**Regression surface to re-run, not just the new file**: `test_add_item.py::test_add_and_continue_carry_forward_workflow`
(quantity-1 continue), the eight existing tests in `test_bulk_creation.py` (quantity > 1 via
**Add**), and — because Principle VI names the add path — the active-status and history suites.
In practice: the full `nox -s e2e`.

**No new unit tests.** The change is browser event wiring and a template attribute; there is no
Python behavior to assert. `tests/unit/test_routes.py:123` already covers the server's
`submit_type` handling and must keep passing unchanged, which is the point.
