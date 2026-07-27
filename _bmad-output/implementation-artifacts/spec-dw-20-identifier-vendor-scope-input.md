---
title: 'DW-20: vendor-scope input for the create form''s Scanned Identifier block'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: '20aaeb8'
final_revision: '11fbfa4'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** The product create form's Scanned Identifier block offers every `IdentifierType` except `INTERNAL` — including the three vendor-scoped ones (`VENDOR_SKU`, `ASIN`, `FNSKU`) — while `_attach_scanned_identifier` deliberately passes no `vendor`, so choosing one of those types stores `vendor_scope=''`, the sentinel meaning "global". A second vendor's identical SKU then collides on `uq_product_identifiers_type_value_scope` instead of coexisting.

**Approach:** Give the Scanned Identifier block its own vendor-scope input (`identifier_vendor`), pass it to `add_identifier` as `vendor`, and refuse a vendor-scoped type submitted without it — before the write, like every other identifier rule on this form. The field is the identifier block's own, never defaulted from the First Receipt block's `vendor`.

## Boundaries & Constraints

**Always:**
- The new input is named and id'd `identifier_vendor`, lives inside the `#scanned-identifier` card, and is never pre-populated from the First Receipt `vendor` field or from anything but its own value.
- Vendor-scoping authority stays `app/models.py:VENDOR_SCOPED_IDENTIFIER_TYPES` (AD-9). Routes import that frozenset; nothing re-lists the three types by hand, and the template never imports the enum — it receives the list from the route, exactly as `identifier_type_choices` is passed today.
- Every check makable from the form alone runs in `_validate_product_create_form` before `create_product` commits, because `_attach_scanned_identifier` is non-fatal and there is still no surface to add an identifier afterwards.
- Identifier-block rules stay gated on a non-blank `identifier_value`: the card (and therefore every `invalid-feedback` slot in it) renders only when one is present, so an error raised beside a blank value would render nowhere.
- Existing behavior for globally-scoped types is unchanged: `add_identifier` ignores `vendor` for them and still stores `vendor_scope=''`.

**Block If:**
- `VENDOR_SCOPED_IDENTIFIER_TYPES` turns out not to be importable into `app/main/routes.py` without a circular import.

**Never:**
- No JS. No client-side show/hide of the new field, no new static asset, no change to `field-autocomplete.js` or its auto-init list — the input is always rendered whenever the card is, and enforcement is server-side only.
- No schema change, no migration, no change to `add_identifier`'s signature or its scope computation.
- No new identifier-management surface on the product detail page; DW-20 is the create form only.
- Do not narrow `_identifier_type_choices()` — the human chose option 2 over option 1.
- Do not touch the First Receipt block's `vendor` field, `_RECEIPT_FIELDS`, or `_record_first_receipt`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Vendor-scoped type with its own scope | POST `identifier_type=VENDOR_SKU`, `identifier_value=296-1234-ND`, `identifier_vendor=DigiKey`, `vendor=Mouser` | 302; identifier row `vendor_scope == 'DigiKey'`; the Purchase's vendor is `Mouser` | No error expected |
| Two vendors, same SKU | Two products, same `VENDOR_SKU` value, different `identifier_vendor` | Both persist; no uniqueness collision | No error expected |
| Vendor-scoped type, scope omitted | POST `identifier_type=ASIN`, `identifier_value=B00X`, no `identifier_vendor` | 200 re-render, no product created | Field error on `identifier_vendor` naming the vendor-scoped types |
| Vendor-scoped type, scope blank but receipt vendor set | POST `identifier_type=VENDOR_SKU`, `identifier_value=X`, `vendor=DigiKey`, blank `identifier_vendor` | 200 re-render, no product created — the receipt vendor is never borrowed | Same field error on `identifier_vendor` |
| Global type with a scope typed anyway | POST `identifier_type=GTIN`, `identifier_value=00012345678905`, `identifier_vendor=DigiKey` | 302; identifier row `vendor_scope == ''` (service ignores it, unchanged) | No error expected |
| Over-long scope | `identifier_vendor` of 256 chars beside a vendor-scoped type | 200 re-render, no product created | Field error on `identifier_vendor` stating the 255 limit |
| Blank identifier value | POST with blank `identifier_value` and any `identifier_vendor` | 302; nothing attached, no vendor rule fires | No error expected |
| Pre-fill and round-trip | GET `?identifier_value=X&identifier_type=VENDOR_SKU&identifier_vendor=DigiKey`; and a POST that fails another field | The input renders carrying `DigiKey`, editable, in both cases | No error expected |

</intent-contract>

## Code Map

- `app/main/routes.py:17` -- `from app.models import (...)`; add `VENDOR_SCOPED_IDENTIFIER_TYPES`.
- `app/main/routes.py:809` -- `_IDENTIFIER_VALUE_LIMIT`; the new vendor-scope limit constant goes beside it.
- `app/main/routes.py:933-1000` -- `_validate_product_create_form`; identifier rules at ~958-1000, where the two new rules go.
- `app/main/routes.py:1115` -- `_PRODUCT_PREFILL_ARGS`; `identifier_vendor` joins the identifier pair.
- `app/main/routes.py:1127` -- `_identifier_type_choices()`; the vendor-scoped-choices helper goes beside it.
- `app/main/routes.py:1187-1226` -- `_attach_scanned_identifier`; its docstring currently explains why no `vendor` is passed, and it now passes one.
- `app/main/routes.py:1275-1293` -- `_render_product_add`; the single render, where the new template context is added.
- `app/templates/product/add.html:125-172` -- the `#scanned-identifier` card; the new field is a second row inside it.
- `app/mariadb_catalog_service.py:1809` / `:1887-1892` -- `add_identifier` and its scope computation (AD-9). Read-only reference; unchanged.
- `app/models.py:172-178` -- `VENDOR_SCOPED_IDENTIFIER_TYPES`, the scoping authority.
- `tests/unit/test_product_routes.py:2200` -- `TestScannedIdentifierTyping`, incl. `test_the_receipt_vendor_does_not_become_the_identifier_scope:2235`, which pins today's behavior and must be rewritten.
- `tests/unit/test_product_routes.py:1379` -- `TestProductAddPrefill`, incl. `test_every_whitelisted_arg_reaches_the_rendered_form` and `test_prefilled_values_stay_editable`.

## Tasks & Acceptance

**Execution:**
- [x] `app/main/routes.py` -- import `VENDOR_SCOPED_IDENTIFIER_TYPES`; add `_IDENTIFIER_VENDOR_LIMIT = 255` with a comment naming `product_identifiers.vendor_scope` (a different column from `product_identifiers.value`, kept as its own constant for the same reason `_RECEIPT_FIELD_LIMITS` is separate from `_PRODUCT_FIELD_LIMITS`); add `_vendor_scoped_identifier_type_choices()` returning `[t.value for t in IdentifierType if t in VENDOR_SCOPED_IDENTIFIER_TYPES]` — iterating the enum, not the frozenset, so the order is the declaration order and the rendered help text is stable.
- [x] `app/main/routes.py` -- in `_validate_product_create_form`, after the existing type rules: gated on a non-blank `identifier_value`, refuse a blank `identifier_vendor` when `identifier_type` is one of the vendor-scoped choices, and refuse an `identifier_vendor` longer than `_IDENTIFIER_VENDOR_LIMIT`. Both errors key `identifier_vendor`. Follow the file's first-writer-wins convention.
- [x] `app/main/routes.py` -- add `identifier_vendor` to `_PRODUCT_PREFILL_ARGS` beside `identifier_type`/`identifier_value`, so all three of the block's fields pre-fill and round-trip alike.
- [x] `app/main/routes.py` -- `_attach_scanned_identifier`: pass `vendor=(form_data.get('identifier_vendor') or '').strip() or None` and replace the "No `vendor` is passed" docstring paragraph with the reason one now is, naming the separate input.
- [x] `app/main/routes.py` -- `_render_product_add`: pass `vendor_scoped_identifier_types=_vendor_scoped_identifier_type_choices()` alongside `identifier_type_choices`.
- [x] `app/templates/product/add.html` -- inside `#scanned-identifier`, add a row with a `Vendor Scope` labelled `<input type="text" id="identifier_vendor" name="identifier_vendor" maxlength="255" autocomplete="off">` carrying `form_data.get('identifier_vendor', '')`, with the `is-invalid` / `invalid-feedback d-block` pattern the sibling fields use, and a `form-text` that names the vendor-scoped types from `vendor_scoped_identifier_types`, says it is the namespace the identifier is unique within, says it is ignored for other types, and says explicitly that it is not the First Receipt block's Vendor.
- [x] `tests/unit/test_product_routes.py` -- rewrite `test_the_receipt_vendor_does_not_become_the_identifier_scope` so it proves the scope comes from `identifier_vendor` and not from `vendor` (both submitted, different values), and add tests for every remaining I/O Matrix row: missing scope refused, receipt vendor never borrowed for a blank scope, global type still scoped `''`, over-long scope refused pre-write, two vendors' identical SKUs coexisting, blank value bypassing the rule, and the field rendering/pre-filling/round-tripping editably inside the card and being absent without one.
- [x] `tests/unit/test_product_routes.py` -- extend `test_every_whitelisted_arg_reaches_the_rendered_form` and `test_prefilled_values_stay_editable` to cover `identifier_vendor`.

**Acceptance Criteria:**
- Given a create form rendered with a scanned identifier, when the page loads, then the Scanned Identifier card contains an editable `identifier_vendor` input and the First Receipt card's `vendor` input is unchanged and independent.
- Given a create form rendered without a scanned identifier value, when the page loads, then neither the card nor `identifier_vendor` appears, and the hand-driven create path is unchanged.
- Given a vendor-scoped identifier type and a non-blank `identifier_vendor`, when the form is saved, then the stored row's `vendor_scope` is exactly the trimmed `identifier_vendor` and any First Receipt vendor is recorded only on the Purchase.
- Given any refusal of the identifier vendor scope, when the form re-renders, then no Product was created and the message appears in the `identifier_vendor` field's own `invalid-feedback` slot inside the card.
- Given the existing suite, when `nox -s tests` runs, then it is green — no test outside the create-form identifier path changes behavior.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 3, low 4)
- defer: 4: (high 0, medium 2, low 2)
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[medium]` `[patch]` The duplicate path's two captions ("an identifier is unique across the catalog — saving will report that it could not be attached", and the warning block's "it cannot be attached here as well") became false once a scope existed: the same `VENDOR_SKU` under a different vendor is a different key and attaches successfully. Both now state the uniqueness *rule* ("unique within its scope") rather than predicting an outcome that depends on a Type and Vendor Scope the operator can still change after the page renders.
  - `[medium]` `[patch]` `docs/user-manual.md` documented the Scanned Identifier card field-by-field, listed the pre-write refusals as "those three", and asserted "An identifier is unique across the whole catalog" — all stale. Added the Vendor Scope field, both new refusals, the corrected uniqueness statement, and the two rewritten captions.
  - `[medium]` `[patch]` Added the coverage the first pass missed: all three vendor-scoped types round-tripping a scope (`FNSKU` was never exercised), the 255 boundary (only 256 was refused, which is equally consistent with an off-by-one), the stored scope being trimmed (surrounding space decides namespace identity), a blank/unrecognised type suppressing both new rules, and the duplicate path both attaching under a distinct scope and rendering the corrected caption.
  - `[low]` `[patch]` `_attach_scanned_identifier`'s docstring said a blank "becomes None, which the service treats as no vendor" — wrong, and wrong about the exact fact DW-20 exists over: the service stores `None` as `''`, the GLOBAL sentinel. Reworded so the validator, not any service degradation, is named as what keeps a blank from reaching it.
  - `[low]` `[patch]` `_vendor_scoped_identifier_type_choices()` was documented as "the offered types" but filtered the raw enum without intersecting `_identifier_type_choices()`. Intersected, so a future exclusion cannot put an unofferable type into the help text or into a rule that could never fire for it.
  - `[low]` `[patch]` The missing-scope message recited all three vendor-scoped types and then said "for this type", making the operator work out which one they had selected — and pinned the enum's declaration order into rendered text. It now names the chosen type.
  - `[low]` `[patch]` Reworded that same message from "A {TYPE} identifier" to "{TYPE} identifiers", the article being ungrammatical for `ASIN`.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 7: (high 0, medium 2, low 5)
- defer: 3: (high 0, medium 1, low 2)
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[medium]` `[patch]` The duplicate-path caption offered an escape hatch that does not exist on the only duplicate path an operator can reach. `_scan_banner_args` puts `identifier_type=GTIN` on the "create a separate product instead" link and no other type, and `add_identifier` discards `vendor` for a globally-scoped type — so "saving will report that it could not be attached unless you give it a Vendor Scope no other product holds" was telling every real arrival to fill in a box that cannot change the outcome. The caption now branches on the chosen type, using the template's existing `vendor_scoped_identifier_types` context; the global branch states the catalog-wide rule and names no Vendor Scope.
  - `[medium]` `[patch]` `docs/user-manual.md` quoted the missing-scope refusal as `A VENDOR_SKU identifier is unique per vendor, so Vendor Scope is required for it.` — the pre-reword string. The code emits `VENDOR_SKU identifiers are unique per vendor, so Vendor Scope is required.` The manual quotes messages verbatim as a convention and nothing pins it in CI, so the drift was invisible. Corrected, and the duplicate caption's quotation rewritten for both branches.
  - `[low]` `[patch]` `_IDENTIFIER_VENDOR_LIMIT`'s comment (and the matching test docstring) justified the form-side length check by claiming the service's refusal would land under `field='vendor'` and so name the receipt input. `_attach_scanned_identifier` never reads `e.field` — it formats the message into an advisory flash. Reworded to the reason that is actually true: post-commit and non-fatal, so the product would exist with its identifier discarded.
  - `[low]` `[patch]` `test_an_unusable_type_leaves_the_scope_rules_unfired` asserted only on `_shown_keyed_errors(...)[0]`, so a Vendor Scope demand emitted *second* — the exact regression its docstring names — would have passed. Now checked across every rendered message.
  - `[low]` `[patch]` `test_a_blank_scope_is_never_borrowed_from_the_receipt_vendor` used a page-wide `in body` substring, the check `_shown_keyed_errors` exists to prevent. Switched to the helper and to whole-list equality, which also proves nothing else was refused.
  - `[low]` `[patch]` No test pinned the same-scope collision — the negative half of the thesis. Only "two vendors coexist" was asserted, which a scope made unique per request would also satisfy while destroying uniqueness. Added `test_the_same_scope_still_collides`.
  - `[low]` `[patch]` No test covered an offered globally-scoped type with the box empty, so a membership test widened to every type would have gone unnoticed. Added a parametrized `MPN`/`GTIN_UNVALIDATED` case, plus a GTIN duplicate-path test pinning the corrected caption and proving a scope supplied anyway is still discarded.

## Design Notes

**Required, not hidden.** DW-20's decision allows "shown (or required)". This spec takes *required*, always-rendered, and server-side. The form has no create-form JS today (`field-autocomplete.js` does nothing with the identifier block and skips `#vendor` for want of a suggestions div), so a JS reveal would be new client machinery that is not enforcement anyway — and a hidden-but-required field is a form that refuses a submit over a control the operator cannot see. Always rendering it keeps the card's server-side-only conditional rendering intact.

**Why `identifier_vendor` and not `vendor`.** The distinctness the decision asks for is carried by the name, the card it sits in, and the help text — three independent signals, so no later reader has to infer that the two Vendor fields are different things.

**Why the service is untouched.** `add_identifier` already computes `scope` correctly from `vendor` (`app/mariadb_catalog_service.py:1887-1892`); the bug was only that nothing ever supplied one. It also already ignores `vendor` for globally-scoped types (pinned by `test_gtin_ignores_vendor_arg`), which is why a scope typed beside a GTIN is silently dropped rather than made a form error — the form documents that in its help text instead of inventing a second rule the service does not have.

**Why the limit is checked on the form too.** `add_identifier` raises `ValidationError(field='vendor')` for an over-long scope, but it runs after `create_product` has committed and is non-fatal, so the refusal would cost a product its identifier behind an advisory flash — and `field='vendor'` would name the *receipt* input on this form. Checking it pre-write under the `identifier_vendor` key puts the message on the right control.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass, including the new create-form vendor-scope tests.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: pass (no `app/utils/` change, so this is a regression guard only).

**Manual checks (if no CLI):**
- `tests/e2e/screenshot_config.yaml` has no `/products/add` entry and the identifier card renders only with a scanned value, so no screenshot regeneration is required; confirm that remains true after the template edit.

## Auto Run Result

Status: done

### Summary

Follow-up review pass over the DW-20 change (the create form's own `identifier_vendor` input, distinct from the First Receipt block's `vendor`, passed to `add_identifier` as the row's `vendor_scope`). No intent gaps and no spec defects: the implementation matches the contract and the human's option-2 decision. Seven patches were applied, of which the substantive one is a caption that promised an outcome the reachable path cannot deliver — `_scan_banner_args` puts only `identifier_type=GTIN` on the duplicate-create link, and a Vendor Scope does nothing for a globally-scoped type, so the duplicate card was sending every real arrival to a box that could not help them. The caption now branches on the chosen type. The rest were a stale message quotation in the user manual, an inaccurate rationale comment, and four test-quality/coverage gaps in the class added by the first pass.

### Files changed

- `app/templates/product/add.html` — the duplicate-path caption branches on whether the chosen `identifier_type` is vendor-scoped; the global branch states the catalog-wide rule and offers no Vendor Scope escape.
- `app/main/routes.py` — `_IDENTIFIER_VENDOR_LIMIT`'s comment corrected: the form-side length check is justified by the service's refusal being post-commit and non-fatal, not by a `field='vendor'` mislabelling that `_attach_scanned_identifier` never produces (it flashes the message instead).
- `docs/user-manual.md` — the missing-scope refusal quoted as the code emits it; the duplicate caption documented as the two branches it now has.
- `tests/unit/test_product_routes.py` — two assertions tightened (whole-message-list instead of `[0]`; `_shown_keyed_errors` instead of a page-wide substring), one caption test scoped to the card and whitespace-normalised, three tests added (GTIN duplicate caption + a supplied scope still discarded, same-scope collision, offered global types saving with an empty box).
- `_bmad-output/implementation-artifacts/deferred-work.md` — DW-183, DW-184, DW-185 appended.

### Review findings

Blind Hunter + Edge Case Hunter, run in parallel on the diff since `20aaeb8`. intent_gap 0, bad_spec 0, patch 7 (medium 2, low 5), defer 3 (medium 1, low 2), reject 7 (all low). Deferred as DW-183 (pre-DW-20 vendor-scoped rows still hold `vendor_scope=''` with no backfill and no repair surface), DW-184 (the ECIA path knows the distributor but does not pre-fill the scope), DW-185 (DW-181's text describes a `maxlength` on `identifier_value` that does not exist). Rejections: the new field's `maxlength="255"` (spec-mandated and the file's dominant convention — six of eight text inputs carry it); the empty-`vendor_scoped_identifier_types` render (a future state in which the rule could not fire anyway); vendor-scope canonicalization (DW-179); the attach path having no guard of its own (DW-180); the silent discard of a scope typed beside a global type (an explicit Design Note and a recorded residual risk); no visible required marker (the `form-text` under the label states the conditional requirement, and a static `*` would be false for three of six types); no correction path for a mistyped scope (the intent contract's **Never** rules the surface out, and DW-180 holds the question).

### Verification

- `nox -s tests` — 2882 passed, 427 deselected.
- `nox -s doctests` — 21 passed.
- `nox -s e2e` not run: the scan path only ever emits `gtin`, the changed caption is server-rendered with no JS, and no e2e test exercises the duplicate-create form's help text.
- `tests/e2e/screenshot_config.yaml` still has no `/products/add` entry and the card renders only with a scanned value, so no screenshot regeneration is owed. Confirmed after the template edit.

### Residual risks

- DW-183 is the one with live data behind it: the corrected form does nothing for rows already written globally scoped, and nothing in the app can rewrite them.
- The duplicate caption's global branch reads "outside the vendor-scoped types an identifier is unique across the whole catalog" for a blank or unrecognised type too. That submit is refused on `identifier_type` before the claim could matter, but the sentence is being shown beside a type it is not, strictly, describing.
- A scope is still stored as typed apart from `.strip()`, so its uniqueness behaviour differs between the unit suite's SQLite and MariaDB's `utf8mb4_unicode_ci` — DW-179, and the reason no test asserts case behaviour.
