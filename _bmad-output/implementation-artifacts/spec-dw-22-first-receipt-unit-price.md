---
title: 'DW-22: a Unit Price on the create form''s First Receipt block'
type: 'feature'
created: '2026-07-27'
status: 'done'
baseline_revision: '0f406d3'
final_revision: '690be8a'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** The create form's First Receipt block carries `quantity`, `order_number`, `vendor` and `vendor_sku` and no `unit_price`, while no route anywhere can edit or delete a `Purchase`. An operator who knows what they paid while cataloguing the arrival can therefore only price it by recording a SECOND Purchase — which then duplicates the row in the FR20/FR21 history and skews "Last paid".

**Approach:** Add `unit_price` to `_RECEIPT_FIELDS` and to the block's markup, validated on the create form by the same `_purchase_unit_price` helper `_parse_purchase_form` and `api_record_purchase` already share, and passed through to `record_purchase`. Update the block's help text, the user manual and the tests that pin the four-field set.

## Boundaries & Constraints

**Always:**
- `_purchase_unit_price` stays the SINGLE definition of what `Purchase.unit_price` accepts. The create form applies it; it does not restate the magnitude, scale, negativity or non-finite rules, and it emits that helper's messages verbatim.
- The price is judged in `_validate_product_create_form` — before `create_product` commits — like every other rule that only `add.html` can trigger, and keyed `unit_price` so the message lands in the new input's own `invalid-feedback` slot.
- `unit_price` joins `_RECEIPT_FIELDS`, so it is a Purchase TRIGGER like the other four: a price alone, with the rest blank, records one Purchase.
- A blank `unit_price` is not an error and is stored as NULL, exactly as a blank is on `purchase_add`.
- The input lives inside the `#first-receipt` card, is named and id'd `unit_price`, and follows the sibling fields' `is-invalid` / `invalid-feedback d-block` / `form_data.get(...)` round-trip pattern.

**Block If:**
- Nothing. The human already chose option 1 over documenting the block as deliberately price-less.

**Never:**
- Do not add `unit_price` to `_RECEIPT_FIELD_LIMITS`. That mapping is text columns only and feeds `_PURCHASE_FIELD_LIMITS`, which `_parse_purchase_form` iterates to build its string values — a non-text key there would corrupt the purchase form.
- Do not add `unit_price` to `_PRODUCT_PREFILL_ARGS`. That whitelist exists to bound what a query string may put in front of the operator, and nothing produces a price: no ECIA envelope carries one (`ECIA_FIELD_KEYS` has no price), `_scan_banner_args` forwards only `mpn`/`quantity`/`order_number`/`vendor_sku`, and `product_search` forwards that same whitelist. A POST re-render round-trips the typed value through `form_data` regardless.
- No change to `record_purchase`, to `api_record_purchase`, to `purchase_add`, or to `_parse_purchase_form`'s own behaviour.
- No purchase edit or delete route — the general fix DW-22's evidence names belongs with whatever story gives Purchases a management surface.
- Do not narrow the Purchase trigger set (that is DW-27, an open ledger entry with its own decision and its own bundle).
- No JS, no schema change, no migration, no new input on `edit.html`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Priced first receipt | POST `description=X`, `quantity=2`, `unit_price=1.25` | 302; one Purchase with `quantity == 2` and `unit_price == Decimal('1.25')` | No error expected |
| Price alone | POST `description=X`, `unit_price=0.50`, every other receipt field blank | 302; one Purchase whose only receipt value is the price | No error expected |
| Whole receipt blank | POST `description=X` with all five receipt fields blank | 302; no Purchase at all (Story 1.3 path untouched) | No error expected |
| Priceless receipt | POST `description=X`, `vendor=DigiKey`, blank `unit_price` | 302; one Purchase with `unit_price is None` | No error expected |
| Unparseable price | `unit_price=abc` (also `1,25`, `$1.25`) | 200 re-render, no Product created | `Unit Price must be a decimal number.` beside the field |
| Non-finite price | `unit_price=NaN`, `unit_price=Infinity` | 200 re-render, no Product created | Same message — a parseable non-finite is the same refusal |
| Negative price | `unit_price=-1.00` | 200 re-render, no Product created | `Unit Price must not be negative.` |
| Third decimal place | `unit_price=1.234` (also `0.005`) | 200 re-render, no Product created | `Unit Price must have at most two decimal places.` |
| Past the column | `unit_price=100000000` (also `99999999.995`, refused by the SCALE rule) | 200 re-render, no Product created | `Unit Price must be less than 100000000.` |
| Boundary that fits | `unit_price=99999999.99` | 302; stored exactly | No error expected |
| Edit form carries one | POST `unit_price=abc` to `/products/edit/<id>` | 302; ignored in both directions — no refusal, no Purchase | No error expected (DW-13/DW-29 rule) |
| Refusal round-trip | Any refused price beside another field error | The typed price is still in the input on the re-render | No error expected |

</intent-contract>

## Code Map

- `app/main/routes.py:1178` -- `_RECEIPT_FIELDS`, the four-name tuple that is both the read set and the Purchase trigger.
- `app/main/routes.py:946-970` -- `_validate_product_create_form`; the receipt limits loop and the `quantity` rule, where the price rule goes.
- `app/main/routes.py:1318-1355` -- `_record_first_receipt`; parses `quantity` defensively and calls `record_purchase`.
- `app/main/routes.py:1629-1707` -- `_MAX_UNIT_PRICE`, `_UNIT_PRICE_STEP` and `_purchase_unit_price`, the shared rule. Defined AFTER the two functions above, which is fine: module-level names resolve at call time.
- `app/main/routes.py:800-804` -- `_RECEIPT_FIELD_LIMITS`; read-only reference — text columns only, and `_PURCHASE_FIELD_LIMITS` is built from it.
- `app/main/routes.py:1169-1174` -- `_PRODUCT_PREFILL_ARGS`; read-only reference — deliberately unchanged.
- `app/templates/product/add.html:222-263` -- the `#first-receipt` card: row 1 (quantity/order_number/vendor), row 2 (`col-md-12` vendor_sku), then the `form-text`.
- `app/templates/product/purchase_add.html:66-72` -- the existing Unit Price input; the markup pattern to mirror.
- `tests/unit/test_product_routes.py:1747-1809` -- `TestFirstReceiptOnCreate`, incl. `test_all_four_receipt_fields_are_carried` and `test_no_receipt_field_records_nothing`, both of which pin the four-field set.
- `tests/unit/test_product_routes.py:3440-3510` -- `TestTheEditFormOnlyEnforcesWhatItRenders`: the add-only parametrize list, the `name="…"` absence tuple, and the class docstring naming the block's fields.
- `docs/user-manual.md:759-784` -- "The First Receipt Block", which states "It has four fields".
- `docs/user-manual.md:1219-1225` -- the purchase form's Unit Price rules and their verbatim messages, to reference rather than restate.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- add `'unit_price'` to `_RECEIPT_FIELDS` and extend its comment to say the price is a trigger like the rest.
- [x] `app/main/routes.py` -- in `_validate_product_create_form`, after the `quantity` rule: for a non-blank stripped `unit_price`, call `_purchase_unit_price` and key its message under `unit_price`. Follow the file's first-writer-wins convention. Add a short comment naming `_purchase_unit_price` as the shared rule and why the create form defers to it (SQLite hides both the magnitude and the scale failure).
- [x] `app/main/routes.py` -- in `_record_first_receipt`, parse the price the way `quantity` is parsed (validated already, re-parsed here for a caller that arrived another way — take the value and discard the message) and pass `unit_price=` to `record_purchase`. Update the docstring's field list if it names the four.
- [x] `app/templates/product/add.html` -- inside `#first-receipt`, split row 2 into `col-md-3` Unit Price + `col-md-9` Vendor SKU. The new input mirrors `purchase_add.html`'s: `type="text"`, `id="unit_price"`, `name="unit_price"`, no `maxlength` (the rule is numeric, not a character count), `autocomplete="off"`, `form_data.get('unit_price', '')`, and the `is-invalid` / `invalid-feedback d-block` pair. Extend the card's `form-text` to say what Unit Price means (the price of one item) and that it is a plain decimal with at most two decimal places and no currency symbol.
- [x] `tests/unit/test_product_routes.py` -- in `TestFirstReceiptOnCreate`: rename `test_all_four_receipt_fields_are_carried` to cover five, submitting and asserting `unit_price` as a `Decimal`; add `unit_price: ''` to `test_no_receipt_field_records_nothing`; add a price-alone test proving the price is a trigger; add a blank-price test proving `unit_price is None` is not an error; add a parametrized refusal test covering every I/O Matrix error row (message + `product_ids() == set()`), and the `99999999.99` boundary that must pass.
- [x] `tests/unit/test_product_routes.py` -- in `TestTheEditFormOnlyEnforcesWhatItRenders`: add `{'unit_price': 'abc'}` to the add-only parametrize list, add `'unit_price'` to the `name="…"` absence tuple, and add it to the class docstring's field list.
- [x] `docs/user-manual.md` -- rewrite "The First Receipt Block" for five fields ("all five" too), state that Unit Price follows the same rules as the purchase form's and cross-reference them rather than restating the numbers, and note that a price alone records a purchase. Add the Unit Price refusals to the Products troubleshooting table.

**Acceptance Criteria:**
- Given the create form is rendered, when the page loads, then the First Receipt card contains an editable `unit_price` input and `edit.html` still contains none.
- Given a create form carrying a storable price, when it is saved, then exactly one Purchase is written and its `unit_price` is the typed value — no second Purchase is needed to price the arrival.
- Given a price the column cannot hold, when the form is submitted, then no Product and no Purchase exist and the message is `_purchase_unit_price`'s own, rendered beside the price input.
- Given the same price string, when it is submitted to the create form and to `purchase_add`, then both accept or both refuse it with the same message.
- Given the existing suite, when `nox -s tests` runs, then it is green.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 2, low 6)
- defer: 4: (high 0, medium 0, low 4)
- reject: 2: (high 0, medium 1, low 1)
- addressed_findings:
  - `[medium]` `[patch]` The new `_RECEIPT_FIELDS` comment claimed "the read set and the trigger set are one set" while a THIRD set — `_PRODUCT_PREFILL_ARGS` — now carries four of the five receipt fields and not the price, so a reader could only take the omission for an oversight. `purchase_add`'s GET does read `unit_price` from `request.args`, which makes the two receipt surfaces disagree about whether a URL may carry a price. The omission is the spec's deliberate decision (no producer emits one), so it stands — but the comment now states it and names its reasons, and `test_a_url_borne_price_does_not_prefill_the_block` pins it beside a sibling that does pre-fill.
  - `[medium]` `[patch]` Nothing proved the input is OFFERED: every structural assertion was made against a POST re-render via `_form_controls`, which only shows that a control with that id exists somewhere on the page. Spec AC 1 was therefore unverified — moving the input into the Product Information card would have left the whole new suite green. Added `test_the_price_input_renders_inside_the_first_receipt_card`, which slices on the card's own id and bounds the slice at its help text.
  - `[low]` `[patch]` `if unit_price and 'unit_price' not in errors:` was a condition that cannot be false — no rule anywhere in the file keys on that name — advertising a first-writer-wins collision a reader would hunt for and not find. Dropped, with a comment naming the `quantity` rule above as the same shape for the same reason.
  - `[low]` `[patch]` `_UNSTORABLE_PRICES` was a strict subset of what `TestPurchaseFormRefusesWhatTheColumnCannotHold` already asks the purchase form in isolation, while the parity class's docstring claimed both surfaces were "asked about the SAME values". Added `sNaN`, `-Infinity`, `1e-30` and `1E+30`; `-Infinity` also pins that `is_finite()` is checked before the sign, which the helper's docstring calls load-bearing.
  - `[low]` `[patch]` Whitespace-only was neither an error nor a trigger and was untested in both directions, so a future `.strip()` removed at either site would have gone unnoticed. Parametrized the blank-price test over `''` and `'   '`, and added `test_whitespace_alone_is_not_a_trigger`.
  - `[low]` `[patch]` `test_the_same_rules_still_bite_on_the_create_form` — the paired half of the edit-scoping class, whose stated job is that scoping a rule out of the shared validator must not weaken it where it belongs — was not extended when its sibling gained `{'unit_price': 'abc'}`. Added the matching case.
  - `[low]` `[patch]` `test_both_forms_accept_and_store_the_same_price` indexed `[0]` without a count, so a create path that ever wrote the receipt twice would have passed the test that exercises the widest set of accepted values. Both sides are now counted.
  - `[low]` `[patch]` `_record_first_receipt`'s new comment explained the discarded parse message but not what the discard costs when the unusable value is the SOLE trigger: the raw-string trigger test has already fired, so the Purchase written carries nothing but today's date. The comment now names that case, notes `quantity` has behaved so since Story 4.5, and points at the ledger rather than silently widening the guard.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 0, low 3)
- defer: 1: (high 0, medium 0, low 1)
- reject: 12: (high 0, medium 2, low 10)
- addressed_findings:
  - `[low]` `[patch]` `_UNSTORABLE_PRICES` still was not a superset of the two pre-existing per-surface lists, despite its comment arguing that a list restated per surface "could only drift". The previous pass closed part of the gap; `nan` (the lowercase spelling both older classes use) and `99999999999.99` were still asked only of the purchase form in isolation, so the parity class held both surfaces to a narrower set than either was held to alone. Both added, and the superset property is now stated in the comment as the rule to keep.
  - `[low]` `[patch]` `test_the_price_input_renders_inside_the_first_receipt_card` argued at length for slicing on the card's id and then ran its last assertion — `_input_value(...)` — against the whole page, so a `unit_price` input rendered outside the receipt card would have satisfied the one assertion the docstring's reasoning was written for. Now asserted against the slice. The two split markers are also asserted before use, so a renamed card id fails with the intended message rather than a bare `IndexError` or a silently page-wide slice.
  - `[low]` `[patch]` Only a REFUSED price was proven to round-trip. The commoner case — a good price bounced by a sibling field's error — was untested, and it is the one that costs the operator retyping. Added `test_a_good_price_survives_a_bounce_on_another_field`, which pins that the price is not what was refused and that the typed value is back in the input.

## Design Notes

**Why the shared helper and not a copy.** `_purchase_unit_price`'s docstring records that two hand-copied lists are exactly how `_parse_purchase_form` and `api_record_purchase` came to disagree about this column. A third entry point writing `Purchase.unit_price` is precisely the case it was extracted for. It is also the reason the create form must not do a bare `Decimal(...)`: `Decimal('NaN')` parses, reports success and stores NULL, and neither the eight-digit magnitude nor the two-place scale is enforced by SQLite, which is what the unit suite runs on.

**Why the price is a trigger.** `_record_first_receipt` records a Purchase when ANY receipt field is non-blank. Leaving `unit_price` out of `_RECEIPT_FIELDS` would mean a form with a price and nothing else silently discarded it — the same class of bug DW-22 reports. Adding it to the tuple makes the read set and the trigger set the same set, as they are today. DW-27 (open, separate bundle) proposes narrowing the trigger set to `quantity` and `order_number`; that decision is not applied here and would subsume this one cleanly, since it changes only which subset of `_RECEIPT_FIELDS` is tested for non-blankness.

**Layout.** Unit Price goes at the head of row 2 so it sits under Quantity on md+ screens — the two values that multiply. Vendor SKU keeps the rest of the row.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass, including the new first-receipt price tests.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (no `app/utils/` change; regression guard only).

**Manual checks (if no CLI):**
- `tests/e2e/screenshot_config.yaml` has no `/products/add` entry, so the template edit owes no screenshot regeneration; confirm that remains true.


## Auto Run Result

Status: done

### Summary

DW-22: the create form's First Receipt block gains a `unit_price` input, so the receipt captured while cataloguing an arrival can be priced without recording a second Purchase — the duplicate row that skewed FR20/FR21's history and "Last paid". The price is a trigger like the other four fields, judged before `create_product` commits by the pre-existing `_purchase_unit_price` — the single definition of what `Purchase.unit_price` accepts, already shared by the HTML purchase form and `api_record_purchase` — so the create form restates none of the magnitude, scale, negativity or non-finite rules and emits that helper's messages verbatim. The human's option-1 decision was implemented as written; the price is deliberately NOT added to `_PRODUCT_PREFILL_ARGS`, since nothing in the app emits a price into a query string.

This entry records a second, independent review pass over the same diff. It changed tests only — no `app/` or `docs/` change was needed.

### Files changed

- `app/main/routes.py` — `unit_price` joins `_RECEIPT_FIELDS`; `_validate_product_create_form` applies `_purchase_unit_price` and keys its message under `unit_price`; `_record_first_receipt` re-parses defensively and passes `unit_price=` to `record_purchase`.
- `app/templates/product/add.html` — the `#first-receipt` card's second row is now `col-md-3` Unit Price + `col-md-9` Vendor SKU, the input mirroring `purchase_add.html`'s; the card's help text says what a price may look like.
- `docs/user-manual.md` — "The First Receipt Block" rewritten for five fields, the price cross-referenced to the purchase form's identical rules, a price alone documented as recording a purchase, and the four Unit Price refusals added to the Products troubleshooting table.
- `tests/unit/test_product_routes.py` — `TestFirstReceiptOnCreate` extended (price carried, price alone, blank and whitespace, every refusal, the `99999999.99` boundary, both halves of the refusal round-trip, the input rendering inside the card on GET, and the URL-borne price that deliberately does not pre-fill); new `TestTheFirstReceiptPriceMatchesThePurchaseForm` pins create-form ↔ purchase-form agreement over a shared `_UNSTORABLE_PRICES` list that is now a superset of both older per-surface lists; the edit-scoping class extended in all three of its halves.
- `_bmad-output/implementation-artifacts/deferred-work.md` — DW-186 … DW-189 appended by the first review pass, DW-190 by the second.

### Review findings

**Pass 1.** Blind Hunter + Edge Case Hunter on the diff since `0f406d3`. intent_gap 0, bad_spec 0, patch 8 (medium 2, low 6), defer 4 (all low), reject 2. Deferred as DW-186 … DW-189.

**Pass 2 (this pass).** Blind Hunter + Edge Case Hunter re-run independently on the same diff. intent_gap 0, bad_spec 0, patch 3 (all low), defer 1 (low), reject 12 (medium 2, low 10). All three patches were test-only; no production behaviour changed. Deferred as DW-190 (no `inputmode`/placeholder on any of the four numeric inputs across both purchase-capture surfaces — pre-existing and symmetrical, and `type="number"` is explicitly not the fix). Four of the rejects were re-discoveries of DW-186 (the `1_0` leniency beside a strict Quantity), DW-187 (the all-NULL Purchase the defensive re-parse can write), DW-188 (the unpinned verbatim help-text quotation) and DW-189 (`-0` passing the negativity rule) — already on the ledger from pass 1, so re-filing them would only duplicate. The rest were verified against the code and did not survive: the manual's "**Category** is the exception" paragraph is about fields with a CHARACTER limit and `unit_price` has none, so it is not falsified; the scan bullet already enumerates exactly the three fields a scan can pre-fill; the double parse of the price mirrors `quantity`'s existing shape deliberately; and the per-field help-text placement and absent `maxlength` are what the spec directed, mirroring `purchase_add.html`.

### Verification

- `nox -s tests` — 2930 passed, 427 deselected (2925 before this pass; +5 from the two new `_UNSTORABLE_PRICES` rows across two parametrized classes and one new test).
- `nox -s doctests` — 21 passed (no `app/utils/` change; regression guard only).
- `nox -s e2e` not run: no e2e test submits the create form's receipt block, no scan path emits a price, and the change is server-rendered with no JS. This pass touched no template at all.
- `tests/e2e/screenshot_config.yaml` still has no `/products/add` entry, so the template edit owes no screenshot regeneration. Confirmed after the edit.

### Residual risks

- DW-186 is the one an operator can meet: `1_0` typed into Unit Price stores 10 without a word, while the same string one box to the left is refused. The leniency is `_purchase_unit_price`'s, is recorded as deliberate, and is now pinned by a parity test — but this change is what put the strict field and the lenient one side by side.
- The price's bounds are enforced only where SQLite cannot show them failing; the unit suite proves the RULE fires, not that MariaDB agrees about the column. That gap is the reason the helper checks magnitude and scale itself, and it is unchanged by this story.
- A purchase still cannot be edited or deleted anywhere, so a mistyped-but-storable price on the create form is as permanent as it was before. DW-22's evidence names that as the more general fix; it stays out of scope.
- `_UNSTORABLE_PRICES` is now a superset of the two older per-surface lists by convention and by comment, not by construction — nothing fails if a future value is added to one of those lists and not to it.
