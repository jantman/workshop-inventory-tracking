---
title: 'DW-69: refuse an all-zero digit run as a GTIN'
type: 'bugfix'
created: '2026-07-28'
status: 'done'
review_loop_iteration: 0
baseline_revision: '5a7131d'
followup_review_recommended: false
final_revision: 'cbe517e'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** An all-zero digit run — `'00000000'`, `'000000000000'`, `'00000000000000'` — is the classic keyboard-wedge no-read output, and it passes the GS1 mod-10 check (zero is the correct check digit over all zeros). So `app/utils/gtin.py` accepts it, `classify()` returns `kind=GTIN, normalized_value='00000000000000'`, and Story 4.3 drives a product lookup that misses and lands the operator on a create form pre-filled with a meaningless trade item number — indistinguishable from a real scan. Nothing in the I/O matrix or the tests covers it in either direction, so today's behavior is accidental rather than chosen.

**Approach:** Refuse an all-zero digit run inside `app/utils/gtin.py` — the single source of truth for GTIN validity — so `normalize_gtin` raises `InvalidGtinError` and `is_valid_gtin` returns `False`. Every caller inherits it with no code change: `scan_router` rule 3 falls through to `free_text`, and the write path can no longer store an all-zero value as a validated `GTIN` identifier (the intended consequence). Pin both directions in tests: `'00000000'` must not be a GTIN, and a genuine GTIN whose check digit happens to be `0` still must be.

## Boundaries & Constraints

**Always:**
- The rule lives **only** in `app/utils/gtin.py`. Under AD-16, `app/utils/scan_router.py` rule 3 delegates validity wholly to `gtin.py`; a zero-run check there would be the second copy of GTIN validity that rule exists to prevent.
- `gtin.py` stays PURE: standard library only, no `app`/Flask/SQLAlchemy imports, no I/O, and `InvalidGtinError` remains its one failure signal.
- `is_valid_gtin` still never raises for any input.
- The refusal applies to the digit string as normalized for length — i.e. an all-zero run of an **accepted** length (8, 12, 13, 14) is refused for being all zeros; runs of other lengths keep their existing wrong-length message. Existing refusal messages for non-digit, wrong-length, non-`str` and bad-check-digit inputs must not change (`tests/unit/test_product_routes.py` asserts them byte-for-byte).
- `compute_check_digit` is unchanged: it is pure arithmetic and `compute_check_digit('0000000000000') == 0` stays true.
- A GTIN that merely *ends* in a zero check digit (e.g. `'00000012345670'`) stays valid.

**Block If:**
- Any existing product identifier row in a fixture, migration, or seed carries an all-zero GTIN that this change would strand.

**Never:**
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md` — the orchestrator records resolution.
- Do not add zero-run logic to `app/utils/scan_router.py`, `app/mariadb_catalog_service.py`, or `app/main/routes.py`.
- Do not broaden the rule to other "suspicious" patterns (repeated digits, sequential runs). All zeros only.
- Do not change accepted lengths, the mod-10 weights, or the canonical key length.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Wedge no-read, GTIN-8 length | `normalize_gtin('00000000')` | raises | `InvalidGtinError`, message names the all-zero reason |
| Wedge no-read, other accepted lengths | `'000000000000'`, `'0000000000000'`, `'00000000000000'` | raises | `InvalidGtinError`, same reason |
| Predicate form | `is_valid_gtin('00000000')` | `False` | Never raises |
| Classifier, both zero forms | `classify('00000000')`, `classify('00000000000000')` | `kind=FREE_TEXT`, `normalized_value=None` | No error expected |
| Genuine GTIN with a zero check digit | `classify('00000012345670')` | `kind=GTIN`, `normalized_value='00000012345670'` | No error expected |
| Genuine GTIN with a zero check digit, util | `normalize_gtin('00000012345670')` | `'00000012345670'` | No error expected |
| Leading zeros but not all zeros | `normalize_gtin('00012348')` | `'00000000012348'` | No error expected |
| All-zero run of a non-accepted length | `normalize_gtin('00000')` | raises | `InvalidGtinError`, existing wrong-length message unchanged |
| Write path, hand-entered | `POST /products/add` with `identifier_type=GTIN`, `identifier_value='00000000'` | 200, nothing written, keyed error naming the all-zero reason plus the existing `GTIN_UNVALIDATED` advisory | Refused before the commit (DW-23 rule) |
| Quarantine type still accepts it | same POST with `identifier_type=GTIN_UNVALIDATED` | stored exactly as entered | No error expected |

</intent-contract>

## Code Map

- `app/utils/gtin.py` -- the only file whose behavior changes; `normalize_gtin` (`:90`) is the enforcement point, `is_valid_gtin` (`:140`) inherits it, module docstring documents the rule.
- `app/utils/scan_router.py` -- rule 3 (`:321-346`) inherits the refusal with no logic change; its "what this module deliberately does not do" docstring (`:56-58`) still names `is_valid_gtin`, which rule 3 no longer calls.
- `app/mariadb_catalog_service.py:2194` -- `add_identifier` calls `normalize_gtin`; inherits the write-path refusal as `ValidationError` naming `GTIN_UNVALIDATED`.
- `app/main/routes.py:1051-1058` -- `_validate_product_create_form` pre-write check; surfaces the new message verbatim.
- `tests/unit/test_gtin.py` -- `TestNormalizeGtin:47`, `TestIsValidGtin:132`; parametrized tables, plain asserts.
- `tests/unit/test_scan_router.py` -- `TestGtinRecognition:296`; `test_every_rejection_reason_falls_through_to_free_text:323` is the home for the zero-run row.
- `tests/unit/test_product_routes.py` -- `TestGtinCheckDigitRefusedBeforeTheWrite:1989`; `test_every_way_the_util_refuses_a_gtin_is_refused_here:2055` asserts exact message bytes.
- `tests/unit/test_scan_resolution.py:2015` -- already carries `'00000000'` as a never-raises vector; must stay green.

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/gtin.py` -- in `normalize_gtin`, after the length check and before the check-digit check, refuse a padded key that is all zeros with `InvalidGtinError`; message must name the reason (e.g. `GTIN must not be all zeros: '00000000'.`) -- placing it after the length check keeps every existing refusal message byte-identical, and before the check-digit check means the reported reason is the true one rather than a check digit that would have passed.
- [x] `app/utils/gtin.py` -- document the rule in the module docstring and in `normalize_gtin`'s `Raises:`; add a doctest to `is_valid_gtin` showing `is_valid_gtin('00000000')` is `False` -- `nox -s doctests` executes `>>>` examples under `app/utils/`, so the example is a live test.
- [x] `app/utils/scan_router.py` -- correct the AD-16 bullet at `:56-58` to name only `gtin.normalize_gtin` (rule 3's actual and only call) and note that GTIN validity, including the all-zero refusal, stays behind it -- the bullet is the module's statement of what it delegates; leaving it naming a function rule 3 does not call invites a future edit to re-add a local check.
- [x] `tests/unit/test_gtin.py` -- add all-zero rejection rows for every accepted length to `TestNormalizeGtin` and to `TestIsValidGtin`, plus a positive row pinning `'00000012345670'` (a genuine GTIN whose check digit is `0`) as valid -- the matrix must be pinned in both directions.
- [x] `tests/unit/test_scan_router.py` -- add `'00000000'` and `'00000000000000'` to `test_every_rejection_reason_falls_through_to_free_text`, and `('00000012345670', '00000012345670')` to `test_every_accepted_length_normalizes_to_the_14_digit_key` -- pins the classifier end of the matrix in both directions.
- [x] `tests/unit/test_product_routes.py` -- add an all-zero row with its exact message to `test_every_way_the_util_refuses_a_gtin_is_refused_here` -- pins the intended write-path consequence rather than leaving it a silent side effect.

**Acceptance Criteria:**
- Given a wedge produces `'00000000'`, when `POST /api/scan` classifies it, then the outcome is the free-text/search path and never a GTIN product lookup.
- Given `app/utils/scan_router.py` after the change, when its source is searched for zero-run logic, then no check for all-zero digits exists outside `app/utils/gtin.py`.
- Given the full unit suite, when `nox -s tests` runs, then it is green with no test weakened or deleted to accommodate the change.
- Given `app/utils/gtin.py` after the change, when `nox -s doctests` runs, then every `>>>` example in the module passes.

## Spec Change Log

## Review Triage Log

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 0, medium 2, low 8)
- defer: 4: (high 0, medium 2, low 2)
- reject: 4: (high 0, medium 0, low 4)
- addressed_findings:
  - `[medium]` `[patch]` AC-1 names `POST /api/scan` but coverage stopped at `classify()` — added `test_the_wedge_no_read_is_not_routed_as_a_trade_item_number` to `tests/unit/test_scan_routes.py`, asserting `kind=free_text`, a `description` pre-fill and NO `identifier_type`/`identifier_value`; also added the no-read as a sixth vector to `test_no_scan_dead_ends`.
  - `[medium]` `[patch]` I/O matrix row 10 (quarantine type still accepts it) had no test — added `test_the_quarantine_type_also_takes_the_wedge_no_read` to `tests/unit/test_product_routes.py`.
  - `[low]` `[patch]` Module docstring enumerated three of the four accepted zero-run lengths — added the 13-digit form.
  - `[low]` `[patch]` Module docstring's list of inheriting callers omitted the lookup path — now names `find_product_id_by_gtin`.
  - `[low]` `[patch]` The read path inherited the change untested — added an all-zero row to `test_find_product_id_by_gtin_resolves_alternate_form`.
  - `[low]` `[patch]` The all-zero key was built inline — extracted `_ALL_ZERO_KEY` beside `_VALID_GTIN_LENGTHS`/`_GTIN_KEY_LENGTH`.
  - `[low]` `[patch]` A second stale `is_valid_gtin` reference survived inside rule 3 itself (`scan_router.py:327`) — renamed to `normalize_gtin`.
  - `[low]` `[patch]` `test_leading_zeros_are_not_an_all_zero_run` duplicated the existing `test_gtin8_normalizes_to_14` byte for byte — replaced with `test_one_nonzero_digit_is_enough_to_be_a_gtin`, the nearest neighbour of the no-read on all four accepted lengths.
  - `[low]` `[patch]` One sentence was split across two `parametrize` data rows in `test_scan_router.py` — each row now carries a complete comment.
  - `[low]` `[patch]` `TestGtinCheckDigitRefusedBeforeTheWrite`'s docstring stated its gate as the check digit alone, which the new row contradicts — restated as the whole of `normalize_gtin`'s acceptance.

### 2026-07-28 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 0, low 7)
- defer: 1: (high 0, medium 1, low 0)
- reject: 12: (high 0, medium 0, low 12)
- addressed_findings:
  - `[low]` `[patch]` `app/main/routes.py:1029` still stated the pre-write gate as "`classify()` types a value GTIN only once its check digit has validated" — the same stale sentence the first pass corrected in `TestGtinCheckDigitRefusedBeforeTheWrite`'s docstring, missed in the code it describes. Restated as the whole of `normalize_gtin`'s acceptance.
  - `[low]` `[patch]` `app/main/routes.py:1036-1038` enumerated the caught-whole `InvalidGtinError` as "a non-digit, a wrong length and a failed check digit" — three reasons where there are now four. Added the all-zero run and corrected "the other two" to "the other three".
  - `[low]` `[patch]` `app/mariadb_catalog_service.py:2172-2176` said "A check-digit failure is surfaced as a domain ValidationError ... that offers the GTIN_UNVALIDATED path" — the all-zero refusal takes that same path and is not a check-digit failure. Restated as any refusal by `normalize_gtin`, with the reasons named.
  - `[low]` `[patch]` `InvalidGtinError`'s docstring was edited in this change to add a reason and still omitted the non-`str` case raised in `normalize_gtin` — now lists all five.
  - `[low]` `[patch]` The all-zero check is an equality against a 14-wide constant, so `zfill` leaves any future accepted length above 14 unpadded and the rule silently stops firing. Confirmed empirically by the reviewer. The Future extensibility section — which already contemplates SSCC-18/GSIN — now names the coupling, keeping the implementation the spec's Design Notes prescribe.
  - `[low]` `[patch]` `tests/unit/test_scan_routes.py` asserted `query == {'description': ...}` and then two `not in` checks that cannot fail. Dropped, with a comment stating that the equality is what pins the absent keys.
  - `[low]` `[patch]` `tests/unit/test_gtin.py:25` pins `compute_check_digit('0000000000000') == 0` ninety lines above a rule refusing that key as a GTIN, with no pointer. Added a cross-reference recording that this is deliberate.

## Design Notes

The check belongs on the **padded 14-digit key**, not the raw input, so all four accepted forms of the no-read collapse to one rule:

```python
padded = s.zfill(_GTIN_KEY_LENGTH)
if padded == '0' * _GTIN_KEY_LENGTH:
    raise InvalidGtinError(f'GTIN must not be all zeros: {value!r}.')
```

Ordering matters for two reasons. It sits **after** the length check so `'00000'` keeps its existing wrong-length message (which the route tests assert byte-for-byte), and **before** the check-digit check so the operator is told the real reason instead of nothing — the all-zero run's check digit is `0` and would have validated.

`is_valid_gtin` needs no code change: it is `try: normalize_gtin(...); return True; except InvalidGtinError: return False`, so it follows automatically.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all unit tests pass.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: `app/utils` doctests pass, including the new `is_valid_gtin` example.
- `grep -rn "0' \* \|'00000000'" app/utils/scan_router.py app/mariadb_catalog_service.py app/main/routes.py` -- expected: no zero-run validity logic outside `app/utils/gtin.py`.

## Auto Run Result

Status: done

**Change.** Unchanged in behavior from the previous pass: `app/utils/gtin.py` — the single source of truth for GTIN validity — refuses an all-zero digit run. The wedge no-read passes the GS1 mod-10 check (zero is the correct check digit over all zeros), so nothing else would have kept it out of the trade-item namespace. `normalize_gtin` raises `InvalidGtinError('GTIN must not be all zeros: …')` on a padded key equal to `_ALL_ZERO_KEY`; the check sits after the length check (so `'00000'` keeps its byte-identical wrong-length message) and before the check-digit check (so the operator is told the true reason). Every caller inherits the rule with no logic change: `scan_router` rule 3 falls through to `free_text`, `find_product_id_by_gtin` misses, and `add_identifier` plus the pre-write route check refuse the value — the write-path consequence the human decision called out as intended. A genuine GTIN whose check digit happens to be `0` is untouched.

This second review pass changed **no production logic and no test outcome**. Its seven patches were all accuracy repairs to prose that the first pass's change had made stale, plus two test-hygiene fixes.

**Files changed** (cumulative since `5a7131d`)
- `app/utils/gtin.py` — the refusal, `_ALL_ZERO_KEY`, a module-docstring section, updated `InvalidGtinError`/`normalize_gtin` docstrings, and a live `is_valid_gtin('00000000')` doctest. *This pass:* `InvalidGtinError` now lists all five refusal reasons (the non-`str` case was still missing), and the Future extensibility section records that the all-zero check is an equality against the 14-wide key.
- `app/main/routes.py` — comments only, **new this pass**: the pre-write block still described its gate as the check digit alone and still enumerated three caught reasons where there are now four.
- `app/mariadb_catalog_service.py` — comments only, **new this pass**: `add_identifier` still described the refusal it surfaces as "a check-digit failure".
- `app/utils/scan_router.py` — comments only. The AD-16 bullet and the rule-3 comment both named `is_valid_gtin`, which rule 3 has not called since Story 4.2.
- `tests/unit/test_gtin.py` — the refusal across all four accepted lengths with exact messages; the ordering-vs-length-check pin; the zero-check-digit positive; nearest-neighbour positives; `is_valid_gtin` rows both directions. *This pass:* a cross-reference on the `compute_check_digit` all-zeros vector recording that leaving it correct is deliberate.
- `tests/unit/test_scan_routes.py` — end-to-end at `POST /api/scan`; a sixth `test_no_scan_dead_ends` vector. *This pass:* dropped two assertions that could not fail after the exact-equality assert above them.
- `tests/unit/test_product_routes.py` — the write-path refusal with its exact message, and the `GTIN_UNVALIDATED` escape hatch holding the value.
- `tests/unit/test_scan_router.py`, `tests/unit/test_catalog_service.py` — classifier both directions; the lookup-path miss.

**Review.** Second pass, two reviewers. 0 intent_gap, 0 bad_spec, 7 patches applied (all low), 1 deferred, 12 rejected. Several reviewer claims did not survive verification and were rejected rather than acted on: the module docstring's "every caller inherits it" is accurate (`resolve_scan`'s GTIN arm queries the namespace inline and is not a `gtin.py` caller); the whitespace × zero-run combination is already covered by `test_strips_surrounding_whitespace` plus the existing rows; and "classic wedge no-read" matches phrasing the codebase already uses at `mariadb_catalog_service.py:3150`. A reported arithmetic error in DW-203's evidence was left alone — existing ledger entries are the orchestrator's to own.

**Deferred** (one new entry): **DW-204** — an all-zero part number inside an ECIA envelope still pre-fills `mpn` and can be saved as an identifier. The no-read is kept out of the GTIN namespace but not out of the MPN one, and closing it is outside this spec's contract, which confines the rule to `app/utils/gtin.py`.

**Rejected:** prose-volume and sourcing critiques of the new comments; the claim that a pure module's docstring must not name its callers; re-litigation of the `GTIN_UNVALIDATED` escape hatch (I/O matrix row 10 makes it intended); and four restatements of DW-200/201/202/203, already on the ledger from the first pass.

**Verification.** `nox -s tests` → 3047 passed, 451 deselected. `nox -s doctests` → 21 passed. Both green; no test was weakened, skipped or deleted. The spec's grep returns one hit, a pre-existing comment about a NUL run (`'\x00'`), not zero-run validity logic. `nox -s e2e` was not run (no template, CSS or JS changed).

**Residual risks.** DW-200 remains the real one: this run verified fixtures, migrations and seeds are clean but cannot see a deployed database, where a pre-existing all-zero `GTIN` row would now be unreachable and unrecreatable. DW-204 is the newly-found one. Everything else is recorded above.

