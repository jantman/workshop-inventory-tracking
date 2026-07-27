---
title: 'Make product_add and product_edit agree on rules, messages and round-trip'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: 'aa85b40'
final_revision: '63b60aa'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [multiple-goals, oversized]
---

<intent-contract>

## Intent

**Problem:** `product_add` and `product_edit` share `_validate_product_form`, `edit.html`'s round-trip and nothing else, and the three seams that creates are all operator-visible failures. (a) The receipt rules (`quantity`, `vendor`, `vendor_sku`, `order_number`) and the identifier rules (`identifier_type`, `identifier_value`) are inherited by `product_edit`, whose `edit.html` renders none of those inputs and no `invalid-feedback` block for any of them — a POST carrying one gets a silent 200 that writes nothing and says nothing (DW-13, DW-29). (b) The FR41 duplicate gate must stay shared, so `confirm_duplicate` has the same silent-200 shape on the edit form. (c) A committed row whose follow-up tag write failed reads as a partial success on `product_add` and as an outright failure on `product_edit` (DW-30). (d) `product_edit`'s failure re-renders hand `edit.html` the raw submitted `form_data`, and the template renders `value="{{ form_data.get('<field>', '') }}"`, so a non-browser client that POSTs one field and then re-posts the rendered form clears every optional field it never sent (DW-52).

**Approach:** Split the validator into a shared base (the fields BOTH forms render, plus the FR41 gate) and a create-only extension (receipt + identifier rules) that only `product_add` calls; give `edit.html` a fallback that renders any error key it has no field for, so no future shared rule can be silent either; apply `product_add`'s collect-then-flash shape to `product_edit`; and merge the STORED product values under the submitted ones on every `product_edit` failure re-render.

## Boundaries & Constraints

**Always:**
- The FR41 duplicate gate (`duplicate_of` + `confirm_duplicate`) stays in the SHARED validator both routes call — a bypass there would be a real hole, and it is the reason `edit.html` needs the unkeyed fallback rather than only a scoping change.
- Every error key `_validate_product_form` (base) can emit renders somewhere visible on `edit.html`: either beside its own field or in the fallback block.
- `product_edit` never rejects a POST because of a field it neither renders nor writes.
- `product_edit`'s post-commit follow-up failures are COLLECTED, then the success is flashed unconditionally, then the failures — the same order and the same reasoning as `product_add:1263-1272`. The row exists either way.
- Every `product_edit` re-render of `edit.html` (validation failure, `update_product` returning false, and the outer exception handler) shows submitted values over stored values, never stored values over submitted ones. A key present-but-empty in the POST renders empty; a key absent from the POST renders the stored value.
- The stored baseline for that merge is `_product_form_data(product, tags)` — the same mapping the GET already renders — so a re-posted form carries exactly what a GET would have carried for the fields the client never sent.
- `product_edit`'s partial-update write rule is untouched: only keys present in `request.form` reach `update_product`, and `_form_tags` still returns None for an absent `tags` key.
- Existing tests that pin the OLD `product_edit` tag-failure behavior are inverted to the new one, in place, with the reason recorded — matching what was done for `product_add`'s equivalent test.

**Block If:** No unattended decision is expected. Block only if the shared/create-only split cannot preserve the FR41 gate on both routes.

**Never:**
- Do not add `quantity`/`vendor`/`vendor_sku`/`order_number`/`identifier_*` inputs to `edit.html`. Those fields belong to the create form's first-receipt and scanned-identifier blocks; the edit route reads and writes none of them.
- Do not change what `product_add` validates, flashes, or writes. It is the correct half of every pairing here; only its shape is being copied.
- Do not touch `admin.add_material` / `admin/add_material.html` or `purchase_add`: both are CREATE forms with no stored baseline, so "merge stored under submitted" is vacuous there (investigated — there is no admin edit form; `/materials/add` is the only admin route that re-renders submitted data). Do not touch `inventory_edit`, which repopulates from a synthesized `temp_item`, not `form_data`.
- Do not remove or weaken the non-blank-`identifier_value` gating that `TestNoErrorRendersNowhere` pins on the add form.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Receipt field on an edit POST | `POST /products/edit/<id>` with valid `description` + `quantity=0` | 302 to the detail page; `quantity` ignored, description written | No error — the rule is add-only now |
| Over-long receipt field on an edit POST | valid `description` + 300-char `vendor` | 302; `vendor` ignored, description written | No error |
| Identifier field on an edit POST | valid `description` + `identifier_type=NOT_A_TYPE` + a 300-char `identifier_value` | 302; both ignored, description written | No error |
| Same rules still bite on add | `POST /products/add` with `quantity=0`, or a 300-char `vendor`, or a bogus `identifier_type` beside a value | 200 re-render carrying the existing field message; nothing created | Field-scoped message, unchanged text |
| FR41 gate still shared | `POST /products/edit/<id>` with valid `description` + `duplicate_of=<real id>` and no `confirm_duplicate` | 200 re-render; the gate's message is VISIBLE on the page; nothing written | Rendered by the unkeyed fallback block |
| Edit tag-apply failure after commit | `set_product_tags` raises; `description` + `tags` posted | 302 to detail; BOTH "Product updated successfully!" and "the product was saved, but its tags were not…" are flashed | Success first, failure after |
| Partial POST re-rendered | product has manufacturer/mpn/notes/tags stored; POST carries only `description=''` | 200 re-render whose manufacturer, mpn, category_path, notes and tags inputs carry the STORED values | Description shows the required-field error |
| Explicit clear survives the merge | stored `manufacturer='TI'`; POST carries `description=''` + `manufacturer=''` | 200 re-render with an EMPTY manufacturer input | Submitted empty beats stored value |
| Re-posting a re-rendered form clears nothing | the re-render above, corrected and re-posted verbatim | 302; every optional field keeps its stored value | No silent clearing |
| Backend failure re-render | `update_product` returns false on a partial POST | 200 re-render, same merge applied, "Failed to update product." flashed | No stored value shown as blank |

</intent-contract>

## Code Map

- `app/main/routes.py:853-937` -- `_validate_product_form`; lines 877-880 (receipt limits), 885-889 (`quantity`), 897-921 (identifier rules) move to the create-only validator; 871-876 (description + `_PRODUCT_FIELD_LIMITS`), 923-927 (FR41 gate) and 929-936 (tags) stay shared.
- `app/main/routes.py:786-790, 796, 798-801` -- `_RECEIPT_FIELD_LIMITS`, `_IDENTIFIER_VALUE_LIMIT`, `_MAX_INT32`: the create-only constants. Unchanged.
- `app/main/routes.py:1003-1017` -- `_product_form_data`, the stored baseline for the merge.
- `app/main/routes.py:1222` -- `product_add`'s validator call; switches to the create-only entry point.
- `app/main/routes.py:1244-1272` -- `product_add`'s collect-then-flash block; the shape `product_edit` copies.
- `app/main/routes.py:2384-2443` -- `product_edit`: the validator call (2405), the three re-render sites (2409-2411, 2428-2429, 2442-2443) and the early-return tag failure (2430-2436).
- `app/templates/product/edit.html:13-77` -- the Product Information card; the six rendered fields and their five keyed feedback blocks. `notes` (73) has none.
- `app/templates/product/add.html:120-212` -- the identifier + receipt blocks that only the create form renders (context; unchanged).
- `tests/unit/test_product_routes.py:870-889` -- `test_a_post_save_tag_failure_on_edit_redirects_too`; asserts the OLD behavior, must be inverted.
- `tests/unit/test_product_routes.py:107-127` -- `test_edit_blank_description_rerenders` / `test_edit_omitted_field_left_unchanged`; the round-trip and partial-update pins the merge must keep green.
- `tests/unit/test_product_routes.py:1388-1394` -- `test_the_gate_does_not_leak_into_the_edit_form`; the FR41-on-edit pin.
- `tests/unit/test_product_routes.py:2404-2432` -- `TestNoErrorRendersNowhere`; the add-form half of the same defect class.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- Split `_validate_product_form` into the shared base (description, `_PRODUCT_FIELD_LIMITS`, tags, FR41 gate) and a create-only function that calls the base then adds the receipt, `quantity` and identifier rules; point `product_add` at the create-only one and leave `product_edit` on the base -- so the edit form stops inheriting rules for fields it does not render (DW-13, DW-29) while the FR41 gate stays shared.
- [x] `app/main/routes.py` -- In `product_edit`, build the re-render `form_data` by merging the submitted mapping over `_product_form_data(product, service.get_tags_for_product(product_id))`, at all three re-render sites -- so an absent key round-trips its stored value instead of a blank (DW-52).
- [x] `app/main/routes.py` -- In `product_edit`, collect the tag-apply failure into a list, flash `'Product updated successfully!'` unconditionally, then flash the collected failures, then redirect -- so both forms tell one story about a committed row with a failed follow-up (DW-30).
- [x] `app/templates/product/edit.html` -- Add a block that renders every `validation_errors` entry whose key has no field on this form (currently `confirm_duplicate`; structurally, anything the shared validator gains later), placed where the operator will see it -- so a shared rule can never produce a silent 200 again.
- [x] `tests/unit/test_product_routes.py` -- Invert `test_a_post_save_tag_failure_on_edit_redirects_too` to assert the success flash IS present beside the failure, recording the reason in its docstring the way the `product_add` sibling at :841-868 does.
- [x] `tests/unit/test_product_routes.py` -- Add unit tests covering every row of the I/O matrix: the add-only rules ignored on edit and still enforced on add, the FR41 gate visibly refused on edit, the collect-then-flash pair, and the merge (partial POST round-trip, explicit clear, re-post clears nothing, backend-failure re-render).

**Acceptance Criteria:**
- Given a product with stored optional fields, when a client POSTs only `description=''` to `/products/edit/<id>` and then re-posts the returned form with a valid description, then every optional field retains its stored value and no field is silently cleared.
- Given `_validate_product_form`'s shared half emits any error key, when `edit.html` renders that error, then the message appears in the response body whether or not the key names a field the template renders.
- Given a POST to `/products/edit/<id>` carrying only fields the edit form does not render alongside a valid description, when the route runs, then it answers 302 and writes the description.
- Given `_apply_product_tags` fails after `update_product` committed, when `product_edit` returns, then the response is a redirect to the detail page carrying both the success flash and the failure flash, in that order.
- Given the whole change, when `nox -s tests` runs, then every pre-existing product-route test still passes except the one deliberately inverted for DW-30.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 2: (high 0, medium 0, low 2)
- reject: 8: (high 0, medium 0, low 8)
- addressed_findings:
  - `[medium]` `[patch]` The merge moved `get_tags_for_product` onto the POST path OUTSIDE the `try`, so a transient read failure became an HTML 500 on a page whose every other failure is a flash and a re-render — and in service of a display-only concern. Guarded it: an unreadable baseline logs a warning and degrades to the pre-DW-52 submitted-values-only render. Pinned by `test_an_unreadable_baseline_degrades_instead_of_500ing`.
  - `[low]` `[patch]` `_validate_product_form`'s docstring claimed the unkeyed fallback makes shared rules "visible on both forms"; only `edit.html` got the block. Corrected to state what is true, including that a `notes`-keyed rule would be homeless on both templates.
  - `[low]` `[patch]` `_input_value` / `_textarea_value` compared and re-posted RAW attribute text, so the round-trip helper would have re-posted `&amp;` and called it lossless. Both now `html.unescape`, `_input_value` asserts the attribute exists instead of returning None, and `TestTheEditRerenderCarriesStoredValues` seeds a manufacturer carrying `&`, `<` and `"`.
  - `[low]` `[patch]` Three comments left stale by the validator split: `product_add`'s docstring routed the reader to `_validate_product_form` for the gate, `test_an_unusable_quantity_rerenders_and_writes_nothing` still claimed "no caller can bypass it", and `test_the_gate_does_not_leak_into_the_edit_form` claimed nothing about editing changes. All three retargeted.
  - `[low]` `[patch]` The "explicit clear survives the merge" matrix row was exercised on `manufacturer` only. Added `test_an_explicit_tag_clear_survives_the_merge_and_then_lands`, since `tags` is the field whose absence is read by `_form_tags` rather than by the `field in form_data` loop.

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 2: (high 0, medium 0, low 2)
- reject: 13: (high 0, medium 0, low 13)
- addressed_findings:
  - `[medium]` `[patch]` The stored baseline was read EAGERLY on every edit POST — including the successful ones that discard the merge — and its degraded path was silent. Silent was the dangerous half: the degraded page renders every omitted field blank, and blank is this form's own spelling of "clear this", so a re-post of the page as handed converts a transient read failure into a wiped manufacturer/mpn/category/notes/tags. Now a `_render_data()` closure called only at the three re-render sites, which flashes a warning when the baseline is unreadable and logs the traceback the route's other handlers log. Pinned by `test_a_successful_save_never_reads_the_baseline` and an extra assertion on `test_an_unreadable_baseline_degrades_instead_of_500ing`.
  - `[low]` `[patch]` `_validate_product_form`'s docstring — itself rewritten by the previous review pass — claimed a `notes`-keyed rule would be homeless on BOTH templates. `notes` is deliberately absent from `edit.html`'s `keyed_error_fields`, so the fallback catches it there; only `add.html` leaves it homeless. Corrected.
  - `[low]` `[patch]` `keyed_error_fields` is template knowledge hand-copied into a Jinja list with nothing keeping the copy honest — delete an `invalid-feedback` block and that error renders nowhere again, with no test failing. Added `test_every_field_the_fallback_skips_still_has_its_own_slot`, parametrized over all five names, asserting from both sides (message present, and NOT via the fallback).
  - `[low]` `[patch]` `test_an_add_only_field_is_ignored_rather_than_refused` asserted only a 302 and the written description, so a regression that made `product_edit` record a Purchase or attach the scanned identifier would have passed. Now asserts no Purchase and no new identifier — "ignored" in both directions.
  - `[low]` `[patch]` `_input_value`'s `\bvalue="` anchor also matches inside a hyphenated attribute name, so a `data-value="…"` rendered before the real attribute would be returned in its place. Anchored on whitespace instead.

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 0, low 3)
- defer: 1: (high 0, medium 0, low 1)
- reject: 14: (high 0, medium 0, low 14)
- addressed_findings:
  - `[low]` `[patch]` `test_every_field_the_fallback_skips_still_has_its_own_slot` — the test added last pass to catch a deleted `invalid-feedback` block — passed vacuously for `description`, the one required field on the form. Its slot always renders, and its placeholder is `A Label Description is required.`, which CONTAINS the validator's `Label Description is required.`, so `assert message in body` held on a page carrying no error at all. Now asserted against `_shown_keyed_errors()`, which extracts only blocks rendered with `d-block` (what makes one visible). Mutation-checked: deleting the slot and neutering its `{% if %}` while leaving the placeholder both fail now; the second passed before.
  - `[low]` `[patch]` `test_a_keyed_error_is_not_duplicated_by_the_fallback`'s `body.count('Label Description is required.') == 1` was true of every render of this template for the same substring reason, so only its `id="form-error-…"` assertion did any work. Counted over the shown feedback blocks instead.
  - `[low]` `[patch]` `keyed_error_fields` was pinned in one direction only: the previous pass's test iterates names hand-copied into its own parametrize list, so adding a field to the TEMPLATE list without giving it a feedback block silenced that key with nothing failing. The list is now a single class constant read by both, plus `test_the_parametrized_names_are_the_templates_own_list`, which parses `edit.html`'s literal and requires the two to name the same fields. Mutation-checked by adding `notes` to the template list. Tightening the comparison also exposed that the `tags` row asserted a prefix (`'Tag is too long: 100 characters'`) rather than the whole message; it now carries the full text.
  - `[low]` `[defer]` DW-159 — the GET branch of `product_edit` makes the same stored-baseline read `_render_data` guards, unguarded, so it 500s where the POST path degrades with a warning.
- rejected (notable): scoping the FR41 gate to the create route, on the argument that `product_edit` cannot create a product and the gate is cleared by re-posting the page it refuses — a third pass re-litigating an explicit `<intent-contract>` **Always**, and the bypass it demonstrates predates the change. Two findings were already-recorded deferrals rediscovered (`add.html` has no unkeyed fallback → DW-158; an absent `description` merges the stored value back under a "required" error → DW-157), so they were not re-appended. The rest were style or restatement: the `_validate_product_form` / `_validate_product_create_form` naming, the single-element `followup_errors` list, comment volume, `_render_data` mixing the request-start `product` snapshot with a fresh tag read (the template renders that same snapshot in its heading), the degraded page remaining submittable (recorded as an accepted residual risk two passes ago), and coverage of code paths that call the identical closure.

## Design Notes

The two halves of the DW-13/DW-29 fix are complementary, not alternatives. Scoping is the correctness fix — `product_edit` should not refuse a write because of `quantity`, a field it never reads. The unkeyed fallback is the safety net, and it is required rather than optional because the FR41 gate is deliberately left shared: `confirm_duplicate` is an error key `product_edit` can still emit with no field to hang it on. Together they make "an error renders nowhere" unreachable on the edit form for every present and future shared rule, which is the invariant `TestNoErrorRendersNowhere` already pins on the add side.

The merge direction matters and is easy to get backwards. Stored values are the BASE and submitted values are the OVERLAY:

```python
form_data = request.form.to_dict()
stored = _product_form_data(product, service.get_tags_for_product(product_id))
render_data = {**stored, **form_data}
```

`request.form.to_dict()` contains a key for every field the client actually sent, including ones sent empty — so `manufacturer=''` overlays and renders empty (an explicit clear survives), while a key the client omitted falls through to the stored value. Only the render mapping is merged; `update_product` and `_form_tags` keep reading the unmerged `request.form`, or the partial-update rule the merge exists to protect would itself be broken.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass; the only pre-existing test whose assertions changed is `test_a_post_save_tag_failure_on_edit_redirects_too`.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (no `app/utils/` change is planned; run to confirm none leaked in).

**Manual checks (if no CLI):**
- `app/templates/product/edit.html` renders no `quantity`, `vendor`, `vendor_sku`, `order_number`, `identifier_type` or `identifier_value` input after the change.

## Auto Run Result

Status: `done` — third review pass over an already-`done` spec. No intent gap and no spec defect: the implementation still matches the intent contract, and the three findings acted on were patch-level and test-only.

**Implemented change (unchanged from the prior runs):** `_validate_product_form` is the shared base (description, `_PRODUCT_FIELD_LIMITS`, tags, FR41 gate); `_validate_product_create_form` adds the receipt/`quantity`/identifier rules and is called by `product_add` alone. `edit.html` renders any error key it has no message slot for. `product_edit` merges submitted values over the stored baseline at all three re-render sites via a `_render_data()` closure, and collects its post-commit tag failure so the success flashes unconditionally first.

**Files changed this pass:** `tests/unit/test_product_routes.py` only — no application code or template changed, so no screenshot regeneration was needed.
- Added `_shown_keyed_errors()`, which extracts only the feedback blocks rendered with `d-block`, and pointed the two assertions that were satisfied by `description`'s always-rendered placeholder at it.
- Made `keyed_error_fields` a single `KEYED_FIELD_CASES` constant feeding the parametrize, and added `test_the_parametrized_names_are_the_templates_own_list`, which parses `edit.html`'s own literal so a name added to the template list without a feedback block fails.
- Corrected the `tags` row from a message prefix to the full message.

**Findings breakdown:** 3 patches applied (all low); 1 deferred (DW-159); 14 rejected. Two of the rejections were rediscoveries of DW-157 and DW-158, deliberately not re-appended to the ledger; the largest was a third attempt to scope the FR41 duplicate gate out of `product_edit`, which the intent contract names as an explicit **Always**.

**Verification:** `nox -s tests` → 2752 passed, 427 deselected. `nox -s doctests` → 21 passed. Each strengthened assertion was mutation-checked against the defect it is supposed to catch — deleting the `description` feedback block, leaving the block but neutering its `{% if %}` so only the placeholder renders, and adding `notes` to the template's `keyed_error_fields` — and all three now fail. The second of those passed under the old assertions, which is the finding.

**Residual risks:**
- `test_the_parametrized_names_are_the_templates_own_list` reads `edit.html` with a regex, so it is coupled to the literal's spelling; it fails loudly with a named message if the fallback changes shape, but it is still a test that parses a template. DW-158 records the macro-sharing refactor that would remove the duplication rather than pin it.
- The degraded-baseline path and the GET/POST asymmetry it creates are unchanged from the previous pass; the latter is now recorded as DW-159.
