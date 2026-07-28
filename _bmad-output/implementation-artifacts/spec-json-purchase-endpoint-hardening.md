---
title: 'The JSON purchase endpoint bounds `quantity` and refuses a body that is not an object'
type: 'bugfix'
created: '2026-07-28'
status: 'done'
baseline_revision: '9fd6930'
final_revision: '9f9dbe3'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `api_record_purchase` (`app/main/routes.py:2061`) has two boundary holes its HTML twin does not. (DW-86) `quantity` is parsed as a bare `int(...)` with no bound, so `{"quantity": 100000000000000000000}` overflows the 32-bit `INTEGER` column and comes back as the generic `server_error` 500 naming no field — the exact DW-25 symptom the rest of this endpoint no longer has — while `0` and `-3` are stored as typed and a JSON `1e400` raises `OverflowError` (caught by neither `TypeError` nor `ValueError`) into the same 500. (DW-90) `request.get_json(silent=True) or {}` leaves a JSON array, string or number as-is, so the first `body.get(...)` raises `AttributeError` and the client gets a generic 500 instead of the AD-13 envelope this endpoint otherwise honors.

**Approach:** Two guards in `api_record_purchase`, both before any write. Bound the already-parsed integer with `0 < quantity <= _MAX_INT32` (and add `OverflowError` to the parse catch) so every unstorable quantity is an `invalid_field` 400 naming `quantity`. Require the decoded body to be a `dict`, answering `invalid_request` 400 otherwise.

## Boundaries & Constraints

**Always:**
- The shipped JSON contract for valid input is unchanged: `{'quantity': 5}` records a purchase (`test_record_purchase_endpoint_creates_201`), `{}` still records an all-null purchase, and every currently-accepted `unit_price`, text and date value still behaves as it does today.
- Bound the PARSED int, never the raw value: the form's `_positive_int_string` takes a string while this contract takes an int, so the parser is not shared and the bound is stated here.
- A refusal writes nothing, and uses the AD-13 envelope (`{success: false, error: {code, message, field?}}`) with HTTP 400 — never a 500, never an unhandled exception.
- `field` is set for a field-scoped refusal (`quantity`) and omitted for the body-shape refusal, which names no field.
- Every new bound is documented in place with why the backend cannot be trusted to enforce it: the unit suite runs on SQLite, which widens `INTEGER` silently, so a green suite proves less than it appears to for this column.

**Block If:** Nothing. Both refusals are prescribed by their ledger entries; no product decision is open.

**Never:**
- Do not reuse `_positive_int_string` or make the JSON side reject a string `"5"` — that would break the shipped contract, and DW-86 says so explicitly.
- Do not add a "whole number" rule: `3.7` stores `3`, `true` stores `1` and `"٥"` stores `5` today and must keep doing so. That is `int()`'s coercion lenience, the counterpart of `Decimal`'s (DW-89), not the bound this closes; narrowing it is a new business rule.
- Do not touch the non-string text values (DW-87), the `date.fromisoformat` grammar (DW-88), `_purchase_unit_price`, `_purchase_text_length_error`, `_purchase_date_order_error`, `_parse_purchase_form`, or any HTML-form behavior or message.
- Do not change `CatalogService.record_purchase`, the 201 success body, the route's error codes for existing refusals, or any schema.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`; the orchestrator records resolution.

## I/O & Edge-Case Matrix

All rows are `POST /api/products/<existing id>/purchases`. "stored" means a Purchase row exists afterward.

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ordinary quantity | `{"quantity": 5}` | 201, stored with `quantity == 5` | No error expected |
| Quantity at the column edge | `{"quantity": 2147483647}` | 201, stored exactly | No error expected |
| Quantity as a digit string | `{"quantity": "5"}` | 201, stored as `5` (unchanged contract) | No error expected |
| Past the column | `{"quantity": 2147483648}`, `{"quantity": 100000000000000000000}` | 400, nothing stored (was: 500 naming no field) | `invalid_field`, `field='quantity'` |
| Non-finite JSON number | raw body `{"quantity": 1e400}` | 400, nothing stored (was: `OverflowError` → 500) | `invalid_field`, `field='quantity'` |
| Not positive | `{"quantity": 0}`, `{"quantity": -3}` | 400, nothing stored (was: 201 storing it) | `invalid_field`, `field='quantity'` |
| Unparseable quantity | `{"quantity": "abc"}`, `{"quantity": [1]}` | 400, nothing stored (unchanged) | `invalid_field`, `field='quantity'` |
| Absent / empty quantity | `quantity` absent, `null`, or `""` | 201, `quantity` NULL (unchanged) | No error expected |
| Coercible quantity | `{"quantity": 3.7}`, `{"quantity": true}` | 201, stored as `3` / `1` — unchanged, deliberate | No new error |
| Empty object body | `{}` | 201, all-null purchase (unchanged) | No error expected |
| Non-object JSON body | `[1, 2]`, `"hello"`, `5`, `null` | 400, nothing stored (was: `AttributeError` → 500) | `invalid_request`, no `field` |
| Absent or unparseable body | no body at all, or `{oops` with a JSON content type | 400, nothing stored (was: 201 storing an all-null row) | `invalid_request`, no `field` |

</intent-contract>

## Code Map

- `app/main/routes.py:2059-2150` -- `api_record_purchase`: the only file to change. Line 2067 is the `or {}` DW-90 names; lines 2101-2105 are the `int(quantity)` block DW-86 names.
- `app/main/routes.py:2049` -- `_catalog_json_error`: the AD-13 envelope builder; `field` is omitted when falsy.
- `app/main/routes.py:824-856` -- `_MAX_INT32` (the 32-bit column bound to reuse) and `_positive_int_string` (the form's string rule — deliberately NOT reused here).
- `app/main/routes.py:1920-1929` -- the form's `quantity` branch and its message, for contrast: it refuses what this endpoint coerces.
- `app/main/routes.py:2748-2752` (`api_scan`) -- the sibling's non-dict body handling: it coerces to `{}` because an absent `raw` is already a refusal there. Here an empty body is VALID, so coercion would silently record a row; hence a distinct refusal. (The function is `api_scan`; there is no `api_resolve_scan` — `resolve_scan` is the service method it calls.)
- `ARCHITECTURE-SPINE.md:152` ("API success") -- states the body-reading convention as `request.get_json() or {}`, i.e. exactly the expression DW-90 requires removing. The departure is deliberate and recorded in the code; restating the convention is deferred (DW-210).
- `app/mariadb_catalog_service.py:1851-1860` -- `record_purchase` defaults a missing `order_date` to today, so an empty body records a dated row, not an all-null one.
- `tests/unit/test_product_routes.py:3661` -- `TestRecordPurchaseEndpointHoldsTheSameColumnBounds`: the sibling class and its `_refusal` shape helper; its docstring disclaims `quantity` parity and must stay accurate.
- `app/api_client.py:578-598` -- `record_purchase`: the shipped programmatic client. It always POSTs a dict and surfaces `error.code`/`error.field`, so both new refusals reach a caller intact.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- In `api_record_purchase`, replace `request.get_json(silent=True) or {}` with a decode that refuses any non-`dict` result via `_catalog_json_error('invalid_request', ..., 400)`. Comment why this endpoint refuses rather than coercing like `api_resolve_scan`, and why an absent/unparseable body is refused with the rest. -- Closes DW-90; the `or {}` cannot simply be kept, since `[] or {}` and `0 or {}` are `{}` and would swallow two of the very bodies being refused.
- [x] `app/main/routes.py` -- In the same function, add `OverflowError` to the `quantity` parse catch and bound the parsed value with `0 < quantity <= _MAX_INT32`, returning `invalid_field` + `field='quantity'`. Comment that the bound is the column's and the parser deliberately is not the form's, and record what `int()` still coerces. -- Closes DW-86 without touching the parser the contract depends on.
- [x] `tests/unit/test_product_routes.py` -- Add one test class per ledger entry covering every I/O matrix row above: status, `error.code`, `error.field` (present for `quantity`, absent for the body-shape refusal), and that `get_purchases_for_product` is unchanged after each refusal. Amend `TestRecordPurchaseEndpointHoldsTheSameColumnBounds`'s docstring so its `quantity` disclaimer stays true: the PARSERS still differ, but the column bound is now enforced on both sides. -- The matrix is the contract, and the two 500s it removes are invisible to any existing test.

**Acceptance Criteria:**
- Given any input in the I/O matrix above, when it is POSTed, then the response is the AD-13 400 named there and no unhandled exception is raised. The claim is bounded by the matrix, not general: DW-87 (a non-string text value) and DW-88 (the ISO date grammar) are still open, so the endpoint has other inputs that reach a generic 500.
- Given the existing purchase tests (`test_record_purchase_endpoint_creates_201`, `TestRecordPurchaseEndpointHoldsTheSameColumnBounds`, `TestBothPurchaseEntryPointsAgreeOnUnitPrice`, `TestPurchaseFormRefusesWhatTheColumnCannotHold`), when the suite runs, then they pass with no change to their assertions.
- Given the HTML purchase form, when any of its inputs is submitted, then its behavior and messages are byte-identical to before this change.

## Spec Change Log

## Review Triage Log

### 2026-07-28 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 0, medium 5, low 6)
- defer: 3: (high 0, medium 0, low 3)
- reject: 6: (high 0, medium 0, low 6)
- addressed_findings:
  - `[medium]` `[patch]` The body-shape message misstated the cause for most of the bodies it refuses: a good object sent as `text/plain`, a form encoding, unparseable bytes and a >4300-digit integer literal all decode to the same `None` and were told the body "must be a JSON object". The message now names the media type as well as the shape and is documented as one requirement statement covering every arrival, on `_purchase_unit_price`'s `not_a_number` precedent, and a `logger.warning` naming the decoded type distinguishes the cases for an operator — the sibling `api_scan` logs its refusals and this one logged nothing.
  - `[medium]` `[patch]` The change contradicted the architecture spine's "API success" row, which still gives `request.get_json() or {}` as the body-reading convention, with no acknowledgement anywhere. The departure and its reason are now recorded at the guard, the spine line is in the Code Map, and restating the convention repo-wide is deferred (DW-210) rather than done as a side effect of a bugfix.
  - `[medium]` `[patch]` `{"quantity": false}` and any fraction under 1 (`0.5`) truncate to 0 and are now refused, where they were stored as 0 — a behavior change the code comment and the tests both described as unchanged (they covered only `true` → 1 and `3.7` → 3). Corrected in place and pinned by `test_a_value_that_truncates_to_zero_is_refused_as_the_zero_it_became`, including the honest cost that `0.5` is told it must be greater than 0.
  - `[medium]` `[patch]` The Content-Type behavior change was in neither the matrix nor any test: a valid JSON object sent as `text/plain`, with no content type, or form-encoded answered 201 with every value silently dropped and now answers 400. Pinned by `test_an_object_sent_as_the_wrong_media_type_is_refused_not_dropped`.
  - `[medium]` `[patch]` The amended sibling docstring claimed the two entry points now share the column's 32-bit bound, but nothing pinned it — and they do not share a helper, so the rule is written twice in two spellings and only `_MAX_INT32` is common. Added `_QUANTITY_BOUND_VERDICTS` and `TestBothPurchaseEntryPointsAgreeOnQuantityBounds`, the same anti-drift device `_UNIT_PRICE_VERDICTS` and `_DATE_ORDER_VERDICTS` already use.
  - `[low]` `[patch]` The sibling function the whole design decision leans on was cited as `api_resolve_scan` at lines 2660-2664 in the code comment, the test docstring and the spec Code Map. No such function exists: it is `api_scan`, guard at 2748-2752, and `resolve_scan` is the service method it calls. Corrected in all three.
  - `[low]` `[patch]` "All-null purchase" was false in four places: `record_purchase` defaults a missing `order_date` to today, so `{}` records a dated row. The test asserted only the three fields that are null, stepping around the one that falsifies it; it now asserts `order_date` too, and the phrase is gone from the code comment, the test name and the class docstring.
  - `[low]` `[patch]` `'null'` was parametrized with the three bodies that "decode to something without a `.get`, which is where the 500 came from" — but `null` decodes to `None`, took the `or {}` branch and answered 201. Moved to the falsy/absent class, whose docstring describes exactly that.
  - `[low]` `[patch]` The >4300-digit integer literal path was undocumented and untested: CPython refuses to parse it, so `json` raises inside `get_json` and the body-shape refusal answers for what is really a `quantity` problem. Named in the comment (the same `sys.int_info.str_digits_check_threshold` cap `_positive_int_string` documents) and pinned at both 4300 and 4301 digits.
  - `[low]` `[patch]` Acceptance Criterion 1 claimed "any body the endpoint cannot honor" answers an AD-13 400, which DW-87 falsifies today. Narrowed to the matrix, naming the two entries that keep the generic 500 reachable.
  - `[low]` `[patch]` The two new refusals emitted no log line at all, unlike `api_scan`'s. A bounded `logger.warning` (the decoded type name, never the body) was added on the body-shape path.
  - `[low]` `[defer]` DW-209 — the dozen legacy `request.get_json() or {}` inventory/admin routes still answer a non-object body as a generic 500. DW-90's own "every AD-13 endpoint" recommendation is satisfied (all three AD-13 readers are guarded); this is the same defect in a different family.
  - `[low]` `[defer]` DW-210 — the spine's body-reading convention.
  - `[low]` `[defer]` DW-211 — a whitespace-only `quantity` 400s while a whitespace-only `unit_price` means "no price", pre-existing and the mirror of a fix the parent spec applied to the price alone.
  - `[low]` `[reject]` The claim that `/api/inventory/items` has the same hole is false: `_normalize_json_item_payload` opens with `if not isinstance(json_body, dict): raise ValueError('Request body must be a JSON object')`, answered as a 400. Verified before deferring it.
  - `[low]` `[reject]` That the body-shape refusal is reachable only after the product lookup (404 first, one DB round-trip per malformed request). Pre-existing ordering, and 404-before-body is conventional REST.
  - `[low]` `[reject]` That `invalid_request` is minted against the spine's "`app/exceptions.py` hierarchy maps into `error.code`". The catalog routes' lowercase codes (`not_found`, `invalid_field`, `server_error`) already diverge from that hierarchy; the new code matches its neighbours, which is the consistency that matters to a client.
  - `[low]` `[reject]` That the body-shape message's capitalization and full stop are inconsistent with `'quantity must be an integer'`. The endpoint already emits both styles, because the shared-helper messages it reuses from the form are capitalized sentences.
  - `[low]` `[reject]` That a wrong media type should be a 415 rather than a 400. DW-90 prescribes the AD-13 400 envelope, and 400 is what every refusal on this endpoint answers.
  - `[low]` `[reject]` Comment volume (55 lines for 9 lines of code). The density matches the surrounding file, whose helpers carry 40-line docstrings; the real complaint — that two of the three copies were factually wrong — is patched above.

### 2026-07-28 — Review pass (follow-up)

- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 1, low 5)
- defer: 2: (high 0, medium 1, low 1)
- reject: 9: (high 0, medium 0, low 9)
- addressed_findings:
  - `[medium]` `[patch]` `_QUANTITY_BOUND_VERDICTS` was advertised as the device pinning the two entry points' agreement, but keyed every refusal row on the fragment `'2147483647'` — including `0` and `-3`, which break the LOWER bound — so either side could have stopped stating "greater than zero" entirely and the table would still pass. Neither side varies its wording by which half was broken (one sentence states the whole rule), so a discriminating per-row fragment does not exist; the row now carries the verdict (`storable`) and each side asserts its own message WHOLE against `_FORM_QUANTITY_REFUSAL` / `_JSON_QUANTITY_REFUSAL`.
  - `[low]` `[patch]` The new code comment and the new test docstring both cited `sys.int_info.str_digits_check_threshold` as the 4300-digit parse cap. Measured on this checkout that constant is **640** — the floor `set_int_max_str_digits` accepts; the parse limit is `sys.get_int_max_str_digits()` / `default_max_str_digits`. Both new copies now name the right one, note that it is 4300 only by default and per-process settable, and point at the pre-existing misnaming in `_positive_int_string` (deferred, DW-213, since the Never list protects that helper). The two tests that straddled the boundary now derive their lengths from `sys.get_int_max_str_digits()` instead of hard-coding 4300/4301, which was an assertion about the environment.
  - `[low]` `[patch]` The comment claimed the `logger.warning` lets an operator "tell the cases apart". It cannot: of the twelve non-object bodies the tests exercise, seven (no body, `null`, unparseable bytes, `text/plain`, no content type, form-encoded, the over-long literal) decode to `None` and emit the identical line. The comment now states what the log actually separates, and why the fields that WOULD discriminate (`request.content_type`, whether bytes arrived) are deliberately not logged on a `@csrf.exempt` unthrottled route — they are client-supplied and unbounded, which is the whole reason the log carries a type name.
  - `[low]` `[patch]` `test_a_non_object_json_body_is_refused_not_dereferenced` credited `5` with demonstrating why `or {}` could not be kept in front of the guard — but `5 or {}` is `5`, so it demonstrates nothing about ordering. All three values in that test are truthy. The argument moved to the falsy test, where `[] or {}` and `0 or {}` actually make it.
  - `[low]` `[patch]` The 4301-digit half of `test_an_integer_literal_python_cannot_parse_is_refused_here` asserted only `error['field'] == 'quantity'` — no `code`, no message — so a refusal that returned `invalid_request` with a stray field, or the wrong message, passed. It now asserts the full AD-13 shape like every other assertion in the class.
  - `[low]` `[patch]` The parse catch this change widened had untested arrivals: `Infinity`/`-Infinity` (the spelling `json.dumps` actually EMITS for a non-finite float, and the `OverflowError` path a real client reaches — only the hand-written `1e400` was covered), `NaN`, a dict `quantity` (the `TypeError` half of the original catch, previously represented only by a list), and an over-long `quantity` sent as a STRING — the path this endpoint's string-accepting contract exists for, which lands on `invalid_field`/`quantity` rather than the body-shape refusal. All added; behavior was already correct in every case.
  - `[medium]` `[defer]` DW-212 — a deeply nested JSON body raises `RecursionError` out of `get_json(silent=True)` itself, on every JSON route. Reproduced live at 600 KB / depth 100000, under the 1 MiB body cap. Pre-existing and one line ahead of this change's guard.
  - `[low]` `[defer]` DW-213 — the same wrong-constant citation in `_positive_int_string`, which the Never list forbids touching here.
  - Rejected (9, all low): the new `logger.warning` as a log-flood amplifier (`api_scan` already logs one WARNING per refusal on the same route family; DW-14/DW-63 were closed by human decision); that the bound belongs in the service or a schema `CHECK` rather than a second route copy (the Never list forbids both, and every other column on this endpoint is validated at the route); rationale duplicated across five artifacts, and `_product`/`_refusal` copied into two more test classes (comment-volume and helper-duplication complaints, both matching the surrounding file; the volume complaint was rejected last pass too); that no test pins 404-before-body-shape (pre-existing ordering shared by every refusal on the route); that the spec's I/O matrix lacks rows for the media-type and truncate-to-zero behaviors (the matrix is inside the frozen intent contract, and both are entailed by rows it already has — "Absent or unparseable body" and `{"quantity": 0}` against the documented `int()` coercion); that the breaking change ships with no client-facing record (checked: the repo has no API reference to update, `app/api_client.py` posts with `json=`, and no JS or template calls the route); that the JSON half of the verdict table duplicates the dedicated class (inherent to the `_UNIT_PRICE_VERDICTS` pattern it copies); and that a year below 1000 overflows MariaDB's DATE range (unverified, contradicted by MariaDB's documented `'0000-01-01'` floor, on a path DW-88 already owns and this spec's Never list protects).

## Design Notes

The two guards sit at opposite ends of the same function and share one reason for existing: `record_purchase` validates nothing, so this route is the only gate in front of the columns.

```python
body = request.get_json(silent=True)
if not isinstance(body, dict):
    return _catalog_json_error(
        'invalid_request',
        'Request body must be a JSON object sent as application/json.', 400)
...
if quantity is not None and not 0 < quantity <= _MAX_INT32:
    return _catalog_json_error(
        'invalid_field',
        f'quantity must be greater than 0 and no more than {_MAX_INT32}',
        400, field='quantity')
```

Two message decisions. The body-shape message names no field because AD-13's `field` identifies a JSON key and there is no key to name — `_catalog_json_error` already omits it when falsy. It is also ONE message for every way a body fails to arrive as an object, on the same reasoning as `_purchase_unit_price`'s single `not_a_number` string: `silent=True` hands the route the same `None` for a missing body, a wrong content type, unparseable bytes and a >4300-digit integer literal, so the message states the requirement rather than the diagnosis — and states all of it, media type included, since for a good object sent as `text/plain` the shape was never the problem.

The quantity message does NOT reuse the form's sentence ("Quantity must be a whole number greater than zero and no more than 2147483647"): that sentence promises a *whole number* rule this endpoint does not apply, so copying it would state a rule the code does not enforce. `quantity` is the one column whose two entry points genuinely differ, and this message says only what is true here — matching the lowercase, machine-facing wording of the `'quantity must be an integer'` message three lines above it. The cost of bounding after parsing rather than instead of it: `False` and any fraction under 1 truncate to 0 and are refused as that zero, where they used to be stored as 0.

Because the bound is written twice in two spellings (`_positive_int_string`'s `parsed <= 0 or parsed > _MAX_INT32` against the guard's `not 0 < quantity <= _MAX_INT32`) and only `_MAX_INT32` is shared, the agreement between the two entry points is pinned by a `_QUANTITY_BOUND_VERDICTS` table driven through both — the same anti-drift device `_UNIT_PRICE_VERDICTS` and `_DATE_ORDER_VERDICTS` already use, and more necessary here, since those two rules at least share a helper.

`invalid_request` is a new `code` value. AD-13 freezes the envelope's *shape*, not a code vocabulary (`ARCHITECTURE-SPINE.md` line 153), and the shipped client reads `error.code` as an opaque string, so a new code is additive.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, with the pre-existing purchase-endpoint and purchase-form tests unmodified and passing.


## Auto Run Result

Status: done

**Implemented change.** This was a follow-up review pass over an already-shipped change (`6694e41`), not a re-implementation. The shipped behavior of `POST /api/products/<id>/purchases` is unchanged by this pass: `quantity` is still bounded by `0 < quantity <= _MAX_INT32` on the parsed int with `OverflowError` added to the parse catch (DW-86), and the decoded body must still be a `dict` or the request is an `invalid_request` 400 in the AD-13 envelope (DW-90). Every finding this pass acted on was a statement that was FALSE or a test that pinned less than it claimed. The only `app/` edit is a comment block; not one line of executable code changed.

**Files changed.**
- `app/main/routes.py` -- `api_record_purchase`'s body-shape comment only: the CPython integer-parse cap is `sys.get_int_max_str_digits()` (4300 by default, per-process settable), not `sys.int_info.str_digits_check_threshold` (which is 640), and the `logger.warning` now claims only what it actually distinguishes — the bodies `get_json` decoded, not the seven that collapse to `None`.
- `tests/unit/test_product_routes.py` -- `_QUANTITY_BOUND_VERDICTS` rekeyed on the verdict with each side's message asserted whole (the old shared `'2147483647'` fragment did not discriminate the lower-bound rows); two docstrings corrected (`5 or {}` is `5`, so `5` never demonstrated the `or {}` ordering argument — `[]` and `0` do); the over-long-literal test given full AD-13 assertions on both halves and lengths derived from `sys.get_int_max_str_digits()`; and four untested arrivals on the widened parse catch added — `Infinity`/`-Infinity`/`NaN`, a dict `quantity`, and an over-long `quantity` sent as a string.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- two new entries (DW-212, DW-213). No existing entry read, modified, or re-opened.

**Review findings breakdown.** 6 patches applied (1 medium: the anti-drift table that could not detect the drift it advertised; 5 low: the wrong CPython constant in two new places plus two hard-coded environment boundaries, the log comment's overclaim, the `5`/`or {}` docstring, the under-asserted 4301-digit half, and the four untested parse-catch arrivals). 2 deferred (DW-212, a `RecursionError` that escapes `get_json(silent=True)` on every JSON route — medium and reproduced live; DW-213, the same wrong-constant citation in `_positive_int_string`, which this spec's Never list protects). 9 rejected, the largest being the claim that the column bound belongs in the service or schema rather than the route (the Never list forbids both, and every other column here validates at the route), that the spec's I/O matrix is missing two rows (it is inside the frozen intent contract, and both behaviors are entailed by rows it has), and a MariaDB DATE-range overflow that does not exist.

**Follow-up review recommendation.** `false`. Six fixes, all localized, all in comments, docstrings and test assertions; the executable surface of the change is byte-identical to what was reviewed last pass and is now pinned by more tests than before. The one finding of real consequence (DW-212) is deferred rather than patched, because it is pre-existing, app-wide, and needs a decision about the whole JSON surface.

**Verification.** `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -R -s tests` -> **3234 passed, 451 deselected** (3229 before this pass; +5 from the new parametrizations and the new string-path test). Every reviewer claim acted on was re-verified directly rather than taken on report: `sys.int_info.str_digits_check_threshold == 640` and `default_max_str_digits == 4300` measured on this interpreter; `int(json.loads('Infinity'))` -> `OverflowError`, `NaN` -> `ValueError`, `int({})` -> `TypeError`, a 4301-digit STRING -> `ValueError` all measured, then driven through a live app built like `tests/conftest.py` to confirm each answers 400 `invalid_field`/`quantity`; the `RecursionError` reproduced at depth 100000 (600 KB, under the 1 MiB cap) and shown absent at depth 20000; `api_scan`'s existing refusal `logger.warning` read at `app/main/routes.py:2760` before rejecting the log-flood finding; `docs/` searched for an API reference before rejecting the undocumented-breaking-change finding (there is none, and `app/api_client.py` posts with `json=`). Claims that did not survive verification were rejected, including the MariaDB DATE-range finding.

**Residual risks.** Unchanged from the previous pass and not narrowed by it: DW-87 (a non-string text value) and DW-88 (the ISO date grammar) are still open, so this endpoint still has inputs that reach a generic 500 — which is why Acceptance Criterion 1 is scoped to the I/O matrix rather than stated generally. The `quantity` bound remains invisible to the unit suite's backend (SQLite widens `INTEGER` silently), so every assertion is about what the route answers. Newly named: DW-212 means a body this route accepts for parsing can still 500 before any guard in it runs, and the two over-long-integer tests now depend on `sys.get_int_max_str_digits()` at runtime rather than on a literal — correct in any environment, but they assert nothing if a future one raises the cap enormously.
