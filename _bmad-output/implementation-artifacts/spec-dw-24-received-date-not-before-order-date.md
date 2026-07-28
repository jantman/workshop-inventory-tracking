---
title: 'A Purchase may not be received before it was ordered'
type: 'feature'
created: '2026-07-27'
status: 'done'
baseline_revision: '71c8ddf'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '46d110e'
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `_parse_purchase_form` (`app/main/routes.py:1835`) and `api_record_purchase` (`app/main/routes.py:1999`) each validate `order_date` and `received_date` for ISO format independently and never compare them, so both entry points record a Purchase received before it was ordered. `CatalogService.record_purchase` validates nothing (`app/mariadb_catalog_service.py:1533`), so these two routes are the only gates. DW-24 deferred this as a new business rule rather than a column constraint; the human has since decided it (2026-07-26, option 1).

**Approach:** Add one cross-field rule — when both dates are present, `received_date` must not precede `order_date` — as a third shared helper beside `_purchase_unit_price` and `_purchase_text_length_error`, applied by both entry points. Follow that established pattern exactly: the helper returns a message string only, and each entry point owns the shape of its refusal.

## Boundaries & Constraints

**Always:**
- Exactly one definition of the rule and one message string, called from both `_parse_purchase_form` and `api_record_purchase`. No duplicated comparison, no second message.
- The helper returns `None` when the pair is acceptable, else the message string — never a response object, never a field name. This mirrors `_purchase_text_length_error` and is why the two refusal shapes can differ.
- Refusal is scoped to `received_date` on both sides: a field-scoped message under `errors['received_date']` on the HTML side (200 re-render), and `_catalog_json_error('invalid_field', message, 400, field='received_date')` on the JSON side.
- Equal dates are accepted — the rule is "must not precede", not "must follow".
- A refusal writes nothing: no Purchase row on any rejection.
- The check runs only on two successfully parsed `date` values, after both dates are parsed, so a malformed date still reports its own format message and is never also reported as out of order.
- The HTML form keeps accumulating errors (no early return); the JSON endpoint keeps first-failure-wins with the cross-field check last, after the two format checks.
- Message style follows the shared helpers: label-cased fields, trailing period.

**Block If:** Nothing. The rule is decided verbatim in the ledger; scope, both entry points, and both refusal shapes are named.

**Never:**
- Do not touch the partial cases. Either date NULL is accepted unchanged — including a `received_date` with no `order_date`, even though `record_purchase` then defaults `order_date` to `date.today()` (`app/mariadb_catalog_service.py:1563`) and can store a row where received precedes order. The decision says partial cases stay untouched; replicating that default in the route would be a rule the human did not choose.
- Do not change `CatalogService.record_purchase` or `record_amazon_purchase`; the service deliberately validates nothing.
- Do not touch `_record_first_receipt` (`app/main/routes.py:1358`). `_RECEIPT_FIELDS` (`app/main/routes.py:1217`) carries no date field at all, so the rule has nothing to apply to there.
- Do not alter the existing ISO-format messages, the unit-price rules, the text-length rules, or `quantity` on either side. Existing tests for those must pass untouched.
- No schema or migration change; no new endpoint; no change to the 201 success body or the 302 redirect.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`; the orchestrator records resolution.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Received after ordered | `order_date='2026-01-01'`, `received_date='2026-01-05'` | Purchase written. HTML 302; JSON 201 | No error expected |
| Received same day as ordered | `order_date='2026-01-01'`, `received_date='2026-01-01'` | Purchase written. HTML 302; JSON 201 | No error expected |
| Received before ordered | `order_date='2026-01-05'`, `received_date='2026-01-01'` | No Purchase written | HTML: 200 re-render, message under `received_date`; JSON: 400, `code='invalid_field'`, `field='received_date'`, same message |
| Only `order_date` given | `order_date='2026-01-05'`, `received_date` absent/blank | Purchase written (partial case untouched) | No error expected |
| Only `received_date` given | `order_date` absent/blank, `received_date='2020-01-01'` | Purchase written; service defaults `order_date` to today (partial case untouched) | No error expected |
| Neither date given | both absent/blank | Purchase written | No error expected |
| Malformed `order_date`, valid `received_date` | `order_date='nope'`, `received_date='2026-01-01'` | No Purchase written | Only the ISO-format message for `order_date`; the cross-field rule does not fire on an unparsed date |
| JSON non-string date value | `order_date=20260105` (JSON number) | Unchanged from today: `str(...)` then `date.fromisoformat` → 400 format error | Existing behavior, not re-specified here |

</intent-contract>

## Code Map

- `app/main/routes.py:1691-1781` -- `_purchase_unit_price` / `_purchase_text_length_error`: the two existing shared purchase helpers. The new helper goes beside them, above `_parse_purchase_form`, and copies their return contract.
- `app/main/routes.py:1784-1845` -- `_parse_purchase_form`: date loop at 1835-1843, `return values, errors` at 1845. The cross-field check goes between them.
- `app/main/routes.py:1848-1897` -- `purchase_add`: renders field-scoped errors via the `_render` closure; `product/purchase_add.html` already has an `invalid_feedback` slot for `received_date` (lines 51/54), so no template change is needed.
- `app/main/routes.py:1945-1953` -- `_catalog_json_error`: the AD-13 envelope builder.
- `app/main/routes.py:1957-2037` -- `api_record_purchase`: `_parse_date` closure at 1999-2005, both dates parsed at 2007-2012. The cross-field check goes after 2012, before the `record_purchase` call at 2014.
- `app/mariadb_catalog_service.py:1533-1584` -- `record_purchase`: validates nothing; documents that parsing is the route's job. Read-only reference.
- `tests/unit/test_product_routes.py:2976` -- `TestPurchaseFormRefusesWhatTheColumnCannotHold`: HTML-side bounds tests; style reference.
- `tests/unit/test_product_routes.py:3099` -- `TestRecordPurchaseEndpointHoldsTheSameColumnBounds`: JSON-side bounds tests, with `_post` and `_refusal` helpers.
- `tests/unit/test_product_routes.py:3293-3370` -- `_UNIT_PRICE_VERDICTS` + `TestBothPurchaseEntryPointsAgreeOnUnitPrice`: the drift-proof parity-table pattern the new tests must follow.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- Add `_purchase_date_order_error(order_date, received_date)` immediately after `_purchase_text_length_error` (before `_parse_purchase_form`), returning `None` when either argument is falsy or `received_date >= order_date`, else the single message string. Docstring states why it lives here rather than in the service (both callers are routes; the service validates nothing) and why the partial cases are deliberately excluded. -- One definition of the rule for both entry points.
- [x] `app/main/routes.py` -- Call the helper in `_parse_purchase_form` after the date loop (after line 1843, before the `return`), assigning any message to `errors['received_date']`. Extend the function docstring's list of shared rules to name the new helper. -- HTML side, field-scoped, accumulating with the other errors.
- [x] `app/main/routes.py` -- Call the helper in `api_record_purchase` after both `_parse_date` calls succeed (after line 2012), returning `_catalog_json_error('invalid_field', message, 400, field='received_date')` on a message. Extend the block comment at 1965-1976 to name the third shared rule. -- JSON side, AD-13 envelope, before any write.
- [x] `tests/unit/test_product_routes.py` -- Add a `_DATE_ORDER_VERDICTS` table of `(order_date, received_date, fragment)` covering every I/O Matrix row, and a `TestBothPurchaseEntryPointsAgreeOnDateOrder` class parametrized over it with `test_the_html_form` and `test_the_json_endpoint`, modeled on `TestBothPurchaseEntryPointsAgreeOnUnitPrice`. Assert the accepted rows store the expected dates and the refused rows store nothing. -- The two entry points cannot drift apart without a test failing.
- [x] `tests/unit/test_product_routes.py` -- Add a named test on each side for the interaction case: a malformed `order_date` alongside a valid `received_date` reports only the ISO-format error, proving the cross-field rule never fires on an unparsed date. -- Guards the ordering the rule depends on.

**Acceptance Criteria:**
- Given a Product exists, when a purchase is submitted through either entry point with `received_date` strictly earlier than `order_date`, then no Purchase row is created and the caller is told which field is wrong — `received_date` — with the same message text on both sides.
- Given a Product exists, when a purchase is submitted with equal dates, with only one date, or with neither, then the Purchase is recorded exactly as it is today.
- Given the rule is changed in future, when a developer edits the message or the comparison, then exactly one place in `app/main/routes.py` needs editing and the parity table fails if only one entry point changes.
- Given the existing purchase test suite, when `nox -s tests` runs, then every previously passing test still passes with no edits to it.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 3, low 3)
- defer: 1: (high 0, medium 1, low 0)
- reject: 6: (high 0, medium 2, low 4)
- addressed_findings:
  - `[medium]` `[patch]` `_assert_stored` recomputed `date.today()` at assert time, racing the service's `date.today()` at write time — the two blank-`order_date` rows would fail on any run crossing midnight. `today` is now read before the POST and both sides of the boundary are accepted.
  - `[medium]` `[patch]` `test_the_html_form` asserted the refusal message as a page-wide substring, so filing it under `errors['order_date']` — whose control has an identical `invalid-feedback` slot — would have kept the test green, leaving the "which field" half of the acceptance criterion unenforced on the HTML side. Now asserts `is-invalid` on the `received_date` control and its absence on `order_date`, via the file's existing `_form_controls` helper.
  - `[medium]` `[patch]` The mirror of the interaction case was untested: a malformed `received_date` is where the format message and the ordering message contend for the same `errors['received_date']` key. Added `test_the_html_form_does_not_clobber_the_received_date_message` and `test_the_json_endpoint_refuses_the_unparsed_received_date_first`.
  - `[low]` `[patch]` The new docstrings claimed the two entry points "cannot come to disagree" about the dates, which is true of the ordering rule and false of the format rule underneath it (DW-88/DW-191). Scoped the claim to ORDER in all three places and named the exception.
  - `[low]` `[patch]` The helper's docstring called `_parse_purchase_form` and `api_record_purchase` "the only gates", dropping the caveat `_purchase_unit_price` makes explicitly: `record_amazon_purchase` writes both dates and does not inherit the rule. Caveat restored.
  - `[low]` `[patch]` The same partial-cases rationale was restated six times around three lines of logic. Trimmed the two call-site comments to what is local to them, leaving the helper docstring as its single home.
  - `[medium]` `[defer]` DW-191: the form strips whitespace around a date and the JSON endpoint does not, so `' 2026-01-01 '` is accepted by one and refused by the other. Pre-existing, reproduced both ways, and a symptom DW-88's evidence does not name.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 0, low 2)
- defer: 1: (high 0, medium 1, low 0)
- reject: 16: (high 0, medium 4, low 12)
- addressed_findings:
  - `[low]` `[patch]` The padding divergence was attributed in code to DW-88, but the ledger entry that owns that symptom is DW-191 — `grep -rn DW-191 app tests` returned nothing, so the entry was unreachable from the code describing it. The helper docstring and the `_DATE_ORDER_VERDICTS` comment now name DW-191 for the padding and DW-88 for the grammar, and say the two close together.
  - `[low]` `[patch]` The JSON block comment claims the cross-field rule is "judged last of all", but only its precedence against the two date-FORMAT errors was pinned; hoisting the call above the `_PURCHASE_FIELD_LIMITS` loop, the price rule or the `quantity` parse left the whole suite green. Added `TestTheDateOrderRuleIsJudgedLastOnTheJsonEndpoint`, parametrized over an over-long `vendor`, a negative `unit_price` and a non-integer `quantity` paired with an out-of-order date pair.

## Design Notes

The helper signature takes the two already-parsed `date` values rather than raw strings, so the "both present" precondition is expressed as "both parsed to a `date`" and the malformed-input interaction resolves itself: an unparsable date is `None` on the form side and short-circuits the whole request on the JSON side, so the comparison is never reached with a non-date.

```python
def _purchase_date_order_error(order_date, received_date):
    """The out-of-order message for a purchase's date pair, or `None`."""
    if order_date and received_date and received_date < order_date:
        return 'Received Date must not be earlier than Order Date.'
    return None
```

Both callers pass their own parsed values and shape their own refusal, exactly as they do for `_purchase_text_length_error`:

```python
    # form, after the date loop
    message = _purchase_date_order_error(values['order_date'], values['received_date'])
    if message:
        errors['received_date'] = message
```

```python
    # JSON, after both dates parse
    message = _purchase_date_order_error(order_date, received_date)
    if message:
        return _catalog_json_error('invalid_field', message, 400, field='received_date')
```

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: full unit suite green, including the untouched `TestPurchaseFormRefusesWhatTheColumnCannotHold` and `TestRecordPurchaseEndpointHoldsTheSameColumnBounds` classes and the new parity table.
- `venv/bin/python -c "import app.main.routes"` -- expected: imports cleanly (catches a syntax or ordering error in the new helper placement).

**Manual checks (if no CLI):**
- Confirm `grep -n 'must not be earlier than' app/main/routes.py` returns exactly one line — the helper — proving the message is defined once.

## Auto Run Result

Status: `done`

**Implemented change.** One cross-field rule for a Purchase's date pair — a `received_date` may not precede its `order_date` — defined once in `_purchase_date_order_error` beside the two existing shared purchase helpers, and applied by both HTTP entry points: `_parse_purchase_form` files it under `errors['received_date']` and keeps accumulating, `api_record_purchase` returns the AD-13 envelope with `field='received_date'`. Equal dates pass; the partial cases (either date blank) are untouched by decision; no schema, service or template change.

**Files changed.**
- `app/main/routes.py` — new `_purchase_date_order_error` helper plus its two call sites; the `_parse_purchase_form` docstring and the `api_record_purchase` block comment updated to name the third shared rule and to scope the parity claim to ORDER (the date FORMAT rule is still unshared — DW-88/DW-191).
- `tests/unit/test_product_routes.py` — `_DATE_ORDER_VERDICTS` parity table and `TestBothPurchaseEntryPointsAgreeOnDateOrder` (both entry points, every I/O Matrix row); `TestAMalformedDateIsNeverAlsoCalledOutOfOrder` (four tests holding the check after the parse on both sides, including the two collision cases where the format and ordering messages contend for the same key); `TestTheDateOrderRuleIsJudgedLastOnTheJsonEndpoint` (three tests pinning the documented first-failure-wins precedence).
- `_bmad-output/implementation-artifacts/deferred-work.md` — DW-191 and DW-192 appended.

**Review findings.** This follow-up pass: 0 intent_gap, 0 bad_spec, 2 patches applied (both low — DW-191 named in the code that describes its symptom; the "judged last of all" precedence pinned by test), 1 deferred (DW-192, medium), 16 rejected. Cumulative across both passes: 8 patches, 2 deferred (DW-191, DW-192).

**Follow-up review recommended:** `false` — the two fixes are localized and low-consequence: one comment-accuracy correction and one added test class. No behavior changed in this pass.

**Verification performed.**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — 2949 passed, 427 deselected, 0 failed. Every pre-existing purchase test passes untouched.
- Same session filtered to the three DW-24 classes — 19 passed.
- `venv/bin/python -c "import app.main.routes"` — clean.
- `grep -n 'must not be earlier than' app/main/routes.py` — exactly one line (1819), the helper.
- `grep -rn DW-191 app tests` — now returns the two places that describe the symptom.

**Residual risks.**
- The rule is a route-level gate, not a data invariant: no CHECK constraint, no service-layer guard, no backfill of existing rows. `record_amazon_purchase` writes both dates and does not inherit the rule (it has no route today); the helper docstring says so.
- DW-192: a blank `order_date` bypasses the rule and the form's own help text advertises the blank. Deliberate scope (the human's 2026-07-26 decision leaves partial cases untouched) but visible to an operator.
- DW-88/DW-191: the two entry points now agree about ORDER while still reaching the dates through two unshared parses that disagree about padding and accept the whole ISO 8601 grammar the `YYYY-MM-DD` message disclaims. `_DATE_ORDER_VERDICTS` deliberately pins no padded or non-canonical row, so the table understates the rule's real input domain until those close.

