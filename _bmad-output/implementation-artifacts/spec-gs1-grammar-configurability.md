---
title: 'GS1 grammar configurability: substitute/marker guard, config-fault attribution, config-derived tests'
type: 'bugfix'
created: '2026-07-26'
status: 'done'
baseline_revision: '5910c8a75d032a9f4032985579bfe404c0f07b44'
final_revision: '5a9365bf0b130b5d6f1275d86506bcedcce86263'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** AD-16 claims one config change flips both encoder and router mechanically. Three things make that false. (1) `gs1.decode` strips one leading `FNC1`-or-`fnc1_substitute` prefix *before* matching the marker, so a `fnc1_substitute` equal to the marker's first character (`ai='96'`, `fnc1_substitute='9'`) silently returns `None` for every genuine label — verified: both `'96WITABC1234567'` and `'\x1d96WITABC1234567'` decode to `None`. `_require_grammar` already fails loudly on the same class of total two-way outage (token-room, 43xx) but has no guard for this one (DW-36). (2) `CatalogService.encode_internal_payload` catches every `gs1.InvalidGs1PayloadError` and re-raises `ValidationError(field='internal_id', value=<the valid id>)`, so an operator's config fault is reported as bad user data — and `ErrorHandler` interpolates `error.field` into user-facing text ("Please check the internal_id field") (DW-39). (3) Four Story 2.4/2.5 tests hardcode the deployed element string, so reconfiguring the pair is already a red build (DW-74).

**Approach:** Move the `fnc1_substitute` rules into `_require_grammar` beside the other grammar rules and add the marker-collision rule there. Give `InvalidGs1PayloadError` a `source` (grammar vs. payload) and a `part` (which knob), set at every raise site, so a caller can classify without parsing messages; `encode_internal_payload` then raises `ConfigurationError(config_key=...)` for grammar faults and keeps `ValidationError(field='internal_id')` for id faults. Rebuild the four hardcoded expectations from `Config`, deriving any alternate grammar arithmetically, and extend the existing AD-16 literal guard to cover the repaired file.

## Boundaries & Constraints

**Always:**
- `app/utils/gs1.py` stays pure: no Flask, no DB, no config import, no literal default for `ai`/`token` (AD-4, AD-16).
- `decode` never raises on `raw` (NFR8). The new rule is a *grammar* fault raised before `raw` is examined, exactly like the existing ones.
- The `fnc1_substitute` checks keep their current shape (single character or `None`) and stay out of `_require_grammar_part`, which forbids whitespace and would reject GS itself. They move into `_require_grammar` as its own block, after the marker is computed.
- Every `raise InvalidGs1PayloadError` in the module passes `source=` explicitly, and `part=` wherever a grammar knob is named. Grammar faults raise from `_require_grammar_part` and `_require_grammar`; payload faults raise only from `encode`.
- `encode_internal_payload` chains the pure error (`raise ... from e`) and carries its message verbatim into whichever domain error it raises, as today.
- `resolve_scan` is untouched: a grammar fault still propagates as `gs1.InvalidGs1PayloadError`, unchanged (4-3 spec line 76).
- In `tests/unit/test_catalog_service.py`, every expected internal element string is assembled from `Config`, and every alternate grammar is *computed* from the configured pair, never spelled — the fourth-recurrence lesson of `4-3-service-scan-resolution.md:171`.
- `'\x1d'` may stay a literal in the tests: FNC1 is a fixed protocol character, not a config value, and spelling it keeps the expectation independent of the module under test.

**Block If:**
- Adding `tests/unit/test_catalog_service.py` to the AD-16 literal guard makes it red on an *ordinary* literal (a description, quantity, or id that happens to equal a reconfigured AI or token) under any pair in the verification matrix. Do not weaken the guard's predicate to accommodate it — leave that file out of the parametrize list, record why in Design Notes, and continue.

**Never:**
- Do not add a config key for `fnc1_substitute` (Epic 4 adds one with its consumer; Story 2.4/2.5 `Never` lists bar a third key here).
- Do not make `scan_router.classify` pass `fnc1_substitute`, and do not catch `InvalidGs1PayloadError` in `resolve_scan`.
- Do not change `ownership_label_text`, `MAX_DATA_FIELD_LENGTH`, the 43xx rule, or the token-room rule.
- Do not fix the residual hardcodes in `tests/unit/test_scan_routes.py` or `tests/e2e/test_wedge_scan.py` — outside DW-74's scope.
- Do not copy helpers between test modules by import; a local definition is correct here.
- Do not edit `{implementation_artifacts}/deferred-work.md`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Substitute collides with the marker | `decode('96WITABC1234567', ai='96', token='WIT', fnc1_substitute='9')` | Refused before `raw` is read | `InvalidGs1PayloadError`, `source='grammar'`, `part='fnc1_substitute'`, message naming the collision and the outage |
| Substitute that does not collide | `decode('~96WITABC1234567', ai='96', token='WIT', fnc1_substitute='~')` | `InternalPayload(internal_id='ABC1234567', ...)` | No error expected |
| Substitute is GS itself | `decode(..., fnc1_substitute='\x1d')` with a non-GS marker | Still accepted, as today | No error expected |
| Substitute malformed | `fnc1_substitute` in `['', '~~', '96', 5, b'~']` | Refused | `InvalidGs1PayloadError`, `source='grammar'`, `part='fnc1_substitute'` (existing behavior, now attributed) |
| Encode with a blank AI | `Config.GS1_INTERNAL_AI = ''`, `encode_internal_payload('ABC1234567')` | Refused as a deployment fault | `ConfigurationError`, `config_key='GS1_INTERNAL_AI'`, message from the pure error, chained |
| Encode with a padded token | token = configured token with a leading space | Refused | `ConfigurationError`, `config_key='GS1_INTERNAL_TOKEN'` |
| Encode under a 43xx marker | `Config.GS1_INTERNAL_AI = '4311'` | Refused | `ConfigurationError`, `config_key='GS1_INTERNAL_AI/GS1_INTERNAL_TOKEN'` (the fault is the pair's, `part='marker'`) |
| Encode a bad id | `encode_internal_payload('')` | Refused as user data | `ValidationError`, `field='internal_id'`, `value=''` — unchanged |
| Encode the ownership text | `encode_internal_payload(ownership_label_text())` | Refused as user data | `ValidationError` — unchanged (spaces/punctuation are a payload fault) |
| Scan under a malformed grammar | `resolve_scan(...)` with `GS1_INTERNAL_TOKEN=''` | Propagates | `gs1.InvalidGs1PayloadError` unchanged → 500 — unchanged |
| Suite under a reconfigured pair | `GS1_INTERNAL_AI=91 GS1_INTERNAL_TOKEN=ZZ nox -s tests` | Green | No error expected |

</intent-contract>

## Code Map

- `app/utils/gs1.py` -- `InvalidGs1PayloadError` (133, docstring only, no `__init__`); `_require_grammar_part` (182, raises at 209/212/215); `_require_grammar` (221, 43xx at 273, token-room at 279, returns marker at 282); `encode` (285, calls `_require_grammar` at 315, id faults at 321/325/330/339); `decode` (351, inline `fnc1_substitute` validation at 393-404, prefix-strip loop at 417-420, marker match at 422). Doctests at 312 and 387-390 must keep passing.
- `app/mariadb_catalog_service.py` -- `encode_internal_payload` at **1781-1806** (the ledger's `:738-743` is stale); the sole `except gs1.InvalidGs1PayloadError` at 1803. Imports at 27 (`from .exceptions import ValidationError`) and 34 (`from config import Config`). `resolve_scan` at 2109 (config read at 2322-2326) — read-only reference.
- `app/exceptions.py` -- `ValidationError` (24, `message/field/value`); `ConfigurationError` (74, `message/config_key`, sets `details={'config_key', 'type'}`).
- `app/error_handlers.py` -- `ConfigurationError` → 500 (415-423); `ValidationError` → 400 (373-380); `error.field` interpolated into user text at 98-103 — the reason the mis-attribution matters.
- `tests/unit/test_gs1.py` -- `AI`/`TOKEN`/`ID` at 27-29; `fnc1_substitute` cases at 142, 146-153, 159, 434-442. Home for the new guard's tests.
- `tests/unit/test_catalog_service.py` -- imports at 1-15 (**no module-level `Config`**); `_added_identifiers` helper at 18 (the precedent for a module-level `_`-helper); `TestEncodeInternalPayload` 911-966 with hardcodes at **917, 924, 931**; `TestOwnershipLabelText` 969-1073 with a hardcode at **1057**. Note the real method names are `test_token_change_flips_output_with_no_code_edit` and `test_ai_change_flips_output_with_no_code_edit` (the ledger's names do not exist).
- `tests/unit/test_scan_resolution.py` -- `_internal_scan()` 120-128 and `_shifted()` 130-150 are the patterns to mirror; `TestConfigSeam` at 1192 with `_string_literals_outside_docstrings` (1199) and `test_no_executed_string_literal_holds_the_configured_grammar` parametrized over `['module', 'this test file']` at ~1271-1316 — the guard to extend.

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/gs1.py` -- give `InvalidGs1PayloadError` an `__init__(self, message, *, source, part=None)` storing `.source` and `.part`, with class constants `GRAMMAR = 'grammar'` and `PAYLOAD = 'payload'`; update its docstring to document the two attributes alongside the existing source split. Pass `source=`/`part=` at all ten existing raise sites: `_require_grammar_part` → `GRAMMAR`, `part=name`; the 43xx rule → `GRAMMAR`, `part='marker'`; the token-room rule → `GRAMMAR`, `part='token'`; all four `encode` id rules → `PAYLOAD`, `part=None`. Rationale: the flat exception carries no way to tell an operator's fault from a user's, and message parsing is not one.
- [x] `app/utils/gs1.py` -- change `_require_grammar` to `(ai, token, fnc1_substitute=None)`; move the single-character validation out of `decode` into it, after the marker is computed, and add the collision rule: refuse when `fnc1_substitute == marker[0]`, because `decode` consumes that character before testing the marker so every genuine label — bare or GS-prefixed, since `raw.strip()` removes GS first — decodes to `None`. Both raise `source=GRAMMAR, part='fnc1_substitute'`. Update `_require_grammar`'s `Raises:` docstring with the new rule in the same voice as the token-room paragraph; update `decode` to call `_require_grammar(ai, token, fnc1_substitute)` and drop its inline block, keeping the explanatory comment about why the substitute is not run through `_require_grammar_part`.
- [x] `app/mariadb_catalog_service.py` -- import `ConfigurationError` alongside `ValidationError`; in `encode_internal_payload`, branch on `e.source`: `GRAMMAR` → `raise ConfigurationError(str(e), config_key=...) from e` with `part` mapped `'ai'`→`'GS1_INTERNAL_AI'`, `'token'`→`'GS1_INTERNAL_TOKEN'`, anything else → `'GS1_INTERNAL_AI/GS1_INTERNAL_TOKEN'`; otherwise `raise ValidationError(str(e), field='internal_id', value=str(internal_id)) from e`. Update the method's `Raises:` docstring to name both outcomes. Rationale: `field`/`value` exist so UI and logs can key on them; pointing them at valid data is the defect.
- [x] `tests/unit/test_gs1.py` -- add coverage for the collision rule (colliding substitute refused for a bare and a GS-prefixed genuine label; a non-colliding substitute still strips and decodes; the rule fires before `raw` is inspected, e.g. with a non-string `raw`) and for `source`/`part` on one representative raise site per category (`ai`, `token`, `marker`, `fnc1_substitute`, and an `encode` payload fault). Keep the file's existing explicit-`ai=`/`token=` style — it is deliberately literal because the grammar is its subject.
- [x] `tests/unit/test_catalog_service.py` -- add `from config import Config` at module level; add module-level `_element_string(internal_id, *, ai=None, token=None)` returning `'\x1d' + ai + token + internal_id` defaulting to the configured pair, and a local `_shifted(text)` mirroring `tests/unit/test_scan_resolution.py:130-150`. Rewrite the four hardcoded assertions (917, 924, 931, 1057) to use them, and in the two flip tests derive the alternate half with `_shifted` and assert it differs from the configured value before monkeypatching. Add tests for the DW-39 matrix rows: blank AI → `ConfigurationError(config_key='GS1_INTERNAL_AI')`, padded token → `ConfigurationError(config_key='GS1_INTERNAL_TOKEN')`, `'4311'` AI → `ConfigurationError` with the pair key, and that `encode_internal_payload('')` still raises `ValidationError(field='internal_id')` and not `ConfigurationError`. Reconfigure via `monkeypatch.setattr(Config, ...)` as the file already does.
- [x] `tests/unit/test_scan_resolution.py` -- add `tests/unit/test_catalog_service.py` as a third case to `test_no_executed_string_literal_holds_the_configured_grammar`'s parametrize list, so the repaired file cannot silently reacquire a hardcoded grammar. Predicate and helpers unchanged. Subject to the **Block If** above.

**Acceptance Criteria:**
- Given `fnc1_substitute` equal to the marker's first character, when any decode is attempted, then it is refused loudly rather than silently returning `None`, matching how the token-room rule treats the same class of total outage.
- Given a malformed configured grammar, when `encode_internal_payload` is called with a perfectly valid id, then no error carries `field='internal_id'` or that id as `value`, and the raised error names the config key an operator would change.
- Given the deployed pair is reconfigured to any of `91/ZZ`, `95/QQ`, `17/AB`, `40/XY`, `01/WT`, when `nox -s tests` runs, then the suite is green — the mechanical config change AD-16 promises.
- Given the AI/token pair is injected as a literal into `tests/unit/test_catalog_service.py`, when the AD-16 literal guard runs, then it turns red.

## Spec Change Log

## Review Triage Log

### 2026-07-26 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 13: (high 0, medium 3, low 10)
- defer: 2: (high 0, medium 0, low 2)
- reject: 6: (high 0, medium 0, low 6)
- addressed_findings:
  - `[medium]` `[patch]` `_shifted` could derive an *illegal* alternate grammar, reintroducing the DW-74 failure mode inside the DW-74 fix: with `GS1_INTERNAL_AI='32'` it yields `'43'`, which `gs1` refuses outright (FR12d), so both flip tests raised instead of flipping. Verified red at `32/WIT` before the fix, green after. Replaced by `_alternate_half` (this file) and `_alternate_pair` (`test_scan_resolution.py`, which carried the same defect and is edited here anyway), which shift repeatedly until the derived grammar is both different and accepted by `gs1.encode` — legality asked of the module rather than restated, so no `'43'` literal is planted in a file the AD-16 guard scans. `_shifted`'s docstring no longer claims the universal "no character survives" its `else` branch contradicts, and its class tests use explicit ranges so a non-ASCII digit cannot crash `int()`.
  - `[medium]` `[patch]` Two contract docstrings stated the opposite of the code after the change — `resolve_scan` (`app/mariadb_catalog_service.py`) and the mirrored sentence in `tests/unit/test_scan_resolution.py` both said `encode_internal_payload` translates a grammar fault to a `ValidationError` "because its bad input is a user-supplied id". Both rewritten around the real distinction: both methods treat it as a deployment fault, and they differ only in how far they translate it.
  - `[medium]` `[patch]` The collision rule's docstring, error message and test class all claimed *every* genuine label would decode to `None`. False for a scanner that always emits its substitute: `decode('996WITABC1234567', fnc1_substitute='9')` decoded before this change and now raises. All three reworded to the true scope — the collision costs two of the three FNC1 transmissions `decode` exists to absorb (stripped and GS, i.e. every label the deployed hardware produces) — and the narrowing is now pinned by its own test rather than left to be rediscovered.
  - `[low]` `[patch]` `InvalidGs1PayloadError` became uncopyable and unpicklable: `BaseException.__reduce__` replays `args` positionally against a keyword-only `source`. Verified `copy`, `deepcopy` and `pickle` all raised `TypeError`. Added `__reduce__` plus a module-level rebuild function, and a test asserting the classification survives all three round trips.
  - `[low]` `[patch]` The service's `except` blamed the id by default, so an unclassified `source` would land in exactly the branch the change exists to avoid. Inverted: only an explicit `PAYLOAD` raises `ValidationError`; everything else is attributed to the configuration.
  - `[low]` `[patch]` The comment on the `config_key` fallback justified it entirely by `part='fnc1_substitute'`, which it then conceded cannot reach that code, and never named `part='marker'` — the case that actually gets there. Rewritten.
  - `[low]` `[patch]` The extended literal guard's third parametrize case resolved `'tests/unit/test_catalog_service.py'` as `Path(__file__).parent / Path(path_name).name`, silently discarding the directory: any future entry outside `tests/unit/` would have rescanned the wrong file. Now resolved from the repository root with an existence assert.
  - `[low]` `[patch]` The widened false-positive surface of guarding a third, literal-dense file was undocumented. Measured and recorded in the guard's docstring: no two-digit AI collides, but ~75 one-to-three-character tokens do. The predicate stays exact (loosening it is what the 4.3 review removed); the constraint is now stated instead of latent.
  - `[low]` `[patch]` Three assertions in the new service tests could not fail — `pytest.raises(Exception)` around a `ConfigurationError` case, `!= getattr(exc.value, 'value', None)` against a class with no `.value`, and `not isinstance(..., ConfigurationError)` inside `pytest.raises(ValidationError)` (disjoint siblings). Tightened to `pytest.raises(ConfigurationError)` with an assertion on the structured `details`, and the unfalsifiable sibling check removed.
  - `[low]` `[patch]` `test_encode_is_unaffected_because_it_takes_no_substitute` asserted only that CPython rejects an unknown keyword, in the collision test class. Replaced by the narrowing test described above.
  - `[low]` `[patch]` Attribution coverage had three holes: no test pinned `part='token'` from the token-room rule, `part='ai'` from the non-printable rule, or the service's `config_key` for either. All added, with the token length computed from `MAX_DATA_FIELD_LENGTH` rather than spelled.
  - `[low]` `[patch]` The overlong-id case added during this pass hardcoded `'A' * 28`, which overflows beside a three-character token and fits beside a two-character one — a red build at `91/ZZ`, caught by the matrix. Replaced by `OVERLONG_ID`, computed from the bound and the configured token.
  - `[low]` `[patch]` `app/utils/gs1.py`'s module docstring still said the service translates the error into a domain `ValidationError` — the first thing a reader of the module sees, and now only half true. Updated to name both outcomes and the `source` that selects between them.
  - `[low]` `[defer]` DW-115 — a `GS1_INTERNAL_TOKEN` of 21-29 characters still surfaces as `ValidationError(field='internal_id', value=<the valid id>)`, DW-39's defect in the data-field-overflow corner. Closing it needs a design call this spec's `Never` list forecloses.
  - `[low]` `[defer]` DW-116 — `resolve_scan` still lets the raw `gs1.InvalidGs1PayloadError` reach the request as an anonymous 500 for the same config fault, on the path that actually has a production caller.

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 0, low 5)
- defer: 0
- reject: 16: (high 0, medium 0, low 16)
- addressed_findings:
  - `[low]` `[patch]` Two of the three assertions in `test_no_config_fault_blames_the_id_it_was_handed` could not fail, leaving the parametrized matrix that advertises itself as pinning the DW-39 defect resting on `config_key` alone. Verified: `ConfigurationError` defines no `field` attribute, so `getattr(exc.value, 'field', None) != 'internal_id'` holds unconditionally, and `app/exceptions.py:104` builds `details` from `config_key` and a type tag only — the message never reaches it, so `'ABC1234567' not in str(exc.value.details)` holds unconditionally too. Replaced by the one falsifiable form, `'ABC1234567' not in str(exc.value)`: the message is the only place left where the id could still surface. An `isinstance(..., ValidationError)` check was considered and rejected as the same unfalsifiable-sibling mistake the previous pass removed in mirror image; the reasoning is recorded in the comment so it is not re-attempted.
  - `[low]` `[patch]` `source` was validated only by being required, not by its value: `InvalidGs1PayloadError('boom', source='typo')` was accepted (verified). Because `encode_internal_payload`'s branch is deliberately asymmetric — only an explicit `PAYLOAD` blames the id — a misspelled source at a future raise site would have reported a genuine bad id as a `ConfigurationError` naming both grammar keys, this attribute's own defect running backwards. `__init__` now refuses anything outside the two constants, the class docstring's guarantee is restated to cover misspelling as well as omission, and a test pins both `'typo'` and `None`.
  - `[low]` `[patch]` The hand-written `__reduce__` added last pass was lossy in three ways, all silent: it rebuilt `InvalidGs1PayloadError` by name (a subclass came back downcast), used the two-element form (every attribute a caller had attached was dropped), and replayed `self.args[0]` alone (args after the first vanished, changing `str()`). All three verified before the fix. Now returns `type(self)`, the full `args` tuple and `self.__dict__` as state, with `_rebuild_invalid_gs1_payload_error` restoring `args` wholesale rather than through the single-message constructor. Pinned by a new test covering a subclass, a multi-arg error and an attached attribute.
  - `[low]` `[patch]` `_overlong_id()` computed `MAX_DATA_FIELD_LENGTH - len(token) + 1` with no floor, so a token at or past the bound drove it to `'A' * 0` — the blank id, which fails for its own unrelated reason, leaving the overlong case passing while testing nothing. Now asserts the length is positive; such a token is already an illegal deployment, so this refuses rather than adjusts.
  - `[low]` `[patch]` `tests/unit/test_gs1.py`'s payload-attribution parametrize kept `'A' * 28`, overlong only because that file's `TOKEN` happens to be three characters — the same "hardcoded grammar wearing a different hat" `_overlong_id()` was written to eliminate one file over, and a case that would silently stop testing anything if the bound were raised. Computed from `MAX_DATA_FIELD_LENGTH` and the module's own `TOKEN` instead. (The file's explicit `AI`/`TOKEN` literals stay — the spec keeps them deliberately, the grammar being this file's subject.)

## Design Notes

**Why `source` on the exception rather than a pre-flight grammar call.** The service could re-validate the pair before encoding, but that duplicates the rule set and lets it drift — precisely what AD-16 exists to prevent. Classifying at the raise site is one keyword per raise and cannot fall out of step with the rules. `source` is required and keyword-only so a future raise site must classify itself; verified that `InvalidGs1PayloadError` is constructed nowhere outside `app/utils/gs1.py`.

**Why `part='marker'` maps to the pair, not to one key.** The 43xx rule is checked against `ai + token`, so `ai='4', token='311'` is refused with neither half individually at fault. Naming one key would send the operator to the wrong line of `.env`; naming the pair matches AD-16's own "one named pair" language. The mapping's fallback branch also absorbs `part='fnc1_substitute'`, which has no config key and cannot reach this path today (`encode` takes no substitute).

**Why `_shifted` is duplicated rather than shared.** Importing it from `tests/unit/test_scan_resolution.py` would recreate exactly the cross-test-module coupling the previous sweep removed from `tests/e2e/`, and hoisting it into `tests/conftest.py` would mean rewriting a file DW-74 does not cover. Ten lines of a pure helper is the cheaper trade.

**Why the 2026-07-27 pass rejected sixteen findings.** Both reviewers led with the data-field-overflow corner — a `GS1_INTERNAL_TOKEN` of 21-29 characters still surfacing as `ValidationError(field='internal_id')` — which is real and already recorded as DW-115 by the previous pass, so it is a duplicate rather than a new finding. Three more objected to behavior the `<intent-contract>` I/O matrix mandates outright: that a `43xx` AI set alone is attributed to `GS1_INTERNAL_AI/GS1_INTERNAL_TOKEN` rather than to the AI, that a slash-joined pseudo-key is a poor shape for `config_key`, and that the extended literal guard's short-token collisions are a hazard (the **Block If** governs that one, and no pair in the matrix trips it). Two more — that the collision rule has no production caller and that `encode_internal_payload` has none either — are the deliberate posture of a seam built ahead of its Epic 4 consumer, which the `Never` list forecloses changing here; both were confirmed by grep and are working as specified. The rest were style (prose volume, `part` lacking named constants where every `part` value is already pinned by a test), unreachable defensiveness (`getattr(e, 'source', ...)` against a required constructor argument), or claims that do not survive checking: `_alternate_half`'s one-character legality probe cannot mis-certify, because the shift preserves length and so the derived pair overflows the data field exactly when the configured pair already does.

**Review-pass additions beyond the Tasks list.** The review pass added four things the Execution tasks do not name: `InvalidGs1PayloadError.__reduce__` plus `_rebuild_invalid_gs1_payload_error` in `app/utils/gs1.py`; `_alternate_half` and `OVERLONG_ID` in `tests/unit/test_catalog_service.py`; `_alternate_pair` in `tests/unit/test_scan_resolution.py`, which also repairs that file's own `_shifted` call sites; and an inversion of `encode_internal_payload`'s `except` so `ValidationError` is the explicit `PAYLOAD` case rather than the default. See the Review Triage Log for why each was needed.

**Known residual, deliberately out of scope.** `tests/unit/test_scan_routes.py:107,178,179` and `tests/e2e/test_wedge_scan.py:157,159,164,172` still spell `96WIT…`. DW-74 names only `tests/unit/test_catalog_service.py`, and the e2e session is not part of the reconfiguration matrix, so those files stay hardcoded after this change and the AD-16 literal guard is not extended to them.

## Verification

**Commands:**
- `venv/bin/python -c "from app.utils.gs1 import decode; decode('96WITABC1234567', ai='96', token='WIT', fnc1_substitute='9')"` -- expected: `InvalidGs1PayloadError` (before this change it returns `None`).
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: green; the `encode`/`decode` examples are unchanged.
- For each pair in `91/ZZ`, `95/QQ`, `17/AB`, `40/XY`, `01/WT`: `GS1_INTERNAL_AI=<ai> GS1_INTERNAL_TOKEN=<token> PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -r -s tests` -- expected: green for every pair (`-r` reuses the session virtualenv so five runs do not reinstall five times). Before this change, four tests in `tests/unit/test_catalog_service.py` fail on all five.
- Mutation check of the extended guard: temporarily replace one rebuilt expectation in `tests/unit/test_catalog_service.py` with the literal element string and confirm `test_no_executed_string_literal_holds_the_configured_grammar[tests/unit/test_catalog_service.py]` fails; revert.

**Manual checks (if no CLI):**
- `grep -n "raise InvalidGs1PayloadError" app/utils/gs1.py` -- every hit passes an explicit `source=`.
- `app/mariadb_catalog_service.py` `resolve_scan` and `app/utils/scan_router.py` are unmodified; `classify`'s `Raises:` section still enumerates only faults it can actually produce (it never passes `fnc1_substitute`).

## Auto Run Result

Status: done
Bundle: `gs1-grammar-configurability` (DW-36, DW-39, DW-74)

**Implemented change.** AD-16's claim that one config change flips both encoder and router is now true in the guard, in the error attribution and in the suite. `gs1._require_grammar` took over the `fnc1_substitute` rules from `decode` and gained a collision rule refusing a substitute equal to the marker's first character — the configuration that silently made every genuine label undecodable (DW-36). `InvalidGs1PayloadError` now carries `source` (`GRAMMAR`/`PAYLOAD`) and `part`, validated and set at every raise site, so `CatalogService.encode_internal_payload` raises `ConfigurationError` naming the config key for an operator's fault instead of `ValidationError(field='internal_id', value=<a valid id>)` (DW-39). The four Story 2.4/2.5 tests that spelled `'\x1d96WITABC1234567'` build their expectations from `Config` and derive alternate grammars arithmetically, and the AD-16 literal guard now covers that file so it cannot reacquire the hardcode (DW-74).

**Files changed.**
- `app/utils/gs1.py` — `InvalidGs1PayloadError` gained `GRAMMAR`/`PAYLOAD`, a keyword-only `source` checked against those two constants, `part`, and a `__reduce__` that carries the classification (with the exception's type, full `args` and instance state) through copy and pickle; `_require_grammar(ai, token, fnc1_substitute=None)` absorbed the substitute rules and added the marker-collision rule; all 11 raise sites classify themselves.
- `app/mariadb_catalog_service.py` — `encode_internal_payload` branches on `e.source`: only an explicit `PAYLOAD` blames `internal_id`; everything else raises `ConfigurationError` with `config_key` mapped from `part`. Both paths chain the pure error. `resolve_scan` unchanged; its `Raises:` docstring corrected.
- `tests/unit/test_gs1.py` — collision coverage (bare, GS-framed, before-`raw`, narrowness, the substitute-carrying form deliberately given up) and attribution coverage (every knob-naming raise site, all four id rules, source validation, and a copy/pickle round trip that pins type, args and attached state).
- `tests/unit/test_catalog_service.py` — module-level `Config`; `_element_string`, `_shifted`, `_alternate_half`, `OVERLONG_ID`; the four hardcodes rebuilt; `TestEncodeAttributesTheFaultToWhoeverCausedIt` covering every grammar rule's `config_key` and the id direction.
- `tests/unit/test_scan_resolution.py` — `_alternate_pair` (fixing the same `_shifted` legality defect this file already carried); the AD-16 literal guard extended to `tests/unit/test_catalog_service.py`, resolved from the repository root.

**Review findings.** Two passes.
- 2026-07-26: 0 intent_gap, 0 bad_spec, 13 patches applied (3 medium, 10 low), 2 deferred (DW-115, DW-116), 6 rejected.
- 2026-07-27 (follow-up): 0 intent_gap, 0 bad_spec, 5 patches applied (all low), 0 deferred, 16 rejected. The pass found no defect in the shipped behavior; all five patches close gaps in what the *tests* prove and in the exception's own defensive plumbing. Nothing was appended to the deferred-work ledger — the one finding worth deferring was already recorded as DW-115. See the Review Triage Log.

**Verification.**
- `nox -s tests` — 2610 passed, 370 deselected.
- `nox -s doctests` — 20 passed.
- Reconfiguration matrix, full unit suite green at every pair: default `96/WIT`, `32/WIT`, `91/ZZ`, `95/QQ`, `17/AB`, `40/XY`, `01/WT`, `09/ZZZ`, `88/QW`. `32/WIT` is retained from the first pass, which found it red — the derived alternate grammar was `43`, which FR12d bars.
- DW-36 repro: `decode('96WITABC1234567', ai='96', token='WIT', fnc1_substitute='9')` raised `InvalidGs1PayloadError(source='grammar', part='fnc1_substitute')`; it returned `None` at baseline.
- Literal-guard mutation check both ways (first pass): reinstating `'\x1d96WITABC1234567'` failed `test_no_executed_string_literal_holds_the_configured_grammar[tests/unit/test_catalog_service.py]`; reverting restored green.
- Second pass, each patched behavior confirmed by execution before and after: `source='typo'`/`None`/`'Grammar'` accepted before, refused with `ValueError` after; a subclass with a multi-arg `args` and an attached attribute came back downcast, truncated and stripped before, faithful after; base-class pickle round trip still intact; the grammar-fault message confirmed not to contain the id, so the replacement assertion is falsifiable rather than another tautology.
- `nox -s e2e` not run (no UI or template change); `nox -s lint` not runnable — flake8 lives only in that session's own virtualenv.

**Residual risks.**
- DW-115 and DW-116 (both logged): the data-field-overflow corner still mis-attributes, and `resolve_scan` still surfaces a config fault as an anonymous 500. Both reviewers rediscovered DW-115 independently, which is a fair signal of how visible it is from the code.
- The extended literal guard is exact-match on a configurable string over a literal-dense file: a one-to-three-character `GS1_INTERNAL_TOKEN` collides with ordinary test data. Measured and documented in the guard's docstring; no pair in the matrix is affected.
- `tests/unit/test_scan_routes.py` and `tests/e2e/test_wedge_scan.py` still hardcode `96WIT…`; outside DW-74's scope and not covered by the guard.
- Neither the collision guard nor `encode_internal_payload` has a production caller until Epic 4 gives `fnc1_substitute` a config key and wires the encoder to a route. DW-36 anticipated this and asked for the guard first; the consequence is that the user-visible half of DW-39's fix (a 400 with recovery suggestions becoming a 500 "Application configuration error") is asserted only at the service boundary.

