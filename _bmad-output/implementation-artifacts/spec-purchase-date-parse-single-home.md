---
title: 'One shared parse for the purchase date columns (DW-88, DW-191)'
type: 'bugfix'
created: '2026-07-28'
status: 'done'
baseline_revision: '7d30b7d'
final_revision: 'd284267'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `order_date`/`received_date` are the last purchase columns whose FORMAT rule is written twice. `_parse_purchase_form` strips then calls `date.fromisoformat(raw_date)` (`app/main/routes.py:1937`); `api_record_purchase._parse_date` calls `date.fromisoformat(str(value))` with no strip (`:2211`). So `' 2026-01-01 '` is a 302 and a stored row through the form and a 400 through the endpoint, the JSON integer `20260101` is silently coerced and stored, and on both sides `date.fromisoformat` accepts the whole ISO 8601 grammar the `YYYY-MM-DD` message says it does not — `'2026-W01-1'` records a purchase in 2025. The two refusal sentences also differ (`'Order Date must be an ISO date (YYYY-MM-DD).'` vs `'order_date must be an ISO date (YYYY-MM-DD)'`).

**Approach:** Give the pair the same seam `unit_price` and the four text columns already have: one `_purchase_date` helper beside `_purchase_unit_price` / `_purchase_text_length_error` / `_purchase_date_order_error` that strips, accepts only a `YYYY-MM-DD` calendar date, and returns the one human-labelled message both entry points then use verbatim. Wire both call sites to it.

## Boundaries & Constraints

**Always:**
- The helper is the single definition of the format rule; neither entry point may keep a `date.fromisoformat` call or a second message string of its own.
- The refusal message keeps its current wording — `f'{label} must be an ISO date (YYYY-MM-DD).'` — because the fix is to make the RULE match the message, not to restate the message. The JSON endpoint reuses that human-labelled sentence verbatim and keeps the machine name in AD-13's `field`, exactly as it already does for `_purchase_text_length_error` and `_purchase_unit_price` (see the comment at `routes.py:2126-2141`).
- Absent stays absent on both sides: `None`, `''` and a whitespace-only string all mean "no date given" and are not refusals.
- The format check must run before `_purchase_date_order_error`, so a malformed date still reports only its own format message (`TestAMalformedDateIsNeverAlsoCalledOutOfOrder` pins this on both sides).
- ASCII-only, zero-padded, exactly `YYYY-MM-DD`. Rejecting the wider grammar must not depend on `re` (not imported in this module) or on `strptime`, whose `%Y`/`%m`/`%d` match Unicode digits and unpadded numbers.

**Block If:** nothing — the rule, the message and the precedent are all already decided in the ledger entries and the existing helpers.

**Never:**
- Do not touch the `received_date >= order_date` ordering rule (`_purchase_date_order_error`, DW-24 — already decided).
- Do not change what a blank `order_date` does (the service defaults it to today — DW-192).
- Do not touch `quantity`, `unit_price`, the text columns, or `_parse_date_from_form` (`routes.py:4950`, the unrelated inventory-item path).
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.
- Do not widen the change into `record_amazon_purchase` or the service layer; `record_purchase` validates nothing by design and the two HTTP routes are the gates.

## I/O & Edge-Case Matrix

Applies identically to `order_date` and `received_date`, and identically through both entry points (form: 302 + stored row, or 200 re-render with the message on that field's control and nothing written; JSON: 201 + stored row, or 400 `invalid_field` with the same message and `field` = the column, nothing written).

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Calendar date | `'2026-01-01'` | Accepted, stored `2026-01-01` | No error expected |
| Padded (DW-191) | `' 2026-01-01 '` | Accepted on BOTH sides, stored `2026-01-01` | No error expected |
| Absent | `None`, `''`, `'   '` | Treated as no date on BOTH sides; no refusal | No error expected |
| Week date (DW-88) | `'2026-W01-1'` | Refused on both sides; nothing stored | `<Label> must be an ISO date (YYYY-MM-DD).` |
| Basic format | `'20260101'` | Refused on both sides | same message |
| JSON integer | `20260101` (int, not str) | Refused; no `str()` coercion | same message |
| Unpadded | `'2026-1-1'` | Refused | same message |
| Impossible day | `'2026-02-30'` | Refused | same message |
| Non-ASCII numerals | `'٢٠٢٦-٠١-٠١'` | Refused | same message |
| Free text | `'nope'`, `'07/01/2026'` | Refused | same message |
| Malformed + out of order | `order_date='nope'`, `received_date='2026-01-01'` | Only the format message, filed against `order_date` | Ordering rule not reached |

</intent-contract>

## Code Map

- `app/main/routes.py:1723-1949` -- the shared purchase helpers (`_PURCHASE_FIELD_LIMITS`, `_purchase_unit_price`, `_purchase_text_length_error`, `_purchase_date_order_error`) and `_parse_purchase_form`, whose date loop is at `:1931-1939`. The new helper belongs in this block, after `_purchase_text_length_error` and before `_purchase_date_order_error`.
- `app/main/routes.py:2061-2226` -- `api_record_purchase`; the nested `_parse_date` at `:2207-2213` and its two call sites at `:2215-2220`, plus the boundary comment at `:2126-2141` that names DW-88 as the one rule still unshared.
- `tests/unit/test_product_routes.py:4248-4326` -- `_UNIT_PRICE_VERDICTS` + `TestBothPurchaseEntryPointsAgreeOnUnitPrice`: the verdict-table idiom to copy (one module-level table, class-level `parametrize`, mirror `test_the_html_form` / `test_the_json_endpoint`).
- `tests/unit/test_product_routes.py:4328-4433` -- `_DATE_ORDER_VERDICTS` + `TestBothPurchaseEntryPointsAgreeOnDateOrder`; the comment at `:4335-4340` and the docstring at `:4360-4366` both explain the absence of a padded row, which this change removes the reason for. `_form_controls` (`:20`) is how the form side asserts the message lands on the right control.
- `tests/unit/test_product_routes.py:2851-2861` -- the older per-form format cases (`'07/01/2026'`, `'tomorrow'`), which must keep passing.
- `docs/user-manual.md:1409-1411` -- already promises "Both dates must be written `YYYY-MM-DD`; anything else is refused with `<Field> must be an ISO date (YYYY-MM-DD).`" — no doc change needed; this change makes that sentence true of the code.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- add `_PURCHASE_DATE_LABELS = {'order_date': 'Order Date', 'received_date': 'Received Date'}` and `_purchase_date(name, value)` returning `(date|None, message|None)` beside the other purchase helpers -- one definition of the format rule, keyed the way `_purchase_text_length_error` is keyed, so the label mapping cannot drift from the columns.
- [x] `app/main/routes.py` -- rewrite the `_parse_purchase_form` date loop (`:1931-1939`) to iterate `_PURCHASE_DATE_LABELS` and call the helper; delete its inline `date.fromisoformat`, its `try/except` and its message literal -- the form's stripping and its label wording survive inside the helper.
- [x] `app/main/routes.py` -- delete the nested `_parse_date` in `api_record_purchase` (`:2207-2213`) and call `_purchase_date` at both sites, returning `_catalog_json_error('invalid_field', message, 400, field=name)` -- the endpoint's second message string and its unstripped `str(value)` coercion both go away; update the `:2126-2141` comment so it no longer says the format rule is unshared.
- [x] `app/main/routes.py` -- update `_purchase_date_order_error`'s docstring (`:1856-1862`) and `_parse_purchase_form`'s (`:1886-1888`), which currently record DW-88/DW-191 as open and the format rule as the one thing not shared.
- [x] `tests/unit/test_product_routes.py` -- add `_DATE_FORMAT_VERDICTS` + `TestBothPurchaseEntryPointsAgreeOnDateFormat` covering every I/O matrix row for both `order_date` and `received_date` through both entry points, in the `_UNIT_PRICE_VERDICTS` idiom -- the anti-drift device the pair has never had.
- [x] `tests/unit/test_product_routes.py` -- add the padded row `(' 2026-01-01 ', ' 2026-01-05 ', None)` to `_DATE_ORDER_VERDICTS` and rewrite the comment at `:4335-4340` and the class docstring at `:4360-4366` that explain its absence -- DW-191 names this row as the thing to add once the parse is shared. `_assert_stored` compares against `date.fromisoformat(order_date)`, so it must strip too.

**Acceptance Criteria:**
- Given a purchase form POST and an equivalent JSON POST carrying the same `order_date` value, when the value is any row of the I/O matrix, then both entry points reach the same verdict and, on refusal, the same message text against the same field.
- Given the JSON endpoint refuses a date, when the response is read, then `error['code'] == 'invalid_field'`, `error['field']` is `order_date`/`received_date` (the machine name), and `error['message']` is the human-labelled sentence — the same string the form renders.
- Given `grep -n 'fromisoformat' app/main/routes.py`, when the two purchase entry points are inspected, then neither contains a date parse of its own; the only date parse for these two columns is inside `_purchase_date`.
- Given an out-of-order but padded pair through either entry point, when it is POSTed, then it is refused by the ordering rule (`must not be earlier than`) rather than by a format error — the strip happens before the comparison.

## Spec Change Log

_Empty: no `bad_spec` finding was raised, so the spec was never amended and the code was never re-derived._

## Review Triage Log

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 2, low 6)
- defer: 2: (high 0, medium 1, low 1)
- reject: 5
- addressed_findings:
  - `[medium]` `[patch]` `_PURCHASE_DATE_LABELS`'s comment claimed a third date column could not be parsed without a label, but only `_parse_purchase_form` iterated the mapping — `api_record_purchase` hardcoded both names. The endpoint now loops the mapping, as it already does for `_PURCHASE_FIELD_LIMITS`, so the claim holds on both sides; judging order is unchanged (insertion order).
  - `[medium]` `[patch]` `'   '` became an accepted "no date" on the JSON side in this change, which newly lets `{"order_date": "   ", "received_date": "2020-01-01"}` store a row whose received date precedes the defaulted order date — the one place the new absence rule meets the ordering rule, and it was pinned by nothing. Added `('   ', '2020-01-01', None)` to `_DATE_ORDER_VERDICTS`.
  - `[low]` `[patch]` `_purchase_date`'s docstring claimed `'2026-01-01T00:00:00'` parses and lands on the day meant; it raises. Rewritten to separate the values the `except` refuses from the three the round-trip comparison refuses, and to say which group a change to the function must be tested against.
  - `[low]` `[patch]` `_DATE_FORMAT_VERDICTS` filed that same row under the "all of these PARSE" comment, so it covered a branch it does not reach. Moved to the never-parsed group and both comments corrected.
  - `[low]` `[patch]` The label lookup sat after the `None` guard, so an unmapped column name passed silently when omitted and raised `KeyError` (a 500 outside the AD-13 envelope) when supplied. Hoisted above it, matching `_purchase_text_length_error`.
  - `[low]` `[patch]` The docstring's "breaking change" paragraph named only the message string. It now names the four value-level verdict flips (`20260101`, `'20260101'`, `'2026-W01-1'` 201→400; `'   '` 400→201) and `ApiClient.record_purchase`, which forwards a caller's dict verbatim.
  - `[low]` `[patch]` `_assert_stored` began calling `.strip()` on raw table entries, so a `None` row — the spelling the sibling table thirty lines above uses — would die as `AttributeError` inside the helper. Now `(x or '').strip()`.
  - `[low]` `[patch]` The `('0999-01-01', 'stored')` row read as an endorsement of a value MariaDB cannot store. It now says it pins the parse, not the value, and points at the deferral.

### 2026-07-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 0, low 3)
- defer: 2: (high 0, medium 1, low 1)
- reject: 13
- addressed_findings:
  - `[low]` `[patch]` `_purchase_date`'s docstring and the `_DATE_FORMAT_VERDICTS` row comment both claimed a year under 1000 "is green here and a generic `server_error` in production". Measured against `mariadb:11.8` under the default `STRICT_TRANS_TABLES`: `'0999-01-01'` and `'0001-01-01'` insert into a `DATE` column with no error and no warning and round-trip unchanged. The `1000-01-01` floor is the DOCUMENTED supported range, not an enforced one. Both copies now say so and cite the measurement; the third copy, DW-214, is flagged by the new DW-216 rather than rewritten.
  - `[low]` `[patch]` The comment above `api_record_purchase`'s date loop claimed the mapping makes a new date column "parsed by BOTH entry points or by neither" and that two hand-written calls "would leave the form iterating the mapping while this route ignored the new one and wrote NULL" — inverted, since the `record_purchase` call below names `order_date`/`received_date` individually and would drop a third column regardless. Rewritten to state what the loop actually buys (one judged column set on both sides) and to name the three places an addition must touch.
  - `[low]` `[patch]` The same comment's "insertion order is the judging order, so `order_date` still answers first" was pinned by nothing — every existing case sends at most one bad date, so reversing the mapping literal left the suite green. Added `TestTheJsonEndpointJudgesTheDatesInMappingOrder`: both dates malformed answers 400 against `order_date` on the endpoint, and comes back with both messages on their own controls through the form.

## Design Notes

The grammar check needs no regex and no new import: parse with `date.fromisoformat`, then require the result to print back as what was given.

```python
text = value.strip()
try:
    parsed = date.fromisoformat(text)
except ValueError:
    return None, message
# `date.isoformat()` is always exactly zero-padded `YYYY-MM-DD`, so equality
# with the input is the whole rule: `'20260101'` and `'2026-W01-1'` parse but
# print back as something else, and no other spelling can round-trip.
if parsed.isoformat() != text:
    return None, message
```

Verified against 3.13: `'2026-W01-1'` → `2025-12-29`, `'20260101'` → `2026-01-01`, `'2026-W01'` → `2025-12-29` (all round-trip-rejected); `'0999-01-01'`, `'0001-01-01'`, `'9999-12-31'` round-trip and stay accepted; `'2026-1-1'`, `'٢٠٢٦-٠١-٠١'`, `'2026-02-30'`, `'2026-01-01T00:00:00'` already raise.

A non-`str` value is refused rather than coerced: `str(value)` is what let the JSON integer `20260101` through, and a JSON number is not a date in any spelling. Absence is decided before the type check so `None` still means "no date".

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: green, including the two new/extended verdict tables.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: green (no doctests are added; `nox -s doctests` covers `app/utils/` only, so no `>>>` examples belong in `routes.py`).
- `grep -n 'fromisoformat' app/main/routes.py` -- expected: no hit inside `_parse_purchase_form` or `api_record_purchase`.

## Auto Run Result

Status: done

**Implemented change.** `order_date` and `received_date` now reach one parse, `_purchase_date`, from both HTTP entry points. It strips, accepts only a zero-padded ASCII `YYYY-MM-DD` calendar date (enforced by requiring `date.fromisoformat`'s result to print back as what was given — no regex, no `strptime`), refuses a non-`str` rather than coercing it, and returns the one human-labelled sentence both sides render. `None`, `''` and whitespace-only all mean "no date" on both sides. The form's inline `try`/`except` and the endpoint's nested `_parse_date` are both gone.

**Files changed.**
- `app/main/routes.py` — added `_PURCHASE_DATE_LABELS` and `_purchase_date`; rewired `_parse_purchase_form`'s date loop and `api_record_purchase`'s two call sites to the helper; updated the boundary comment and three neighbouring docstrings that recorded DW-88/DW-191 as open.
- `tests/unit/test_product_routes.py` — added `_DATE_FORMAT_VERDICTS` + `TestBothPurchaseEntryPointsAgreeOnDateFormat` (every I/O-matrix row × both columns × both entry points), `TestTheJsonEndpointJudgesTheDatesInMappingOrder`, and the padded/whitespace rows to `_DATE_ORDER_VERDICTS`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended DW-216 and DW-217 (new entries only; existing entries untouched).

**Review findings, this pass.** 3 patches applied (all low, all listed in the triage log): the false MariaDB pre-1000 claim in two files, the inverted extensibility claim on the endpoint's date loop, and an untested judging-order claim now pinned by a test. 2 deferred as new ledger entries — DW-216 (medium: DW-214's premise is empirically false, and its proposed `1000 <= year` guard would refuse storable values) and DW-217 (low: `_PURCHASE_DATE_LABELS` is not the extension point it reads as). 13 rejected, chiefly items already covered by existing ledger entries (DW-211's `quantity` whitespace asymmetry, DW-215's missing API reference), items the intent contract explicitly scopes out (the refusal wording, `record_amazon_purchase`, `_parse_date_from_form`), and test/docstring style matching the sibling helpers.

**Verification.**
- `nox -s tests` — green: 3308 passed, 2 skipped, 451 deselected. (Up 2 from the previous pass's 3306; the 2 skips are the JSON-integer row, which has no HTML form spelling.)
- `nox -s doctests` — green: 22 passed.
- `grep -n 'fromisoformat' app/main/routes.py` — two hits, both inside `_purchase_date` (one in its docstring, one at the parse). Neither entry point carries a parse of its own.
- MariaDB claim checked empirically against `mariadb:11.8` in a throwaway container under default `STRICT_TRANS_TABLES`, as recorded in DW-216. Container removed.

**Residual risks.**
- The JSON endpoint's shipped contract changed: `20260101` (integer), `'20260101'` and `'2026-W01-1'` went 201→400, `'   '` went 400→201, and both date refusal strings gained a label and a period. `ApiClient.record_purchase` forwards caller dicts verbatim, so an integration is affected without changing a line. Those flips are the defect being closed, but there is no reference document to carry them to a caller — DW-215.
- No integration coverage against a real MariaDB for either purchase entry point; the unit suite is SQLite. That gap is what allowed a false claim about backend behaviour to sit in three files — see DW-216.

