---
title: 'Logging redaction completeness: sibling helpers and a guard that sees the real payloads'
type: 'bugfix'
created: '2026-07-28'
status: 'done'
baseline_revision: '045f211a176f3309da1f47fddba58aac79013d18'
final_revision: 'ea403d962a085d3c34d541c71153e28a98cc0769'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** DW-97 — `_redact_sensitive` guards every payload of `log_audit_operation` / `log_audit_batch_operation`, but the sibling helpers `log_operation(details=…)` (`app/logging_config.py:342`) and `log_performance(context=…)` (`:403`) merge caller dicts straight into the log record unfiltered; that asymmetry is the exact shape that produced DW-43. DW-100 — the guard enforcing the source spec's "Block If" (`tests/unit/test_audit_redaction.py::TestDenylistDoesNotSwallowRealFields`) scans `app/database.py` column names and static template `name=` attributes, neither of which is what the redaction walk receives: the real payloads are `_item_to_audit_dict`, ORM `to_dict()` snapshots, the `changes` maps and `batch_results`.

**Approach:** Route both sibling helpers through the one redaction helper, via a small merge wrapper that keeps `_redact_payload`'s fail-closed return (a `str`) from breaking a `dict.update`. Widen the collision guard with three prongs that enumerate the payload key sets the walk actually sees: exercise `_item_to_audit_dict`, exercise the ORM `to_dict()` builders, and AST-scan the dict literals reaching the audit helpers' payload arguments in `app/**/*.py`.

## Boundaries & Constraints

**Always:**
- Redaction stays key-based and stays in `app/logging_config.py`; the sibling helpers use the same `SENSITIVE_FIELD_SUBSTRINGS` denylist and `REDACTED_VALUE`, not a second one.
- A logging helper must never raise into its caller. Any new code path preserves that.
- The caller's dict is never mutated (`_redact_sensitive` returns a copy; keep it that way).
- The AST scan must fail loudly when it stops recognising the code it scans (rot detection), rather than silently collecting nothing.
- Every payload argument the AST scan cannot resolve to dict literals must be shown to trace to a builder another prong covers, or the scan fails.

**Block If:**
- A prong finds a real audit key that the current denylist would redact. That is the source spec's "Block If" firing for real: HALT, do not weaken the denylist unattended.

**Never:**
- No value-based redaction (a secret under a benign key) — that is DW-99, out of scope.
- Do not change `SENSITIVE_FIELD_SUBSTRINGS`, `MAX_REDACTION_DEPTH`, `REDACTED_VALUE`, or `_redact_sensitive`'s walk semantics.
- Do not touch `log_api_access` (no caller dict merge), and do not change any route's audit-logging call sites.
- Do not "fix" the pre-existing shadowing of `operation` / `duration` / `item_id` by caller keys — not this bundle.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Sibling helper, secret key | `log_operation('add_item', details={'csrf_token': 'LEAK', 'ja_id': 'JA1'})` | Emitted record has `csrf_token == REDACTED_VALUE`, `ja_id == 'JA1'` | No error expected |
| Sibling helper, nested secret | `log_performance('search', 0.0, 1.0, context={'req': {'password': 'p'}})` | `record.req == {'password': REDACTED_VALUE}` | No error expected |
| Benign payload untouched | `details={'item_count': 3, 'request_key': 'abc'}` | Both values pass through verbatim | No error expected |
| Payload that fails the walk | `details` is a mapping whose `items()` raises | Record still emitted; the payload appears as `details = REDACTED_VALUE` (nested under the parameter name) | Fail closed, never propagate |
| Non-mapping payload | `context` is a list / an object | Record still emitted; value nested under `context`, `dict.update` never sees a non-mapping | Fail closed, never propagate |
| Falsy payload | `details=None` / `details={}` | Record unchanged from today (no extra key added) | No error expected |
| Guard: colliding audit key | A payload builder gains a key like `access_token` | `TestDenylistDoesNotSwallowRealFields` fails naming the key | Test failure |
| Guard: scanner rot | Audit call sites renamed / a payload arg built by an unrecognised builder | Scan asserts rather than silently returning an empty/partial key set | Test failure |

</intent-contract>

## Code Map

- `app/logging_config.py` -- `_redact_payload` (:74), `_redact_sensitive` (:88), `log_operation` (:319), `log_performance` (:383), and the choke-point comment at :446-450 that currently states the siblings are *not* redacted.
- `tests/unit/test_audit_redaction.py` -- `TestDenylistDoesNotSwallowRealFields` (:431) is the guard to widen; `setup_method` (:46-58) is the record-capture pattern to reuse.
- `app/main/routes.py` -- `_item_to_audit_dict` (:68) is the primary hand-built audit payload; `_detect_item_changes` (:96) derives `changes` keys from it.
- `app/database.py` -- `InventoryItem.to_dict()`, `Product.to_dict()`, `Purchase.to_dict()`, `Attachment.to_dict()`, `ProductIdentifier.to_dict()` are the `item_before`/`item_after` snapshots. All five work on a bare, unsaved instance.
- `app/mariadb_inventory_service.py`, `app/mariadb_catalog_service.py` -- the other 32 audit call sites; hand-built `changes` / `results` dict literals live here.

## Tasks & Acceptance

**Execution:**
- [x] `app/logging_config.py` -- add a module-private merge wrapper (e.g. `_redact_merge(payload, fallback_key)`) that returns `_redact_payload(payload)` when it is a `Mapping` and `{fallback_key: <result>}` otherwise -- `_redact_payload` fails closed by returning a `str`, and `dict.update` on a `str` would raise out of the logging call the fail-closed path exists to protect.
- [x] `app/logging_config.py` -- route `log_operation`'s `details` and `log_performance`'s `context` through it, replacing the bare `extra_data.update(...)` at :342 and :403. Keep `log_performance`'s `item_count` message lookup reading the caller's original `context` (it is not a secret and the message is not the audit trail).
- [x] `app/logging_config.py` -- update the choke-point comment at :446-450 and `_redact_payload`'s docstring: all four helpers now go through the choke point, so the parenthetical claiming the siblings are unredacted is false. State the remaining difference: the siblings merge *flat* into the record, the audit helpers nest under `audit_data`.
- [x] `tests/unit/test_audit_redaction.py` -- add a class covering the sibling helpers against the I/O Matrix rows. Assert on the emitted `logging.LogRecord` attributes, not on `JSONFormatter` output: the formatter only serialises a fixed attribute allowlist, so a flat-merged `csrf_token` never reaches the JSON today. Extend the module docstring to say the file now pins all four helpers.
- [x] `tests/unit/test_audit_redaction.py` -- extend `TestDenylistDoesNotSwallowRealFields` with the three prongs (below). Each prong asserts its own rot sentinels before asserting no key is sensitive.
- [x] `tests/unit/test_audit_redaction.py` -- close DW-100's narrower gap: the template field scan captures Jinja-computed `name=` attributes literally (`app/templates/product/search.html:30` yields `{{ name }}`), so a dynamically named field is invisible by construction. Collect those separately, assert the set matches an explicitly reviewed literal, and check the one real source (`_scan_prefill_args` / `_ecia_prefill` in `app/main/routes.py`) key set against the denylist.

**Acceptance Criteria:**
- Given a caller-supplied dict containing a denylisted field name, when it is passed as `log_operation(details=…)` or `log_performance(context=…)`, then the emitted record carries `REDACTED_VALUE` for that field and the original secret appears nowhere in the record.
- Given `app/logging_config.py`, when the four public log helpers that accept a caller dict are inspected, then none merges a caller dict into a log record without passing it through `_redact_payload` first.
- Given a hypothetical rename of any audit payload key to a name containing a denylist substring, when `nox -s tests` runs, then `TestDenylistDoesNotSwallowRealFields` fails and names the offending key.
- Given the audit call sites are refactored so a payload argument is built by a builder the scan does not recognise, when the scan runs, then it fails rather than reporting success on a partial key set.
- Given `nox -s tests`, when it runs, then it is green with no pre-existing test modified beyond the additive changes above.

## Spec Change Log

## Review Triage Log

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 0, medium 3, low 8)
- defer: 1: (high 0, medium 1, low 0)
- reject: 8: (high 0, medium 0, low 8)
- addressed_findings:
  - `[medium]` `[patch]` The flat merge could raise `KeyError` out of the logging call: `makeRecord` rejects any `extra` key colliding with a `LogRecord` attribute (`name`, `module`, `filename`, `args`…), and `_serializable_key`'s coercion newly turned a harmless `b'name'` into a colliding `'name'`. `_redact_merge` now nests reserved keys under `fallback_key` — lossless, never raises. Reserved set derived from a probe `LogRecord`, not hardcoded.
  - `[medium]` `[patch]` A name bound to a dict literal masked its other bindings, so `_detect_item_changes`' incrementally-built `changes` payload was collected by nothing AND reported in nothing — contradicting the "never quietly dropped" promise. Subscript assignments (`changes[k] = {…}`) are now indexed, and a `Name` is always handed to `_classify_builder`. Surfaced `_detect_item_changes` and `_normalize_json_item_payload`; each recognised only with prong coverage added (`_JSON_ITEM_FIELDS` now checked and exercised). Keys 58 → 60.
  - `[medium]` `[patch]` `_classify_builder` waved through ANY `.to_dict()` while prong 2 checked a hardcoded five models. Prong 2 now discovers every mapped class in `app/database.py` defining `to_dict` (9 found), with a rot assertion that the known five are among them.
  - `[low]` `[patch]` `log_audit_batch_operation`'s `'successful_count' in results` carried the exact `TypeError` hazard just guarded in `log_performance` — the same sibling asymmetry this bundle exists to remove. Both now share a `_message_field` helper.
  - `[low]` `[patch]` The `isinstance(context, Mapping)` guard still let a Mapping with an exploding `__contains__`/`__getitem__` escape; `_message_field` wraps the lookup.
  - `[low]` `[patch]` `_redact_merge`'s docstring called nesting "the whole point of failing closed", but an arbitrary object is handed back untouched — nesting keeps the record emittable, it is not a redaction guarantee. Wording corrected.
  - `[low]` `[patch]` `_ModuleIndex.enclosing` was inverted: `ast.walk` is breadth-first, so `setdefault` kept the OUTERMOST function for every node in the 26 nested functions under `app/`, making `_parameter_names` and `_calls_to` consult the wrong function. Now innermost-wins.
  - `[low]` `[patch]` `_literal_dict_keys`' hard assert was armed against every dict literal under `app/`; an unrelated `{**base, 'x': 1}` would abort the class with a misleading message. Index made lenient; the strict reader kept only where a literal directly reaches a payload argument.
  - `[low]` `[patch]` A `**kwargs`/`*args` audit call site was counted (propping up the floor) while contributing no keys and failing nothing. Now flagged `unaccounted`.
  - `[low]` `[patch]` `test_no_helper_merges_a_caller_dict_without_redacting_it` failed on a safe `extra_data.update({'literal': 1})`; a dict literal is now accepted, since it carries no caller data.
  - `[low]` `[patch]` Stale comment: `AUDIT_HELPERS` was described as "the two helpers whose payloads reach `_redact_sensitive`" when all four now do; reworded to say what it is — the two the AST scan scans for.
  - `[medium]` `[defer]` DW-226: `app/error_handlers.py:81` merges `WorkshopInventoryError.details` into `extra` unredacted, and `error_details` IS in `JSONFormatter`'s allowlist — the one LIVE instance of the pattern this bundle closed in two helpers that have no callers. Out of the spec's scope (`app/logging_config.py` + its tests) and entangled with the response body echoing the same dict.

### 2026-07-28 — Follow-up review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 0, medium 4, low 6)
- defer: 0
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[medium]` `[patch]` The message leaked what the payload had just redacted. `_message_field` read the caller's ORIGINAL dict (per the spec's task line) and the value was interpolated into `message` — the one field `JSONFormatter` emits unconditionally, while `details`/`context` are not in its allowlist at all. `log_audit_batch_operation(results={'successful_count': {'csrf_token': 'LEAK'}})` printed the token verbatim beside the redacted copy of the same dict. Only a scalar reaches the message now; the payload still carries the rest, redacted. Still reads the original dict, so the task line's intent holds.
  - `[medium]` `[patch]` `_RESERVED_RECORD_ATTRS` was derived from a probe `LogRecord`, which is blind to the names this module stamps on AFTERWARDS. A flat-merged `details={'url': …}` satisfied `JSONFormatter`'s `hasattr(record, 'url')` sentinel without the four siblings `AuditLogFilter` sets alongside it, so `format` raised `AttributeError` on `record.method` and `logging` DROPPED THE WHOLE RECORD — worse than the `KeyError` the probe set exists to prevent, because nothing announces it. Also: a caller `audit_data` forged an audit block from a helper that writes no audit trail, and a caller `user_id` was silently overwritten by the filter, contradicting the "lossless" docstring. New `_MODULE_RECORD_ATTRS` covers the filter's five and the formatter's error/audit blocks, pinned against the source by `test_the_module_record_attrs_match_what_the_module_uses`. `operation`/`duration`/`item_id` deliberately excluded — the spec's "Never".
  - `[medium]` `[patch]` Prong 3's strictness depended on whether the author used a temporary variable. `_literal_dict_keys`' loud assert only fired for a literal passed INLINE; the same `{**request_form, 'ja_id': …}` bound to a name first went down the lenient `_visible_dict_keys` path and the scan reported full success on a payload half of which it had never seen — the exact "collected an empty key set and called it success" failure it exists to prevent. `_ModuleIndex` now records `opaque_bindings` and `_classify_builder` fails on them, checked before and regardless of any other binding.
  - `[medium]` `[patch]` `_classify_builder` waved through ANY `.to_dict()` on the strength of prong 2, which only parametrizes `Base` subclasses in `app/database.py`. `to_dict` is not an ORM-only name — `app/models.py`, `app/export_schemas.py` and `SearchFilter.to_dict()` define their own, and `SearchFilter`'s keys are built dynamically (`f'min_{field}'`), bounded by no prong at all. Receivers are now pinned to `REVIEWED_TO_DICT_RECEIVERS` (7 today, each naming its prong), checked for staleness as well as growth.
  - `[low]` `[patch]` `_message_field` guarded the lookup but not the interpolation: the f-string ran `__format__`/`__str__` — caller code — outside the try, so a value with an exploding `__str__` still propagated out of a logging call, which is precisely the invariant the helper was added to establish. The formatting moved inside the guard.
  - `[low]` `[patch]` `if details:` / `if context:` / `if form_data:` / `if results:` run the caller's `__bool__`/`__len__` in FRONT of every guard — the first caller code these helpers execute and the last unguarded line left. All four helpers raised on a payload whose `__len__` raises. New `_has_payload` closes the gate; an unanswerable truth test reads as "there is something here", so the payload goes through the fail-closed walk.
  - `[low]` `[patch]` The structural "no unredacted merge" guard matched the identifier `extra_data` literally, so a helper naming its record dict `extra`/`payload`/`log_data` was invisible to it. Matched on the shape (`<name>.update(…)`) now.
  - `[low]` `[patch]` `test_no_name_logging_reserves_can_raise_out_of_the_helper` compared two byte-identical derivations, so a wrong derivation would move in lockstep with the test and stay green. Each name is now first proved rejected by calling `makeRecord` — `logging` is the only independent authority on what it refuses.
  - `[low]` `[patch]` `_redact_merge`'s docstring called the merge "lossless" without noting that `record.<fallback_key>` is the caller's own value when nothing needed nesting and a dict when something did. Documented; the losslessness itself is now true, given the widened reserved set.
  - `[low]` `[patch]` Design Notes said "72 call sites and 56 distinct literal keys" while the test asserts 60 — stale since the previous pass's `58 → 60`. Corrected, and the `.to_dict()` recognition rule restated to match what the scan now does.

### 2026-07-28 — Second follow-up review pass
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 4, low 4)
- defer: 2: (high 0, medium 1, low 1)
- reject: 11: (high 0, medium 0, low 11)
- addressed_findings:
  - `[medium]` `[patch]` Prong 3 read only the TOP-LEVEL keys of a payload literal while the redaction walk recurses, so `changes={'location': {'session_id': 1}}` contributed `location` and the collision one level down was checked by nothing — and a `.to_dict()` nested in a payload literal bypassed `REVIEWED_TO_DICT_RECEIVERS` entirely (`receivers` came back empty). `_nested_dict_literals` / `_nested_payload_expressions` now recurse for both keys and builder classification; `_every_key` (prongs 1 and 2) already did.
  - `[medium]` `[patch]` A payload built incrementally (`payload = {}` then `payload['ja_id'] = …`) resolved to an EMPTY key set that the scan reported as success — the exact failure it exists to prevent. Constant subscript keys are now collected, a builder assigned in by subscript is classified, and a `payload.update(<non-literal>)` marks the name opaque instead of leaving "some literal bound this name" to mean "the scan has seen everything in it".
  - `[medium]` `[patch]` `_ModuleIndex` indexed `ast.Assign` and nothing else, so a name bound by a tuple unpack, an annotated assignment, a loop target, a `with … as` or an `except … as` had no recorded binding — and `_classify_builder`'s module-wide "a dict-literal binding and nothing else is fully accounted for" fallback then waved it through on the strength of an unrelated `changes = {…}` elsewhere in the file. Whether the guard was strict came down to the statement shape the author used, which is the arbitrariness the previous pass's `_dict_literal_is_opaque` was added to remove. New `_UnreadableBinding` makes each of those shapes fail and say which one it was.
  - `[medium]` `[patch]` Call-site recognition matched the bare spelling, so one `from app.logging_config import log_audit_operation as _audit` made a whole site invisible: not counted, payload never resolved, nothing flagged. `_called_name` resolves through the module's import aliases and matches attribute calls, and `_calls_to` does the same so a payload parameter reached via `self.helper(…)` is traced to its callers — with the bound-call positional offset handled, since crediting the payload with the wrong argument would not fail, it would silently succeed.
  - `[low]` `[patch]` The structural merge guard matched `<Name>.update(…)` only: `self.extra.update(details)`, `extra_data |= details` and `extra_data = {**extra_data, **details}` were all invisible to it. Widened to attribute receivers and `|=`, and backed by a second check from the other end — every read of a caller payload parameter in the four helpers must be a direct argument to one of the guard helpers, which is the acceptance criterion almost verbatim and catches merge shapes the shape scan does not know.
  - `[low]` `[patch]` Three docstrings claimed more than the code holds. `_has_payload` argued that leaving the truth test unguarded "would just move the asymmetry one line up" while `if item_id:` one line up is exactly that; `_message_field` said "a message decoration must not be the one thing that escapes a logging call" four lines above an unguarded `f"on item {item_id}"`; and `_redact_merge` called the merge "Lossless" without noting that two keys coercing to the same string collapse in the walk upstream of it. All three now state the surface they actually cover; the uncovered one is [DW-228].
  - `[low]` `[patch]` `test_a_caller_url_key_does_not_cost_the_whole_record` and `test_a_caller_cannot_forge_an_audit_block_through_log_operation` asserted only that the key was absent from the emitted JSON — which DROPPING it would satisfy just as well, while "lossless" is what the merge claims. Both now assert the value is on the record, nested.
  - `[low]` `[patch]` `_module_record_attr_names` read two named class bodies, so a third filter/formatter, a `setattr(record, …)`, or a `%(name)s` in `setup_logging`'s `stderr_handler` format string (which reads `record.__dict__` exactly like an attribute access) would claim a name the pin never saw. Scanned across the whole module now.
  - `[medium]` `[defer]` DW-227: `operation`/`item_id`/`duration` are the three flat-merge keys still excluded from `_UNMERGEABLE_KEYS` by the spec's explicit **Never**. They are caller-forgeable in the emitted JSON, and they are the last route to the silent record drop the rest of that set exists to close.
  - `[low]` `[defer]` DW-228: the helpers' scalar parameters still run caller `__bool__`/`__format__`/arithmetic outside every guard; five reproducing cases raise out of a logging call.

## Design Notes

**Why a merge wrapper and not a bare `_redact_payload`.** The audit helpers assign the result to a nested key, so a fail-closed `str` return is harmless there. The siblings `update()` it into `extra_data`, where a `str` raises `ValueError`. Nesting the fail-closed result under the parameter name keeps the record emittable and still says what happened.

**The three guard prongs, and the boundary each covers.**

1. *Exercise `_item_to_audit_dict`* with a populated `app.database.InventoryItem` — set the thread columns so the nested `thread` dict materialises (it is `None` on a bare instance), then walk the result recursively. This is the only way to reach the nested `Dimensions.to_dict()` / `Thread.to_dict()` key sets.
2. *Exercise the five ORM `to_dict()` builders* on bare instances — all five work unsaved. `Purchase.to_dict()` yields `request_key`, the exact field the denylist comment cites as the reason for omitting a bare `key`; assert it survives.
3. *AST-scan `app/**/*.py`* for calls to the two audit helpers — matched through the module's import aliases and on attribute calls, so a rename or a `self.helper(…)` cannot switch the recognition off — resolving the payload keyword arguments (`form_data`, `item_before`, `item_after`, `changes`, `batch_data`, `results`) to dict literals: directly, through `IfExp`, through module-wide `name = {…}` bindings, through constant subscript assignments into such a name, and one level through an enclosing function's parameter (`_add_item_with_logging(context=…)`). Literals are read RECURSIVELY, because the redaction walk is: a nested `{'location': {'before': …}}` contributes the inner pair too, and a builder nested one level down is classified rather than skipped. Currently 72 call sites and 60 distinct literal keys. Every argument that stays unresolved must trace to a recognised builder — `_item_to_audit_dict(...)`, an `X.to_dict()` whose receiver is in the reviewed pin, or a literal `None`; anything else fails the scan. A `.to_dict()` is *not* waved through on the method name alone: `to_dict` is defined outside `app/database.py` too (`SearchFilter.to_dict()` builds its keys dynamically), so the receivers are pinned to an explicitly reviewed set naming the prong that covers each.

Prong 3's resolution is deliberately an over-approximation within a module (a `changes = {…}` literal anywhere in `app/main/routes.py` counts). Extra keys only tighten the collision check; there is no false-negative risk, and precise dataflow would be far more fragile than the tripwire is worth.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the new classes.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: green (no `app/utils/` change, but the run is cheap and proves nothing regressed).
- `venv/bin/python -c "import app.logging_config"` -- expected: clean import, no syntax error in the edited module.

**Manual checks:**
- Confirm each new prong fails for the right reason: temporarily add a `'session_token'` key to `_item_to_audit_dict`, a colliding column to one ORM `to_dict()`, and a `changes={'auth_token': 1}` literal at an audit call site; each must fail its own prong. Revert all three.

## Auto Run Result

Status: done
Bundle: `logging-redaction-completeness` (DW-97, DW-100) — second follow-up review pass

**Implemented change.** No new intent. This pass reviewed the committed
DW-97/DW-100 implementation and hardened it. Eight findings were patched; the
production module changed only in its docstrings, and every functional fix
landed in the guard the bundle exists to install — prong 3, whose stated
invariant is that it must FAIL LOUDLY rather than report success on a payload
it never saw. Four ways it did exactly that were found and closed:

- **The scan read only the top level of a payload literal** while the redaction
  walk recurses, so a collision nested one level down was checked by nothing,
  and a `.to_dict()` nested in a literal bypassed the receiver pin entirely.
- **A payload built incrementally** (`payload = {}`, then `payload['x'] = …`)
  resolved to an empty key set the scan called success.
- **A name bound by anything other than a plain `=`** — tuple unpack, annotated
  assignment, loop target, `with … as` — had no recorded binding, and the
  module-wide "a dict literal bound this name" fallback then waved it through.
  Strictness came down to the statement shape the author happened to use.
- **One `import … as`** made a whole call site invisible: not counted, payload
  never resolved, nothing flagged.

Each is now pinned by a synthetic-module test rather than only by the shape of
`app/` today, which is what the previous passes could not assert.

**Files changed.**
- `app/logging_config.py` — docstrings only: `_has_payload` and `_message_field`
  now state that they cover the caller PAYLOAD surface and not the scalar
  parameters one line away (that gap is DW-228), and `_redact_merge` qualifies
  its "lossless" claim against the key coercion upstream of it.
- `tests/unit/test_audit_redaction.py` — `_nested_dict_literals`,
  `_nested_payload_expressions`, `_builds_a_mapping`, `_UnreadableBinding`,
  `_called_name`, `_module_label`; `_ModuleIndex` rewritten around a
  shape-complete binding pass with import aliases; `_scan_audit_payload_keys`
  parametrized over its modules; the structural merge guard widened to attribute
  receivers and `|=` and given a parameter-end companion check; the record-attr
  pin widened to the whole module; two nesting assertions added; and a new
  `TestTheAuditScanFailsLoudlyOnWhatItCannotRead` class (14 tests).
- `_bmad-output/implementation-artifacts/deferred-work.md` — DW-227, DW-228
  appended. No existing entry touched.

**Review findings.** 8 patches applied (4 medium, 4 low), 2 deferred (1 medium,
1 low), 11 rejected, 0 intent gaps, 0 spec defects. Rejected: the receiver pin
keying on receiver TEXT rather than identity (an accepted, documented
over-approximation with a staleness check); prong 2's discovery being
import-order dependent (moot now that receivers are pinned); non-`str` keys
surviving into `record.__dict__` (pre-existing, adjudicated last pass); the two
sibling helpers having no production callers (that is what DW-97 asks be
closed); `app/error_handlers.py` (already tracked as DW-226 — not re-raised);
a secret in a VALUE under a benign key (DW-99, the spec's explicit "Never"); the
prong-3 floors having no headroom (deliberate); unmergeable keys being nested
where `JSONFormatter` does not emit them (that is the forgery prevention
working); `_message_field` rejecting a dict-like non-`Mapping` count; user
attribute names inside `Product.attributes` not being enumerable from a bare
instance; and `dict_bindings` being module-wide (the documented
over-approximation, mitigated by the per-path sentinel keys).

**Verification.**
- `nox -s tests` — green: 3471 passed, 2 skipped (was 3457; +14 tests).
- `nox -s doctests` — green: 22 passed. `import app.logging_config` clean.
- Every patched hole was reproduced against the committed code before the fix
  and re-checked after, with twelve temporary probe modules under `app/`
  (aliased import, attribute call site, tuple unpack, annotated assignment,
  loop target, `with … as`, incremental subscript fill, `.update()` from an
  opaque source, a nested `.to_dict()`, a nested `**` unpack, and two denylist
  collisions reachable only through the new paths). Each failed with its own
  message; all removed, tree confirmed clean.
- The four scan fixes were then reverted one at a time to confirm the new tests
  FAIL when the behaviour they pin regresses — a test that would move in
  lockstep with a wrong implementation is the failure mode the previous pass
  patched. All four are caught.
- The widened structural merge guard was probed with `|=`, an attribute
  receiver, and a `{**extra_data, **details}` rebuild behind an intact
  `_has_payload` gate; the first two fail the shape scan and the third fails the
  new parameter-end check, which no shape scan would have seen.
- The spec's three original manual checks were re-run against the widened scan:
  a `session_token` in `_item_to_audit_dict`, an `api_key_hint` column in an ORM
  `to_dict()`, and a `changes={'auth_token': 1}` literal at a call site each
  still fail their own prong, naming the key. All reverted.

**Residual risks.**
- The two behavioural gaps this pass found were deferred, not closed: DW-227
  (`operation`/`item_id`/`duration` forgeable and able to drop the record) and
  DW-228 (the scalar parameters still raising out of a logging call). Both were
  ruled out by the spec's explicit "Never" list, and DW-227 is the last route to
  the silent record drop the rest of `_UNMERGEABLE_KEYS` exists to close.
- Prong 3 treats a nested value produced by any call other than a `.to_dict()`,
  a dict comprehension or a recognised builder as a scalar leaf. That boundary
  is now stated in `_nested_payload_expressions` rather than implicit, but it is
  still a boundary: an AST pass cannot tell `str(x)` from a dict-returning
  helper.
- The structural merge guard and the parameter-end check are themselves
  verified only by the manual probes above; unlike the resolution logic, they
  read the real `app/logging_config.py` and have no synthetic-source tests.
- `REVIEWED_TO_DICT_RECEIVERS` still pins receiver TEXT, so a generic local
  name (`product`, `purchase`) rebound to a non-ORM class defining `to_dict`
  would be waved through under the wrong prong.
- Redaction remains key-based; DW-99 and DW-226 are unchanged by this pass.
