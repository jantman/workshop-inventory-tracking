---
title: 'DW-7: pin the product write path''s identifier trim'
type: 'bugfix'
created: '2026-07-27'
status: 'done'
baseline_revision: 'd461a40'
final_revision: '0359d90'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** DW-7 records that `create_product`/`update_product` store `mpn`/`manufacturer` exactly as submitted, so form or programmatic padding survives into the column and `resolve_scan`'s exact ECIA lookup — which trims its candidate — would miss it. The human decision was to strip those columns at the write path, matching `add_identifier`'s rule.

**Approach:** The decided behaviour is already the actual behaviour: both writers pass `mpn`/`manufacturer` through `_clean`, which `.strip()`s before the blank→NULL coercion, and has since Story 1.3 (commit `612a538`) — DW-7's evidence sentence ("coerces blanks to NULL but does not strip") contradicts the function body. So no behaviour change is warranted, and inventing one would be fabricating a fix. What is genuinely missing is the pinning the decision asked for: no test asserts a *padded-but-non-blank* `mpn`/`manufacturer` stores trimmed, at the service, at the form, or across the scan lookup. Add those tests, and make the write path *say* it is the identifier-trim rule so the same misreading cannot be re-lodged.

## Boundaries & Constraints

**Always:**
- Keep `_clean` as the single trim rule for `manufacturer`/`mpn`; do not add a second per-column stripper beside it.
- Every new test carries `@pytest.mark.unit` and matches the surrounding file's fixture style (`catalog_service` for service tests; `client` + `test_storage` for route tests).
- Assert the *stored* value by reading the row back through `CatalogService.get_product`, not by inspecting the submitted dict.

**Block If:**
- Closing this would require changing what `description`/`notes` store, or bounding `mpn` length the way `add_identifier` bounds identifier values. Both are out of scope; if a finding forces one, HALT.

**Never:**
- Do not touch `description` or `notes` semantics — they are prose, and their existing trim is incidental, not a rule being asserted here.
- Do not change `category_path`. **Explicit decision:** it is normalized by `category_util.normalize_category_path`, which subsumes `_clean` for that column, and `TestCategoryPathNormalization` (`tests/unit/test_catalog_service.py:1323`) already pins it. No change, no duplicate test.
- Do not edit `_bmad-output/implementation-artifacts/deferred-work.md`.
- Do not make `_clean` coerce non-strings via `str()`. `add_identifier` does, but no product write path can deliver a non-string: `request.form` yields `str`, and there is no JSON product-create endpoint.
- No new endpoints, no schema change, no Alembic revision.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Padded MPN, service create | `create_product(description='x', mpn=' RC0805-10K ', manufacturer=' TI ')` | Row stores `mpn == 'RC0805-10K'`, `manufacturer == 'TI'` | No error expected |
| Padded MPN, service update | Product exists; `update_product(pid, mpn=' RC0805-10K ', manufacturer=' TI ')` | Same trimmed values stored | No error expected |
| Padded MPN, create form | `POST /products/add` with `data={'description': 'x', 'mpn': ' RC0805-10K ', 'manufacturer': ' TI '}` | 302; row stores trimmed values | No error expected |
| Padded MPN, edit form | `POST /products/edit/<pid>` with padded `mpn` | 302; row stores trimmed value | No error expected |
| Scan finds a padded-submitted MPN | Product created with `mpn=' RC0805-10K '`; `resolve_scan(_envelope('1PRC0805-10K'))` | `r.product` is that product; `r.free_text_hits == ()` (exact lookup hit, not the search fallthrough) | No error expected |
| Whitespace-only MPN | `mpn='   '` | Stored `NULL` (already pinned by `test_blank_optional_fields_coerced_to_none`) | No error expected |

</intent-contract>

## Code Map

- `app/mariadb_catalog_service.py:123` -- `_clean`: the trim + blank→NULL rule. Already strips; docstring to be amended to name it as the identifier-trim rule.
- `app/mariadb_catalog_service.py:335` -- `create_product`; `mpn`/`manufacturer` go through `_clean` at lines 362-363. Only `Product(...)` construction site in `app/`.
- `app/mariadb_catalog_service.py:439` -- `update_product`; whitelist loop, `_clean` fallback for `manufacturer`/`mpn`/`description`/`notes`. Only `setattr` mutation site.
- `app/mariadb_catalog_service.py:1819` -- `add_identifier`'s strip, the rule DW-7 asks the write path to match.
- `app/mariadb_catalog_service.py:216` -- `_ecia_candidates`' candidate trim; the other half of the agreement.
- `app/main/routes.py:1323`, `:2566` -- the only two callers; neither pre-strips, which is correct because the service owns the rule.
- `tests/unit/test_catalog_service.py:141`, `:199` -- `TestCatalogServiceCreate` / `TestCatalogServiceUpdate`.
- `tests/unit/test_product_routes.py:99` -- `TestProductRoutes` (`_make_product` helper at `:101`).
- `tests/unit/test_scan_resolution.py:654` -- `TestEciaResolution`; `MPN` constant at `:95`, `_envelope` at `:80`, `catalog_service` fixture at `:193`.

## Tasks & Acceptance

**Execution:**
- [x] `app/mariadb_catalog_service.py` -- amend `_clean`'s docstring to state that the trim IS the write path's identifier rule and that it agrees with `add_identifier` (`:1819`) and `_ecia_candidates` (`:216`); note that non-string coercion is deliberately not copied because no product write path can deliver one. Comment-only; no behaviour change.
- [x] `tests/unit/test_catalog_service.py` -- add a padded-`mpn`/`manufacturer` create test to `TestCatalogServiceCreate` and a padded update test to `TestCatalogServiceUpdate`, each asserting the trimmed stored value and naming DW-7's cross-path concern in the docstring.
- [x] `tests/unit/test_product_routes.py` -- add create-form and edit-form padding tests to `TestProductRoutes`, posting `data={...}` with padded values and reading back through `CatalogService(test_storage).get_product`.
- [x] `tests/unit/test_scan_resolution.py` -- add a test to `TestEciaResolution` that stores a *padded* `mpn` and resolves an unpadded `1P` envelope, asserting the exact lookup hits and `free_text_hits == ()`; it is the mirror of `test_a_padded_part_number_still_matches_exactly` (`:762`), which pads the scan instead of the column.

**Acceptance Criteria:**
- Given the two product write methods, when the suite runs, then every stored-side trim assertion in the I/O matrix passes without any change to `_clean`'s behaviour.
- Given a product whose `mpn` was submitted with padding, when a clean ECIA label carrying that part number is resolved, then it matches on the exact lookup rather than degrading to the free-text fallthrough.
- Given `category_path`, when this spec is implemented, then no test and no code line for it changed, and the reason is recorded in this spec.
- Given the deferred-work ledger, when this spec is implemented, then `deferred-work.md` is unmodified.

## Spec Change Log

## Review Triage Log

### 2026-07-27 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 0, low 6)
- defer: 3: (high 0, medium 1, low 2)
- reject: 6
- addressed_findings:
  - `[low]` `[patch]` The new scan test's docstring justified itself backwards, claiming `free_text_hits == ()` was the load-bearing assertion and that `r.product` "passes either way". Verified false by storing a padded `mpn` directly and resolving: the regression yields `product=None` with the row in `free_text_hits`, so the product assertion fails first. Docstring rewritten to name the actual regression shape and to state that the hits assertion restates the product one (`ScanResolution` forbids holding both at once).
  - `[low]` `[patch]` `_clean`'s new docstring claimed a non-string value "should surface, not be silently stringified into a column". Verified false: `create_product(description='x', mpn=1234567890)` returns a valid id and the column holds `'1234567890'`. Replaced with what actually happens.
  - `[low]` `[patch]` `_clean`'s docstring ran 27 lines of `mpn`/ECIA rationale on a helper shared by `description`, `notes` and four purchase columns, and overstated two things: the `_ecia_candidates` agreement (that function ALSO drops what `sql_text.is_storable_text` rejects; this side does not) and the exact-lookup consequence (MariaDB's `utf8mb4_unicode_ci` is PAD SPACE, so a trailing-only pad compares equal in production and only leading whitespace bites on both backends). Rewritten shorter, framed as the shared helper it is, with both limits stated.
  - `[low]` `[patch]` `_ecia_prefill` (`app/main/routes.py`) still said the pre-fill trim happens "here, at the pre-fill boundary, and nowhere else" — now directly contradicted by the write-path docstring, on a change whose whole deliverable is making the code say the right thing. Corrected to state what that boundary uniquely owns rather than exclusivity.
  - `[low]` `[patch]` `_clean`'s docstring asserts a cross-home agreement with `add_identifier`'s `MPN` rows that no test covered — the existing identifier tests pin only the blank and non-string cases. Added `TestCatalogServiceIdentifiers::test_padded_value_is_stored_trimmed`.
  - `[low]` `[patch]` The new create test's docstring called its sibling "the blank case above ... a different rule", but that sibling also asserts `description == 'Widget'` trimmed and therefore already fails on a lost trim. Docstring corrected to concede the overlap and state what this test actually adds.

### 2026-07-27 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 0, low 5)
- defer: 3: (high 0, medium 1, low 2)
- reject: 10
- addressed_findings:
  - `[low]` `[patch]` `_clean`'s new docstring enumerated "a purchase's `vendor`, `vendor_sku`, `order_number` and `source_url`" as columns it cleans. Verified false: `record_amazon_purchase` (`app/mariadb_catalog_service.py:1676`) sets `vendor=(scope or None)` and `vendor_sku=asin` directly, bypassing `_clean`; only `record_purchase` routes all four through it. The list shipped stale on a change whose deliverable is prose accuracy. Rewritten to name `record_purchase` as the caller and `record_amazon_purchase` as the writer that does not, and to say a caller list is not a column guarantee.
  - `[low]` `[patch]` The new scan test's docstring claimed "nothing at all fails today if one of them stops stripping while the other keeps going." Verified false in both directions: `test_blank_optional_fields_coerced_to_none` (`tests/unit/test_catalog_service.py:174`) asserts `description == 'Widget'` from `'  Widget  '` and so already fails on a lost `_clean` strip, and `test_a_padded_part_number_still_matches_exactly` covers the query side. The commit's own create-test docstring concedes the first of these two files away. Rewritten to state what the test actually adds: that the two trims must produce the SAME spelling, which a suite checking each in isolation never asks.
  - `[low]` `[patch]` `_ecia_prefill`'s rewritten docstring said the trim happens "at the boundary that produces the padding". That function consumes padding; the label prints it and `ecia.parse_fields` preserves it. Corrected to "the first boundary that has any business removing it", naming both upstream producers.
  - `[low]` `[patch]` `_clean`'s PAD SPACE sentence said "a trailing-only pad ... compares equal in production". PAD SPACE pads U+0020 and nothing else, so a trailing tab or newline misses on both backends — the sentence claimed more than the collation gives, on the one line stating a production-only behaviour no test can reach. Narrowed to ordinary spaces with the exclusion stated.
  - `[low]` `[patch]` Every new docstring rests on `_ecia_match` consulting BOTH homes of a part number (verified: `app/mariadb_catalog_service.py:2308`, one query over `Product.mpn` and an `MPN` identifier `exists()`), but only the column home had an end-to-end `resolve_scan` assertion; the identifier home had the strip pinned and the consequence unpinned. Added `test_a_padded_stored_identifier_row_still_matches_a_clean_label` to `TestEciaResolution`, the mirror of the existing `test_a_supplier_part_number_matching_an_mpn_identifier_row_resolves`. Mutation-checked: removing `add_identifier`'s `.strip()` fails it and `test_padded_value_is_stored_trimmed`, and nothing else.

## Design Notes

The "by hand and by JSON" phrasing in the decision comes from DW-7's claim that the defect is "reachable ... from any JSON client". There is no JSON product-create or product-edit endpoint: `/products/add` and `/products/edit/<id>` read `request.form` only, and the JSON endpoints under `/api/` cover scan, purchases, inventory and photos. The programmatic surface a JSON client would reach is therefore `CatalogService.create_product` / `update_product` themselves, which is what the service-level tests cover — that is the honest reading, recorded here so the coverage is not mistaken for a missing endpoint test.

The scan test is the one that earns its keep: the two halves of the agreement live in different modules (`_clean` strips what is stored, `_ecia_candidates` strips what is queried), and nothing today fails if one of them stops stripping while the other keeps going.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: full unit suite green, including the new tests.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: green (guards the `app/utils/` docstring examples; unaffected but cheap).
- `git diff --stat -- _bmad-output/implementation-artifacts/deferred-work.md` -- expected: empty output.

## Auto Run Result

Status: `done`

**Implemented change.** DW-7 asked that `create_product`/`update_product` strip `mpn`/`manufacturer` at the write path. Both already do: each routes those columns through `_clean`, which `.strip()`s before the blank->NULL coercion, and has since Story 1.3 (`612a538`) — DW-7's evidence sentence ("coerces blanks to NULL but does not strip") is contradicted by the function body. `create_product` is the only `Product(...)` construction site in `app/` and `update_product`'s `setattr` loop the only mutation site, so the invariant is genuinely closed. No behaviour change was made. What the decision actually asked for and was missing is the pinning, plus prose that stops the same misreading being re-lodged.

**Files changed (cumulatively, since `d461a40`):**
- `app/mariadb_catalog_service.py` -- `_clean` docstring only, function body untouched: records that the trim is the write path's half of the part-number agreement with `add_identifier` and `_ecia_candidates`, names its callers honestly (including the one purchase writer that bypasses it), and states the limits of that agreement.
- `app/main/routes.py` -- `_ecia_prefill` docstring only: dropped an "and nowhere else" claim about the trim that the write path contradicts, and named the boundary correctly.
- `tests/unit/test_catalog_service.py` -- 3 tests: padded `mpn`/`manufacturer` trimmed by `create_product`, by `update_product`, and by `add_identifier`.
- `tests/unit/test_product_routes.py` -- 2 tests: the same through `POST /products/add` and `POST /products/edit/<id>`.
- `tests/unit/test_scan_resolution.py` -- 2 tests: a product whose `mpn`, and a product whose `MPN` identifier row, was submitted with padding is still matched by `resolve_scan`'s exact ECIA lookup for a clean label, rather than degrading to the free-text fallthrough.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- three NEW entries appended (DW-176, DW-177, DW-178); no existing entry read, modified or re-opened.

**This pass (follow-up review).** 5 patches applied (all low, four documentation-accuracy and one added test), 3 deferred, 10 rejected, 0 intent gaps, 0 spec defects. See the Review Triage Log.

**Deferred — filed as NEW ledger entries** (the invocation authorized appending new entries; the orchestrator retains ownership of existing ones, and none was touched):
- `DW-176` *(medium)* -- `mpn`/`manufacturer` carrying a NUL or unpaired surrogate is form-reachable and stores, after which `_ecia_candidates` drops it and `search_products` refuses it: the row is unreachable by the identifier it holds. Same defect class as the open DW-160 on `category_path`; the two should be decided together.
- `DW-177` *(low)* -- `str.strip()` removes NBSP but not U+200B/U+FEFF, so a part number pasted from a datasheet — the case the new prose names three times as motivating — stores looking clean and misses the exact lookup permanently.
- `DW-178` *(low)* -- `mpn`/`manufacturer` length is bounded only at the route (`_PRODUCT_FIELD_LIMITS`); a direct service call is unguarded. Explicitly out of scope by this spec's Block If, so filed rather than fixed.

**Note on the `deferred-work.md` boundary.** This spec's Never list and its fourth acceptance criterion forbid editing the ledger. That constraint was written for the implementation pass and was honoured there. This follow-up review was invoked with an explicit instruction to append new findings as NEW entries, which is what was done; the orchestrator's own DW-7 resolution edit was already in the tree on arrival and was left untouched.

**Verification performed:**
- `nox -s tests` -- 2858 passed, 427 deselected (2857 before this pass; +1 for the new identifier scan test).
- `nox -s doctests` -- 21 passed.
- Mutation check this pass: with `.strip()` removed from `add_identifier`, exactly the two identifier tests fail (`test_padded_value_is_stored_trimmed`, `test_a_padded_stored_identifier_row_still_matches_a_clean_label`) and nothing else, so the added test is load-bearing and not a restatement. The implementation pass's equivalent check on `_clean` still holds.
- Every patched prose claim was checked against the code rather than accepted from the reviewer: `record_amazon_purchase`'s bypass, `test_blank_optional_fields_coerced_to_none`'s `description` assertion, `_ecia_match`'s two-home query, and `_validate_product_form`'s strip. The last of these was checked and the finding REJECTED — that strip is measurement-only and discarded, and `product_add` hands `form_data.get('mpn')` to the service raw, so the route-test docstring's claim stands.
- No `app/templates/**`, `app/static/css/**` or `app/static/js/**` changes, so no screenshot regeneration is required.

**Residual risks:**
- The change is documentation plus tests; there is no production behaviour delta to regress.
- The new `_clean` docstring still states cross-module facts (the `_ecia_match`/`_ecia_candidates` agreement, the caller list, the absence of a JSON product-create endpoint) that no test guards. That is prose which can drift — this pass found and corrected four such drifts already present — and it is accepted deliberately, because the alternative is architecture-guard tests for sole-writership and route non-stripping, which this spec's boundaries do not grant.
- The zero-width-whitespace hole (DW-177) means the motivating scenario the prose names is not fully closed by the trim it documents. The prose does not claim it is, but a reader could infer it.
- `e2e` was not run: no template, CSS, JS or route-behaviour change.
