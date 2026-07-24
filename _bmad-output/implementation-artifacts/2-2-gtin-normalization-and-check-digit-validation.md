---
title: 'GTIN normalization and check-digit validation'
type: 'feature'
created: '2026-07-24'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
baseline_revision: '6462cf4'
final_revision: 'c9faf56'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** Story 2.1 stores a `GTIN` identifier as whatever raw string is handed in, so the four GTIN encodings (GTIN-8, UPC-A/12, EAN-13/13, GTIN-14) of one product land under different keys and never collide, and a mis-keyed value with a bad check digit can occupy — and thereby squat — a real product's GTIN slot (FR9, FR10, AD-7).

**Approach:** Add a pure `app/utils/gtin.py` (no Flask/DB) that check-digit-validates and normalizes any GTIN form to its canonical 14-digit, left-zero-padded key. Wire it into `CatalogService.add_identifier` so `GTIN` values are validated and stored normalized (making 2.1's existing `UNIQUE` constraint the shared-key guarantee), add a `GTIN_UNVALIDATED` identifier type that is stored as-entered and outside the GTIN namespace for rejected values, and add a normalized GTIN lookup so any encoded form resolves to the same Product.

## Boundaries & Constraints

**Always:**
- `app/utils/gtin.py` is a **pure** module: standard library only, no Flask/DB/app imports, no I/O — its failure signal is a plain `ValueError` subclass (`InvalidGtinError`). It is the single source of truth for GTIN validity, the mod-10 check digit, and the 14-digit key (AD-4, AD-7, NFR7). Mirror the existing pure-util style of `app/utils/location_validator.py`.
- Normalization = strip; require all-ASCII digits and a length in {8, 12, 13, 14}; left-zero-pad to 14; verify the GS1 mod-10 check digit over the padded 14 digits. Padding-then-fixed-weights is correct because leading zeros contribute nothing to the weighted sum. Normalization applies **only** to `GTIN` (FR9).
- In `add_identifier`, a `GTIN` value is normalized+validated before insert and the **normalized 14-digit** string is what is stored, snapshotted, and uniqueness-checked. A validation failure raises `ValidationError` (never a raw error) with a clear message that names the "store as GTIN_UNVALIDATED" option (FR10).
- `GTIN_UNVALIDATED` is a new `IdentifierType` member. It is **global** (NOT added to `VENDOR_SCOPED_IDENTIFIER_TYPES`) and is stored **exactly as entered** — never normalized, never check-digit-validated — so it lives outside the `GTIN` uniqueness namespace and can never block a later valid `GTIN` (FR10, AD-7, H4).
- All new mutation/query stays in `CatalogService`; the pure module holds no session. Preserve every 2.1 invariant (empty-string vendor sentinel, caught-`IntegrityError`→`ValidationError`, `IDENTIFIER_MAX_LENGTH` bounds, audit logging).

**Block If:**
- A GTIN form outside {8, 12, 13, 14} digits is required to be accepted (e.g. GSIN/SSCC-18) — that is beyond FR9's four forms; do not invent handling.

**Never:**
- No Alembic migration: the type is a plain `String` column by 2.1 design, so a new enum value needs no schema change. No `float`. No route/template/UI changes (the "store as unvalidated" choice is a service-level capability the caller selects by type; UI arrives in a later epic). No ASIN/internal-id/GS1 work (Stories 2.3–2.5). Do not normalize or check-digit-validate any type other than `GTIN`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| `normalize_gtin` — UPC-A | `'012345678905'` | returns `'00012345678905'` | — |
| `normalize_gtin` — GTIN-14 already | `'00012345678905'` | returns `'00012345678905'` (idempotent) | — |
| `normalize_gtin` — GTIN-8 valid | valid 8-digit GTIN (e.g. `'00012348'`) | returns its 14-digit left-padded key | — |
| `normalize_gtin` — bad check digit | `'012345678900'` | raises `InvalidGtinError` (message says check digit) | pure `ValueError` subclass |
| `normalize_gtin` — non-digit / wrong length | `'ABC123'`, `'1234567'` (7) | raises `InvalidGtinError` | pure `ValueError` subclass |
| `is_valid_gtin` | valid vs invalid inputs above | `True` / `False`, never raises | — |
| add `GTIN`, valid, any form | product A; UPC-A `'012345678905'` | row persists with `value=='00012345678905'`; snapshot shows normalized value | No error |
| add same product's GTIN-14 form to B | A has `'00012345678905'`; add `'00012345678905'` (or `'012345678905'`) to B | rejected — same normalized key | caught `ValidationError` naming A |
| add `GTIN`, bad check digit | product A; `'012345678900'` | rejected as a GTIN; message offers GTIN_UNVALIDATED | caught `ValidationError`, not `InvalidGtinError` |
| add `GTIN_UNVALIDATED` | product A; `'012345678900'` | persists as-entered (`value=='012345678900'`, not normalized) | No error |
| unvalidated does not block valid GTIN | A has `GTIN_UNVALIDATED` `'012345678900'`; add `GTIN` `'012345678905'` to B | both persist (different type/namespace) | No error |
| `find_product_id_by_gtin` resolves any form | A stored via GTIN-14; look up its UPC-A form | returns A's product id | returns `None` if unknown or input not a valid GTIN |

</intent-contract>

## Code Map

- `app/utils/gtin.py` — **NEW** pure module: `InvalidGtinError(ValueError)`, `compute_check_digit(data13: str) -> int`, `is_valid_gtin(value: str) -> bool`, `normalize_gtin(value: str) -> str`. Model on `app/utils/location_validator.py` (module-level pure functions, typed, docstrings).
- `app/models.py` — add `GTIN_UNVALIDATED = "GTIN_UNVALIDATED"` to `IdentifierType` (leave `VENDOR_SCOPED_IDENTIFIER_TYPES` unchanged → global scope).
- `app/mariadb_catalog_service.py` — `add_identifier`: after type/blank/length guards, if `itype is IdentifierType.GTIN` normalize via `gtin.normalize_gtin`, replacing `value` with the 14-digit key; on `InvalidGtinError` raise `ValidationError` offering the GTIN_UNVALIDATED path. Add `find_product_id_by_gtin(self, value) -> Optional[int]`. Import the `gtin` util.
- `tests/unit/test_gtin.py` — **NEW** exhaustive pure unit tests (the whole `normalize_gtin`/`is_valid_gtin`/`compute_check_digit` surface + the I/O matrix's pure rows).
- `tests/unit/test_catalog_service.py` — add GTIN-normalization/validation/lookup service tests; **fix existing 2.1 tests that used invalid GTIN values** (`test_add_each_type_persists`, `test_gtin_ignores_vendor_arg`, `test_non_string_value_coerced`, `test_get_identifiers_empty_and_ordered`) to use a valid GTIN and assert the normalized value, or switch the generic-behavior cases to a non-GTIN type.

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/gtin.py` — implement the pure module (`InvalidGtinError`, `compute_check_digit`, `is_valid_gtin`, `normalize_gtin`) per the Always rules; stdlib only, no app imports — the exhaustively-tested single source of truth for GTIN validity/normalization (FR9, FR10, AD-4/7, NFR7).
- [x] `app/models.py` — add `GTIN_UNVALIDATED` to `IdentifierType`; keep it out of `VENDOR_SCOPED_IDENTIFIER_TYPES` — global, quarantine namespace for check-digit-failing values (FR10, AD-7).
- [x] `app/mariadb_catalog_service.py` — normalize+validate `GTIN` in `add_identifier` (store the 14-digit key; bad value → `ValidationError` offering GTIN_UNVALIDATED); store `GTIN_UNVALIDATED` as-entered; add `find_product_id_by_gtin` (normalize input, query `identifier_type='GTIN'`, return `product_id` or `None`) — write/lookup both normalize so every form resolves to one Product (FR9, FR10).
- [x] `tests/unit/test_gtin.py` — exhaustive pure tests: each valid form normalizes to its 14-digit key; idempotent 14-digit; bad check digit, non-digit, and wrong-length rejected with `InvalidGtinError`; `is_valid_gtin` never raises; `compute_check_digit` matches known vectors.
- [x] `tests/unit/test_catalog_service.py` — GTIN service tests (normalized storage; cross-form duplicate rejected naming the conflict; bad check digit → `ValidationError` mentioning GTIN_UNVALIDATED; `GTIN_UNVALIDATED` stored as-entered; unvalidated does not block a later valid GTIN; `find_product_id_by_gtin` resolves an alternate form and returns `None` for misses) **and** repair the 2.1 GTIN tests noted in the Code Map so the suite stays green.

**Acceptance Criteria:**
- Given the pure `app/utils/gtin.py` module, when GTIN-8, UPC-A, EAN-13, and GTIN-14 forms of one product are normalized, then all yield the same 14-digit key and the module imports no Flask/DB (FR9, AD-4, NFR7).
- Given a `GTIN` value whose check digit is invalid, when it is added, then it is rejected with a caught `ValidationError` whose message offers storing it as `GTIN_UNVALIDATED`, and no `InvalidGtinError`/`IntegrityError` reaches the caller (FR10).
- Given a stored `GTIN_UNVALIDATED` value, when a later check-digit-valid `GTIN` normalizing to the same digits is added to another product, then it persists — the unvalidated value never blocked the namespace (FR10, AD-7).
- Given one form of a product's GTIN is stored, when another encoding of it is looked up via `find_product_id_by_gtin`, then it resolves to the same Product (FR9).
- Given `nox -s tests`, when the suite runs, then the new `test_gtin.py` and catalog GTIN tests pass and all pre-existing tests remain green.

## Review Triage Log

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1: (high 0, medium 0, low 1)
- defer: 0
- reject: 6
- addressed_findings:
  - `[low]` `[patch]` Pure-module contract hardening: `normalize_gtin` now raises `InvalidGtinError` (not a bare `AttributeError`) on non-str input, and `compute_check_digit` guards its input, so `is_valid_gtin` honors its documented "never raises" contract and the module's sole failure signal is always `InvalidGtinError` — matters because Epics 4/6 call this substrate directly. Added parametrized tests for non-str/None/malformed inputs across all three public functions.
  - Rejected (by-design / beyond captured spec / non-consequential): all-zeros GTIN accepted (passes the spec's defined validity = 4 lengths + valid mod-10 check digit; rejecting it is an extra rule beyond FR9/FR10, needs deliberate malformed input); integer-barcode leading-zero coercion into GTIN (GTIN values arrive as strings from routes/scanners; numeric representation is inherently lossy and the worst case is a false miss, not a wrong-product match — consistent with 2.1 rejecting str-coercion concerns); `GTIN_UNVALIDATED` whitespace-stripped (universal `.strip()` is pre-existing 2.1 behavior; "as entered" means not GTIN-normalized); a value coexisting as `GTIN` and `GTIN_UNVALIDATED` being invisible to GTIN lookup (spec-sanctioned AD-7/H4); the `not isinstance(..., InvalidGtinError)` test assertion being tautological (the no-raw-leak guarantee is already enforced by the enclosing `pytest.raises(ValidationError)`); the `existing is None` re-raise branch being untested (pre-existing 2.1 defensive code, unchanged by this story).

## Design Notes

**GS1 mod-10 over the padded 14 (golden example).** Zero-pad to 14 first, then apply fixed weights so the algorithm is uniform across all four forms:
```python
def compute_check_digit(data13: str) -> int:  # 13 digits, left of the check digit
    total = sum((3 if i % 2 == 0 else 1) * int(d)
                for i, d in enumerate(reversed(data13)))
    return (10 - (total % 10)) % 10
# normalize_gtin: s=value.strip(); require s.isdigit() and len(s) in {8,12,13,14};
# p=s.zfill(14); if compute_check_digit(p[:13]) != int(p[13]): raise InvalidGtinError(...)
# return p
```
Known-valid vector: UPC-A `012345678905` → `00012345678905` (check digit 5). Known-invalid: `012345678900`.

**Why no migration and why GTIN_UNVALIDATED is global.** 2.1 stores `identifier_type` as a plain `String(32)`, not a DB `ENUM`, expressly so new members need no schema change. `GTIN_UNVALIDATED` stays out of `VENDOR_SCOPED_IDENTIFIER_TYPES` (global) and is never normalized, so it shares no key space with `GTIN` — a garbage value can never squat a real GTIN slot, and the same digit string may coexist as both a quarantined `GTIN_UNVALIDATED` and a valid `GTIN` on different products.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — expected: all pass, including new `test_gtin.py` and the catalog GTIN tests; no pre-existing test regressed.
- `venv/bin/python -c "import ast,sys; ast.parse(open('app/utils/gtin.py').read())"` then inspect imports — expected: `app/utils/gtin.py` imports only the standard library (no `flask`, `sqlalchemy`, or `app.*`).

## Auto Run Result

Status: done

**Summary.** Added GTIN normalization + check-digit validation (FR9, FR10). A new **pure** `app/utils/gtin.py` (zero imports — verified by AST) is the single source of truth for GTIN validity, the GS1 mod-10 check digit, and the canonical 14-digit key; GTIN-8, UPC-A, EAN-13, and GTIN-14 forms of one product all normalize to the same key. `CatalogService.add_identifier` now normalizes+validates `GTIN` values (storing the 14-digit key, so 2.1's `UNIQUE` constraint becomes the shared-key guarantee) and surfaces a check-digit failure as a caught `ValidationError` that offers the new `GTIN_UNVALIDATED` type. `GTIN_UNVALIDATED` is global and stored as-entered — outside the GTIN namespace, so a garbage value can never squat a real GTIN slot and never blocks a later valid GTIN (AD-7/H4). `find_product_id_by_gtin` normalizes on lookup so any encoded form resolves to the same Product. No migration (the type column is a plain `String` by 2.1 design); no route/UI changes.

**Files changed.**
- `app/utils/gtin.py` — NEW pure module: `InvalidGtinError`, `compute_check_digit`, `normalize_gtin`, `is_valid_gtin`.
- `app/models.py` — added `GTIN_UNVALIDATED` to `IdentifierType` (kept out of `VENDOR_SCOPED_IDENTIFIER_TYPES` → global).
- `app/mariadb_catalog_service.py` — GTIN normalize/validate in `add_identifier` (bad value → `ValidationError` offering GTIN_UNVALIDATED); `GTIN_UNVALIDATED` stored verbatim; added `find_product_id_by_gtin`.
- `tests/unit/test_gtin.py` — NEW exhaustive pure tests (normalization, all-four-forms key unity, check-digit vectors, boundaries, non-str/None/malformed contract).
- `tests/unit/test_catalog_service.py` — added GTIN service tests (normalized storage, cross-form duplicate rejection, bad-check-digit → GTIN_UNVALIDATED offer, verbatim GTIN_UNVALIDATED, unvalidated-does-not-block-valid, `find_product_id_by_gtin`) and repaired the four pre-existing 2.1 tests that used invalid GTIN values.

**Review findings.** 1 patch applied (low: pure-module contract hardening — non-str/malformed input now fails as `InvalidGtinError`, honoring the module's "never raises" / single-failure-signal contract that Epics 4/6 rely on; +tests). 0 deferred. 6 rejected as by-design, beyond the captured FR9/FR10 validity rule, or non-consequential (all-zeros GTIN, integer leading-zero coercion, GTIN_UNVALIDATED whitespace strip, quarantine-invisible-to-lookup, a tautological test assertion already covered by `pytest.raises`, and a pre-existing untested defensive branch). No intent gaps, no spec repairs.

**Verification.** `nox -s tests`: **486 passed, 305 deselected** (green; +new GTIN tests, all pre-existing tests intact including the repaired 2.1 identifier tests). `app/utils/gtin.py` confirmed import-free via AST; module doctests pass. The `manage.py db upgrade` round trip is N/A — this story adds no migration (new enum value on a plain `String` column by 2.1 design).

**Residual risks.** (1) No live caller yet — `add_identifier(GTIN)` and `find_product_id_by_gtin` are exercised only by unit tests until a later epic wires UI/scan routing; the lookup substrate is intentionally GTIN-only (Epic 4 owns the general scan classifier). (2) The 2.1-deferred SQLite↔MariaDB collation parity is not a GTIN concern (GTIN keys are numeric, case-stable). (3) An all-zeros value is accepted as a valid GTIN (passes mod-10); flagged and rejected as beyond FR9/FR10 — revisit only if a real all-zeros mis-scan is observed.
