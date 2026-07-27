---
title: 'Escape at the toast sink, not at the call sites'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: 'e4929dd'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '3128a86'
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `WorkshopInventory.utils.showToast` (`app/static/js/main.js:383-409`) interpolates its `message` into an HTML string (`<div class="toast-body">${message}</div>`) and inserts it with `insertAdjacentHTML`, so every toast in the app is an unescaped HTML sink; 9 of its 28 call sites pass server-derived, filename-derived, or scanned-barcode text straight through, and a barcode label is attacker-suppliable physical input.

**Approach:** Build the toast out of DOM nodes and set the message with `textContent`, so the sink is safe by construction and no caller can get it wrong. Story 4.1 escaped at its own call site (`ScanCapture.notify`) only because its NFR9 boundary held `main.js` read-only; with the sink escaping, that call-site escaping becomes a double-escape and must be removed.

## Boundaries & Constraints

**Always:**
- The rendered toast keeps its current DOM shape and classes — `div.toast.align-items-center.text-bg-{type}` with `role="alert"`, containing `div.d-flex` > (`div.toast-body`, `button.btn-close.btn-close-white.me-2.m-auto[data-bs-dismiss="toast"]`) — appended to `#toast-container`, shown via `new bootstrap.Toast(...)`, and removed on `hidden.bs.toast`. Existing e2e selectors (`.toast.text-bg-danger`, `.toast-body`) and Bootstrap dismissal must keep working.
- Exactly one escaping boundary end-to-end: text reaches the toast escaped once and only once. `&lt;` must never appear as visible characters for a message containing `<`.
- Behavior for every current caller is unchanged (NFR9, whose text is "metal-stock functionality unaffected" — a behavior guarantee, not a file-level one). The caller audit below establishes that no caller passes intentional markup, so nothing degrades.

**Block If:**
- A caller is found that depends on markup rendering in a toast (none exists per the audit; a new one appearing mid-implementation is a human decision).

**Never:**
- Do not add a `showToastHtml` / `{html: true}` opt-in. The audit found zero markup-passing callers, so an opt-in would be a new unescaped sink with no user — the opposite of the intent. If a rich toast is ever needed, that is the story that adds it.
- Do not touch `showAlert` in `app/static/js/inventory-move.js:716` / `app/static/js/inventory-shorten.js:395`. They are a separate inline-alert sink (also `innerHTML`, also no markup-passing callers) outside DW-54's scope; leave them for their own ledger entry.
- Do not change any toast message text, any toast `type` argument, or `PhotoManager.showToast`'s fallback path.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Plain message | `showToast('Photo deleted', 'success')` | `.toast-body` text is `Photo deleted`; toast has class `text-bg-success` | No error expected |
| Markup in message | `showToast('<img src=x onerror="window.__pwned=1">')` | Shown as literal text; `.toast img` count is 0; `window.__pwned` stays undefined | No error expected |
| Entity in message | `showToast('a &amp; b < c')` | `.toast-body` inner_text is exactly `a &amp; b < c` (single-escaped, not `a &amp;amp; b &lt; c`) | No error expected |
| Server error via scan | `/api/scan` returns `error.message` containing `<img ...>` | Toast shows the tag as literal text once; no element created | Existing `test_server_error_message_is_escaped_not_rendered` still passes |
| Non-string message | `showToast(undefined)` / `showToast({a:1})` | `undefined` / `[object Object]` as text — same as today's interpolation | No error expected |
| Close button | Operator clicks `.btn-close` | Toast dismisses and the element is removed from `#toast-container` | No error expected |

</intent-contract>

## Code Map

- `app/static/js/main.js:383-409` -- `WorkshopInventory.utils.showToast`, the sink being fixed. Object-literal style; keep the container-creation block as-is.
- `app/static/js/scan-capture.js:426-448` -- `ScanCapture.notify`, the only pre-escaping caller (`this.escapeHtml(message)`); its doc comment names the sink's interpolation as the reason.
- `app/static/js/scan-capture.js:476-484` -- `ScanCapture.escapeHtml`, used at `:442` and nowhere else in `app/` or `tests/`; becomes dead once `notify` stops escaping.
- `app/static/js/photo-manager.js:9-25` -- `PhotoManager.showToast` wrapper: forwards verbatim, no escaping. No change needed once the sink is safe.
- `tests/e2e/test_wedge_scan.py:785-808` -- `test_server_error_message_is_escaped_not_rendered`; asserts `'<img' in toast.inner_text()`, which fails under double-escaping. It is the existing end-to-end guard.
- `tests/e2e/conftest.py` -- `SCAN_INPUT`, `simulate_wedge_scan`; `live_server` comes from `tests/conftest.py:174`.
- `app/static/js/components/item-formatters.js:143` -- an unrelated `escapeHtml` for table cells; do not conflate.

**Caller audit (28 sites, complete):** 15 direct (`main.js:184`; `inventory-add.js:172,202,207,527,562,607,724,731,735,901,1048`; `templates/inventory/edit.html:952,957,961`), 6 via `PhotoManager.showToast` (`photo-manager.js:193,216,224,242,591,595`), 7 via `ScanCapture.notify` (`scan-capture.js:104,118,249,280,332,345,391`). **Zero pass intentional markup.** Exactly one pre-escapes: `ScanCapture.notify`. `inventory-list.js:261` has its own `textContent`-based helper and does not reach this sink.

## Tasks & Acceptance

**Execution:**
- [x] `app/static/js/main.js` -- rewrite `showToast`'s toast construction with `document.createElement` + `textContent` for the message, appending to the container and keeping the local `toastElement` reference (no `insertAdjacentHTML`, no `lastElementChild`) -- makes the sink safe by construction while preserving the DOM shape Bootstrap and the e2e selectors depend on.
- [x] `app/static/js/scan-capture.js` -- drop the `escapeHtml` call in `notify`, delete the now-unused `escapeHtml` helper, and rewrite the `notify` doc comment to state that the sink escapes and callers pass plain text -- prevents double-escaping and removes a helper whose comment documents a constraint that no longer exists.
- [x] `tests/e2e/test_toast_escaping.py` -- new file; e2e tests driving `WorkshopInventory.utils.showToast` directly via `page.evaluate` on `/`, covering every I/O matrix row (plain, markup, entity/single-escape, non-string, close-button removal) -- the sink has no unit-test harness (no JS test infra in this repo), so Playwright is the only executable guard.

**Acceptance Criteria:**
- Given a message containing `<img src=x onerror=...>`, when any caller invokes `showToast`, then it renders as literal text, no `img` element exists inside `.toast`, and no injected script runs.
- Given the scan failure path, when the server returns an error message containing markup, then the toast shows it exactly once-escaped — `tests/e2e/test_wedge_scan.py::test_server_error_message_is_escaped_not_rendered` passes unmodified, proving no double-escaping.
- Given any existing caller, when it toasts, then the visible text, the `text-bg-{type}` styling, the auto-hide, and the close button behave as before.
- Given the repo after the change, when `grep -rn "escapeHtml" app/static/js/scan-capture.js` runs, then there are no matches.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 3, low 4)
- defer: 2: (high 0, medium 1, low 1)
- reject: 10: (high 0, medium 5, low 5)
- addressed_findings:
  - `[medium]` `[patch]` `test_close_button_dismisses_and_removes_the_toast` could not fail: `showToast` passes no options, so Bootstrap's `autohide: true, delay: 5000` removes the toast on its own inside the assertion's own 5s deadline — an unwired close button would have gone green. Deadline tightened to 1s and the reason documented; verified by mutation (removing `data-bs-dismiss` now fails both dismissal tests, and only those).
  - `[medium]` `[patch]` `tests/e2e/test_wedge_scan.py:786`'s docstring still told the next editor that `showToast` interpolates into innerHTML "so the message must reach it escaped" — an instruction to reintroduce the double-escape this change removes. Rewritten to state the sink renders text and to explain that its `'<img'` assertion is itself the double-escape detector. Assertions untouched, so the AC's "passes unmodified" still holds.
  - `[medium]` `[patch]` The only guard on the new invariant was a ~20-minute Playwright suite, so a rewrite back to a template literal would pass `nox -s tests` — the suite developers actually run. Added `tests/unit/test_toast_markup.py`, a source tripwire in the fast session (pattern borrowed from the existing `tests/unit/test_autocomplete_markup.py`): the sink must use `textContent` and none of `insertAdjacentHTML`/`innerHTML`/`outerHTML`/`document.write`, no `toast-body` may be interpolated, and `scan-capture.js` must stay free of `escapeHtml`.
  - `[low]` `[patch]` No case covered a second toast, so both the container-reuse branch and the `appendChild` ordering that replaced `lastElementChild` were unproven. Added `test_a_second_toast_stacks_and_dismisses_independently`, which pins order and dismisses the second without disturbing the first.
  - `[low]` `[patch]` `null` — likelier than `undefined` from a JSON `data.message` — was missing from the non-string matrix that exists to pin the nullable-IDL behavior. Added as a parametrized row.
  - `[low]` `[patch]` The new test module's docstring called `showToast` "the app's only toast renderer", which would send a future auditor home after reading one function. Corrected to name the other notification sinks (`inventory-list.js`'s own helper, `showAlert` in move/shorten, `PhotoManager`'s `alert()` fallback) and mark them out of scope.
  - `[low]` `[patch]` `main.js`'s new comment called `textContent` an "escaping boundary", which invites both failure modes it is meant to prevent (pre-escaping callers, and an `{html: true}` opt-in). Reworded: `textContent` does not escape, it never reaches the HTML parser — and a caller that escapes first is now the bug.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 1, low 3)
- defer: 1: (high 0, medium 0, low 1)
- reject: 13: (high 0, medium 1, low 12)
- addressed_findings:
  - `[medium]` `[patch]` Both dismissal e2e cases could be settled by Bootstrap's autohide rather than by the close button, and the previous pass's fix did not actually close that. Tightening the post-click deadline to 1s only helps if the pre-click stretch is bounded — the 5s clock starts at `toast.show()`, not at the click, and nothing bounded the `expect()` waits in between. A slow run could click at ~4.5s and watch the toast expire inside the 1s deadline (false green for a dead button), or lose the *first* toast mid-way through the stacking case (false red for working code). Added `assert_autohide_cannot_explain_it`, which fails with a diagnostic naming the loaded machine when the pre-click stretch reaches 2s, and corrected the docstring that claimed the short deadline sufficed. Elapsed is milliseconds in practice, so the guard does not fire: 51 passed.
  - `[low]` `[patch]` The unit tripwire's `'textContent' in _show_toast_body()` proved only that the token appears somewhere in the function — `toastBody.textContent = ''` beside a markup-built message would have passed it. Tightened to a regex requiring `.textContent = String(message)`, i.e. that the *message* is what goes through it, while deliberately leaving the element variable's name unpinned so a rename is not a failure.
  - `[low]` `[patch]` `HTML_SINKS` was commented as "every way a string can become markup" while listing only four, all of which name HTML at the call site. Added the parser entry points that do not — `setHTMLUnsafe`, `createContextualFragment`, `DOMParser`, `.html(` — since those are what a reintroduced sink would most plausibly hide behind.
  - `[low]` `[patch]` `test_markup_in_message_is_literal_text_and_runs_nothing` claimed its `window.__pwned` read proved the injected handler never fired. It cannot: `onerror` fires only after the failed fetch of `src=x`, asynchronously, so the synchronous read would come back `undefined` even against vulnerable code. Docstring corrected to name the `.toast img` count as the load-bearing assertion and `__pwned` as a backstop whose silence proves nothing. Assertions unchanged.

## Design Notes

The sink builds nodes rather than escaping a string, because escaping a string leaves the `innerHTML` call in place for the next editor to reuse. `textContent` cannot be talked into parsing markup, so the safety is structural.

```js
const body = document.createElement('div');
body.className = 'toast-body';
body.textContent = message;          // the one escaping boundary
```

`text-bg-${type}` stays a template string on `className`: `type` is a developer-supplied literal at all 28 call sites and a class token is not an HTML-parsing context, so hardening it is not this story's job — and `classList.add` would throw on a whitespace-bearing token, turning a cosmetic problem into a lost notification.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- tests/e2e/test_toast_escaping.py tests/e2e/test_wedge_scan.py` -- expected: all pass (needs a 20-minute harness timeout; `git checkout -- docs/` afterwards to revert screenshots the session rewrites).
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green (no Python behavior changed; this is the regression floor).
- `grep -rn "escapeHtml" app/static/js/scan-capture.js` -- expected: no matches.
- `grep -n "insertAdjacentHTML" app/static/js/main.js` -- expected: only `:102`, the keyboard-shortcut help modal's static string. The toast sink must not appear.

**Manual checks (if no CLI):**
- `git diff app/static/js/main.js` shows only `showToast`'s body changed — the container-creation block, `bootstrap.Toast` call, and `hidden.bs.toast` cleanup are intact.

## Auto Run Result

Status: done

**Implemented change.** `WorkshopInventory.utils.showToast` no longer interpolates its message into an HTML string. It builds the toast from DOM nodes and sets the message with `textContent`, so all 28 call sites — including the nine carrying server-derived, filename-derived or scanned-barcode text — are inert by construction rather than by caller discipline. `ScanCapture.notify`'s call-site escaping, which Story 4.1 added only because NFR9 held `main.js` read-only, is removed along with its now-dead `escapeHtml` helper; keeping it would have shown operators `&lt;img` instead of `<img`. The caller audit DW-54 asked for is recorded in the Code Map: **zero callers pass intentional markup**, which is why no `showToastHtml` opt-in was added — it would be a new unescaped sink with no user.

**Files changed.**
- `app/static/js/main.js` — `showToast` rebuilt with `createElement` + `textContent`; DOM shape, classes, `bootstrap.Toast` wiring and `hidden.bs.toast` cleanup unchanged. `String(message)` is explicit: `textContent` is a nullable IDL attribute, so a bare assignment would turn `undefined`/`null` into an empty toast instead of the word the interpolation rendered.
- `app/static/js/scan-capture.js` — `notify` passes plain text; `escapeHtml` deleted; two comments that described the old contract corrected.
- `tests/e2e/test_toast_escaping.py` — new; 8 tests driving the sink directly (markup is literal text and creates no element, single-escape, type styling, three non-string rows, close-button dismissal, stacked toasts). This pass added the elapsed-time guard that makes the two dismissal cases actually distinguish the close button from Bootstrap's autohide.
- `tests/unit/test_toast_markup.py` — new; source tripwire so the invariant is guarded by the fast suite, not only by e2e. This pass tightened it to assert that the *message* flows through `textContent`, and widened the forbidden-sink list to the parser entry points that do not name HTML.
- `tests/e2e/test_wedge_scan.py` — docstring only; assertions untouched, so the AC's "passes unmodified" holds.
- `_bmad-output/implementation-artifacts/deferred-work.md` — three entries appended across both passes (DW-125, DW-126, DW-127); no existing entry modified.

**Review findings breakdown (follow-up pass).** 4 patched (1 medium, 3 low), 1 deferred (DW-127: three unescaped `innerHTML` interpolation sinks still sitting in `WorkshopInventory.utils` — `showLoading`, `showLoadingOverlay`, `createRecentItemsDropdown` — all currently unreachable, which is why it is low and not high), 13 rejected. All four patches were test-only; no production code changed in this pass. No intent gap and no spec defect, so no loopback; `review_loop_iteration` stays 0. Notable rejections, all verified rather than waved off: the claim that the spec's "28 call sites" is wrong (it is right — 15 direct + 1 `PhotoManager` forwarder = the 16 raw `showToast(` matches, plus 6 `PhotoManager` callers and 7 `notify` callers); `text-bg-error` and the missing toast ARIA attributes (already filed as DW-125/DW-126 by the previous pass, so re-filing would duplicate); the unit tripwire only checking `scan-capture.js` for `escapeHtml` (that is precisely what the spec's fourth AC pins, and the double-escape regression is caught end to end by the wedge-scan case); a throwing `toString`, and the orphan node left behind if the Bootstrap CDN fails (both pre-existing and unchanged in shape by this diff).

**Verification.**
- `venv/bin/nox -s tests` — `2631 passed, 413 deselected in 24.62s` (up from 2627; the four added `HTML_SINKS` parametrizations).
- `venv/bin/nox -s e2e -- tests/e2e/test_toast_escaping.py tests/e2e/test_wedge_scan.py` — `51 passed in 81.91s`. The new elapsed-time guard never fires: the pre-click stretch is milliseconds, well inside its 2s budget.
- Full `venv/bin/nox -s e2e` during implementation — `391 passed, 1 skipped` in 19m58s; screenshot churn under `docs/` reverted, and no `docs/` change is in this commit.
- Earlier mutation check still stands: deleting `closeButton.setAttribute('data-bs-dismiss', 'toast')` fails both dismissal tests and nothing else.
- `grep -rn "escapeHtml" app/static/js/scan-capture.js` — no matches. `insertAdjacentHTML` survives in `main.js` only at `:102`, the help modal's static string.

**Residual risks.** The e2e cases reach `showToast` through `page.evaluate`, not through a caller, so they prove the sink and not the 28 paths into it; the wedge-scan case remains the one end-to-end caller covered. The dismissal cases now fail loudly instead of silently mis-passing when a machine is too loaded to discriminate, which trades a rare false green for a rare diagnosed red — the right direction, but `--reruns=3` is what absorbs it. Bootstrap loads from a CDN, so a blocked CDN turns every toast test red for a reason unrelated to escaping. DW-125/126/127 are cosmetic, a11y, and latent-dead-code respectively; none is a live security exposure.
