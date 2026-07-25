---
title: 'Pure scan classifier'
type: 'feature'
created: '2026-07-25'
status: 'done'
review_loop_iteration: 0
baseline_revision: 'efb4c30'
final_revision: '2f5cdbf'
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** FR36/FR37 — scans must be classified by structure in a fixed precedence — has no implementation. Story 4.1 built the transport (`POST /api/scan` echoes cleaned text back with `outcome: 'unrouted'`, `app/main/routes.py:1080-1142`) and deliberately stopped at the seam. `app/utils/scan_router.py` does not exist; the `ScanClassification` shape that AD-15 freezes for Stories 4.3, 4.5, 7 and 9 does not exist. Nothing in the app can yet tell an internal label from a manufacturer GTIN from a DigiKey envelope, so every downstream story is blocked on a contract nobody has written.

**Approach:** Add the frozen `ScanClassification` shape (plus a `ScanKind` enum) to `app/models.py`, and a new pure `app/utils/scan_router.py` exposing one function, `classify(raw, *, ai, token) -> ScanClassification`. It strips an optional AIM symbology identifier, then applies FR36's four rules in order, delegating rule 1 to `gs1.decode()` and rule 3 to `gtin.is_valid_gtin`/`normalize_gtin` rather than re-deriving either. It performs no lookup, imports no Flask and no DB, and reads no config — `ai`/`token` arrive as keyword arguments, exactly as `mariadb_catalog_service.encode_internal_payload` already passes them into `gs1.encode` (`app/mariadb_catalog_service.py:1684-1686`).

## Boundaries & Constraints

**Always:**
- `classify()` is **pure**: no `flask`, no `current_app`, no `config`, no `sqlalchemy`, no `app.database`, no I/O. The only permitted imports are the standard library, `app.models`, `app.utils.gs1` and `app.utils.gtin` (AD-4, AD-5).
- Precedence is fixed and exhaustive — the first rule that matches wins, and rule 4 always matches (FR36):
  1. `gs1.decode(candidate, ai=ai, token=token)` returns a payload → `internal`, `normalized_value = payload.internal_id` (the token-stripped id `decode` already returns).
  2. candidate opens with the ISO/IEC 15434 format-06 header → `ecia`, `normalized_value = None`.
  3. candidate is all ASCII digits, length 8/12/13/14, and `gtin.is_valid_gtin(candidate)` → `gtin`, `normalized_value = gtin.normalize_gtin(candidate)` (14 digits).
  4. anything else → `free_text`, `normalized_value = None`.
- Internal recognition is **delegated, never reimplemented** (AD-16). `scan_router` must not pattern-match the AI or the token itself, must contain no literal `'96'`/`'WIT'`, and must not re-derive a check digit or a 14-digit form — one config change moves encoder and router together.
- An AIM symbology identifier (`]` + one ASCII letter + one digit, e.g. `]d1`, `]C1`) is stripped **once** from the front before the rules run, and only narrows the symbology class — the payload still selects the handler (FR37). `gs1.decode` deliberately does not strip it (`app/utils/gs1.py:89-91`), so the classifier must. A leading `]` that is not that exact 3-character shape is data, not a prefix, and is left alone.
- `raw` on the returned `ScanClassification` is the **verbatim** argument, AIM prefix and all — never the stripped candidate, never re-trimmed. `classify()` performs no whitespace handling of its own; its caller has already applied the one cleaning rule (`_clean_scan_input`, `app/main/routes.py:1071-1077`).
- No value of a `str` `raw` ever raises — not an empty string, not control characters, not 4096 characters of garbage (NFR8). The only two exceptions reachable are caller faults, and both are tested: `TypeError` for a non-`str` `raw`, and `gs1.InvalidGs1PayloadError` propagated unchanged for a malformed `ai`/`token`. A config fault must surface, not silently disable rule 1.
- `ScanClassification` is `@dataclass(frozen=True)` with exactly the AD-15 fields — `kind`, `normalized_value`, `ecia_fields`, `raw` — and lives in `app/models.py`, which stays a leaf module (it imports nothing from `app/`; the dependency runs `scan_router` → `models`, never back).
- `ecia_fields` is always `None` in this story. It is part of the frozen shape, not a placeholder: Story 4.4's parser populates it, and freezing it now is what lets 4.3/4.5/7/9 be written against one contract.
- New tests are `tests/unit/test_scan_router.py`, `@pytest.mark.unit`, grouped in `class Test*`, using the house parametrize idiom of `tests/unit/test_gtin.py:22-30` (one case per line, aligned trailing `#` comment saying why the case exists), citing FR36/FR37/FR37a/AD-15/AD-16 in docstrings, and requiring **no fixtures at all** — the same posture as `test_gtin.py` and `test_gs1.py`.

**Block If:**
- `nox -s tests` is already red on this branch before any change — pre-existing breakage, not this story's.
- Satisfying FR36 would require changing `app/utils/gs1.py` or `app/utils/gtin.py`. Both are frozen Epic 2 contracts with their own exhaustive suites; if the classifier cannot be built on their public API as it stands, that is a human decision.

**Never:**
- No database access, no `CatalogService`, no lookup, no fallthrough-to-search. `resolve_scan()` and `search_products()` are Story 4.3's.
- No ECIA field *parsing*. This story recognizes the envelope's header and stops; extracting `P`/`1P`/`Q`/`K`/`1K`/`9D`/`10D` is Story 4.4's.
- No change to `app/main/routes.py`, `app/templates/**`, `app/static/js/**`, or any existing test. `POST /api/scan` keeps returning `outcome: 'unrouted'` — wiring the classifier into the endpoint without resolution would ship a routed-looking response that routes nowhere, and 4.3 replaces that field anyway. Consequently no screenshots go stale and no e2e test changes.
- No `ScanResolution` shape (4.3 owns it), no `fnc1_substitute` knob (no config key exists and the deployed Tera HW0009 strips FNC1 entirely, which `decode` already handles), no AIM-based dispatch.

## I/O & Edge-Case Matrix

All rows call `classify(raw, ai='96', token='WIT')`. `ecia_fields` is `None` in every row.

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Internal, bare (deployed wedge, FR37a) | `'96WITABC1234567'` | `kind=INTERNAL`, `normalized_value='ABC1234567'`, `raw` verbatim | No error expected |
| Internal, FNC1 transmitted | `'\x1d96WITABC1234567'` | Identical to the bare row — `decode` absorbs it | No error expected |
| Internal behind an AIM prefix (FR37) | `']d196WITABC1234567'` | `kind=INTERNAL`, `normalized_value='ABC1234567'`, `raw` still carries `]d1` | No error expected |
| Rule 1 beats rule 3 | `ai='96'`, `token='0'`, a 13-digit value opening `960` whose check digit is valid | `kind=INTERNAL`, `normalized_value` = the 10 digits after `960` — not `kind=GTIN` | No error expected |
| ECIA format-06 envelope | `'[)>\x1e06\x1dP123\x1e\x04'` | `kind=ECIA`, `normalized_value=None` | No error expected |
| ECIA behind an AIM prefix | `']d1[)>\x1e06\x1dP123\x1e\x04'` | `kind=ECIA` | No error expected |
| Damaged envelope header | `'[)>06\x1dP123'`, `'[)>\x1e05\x1dP123'`, `'[)>\x1e06P123'` | `kind=FREE_TEXT` (NFR8 — never an exception, never a false `ecia`) | No error expected |
| Header with no body | `'[)>\x1e06'` | `kind=ECIA` — a legal empty envelope; 4.4 degrades it | No error expected |
| Valid GTIN-13 | `'9506000134352'` | `kind=GTIN`, `normalized_value='09506000134352'` | No error expected |
| Valid GTIN-14 / UPC-A / GTIN-8 | `'09506000134352'` / `'012345678905'` / `'00012348'` | `kind=GTIN`, normalized to `'09506000134352'` / `'00012345678905'` / `'00000000012348'` | No error expected |
| Bad GTIN check digit | `'9506000134353'` | `kind=FREE_TEXT` | No error expected |
| All-digit, wrong length | `'12345678901'` (11), `'0109506000134352'` (16) | `kind=FREE_TEXT` | No error expected |
| Digits with a separator or sign | `'950-6000134352'`, `'+9506000134352'`, `'٩٥٠٦٠٠٠١٣٤٣٥٢'` (Arabic-Indic) | `kind=FREE_TEXT` — ASCII digits only | No error expected |
| Free text | `'RES 10K 0805 1%'` | `kind=FREE_TEXT`, `normalized_value=None` | No error expected |
| Empty string | `''` | `kind=FREE_TEXT`, `raw=''` | No error expected |
| Adversarial payload | 4096 chars of mixed control characters / `']'` / partial headers | `kind=FREE_TEXT` | Never raises (NFR8) |
| Non-`str` `raw` | `123`, `None`, `b'96WIT'` | — | `TypeError` — a caller fault, not a scan |
| Malformed grammar | `ai=''`, `token=None`, `ai='43'`+`token='1'` | — | `gs1.InvalidGs1PayloadError` propagates unchanged |

</intent-contract>

## Code Map

- `app/models.py` -- 416 lines, leaf module (imports nothing from `app/`). Enum block ends at `IdentifierType` (`:117-136`); put `ScanKind` immediately after it, before `VENDOR_SCOPED_IDENTIFIER_TYPES` (`:139`). Dataclass section is last (`Thread` `:199`, `Dimensions` `:321`); `ScanClassification` goes at end of file. Note: no `frozen=True` exists in this file yet — copy the style from `app/utils/gs1.py:155-179` instead.
- `app/utils/gs1.py` -- `decode(raw, *, ai, token, fnc1_substitute=None) -> Optional[InternalPayload]` at `:351`; returns `None` for any foreign payload and raises `InvalidGs1PayloadError` (`:133`) only on grammar faults. `InternalPayload.internal_id` (`:176`) is already token-stripped. `:89-91` states that stripping an AIM identifier is the classifier's job, not `decode`'s. **Read-only.**
- `app/utils/gtin.py` -- `is_valid_gtin(value) -> bool` at `:140` (never raises), `normalize_gtin(value) -> str` at `:90` (raises `InvalidGtinError`), `_VALID_GTIN_LENGTHS = {8, 12, 13, 14}` at `:40`. **Read-only.**
- `app/mariadb_catalog_service.py:1665-1689` -- the AD-16 config seam to mirror: `Config` read per call, `ai=`/`token=` passed explicitly as keyword args into the pure module. Story 4.3 will call `classify()` this same way. **Read-only in this story.**
- `app/main/routes.py:1053-1142` -- `MAX_SCAN_LENGTH`, `_SCAN_TRIM`, `_clean_scan_input`, `api_scan`. Defines the cleaned-input contract `classify()` assumes and names 4.2 as the seam owner at `:1086`. **Read-only in this story.**
- `tests/unit/test_gtin.py:22-30` -- the canonical parametrize idiom and fixture-free posture to copy. `tests/unit/test_gs1.py:320` -- the repo's canonical ECIA envelope literal `'[)>\x1e06\x1dP12345\x1d1PABC\x1dQ10\x1d\x1e\x04'`; `tests/unit/test_scan_routes.py:39` carries the short form. Reuse these vectors rather than inventing new ones.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- the open entry arguing `_SCAN_TRIM`/`_clean_scan_input`/`MAX_SCAN_LENGTH` should move out of `routes.py` "before 4.2 adds the second consumer". See Design Notes: this story deliberately adds no second Python consumer, so the entry stays open and untouched.

## Tasks & Acceptance

**Execution:**
- [x] `app/models.py` -- add `ScanKind(Enum)` with members `INTERNAL='internal'`, `ECIA='ecia'`, `GTIN='gtin'`, `FREE_TEXT='free_text'` after `IdentifierType`, and `@dataclass(frozen=True) class ScanClassification` with `kind: ScanKind`, `normalized_value: Optional[str]`, `ecia_fields: Optional[Mapping[str, str]]` — `Mapping` from `collections.abc`, not `typing` (widened from `Dict` by the first review pass, which added a `__post_init__` that copies and wraps any mapping in a `MappingProxyType` so `frozen=True` is not a shallow promise; the second pass made that copy unconditional; the third closed the guard set, so `__post_init__` now validates every field's own type plus both cross-field rules tying `normalized_value` and `ecia_fields` to `kind`, against the module constant `_KINDS_CARRYING_A_NORMALIZED_VALUE`), `raw: str` at end of file -- AD-15's four fields in AD-15's order, **all required, no defaults**, so no consumer in Epics 4/7/9 can construct a half-populated classification and every call site states the kind's contract explicitly. Docstrings cite the story, FR36 and AD-15, and state per field what it holds for each kind (as `gs1.py:155-179` does), including that `ecia_fields` is populated only by Story 4.4 and that `raw` is untrusted and must be `repr`-escaped before logging.
- [x] `app/utils/scan_router.py` -- new pure module: module constants `_ECIA_HEADER = '[)>\x1e06'`, `_ECIA_SEPARATORS = ('\x1d', '\x1e')`, `_AIM_PREFIX_RE`, `_FAULT_REPR_CHARS`, `_SLICEABLE_FAULT_TYPES` (the third review pass added the last one: `_bounded_repr` may only pre-slice types that slice without side effects, because slicing an arbitrary object runs its `__getitem__` and a `defaultdict` answers that by inserting a key -- a pure module must not mutate what it was handed, even to describe it); private `_is_ecia_envelope(value)` and `_bounded_repr(value)`; public `strip_aim_prefix(value)` -- exported rather than private because AD-15 freezes four fields, so the AIM-stripped candidate is not carried on the result and Stories 4.3/4.4 must strip it themselves rather than re-derive the shape -- and public `classify(raw, *, ai, token) -> ScanClassification` implementing the four rules in order. Rule 3 calls `gtin.normalize_gtin` inside a `try` rather than asking `gtin.is_valid_gtin` first: behaviourally identical (the predicate *is* try/normalize/except) but it makes NFR8 hold by construction instead of by a private detail of `gtin.py`, and drops a double parse. Comments must say *why* each boundary is where it is (why the header check requires a separator or end-of-string, why AIM is stripped here and not in `gs1.decode`, why a config fault propagates) -- this module is the epic's single routing authority, so its boundaries have to be readable rather than re-derived by Stories 4.3/4.4/4.5.
- [x] `tests/unit/test_scan_router.py` -- new file; module docstring naming the module, story, FR36/FR37 and the fixture-free posture, and stating why the `ScanClassification` shape tests live here rather than in `test_models.py` (the shape is the epic's contract, not a metal-stock model). Classes: `TestScanClassificationShape` (frozen, exact field set, all four required, `ScanKind` members and their wire values), `TestInternalRecognition` (bare/FNC1/AIM forms, token-stripped `normalized_value`, foreign payload is not internal, and a case proving a changed `ai`/`token` pair flips recognition -- AD-16), `TestEciaEnvelopeRecognition`, `TestGtinRecognition` (every valid length, every rejection reason), `TestFreeTextFallthrough`, `TestPrecedenceOrder`, `TestAimSymbologyPrefix` (including a leading `]` that is not an AIM shape), `TestNeverRaisesOnScanData`, `TestCallerFaults` (`TypeError`, propagated `InvalidGs1PayloadError`). Cover every row of the I/O matrix.
- [x] `tests/unit/test_scan_router.py` -- add `TestModulePurity`: parse `app/utils/scan_router.py` with `ast` and assert its import set is a subset of the standard library plus `app.models`, `app.utils.gs1`, `app.utils.gtin`, and that the source contains no literal `'96'`/`'WIT'` -- AD-4/AD-5/AD-16 are stated invariants that no behavioral test can catch being violated, and importing Flask or hardcoding the token would otherwise leave the whole suite green.

**Acceptance Criteria:**
- Given `app/utils/scan_router.py`, when it is imported in a process with no Flask application context and no database configured, then it imports and `classify()` runs -- the classifier is usable by Epic 7's capture path and by tests without an app.
- Given the four FR36 rules, when a value matches more than one, then the earlier rule wins and the result is deterministic for a given `(raw, ai, token)` -- classification depends on nothing but its arguments.
- Given any `str` value whatsoever, when `classify()` is called with a valid `ai`/`token`, then it returns a `ScanClassification` and raises nothing (NFR8).
- Given `ScanClassification`, when a consumer attempts to mutate any field, then it raises -- the shape is frozen so Stories 4.3/4.5/7/9 can pass it around without defensive copying (AD-15).
- Given `POST /api/scan`, when this story ships, then its response is byte-identical to `efb4c30` -- no route, template, JS or e2e change, and no screenshot goes stale.
- Given `nox -s tests`, when it runs, then it is green, including the new `tests/unit/test_scan_router.py`, with no previously passing test newly failing.

## Spec Change Log

## Review Triage Log

### 2026-07-25 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 0, medium 4, low 7)
- defer: 2: (high 0, medium 1, low 1)
- reject: 11
- addressed_findings:
  - `[medium]` `[patch]` The module docstring stated "**No trimming.** `classify()` performs no whitespace handling of its own" — false in one of the four rules and therefore worst where it mattered. `gs1.decode` opens with `raw.strip()` as its FNC1/CR-LF tolerance, so `' 96WITABC1234567 '` classifies `internal` while `' 9506000134352 '` and `' [)>\x1e06…'` classify `free_text`. Two contradictory input policies, and the suite pinned only the strict half. The behavior is right (a matching tolerance here would be the third copy of the trim rule the caller owns), so the fix is to document the asymmetry as deliberate and pin both halves: `TestWhitespaceAsymmetryBetweenRules` now asserts rule 1 tolerates padding, rules 2-4 do not, a leading space even defeats the AIM strip, and every one of those cases routes correctly once the caller's rule has run.
  - `[medium]` `[patch]` The module declared itself the sole owner of AIM knowledge — "no rule has to know AIM exists" — and then discarded the stripped candidate entirely. `classify(']d1RES 10K 0805')` returns `free_text` with `raw` still carrying `]d1`, and `ScanClassification`'s own docstring says free text "is searched as it arrived, via `raw`", so Story 4.3 would have handed `search_products()` a query beginning `]d1` and Story 4.4 would have parsed `]d1[)>…`. AD-15 freezes four fields so the candidate cannot be carried; instead `_strip_aim_prefix` is now the exported `strip_aim_prefix()` and both docstrings state the consumer obligation, so 4.3/4.4 strip with the one implementation rather than re-deriving the shape. Covered by `TestAimPrefixIsExportedForConsumers`.
  - `[medium]` `[patch]` `ScanClassification` was frozen only shallowly, on exactly the field that will hold mutable data. Verified before the fix: `c.ecia_fields['P'] = 'MUTATED'` succeeded through a frozen instance, and `hash(c)` raised `TypeError` once a dict was present — while the docstring's central justification was "passed around without defensive copying: a consumer that needs a different verdict must classify again, not mutate this one". Story 4.4 would have violated the stated invariant with the suite fully green. `__post_init__` now copies and wraps any mapping in a `MappingProxyType`, the field is typed `Optional[Mapping[str, str]]`, and the hashability consequence is documented in both directions. Covered by `TestEciaFieldsIsReadOnly` (5 cases).
  - `[medium]` `[patch]` `test_source_contains_no_literal_from_the_deployed_grammar` — the one test enforcing AD-16 — hardcoded `'96'` and `'WIT'` instead of reading them from `Config`. Change `GS1_INTERNAL_AI`/`GS1_INTERNAL_TOKEN` and it would have kept guarding a grammar that was no longer deployed while the module hardcoded the new one and stayed green: AD-16 defeated by the test written to enforce it. It now reads the configured pair and asserts the configured values are absent from the module source.
  - `[low]` `[patch]` NFR8 held by luck rather than by construction. Rule 3 called `gtin.is_valid_gtin(candidate)` and then `gtin.normalize_gtin(candidate)` separately; that the second cannot raise is true only because the first is implemented as try/normalize/except — a private detail of `gtin.py`, whose docstring anticipates future changes to accepted forms. Any divergence would let `InvalidGtinError` escape a function contracted never to raise on scan data. Now one call inside one `try`, falling through to rule 4 on `InvalidGtinError`, which also drops the double parse.
  - `[low]` `[patch]` The `TypeError` message repr'd an unbounded untrusted value into the traceback and thence the log — a multi-megabyte `bytes` rendered in full — while the module's sibling docstring lectured consumers about log forging. Bounded by `_FAULT_REPR_CHARS = 512`, matching the house rule `app/main/routes.py` already applies to the scan it logs.
  - `[low]` `[patch]` `TestModulePurity` advertised AD-4/AD-5 ("no I/O", "no config") and checked neither: `os`, `pathlib`, `sqlite3` and a bare `open()` are all stdlib or builtins and passed every assertion, so `os.environ['GS1_INTERNAL_AI']` inside `classify()` would have been green. Added an I/O-and-environment import check and a builtin-call check (`open`/`input`/`eval`/`exec`/`__import__`).
  - `[low]` `[patch]` The spec required `app/models.py` to stay a leaf module — a live circular-import hazard, since `ScanClassification`'s docstring is written entirely in terms of `scan_router`, `gs1` and `gtin` — and nothing tested it. The AST machinery existed and was aimed only at `scan_router.py`. Added `test_models_stays_a_leaf_module`.
  - `[low]` `[patch]` `classify`'s `Raises:` section listed the grammar faults incompletely, omitting `_require_grammar`'s token-room rule (`len(token) >= MAX_DATA_FIELD_LENGTH`, `app/utils/gs1.py:278`), which is equally reachable through `classify`; `TestCallerFaults` parametrized eight faults and not that one. Both corrected.
  - `[low]` `[patch]` An internal payload whose data field exceeds `gs1.MAX_DATA_FIELD_LENGTH` returns `None` from `decode` — foreign, not malformed — and so degrades to `free_text` with no signal. Correct (a corrupted label becomes a search rather than an error, which is what "no dead end" means), but it makes the id length limit an undeclared input to classification that neither the docstring's four-rules narrative nor any test named. Documented as a rule-1 exit and pinned from both sides by `TestOverlongInternalPayloadFallsThrough`.
  - `[low]` `[patch]` No case combined an AIM prefix with a transmitted FNC1 (`']C1\x1d96WIT…'`) — the canonical output of a GS1-128 scanner configured to emit both. The matrix covered each half alone. Added.

### 2026-07-25 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 0, medium 4, low 6)
- defer: 3: (high 0, medium 1, low 2)
- reject: 8
- addressed_findings:
  - `[medium]` `[patch]` The previous pass's `MappingProxyType` wrap made the shape unserializable by the two most obvious routes. Verified: `dataclasses.asdict(c)` and `copy.deepcopy(c)` both raise `TypeError: cannot pickle 'mappingproxy' object` for any classification carrying `ecia_fields`. `ScanKind`'s own docstring says the kinds exist because Story 4.5 serializes them to JSON, and `asdict` is the obvious route from a frozen dataclass to JSON — yet the class docstring enumerated exactly one consequence of the wrap (non-hashability) and missed the one that lands as a 500 the moment Story 4.4 populates the field. Documented in both directions and pinned by `test_the_wrap_breaks_asdict_and_deepcopy_for_a_populated_instance` plus its counterpart proving nothing `classify()` returns today is affected.
  - `[medium]` `[patch]` The read-only guarantee had an aliasing hole on the exact branch `__post_init__` skipped. `if not isinstance(fields, MappingProxyType)` meant a caller passing an existing proxy got no copy, so the dict behind it stayed a live write channel into a frozen classification — verified: build with `MappingProxyType(d)`, then `d['P'] = 'MUTATED'`, and `c.ecia_fields['P']` reads `'MUTATED'`. The stated justification for the skip ("equality and repr stay stable across a round trip") was also false; `MappingProxyType(dict(proxy))` compares equal and reprs identically. The copy is now unconditional. Covered by `test_an_incoming_proxy_is_copied_rather_than_adopted`.
  - `[medium]` `[patch]` `__post_init__` coerced non-mappings instead of rejecting them: `dict(fields)` turned `ecia_fields=['ab','cd']` into `{'a': 'b', 'c': 'd'}` — a silently wrong classification — and leaked `dict()`'s own message for a `str` (`ValueError: dictionary update sequence element #0 has length 1`) or an `int`, never naming the class or the field. An `isinstance(fields, Mapping)` guard now rejects by name before the copy. Covered by `test_a_non_mapping_is_rejected_by_name` (5 cases).
  - `[medium]` `[patch]` Every cross-field invariant the docstring asserted was prose only. `ScanClassification(kind='gtin', ...)` constructed cleanly, and every downstream `c.kind is ScanKind.GTIN` would silently have been False; `ecia_fields` could be attached to any kind despite "It is `None` for every non-`ECIA` kind, permanently". The whole rationale for requiring all four fields is that no call site can build a half-populated classification — a call site could still build a self-contradictory one, which is the failure mode Stories 4.3/4.5/7/9 would actually hit. `__post_init__` now enforces both. Covered by `test_kind_must_actually_be_a_scankind` and `test_ecia_fields_cannot_be_attached_to_a_non_ecia_kind`.
  - `[low]` `[patch]` The whitespace-asymmetry analysis the previous pass added stopped at spaces and missed the control characters the caller is explicitly documented as never removing. `str.strip()` eats `\x1c`-`\x1f`, so `gs1.decode` absorbs a transmitted GS while `_clean_scan_input` deliberately preserves it: verified, `'\x1d96WITABC1234567'` is `internal` while `'\x1d[)>\x1e06\x1dP123'` is `free_text`, so a wedge that prefixes a GS silently misroutes every distributor label. `TestWhitespaceAsymmetryBetweenRules` tested only `' ' + ECIA_SHORT`, and its "recovery" case used `.strip(' \t\r\n')`, which by construction cannot recover this one. Now documented in the module contract and pinned from both sides; the behavioral decision is deferred to the story that owns the caller seam.
  - `[low]` `[patch]` The `MAX_DATA_FIELD_LENGTH` boundary pair could not detect upward drift. `'A' * MAX_DATA_FIELD_LENGTH` is a data field of 33 against a limit of 30 — verified, 27 A's is the last `internal` and 28 the first `free_text` — so raising the constant by two left both tests green while the class docstring claimed the limit "cannot drift down without a test noticing". Now `MAX_DATA_FIELD_LENGTH - len(TOKEN) + 1`: exactly one character over.
  - `[low]` `[patch]` `_FAULT_REPR_CHARS` bounded the log line but not the cost its own comment claimed. The code was `repr(raw)` *then* slice, so a multi-megabyte `bytes` was fully materialized as an escaped string before truncation — the amplification half of the stated problem was untouched. Extracted to `_bounded_repr`, which slices before repr'ing wherever the value supports it and keeps the post-slice as a backstop.
  - `[low]` `[patch]` A hostile `__repr__` on a non-`str` `raw` propagated out of the guard that promises `TypeError`, replacing the documented contract with an arbitrary exception for the sake of a diagnostic. `_bounded_repr` now falls back to `<unrepresentable T>`. Covered by `test_a_hostile_repr_does_not_replace_the_documented_typeerror`.
  - `[low]` `[patch]` `TestModulePurity`'s stdlib deny-list was a hand-picked six and missed everything else stdlib: `importlib.import_module('flask')` inside `classify()` passed every assertion in the class, as would `ctypes`, `urllib.request`, `http.client` or `tempfile` — and the builtin-call check only sees `ast.Name` callees, so `os.popen(...)` depended entirely on the deny-list catching the module. Replaced with an allow-list asserting the module's whole import set is exactly `{re, typing, app.models, app.utils}`, which is airtight and makes adding an import an explicit AD-4/AD-5 decision.
  - `[low]` `[patch]` `test_a_classification_without_ecia_fields_is_still_hashable` asserted `hash(c) is not None` — vacuously true for every possible `int`, so the test carried no information beyond "did not raise" and said so nowhere. Now asserts equal classifications hash equally and collapse to one set slot. The Tasks section's stale description of `ecia_fields` as `Optional[Dict[str, str]]`, of `strip_aim_prefix` as private, and of rule 3 as calling `is_valid_gtin` — all three changed deliberately by the first review pass and none recorded — was corrected in the same pass.

### 2026-07-25 — Review pass (second follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 0, medium 3, low 8)
- defer: 1: (high 0, medium 1, low 0)
- reject: 9
- addressed_findings:
  - `[medium]` `[patch]` The cross-field guards the previous pass added enforced two invariants and silently skipped the two with the worst consequences. Verified before the fix: `ScanClassification(kind=ScanKind.GTIN, normalized_value=None, ...)`, `kind=ScanKind.ECIA` *with* a `normalized_value`, and `raw=12345` all constructed cleanly. A `GTIN` carrying nothing to look up is precisely the self-contradictory instance whose prevention was the stated justification for adding guards at all — Story 4.3 would have keyed a lookup on `None` — and `classify()` rejects a non-`str` `raw` at its own door while the shape it builds accepted anything. Partial enforcement is the worst of the three options: it reads as "validated" at the call site while leaving the highest-consequence hole open. `__post_init__` now enforces a closed set — every field's own type, plus both cross-field rules tying `normalized_value` and `ecia_fields` to `kind` — with the two-kind split named as `_KINDS_CARRYING_A_NORMALIZED_VALUE`. Covered by four new tests plus `test_everything_classify_produces_satisfies_every_guard`, which re-runs `__post_init__` over every rule's output so the guards cannot turn an NFR8-clean classifier into one that raises.
  - `[medium]` `[patch]` The one test enforcing AD-16 red-built a correct, unchanged module on reconfiguration. It substring-searched the *whole* 348-line source for the configured AI — two characters, against a file dense with prose — and the module's own `classify()` docstring carries a deliberately illustrative `ai='91', token='ZZ'` example. Reproduced: `GS1_INTERNAL_AI=91 GS1_INTERNAL_TOKEN=ZZ` fails on the docstring the line above disclaims as "illustrative, not the deployed one", and any AI colliding with two adjacent characters anywhere in the prose does the same. AD-16 is a claim about behavior and a docstring has none, so the scan now walks the AST and searches only executed string constants, docstrings excluded. Mutation-tested both ways: no false positive under the reconfigured pair, and injecting `_HARDCODED_AI = '96'` still fails the guard.
  - `[medium]` `[patch]` `_bounded_repr` mutated the caller's object while building an error message about it. `value[:512]` runs an arbitrary `__getitem__`, and a `defaultdict` answers a slice key by *inserting* it — verified: after `classify(defaultdict(list), ...)` raised, the caller's dict read `{slice(None, 512, None): []}`. A module whose entire contract is purity must not modify what it was handed, least of all to describe it. The pre-slice is now gated on `_SLICEABLE_FAULT_TYPES` — the types a bad `raw` is plausibly one of that slice cheaply and without side effects — and everything else is repr'd whole and truncated after, which was already the documented backstop. Covered by `test_describing_a_bad_raw_does_not_mutate_it`.
  - `[low]` `[patch]` `ecia_fields` is declared `Mapping[str, str]` and the docstring names the seven legal MH10.8.2 keys, but only the container type was checked. Verified: `{1: object(), None: b'x'}` was accepted, and `{'P': ['a']}` left the read-only promise false one level down — `c.ecia_fields['P'].append('MUTATED')` succeeded through the proxy. Non-str keys would also reach Story 4.5's `json.dumps` as something it rejects or silently stringifies. Keys and values must now both be `str`.
  - `[low]` `[patch]` `test_the_rejected_value_is_bounded_before_it_is_rendered` asserted only `len(str(exc.value)) < 2_000`, which a post-slice-only implementation — exactly the one its docstring says is wrong — passes identically at 566 characters, so the pre-slice could have been deleted with the suite green. Now pinned with a probe that reports one thing when sliced and another when repr'd whole, plus a case exercising the non-sliceable branch.
  - `[low]` `[patch]` `isinstance(fields, Mapping)` ran against `typing.Mapping`, a deprecated alias since 3.9 that is documented as removable and is not `collections.abc.Mapping`. Runtime checks now use `collections.abc.Mapping`, which also serves the annotation.
  - `[low]` `[patch]` `test_the_whole_import_set_is_the_declared_three` asserted a four-element set, and the builtin deny-list beside it omitted `print` — I/O by any definition and the one of that family a debugging session plausibly leaves behind. Both corrected.
  - `[low]` `[patch]` `test_imports_only_stdlib_models_gs1_and_gtin` was left behind when the previous pass replaced the stdlib deny-list with an exact-set allow-list that strictly subsumes it: it could no longer fail without the newer test failing first. Removed, along with the now-unused `sys` import and `ALLOWED_APP_MODULES`.
  - `[low]` `[patch]` The `__post_init__` error taxonomy was order-dependent: a non-mapping `ecia_fields` raised `TypeError` naming the field for `kind=ECIA` but `ValueError` naming the *kind* for any other — telling the caller the one thing that was not wrong with it, and untested because the non-mapping cases only parametrized over `ECIA`. The type check now runs before the combination check throughout, so `TypeError` always means a wrong type and `ValueError` a wrong combination.
  - `[low]` `[patch]` A test comment labelled `]z9` "an unassigned-but-well-formed identifier". ISO/IEC 15424 assigns `]z` to Aztec Code with modifiers `0`-`9` and `A`-`C`; the genuinely out-of-range values are the letters the regex excludes, which is the open ledger entry on the AIM shape. Comment corrected so it does not misstate the standard it is testing against.
  - `[low]` `[patch]` The test module's docstring claimed a strictly fixture-free posture "the same as test_gtin.py and test_gs1.py" while importing `config`, which calls `load_dotenv()` at import. The import is deliberate and load-bearing for AD-16 — a test restating the grammar as a literal would keep guarding a pair no longer deployed — so the docstring now says so instead of overstating.

## Design Notes

**Why the classifier is not wired into `POST /api/scan` here.** Story 4.1's endpoint docstring names 4.2 and 4.3 as the two fillers of the `outcome: 'unrouted'` seam, which invites wiring `classify()` in now. It should not be: a response saying `outcome: 'gtin'` with no product and no destination is a routed-looking answer that routes nowhere, and 4.3 overwrites that field with a `ScanResolution` the moment it lands. Story 4.2's acceptance criteria are about the function, and AD-4/AD-5 put config-reading and lookup in the service. The endpoint stays untouched, which is also what keeps this story's blast radius to two new files plus an additive edit to `models.py`.

**Where the 4.2/4.4 boundary actually falls.** The epic says a malformed format-06 envelope classifies as `free_text` (NFR8). With no parser in this story, the only thing the classifier can judge is the *header*: header present → `ecia`; header absent, truncated, or a different format indicator → `free_text`. Malformed *contents* behind a valid header still classify as `ecia` here and degrade in Story 4.4, which must fall back to `free_text` when its parse yields nothing. The two halves satisfy NFR8 jointly; 4.4 needs to know it owns the second half.

**Why the header check demands a separator.** ISO/IEC 15434 is `[)>` RS `06` GS … RS EOT, and the format indicator is exactly two digits. `'[)>\x1e0612345'` is therefore not a legal message, and calling it `ecia` would hand Story 4.4 something it cannot parse when `free_text` is the honest answer:

```python
_ECIA_HEADER = '[)>\x1e06'          # '[)>' RS '06' -- tests/unit/test_gs1.py:320
_ECIA_SEPARATORS = ('\x1d', '\x1e')  # GS opens the first record; RS closes an empty one

def _is_ecia_envelope(value):
    if not value.startswith(_ECIA_HEADER):
        return False
    rest = value[len(_ECIA_HEADER):]
    return not rest or rest[0] in _ECIA_SEPARATORS
```

**Why `ScanKind`'s values are lowercase while `IdentifierType`'s are uppercase.** `IdentifierType` (`app/models.py:117-136`) is persisted, and its `value == name` rule exists so a DB row reads unambiguously. `ScanKind` is never persisted — it is a wire value that Story 4.5's JSON response and Epic 7's capture path serialize, sitting beside the existing lowercase `outcome: 'unrouted'` (`app/main/routes.py:1142`). AD-15 spells the four kinds lowercase; matching it keeps the JSON the epic already describes.

**Why `normalized_value` is the token-stripped id, not the payload.** `gs1.decode` already returns `InternalPayload.internal_id` with `ai + token` removed, and Story 2.4 stores exactly that string in `product_identifiers`. Handing 4.3 anything else would force the resolver to strip it a second time — the duplication AD-16 exists to prevent.

**On the deferred `_SCAN_TRIM` relocation.** The ledger argues the trim rule should move into a pure util "before 4.2 adds the second consumer". This story adds no second Python consumer: `classify()` deliberately does no trimming, because a pure classifier that re-cleans its input would be the third copy of the rule rather than a shared one, and because the caller's cleaning is already pinned by `tests/unit/test_scan_routes.py`. The entry stays open and correctly aimed at Story 4.3, which is where the service first calls both the cleaner and the classifier. Do not fold it into this story.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the new `tests/unit/test_scan_router.py`; no previously passing test newly failing.
- `git status --short` -- expected: exactly four paths — modified `app/models.py`, new `app/utils/scan_router.py`, new `tests/unit/test_scan_router.py`, and this spec file. Anything under `app/main/`, `app/templates/`, `app/static/`, `tests/e2e/` or `docs/images/` means the Never boundary was crossed. (`git diff --stat` alone is not sufficient — two of the three code paths are untracked new files.)
- `git diff efb4c30 -- app/utils/gs1.py app/utils/gtin.py` -- expected: empty. Proves the Epic 2 contracts were consumed, not amended.
- `venv/bin/python -c "from app.utils.scan_router import classify; print(classify('96WITABC1234567', ai='96', token='WIT'))"` -- expected: a `ScanClassification` with `kind=ScanKind.INTERNAL` printed with no Flask app context and no database, proving purity outside the test harness.

**Manual checks (if no CLI):**
- `nox -s e2e` is not required: `git status --short` proves no route, template, JS or e2e file changed, so no browser-observable behavior moved. If that diff shows otherwise, run it.


## Auto Run Result

Status: done

**Implemented change.** FR36/FR37's structural scan classification exists as a pure function. `classify(raw, *, ai, token)` in `app/utils/scan_router.py` strips an optional AIM symbology identifier, then applies the four precedence rules — internal (delegated whole to `gs1.decode`), ISO/IEC 15434 format-06 envelope header, check-digit-valid GTIN normalized to 14 digits (delegated to `gtin.normalize_gtin`), free-text fallthrough — and returns the frozen `ScanClassification` that AD-15 fixes as the contract for Stories 4.3/4.5 and Epics 7/9. The module imports no Flask, no config and no database; the grammar arrives as keyword arguments the way `mariadb_catalog_service` already passes it into `gs1.encode`. `POST /api/scan` is untouched and still answers `outcome: 'unrouted'` — wiring resolution in is Story 4.3's.

This pass changed no routing behavior: every I/O-matrix vector classifies exactly as before. It closed the `ScanClassification` construction contract that the previous pass's follow-up recommendation pointed at. That recommendation left the outcome open — complete the accreted guards or judge the accretion itself the problem — and this pass completed them, because a validating constructor covering *two* of the four invariants its own docstring asserts is worse than either extreme: it reads as validated at the call site while leaving the highest-consequence hole (a `GTIN` with nothing to look up) open. The guard set is now closed against the docstring rather than partially covered, which is a terminal state the previous two passes did not reach.

**Files changed (this pass):**
- `app/models.py` — `__post_init__` completed: every field's own type, plus both cross-field rules tying `normalized_value` and `ecia_fields` to `kind`, with type checks ordered before combination checks; `Mapping` taken from `collections.abc` rather than the deprecated `typing` alias; new module constant `_KINDS_CARRYING_A_NORMALIZED_VALUE`.
- `app/utils/scan_router.py` — `_bounded_repr` may only pre-slice `_SLICEABLE_FAULT_TYPES`, so describing a bad `raw` can no longer mutate it.
- `tests/unit/test_scan_router.py` — 1475 total suite cases, up from 1454: the AD-16 literal guard rebuilt on the AST, the bounding test given a probe that can actually fail, a subsumed purity test removed, and new coverage for the completed invariant set, the argument-mutation fix and the error taxonomy.
- `_bmad-output/implementation-artifacts/deferred-work.md` — one new entry appended; no existing entry touched.
- This spec — two stale Tasks descriptions corrected; triage log entry appended.

**Review findings:** 11 patches applied (3 medium, 8 low), 1 deferred (medium), 9 rejected, 0 intent gaps, 0 spec defects. The three medium patches were a partially-enforced constructor contract, an AD-16 test that red-built a correct module whenever the grammar was reconfigured, and a purity violation in the diagnostic path. Rejections were mostly questions the intent contract had already settled (`fnc1_substitute`, the AIM shape, the `_SCAN_TRIM` relocation), one re-litigation of the `MappingProxyType` decision the previous pass documented and pinned, one duplicate of an entry already on the ledger (unexecuted doctests), and three unreachable or incorrect edge cases (`ai=']d'` requires a non-numeric Application Identifier; `strip_aim_prefix(None)` already raises `TypeError`; catching `BaseException` would swallow `KeyboardInterrupt`).

**Verification performed:**
- `nox -s tests` — green: `1475 passed, 359 deselected` (baseline `efb4c30` was `1246 passed`; previous pass `1454 passed`). Nothing previously passing failed.
- Every finding reproduced before fixing and re-checked after: the `GTIN`/`None`, `ECIA`-with-a-value and `raw=12345` constructions; `{1: object()}` and the writable `{'P': ['a']}`; the `defaultdict` left holding `{slice(None, 512, None): []}`; the `ValueError` naming the kind for a non-mapping; and the post-slice-only implementation passing the bounding test at 566 characters.
- The AD-16 guard mutation-tested in both directions: `GS1_INTERNAL_AI=91 GS1_INTERNAL_TOKEN=ZZ` now passes all 229 module tests (it failed before), and injecting `_HARDCODED_AI = '96'` into the module still fails the guard.
- `test_everything_classify_produces_satisfies_every_guard` re-runs `__post_init__` over every rule's output, proving the new guards cannot turn an NFR8-clean classifier into one that raises; NFR8 also re-checked directly over the hostile vectors.
- `git status --short` — only `app/models.py`, `app/utils/scan_router.py`, `tests/unit/test_scan_router.py` and the two artifact files. No route, template, JS, e2e or screenshot change, so `nox -s e2e` was not required.
- `git diff efb4c30 -- app/utils/gs1.py app/utils/gtin.py` — empty. The Epic 2 contracts were consumed, not amended.
- `venv/bin/python -c "from app.utils.scan_router import classify; ..."` — returns a `ScanClassification` with no Flask app context and no database.

**Follow-up review recommendation: true**, with a convergence caveat that matters more than the recommendation. Eleven patches across three files, three at medium, changing when a shared contract's constructor raises — that is above the bar on volume and consequence alone. But this is the third consecutive pass to rework the same object, and each has found real defects in the previous pass's work on it while the routing logic the story is actually about has been unchanged and re-verified three times. The honest reading is that review is now generating work on `ScanClassification` rather than converging on it, and the argument for a fourth pass is weaker than the raw counts suggest. If the orchestrator's follow-up budget is spent, this is a reasonable place to stop: the guard set is closed against the docstring, the sole producer is proven unable to trip it, and no consumer exists yet whose real usage could sharpen the question further.

**Residual risks:**
- `__post_init__` now rejects constructions that previously succeeded. Nothing in the repo builds a `ScanClassification` except `classify()`, which is proven compliant, but Stories 4.3/4.5/7/9 will be the first real callers and will meet these guards before they meet any consumer test.
- An AI-01 element string — the most common manufacturer encoding of a GTIN on a box — classifies as `free_text`. Spec-conformant under FR36's four rules; newly deferred, because a fifth rule is a requirements decision.
- A wedge that prefixes a separator misroutes distributor envelopes to `free_text` while internal labels still route correctly, because `gs1.decode` strips control characters and `_clean_scan_input` deliberately does not. Pinned and documented; deferred, because both fixes cross this story's boundaries.
- The strict ECIA header check may not match what a real wedge transmits (deferred; needs the physical scanner).
- `strip_aim_prefix` implements the intent contract's AIM shape exactly, which is narrower than ISO/IEC 15424 allows for a few symbologies; deferred rather than widened.
- An all-zero digit run classifies as a `gtin` — plausible no-read output. Deferred to `app/utils/gtin.py`, held read-only here.
- A classification carrying `ecia_fields` cannot go through `dataclasses.asdict()` or `copy.deepcopy()`. Documented and pinned, but Story 4.5's serializer must build its payload field by field.
- Nothing in production calls `classify()` yet, so AD-16's config flow reaching the pure function is proven only in Story 4.3.
