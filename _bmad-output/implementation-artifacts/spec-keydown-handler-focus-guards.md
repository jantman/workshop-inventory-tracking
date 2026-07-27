---
title: 'Focus guards for the two document-level keydown handlers (DW-56, DW-64)'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: 'e3416ffd13e1947cfa77264854ecce642b33f4de'
final_revision: 'c5fe2306196ecaf7cbf3009b554dcd6182b90f9c'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** Both of the app's document-level `keydown` listeners act without regard to what actually has focus. `app/static/js/inventory-add.js:128-146` appends every printable key to its own barcode buffer and `preventDefault()`s it once scan mode is active, so while scan mode is on, typing into any field on `/inventory/add` — including the global navbar `#scan-input` — is swallowed (DW-56). `app/static/js/main.js:135-137` skips its "user is typing" early-return whenever Ctrl/Meta/Alt is held, so a wedge emitting ASCII control characters as Ctrl chords (GS as `Ctrl`+`]`, RS as `Ctrl`+`^`) reaches the shortcut table with the scan field focused: `Ctrl`+`/` puts a spurious "Focus Search" toast on screen mid-burst and `Ctrl`+`Shift`+`/` opens the keyboard-help modal, pulling focus out of the field (DW-64).

**Approach:** Add one shared "does a form field own focus right now" predicate to `WorkshopInventory.utils` and gate both handlers on it — read from `document.activeElement` at keydown time rather than from a tracked flag, so the guarantee does not depend on listener-registration order. In `main.js`, drop the modifier escape hatch from the early return, and gate the shortcut's confirmation toast on whether the action actually did something, the way each action's own body already gates itself.

## Boundaries & Constraints

**Always:**
- The focus predicate keeps `main.js`'s existing selector verbatim — `input, textarea, select, [contenteditable]` — so which elements count as "typing" does not change, only when and how freshly it is asked.
- With no field focused, every shortcut behaves exactly as today: `Shift`+`/` opens the help modal and toasts "Help"; the add-page scan buffer captures a wedge burst and populates `#ja_id`.
- NFR9 ("metal-stock functionality unaffected") is a behavior guarantee: the add-item scan button must still capture a barcode into `#ja_id` after this change. Both handlers were off limits to Epic 4 under that clause; they are in scope here, the behavior guarantee is not waived.
- The add-page handler only *ignores* keystrokes while a field owns focus. Scan mode stays active and ends through its existing paths (Enter, the 100 ms flush, the 10 s auto-cancel, `cancelBarcodeCapture`).

**Block If:**
- A caller is found that depends on a shortcut firing while a form field has focus. None exists — `Focus Search`'s body already no-ops in that state and `Help` only steals focus — so this is a human decision if one appears mid-implementation.

**Never:**
- Do not fix the neighbouring shortcut-table defects: `Help`'s entry-level `shift: true` making bare `F1` dead, `Shift`+`/` matching *both* entries and firing two shortcuts, or `matchesCtrl = !shortcut.ctrl || e.ctrlKey || e.metaKey` letting any chord match a modifier-less shortcut. They are distinct from DW-56/DW-64; defer them.
- Do not point `Focus Search` at a real field, remove the shortcut, or edit its `docs/user-manual.md` entries. No element in the app matches its selector today, which is a product decision, not this bundle's.
- Do not add a document-level listener to `scan-capture.js`, and do not change what `ScanCapture` does with modifiers.
- Do not cancel or auto-exit add-page scan mode when a field takes focus, and do not change the scan buffer's parsing, timeouts, or toasts.
- Do not edit the deferred-work ledger's DW-56/DW-64 entries; the orchestrator records resolution.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Wedge control chord, field focused | `#scan-input` focused, burst contains `Ctrl`+`/` | No shortcut runs, no toast, focus and field value unchanged | No error expected |
| Wedge help chord, field focused | `#scan-input` focused, `Ctrl`+`Shift`+`/` | `#keyboard-help-modal` never created; focus stays in `#scan-input` | No error expected |
| Help shortcut, nothing focused | `Shift`+`/` on `/` with focus on `body` | Help modal opens; exactly one toast, text `Help` | No error expected |
| Focus-search shortcut, no target | `/` pressed, no element matches `input[type="search"], input[name*="search"], #search` (true on every page today) | Nothing focused, **no toast**, `preventDefault()` not called | No error expected |
| Add page, scan mode + field focused | Scan mode active, operator types into `#scan-input` or `#ja_id` | Characters land in that field; add-page buffer stays empty; scan mode still active | No error expected |
| Add page, scan mode + no field focused | Scan mode active, focus on `#scan-ja-id-btn`, wedge types `JA000123` then Enter | `#ja_id` becomes `JA000123`, success toast — capture unchanged | Non-matching text still error-toasts as today |
| No focused element | `document.activeElement` is `null` or `body` | Predicate returns `false` — treated as "no field owns focus" | No throw |

</intent-contract>

## Code Map

- `app/static/js/main.js:115-200` -- `setupKeyboardShortcuts`. `:117` the `inInputField` closure flag, `:120-130` its focusin/focusout tracking, `:135-137` the early return being fixed, `:141-153` `Focus Search` (action self-guards on `!inInputField`, `:145` `preventDefault` fires before the target lookup at `:146`), `:155-165` `Help`, `:169-189` the match loop with the unconditional `showToast(name)` at `:184`.
- `app/static/js/main.js:297+` -- the `utils` object literal (8-space members, each closed by `        },`); new predicate belongs here. `showToast` at `:384` must stay byte-identical — `tests/unit/test_toast_markup.py:41` bounds it by that exact indentation.
- `app/static/js/inventory-add.js:126-157` -- `setupBarcodeScanning`; `:129` the `scanModeActive` gate, `:132-134` the `clearTimeout`, `:137-139` the buffer append + `preventDefault`, `:149-155` the 100 ms flush. Guard goes immediately after `:129`, before the `clearTimeout`, or typing into a field would postpone the flush indefinitely.
- `app/static/js/inventory-add.js:159-192` -- `startBarcodeCapture` (focuses nothing, so focus stays on `#scan-ja-id-btn`) / `cancelBarcodeCapture`. This is why guarding on focus does not break capture.
- `app/static/js/scan-capture.js:18-22` -- header comment asserting main.js "already early-returns while focus is in an input"; true only without modifiers until this change. `:53-58`, `:60-135` bind `keydown` on the field, never on document.
- `app/templates/base.html:100` -- `#scan-input`, present on every page including `/inventory/add`; `:167` loads `main.js` before `{% block scripts %}` at `:172`, so `WorkshopInventory.utils` is defined before `inventory-add.js` runs.
- `tests/e2e/conftest.py:21,64-74` -- `SCAN_INPUT`, `simulate_wedge_scan(page, text)`; `live_server` at `tests/conftest.py:174`, `page` at `:223`.
- `tests/unit/test_toast_markup.py` -- the source-tripwire pattern to copy (bound a function by regex, assert the anchor exists, assert on the slice, every assert names the defect that would return).
- `tests/e2e/pages/add_item_page.py:11,35-37` -- `AddItemPage.navigate()` → `/inventory/add`.

**Coverage baseline:** no test anywhere presses `/`, `?`, `F1`, or any modifier chord, and no test drives add-page scan mode (`scanModeActive`/`startBarcodeCapture` appear nowhere under `tests/`). Both defects are currently unguarded end to end.

## Tasks & Acceptance

**Execution:**
- [x] `app/static/js/main.js` -- add `utils.isFieldFocused()` reading `document.activeElement` against the existing selector; replace the early return's modifier clause with it; have each shortcut action return whether it acted (`Focus Search`: only when a target exists — move its `preventDefault()` inside that branch; `Help`: only when its `e.code` check passes) and gate `showToast(name)` on that result; delete the now-dead `inInputField` flag and its two tracking listeners -- one authoritative focus check replaces a stale-prone proxy, and the toast stops announcing actions that did not happen.
- [x] `app/static/js/inventory-add.js` -- return early from the scan-mode `keydown` handler when `WorkshopInventory.utils.isFieldFocused()`, placed after the `scanModeActive` gate and before the `clearTimeout` -- keystrokes aimed at a field reach that field instead of the barcode buffer, without disarming a pending flush.
- [x] `app/static/js/scan-capture.js` -- amend the header comment so it states the early return is unconditional -- the comment records the invariant `ScanCapture` relies on for having no document listener; leaving it describing the modifier-bypassed version invites a future editor to re-add one.
- [x] `tests/unit/test_keydown_focus_guards.py` -- new source tripwires: no negated `e.ctrlKey`/`e.metaKey`/`e.altKey` inside `setupKeyboardShortcuts`; the focus predicate is consulted before the `shortcuts` table is built; the `showToast` call sits inside a conditional on the value returned by `shortcut.action(...)`; `inventory-add.js`'s scan handler consults the predicate before touching buffer or timeout; `utils.isFieldFocused` reads `document.activeElement` -- the only fast-suite guard, since the repo has no JS test harness and the e2e suite takes ~20 minutes.
- [x] `tests/e2e/test_keydown_focus_guards.py` -- new Playwright file covering every I/O matrix row: chords with `#scan-input` focused produce no toast and no modal, `Shift`+`/` unfocused still opens the modal, `/` with no target produces no toast, add-page scan mode leaves `#scan-input`/`#ja_id` typing alone, and add-page capture still fills `#ja_id` from a wedge burst -- these are the only executable proof the guards work in a browser.

**Acceptance Criteria:**
- Given the add page with scan mode active and any form field focused, when keys are typed, then the add-page buffer neither captures them nor calls `preventDefault()`, and the field receives them.
- Given the add page with scan mode active and no field focused, when a barcode burst arrives, then `#ja_id` is populated exactly as before the change (NFR9).
- Given focus in a form field, when any key is pressed with any combination of Ctrl/Meta/Alt/Shift, then no entry in the shortcut table runs and no toast appears.
- Given no field focused, when a shortcut's action does not perform its effect, then no confirmation toast is shown for it.
- Given the repo after the change, when `grep -n "inInputField" app/static/js/main.js` runs, then there are no matches.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 3, low 6)
- defer: 4: (high 0, medium 2, low 2)
- reject: 5: (high 0, medium 2, low 3)
- addressed_findings:
  - `[medium]` `[patch]` The DW-56 guard silently killed a whole burst whenever a field held focus when the scanner was armed. The Code Map's premise — "`startBarcodeCapture()` focuses nothing, so focus stays on `#scan-ja-id-btn`" — is a Chromium behavior, not a guarantee: Firefox and Safari on macOS do not focus a clicked button, and `clearFormForContinue()` parks focus in `#ja_id` after every Save & Continue, so bulk entry arms from a field-focused state by default. There the guard ignored every key of the burst: no capture, no toast, button stuck armed for the 10 s auto-cancel. `startBarcodeCapture()` now calls `button.focus()`, making "no field owns focus during capture" a fact this code establishes rather than a convention it inherits.
  - `[medium]` `[patch]` The NFR9 e2e case staged its own premise with `page.locator(SCAN_BUTTON).focus()` after arming — deleting that line left all three add-page tests green, so it bought nothing and cost the suite its only chance to assert that *arming itself* leaves no field focused. Removed; the assertion now lives in `arm_add_page_scan_mode` off the click alone, and a new case dispatches a synthetic `MouseEvent('click')` (handler runs, focus does not move — exactly what a non-Chromium browser leaves behind) to make the fix above falsifiable in a Chromium-only suite. Mutation-verified: dropping `button.focus()` fails that case and the matching unit tripwire, nothing else.
  - `[medium]` `[patch]` `assert page.locator(TOAST_BODY).all_text_contents() == ['Ready to scan barcode...']` required a toast that Bootstrap autohides after 5 s to still be on screen after a `goto` + `networkidle` + click + several `expect`s + a 500 ms dwell — a scheduled flake on a loaded box, failing safe but for the wrong reason. Replaced with the absence of a `Scanned JA ID:`/`Invalid JA ID format:` toast, which is what "the buffer stayed empty" actually means and is immune to the timer.
  - `[low]` `[patch]` Both test modules oversold the unit tripwires ("the fast structural tripwire that stands in for [e2e]"). An inverted predicate — `return !(...)`, which reverses both fixed defects at once — passes all of them, as the reviewer demonstrated. Both docstrings now state plainly that the module asserts presence, shape and ordering only, and that behavior is the e2e file's job alone.
  - `[low]` `[patch]` The two guard regexes demanded contradictory brace styles — `if (…) { return; }` in `main.js`, `if (…) return;` in `inventory-add.js` — so a formatter or an eslint `curly` rule would red-fail one of them with a message ("it is now doing something else to scan mode") that misdirects. Both now accept either form.
  - `[low]` `[patch]` The modifier tripwire matched exactly one spelling of the negation. Added `e.ctrlKey === false`-style comparisons and a `getModifierState` check, with a docstring saying outright that a text scan cannot be exhaustive here.
  - `[low]` `[patch]` `body.count('preventDefault', 0, lookup) == 0` held only because `Focus Search` happens to be listed first; swapping the two table entries would have failed it with a false accusation against `Focus Search`. Scoped to the `Focus Search` entry.
  - `[low]` `[patch]` Added a unit tripwire for the new arm-time focus, so the fast suite catches its removal even though Chromium cannot.
  - `[low]` `[patch]` Comments claimed `Focus Search`'s selector "matches no element in any template" while the test verified only the page it visits. Reworded to say what is verified where.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 2, low 1)
- defer: 3: (high 0, medium 0, low 3)
- reject: 18: (high 0, medium 2, low 16)
- addressed_findings:
  - `[medium]` `[patch]` The `setupBarcodeScanning` guard's comment asserted "`startBarcodeCapture()` focuses nothing, so a wedge burst still arrives with focus on `#scan-ja-id-btn`" while the *same diff* added `button.focus()` to that function for the opposite reason — the two hunks came from different passes and were never reconciled. A future editor reading the handler is told the button gets focus by luck, which is precisely the premise `button.focus()` exists to stop being luck, and is exactly the reasoning that would justify deleting it. Comment rewritten to state that `startBarcodeCapture()` takes the focus itself.
  - `[medium]` `[patch]` The two DW-64 negative cases ("`Ctrl`+`/` and `Ctrl`+`Shift`+`/` do nothing with `#scan-input` focused") had no positive control. Recording the keydown proves the *key* arrived, but nothing anywhere proved the *chord would otherwise have acted*: `matchesCtrl = !shortcut.ctrl || e.ctrlKey || e.metaKey` (DW-136) is the only reason a modifier-less entry matches a Ctrl chord at all, and if it ever tightens both cases go green having tested nothing — the vacuity the module preamble claims to be designed against. Added `TestTheSameChordsWithNothingFocused`: with focus on `body`, `Ctrl`+`/` demonstrably focuses the injected probe and toasts `Focus Search`, and `Ctrl`+`Shift`+`/` demonstrably opens the help modal. Both pass, so the negatives above now measure the guard.
  - `[low]` `[patch]` `assert elapsed_ms < 800` in the NFR9 case turned machine load into a red test, with a message telling the reader `--reruns` would absorb it — `--reruns=3` re-runs on the same loaded box. It also measured the wrong quantity: total elapsed over the burst's 9 events, against a threshold derived from a per-gap invariant. Now consulted only after the scan has already failed, and then to `pytest.skip` rather than to fail; a genuine break stays red because the value assertion runs unconditionally.

## Design Notes

`document.activeElement` rather than the tracked `inInputField` flag: the flag is only as good as the focusin/focusout listeners registered at `DOMContentLoaded`, so focus landing before that (an `autofocus` attribute, an inline `.focus()`) leaves it `false` while the caret sits in a field — precisely the state DW-64's fix has to be trustworthy in. Reading focus at keydown time cannot go stale, and it removes two listeners rather than adding any.

```js
// True while an editable/selectable control owns keyboard input.
isFieldFocused: function() {
    const active = document.activeElement;
    return !!active && typeof active.matches === 'function' &&
        active.matches('input, textarea, select, [contenteditable]');
},
```

Gating the toast on the action's return value, rather than on `inInputField` a second time, is what makes it honest in the case the early return does not cover: `Focus Search`'s selector (`input[type="search"], input[name*="search"], #search`) matches nothing in any template — `#search-filter` on the list page is a near miss — so today `/` always toasts "Focus Search" and never focuses anything. After this change `/` is silently inert, which is the truth. That the shortcut has no target at all is a separate defect to defer, not to fix here.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the new `tests/unit/test_keydown_focus_guards.py`.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- tests/e2e/test_keydown_focus_guards.py tests/e2e/test_wedge_scan.py tests/e2e/test_scan_routing.py tests/e2e/test_toast_escaping.py` -- expected: all pass (needs a 20-minute harness timeout; `git checkout -- docs/` afterwards to revert screenshots the session rewrites).
- Mutation check: revert the `inventory-add.js` guard alone -- expected: the add-page typing tests fail and nothing else. Revert the `main.js` early-return alone -- expected: the chord tests fail and nothing else.
- `grep -n "inInputField\|isFieldFocused" app/static/js/main.js` -- expected: `isFieldFocused` only (definition plus one call site); no `inInputField`.

**Manual checks (if no CLI):**
- `git diff app/static/js/inventory-add.js` shows only the added guard in `setupBarcodeScanning` — buffer, timeouts, `processBarcodeInput` and the button state handling untouched.

## Auto Run Result

Status: `done` (follow-up review pass, `review_loop_iteration: 0`)

**Implemented change.** Both document-level `keydown` listeners now consult one shared predicate, `WorkshopInventory.utils.isFieldFocused()`, which reads `document.activeElement` at keydown time. `main.js`'s shortcut handler early-returns on it unconditionally — the Ctrl/Meta/Alt escape hatch a wedge's control chords walked through is gone (DW-64) — and each shortcut action now reports whether it acted so the confirmation toast can only announce what happened. `inventory-add.js`'s scan-mode buffer ignores keystrokes while a field owns focus (DW-56), and `startBarcodeCapture()` takes focus onto the scan button so "no field owns focus during capture" is established rather than inherited from Chromium's click behavior. The stale `inInputField` flag and its two tracking listeners are gone.

**Files changed in this pass.**
- `app/static/js/inventory-add.js` — corrected the scan-guard comment, which still claimed `startBarcodeCapture()` focuses nothing while the same function calls `button.focus()`.
- `tests/e2e/test_keydown_focus_guards.py` — added `TestTheSameChordsWithNothingFocused` (positive controls for the two Ctrl-chord negatives), factored the `Focus Search` probe into `inject_search_probe`, and reshaped the NFR9 timing check from a hard assert into a post-failure skip.
- `_bmad-output/implementation-artifacts/deferred-work.md` — three new entries (DW-138, DW-139, DW-140); no existing entry touched.

**Review findings breakdown.** 3 patches applied (medium 2, low 1); 3 deferred (all low: DW-138 stranded focus after capture, DW-139 truncated-burst flush, DW-140 uncleared auto-cancel timer); 18 rejected, of which 4 were re-reports of DW-134/135/136/137 already logged by the previous pass, 3 were changes to the field selector or the `inInputField` acceptance criterion that the intent contract locks, and the rest were non-defects on inspection (`showKeyboardHelp` already removes an existing modal; no shadow DOM in the app; DW-136's own recommended fix does not trip the modifier tripwire).

**Verification performed.**
- `nox -s tests` — **2649 passed**, 427 deselected, 0 failures.
- `nox -s e2e -- tests/e2e/test_keydown_focus_guards.py tests/e2e/test_wedge_scan.py tests/e2e/test_scan_routing.py tests/e2e/test_toast_escaping.py` — **72 passed** in 100 s, including both new positive controls. No screenshots rewritten (`git status` clean outside the four intended files).
- `grep -n "inInputField\|isFieldFocused" app/static/js/main.js` — two `isFieldFocused` hits (definition at `:307`, call site at `:126`), no `inInputField`. Acceptance criterion met.

**Residual risks.**
- The unit tripwires assert presence, shape and ordering only; an inverted predicate passes all of them. Behavior rests entirely on the e2e file, which runs only under Chromium.
- `startBarcodeCapture()`'s `button.focus()` is verified on non-Chromium behavior only through a synthetic `MouseEvent('click')`; no real Firefox/WebKit run exercises it.
- DW-136 remains open, so with no field focused a wedge's control chords still reach the shortcut table — the guard closes this only while a field owns focus. The two new positive controls pin that live behavior and will fail, correctly, when DW-136 is resolved.

