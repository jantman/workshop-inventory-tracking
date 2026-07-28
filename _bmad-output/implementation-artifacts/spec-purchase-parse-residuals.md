---
title: 'Purchase parse residuals: trigger on parsed values, normalize the stored price'
type: 'bugfix'
created: '2026-07-28'
status: 'done'
baseline_revision: '75d49cb'
final_revision: '39c88f5'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['multiple-goals', 'oversized']
---

<intent-contract>

## Intent

**Problem:** Two fail-open corners remain in the purchase parse helpers in `app/main/routes.py`. `_record_first_receipt` tests its trigger on the RAW stripped strings while the parse below it discards anything unusable, so `_record_first_receipt(svc, pid, {'quantity': 'abc'})` writes a Purchase whose only content is the server-defaulted `order_date` and reports success. `_purchase_unit_price` returns the value AS TYPED, so `-0`, `0.00E-99999999999999999` (`Decimal('0E-100000000000000001')`), `0E+5` and `1E+7` are all accepted and handed to the driver as `Decimal`s whose `str()` is not a shape a MySQL DECIMAL literal takes.

**Approach:** In `_record_first_receipt`, parse before testing the trigger and test it on the values that survived parsing, so an unusable-only receipt records nothing. In `_purchase_unit_price`, quantize the accepted value once and return the quantized form, resolving `-0` explicitly to positive `0.00`, so all three entry points store the same number. Rewrite the `_record_first_receipt` comment that DW-195 names as the current source of truth so it describes the closed hazard rather than the live one.

## Boundaries & Constraints

**Always:**
- `_RECEIPT_TRIGGER_FIELDS` keeps its current membership `('quantity', 'order_number')` and stays a subset of `_RECEIPT_FIELDS`; the guard keeps subscripting by name so a non-read trigger still raises `KeyError` loudly.
- `order_number` has no parse — its stripped string IS its parsed form; only `quantity` changes what the trigger sees.
- Declining on an unusable-only receipt stays SILENT (`return None`), matching the existing no-trigger behaviour.
- `_purchase_unit_price` keeps its existing refusal order (`is_finite` → negative → ceiling → scale) and every existing refusal message verbatim.
- `_purchase_unit_price` returns a `Decimal` quantized to exactly two places for every accepted value.

**Block If:**
- Closing either hole would require changing which fields trigger a receipt, or changing the accepted SPELLING of a price (underscores / non-ASCII numerals, DW-89).

**Never:**
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md` — the orchestrator records resolution.
- Do not widen or narrow `_RECEIPT_TRIGGER_FIELDS` (DW-193), and do not add a validation error for a receipt that declines.
- Do not move the price rule into the service layer, and do not touch `record_purchase`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Unusable quantity alone | `_record_first_receipt(svc, pid, {'quantity': 'abc'})` | Returns `None`; NO Purchase written | No error expected |
| Unusable quantity + real trigger | `{'quantity': 'abc', 'order_number': 'PO-1'}` | One Purchase, `quantity` NULL, `order_number` `'PO-1'` | No error expected |
| Unusable quantity + non-trigger | `{'quantity': 'abc', 'vendor': 'Acme'}` | Returns `None`; NO Purchase written | No error expected |
| Usable quantity | `{'quantity': '2'}` | One Purchase, `quantity` 2 | No error expected |
| Negative zero price | `unit_price='-0'` at any of the three entry points | Accepted; stored `Decimal('0.00')`, sign positive | No error expected |
| Zero with extreme exponent | `unit_price='0.00E-99999999999999999'` | Accepted; stored `Decimal('0.00')` | No error expected |
| Non-zero exponent form | `unit_price='1E+7'` | Accepted; stored `Decimal('10000000.00')` | No error expected |
| Still refused | `-0.001`, `1E-30`, `99999999.995`, `1E+30`, `NaN` | Refused with the existing message, unchanged | Existing field messages |

</intent-contract>

## Code Map

- `app/main/routes.py:1404-1462` (`_record_first_receipt`) -- the raw-string trigger test and the fail-open parse below it; also carries the DW-27 comment DW-195 flags as out of date.
- `app/main/routes.py:1195-1266` -- the `_RECEIPT_FIELDS` / `_RECEIPT_TRIGGER_FIELDS` comment block; unchanged in membership, may need a pointer to the new parse-order rule.
- `app/main/routes.py:1741-1817` (`_purchase_unit_price`, `_MAX_UNIT_PRICE`, `_UNIT_PRICE_STEP`) -- the price rule; the return at :1816 is what hands the un-normalized value out.
- `app/main/routes.py:990, 1444, 2031, 2272` -- the four call sites; three of them (:1444, :2031, :2272) write the column, :990 only reads the message.
- `app/mariadb_catalog_service.py:1850` (`record_purchase`) -- assigns the `Decimal` verbatim to `Purchase(unit_price=...)`; validates nothing. Read-only reference.
- `tests/unit/test_product_routes.py:2237` (`TestFirstReceiptOnCreate`), `:4253` (`_UNIT_PRICE_VERDICTS`), `:4282` (`TestBothPurchaseEntryPointsAgreeOnUnitPrice`) -- the suites the new cases extend.
- `tests/integration/conftest.py:438` (`integration_catalog_service`) -- the fixture a real-DECIMAL round-trip test builds on.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` (`_purchase_unit_price`) -- compute `quantized = price.quantize(_UNIT_PRICE_STEP)` ONCE, compare `price != quantized` for the scale refusal, and return the quantized value; return a positive `Decimal('0.00')` when it is zero (add a module constant `_ZERO_UNIT_PRICE = Decimal('0.00')` beside `_UNIT_PRICE_STEP`), so `-0` is a zero rather than a refusal. Update the docstring: replace the leniency paragraph's silence about these with the explicit decision, and note that the returned value is always two-place normalized so every caller stores the same number. -- one number per price, and a `str()` a DECIMAL literal takes.
- [x] `app/main/routes.py` (`_record_first_receipt`) -- move the `quantity` / `unit_price` parse ABOVE the trigger test and test the trigger on the parsed values (`order_number`'s stripped string is its parsed form); pass the same parsed values to `record_purchase`. -- an unusable-only receipt records nothing.
- [x] `app/main/routes.py` (`_record_first_receipt` docstring + inline comment) -- rewrite the DW-27 fail-open paragraph so it states the closed rule (trigger = a value that SURVIVED parsing) instead of the live quantity hazard, since DW-195 names this comment as the source of truth. -- the comment stops describing a hazard that no longer exists.
- [x] `tests/unit/test_product_routes.py` -- add a `TestFirstReceiptOnCreate` sibling class that calls `_record_first_receipt` DIRECTLY (the route validates first, so the hole is unreachable over HTTP) covering the four receipt rows of the I/O matrix; add the four new price rows to `_UNIT_PRICE_VERDICTS` / the create-form price suite so all three entry points are asserted to store the same normalized `Decimal`. -- pins both fixes at the level each is reachable.
- [x] `tests/integration/test_purchase_unit_price_decimal.py` -- new file: round-trip the normalized prices (`-0`, `0.00E-99999999999999999`, `1E+7`, `99999999.99`, `0`) through `integration_catalog_service.record_purchase` and read them back, asserting the real `Numeric(10, 2)` column accepts each and returns `Decimal('0.00')` / `Decimal('10000000.00')` / `Decimal('99999999.99')`. -- answers the question SQLite cannot.

**Acceptance Criteria:**
- Given a caller reaches `_record_first_receipt` with only unusable trigger content, when it runs, then it returns `None` and `get_purchases_for_product` reports zero purchases.
- Given a receipt whose trigger content survives parsing, when it runs, then exactly one Purchase is written with the same fields as before this change.
- Given `unit_price` values `-0`, `0.00E-99999999999999999`, `0E+5` and `1E+7`, when submitted to the create form, the `/purchases` form and `api_record_purchase`, then all three store the identical two-place `Decimal` and none is refused.
- Given every price the current `_UNIT_PRICE_VERDICTS` table refuses, when submitted, then it is still refused with the same message.
- Given `nox -s tests` and `nox -s doctests`, when run, then both pass with no new failures.

## Spec Change Log

## Review Triage Log

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 0, low 8)
- defer: 2: (high 0, medium 1, low 1)
- reject: 5
- addressed_findings:
  - `[low]` `[patch]` The `_RECEIPT_FIELDS` header comment still stated the removed rule ("the subset whose non-blankness decides whether there is a Purchase") 60 lines above its own correction — the exact stale-comment defect DW-195 was filed about. Rewritten to state the parse-survival rule and name DW-187.
  - `[low]` `[patch]` The guard tested parsed values by truthiness, which is correct only by accident (`_positive_int_string` never returns `0`) and would silently never fire for a trigger whose parsed form can be falsy, e.g. an accepted `Decimal('0.00')`. Changed to `all(parsed[name] in (None, '') ...)` with the reason stated.
  - `[low]` `[patch]` The `_RECEIPT_TRIGGER_FIELDS` note claimed the guard tests "the PARSED value" as a general rule, but `parsed` only puts `quantity` and `unit_price` through a helper. Narrowed to say which names have a parse and that adding a trigger that has one means adding it to the parse too.
  - `[low]` `[patch]` Nothing recorded that moving the parse above the guard makes `_purchase_unit_price` run on every priced create, which is safe only because both parse helpers are total. Stated at the call site.
  - `[low]` `[patch]` Three new prose passages quoted "Failed to record the purchase" as *the* operator message, but that string belongs to the purchase form alone — the create form says "its first receipt was not recorded" and the JSON endpoint returns a 500. Corrected in `_purchase_unit_price`'s docstring and the integration module docstring.
  - `[low]` `[patch]` The new receipt test class covered only `quantity='abc'`. Added `'0'` (which an ECIA `Q 0` record can actually supply), `'-1'` and `2147483648` — the values where "parsed successfully" and "truthy" could come apart.
  - `[low]` `[patch]` Dropping `-0`'s sign has exactly one observable effect — `Purchase.to_dict` renders the column with `float()`, so the JSON 201 body echoed `-0.0` — and nothing asserted it. Added `TestANegativeZeroPriceIsEchoedAsAZero`.
  - `[low]` `[patch]` `_UNIT_PRICE_VERDICTS`'s accepted sentinel changed from `None` to "is a `Decimal`", so a row still written the old way would take the refusal branch and die on `None.encode()`. Added a named assertion; also corrected a false rationale in the spelling property test's docstring.

### 2026-07-28 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 0, low 4)
- defer: 2: (high 0, medium 0, low 2)
- reject: 13
- addressed_findings:
  - `[low]` `[patch]` A new test comment justified the `quantity='0'` case by claiming an ECIA label's `Q 0` reaches the field via `_ecia_prefill`. It does not — `_ecia_prefill` copies `Q` only when `_positive_int_string` already accepts it, and that helper refuses `'0'`. Rewritten to state where `'0'` actually comes from and why it is pinned against the guard anyway.
  - `[low]` `[patch]` Both price tables covered only exponent spellings (`1E+7`, `0E+5`, `0.00E-99999999999999999`), missing the un-normalized spelling a real client actually sends: the scale rule is numeric, so `'2.3400'` is accepted and `str()` keeps four places. Added `('2.3400', Decimal('2.34'))`, which flows through `_STORABLE_PRICES` into all three suites.
  - `[low]` `[patch]` The table-hygiene assertion was hidden inside `TestBothPurchaseEntryPointsAgreeOnUnitPrice._product`, re-ran 34 times, and was narrower than the invariant it guarded — a row typo'd as a plain `str` still misrouted into the refusal branch. Moved to one `TestTheUnitPriceVerdictTableIsWellFormed` case checking `isinstance(verdict, (Decimal, str))`; the factory makes products again.
  - `[low]` `[patch]` `TestTheCreateFormStoresTheSameNormalizedPrice`'s docstring implied it would catch a create form that stored a non-normalized price, but its readback is SQLite, which re-spells the column — removing the helper's `quantize` leaves every case green. Docstring corrected to claim the number and the parity, and to name where the spelling is actually pinned.

## Design Notes

The price fix is one edit, not two: the scale check ALREADY calls `quantize`, so reusing its result removes a double call and normalizes at the same time. Quantize cannot raise here — the checks above bound the value to `[0, 100000000)`, which is the ordering the docstring already declares load-bearing.

```python
    if price >= _MAX_UNIT_PRICE:
        return None, f'Unit Price must be less than {_MAX_UNIT_PRICE}.'
    quantized = price.quantize(_UNIT_PRICE_STEP)
    if price != quantized:
        return None, 'Unit Price must have at most two decimal places.'
    # `-0` is not negative, so it reaches here; it is a zero, and `quantize`
    # keeps the sign (`Decimal('-0.00')`), so the sign is dropped explicitly.
    return (_ZERO_UNIT_PRICE if quantized == 0 else quantized), None
```

The receipt fix must not let the price parse become a trigger: `unit_price` is not in `_RECEIPT_TRIGGER_FIELDS`, so parsing it earlier changes nothing but the order of two pure calls.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass, including the new cases.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (docstrings edited in this change carry no `>>>` examples, and `routes.py` is outside the doctest path either way).
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s integration` -- expected: pass. Requires Docker for the MariaDB testcontainer; if the daemon is unavailable, record that the new integration test was written but not executed rather than deleting it.


## Auto Run Result

Status: done

**Implemented change.** Unchanged from the first run, and re-confirmed here: `_record_first_receipt` parses `quantity` and `unit_price` BEFORE testing the trigger and tests the trigger on what survived, so a receipt whose only trigger content is unusable records nothing instead of writing a Purchase carrying only the server-defaulted `order_date` and reporting success; `_purchase_unit_price` quantizes once — reusing the same `Decimal` as both the scale test and the returned value — and resolves `-0` to a positive `Decimal('0.00')`, so all three entry points that write the column store one number with one spelling. This follow-up review pass changed no application code: `app/main/routes.py` is byte-identical to the previous run's final revision, and all four patches landed in the unit suite.

**Files changed in this pass.**
- `tests/unit/test_product_routes.py` — corrected a false provenance claim about ECIA `Q 0`; added the `'2.3400'` row (the realistic un-normalized spelling both tables were missing); moved the table-hygiene assertion out of the product factory into `TestTheUnitPriceVerdictTableIsWellFormed` and widened it to the actual invariant; corrected `TestTheCreateFormStoresTheSameNormalizedPrice`'s docstring, which claimed coverage its SQLite readback cannot provide.
- `_bmad-output/implementation-artifacts/deferred-work.md` — two new entries appended (DW-220, DW-221); no existing entry read, modified or re-opened.

**Review findings.** Two independent reviewers (adversarial + edge-case) produced 19 distinct findings. 4 patched (all low, all in the test tier: 2 comment/docstring corrections, 1 missing test case, 1 assertion relocation). 2 deferred — DW-220 (the refused half of the price rule is still two hand-maintained tables while the accepted half is now derived) and DW-221 (`_record_first_receipt` drops an unstorable price with no log line, the one fail-open corner left). 13 rejected: the "unreachable over HTTP" objections (already the spec's stated residual risk, and the reason the new class calls the helper directly), the prose-volume and duplication objections (this file's established style), integration cases with no discriminating power (deliberate boundary/parity rows), `_ZERO_UNIT_PRICE` not deriving its scale from `_UNIT_PRICE_STEP` (the constant is named for readability and documented as such), the double parse of `unit_price` per create POST (one shared helper, negligible cost), and one duplicate of the already-filed DW-218.

Two reviewer claims were checked against the code before triage and are the basis for two of the patches: `_ecia_prefill` gates on `_positive_int_string(fields.get('Q')) is not None`, so a `Q 0` record never reaches the quantity field; and `Decimal('2.3400')` equals its own quantize, so it is accepted by the scale rule with `str()` still four places.

**Verification.** `nox -s tests` 3364 passed / 2 skipped (up 6 from 3358: the new hygiene case plus the `'2.3400'` row across all three price suites). `nox -s doctests` 22 passed. `nox -s integration` 43 passed in 6m23s against a real MariaDB 11.8 testcontainer, including the 5 unit-price round-trips. `git diff app/main/routes.py` is empty against the previous final revision, confirming the reviewers' source mutations were fully restored before these runs.

**Residual risks.** Unchanged from the first run and unmitigated by this pass: the receipt fix is unreachable over HTTP, since `_validate_product_create_form` refuses these values before `product_add` commits, so it is defence-in-depth on a second gate pinned by direct calls rather than by route tests. One reviewer measured that reverting `_purchase_unit_price`'s normalization leaves every route-level test green — the unit tier reads through SQLite, which re-spells the column — so the normalization is pinned only on the helper's own return and by the single integration row `'0.00E-99999999999999999'`; that limitation is now stated in the docstrings rather than implied away. DW-218 (an over-long `order_number` triggering a receipt MariaDB then refuses whole) remains the nearest open corner of the same shape, with DW-221 beside it.
