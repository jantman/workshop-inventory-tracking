---
title: 'Wedge scan capture'
type: 'feature'
created: '2026-07-25'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
baseline_revision: '80d5212'
final_revision: 'e53cf03'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** FR35 — "the scan field captures a wedge scan on any page" — has no implementation. Epic 4 opens the identification loop (scan → classify → resolve → route), but there is no input that accepts a barcode scan for the catalog and no endpoint that receives one. The navbar's `#ja-id-lookup` (`app/templates/base.html:74-88`, `app/static/js/main.js:205-243`) is metal-stock-only: it regex-gates on `^JA[0-9]{6}$`, uppercases what you type, and navigates client-side — it can never carry a GTIN, an internal GS1 payload, or an ECIA envelope. `app/main/routes.py` has no `/api/scan` handler and `CatalogService` has no scan surface at all.

**Approach:** Add a second, deliberately dumb global input to the navbar — `#scan-input`, beside the JA-ID field, present on every page because every template extends `base.html` — driven by a new globally-loaded `app/static/js/scan-capture.js` that does one thing: on `Enter`, POST the field's value verbatim to a new `POST /api/scan`. The client performs **no** classification, normalization, or navigation; the server endpoint performs **no** lookup. It validates the payload, applies one narrowly-defined whitespace rule, and echoes the cleaned raw text back with `outcome: 'unrouted'` — the single named seam that Story 4.2's `scan_router.classify()` and Story 4.3's `resolve_scan()` fill in without changing the transport, the field, or the request shape.

## Boundaries & Constraints

**Always:**
- The captured value is transmitted **verbatim** apart from one rule: strip leading and trailing space, tab, CR and LF only. Every other character — including the ASCII control characters an ISO/IEC 15434 format-06 envelope carries (`\x1d` GS, `\x1e` RS, `\x04` EOT) and any interior whitespace — survives to the server byte-for-byte. Story 4.4's parser depends on this; a broader `.strip()` would silently destroy the envelope's terminator.
- No case folding, no Unicode normalization, no uppercasing, no pattern matching, on either side. `#scan-input` must **not** inherit the JA-ID field's `input`-handler uppercasing (`app/static/js/main.js:239-243`) — GTINs are digits but internal payloads and ECIA fields are case-significant.
- Capture requires the field to have focus, per FR35's Given. Bind `keydown` on `#scan-input` only. Register **no** document-level key handler: `main.js:115-148`'s global shortcut handler already early-returns while focus is in any input, so a focused scan field is inert to it, and adding a second global listener would create the conflict that absence avoids.
- The scan field must not match `main.js:141-148`'s focus-search selector `input[type="search"], input[name*="search"], #search`, or the `/` shortcut hijacks focus to it. Use `type="text"`, id `scan-input`, and no `name` containing `search`.
- `POST /api/scan` lives in `app/main/routes.py` with the other `/api/...` handlers, carries `@csrf.exempt` directly under `@bp.route` (the pattern every JSON route in that file follows, e.g. `routes.py:989-990`), and returns the AD-13 object-error envelope exclusively via `_catalog_json_error` (`routes.py:979-986`). It never returns the legacy string-`error` shape.
- The endpoint touches no database and constructs no service. It does not call `_get_catalog_service()`. Resolution is Story 4.3's; wiring the service in now would make this story's tests depend on storage for no behavior.
- A scan is never lost. Any failure — network error, non-2xx, malformed response — leaves the raw text in the field and selects it, so the operator can retry or read it off. Only a `success: true` response clears the field.
- Focus returns to `#scan-input` after every successful scan, so consecutive scans need no mouse.
- The client ignores `Enter` while a POST is in flight, so a fast double-scan cannot produce two overlapping requests against one keystroke burst.
- New tests carry `@pytest.mark.unit` or `@pytest.mark.e2e`, are grouped in `class Test*`, use the house parametrize idiom (one case per line, aligned trailing `#` comment), and cite FR35 in docstrings. The e2e tests mutate no data, so they are trivially safe under `--reruns=3`.

**Block If:**
- `nox -s tests` is already red on this branch before any change — pre-existing breakage, not this story's.
- Delivering the scan field would require changing `#ja-id-lookup`'s markup, its handler, or its behavior. NFR9 forbids disturbing metal-stock scanning; if the two cannot coexist, that is a human decision.

**Never:**
- No classification. `app/utils/scan_router.py` is **not** created here, no GTIN check-digit call, no `gs1.decode()` call, no `[)>` sniffing, no precedence logic anywhere. Story 4.2 owns all of it.
- No resolution, no lookup, no `resolve_scan`, no `search_products`, no `CatalogService` method, no navigation or redirect on scan. Stories 4.3 and 4.5 own those; this story's response deliberately has nowhere to send the operator.
- No change to `#ja-id-lookup`, `setupJaIdLookup`, or any metal-stock scan path (`inventory-move.js`, `inventory-shorten.js`). No merging of the JA-ID field into the scan field — unifying the two navbar inputs is a later-epic decision, not this story's.
- No timeout-based scan terminator. `inventory-move.js:146-160`'s `scannerDelay` fallback exists for scanners that omit Enter; FR35 specifies Enter-terminated input and the deployed Tera HW0009 sends it. Adding a timer here would fire on ordinary typing.
- No new dependency, no build step, no ES-module conversion, no `<meta name="csrf-token">` (the endpoint is `@csrf.exempt`, matching every other JSON route; the two existing broken meta-tag readers in `inventory-search.js` and `components/item-actions.js` are pre-existing and out of scope).
- No schema change, no migration, no config key, no change to `app/utils/**` or `app/mariadb_catalog_service.py`.
- No scanner-side configuration of any kind — no AIM identifier prefix, no suffix programming. FR35's whole point is that a stock keyboard wedge works untouched, and scanner settings are global to the shop's metal-stock workflow.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | `POST /api/scan` body `{"raw": "00012345678905"}` | `200 {"success": true, "raw": "00012345678905", "outcome": "unrouted"}` | No error |
| Outer whitespace | `{"raw": "  0123 \r\n"}` | `200`, `raw` == `"0123"` — leading/trailing space, tab, CR, LF stripped | No error |
| Control chars survive | `{"raw": "[)>\x1e06\x1dP123\x1e\x04"}` | `200`, `raw` echoed with `\x1e`, `\x1d`, `\x04` intact — only the 15434 envelope's own terminators, never stripped | No error |
| Interior whitespace kept | `{"raw": "a b\tc"}` | `200`, `raw` == `"a b\tc"` | No error |
| Case preserved | `{"raw": "96WITabc"}` | `200`, `raw` == `"96WITabc"` — never uppercased | No error |
| Missing `raw` | `{}` | `400`, `error.code` == `invalid_field`, `error.field` == `raw` | AD-13 object envelope |
| Blank after cleaning | `{"raw": "   "}` or `{"raw": ""}` | `400 invalid_field` on `raw` | AD-13 object envelope |
| Non-string `raw` | `{"raw": 12345}`, `{"raw": null}`, `{"raw": ["a"]}` | `400 invalid_field` on `raw` — no coercion | AD-13 object envelope |
| Non-object body | `json=["not", "a", "dict"]`, or no/invalid JSON body | `400 invalid_field` on `raw` | `request.get_json(silent=True) or {}`, never a 500 |
| Over-length scan | 4097-character `raw` | `400 invalid_field` naming the 4096 limit | AD-13 object envelope |
| At the limit | exactly 4096 characters | `200` | No error |
| Client: blank Enter | Field empty or whitespace-only, `Enter` pressed | No request is sent; field state unchanged | No error surfaced |
| Client: successful scan | Field holds `"0123"`, `Enter` | One POST to `/api/scan`; on `success` the field clears and keeps focus | No error |
| Client: request fails | Endpoint returns 400/500, or fetch rejects | Field retains the raw text and selects it; a danger toast is shown | Scan is never silently dropped |
| Client: scan while in flight | `Enter` pressed again before the first response | Second `Enter` is ignored; exactly one request outstanding | No error |
| Regression: JA-ID field | `JA000123` typed into `#ja-id-lookup` + `Enter` | Still navigates to `/inventory/edit/JA000123`; no request to `/api/scan` | Unchanged (NFR9) |

</intent-contract>

## Code Map

- `app/templates/base.html` -- the only base template; all 19 templates extend it. Navbar JA-ID block at `:74-88` (insert the scan block immediately after it); global `<script>` tags at `:149-150` (add `scan-capture.js` there).
- `app/static/js/main.js` -- `WorkshopInventory` object-literal + `init()` style to match (`:6`, `:805-810`); `utils.showToast(message, type)` at `:383` for feedback; `setupJaIdLookup` at `:205` and the global shortcut handler at `:115-148` — both **read-only references**, do not edit.
- `app/main/routes.py` -- 3666 lines, all `/api/...` handlers; `_catalog_json_error` at `:979-986`; canonical `@csrf.exempt` JSON POST at `:989-1049`. New endpoint goes here (the project has no per-feature route-module pattern).
- `app/static/js/inventory-move.js:130-160` -- the existing wedge idiom (keydown/Enter/preventDefault) worth matching, minus its `scannerDelay` timer and its client-side `classifyInput`.
- `tests/unit/test_product_routes.py:144-177` -- canonical AD-13 JSON route test: `client.post(..., json=...)`, `data['error']['code']`, `data['error']['field']`.
- `tests/e2e/test_move_items.py:25-37` -- `simulate_barcode_scan()`: `fill("")` → `focus()` → `type()` → `press("Enter")`. The wedge simulation to model.
- `tests/e2e/test_ja_id_lookup.py` -- existing coverage of the neighbouring navbar field; the NFR9 regression guard belongs alongside it in shape.
- `tests/conftest.py` -- `client` (`:76`) for unit route tests; `page` (`:222`) + `live_server` (`:173`) for e2e.
- `tests/e2e/screenshot_config.yaml` -- 20 screenshot definitions; the navbar appears in all of them, so this story's markup change makes them stale.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- add `POST /api/scan` (`api_scan`) with `@csrf.exempt`, a module-level `MAX_SCAN_LENGTH = 4096`, and a private `_clean_scan_input(value)` implementing the strip-outer-space/tab/CR/LF-only rule; validate per the I/O matrix via `_catalog_json_error`; return `{'success': True, 'raw': cleaned, 'outcome': 'unrouted'}` at 200 -- the transport seam Stories 4.2/4.3 extend without touching the request shape.
- [x] `app/static/js/scan-capture.js` -- new file; `ScanCapture` object literal with `init()`/`bindEvents()`/`submitScan()`, an `isSubmitting` guard, `fetch` POST of `{raw}` as JSON, clear-and-refocus on success, retain-and-select plus `WorkshopInventory.utils.showToast(..., 'danger')` on failure; trailing `DOMContentLoaded` wiring and `window.ScanCapture` export -- kept out of `main.js` so Story 4.5's routing logic lands in one isolated epic-4 file.
- [x] `app/templates/base.html` -- add the `#scan-input` navbar block (input-group with a `bi-upc-scan` icon, `type="text"`, `autocomplete="off"`, `aria-label`, placeholder) directly after the JA-ID block, and the `scan-capture.js` `<script>` tag beside `main.js` -- makes the field present on every page without per-template work.
- [x] `tests/unit/test_scan_routes.py` -- new file; `@pytest.mark.unit class TestScanCaptureEndpoint` covering every server row of the I/O matrix, parametrized in the house style, asserting status, `success`, `raw` (including byte-exact control-character preservation) and `error.code`/`error.field`.
- [x] `tests/e2e/test_wedge_scan.py` -- new file; `@pytest.mark.e2e`, a local `simulate_wedge_scan(page, text)` helper modeled on `test_move_items.py:25-37`; assert via `page.expect_response('**/api/scan')` that the raw text posts unmodified, that the field clears and retains focus, and that `#scan-input` is present on at least two different pages -- FR35's "on any page". For the blank-Enter negative case, install a `page.route('**/api/scan', ...)` handler that records calls into a list and `route.continue_()`s, press Enter on an empty field, settle, and assert the list is empty -- `expect_response` cannot assert the absence of a request.
- [x] `tests/e2e/test_wedge_scan.py` -- add the NFR9 regression case: `#ja-id-lookup` still navigates to `/inventory/edit/JA000123` with the scan field present, and issues no `/api/scan` request.
- [x] `docs/images/screenshots/` -- the navbar markup change makes all 20 screenshot definitions stale; run `nox -s screenshots_headless` then `nox -s screenshots_verify` and commit the regenerated PNGs. If regeneration cannot run in this environment, leave the images untouched and record the staleness as a deferred-work entry rather than committing partial output.

**Acceptance Criteria:**
- Given any page in the app, when it renders, then `#scan-input` is present in the navbar and `scan-capture.js` is loaded, without that template having been modified individually.
- Given `#scan-input` has focus, when a scanner emits a barcode as keystrokes terminated by `Enter`, then exactly one `POST /api/scan` is issued whose `raw` equals the scanned characters, with no scanner driver, scanner configuration, or AIM prefix involved.
- Given a successful scan response, when it is received, then the field is cleared and still focused so the next scan needs no interaction.
- Given the scan endpoint receives a payload it cannot accept, when it responds, then the body is the AD-13 object-error envelope and the process never raises a 500 for malformed input.
- Given the existing metal-stock JA-ID lookup and move/shorten scan paths, when this story ships, then their markup, handlers and behavior are byte-identical to `80d5212` (NFR9).
- Given `nox -s tests` and `nox -s e2e`, when they run, then both are green.

## Spec Change Log

## Review Triage Log

### 2026-07-25 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 1, medium 2, low 5)
- defer: 6: (high 0, medium 4, low 2)
- reject: 9
- addressed_findings:
  - `[high]` `[patch]` An `Enter` arriving while a POST was in flight was dropped silently, and `handleSuccess` then blanked the field unconditionally — so the typed-ahead second scan was erased and the operator saw the cleared field that means "accepted". Violated the story's own "a scan is never lost" invariant. The in-flight `Enter` now raises a warning toast, `handleSuccess` clears only when the field still holds exactly what was submitted, and `handleFailure` restores only into an empty or unchanged field. Covered by `test_second_enter_while_in_flight_is_ignored_but_not_silently` and the new `TestLateResponseDoesNotClobberTheOperator::test_late_success_does_not_erase_newer_keystrokes`.
  - `[medium]` `[patch]` A late response called `this.input.focus()` unconditionally, yanking focus back from whatever field the operator had moved to. Added `refocus()`, which only focuses when the scan field (or nothing) is already active. Covered by `test_late_response_does_not_steal_focus_from_another_field`.
  - `[medium]` `[patch]` `errorMessage` piped the server-supplied `error.message` into `showToast`, which interpolates into `innerHTML`. Harmless with today's static messages, but this story establishes the epic's error-display path and Stories 4.2/4.3 will echo the scanned payload — a printed label is attacker-suppliable physical input. The message is now escaped at the call site (`main.js` is off limits under NFR9; the sink itself is deferred). Covered by `test_server_error_message_is_escaped_not_rendered`.
  - `[low]` `[patch]` The single trailing `.catch()` wrapped the whole promise chain, so a bug thrown inside `handleSuccess` would have been reported to the operator as an offline server for a scan the server had accepted. Network rejection is now handled by the `fetch` stage's own rejection handler; the trailing `.catch()` only logs handler bugs and leaves field state alone.
  - `[low]` `[patch]` A `fetch` that never settled would have left `isSubmitting` stuck true, refusing every later scan for the rest of the session. Added a 10s `AbortController` timeout plus a `.finally()` reset.
  - `[low]` `[patch]` The endpoint had no logging at all, unlike its neighbours in `routes.py` — the one endpoint whose entire purpose is "did the scan arrive" left no server-side record. Added `warning` on each rejection path and `debug` on capture.
  - `[low]` `[patch]` `_SCAN_TRIM`'s boundary was undocumented for `\x0b`/`\x0c`/`\x00`, which `str.strip()` would remove and the rule deliberately keeps. Added `test_other_control_characters_are_also_never_trimmed` so changing it is a conscious act rather than a silent drift in Story 4.4.
  - `[low]` `[patch]` The CSRF-exemption test hardcoded `'app.main.routes.api_scan'`, which a module or function rename would silently invalidate. It now derives the registry key from the view function itself.

### 2026-07-25 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 0, medium 3, low 9)
- defer: 2: (high 0, medium 2, low 0)
- reject: 17
- addressed_findings:
  - `[medium]` `[patch]` The previous pass added `refocus()` specifically so a late response could not yank focus away from wherever the operator had moved — and then `handleFailure` called `this.input.select()` on the next line, outside the guard. `select()` focuses the element as a side effect, so the *failure* path still stole focus; only the success path was actually fixed. `refocus()` now returns whether focusing was allowed and `select()` runs only when it was. Covered by `test_late_failure_does_not_steal_focus_from_another_field`, which the previous pass's success-only stub could not have caught.
  - `[medium]` `[patch]` The in-flight guard dropped the second `Enter` but not the second burst's **characters**, which a real wedge types *before* sending Enter. The field was left holding `SCAN1SCAN2`, `handleSuccess` correctly refused to clear it, and the operator's rescan appended again and POSTed the concatenation as one valid scan — a silently *wrong* scan, which is worse than the lost scan the guard was protecting against. The residue is now selected (on both the in-flight path and `handleSuccess`'s declined-clear path) so the next burst's first keystroke overwrites it. Covered by `test_typed_ahead_burst_does_not_concatenate_onto_the_next_scan`, which simulates the burst faithfully rather than dispatching two bare Enters.
  - `[medium]` `[patch]` `handleFailure`'s else-branch — the operator has already started a fresh scan — restored nothing and showed a toast that still said the text had been kept. The failed scan existed nowhere on either side (the server logs it only at debug), so "the operator can retry it or read it off" was false on exactly the branch where it mattered. The unrestored text now goes into the toast. Covered by `test_unrestorable_scan_text_is_surfaced_in_the_toast`.
  - `[low]` `[patch]` The client gated "is this blank" on JS `trim()`, which strips the full Unicode whitespace set, while the server trims only `' \t\r\n'`. A payload of `\x0b`/`\x0c`/NBSP/BOM — which `test_other_control_characters_are_also_never_trimmed` deliberately pins the server as *keeping* — was therefore dropped by the client with no request and no toast. Added `ScanCapture.stripOuter`, mirroring `_SCAN_TRIM` exactly, and `test_blank_gate_uses_the_servers_trim_set_not_js_trim`.
  - `[low]` `[patch]` A 10-second abort was reported to the operator as "could not reach the server", but an abort cannot distinguish a dropped request from a slow response to one the server processed. Now reported as a timeout with an unknown outcome. Covered by `test_timeout_is_not_reported_as_an_unreachable_server`; the at-least-once consequence for Stories 4.3/4.5 is deferred.
  - `[low]` `[patch]` The comment on the length check called it "a transport limit", which it is not: `get_json()` has already read and parsed the whole body, and `len()` counts code points, not bytes. Corrected to say what it actually bounds, and to point at the deferred `MAX_CONTENT_LENGTH` entry for the real one.
  - `[low]` `[patch]` The debug log claimed to be "the entire diagnostic value of a transport-only endpoint when a scanner starts emitting something unexpected" while logging only a character count — which cannot answer the one question a wedge investigation asks. Now logs `repr(cleaned)`, making control characters visible.
  - `[low]` `[patch]` `escapeHtml` escapes `&`/`<`/`>` but not quotes, and the surrounding comment invited Stories 4.2/4.3 to reuse it for attacker-suppliable barcode payloads. Sufficient for `showToast`'s text-node position (verified: `main.js:395-403` interpolates into `<div class="toast-body">`), so the fix is to document the limit rather than widen the helper.
  - `[low]` `[patch]` The new navbar icon `<i class="bi bi-upc-scan">` carried no `aria-hidden="true"`, so the icon-font glyph may be announced alongside the input's `aria-label`.
  - `[low]` `[patch]` `test_max_scan_length_is_4096` requested the `client` fixture and never used it.
  - `[low]` `[patch]` `test_two_consecutive_scans_each_post_once` asserted only `len(calls) == 2` and discarded the payloads it had already captured — it would have passed if both requests carried `FIRST-SCAN`, the exact residue bug a consecutive-scan test exists to catch. Now asserts the payloads.
  - `[low]` `[patch]` `test_scan_capture_script_is_loaded` asserted `typeof window.ScanCapture === 'object'`, which is true at parse time even when `init()` bailed out at `if (!this.input) return;`. Now also asserts the binding.

## Design Notes

**Why a second navbar field rather than reusing `#ja-id-lookup`.** The JA-ID field uppercases input, gates on `^JA[0-9]{6}$`, and navigates client-side — three behaviors that are wrong for every payload Epic 4 handles, and all three are load-bearing for metal-stock scanning (NFR9). Folding them together would require the classifier that Story 4.2 has not built yet, so the merge cannot be done correctly in this story. Two fields is the honest interim state; reconciling them belongs after 4.5 makes catalog routing real.

**Why `outcome: 'unrouted'`.** The endpoint must return something, and the alternative — inventing the full `ScanResolution` envelope now — would guess at a shape AD-15 fixes in Story 4.3. A single named string states plainly that the transport works and routing does not exist yet, and gives 4.2/4.3 an obvious place to land without renegotiating the request contract or re-touching the template and JS.

**The whitespace rule is the one subtle thing here.** A plain `.strip()` looks harmless and is not: Python strips `\x1c`–`\x1f` as whitespace, so `str.strip()` would eat the trailing `RS` of an ISO/IEC 15434 envelope and Story 4.4 would parse a truncated record. Strip an explicit character set:

```python
_SCAN_TRIM = ' \t\r\n'   # NOT str.strip(): that also eats \x1c-\x1f,
                         # which are ISO/IEC 15434 envelope structure (Story 4.4).

def _clean_scan_input(value):
    return value.strip(_SCAN_TRIM)
```

**Toast on success is optional; toast on failure is not.** A cleared, refocused field is sufficient confirmation for a successful scan and keeps a rapid-scanning operator from drowning in toasts. A failure must be visible, because the retained text in the field is otherwise indistinguishable from a scan that never fired.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the new `tests/unit/test_scan_routes.py`; no pre-existing test newly failing.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: green, including `tests/e2e/test_wedge_scan.py` and the untouched `tests/e2e/test_ja_id_lookup.py`. Requires a 20-minute tool timeout.
- `git diff 80d5212 -- app/static/js/main.js app/static/js/inventory-move.js app/static/js/inventory-shorten.js` -- expected: empty. Proves the NFR9 no-touch boundary.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless` then `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify` -- expected: regenerated PNGs, all under 500 KB and RGB/RGBA.

## Auto Run Result

Status: done

**Follow-up review recommendation: true.** This pass changed operator-visible behavior on three paths (focus handling on failure, field-residue selection after a dropped burst, and what the failure toast carries), added a client-side mirror of the server's trim rule, and introduced new selection semantics that have not themselves been independently reviewed. Both review passes so far have found genuine medium-severity defects in exactly this code — the second pass's headline finding was that the first pass's own `refocus()` guard was defeated one line later — which is the strongest available evidence that another independent look is worth its cost.

**Implemented change.** FR35's wedge-scan capture, as a transport seam and nothing more. A second global navbar input (`#scan-input`) sits beside the metal-stock JA-ID field in `base.html`, so it reaches every page without per-template work. A new `scan-capture.js` binds `keydown` on that field only and, on `Enter`, POSTs the field's value verbatim to a new `POST /api/scan`. The client classifies, normalizes and navigates nothing; the endpoint looks nothing up, touches no database and constructs no service. It validates the payload, trims leading/trailing space/tab/CR/LF **only**, and echoes the cleaned text back with `outcome: 'unrouted'` — the named seam Stories 4.2/4.3/4.5 fill in without renegotiating the request shape, the field, or the transport.

**Files changed.**
- `app/main/routes.py` — new `POST /api/scan` (`api_scan`, `@csrf.exempt`), `MAX_SCAN_LENGTH = 4096`, and `_clean_scan_input()` implementing the narrow trim rule; all rejections go through the AD-13 object-error envelope, all paths logged.
- `app/static/js/scan-capture.js` — new; the `ScanCapture` object literal: Enter-to-POST, an in-flight guard, an abort timeout, conditional clear/restore of the field, conditional refocus, and escaped failure toasts.
- `app/templates/base.html` — the `#scan-input` navbar block (deliberately `type="text"`, no `name` containing `search`, so `main.js`'s `/` shortcut cannot hijack it) plus the global `<script>` tag.
- `tests/unit/test_scan_routes.py` — new; 49 tests covering every server row of the I/O matrix, the trim rule in isolation including its exact boundary, and byte-exact control-character preservation.
- `tests/e2e/test_wedge_scan.py` — new; 23 tests covering field presence across four pages, verbatim posting, clear-and-refocus, the failure paths, the late-response races, and the NFR9 JA-ID regression guard.
- `docs/images/screenshots/` — 12 PNGs plus `metadata.json` regenerated for the navbar change.

**Review findings breakdown.** Two review passes, each with 2 reviewers (adversarial + edge-case).

- *First pass:* **0 intent_gap, 0 bad_spec, 8 patch, 6 defer, 9 reject**. The material finding was a silent-scan-loss race between the in-flight `Enter` guard and an unconditional asynchronous field clear.
- *Follow-up pass:* **0 intent_gap, 0 bad_spec, 12 patch, 2 defer, 17 reject**. Three findings were medium: the first pass's own `refocus()` guard was defeated one line later by an unguarded `select()` (which focuses as a side effect), so the failure path still stole focus; the in-flight guard dropped the second `Enter` but not the second burst's *characters*, so a rescan concatenated and POSTed a silently **wrong** scan; and `handleFailure`'s "operator already rescanned" branch discarded the failed text while the toast still claimed it had been kept. The remaining nine were low: a client/server disagreement about what counts as blank, an abort reported as an unreachable server, two overstated code comments, a text-node-only escaper presented as general-purpose, a missing `aria-hidden`, and four test-strength gaps.

No spec-repair loopback was required in either pass (`review_loop_iteration` stayed 0). The 8 deferrals are in `deferred-work.md`: no app-wide request-body limit, the unescaped `showToast` sink in `main.js`, navbar inputs hidden below the `lg` breakpoint, `inventory-add.js`'s document-level scan-mode handler swallowing keystrokes, whether a wedge can physically type ASCII control characters into a text input (a real risk to Story 4.4), the screenshot generator writing a truncated manifest, the trim rule living as a private symbol in `routes.py` that Story 4.2 must import or duplicate, and the transport's at-least-once semantics on timeout once 4.3/4.5 give the endpoint side effects. Rejections across both passes were design decisions the intent contract states explicitly (`outcome: 'unrouted'` not routing anything; no success toast; no timeout terminator; focus-required capture with no document-level handler), unevidenced layout and browser-compatibility speculation, one artifact of the review input rather than the code, and suggestions that would have made things worse — notably a client-side `maxlength="4096"`, which would silently truncate an over-long payload into a *valid* 200 instead of the loud rejection the server gives today.

**Verification performed.**
- `nox -s tests` — green: **1238 passed**, 345 deselected.
- `nox -s e2e` — green: **344 passed, 1 skipped** in 19m45s, including all 28 `test_wedge_scan.py` cases (23 before the follow-up pass, +5 from the new regression guards) and the untouched `test_ja_id_lookup.py`.
- `git diff 80d5212 -- app/static/js/main.js app/static/js/inventory-move.js app/static/js/inventory-shorten.js` — empty. NFR9's no-touch boundary holds; no JA-ID or metal-stock scan code was modified.
- `node --check app/static/js/scan-capture.js` — clean.
- `nox -s screenshots_verify` — green: all 12 screenshots valid PNG, all under 500 KB. The follow-up pass's only template change is an `aria-hidden` attribute, which has no visual effect, so the PNGs were not regenerated again.

**Residual risks.**
- **Whether a real wedge can deliver ISO/IEC 15434 control characters at all.** The server preserves `\x1d`/`\x1e`/`\x04` byte-for-byte and is unit-tested for it, but browsers do not put non-printable characters into a text input from keystrokes. If the deployed Tera HW0009 emits an envelope as raw control keystrokes, the separators may never reach the field. This is deferred rather than resolved because settling it needs the physical scanner, and every available fix is excluded by this story's stated boundaries. Story 4.4 should confirm it before relying on the preservation path.
- **The field is live on every page and does nothing yet.** By design — routing arrives in 4.2/4.3/4.5 — but until then an operator scanning a catalog part gets a cleared field and no outcome. The `unrouted` value names the state honestly; nothing surfaces it to the operator.
- **Two navbar scan inputs coexist.** Deliberate and argued in Design Notes, but the shop-floor operator now has to know which field a given barcode belongs in. Reconciling them is a post-4.5 decision.
- **The double-scan handling is correct by construction but unexercised against a real scanner's burst timing.** The in-flight guard now warns and selects the residue so the next burst overwrites it; both are verified against synthetic bursts in Chromium, not against a Tera HW0009 emitting two labels back to back.
- **The trim rule now exists in three places** — `_SCAN_TRIM`, its JavaScript mirror `ScanCapture.stripOuter`, and the tests that pin each — with nothing comparing the Python and JS sets. Deferred; it is the reason the rule should move to a pure util before Story 4.2 adds a fourth consumer.
