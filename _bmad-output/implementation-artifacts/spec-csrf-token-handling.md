---
title: 'Redact secrets from audit logs and prove CSRF tokens are required'
type: 'bugfix'
created: '2026-07-26'
status: 'done'
baseline_revision: '40b5020ea67abe4e01a2ef7b060ad7f961c3b71f'
final_revision: 'c8c09e7bea5ec0d3d4ded75387c64044f65b826f'
review_loop_iteration: 0
followup_review_recommended: true
context: ['{project-root}/_bmad-output/project-context.md']
warnings: ['multiple-goals', 'oversized']
---

<intent-contract>

## Intent

**Problem:** Seven route handlers pass `request.form.to_dict()` straight into `log_audit_operation` (`app/main/routes.py:261, 670, 1207, 1628, 2293, 2492, 2814`), and the helper writes every dict payload through verbatim (`app/logging_config.py:288-304`), so each form POST's `csrf_token` is persisted into the audit log. Separately, both `TestConfig`s disable CSRF (`config.py:198`, `tests/test_config.py:18`) for unit *and* e2e runs, so deleting or misspelling a template's `csrf_token` hidden input — or losing server-side enforcement on a form endpoint — leaves the whole suite green while every real browser POST 400s.

**Approach:** Redact secret-ish field names inside the audit-logging helpers themselves, so every current and future caller is covered at one choke point rather than route by route. Then add unit coverage that (a) statically asserts every POST form template still carries a `csrf_token` hidden input and (b) behaviourally asserts, in a CSRF-*enabled* app, that each non-exempt POST endpoint refuses a tokenless request.

## Boundaries & Constraints

**Always:**
- Redaction happens in `app/logging_config.py`, applied to every dict payload of `log_audit_operation` (`form_data`, `item_before`, `item_after`, `changes`) and `log_audit_batch_operation` (`batch_data`, `results`).
- Match field names case-insensitively as substrings, and recurse into nested dicts and lists of dicts.
- Never mutate the caller's dict — build and log a redacted copy; the caller's `request.form.to_dict()` result must be unchanged after the call.
- Redacted values are replaced with a fixed marker string; the key itself stays present so the audit record still shows the field was submitted.
- The CSRF-enabled test app follows the existing precedent at `tests/unit/test_scan_routes.py:325-353`: a `TestConfig` subclass with `WTF_CSRF_ENABLED = True`, plus a control route proving protection is genuinely on before any assertion is trusted.
- The template scan derives its own list from `app/templates/**` at runtime, so a newly added POST form is covered without editing the test.

**Block If:**
- Redacting a field name would remove data the audit log demonstrably needs for reconstruction (e.g. a denylist substring collides with a real inventory/product field name).

**Never:**
- Do not change `WTF_CSRF_ENABLED` for the shared `client` fixture, `config.TestConfig`, `tests/test_config.TestConfig`, or the e2e server — the new coverage builds its own app.
- Do not add or remove `@csrf.exempt` on any route, and do not change any route's audit-logging call sites.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.
- No e2e tests, no new `meta[name=csrf-token]` tag, no fixing the unrelated dead `getCSRFToken()` readers in `app/static/js`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CSRF token in form data | `log_audit_operation(..., form_data={'ja_id': 'JA1', 'csrf_token': 'abc'})` | Logged `audit_data.form_data` = `{'ja_id': 'JA1', 'csrf_token': '[REDACTED]'}` | No error expected |
| Case / prefix variants | field names `CSRF_Token`, `X_CSRFToken`, `password`, `api_key`, `session_id` | All redacted | No error expected |
| Benign fields preserved | `{'ja_id', 'material', 'length', 'notes', 'request_key', 'photo_id'}` | Logged verbatim, unchanged | No error expected |
| Nested payload | `item_after={'meta': {'csrf_token': 'x'}, 'rows': [{'token': 'y'}]}` | Both nested values redacted, structure preserved | No error expected |
| Caller dict untouched | caller passes a dict, then reads it after logging | Caller's dict still holds the original token value | No error expected |
| Non-dict payload | `form_data` is `None`, empty, or a non-dict value | Existing behaviour unchanged (falsy dropped; non-dict passed through) | Must not raise |
| Tokenless POST, CSRF on | `POST` to each non-exempt form endpoint with no `csrf_token` | HTTP 400 | Rejection is the expected outcome |
| Template missing token | a POST form template without `name="csrf_token"` | Template-scan test fails naming the file | Rejection is the expected outcome |

</intent-contract>

## Code Map

- `app/logging_config.py` -- `log_audit_operation` (:255) and `log_audit_batch_operation` (:324); dict payloads assembled at :286-304 and :345-354; `JSONFormatter` (:73-80) emits `audit_data` as JSON. Redaction goes here.
- `app/main/routes.py` -- 7 callers passing raw form dicts (:261, :670, :1207, :1628, :2293, :2492, :2814). Read-only; not modified.
- `tests/unit/test_scan_routes.py:325-353` -- existing `CsrfEnabledConfig` + control-route precedent to copy.
- `tests/unit/test_request_limits.py:1537-1575` -- second precedent (`_csrf_app` helper).
- `tests/unit/test_audit_json_fix.py` -- asserts `form_data` round-trips through `JSONFormatter`; its fixtures use only benign field names, so it must stay green untouched.
- `app/templates/**` -- 10 native POST forms (`inventory/add|edit|move|shorten.html`, `product/add|edit|purchase_add|category_rename|detail.html`, `admin/add_material.html`), all currently carrying a `csrf_token` hidden input.
- `app/__init__.py:13,45-47` -- `csrf = CSRFProtect()` and init order; `app/main/routes.py` holds 16 `@csrf.exempt` JSON routes that must stay excluded from the tokenless-POST test.

## Tasks & Acceptance

**Execution:**
- [x] `app/logging_config.py` -- add a module-level denylist of case-insensitive name substrings (`csrf`, `token`, `password`, `passwd`, `secret`, `api_key`, `apikey`, `authorization`, `credential`, `private_key`, `session`) plus a recursive `_redact_sensitive(value)` helper returning a redacted copy; apply it to every dict payload in `log_audit_operation` and `log_audit_batch_operation` -- one choke point covers all 40+ existing call sites and any future one. Deliberately excludes a bare `key` substring, which would swallow the legitimate `request_key` field (`app/database.py:921`).
- [x] `tests/unit/test_audit_redaction.py` -- new file covering the redaction rows of the I/O matrix: token redaction in `form_data`, case/prefix variants, benign fields preserved, nested dict/list recursion, caller dict not mutated, `None`/empty/non-dict inputs, and `log_audit_batch_operation` payloads. Assert against JSON-formatted output using the `JSONFormatter` + `StringIO` handler pattern from `tests/unit/test_audit_json_fix.py:20-29` with a dedicated `logger_name`. Include one route-level test that POSTs a form (with a `csrf_token` field) through the `client` fixture to a route that audit-logs `request.form.to_dict()`, capturing the `inventory` logger, and asserts the token is redacted in the emitted record -- proving the choke point covers real callers, not just direct helper calls.
- [x] `tests/unit/test_csrf_protection.py` -- new file with (1) a template scan that walks `app/templates/**/*.html`, finds every `<form>` whose method is POST, and asserts each contains a `csrf_token` hidden input rendered from `csrf_token()`; and (2) a CSRF-enabled app fixture (subclass of `config.TestConfig` with `WTF_CSRF_ENABLED = True`, storage injected from `test_storage`) plus a control route, parametrized over the non-exempt POST endpoints so each is asserted to 400 without a token.

**Acceptance Criteria:**
- Given a real `POST /products/add` submission through the app, when the route audit-logs its input, then the emitted JSON `audit_data.form_data` contains a `csrf_token` key whose value is the redaction marker and no other field's value changed.
- Given the CSRF-enabled test app, when the control route is POSTed without a token, then it returns 400 — and if it does not, the endpoint assertions fail loudly rather than passing vacuously.
- Given every non-exempt POST endpoint backing a form template, when POSTed without a `csrf_token`, then the response status is 400.
- Given a form template whose `csrf_token` hidden input is deleted or misspelled, when the unit suite runs, then the template-scan test fails and names the offending template.
- Given the pre-existing suite, when `nox -s tests` runs, then it is green with no edits to `tests/unit/test_audit_json_fix.py` or `tests/unit/test_audit_logging.py`.

## Spec Change Log

## Review Triage Log

### 2026-07-26 — Review pass 1
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 0, medium 2, low 10)
- defer: 1: (high 0, medium 0, low 1)
- reject: 14: (high 0, medium 3, low 11)
- addressed_findings:
  - `[medium]` `[patch]` `_redact_sensitive` failed **open** past `MAX_REDACTION_DEPTH`, returning the raw subtree — a deeply nested `csrf_token` reached the log intact (reproduced). Now returns `REDACTED_VALUE`; two tests pin fail-closed at depth and no truncation of benign data within the walk.
  - `[medium]` `[patch]` Every CSRF assertion was a rejection, so an app that refused *all* POSTs (broken `csrf_token()`, bad `SECRET_KEY`, over-broad hook) passed the whole file green while no real form worked. Added a valid-token control on the control route plus a per-endpoint "a valid token gets through the gate" case.
  - `[low]` `[patch]` `error_details` was the one payload skipping the choke point while the new comment claimed totality; now routed through `_redact_sensitive` (no-op for the `str` every real caller passes) with both cases tested.
  - `[low]` `[patch]` The spec's "Block If" (a denylist substring colliding with a real field) was unguarded at runtime; added `TestDenylistDoesNotSwallowRealFields`, checking the denylist against actual `app/database.py` columns and actual template field names rather than against a constant.
  - `[low]` `[patch]` Forged tokens were never tried — enforcement accepting any non-empty value satisfied every tokenless case. Added a per-endpoint forged-token case.
  - `[low]` `[patch]` The scan tripwire counted templates, not forms, so a second POST form in an already-listed template got zero coverage and failed nothing; parity is now per-form.
  - `[low]` `[patch]` Scanner false passes: an unclosed `<form>` read to EOF and a nested one borrowed the inner form's token. Both now fail loudly, with tests.
  - `[low]` `[patch]` A Jinja-computed `method="{{ … }}"` was silently classified GET and dropped from coverage; now treated as POST. (First attempt over-matched `product/search.html`; corrected to inspect the method *value*.)
  - `[low]` `[patch]` The scan only walked `*.html`, so a form moved into a `.jinja`/`.j2` partial would escape; now walks a suffix set.
  - `[low]` `[patch]` Assertions matched Flask-WTF's English prose (`The CSRF token is missing.`), which a dependency bump would break. Replaced with a `CSRFError` handler returning a sentinel — decoupled from wording *and* from any future app-level 400 handler.
  - `[low]` `[patch]` The redaction tests left `propagate` on, coupling "was the secret redacted?" to whatever another test left on the root logger; set `propagate = False`.
  - `[low]` `[patch]` `admin.update_material_status` and `admin.validate_material` are CSRF-protected POSTs driven by `fetch`, invisible to a form scan and uncovered; added to the tokenless-POST coverage.

### 2026-07-26 — Review pass 2
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 2, low 6)
- defer: 3: (high 0, medium 0, low 3)
- reject: 10: (high 0, medium 0, low 10)
- addressed_findings:
  - `[medium]` `[patch]` `_redact_sensitive` failed **closed** on depth but **open** on type: it walked only `dict`/`list`/`tuple`, so a `collections.abc.Mapping` (SQLAlchemy `RowMapping`), a namedtuple, or a non-`str` key (`b'csrf_token'`) carried its secret past the choke point to `JSONFormatter`, which `str()`s it into the record via `default=str`. Reproduced all three. Now walks any `Mapping`, redacts namedtuples by field name via `_asdict`, and coerces non-`str` keys before matching. The docstring also now states the two boundaries it deliberately does *not* cover (value-channel secrets; arbitrary objects, which are left as scalars rather than reflected over) instead of implying totality.
  - `[medium]` `[patch]` The endpoint lists were hand-maintained with no parity guard — the mirror of the template scan's own tripwire. A new `fetch`-driven POST endpoint, or a form whose `<form>` tag carries no `method` (`export-form`, `advanced-search-form`: both submitted by JS `fetch(..., method: 'POST')` and invisible to the template scan), would get zero coverage silently. Added `TestEveryProtectedEndpointIsCovered`, deriving the enforcing set from `app.url_map` minus `csrf._exempt_views` and asserting it equals the covered set, plus a pinned `EXEMPT_VIEWS` so an added `@csrf.exempt` — the one way to leave the derived set quietly — has to be a deliberate edit.
  - `[low]` `[patch]` `test_form_endpoint_lets_a_valid_token_through_the_gate` asserted only `!= CSRF_SENTINEL`, which an unhandled exception satisfies as well as an open gate. Now also rejects a 500.
  - `[low]` `[patch]` Each of the ~35 `create_app` calls in the CSRF file left another handler on the shared `inventory`/`performance`/`api_access`/`google_sheets`/`mariadb_catalog_service` loggers (`setup_logging` never clears; measured 1, 2, 3, 4…), so any later test reading log output — including this story's own redaction tests — saw duplicated records. Replaced with a `csrf_app` fixture that restores the handler lists; verified the file now leaves the `inventory` logger at 0 handlers.
  - `[low]` `[patch]` A tuple payload came back as a list, contradicting the docstring's "redacted COPY". Tuple-ness is now preserved, with a test.
  - `[low]` `[patch]` The depth tests sampled `MAX-2` and `MAX+2` only, so an off-by-one in either direction passed both. Added a parametrized case pinning both sides of the cliff at exactly `MAX_REDACTION_DEPTH`.
  - `[low]` `[patch]` `_logged()` raised an opaque `JSONDecodeError` if a second record ever reached the buffer; now asserts a single record and reports what it saw.
  - `[low]` `[patch]` The denylist collision scan matched form field names with `\w+`, skipping hyphenated names — blind to exactly the fields it exists to protect. Widened.

### 2026-07-26 — Review pass 3
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 0, medium 3, low 9)
- defer: 1: (high 0, medium 0, low 1)
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[medium]` `[patch]` The walk was still fail-**open** on the *sequence* side: pass 2 fixed mapping recognition to the `Mapping` ABC but left `isinstance(value, (list, tuple))` beside it, so a `deque`, a `dict_values` view, a `frozenset` — any non-`list`/`tuple` container — was handed to `JSONFormatter` and `str()`-ed into the record with its nested secret intact. Reproduced (`{"rows": "deque([{'csrf_token': 'LEAK'}])"}`). Both sides now recognise containers by ABC; a one-shot `Iterator` fails closed rather than being consumed (which would mutate the caller) or passed through (which would bypass).
  - `[medium]` `[patch]` Redacting the value while re-emitting a non-`str` **key** made the payload unserializable: `json.dumps`'s `default=` applies to values only, so a `b'csrf_token'` key raised `TypeError` out of `JSONFormatter`, logging swallowed it, and the *entire audit record* was dropped — trading a leak for a hole in the audit trail. `test_non_string_keys_do_not_bypass_the_denylist` asserted on the in-memory dict and never serialized it, pinning the wrong half. Keys are now coerced (`bytes` decoded), and a test round-trips through `json.dumps`.
  - `[medium]` `[patch]` `_redact_sensitive` could raise into its caller: it walks caller-supplied objects, so a payload whose `items()` or iteration throws propagated out of a *logging* call and failed the request it only meant to describe (reproduced). Audit call sites now go through a fail-closed `_redact_payload` wrapper.
  - `[low]` `[patch]` The endpoint parity guard derived its set from POST rules only, while `WTF_CSRF_METHODS` is `{POST, PUT, PATCH, DELETE}`. A protected PATCH/PUT/DELETE route would be invisible to both the parity check and the template scan. Now derived from `WTF_CSRF_METHODS`; mutation-tested by adding a protected PATCH route (fails now, passed under the old derivation).
  - `[low]` `[patch]` `test_form_endpoint_rejects_a_forged_token` never reached token comparison — with no CSRF session, Flask-WTF short-circuits on "session token is missing", so the forgery was rejected for the same reason the tokenless case already covered and the signature check was tested by nothing. The session is now seeded, and each case asserts its rejection reason differs from a sessionless client's — prose-free, via an `X-CSRF-Reason` header off the sentinel handler.
  - `[low]` `[patch]` The `csrf_app` fixture restored handler lists but not levels, and ignored the root and `app` loggers, which `setup_logging` also rewrites (root handlers *replaced*, level 30→20). Measured: the file used to leave root at INFO minus a handler and all five specialized loggers at INFO. Now restores handlers+level across all seven; a probe test after the file sees state byte-identical to a clean baseline.
  - `[low]` `[patch]` The `X-CSRFToken` header channel — the mechanism both `fetch`-driven admin endpoints actually use — had rejection-only coverage, so a `WTF_CSRF_HEADERS` break would leave the file green while every admin JS POST 400s. Added valid-header and forged-header cases.
  - `[low]` `[patch]` `_post_form_bodies` searched for `</form>` case-sensitively while `_FORM_TAG` and the nested-form check were case-insensitive: a `</FORM>` would have tripped the "unclosed form" assertion. Three casing policies in one helper, now one.
  - `[low]` `[patch]` `test_a_multidict_is_walked`'s docstring claimed `app/admin/routes.py` hands the audit helpers `request.form`; that module makes no audit calls at all (its `form_data=request.form` at :108 is a `render_template` kwarg). Rewritten to state the real justification.
  - `[low]` `[patch]` The `!= 500` guard's comment described behaviour the app does not have — under `TESTING` an unhandled exception propagates out of `client.post` rather than becoming a 500. Assertion kept (it still catches a crash *converted* to a 500); comment corrected.
  - `[low]` `[patch]` Nothing pinned that CSRF stays enabled outside the test configs — every app here forces `WTF_CSRF_ENABLED = True` in its own subclass, so adding `WTF_CSRF_ENABLED = False` to the base `Config` would disable it in production and fail nothing. Added `TestCsrfStaysEnabledOutsideTheTestConfigs` over `config.Config` and every non-test subclass.
  - `[low]` `[patch]` The choke-point comment claimed "no caller can leak … any other secret-ish field" unqualified while the docstring below correctly enumerated the boundaries. Tightened to name the key-based limit and defer to the docstring.

## Design Notes

Denylist substrings were checked against real field names before selection: `grep` over `app/templates` shows `csrf_token` is the only form field matching any secret-ish pattern, and the only `app/database.py` column that would collide under a looser list is `request_key` — hence `api_key`/`private_key` rather than `key`.

Shape of the helper:

```python
SENSITIVE_FIELD_SUBSTRINGS = ('csrf', 'token', 'password', ...)
REDACTED_VALUE = '[REDACTED]'

def _redact_sensitive(value, _depth=0):
    if isinstance(value, (str, bytes, bytearray)):
        return value               # sequences, but must not be walked
    # Containers are recognised by ABC in BOTH directions -- an unrecognised
    # container is a silent bypass, since JSONFormatter's `default=str` will
    # stringify it into the record with its secret intact.
    is_mapping = isinstance(value, Mapping)
    if not (is_mapping or isinstance(value, Iterable)):
        return value
    if _depth > MAX_REDACTION_DEPTH:
        return REDACTED_VALUE      # depth guard fails CLOSED, not open
    if is_mapping:
        return {_serializable_key(k): (REDACTED_VALUE if _is_sensitive_name(k)
                                       else _redact_sensitive(v, _depth + 1))
                for k, v in value.items()}
    if isinstance(value, Iterator):
        return REDACTED_VALUE      # consuming it would mutate the caller
    return [_redact_sensitive(v, _depth + 1) for v in value]
```

Three fail-closed properties hold together, and each was a separate leak when it
did not: the **depth** guard drops a too-deep subtree instead of returning it
raw; **container recognition** is by ABC, so a `deque`/`RowMapping`/`frozenset`
is walked rather than stringified; and **keys** are coerced to something
`json.dumps` accepts, because an unserializable key costs the whole record — a
worse outcome than the leak. `_redact_payload` wraps the walk so a payload that
raises can never fail the request that was only trying to log it.

Why a template scan *and* tokenless POSTs: the POST tests prove the server enforces CSRF, but they pass even if a template's hidden input is deleted; the scan proves the input exists, but not that it is enforced. DW-44's stated failure mode needs both halves.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: full unit suite green, including the two new test files.
- `venv/bin/python -m pytest tests/unit/test_audit_redaction.py tests/unit/test_csrf_protection.py -q` -- for fast iteration only; the authoritative run is the `nox` session above.

## Auto Run Result

Status: done

**Summary.** Follow-up review pass (pass 3) over the already-committed `csrf-token-handling` bundle (DW-43, DW-44). No intent gap and no spec defect — the shipped design held for the third time. Twelve patches were applied. The three that matter are all the *same* fail-open shape the previous two passes kept finding one instance of at a time, finally closed as a class: pass 1 fixed the depth guard, pass 2 fixed mapping recognition, and this pass found that the sequence side beside it was still `isinstance(value, (list, tuple))` — so a `deque`, a `dict_values` view or a `frozenset` walked straight past the choke point to be `str()`-ed into the record with its secret intact. Alongside it, two failure modes worse than the leak they guard: a non-`str` mapping key made the redacted payload unserializable, so `JSONFormatter` raised and the **entire audit record** was silently dropped; and the walk could raise out of a logging call and fail the request it was only describing.

**Files changed (this pass):**
- `app/logging_config.py` — container recognition is now by ABC on both sides (`Mapping` / `Iterable`), one-shot iterators fail closed rather than being consumed or bypassed, mapping keys are coerced to a JSON-serializable form via a new `_serializable_key`, and all eight audit call sites route through a new fail-closed `_redact_payload` wrapper. The choke-point comment no longer overclaims.
- `tests/unit/test_csrf_protection.py` — parity derived from `WTF_CSRF_METHODS` instead of a hardcoded `POST`; forged-token cases now seed a CSRF session so they reach the signature check, and assert their rejection reason differs from a sessionless client's via an `X-CSRF-Reason` header (prose-free); new `X-CSRFToken` header valid/forged cases; new `TestCsrfStaysEnabledOutsideTheTestConfigs`; `csrf_app` restores levels and the root/`app` loggers; case-insensitive `</form>` search.
- `tests/unit/test_audit_redaction.py` — new container-type cases (`deque`, `dict_values`, `frozenset`, one-shot iterator), a JSON-serializability assertion over mixed key types, and a fail-closed-on-raise case. 54 tests (was 48); `test_csrf_protection.py` is now 49 (was 43).

**Review findings breakdown:** 12 patched (3 medium, 9 low), 1 deferred, 7 rejected. Notable rejections: the claim that `from config import TestConfig` is "the TestConfig nobody uses" — it is what the spec names and what *both* cited precedents (`test_scan_routes.py:336`, `test_request_limits.py:1546`) use, and it does set `TESTING = True`; `csrf._exempt_views` being a private attribute (accepted in passes 1–2, and already used by `test_scan_routes.py`); `_exempt_blueprints` not being pinned (a blueprint exemption makes the tokenless cases fail *loudly*, so it cannot slip through); the depth guard walking nine levels rather than eight (wording, and the cliff is pinned either way); `_CSRF_INPUT`'s brittleness to `{{- csrf_token() -}}` or a macro (recorded as a residual risk in pass 1, fails loudly); a `>` inside a form-tag attribute (no occurrence, and the per-form parity count catches a form that disappears); and the committed `SECRET_KEY` default (already on the ledger as DW-98).

**Deferred — appended to the ledger as DW-100 (new entry only):**
- DW-100: the denylist collision guard scans DB columns and static template fields, but the payloads the walk actually receives are hand-built dicts (`_item_to_audit_dict`, `changes`, `batch_results`). Verified zero collisions today, so it is a coverage gap rather than a live defect.

**Verification:**
- `PATH=… venv/bin/nox -s tests` — **2571 passed**, 367 deselected, 18 pre-existing warnings, 26.7s. Was 2559 before this pass; +12. `tests/unit/test_audit_json_fix.py` and `tests/unit/test_audit_logging.py` remain untouched and green, and no template or route file was modified.
- Reproduced all three medium findings before fixing: `_redact_sensitive({'rows': deque([{'csrf_token': 'LEAK'}])})` serialized to `{"rows": "deque([{'csrf_token': 'LEAK'}])"}`; `json.dumps({b'csrf_token': '[REDACTED]'}, default=str)` raised `TypeError: keys must be str…`; a payload whose `items()` raises propagated a `RuntimeError` out of the logging call.
- Mutation-tested every new guard, restoring each afterwards: reverting `Iterable` to `(list, tuple)` fails the three container cases; reverting key coercion fails the serializability case; removing the `_redact_payload` try/except fails the raise case; letting a one-shot iterator through fails the iterator case; adding a CSRF-protected `PATCH` route fails the parity check under the new derivation and **passes** under the old POST-only one (the gap being closed); breaking `WTF_CSRF_HEADERS` fails the header cases; setting `WTF_CSRF_ENABLED = False` on the base `Config` fails both new config guards; removing the session seeding fails all 12 forged-token cases.
- The first version of the forged-token guard compared against the wrong baseline and survived its own mutation (removing the seeding still passed). It was rewritten to compare against a sessionless client and re-mutated before being accepted.
- Measured the fixture's isolation with a probe test appended after the file: with the patched fixture the logging state is byte-identical to a clean baseline (`root 4 handlers/level 30`, all others `0/0`); with the pre-patch handlers-only version, root lost a handler and dropped to level 20, `app` kept 2 handlers, and all five specialized loggers were left at INFO.

**Residual risks:**
- Unchanged from earlier passes: the template scan is regex-based over template *source* (a refactor into macros, includes, or `form.hidden_tag()` would report a false offender), `EXEMPT_VIEWS` is a pinned snapshot needing a manual edit when an exemption legitimately changes, and the e2e session still runs with CSRF disabled by design.
- Redaction remains key-based (DW-99) and still treats an arbitrary non-iterable object as a scalar — deliberate, since reflecting over `__dict__` on a logging path risks pulling in ORM instrumentation state.
- `_redact_payload` collapses the *whole* payload to the marker if any node raises mid-walk. That is the fail-closed choice, but it means one pathological sub-object costs the rest of the record's detail.
- Widening the walk to any `Iterable` means a future caller passing an exotic lazy container gets materialized into a list on the logging path; every payload this app builds is already a plain dict or list.


