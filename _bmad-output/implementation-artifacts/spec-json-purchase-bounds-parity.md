---
title: 'JSON purchase endpoint enforces the same column bounds as the HTML purchase form'
type: 'bugfix'
created: '2026-07-26'
status: 'done'
baseline_revision: '53c20b5'
final_revision: '540b987'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `POST /api/products/<id>/purchases` (`api_record_purchase`, `app/main/routes.py:1635`) parses `unit_price` with `Decimal(str(...))` inside a `try` catching only `InvalidOperation`/`ValueError`, so `NaN`/`Infinity` answer 201 while storing NULL (DW-12); it also enforces none of the `Numeric(10, 2)` magnitude ceiling, the two-decimal scale rule, the non-negative rule, or the text-column length limits that `_parse_purchase_form` already applies to the very same `purchases` columns (DW-25).

**Approach:** Lift the unit-price rule and the text-length rule out of `_parse_purchase_form` into two shared helpers, and have both `_parse_purchase_form` and `api_record_purchase` call them, so the two entry points are written from one list rather than two hand-copied ones. The JSON side keeps its AD-13 envelope (`{success:false, error:{code, message, field}}`, HTTP 400) as the shape of the refusal.

## Boundaries & Constraints

**Always:**
- No new business rule: every bound already ships on the HTML side, whose behavior and messages must be unchanged — the existing `TestPurchaseFormRefusesWhatTheColumnCannotHold` tests pass untouched.
- Exactly one definition per rule: no duplicated bound literal, no duplicated message string.
- The JSON endpoint keeps accepting JSON *numbers* as well as strings for `unit_price` (`2.34` and `"2.34"` both work) — that is the shipped contract and the reason the parse is `Decimal(str(...))`.
- A refusal writes nothing: no Purchase row is created on any 400.
- Refusal shape stays per-entry-point: field-scoped message on a 200 re-render for HTML; `code='invalid_field'` + `field=<json field name>` + HTTP 400 for JSON.

**Block If:** Nothing. Every rule is already shipped and observable in `_parse_purchase_form`; no product decision is open.

**Never:**
- Do not touch `quantity` on the JSON side. The form's `_positive_int_string` rule takes a *string*, while the JSON contract accepts an int (`{'quantity': 5}`, exercised by `test_record_purchase_endpoint_creates_201`). Mirroring it would break that contract, and no ledger entry asks for it.
- Do not add the `received_date >= order_date` cross-field rule (DW-24) — a separate open ledger entry, not in this bundle.
- Do not change `CatalogService.record_purchase`; it deliberately validates nothing (`app/mariadb_catalog_service.py:1351`).
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`; the orchestrator records resolution.
- No schema/migration change. No new endpoint, no change to the 201 success body.

## I/O & Edge-Case Matrix

All rows are `POST /api/products/<existing id>/purchases` with a JSON body.

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Valid price, string or number | `{"unit_price": "2.34"}` / `{"unit_price": 2.34}` | 201, purchase stored with `2.34` | No error expected |
| Column-edge price | `{"unit_price": "99999999.99"}` | 201, stored exactly | No error expected |
| Non-finite | `unit_price` = `"NaN"`, `"nan"`, `"sNaN"`, `"Infinity"`, `"-Infinity"` | 400, nothing stored | `invalid_field`, `field='unit_price'`, "decimal number" message |
| Unparseable | `unit_price` = `"not-a-number"` | 400 (unchanged behavior), nothing stored | `invalid_field`, `field='unit_price'` |
| Negative | `unit_price` = `"-1.00"` | 400, nothing stored | `invalid_field`, `field='unit_price'`, "must not be negative" |
| Past the column | `unit_price` = `"100000000"`, `"1E+30"`, `"99999999999.99"` | 400, nothing stored | `invalid_field`, `field='unit_price'`, "less than 100000000" |
| Finer than the column | `unit_price` = `"0.005"`, `"1.234"`, `"1e-30"` | 400, nothing stored | `invalid_field`, `field='unit_price'`, "at most two decimal places" |
| Empty / absent price | `unit_price` absent, `null`, or `""` | 201, `unit_price` NULL (unchanged) | No error expected |
| Over-long text column | `vendor`/`vendor_sku`/`order_number` = 256 chars, or `source_url` = 1025 chars | 400, nothing stored | `invalid_field`, `field=` that column, "characters or fewer" |
| Text column at its limit | `vendor` = 255 chars, `source_url` = 1024 chars | 201, stored | No error expected |
| Non-string text value | `{"vendor": 5}` | Unchanged from today — the length rule does not apply to a non-string | No new error |

</intent-contract>

## Code Map

- `app/main/routes.py:1435-1443` -- `_PURCHASE_FIELD_LIMITS` (fed by `_RECEIPT_FIELD_LIMITS`, line 773), `_MAX_UNIT_PRICE`, `_UNIT_PRICE_STEP`: the bounds to share.
- `app/main/routes.py:1446-1525` -- `_parse_purchase_form`: the HTML rules, source of truth to extract from. Its docstring explains *why* each bound exists — keep that rationale with the extracted helpers.
- `app/main/routes.py:1635-1696` -- `api_record_purchase`: the endpoint to bring into parity. `_catalog_json_error` (line 1625) is the AD-13 envelope builder it keeps using.
- `app/mariadb_catalog_service.py:1339` -- `record_purchase`: validates nothing; why the route is the only gate.
- `tests/unit/test_product_routes.py:164-195` -- existing JSON-endpoint tests (201 path, 404 envelope, invalid price). `TestPurchaseFormRefusesWhatTheColumnCannotHold` (line 1813) holds the HTML expectations these JSON tests mirror.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- Extract two module-level helpers next to the purchase bounds: one that turns a raw unit price into `(Decimal, None)` or `(None, message)` applying, in order, parse → finite → non-negative → `< _MAX_UNIT_PRICE` → quantizes to `_UNIT_PRICE_STEP`; and one that returns the over-length message (or `None`) for a named text column from `_PURCHASE_FIELD_LIMITS`. Move the relevant rationale from `_parse_purchase_form`'s docstring onto them. -- One definition per rule is the point of the change; ordering matters because `quantize` is only safe once the magnitude is bounded.
- [x] `app/main/routes.py` -- Rewrite `_parse_purchase_form`'s price branch and length loop to call the helpers, leaving its `(values, errors)` contract, its messages and its date/quantity handling exactly as they are. -- Proves the helpers really are the HTML rules, not a second copy.
- [x] `app/main/routes.py` -- In `api_record_purchase`, check the four text columns' lengths and parse `unit_price` through the helpers, returning `_catalog_json_error('invalid_field', <message>, 400, field=<name>)` on the first failure, before any call to `service.record_purchase`. Leave `quantity` and the date parsing untouched. -- Closes DW-12 and DW-25 without widening the JSON contract.
- [x] `tests/unit/test_product_routes.py` -- Add a JSON-endpoint test class covering every I/O matrix row, asserting status, `error.code`, `error.field`, the message fragment, and that `get_purchases_for_product` is empty after each refusal. -- The matrix is the contract; nothing else pins the JSON side.

**Acceptance Criteria:**
- Given a product and any value the HTML purchase form refuses for `unit_price`, when it is POSTed to `/api/products/<id>/purchases`, then the response is 400 with an AD-13 error object naming `unit_price` and no Purchase row exists.
- Given a value either entry point accepts for `unit_price`, when it is submitted to the other entry point, then that one accepts it too — the two agree on every value in the matrix.
- Given a `vendor`, `vendor_sku`, `order_number` or `source_url` string longer than its column, when it is POSTed as JSON, then the response is 400 naming that field rather than a 500 from the write path.
- Given the existing HTML purchase-form and JSON-endpoint tests, when the suite runs, then they pass unmodified.

## Spec Change Log

## Review Triage Log

### 2026-07-26 — Review pass

- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 1, low 8)
- defer: 2: (high 0, medium 2, low 0)
- reject: 5: (high 0, medium 0, low 5)
- addressed_findings:
  - `[medium]` `[patch]` The JSON length check measured the RAW value while the service stores the `_clean`-stripped one, so `{"vendor": "x"*255 + " "}` was newly refused 400 where the HTML form accepts it and the column holds it — a fresh disagreement introduced by the change meant to remove disagreements. `_purchase_text_length_error` now measures `value.strip()`, pinned by `test_padding_is_not_counted_because_it_is_not_stored`.
  - `[low]` `[patch]` A whitespace-only `unit_price` string 400'd on the JSON side while the form reads it as "no price". Strings are stripped before the `None`/`''` gate in `api_record_purchase`; pinned by `test_a_whitespace_only_price_means_no_price_as_it_does_on_the_form`.
  - `[low]` `[patch]` `_purchase_unit_price` contained the literal `'Unit Price must be a decimal number.'` twice — the exact duplication the spec's "no duplicated message string" constraint forbids. Hoisted to one local.
  - `[low]` `[patch]` The new code comments claimed the two entry points "cannot disagree about what `purchases` will hold" while `quantity` still diverges by design. Scoped the claim to the columns the helpers govern and named `quantity` as the deliberate exception.
  - `[low]` `[patch]` `_purchase_unit_price`'s docstring claimed to be "the single definition of what `Purchase.unit_price` accepts" though it lives in the routes module and no service-layer writer (`record_amazon_purchase`) inherits it. Scoped to "both HTTP entry points" and the limit stated.
  - `[low]` `[patch]` The new test class's docstring asserted that every value the HTML class refuses is refused by the JSON endpoint — false for `quantity`. Corrected to the columns actually claimed.
  - `[low]` `[patch]` `_parse_purchase_form` iterates `_PURCHASE_FIELD_LIMITS` and indexed `values[name]`, so a column added to `_RECEIPT_FIELD_LIMITS` would turn every purchase-form POST into a `KeyError` 500. Changed to `values.get(name)` in the loop the diff already rewrote.
  - `[low]` `[patch]` `test_a_non_string_value_...` asserted only `status_code != 400`, which a 500 also satisfies; it now asserts 201 and a stored row. The at-the-limit test covered 2 of the 4 text columns and now covers all four.
  - `[low]` `[patch]` The scale rule silently narrowed the JSON contract for binary-float prices (`0.1 + 0.2` was stored as `0.30`, now 400). The behavior is what the intent contract's scale rule requires, so it was kept, documented in `_purchase_unit_price`, and pinned by `test_a_json_float_carrying_binary_repr_noise_is_refused`. Acceptance Criterion 2 was also only verified by two hand-copied test lists; a single `_UNIT_PRICE_VERDICTS` table is now driven through both entry points by `TestBothPurchaseEntryPointsAgreeOnUnitPrice`.

### 2026-07-26 — Review pass (follow-up)

- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 0, low 5)
- defer: 5: (high 0, medium 3, low 2)
- reject: 8: (high 0, medium 0, low 8)
- addressed_findings:
  - `[low]` `[patch]` The previous pass's `values.get(name)` traded a loud `KeyError` for a silent parity break: `values` was still built from a hand-copied `('vendor', 'vendor_sku', 'order_number', 'source_url')` tuple, so a column added to `_RECEIPT_FIELD_LIMITS` would be bounded by `api_record_purchase` (which reads the mapping) and neither parsed nor bounded by the form — a new divergence, in the opposite direction from the one this change closes. `values` is now built from `_PURCHASE_FIELD_LIMITS` itself, which makes both the `KeyError` and the drift impossible and removes the last hand-copied field list on the form side; the indexing is direct again.
  - `[low]` `[patch]` `_purchase_unit_price` refuses neither PEP 515 underscores nor non-ASCII numerals (`'1_0'` stores `10.00`, `'٥'` stores `5.00`) while `_positive_int_string` twenty lines away exists to refuse exactly those for `quantity` — and extracting the helper made that lenience a single shared definition, so both routes are now guaranteed lenient the same way. Tightening it would be a new business rule the intent contract forbids, and the two entry points do still agree, so the behavior is unchanged and the limit is now stated in the helper's docstring and ledgered (DW-89).
  - `[low]` `[patch]` The magnitude ceiling and the scale rule cover a gap only together: `99999999.995` passes `>= _MAX_UNIT_PRICE` as typed and quantizes to `100000000.00`, past the column, so it is the SCALE rule that refuses it. The docstring documented only the opposite dependency (bounding the magnitude protects `quantize`); it now records that relaxing the scale rule to round would reopen the overflow the ceiling exists to prevent, and `'99999999.995'` is pinned in `_UNIT_PRICE_VERDICTS`.
  - `[low]` `[patch]` `test_an_absent_or_empty_price_still_records_a_null` parameterized `{}` and then POSTed `dict(body, vendor='DigiKey')`, so the genuinely empty body — the input most likely to catch a `body.get` assumption — was never sent, and the injected `vendor` was asserted nowhere. The bodies are POSTed as written.
  - `[low]` `[patch]` `_UNIT_PRICE_VERDICTS` re-stated only values the per-endpoint class already asserted, so the table justified as the anti-drift mechanism carried none of the values the two entry points are most likely to diverge on. Added `'0.00'`, `'+2.34'`, `'  2.34  '` (both sides strip before parsing) and `'99999999.995'`.

## Design Notes

Shape of the shared rule (the order is load-bearing — `quantize` on an unbounded `Decimal` can itself raise, and `is_finite()` must come before any comparison):

```python
def _purchase_unit_price(raw):
    """`(price, None)`, or `(None, message)` refusing it. The bounds
    `Purchase.unit_price`'s `Numeric(10, 2)` column implies, applied by BOTH
    entry points that write it — see `_parse_purchase_form`."""
    try:
        price = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None, 'Unit Price must be a decimal number.'
    if not price.is_finite():
        return None, 'Unit Price must be a decimal number.'
    ...
```

The JSON envelope reuses the helper's human-readable message verbatim rather than restating a snake_case one; `error.field` already carries the machine name a client keys on, and a second message string is exactly the divergence this change exists to remove.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the pre-existing JSON and HTML purchase tests unmodified.

## Auto Run Result

Status: done

**Implemented change.** `POST /api/products/<id>/purchases` now applies the same `unit_price` and text-column bounds the HTML purchase form applies, from one definition rather than two hand-copied ones: `_purchase_unit_price` (parse -> finite -> non-negative -> under the `Numeric(10, 2)` ceiling -> exactly two decimal places) and `_purchase_text_length_error` (the four `_PURCHASE_FIELD_LIMITS` columns, measured on the stripped value the service actually stores). Both entry points call both helpers; the JSON side keeps its AD-13 refusal shape (`invalid_field` + `field` + HTTP 400) and the HTML side keeps its field-scoped re-render, unchanged. DW-12 (non-finite prices answering 201 while storing NULL) and DW-25 (no magnitude, scale, sign or length bound on the JSON side) are closed.

**Files changed.**
- `app/main/routes.py` -- two shared bound helpers extracted from `_parse_purchase_form`; the form's price branch and length loop now call them, and its text values are derived from `_PURCHASE_FIELD_LIMITS` rather than a restated tuple; `api_record_purchase` applies both before any write.
- `tests/unit/test_product_routes.py` -- a JSON-endpoint class covering every I/O matrix row (status, `error.code`, `error.field`, message fragment, and no stored row after each refusal), plus `_UNIT_PRICE_VERDICTS` driven through both entry points so the two cannot drift apart silently.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- five new entries (DW-86..DW-90) from this follow-up review; no existing entry touched.

**Review findings breakdown (follow-up pass).** 5 patches applied (all low: the last hand-copied field list removed and the silent-skip it enabled with it; two docstring limits recorded — `Decimal`'s spelling lenience and the ceiling/scale interdependence; the empty-body test row actually POSTed; four discriminating rows added to the drift table). 5 deferred (medium: JSON `quantity` still unbounded and still producing DW-25's generic 500; non-string text values bypassing the length rule into that same 500; `date.fromisoformat` accepting the whole ISO 8601 grammar both messages deny, so `"2026-W01-1"` records the wrong year. low: `Decimal`'s underscore/non-ASCII-numeral lenience on both entry points; a non-object JSON body answering a generic 500 rather than AD-13). 8 rejected, the largest being the JSON price message adopting the form's wording (an explicit Design Notes decision, and no consumer keys on the string), the ceiling message naming `100000000` rather than `99999999.99` (changing it would change the HTML messages the intent contract freezes), and the new tests' page-wide substring assertions and function-local `Decimal` imports (both the established convention of the sibling class in the same file).

**Follow-up review recommendation.** `false`. This pass changed no shipped behavior: one refactor that is byte-identical in effect today, two docstring additions, and two test improvements — all low-consequence and localized.

**Verification.** `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -> **2127 passed, 367 deselected** after the patches. The two purchase parity classes alone: 72 passed. The pre-existing `TestPurchaseFormRefusesWhatTheColumnCannotHold` and JSON-endpoint tests remain unmodified and green, which is Acceptance Criterion 4. Every reviewer claim acted on was re-verified directly rather than taken on report (`date.fromisoformat('2026-W01-1')` -> `2025-12-29`; `Decimal('1_0')` -> `10`; `Decimal('99999999.995').quantize(Decimal('0.01'))` -> `100000000.00`; `_PURCHASE_FIELD_LIMITS`'s key set identical to the tuple it replaced).

**Residual risks.** The five deferred entries are all reachable today on the JSON endpoint; DW-86 and DW-87 keep the generic 500 naming no field — DW-25's own symptom — alive for `quantity` and for non-string text values, and DW-88 can store a date in the wrong year from a string the refusal message says is not accepted. None was closable inside this spec's boundaries (`quantity` and the dates are on its Never list; the non-string row is stated as unchanged in its I/O matrix). The `quantity` overflow in DW-86 is invisible to the unit suite, which runs on SQLite: a green suite proves less than it appears to for that column.

