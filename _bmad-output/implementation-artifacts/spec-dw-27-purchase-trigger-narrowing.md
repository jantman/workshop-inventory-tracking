---
title: 'DW-27: narrow the first-receipt Purchase trigger to Quantity and Order Number'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: '6642608'
final_revision: 'faa3439'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `_record_first_receipt` writes a Purchase when ANY of the five `_RECEIPT_FIELDS` is non-blank, and `_ecia_prefill` puts the distributor's `P` record into `vendor_sku`. So scanning a part-number-only ECIA label (`1P`+`P`, no `Q`, no `K`), typing a description and saving records a Purchase the operator never asked for — `vendor=NULL, quantity=NULL, unit_price=NULL, order_number=NULL`, `vendor_sku` the distributor's part number, `order_date` defaulted to today by `record_purchase` — into the FR20/FR21 history. Nothing in any suite submits an ECIA-prefilled create form, so no test sees it.

**Approach:** Split the trigger out of the read set. `_RECEIPT_FIELDS` keeps all five names (they are still all WRITTEN onto the Purchase); a new `_RECEIPT_TRIGGER_FIELDS = ('quantity', 'order_number')` becomes what `_record_first_receipt` tests for non-blankness. Restate the block's help text and the user manual accordingly, and add the missing unit and e2e coverage that GETs a pre-filled create form and POSTs it.

## Boundaries & Constraints

**Always:**
- The trigger is exactly `quantity` or `order_number` non-blank after `.strip()`. This is the human's decision (option 1, "trigger only on the fields a human plausibly typed"), applied as written.
- `_RECEIPT_FIELDS` stays all five names and stays the READ set: when a trigger fires, `vendor`, `vendor_sku` and `unit_price` are still written onto the same one Purchase exactly as today.
- `_RECEIPT_TRIGGER_FIELDS` is a subset of `_RECEIPT_FIELDS`, pinned by a test — a name in the trigger that is not read would trigger and then store nothing.
- A quantity or order number that a SCAN pre-filled still records a Purchase. The human chose this explicitly: ECIA labels do carry `Q` and `K`/`1K`, they are receipt content rather than identity, and the operator confirms them on the form. `_ecia_prefill` is unchanged.
- Validation is unchanged and stays independent of the trigger: an unstorable `unit_price` or an over-long `vendor_sku` is still refused before `create_product` commits, whether or not a trigger is present.
- Exactly one Purchase, or none. No change to `record_purchase`, to `order_date` defaulting, or to the non-fatal failure contract (`_record_first_receipt` still returns a message rather than raising).

**Block If:**
- Nothing. The trigger set is the human's decision and the price question is resolved in **Never** below.

**Never:**
- Do not make a non-trigger receipt field with no trigger into a validation ERROR. A scan pre-fills `vendor_sku`, so refusing that shape would hand the operator an error on a field they never typed — strictly worse than the bug being fixed. The value is silently not recorded; the help text is what tells them.
- Do not keep `unit_price` in the trigger. DW-22 added it as a trigger on 2026-07-27 and its own spec anticipated this bundle by name, calling the narrowing to `quantity`/`order_number` a clean subsumption. DW-22's actual complaint — that pricing an arrival required a SECOND Purchase — stays fixed: a quantity plus a price still records one priced Purchase.
- Do not touch `_PRODUCT_PREFILL_ARGS`, `_RECEIPT_FIELD_LIMITS`, `_purchase_unit_price`, `_ecia_prefill`, `_scan_banner_args`, `purchase_add`, `api_record_purchase`, or `edit.html`.
- No schema change, no migration, no JS, no new input, no purchase edit/delete route.
- Do not edit `{implementation_artifacts}/deferred-work.md` to resolve DW-27; the orchestrator records that.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| The DW-27 repro | GET `/products/add?mpn=ABC-123&vendor_sku=XYZ-999`, then POST that form with `description` typed and the pre-filled `vendor_sku` returned | 302; Product created; **no Purchase at all** | No error expected |
| Scan plus a real receipt | Same pre-fill, operator adds `quantity=42` | 302; one Purchase with `quantity == 42` and `vendor_sku == 'XYZ-999'` | No error expected |
| Quantity alone | POST `description=X`, `quantity=5` | 302; one Purchase | No error expected |
| Order number alone | POST `description=X`, `order_number=PO-1` | 302; one Purchase, `order_number == 'PO-1'` | No error expected |
| Vendor alone | POST `description=X`, `vendor=DigiKey` | 302; no Purchase | No error expected |
| Vendor SKU alone | POST `description=X`, `vendor_sku=XYZ-999` | 302; no Purchase | No error expected |
| Price alone | POST `description=X`, `unit_price=0.50` | 302; no Purchase — the price is read, not a trigger | No error expected |
| Whitespace trigger | POST `description=X`, `quantity='   '`, rest blank | 302; no Purchase (both sites `.strip()`) | No error expected |
| Everything blank | POST `description=X`, all five blank | 302; no Purchase (Story 1.3 path untouched) | No error expected |
| Full receipt | POST all five non-blank | 302; one Purchase carrying all five values | No error expected |
| Price still validated without a trigger | POST `description=X`, `unit_price=abc`, no quantity/order number | 200 re-render, no Product, no Purchase | `Unit Price must be a decimal number.` beside the field |
| Non-trigger field still bounded | POST `description=X`, `vendor_sku` 256 chars, no trigger | 200 re-render, no Product | The existing over-long message beside the field |
| Unparseable quantity alone | POST `description=X`, `quantity=abc` | 200 re-render, no Product | Existing quantity message — validation catches it before the trigger is reached |

</intent-contract>

## Code Map

- `app/main/routes.py:1199-1218` -- the `_RECEIPT_FIELDS` comment block and tuple. The comment currently argues at length that the read set and the trigger set are one set; it is what changes.
- `app/main/routes.py:1358-1409` -- `_record_first_receipt`. `values = {…for name in _RECEIPT_FIELDS}` at 1373 stays; `if not any(values.values())` at 1374 is the whole trigger. The 1380-1388 comment about the defensive re-parse failing open names the price as a case that can no longer arise.
- `app/main/routes.py:1491` -- the single call site in `product_add`.
- `app/main/routes.py:1192-1197` -- `_PRODUCT_PREFILL_ARGS`; read-only reference. Carries `quantity`/`order_number`/`vendor`/`vendor_sku` and not `unit_price`.
- `app/main/routes.py:2112-2160` -- `_ecia_prefill`; read-only reference. `vendor_sku` <- `P`, `quantity` <- `Q` only when a positive whole number, `order_number` <- `K` then `1K`.
- `app/templates/product/add.html:222-223` -- the block's Jinja comment ("any non-blank field records one Purchase").
- `app/templates/product/add.html:269-273` -- the `form-text`, quoted verbatim by the user manual.
- `tests/unit/test_product_routes.py:1787-1996` -- `TestFirstReceiptOnCreate`.
- `tests/unit/test_product_routes.py:1834, 1853, 1936` -- the three tests that assert a price-alone or vendor-alone submission records a Purchase.
- `tests/unit/test_product_routes.py:2000-2071` -- `TestTheFirstReceiptPriceMatchesThePurchaseForm`; `test_both_forms_accept_and_store_the_same_price` at 2048 posts a price with no trigger.
- `tests/unit/test_product_routes.py:2504` -- `TestScannedIdentifierTyping.test_the_receipt_vendor_does_not_become_the_identifier_scope`; vendor-only, asserts `get_purchases_for_product(pid)[0]`.
- `tests/unit/test_product_routes.py:1379-1467` -- `TestProductAddPrefill`; the GET-side whitelist tests, the place a GET-then-POST test belongs beside.
- `tests/e2e/test_scan_routing.py:45-78` -- `_envelope()`, `_scan_raw()`, `_create_product()` helpers.
- `tests/e2e/test_scan_routing.py:156-175` -- `test_an_ecia_envelope_prefills_mpn_quantity_and_order_references`; scans `1P`/`P`/`Q42`/`K…` and asserts the inputs, never submitting.
- `tests/e2e/test_toggle_item_status.py:77` -- the `sessionmaker(bind=live_server.engine)` DB-assertion pattern to reuse.
- `docs/user-manual.md:759-792` -- "The First Receipt Block".
- `docs/user-manual.md:1155-1176` -- the scan pre-fill bullets.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- add `_RECEIPT_TRIGGER_FIELDS = ('quantity', 'order_number')` beside `_RECEIPT_FIELDS` and change `_record_first_receipt`'s guard to test only those two. Rewrite the tuple's comment: the read set and the trigger set are now DIFFERENT sets, and say why — a scan pre-fills `vendor_sku` from the label's `P` record, so triggering on it recorded a receipt dated today that nobody entered (DW-27); `quantity` and `order_number` are receipt content the operator confirms even when a label supplied them. State that the other three are still written when a trigger fires and silently not written when none does.
- [x] `app/main/routes.py` -- update the 1380-1388 fail-open comment in `_record_first_receipt`: only `quantity` can now trigger on a raw string that then fails to parse, since an unstorable price is no longer a trigger.
- [x] `app/templates/product/add.html` -- update the block's Jinja comment and rewrite the `form-text` so it states what records a receipt: a Quantity or an Order Number, with Vendor, Unit Price and Vendor SKU saved alongside; both blank records no purchase, **including when a scan filled in the Vendor SKU for you**. Keep the existing Unit Price sentence.
- [x] `tests/unit/test_product_routes.py` -- in `TestFirstReceiptOnCreate`: replace `test_a_price_alone_records_one_purchase` with a test that a price alone records NOTHING; give `test_a_blank_price_beside_another_field_is_not_an_error` and `test_the_boundary_price_the_column_holds_is_stored` a trigger (`quantity`); add per-field non-trigger tests for `vendor` and `vendor_sku` alone; add `test_an_order_number_alone_records_one_purchase`; add a whitespace-only-`quantity` non-trigger test; add a test pinning `set(_RECEIPT_TRIGGER_FIELDS) <= set(_RECEIPT_FIELDS)` and the trigger tuple's exact contents, with a docstring naming DW-27 as the reason.
- [x] `tests/unit/test_product_routes.py` -- add a class (beside `TestProductAddPrefill`) that GETs `/products/add?mpn=ABC-123&vendor_sku=XYZ-999`, asserts both values are in the rendered form, then POSTs them back with a typed `description`: no Purchase. Second test: the same, plus `quantity=42` typed — one Purchase carrying `quantity == 42` and `vendor_sku == 'XYZ-999'`. This is the coverage the ledger says nothing has.
- [x] `tests/unit/test_product_routes.py` -- give `test_both_forms_accept_and_store_the_same_price` (2048) and `test_the_receipt_vendor_does_not_become_the_identifier_scope` (2504) a `quantity` so each still exercises what it is about; note in each docstring that the trigger, not the assertion, is what changed.
- [x] `tests/e2e/test_scan_routing.py` -- add an e2e that wedge-scans a part-number-only envelope (`1P`+`P`, deliberately no `Q` and no `K`), asserts `#vendor_sku` is pre-filled, fills only `#description`, submits, and asserts via `sessionmaker(bind=live_server.engine)` that the created Product has zero `Purchase` rows. Add its counterpart: the same scan with `#quantity` typed by hand submits to exactly one Purchase whose `vendor_sku` is the scanned value. Mark both `@pytest.mark.e2e`; follow the module's uuid-token uniqueness convention.
- [x] `docs/user-manual.md` -- rewrite "The First Receipt Block" (759-792): re-quote the new help text verbatim, replace "Fill in **any one** of them" with the Quantity-or-Order-Number rule, delete the "Unit Price on its own still records the purchase" claim, and rewrite the scan paragraph — a scanned Vendor SKU alone no longer records anything, while a scanned quantity or order number does. State plainly that Vendor, Unit Price and Vendor SKU are saved only alongside a Quantity or an Order Number. Check 1155-1176 for anything the change falsifies.

**Acceptance Criteria:**
- Given a create form whose only non-blank receipt field was pre-filled by a distributor part-number scan, when it is saved, then the Product exists and the FR20/FR21 purchase history for it is empty.
- Given the same form with a quantity or an order number, when it is saved, then exactly one Purchase exists and it carries the scanned `vendor_sku` too.
- Given the block's rendered help text, when it is compared with `docs/user-manual.md`'s quotation of it, then the two agree word for word.
- Given the existing suite, when `nox -s tests` and `nox -s e2e` run, then both are green.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 0, medium 0, low 10)
- defer: 2: (high 0, medium 2, low 0)
- reject: 4: (high 0, medium 2, low 2)
- addressed_findings:
  - `[low]` `[patch]` The new `_RECEIPT_FIELDS` comment justified removing `vendor` from the trigger by claiming it "has the same shape (a scan can supply one)" — factually false. No scan path emits `vendor`: `_ecia_prefill` returns only `mpn`/`vendor_sku`/`quantity`/`order_number`, `_scan_banner_args` forwards that same four, and ECIA format-06 has no vendor record. A maintainer would have reasoned about a hazard that does not exist while the real reason went unrecorded. Restated on both the comment and the matching test docstring: `vendor` names WHO sells the part rather than that a shipment came.
  - `[low]` `[patch]` `test_the_trigger_is_a_subset_of_what_is_read`'s docstring claimed the containment prevents "a Purchase carrying nothing but today's date", but `_record_first_receipt` consumes the read set through hardcoded keys rather than by iterating it, so membership proves only that a name COULD be reached — not that it is passed to `record_purchase`. Adding a name to both tuples would satisfy the assertion and still write the row. Docstring now states what the assertion covers and names the per-field behavioural tests as what covers the rest.
  - `[low]` `[patch]` `test_whitespace_alone_is_not_a_trigger` argued that "whitespace in a TRIGGER field is the one place the `.strip()` is what stands between a blank form and a spurious Purchase" and then covered only one of the two triggers. `order_number` added to the parametrize.
  - `[low]` `[patch]` `TestAPrefilledFormIsSavedBack`'s docstring criticised existing tests for POSTing "a form built by hand", while `_prefilled_form_values` asserted two inputs and then returned hardcoded literals — so a pre-fill that arrived double-escaped or truncated would still be POSTed correctly and the round trip would pass on values the browser never sent. Now returns what `_input_value` parsed out of the page.
  - `[low]` `[patch]` The trigger tuple's comment referenced the pinning test by a name broken across a line (`test_the_trigger_is_a_subset_of_` / `what_is_read`), which no grep would find. Replaced with the class name.
  - `[low]` `[patch]` `docs/user-manual.md:730` — the numbered create-form step an operator reads WHILE filling the form — still said only "fill this in if you are cataloguing something that just arrived", which invites the exact Vendor+Price-without-Quantity shape that is now silently dropped. It sits outside the 1155-1176 window the spec told the implementation to check. Now names the two fields that record the purchase.
  - `[low]` `[patch]` The manual carefully documented that an unstorable Unit Price is refused even when it would have been dropped, and said nothing about the same asymmetry for an over-long Vendor or Vendor SKU — which is larger, since those are the scan-adjacent fields. Added.
  - `[low]` `[patch]` The Scanning section's pre-fill bullets said "**Order Number** is filled whenever the label carried one" with no hint that this is now one of the two fields that book a purchase on save. An operator reading only that section would take all scan-filled receipt data for inert — correct for Vendor SKU, wrong for Order Number, and the path to DW-193. Bullet now states the consequence and the Vendor SKU contrast.
  - `[low]` `[patch]` The manual's one actionable remedy — "If you meant to record what arrived, give it a quantity" — contradicted the rule established two lines above it, that an Order Number does the job equally well. Reworded.
  - `[low]` `[patch]` `_purchases_for` was defined between two test classes while every other helper in `tests/e2e/test_scan_routing.py` lives in the block at the top. Moved to join them.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 2, low 7)
- defer: 1: (high 0, medium 1, low 0)
- reject: 7: (high 0, medium 3, low 4)
- addressed_findings:
  - `[low]` `[patch]` The `_RECEIPT_TRIGGER_FIELDS` comment stated the wrong consequence for a trigger name that is not also read — "would write a Purchase carrying nothing but today's date". It would not: the guard subscripts `values`, which is keyed by `_RECEIPT_FIELDS`, so a non-subset name raises `KeyError` on every create POST, and `product_add`'s blanket `except` turns that into "An error occurred while creating the product" over a Product that has ALREADY committed — the save-looks-failed resubmit `_record_first_receipt`'s own docstring names FR41 to avoid. The comment now states that, and states why the loud subscript is preferred over a quiet `.get()`.
  - `[low]` `[patch]` `test_the_trigger_is_a_subset_of_what_is_read`'s docstring repeated the same false consequence. Rewritten to the real one, which also gives the assertion a sharper justification: it is what makes the KeyError a red test rather than a traceback an operator meets.
  - `[low]` `[patch]` The `_RECEIPT_FIELDS` comment justified excluding `vendor` with "nothing pre-fills it" — false, and contradicted twenty lines below in the same comment: `_PRODUCT_PREFILL_ARGS` carries `vendor` and `product_search` forwards that whitelist, so `/products/add?vendor=Mouser` pre-fills it. Only the ECIA half is true. Restated as an exclusion of MEANING rather than of exposure. (The previous pass corrected this sentence once already, in the other direction.)
  - `[low]` `[patch]` The rewritten fail-open comment conceded that `quantity` can still trigger-then-fail-to-parse and then concluded "the Purchase written is a real one missing a price rather than a row carrying nothing but today's date", which reads as a blanket claim that the all-NULL row is gone. Both reviewers read it that way. Split explicitly: the PRICE half is closed, the QUANTITY half is open and unchanged.
  - `[medium]` `[patch]` `docs/user-manual.md` warned about the trigger on only one of the ECIA pre-fill paths. The sibling bullet — "a **distributor envelope naming no part number** fills whatever else it carried" — is precisely the `quantity`/`order_number` case, and on that path **Label Description** is pre-filled too, so the form can be saved with nothing typed at all and book a purchase. Warning added.
  - `[medium]` `[patch]` "Confirming a Duplicate" documents the form reached from **Create a separate product instead** in detail and never mentioned the receipt block, though `_scan_banner_args` forwards `quantity`/`order_number`/`vendor_sku` onto that link — so the confirmed-duplicate form can arrive with a trigger already populated and book a purchase against the NEW product. Paragraph added.
  - `[low]` `[patch]` `tests/e2e/test_scan_routing.py`'s `_purchases_for` returned ORM instances that callers read after `session.close()`, while citing an e2e that asserts inside the session as its precedent. It works only because `close()` happens not to expire loaded attributes. Now returns plain dicts of column values, so no `expire_on_commit` change or deferred column can turn it into a `DetachedInstanceError` twenty minutes into a run.
  - `[low]` `[patch]` `test_an_order_number_alone_records_one_purchase` dropped the `vendor is None` guard the price-alone test it replaced had carried, so a stray default written into a partial receipt would pass. Restored, with `unit_price` beside it.
  - `[low]` `[patch]` `test_a_receipt_field_records_one_purchase` kept a name asserting the rule this change removed — since DW-27 "a receipt field" does not record a purchase, two specific ones do. Renamed to `test_the_trigger_fields_record_one_purchase`.

### 2026-07-27 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 0
- reject: 9: (high 0, medium 3, low 6)
- addressed_findings:
  - `[medium]` `[patch]` The manual now warns about a scan-armed trigger on landing 3 and on the FR41 confirmed-duplicate form, and said nothing about the THIRD pre-filled surface. `product_search` builds its **Create a new product** link from `_PRODUCT_PREFILL_ARGS` (`routes.py:1689-1690`, `1708`), which carries `quantity` and `order_number`, so a scan that lands on search results reaches an add form armed exactly as landing 3 would have armed it. Warning added to the landing-2 bullet, plus a paragraph in "The Search Page — A Deliberate First Cut", which described the Create button as though it opened blank.
  - `[low]` `[patch]` The `_RECEIPT_FIELDS` comment's "the block's help text — not a validation error — is what tells the operator" read as a blanket claim that no non-trigger field is ever refused. The rules in `_validate_product_create_form` never consult the trigger, so an unstorable `unit_price` or an over-long `vendor`/`vendor_sku` IS refused with both triggers blank — the very "error over a field a scan filled in" the next sentence says was avoided. The comment now scopes the claim to the missing trigger itself and states the validation asymmetry the manual already documents.
  - `[low]` `[patch]` `TestAPrefilledFormIsSavedBack._prefilled_form_values` read back only `mpn` and `vendor_sku` and returned only those two keys, so its POST omitted the receipt block a browser would have submitted. The class's whole purpose is to assert an ABSENCE of Purchases; had a later pre-fill change armed `quantity`, the helper would have neither read nor posted it and the test would have gone green over the exact regression it exists to catch. Now reads and returns `('mpn',) + _RECEIPT_FIELDS` and pins the three unpopulated ones blank — the unit-test counterpart of the `#quantity`/`#order_number` emptiness the e2e already asserted.
  - `[low]` `[patch]` The same class's docstring credited the query-string literal to `/scan/route`, an endpoint that does not exist anywhere in the app; the producer is `POST /api/scan` -> `_scan_destination`. The literal itself is correct, so the only cost was sending a reader after a route they would never find. Corrected.
  - `[low]` `[patch]` `test_a_non_trigger_field_alone_records_nothing` parametrizes the three one at a time, while the manual's promise is about the combination ("no matter what the other three hold") and the realistic forgetting is all three at once — vendor, price and SKU typed, quantity omitted. Equivalent under today's `any()`, which is why it needed its own pin: a future guard treating a full vendor/price/SKU set as "surely a receipt" would falsify the manual with every single-field test still green. `test_all_three_non_triggers_together_still_record_nothing` added.

## Design Notes

**Why two tuples rather than one shrunk tuple.** `vendor`, `vendor_sku` and `unit_price` must still be READ — a receipt with a quantity and a price stores both. Shrinking `_RECEIPT_FIELDS` would drop them from the write. The narrowing is only about which subset is tested for non-blankness, which is exactly how DW-22's spec predicted this bundle would land.

**Why the price loses its trigger.** DW-22 made `unit_price` a trigger a day after this decision was recorded, and wrote into its own contract that DW-27 "would subsume this one cleanly". The two are compatible in the case DW-22 was filed over — cataloguing an arrival you know the price of means typing a quantity too — and the human's chosen principle is that a field must be one a human plausibly typed *as part of a receipt*. A lone price is a fact about the product, not evidence that a shipment arrived today.

**Why a silent drop and not a refusal.** The asymmetry is deliberate and worth naming: an unstorable price with no trigger is still refused (validation never consulted the trigger), while a perfectly good price with no trigger is dropped. Making the drop an error is the one change that would recreate DW-27 in mirror image, because the field a scan fills is `vendor_sku` and the operator did not fill it. The help text is the fix for the surprise.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: all pass, including the two new scan-then-save tests. Needs a 20-minute harness timeout; run detached and poll.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (no `app/utils/` change; regression guard only).

**Manual checks (if no CLI):**
- `tests/e2e/screenshot_config.yaml` has no `/products/add` entry, so the template edit owes no screenshot regeneration; confirm that remains true after the edit.
- Diff `add.html`'s `form-text` against the sentence `docs/user-manual.md` quotes; they must match character for character.

## Auto Run Result

Status: done

### Summary

Second follow-up review pass over the DW-27 change (a first receipt on the
create form is TRIGGERED only by a Quantity or an Order Number; `_RECEIPT_FIELDS`
stays the five-name READ set). Two adversarial reviewers ran against the full
diff since `6642608`.

No intent gap and no spec defect. The narrowing itself, the two-tuple split, the
silent-drop asymmetry, and the deliberate acceptance of scan-supplied triggers
all survived a third independent reading. Both reviewers pushed hardest on the
`K`/`1K` order-number label still booking a purchase and on the three typed
fields vanishing without a message — both are the human's recorded decisions and
both are already on the ledger (DW-193, DW-194), so neither was re-filed.

Five patches were applied, and **no production behaviour changed** —
`app/main/routes.py` was touched only in a comment. What this pass actually
found was one operator-facing documentation hole and one test that could have
gone green over the regression it exists to catch:

- The manual now warns about a scan-armed trigger on the pre-filled add form and
  on the confirmed-duplicate form, and said nothing about the third surface.
  `product_search` builds its **Create a new product** link from
  `_PRODUCT_PREFILL_ARGS`, which carries `quantity` and `order_number`, so a scan
  landing on search results reaches an add form armed exactly the same way. The
  "Search Page" section described that button as though it opened blank.
- `TestAPrefilledFormIsSavedBack` GETs the scan-shaped form and POSTs it back to
  prove no Purchase is written, but its helper read back only `mpn` and
  `vendor_sku`. A later pre-fill change arming `quantity` would have been neither
  read nor posted, and the absence assertion would have kept passing.
- The `_RECEIPT_FIELDS` comment's "help text — not a validation error" claim read
  as blanket, while `_validate_product_create_form` never consults the trigger:
  an unstorable price or an over-long vendor SKU is refused with both triggers
  blank. The manual documented that asymmetry; the code comment denied it.

### Files changed (this pass)

- `app/main/routes.py` — one comment correction: the `_RECEIPT_FIELDS` block now
  scopes "not a validation error" to the missing trigger itself and states the
  validation asymmetry. No executable line changed.
- `docs/user-manual.md` — scan-landing-2 bullet gains the trigger warning; "The
  Search Page — A Deliberate First Cut" gains a paragraph on what the **Create a
  new product** button carries.
- `tests/unit/test_product_routes.py` — `_prefilled_form_values` now reads and
  posts the whole receipt block and pins the three unpopulated fields blank; the
  fabricated `/scan/route` reference corrected to `POST /api/scan` ->
  `_scan_destination`; `test_all_three_non_triggers_together_still_record_nothing`
  added to pin the combination the manual promises about.

### Review findings

- intent_gap 0, bad_spec 0.
- patch 5 (1 medium, 4 low) — all applied; see the triage log.
- defer 0 — every deferrable finding this pass raised was already on the ledger
  (DW-187/DW-193/DW-194/DW-195 for the residual hazards, DW-188 for the unpinned
  manual quotation), so nothing new was appended.
- reject 9 (3 medium, 6 low) — the DW-193 and DW-194 restatements; the
  refuse-then-drop price asymmetry and the proposal to gate validation on the
  trigger, both of which contradict the contract's explicit "validation is
  unchanged and stays independent of the trigger"; the argument that the guard
  should use `.get()` or a module-scope `assert` rather than a subscript, which
  the previous pass settled deliberately; the pin's incidental tuple-ordering
  strictness; stale statements in the FROZEN DW-22 and Story 4.5 specs, which are
  historical artifacts and not editable; the "rule lives in five places" grumble,
  already ledgered as DW-188; and the in-flight dirty working tree, which is this
  workflow's own state.

### Verification

- `nox -s tests` — 2958 passed, 429 deselected.
- `nox -s e2e` — 409 passed, 1 skipped, in 20m39s. Screenshot churn the run
  produces (`docs/images/screenshots/`) reverted, as it is unrelated to this
  change.
- `nox -s doctests` — 21 passed.
- Help text vs. manual quotation compared programmatically: identical word for
  word after whitespace normalization.
- `tests/e2e/screenshot_config.yaml` still has no `/products/add` entry, so the
  earlier template edit owes no regeneration.

### Residual risks

- DW-193 is the live one: a distributor label carrying `K`/`1K` still books a
  purchase dated today on a scan-and-catalogue save, and real bag labels carry
  `K` more often than they carry `1P`+`P` alone. That is the human's recorded
  decision, warned about in the manual, and unmeasured.
- DW-194's silence is unchanged: three typed receipt fields with no trigger are
  dropped behind "Product created successfully!".
- The rule is stated in the code comments, the template, four passages of the
  manual and the tests, and only the tests are enforced. DW-188 tracks pinning
  the manual's verbatim quotation.


