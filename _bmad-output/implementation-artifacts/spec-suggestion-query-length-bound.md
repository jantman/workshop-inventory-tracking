---
title: 'One length bound on the suggestion query, at both ends of the request (DW-95, DW-162)'
type: 'bugfix'
created: '2026-07-28'
status: 'done'
baseline_revision: '133e3e8b5bcf692ef384386c120d0a062960afe5'
final_revision: '6fc4f37'  # the follow-up review pass
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** The field-suggestions endpoint bounds storability but not length, so a `q` of any size becomes a `%…%` LIKE pattern matched against every row of `inventory_items` (`get_field_value_suggestions` clamps `limit` and refuses unstorable text, but never checks length; the route applies only `.strip()`) — while `search_products` treats storability and length as one pair of guards under `SEARCH_QUERY_MAX_LENGTH`. At the other end of the same request, `field-autocomplete.js` puts the whole current fragment on the wire verbatim, so a pasted multi-kilobyte value overruns the request line and the dropdown fails with nothing but a `console.warn`.

**Approach:** Apply one length bound at both ends. Server-side: reuse `SEARCH_QUERY_MAX_LENGTH` (4096) as the length half of the guard pair in `InventoryService.get_field_value_suggestions`, alongside the storability guard it already has — which requires moving the constant to the neutral `app/utils/sql_text.py` (the inventory service cannot import the catalog service across the AD-1 seam) and re-exporting it from its current home so existing importers are unaffected. Client-side: `buildUrl` refuses to build a URL whose operator-supplied text exceeds the same number, and `fetchAndRender` treats that as `hide()`, for every field the component serves.

## Boundaries & Constraints

**Always:**
- One number, one definition. `SEARCH_QUERY_MAX_LENGTH` keeps its name and value (4096) and is defined exactly once, in `app/utils/sql_text.py`; `app/mariadb_catalog_service.py` re-exports it so `from app.mariadb_catalog_service import SEARCH_QUERY_MAX_LENGTH` keeps working. The JS number is a second copy by necessity (no build step, no module system) and is therefore pinned by a source-text tripwire test, the pattern `tests/unit/test_autocomplete_markup.py` already establishes.
- Over-length is `[]`, never truncation and never an error. A truncated pattern answers a different question; a 400 would be wrong because nothing about the request is malformed. The endpoint keeps its documented 200-with-empty-suggestions contract and its exact response keys (`success`, `field`, `suggestions`; `normalized` only for catalog fields).
- The server guard is answered before a session opens, like the storability guard beside it.
- The client guard suppresses the request entirely (dropdown hidden), which is the same visible outcome the server's `[]` produces — the two ends must not disagree about what an over-long value means.
- Existing behavior for in-bounds queries is unchanged: ordering tiers, dedup, over-fetch, `limit` clamping, sub-location scoping.

**Block If:**
- Moving `SEARCH_QUERY_MAX_LENGTH` into `app/utils/sql_text.py` turns out to break an importer that cannot be fixed by the re-export.

**Never:**
- Do not bound `location` server-side. The stated reasoning for this bound is that no LIKE pattern can safely carry unbounded text; `location` is an equality filter, not a pattern, and the storability rule covers it for a different reason (an unbindable parameter is a 500). Client-side `location` IS bounded, because there the rule is about the request line, not the pattern — state that difference in the comments rather than letting the two look like one rule.
- Do not add a length guard to `CatalogService.get_field_value_suggestions`. Its two fields are already bounded by `normalize_category_path` / `normalize_tag`, which reject over-length input and answer `[]`.
- Do not touch `search_products`' guard logic, `MAX_SCAN_LENGTH`, the scan path, `is_storable_text`, or `escape_like_literal`.
- Do not add `maxlength` attributes to the wired inputs — the product templates carry explicit comments explaining why they have none, and this bound is a transport rule, not a stored-value rule.
- No new e2e test: the pre-fix and post-fix symptoms are both "no dropdown", so a Playwright assertion could not tell them apart.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| In-bounds query | `q` of length ≤ 4096 on any of the five item fields | Unchanged: filtered, ranked suggestions | No error expected |
| Boundary | `q` of length exactly 4096 | Still queried and matched normally | No error expected |
| Over-length query | `q` of length 4097+ on any of the five item fields | `[]` from the service, without emitting any SQL; endpoint returns 200 with `suggestions: []` and the three usual keys | No error expected |
| Over-length, unstorable | `q` of 5000 chars containing `\x00` | `[]`, no SQL | No error expected |
| Over-length `location` (server) | `sub_location` with a 5000-char `location` | Unchanged — the equality filter runs and matches nothing | No error expected |
| Over-length fragment (client) | Input holds a 5000-char value; user types or focuses | No request is issued; dropdown hidden | No `console.warn` — this is a refusal, not a failure |
| Over-length `location` field (client) | `#location` holds 5000 chars, user focuses `#sub_location` | No request is issued; dropdown hidden | No error expected |
| Multi-value fragment (client) | Tags input where one comma-separated fragment exceeds 4096 | No request is issued; dropdown hidden | No error expected |

</intent-contract>

## Code Map

- `app/utils/sql_text.py` -- pure module both services import; new home of `SEARCH_QUERY_MAX_LENGTH` (currently defines `LIKE_ESCAPE_CHAR`, `escape_like_literal`, `is_storable_text`)
- `app/mariadb_catalog_service.py:115-124` -- current definition + its rationale comment; becomes a re-export. `search_products` guard pair at :2579-2590 is the model to mirror; do not change it
- `app/mariadb_inventory_service.py:790-877` -- `get_field_value_suggestions`; storability guard at :864-868, `q` computed at :877, LIKE pattern built at :901-906. The length guard joins the guard block
- `app/main/routes.py:4014-4080` -- `inventory_field_suggestions`; passes `q` through with only `.strip()`. No change needed
- `app/static/js/field-autocomplete.js:44-46, 299-321, 323-344, 346-380` -- module constants, `currentFragment`, `buildUrl`, `fetchAndRender`
- `tests/unit/test_inventory_service.py:428-725` -- `TestFieldValueSuggestions`; the `before_cursor_execute` spy idiom at :663-686 is what proves "without querying"
- `tests/unit/test_routes.py:1654-1999` -- endpoint tests; :1980-1991 is the empty-200 shape assertion to mirror
- `tests/unit/test_autocomplete_markup.py` -- the source-text tripwire idiom for JS/template constants
- `tests/unit/test_scan_resolution.py:54` -- imports `SEARCH_QUERY_MAX_LENGTH` from `app.mariadb_catalog_service`; must keep working unchanged

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/sql_text.py` -- add `SEARCH_QUERY_MAX_LENGTH = 4096`, moving the existing rationale comment and extending it to say the bound now serves both LIKE-pattern builders (search and suggestions), which is why it lives here rather than on either service -- one definition reachable from both sides of the AD-1 seam
- [x] `app/mariadb_catalog_service.py` -- delete the definition, import the constant from `.utils.sql_text`, and leave a short note that the name is re-exported for existing importers -- keeps `search_products` and `tests/unit/test_scan_resolution.py` untouched
- [x] `app/mariadb_inventory_service.py` -- add the length guard to `get_field_value_suggestions`' pre-session guard block and document it in the `query` docstring arg -- the length half of the pair the method was missing
- [x] `app/static/js/field-autocomplete.js` -- add a `MAX_QUERY_CHARS` module constant; make `buildUrl` return `null` when the trimmed fragment or the location value exceeds it; make `fetchAndRender` treat `null` as `hide()` without a warning -- keeps the failure off the wire for every wired field
- [x] `tests/unit/test_inventory_service.py` -- add over-length cases to `TestFieldValueSuggestions`: `[]` with no SQL emitted across the five fields, and the 4096/4097 boundary pair expressed against the imported constant -- covers the I/O matrix rows
- [x] `tests/unit/test_routes.py` -- add an endpoint-level over-length case asserting the empty 200 and the exact three-key body -- proves the guard is reachable through the route
- [x] `tests/unit/test_autocomplete_markup.py` -- add a tripwire asserting the JS `MAX_QUERY_CHARS` literal equals `SEARCH_QUERY_MAX_LENGTH` and that `buildUrl` still carries the guard -- the two copies cannot drift silently

**Acceptance Criteria:**
- Given the five item fields each have stored values, when `get_field_value_suggestions` is called with a query longer than `SEARCH_QUERY_MAX_LENGTH`, then it returns `[]` and no statement reaches the engine.
- Given a query of exactly `SEARCH_QUERY_MAX_LENGTH` characters that matches a stored value, when the same method is called, then the match is still returned — the bound is inclusive.
- Given `SEARCH_QUERY_MAX_LENGTH` is now defined in `app/utils/sql_text.py`, when a module imports it from `app.mariadb_catalog_service`, then it resolves to the same object with value 4096.
- Given a wired input holding text longer than the JS bound, when the component would fetch, then `buildUrl` returns `null`, no `fetch` is issued, and the dropdown is hidden.
- Given the whole change, when `nox -s tests` and `nox -s doctests` run, then both pass with no new failures.

## Spec Change Log

_Empty: no bad_spec loopback occurred._

## Review Triage Log

### 2026-07-28 — Review pass (iteration 0)
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 2, low 7)
- defer: 1: (high 0, medium 0, low 1)
- reject: 4: (high 0, medium 1, low 3)
- addressed_findings:
  - `[medium]` `[patch]` The client bound did not bound the thing it named. `MAX_QUERY_CHARS` capped each parameter at 4096 *pre-percent-encoding* characters, so `q` and `location` at 4096 apiece cleared both checks and emitted an 8272-byte request line (past gunicorn's 8190), and 4096 CJK characters emitted ~37 KB — the request-line overrun DW-162 is about, still reachable. Added `MAX_URL_CHARS = 7000` applied to the finished, already-encoded URL, which is the treatment `_bounded_scan_url` (`app/main/routes.py`) reached for the same transport and writes down ("a per-value byte cap has to assume the worst case for every value at once"). The per-value checks stay — they restate the *server's* rule — and the new one is the transport's. Pinned to `_MAX_SCAN_URL_CHARS` by the tripwire.
  - `[medium]` `[patch]` The refusal path was silent to screen readers, and its own comment claimed otherwise. `render([])` calls `hide()` **then** `announce(0, null)`; `hide()` *clears* the live region, so the bare `hide()` on the refusal landed with the fetch-failure paths — a pasted over-long value produced silence and wiped the previous announcement, where the same input previously produced the server's `[]` and "No suggestions". Added `announce(0, null)`, making the refusal render's no-matches pair rather than a failure.
  - `[low]` `[patch]` `sql_text.py`'s new prose claimed the length bound covers "both of the application's LIKE-pattern builders", which its own census paragraph disproves 30 lines earlier — `InventoryService.search_items` and `mariadb_materials_admin_service` build unescaped `ilike()` patterns and remain outside every rule in the module. Reworded to name what "both" means and to state that the length rule joins, not closes, that census.
  - `[low]` `[patch]` The `fetchAndRender` tripwire could not catch the regression it was written for: three unordered `in` checks meant deleting the `return;` still passed while the component fell through to `fetch(null)` → `GET /null` → 404 → a hide indistinguishable from "no matches". Replaced with a single `REFUSAL_BLOCK` regex matching hide + announce + return as one adjacent block, plus an ordering assertion that the URL check follows `params.toString()`. All three mutations (dropped `return`, dropped URL bound, dropped `announce`) verified to fail the suite.
  - `[low]` `[patch]` "Measured on the argument as passed… the quantity the bound is about is the text that crossed the wire" was self-refuting: the route strips before forwarding and the browser trims before measuring, so neither end measures untrimmed text, and 100 KB of whitespace plus ten characters passes every check. Reworded to the true reason (it sits with its pair, ahead of the session) and the whitespace hole is now named rather than implicitly denied.
  - `[low]` `[patch]` The JS/Python number equality is not a unit equality — `String.length` counts UTF-16 code units, `len()` counts code points, so 2049 astral characters are refused client-side and would be answered server-side. Documented, with why the conservative direction is accepted rather than counting code points per keystroke.
  - `[low]` `[patch]` The component's comment implied one server bound for all seven fields; for `category_path` and `tags` the real server bounds are `MAX_CATEGORY_PATH_LENGTH` (512) and `MAX_TAG_LENGTH` (64), 8×–64× tighter. Qualified: for those two this cap is a ceiling, never the limit.
  - `[low]` `[patch]` The nine-line comment marking where `SEARCH_QUERY_MAX_LENGTH` used to live recorded a fact git already records. Cut to the fact that does not survive elsewhere: the import is a deliberate re-export, so an "unused import" cleanup would break `tests/unit/test_scan_resolution.py`.
  - `[low]` `[patch]` Unexplained magic `904` appeared twice in the new tests; replaced with `100`, which carries the same meaning (comfortably past the bound) without inviting the question.
- deferred (recorded here, NOT written to the ledger — this run was instructed not to edit it):
  - `[low]` The browser half of this change has no executable coverage, and the intent contract's stated reason for skipping e2e ("pre-fix and post-fix symptoms are both 'no dropdown'") is wrong. The new behavior is *no request is issued*, which Playwright observes directly via `page.route` / `page.on('request')` — as would the companion regressions (a legal 4096-character query still being sent; the refusal not wedging the component for the next keystroke). The only assertions about the browser behavior today are source-text regexes. The contract froze the no-e2e decision, so this is left for a focused follow-up rather than resolved here.
- rejected:
  - `[medium]` `location` left unbounded server-side could ship a multi-megabyte parameter to MariaDB. Not reachable through the only entry point: a GET query string that size does not survive the WSGI request line, the client now bounds the finished URL, and the spec made this call deliberately on stated reasoning (the bound is about what a LIKE pattern can carry; an equality filter is not a pattern).
  - `[low]` Non-`str` `query` (bytes, int) skips both guards. `app/utils/sql_text.py` documents this stance explicitly — "a `TypeError` out of `None.replace` is a more useful report of a wiring mistake" — the route always yields `str`, and the new guard correctly matches the shape of the pair it joined.
  - `[low]` New tests seed values past the declared column widths, so they would fail on MariaDB. The unit suite is SQLite by fixture construction (`test_storage`), the docstrings state the assumption, and the alternative removes the seeded row that makes these tests mutation-sensitive.
  - `[low]` No route-level test for the inclusive boundary or for over-length `location`. The route contributes no length logic; the service tests pin the comparison operator, and a route-level copy would assert the same thing one layer out.

### 2026-07-28 — Review pass (follow-up, iteration 0)
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 0, low 4)
- defer: 2: (high 0, medium 0, low 2)
- reject: 10: (high 0, medium 0, low 10)
- addressed_findings:
  - `[low]` `[patch]` The service comment contradicted itself about what it measures. "Measured on the argument as passed rather than on the stripped `q`" was followed five lines later by "100 KB of spaces plus ten characters passes every check here" — false for this method, which measures the raw argument and refuses it. The sentence is only true end-to-end, because the route strips first. Reworded to say both true things: the guard measures the argument as passed, `search_products` measures `query.strip()`, the divergence is visible only to a direct caller passing unstripped padding, and the whitespace this bound does not reach arrives here already dropped by the route.
  - `[low]` `[patch]` The worked example was arithmetically wrong in two places. `q` and `location` at 4096 apiece assemble to 8259 characters, not the 8272 stated in `field-autocomplete.js` and copied into the tripwire's docstring (base 45 + `?q=` + 4096 + `&limit=10` + `&location=` + 4096). Verified by construction; the conclusion — past 8190 — is unchanged. Corrected in both places rather than left as a number presented as measured.
  - `[low]` `[patch]` `sql_text.py`'s docstring claimed the length bound now covers "both halves of that endpoint's search-shaped path instead of one". It covers one half. The suggestions endpoint's catalog half never consults the constant — `normalize_category_path` (512) and `normalize_tag` (64) bound it before a pattern exists, which the spec deliberately chose. Rewritten to name the constant's two actual callers (`search_products` and `InventoryService.get_field_value_suggestions`, the two LIKE-pattern builders on opposite sides of the seam) and to state why the catalog half is deliberately not one of them.
  - `[low]` `[patch]` `MAX_QUERY_CHARS_DECL`'s docstring claimed an anchoring the regex cannot deliver: "anchored ... to the line start so it is the MODULE constant that is read rather than some future shadowing local". The pattern is `^\s*const ...`, and the `\s*` is *required* because every declaration in that file is indented inside its IIFE — so it cannot distinguish the module constant from an equally-indented local, and `search` takes whichever comes first. Reworded to the property it actually has.
- deferred (appended to the ledger as new entries, per this run's instruction):
  - `[low]` DW-222 — the 7000-character URL ceiling is justified by gunicorn's *maximum permitted* `limit_request_line` (8190), not its default (4094); gunicorn is not a declared dependency and the repo carries no server config. Pre-existing: `_MAX_SCAN_URL_CHARS` and this reasoning arrived in commit cfc7102, before this spec's baseline. This change copied the number into a second file and pinned the two together, which is what makes correcting it one edit.
  - `[low]` DW-223 — the browser half has no executable coverage; the only assertions are source-text regexes slicing on exact indentation. The contract's stated reason for skipping e2e ("both symptoms are 'no dropdown'") is not the property that changed — *no request is issued* is directly observable via `page.route`. Frozen by the contract's "Never" list, so a spec decision rather than a review patch.
- rejected:
  - `[low]` Non-`str` `query` (bytes, int) skips both guards. `sql_text.py` documents this stance explicitly; the route always yields `str`; the new guard matches the shape of the pair it joined. Same rejection as the first pass.
  - `[low]` `CatalogService.get_field_value_suggestions` never consults `SEARCH_QUERY_MAX_LENGTH`. The contract forbids adding it, on stated reasoning the normalizers already bound those two fields far tighter.
  - `[low]` Pinning `MAX_QUERY_CHARS` to `SEARCH_QUERY_MAX_LENGTH` couples the browser's `location` bound to a LIKE-pattern ceiling `location` is not subject to. Deliberate and documented in the constant's own comment; the alternative is a third number.
  - `[low]` The bound is 20x-200x wider than the columns it filters, so it never fires on storable input, and no `maxlength` was added. The contract forbids `maxlength` explicitly and says why; this is a transport/pattern bound, not a validation rule.
  - `[low]` The `OperationalError`-to-500 risk is unreachable through a GET whose request line no server would accept. True, and the guard is defence-in-depth for exactly that reason — DW-95 frames it the same way, and the route-level test reaches it because Werkzeug's test client imposes no request-line limit.
  - `[low]` New tests seed values past the declared column widths, so they would fail on MariaDB. The unit suite is SQLite by fixture construction, the docstrings state the assumption, and no honestly-sized value could contain a 4097-character substring. Same rejection as the first pass.
  - `[low]` `test_autocomplete_markup.py` was a pure text-scanner and now imports `_MAX_SCAN_URL_CHARS` from `app.main.routes`. Importing the constant is what makes the tripwire robust; regexing it out of a second source file to preserve the module's "scanned as text" character would trade correctness for consistency, and that rationale is about Jinja templates, not Python constants.
  - `[low]` Two of the three parametrized over-length cases exercise the same branch, at ~1 MB of throwaway strings. The `far-over` and `over-and-unstorable` cases pin different claims (magnitude-independence, and that neither guard is load-bearing alone); the cost is milliseconds.
  - `[low]` The tripwire's failure message says the two numbers "are one rule stated twice" while the source documents that their units differ. They are one rule; the UTF-16-vs-code-point caveat is about measurement, and the comment three lines above the constant already carries it.
  - `[low]` The refusal is indistinguishable from "nothing matched", and an over-long `location` darkens the sub-location dropdown with no console signal. That identity is the contract's explicit requirement — "the two ends must not disagree about what an over-long value means" — and the suppressed warning is the first pass's deliberate patch.

## Design Notes

Why `app/utils/sql_text.py` and not a mirrored constant: the module's own docstring already argues the case — "Every caller of these two rules is somewhere that cannot import the others… A sibling pure module is the one seam all three can reach." The length bound is a third question of the same kind, asked about the same object (a LIKE pattern built from operator text), by callers on both sides of the AD-1 seam. Mirroring the number into the inventory service would recreate exactly the drift DW-42 closed for the escaper.

The guard, mirroring `search_products`' ordering (length before storability) inside the existing pre-session block:

```python
        if isinstance(query, str) and len(query) > sql_text.SEARCH_QUERY_MAX_LENGTH:
            return []
        if isinstance(query, str) and not sql_text.is_storable_text(query):
            return []
```

Judged on the argument as passed, like the storability guard beside it, rather than on the stripped `q` computed further down: the quantity the bound is about is the text that crossed the wire, and the route has already stripped what it forwards.

Client-side, `buildUrl` returning `null` keeps the fragment-reading in one place rather than duplicating `currentFragment().fragment.trim()` into `fetchAndRender`. The `null` branch must not `console.warn`: a warning is the file's signal for an unexpected failure, and refusing to send a request we know the server will answer `[]` to is an ordinary decision.

## Verification

**Commands:**
- `venv/bin/nox -s tests` -- expected: pass, including the new cases (prefix with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`)
- `venv/bin/nox -s doctests` -- expected: pass
- `venv/bin/python -c "from app.mariadb_catalog_service import SEARCH_QUERY_MAX_LENGTH as a; from app.utils.sql_text import SEARCH_QUERY_MAX_LENGTH as b; assert a is b == 4096"` -- expected: no output, exit 0

**Manual checks (if no CLI):**
- `app/static/js/field-autocomplete.js` -- `MAX_QUERY_CHARS` is 4096, `buildUrl` returns `null` on the over-length branch, and `fetchAndRender` hides without warning on `null`.

## Auto Run Result

Status: done

**Implemented change.** Unchanged from the implementation pass in behavior: one length bound on the suggestion query, applied at both ends of the same request. Server-side, `InventoryService.get_field_value_suggestions` answers `[]` before a session opens for a query longer than `SEARCH_QUERY_MAX_LENGTH` (4096, DW-95), alongside the storability guard and in the order `search_products` asks the two questions; the constant moved to `app/utils/sql_text.py` because the two services cannot import each other across the AD-1 seam, with `app/mariadb_catalog_service.py` re-exporting the name. Client-side (DW-162), `buildUrl` returns `null` when either operator-supplied parameter exceeds the server's bound or when the finished, percent-encoded URL exceeds `MAX_URL_CHARS` (7000), and `fetchAndRender` answers that with `hide()` + `announce(0, null)`.

**This follow-up pass changed no behavior.** All four patches correct statements the code makes about itself — comments and test docstrings that were verifiably false. No production logic, no test assertion, and no constant was altered; `nox -s tests` reports the same 3390 passed as the implementation pass.

**Files changed in this pass.**
- `app/mariadb_inventory_service.py` -- the guard's comment no longer claims the method measures stripped text and unstripped text at once; it now states the real asymmetry with `search_products` and where the whitespace hole actually is
- `app/utils/sql_text.py` -- the module docstring no longer claims the length bound covers both halves of the suggestions endpoint; it names the constant's two real callers and why the catalog half is deliberately not one
- `app/static/js/field-autocomplete.js` -- the worked request-line example corrected from 8272 to 8259 characters
- `tests/unit/test_autocomplete_markup.py` -- the same 8272→8259 correction in the tripwire docstring, and `MAX_QUERY_CHARS_DECL`'s docstring reworded to the anchoring property the regex actually has
- `_bmad-output/implementation-artifacts/deferred-work.md` -- two new entries appended (DW-222, DW-223); no existing entry touched

**Review findings.** 4 patches applied (all low), 2 deferred (both low), 10 rejected, 0 intent gaps, 0 spec defects — no spec amendment and no implementation loopback. Both reviewers converged on the same substantive observation, the whitespace/measurement asymmetry between the two halves of the "one guard pair"; the behavior there is what the contract chose, so what was fixed is the comment that overstated the symmetry. See the Review Triage Log for the rejection reasons.

**Verification.**
- `nox -s tests` -- 3390 passed, 2 skipped, 456 deselected
- `nox -s doctests` -- 22 passed
- Re-export identity check (`a is b == 4096` across both import paths) -- exit 0
- The 8259 figure computed by construction rather than asserted; `_MAX_SCAN_URL_CHARS`'s provenance (commit cfc7102, before this baseline) confirmed by `git log -S`, which is what makes DW-222 pre-existing rather than introduced here
- `nox -s e2e` and `nox -s screenshots` not run: this pass touched only comments and docstrings, no template, CSS, or markup

**Residual risks.**
- Unchanged from the implementation pass: the browser half is pinned only by source-text regexes (now DW-223), the two JS numbers are hand-copied and kept honest by a tripwire, and the unit suite exercises SQLite only.
- `MAX_URL_CHARS`/`_MAX_SCAN_URL_CHARS` rest on a gunicorn figure that is the maximum rather than the default, against a server this repo does not configure (now DW-222).
- The `## Design Notes` paragraph on judging the argument as passed still carries the phrasing the *first* review pass replaced in the code ("the quantity the bound is about is the text that crossed the wire"). Left as written: amending non-contract spec prose is the bad_spec path, and no bad_spec finding arose. The Review Triage Log above records the corrected reasoning.

