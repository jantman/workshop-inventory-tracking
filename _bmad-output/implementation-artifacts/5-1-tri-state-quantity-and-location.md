---
title: 'Tri-state quantity and location'
type: 'feature'
created: '2026-07-29'
status: done
review_loop_iteration: 0
baseline_revision: '4278217'
final_revision: '35b854a'
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-context.md'
warnings: ['multiple-goals', 'oversized']
---

<intent-contract>

## Intent

**Problem:** Epic 5 opens with nothing built: `Product` (`app/database.py:862-956`) has no stock or location columns at all — its docstring reserves them ("stock/quantity/location fields (Epic 5)") — so FR23/FR24 (a quantity that distinguishes *untracked* from *none on hand*), FR25 (a verification timestamp whose age is shown) and FR27 (an optional location reusing the existing autocomplete vocabulary) are all unrealized. The only `quantity` anywhere near the product form is the create form's first-receipt `Purchase.quantity` (`app/main/routes.py:962-969`), which is a different thing entirely, and the only `location` vocabulary is metal-stock-sourced (`InventoryService.FIELD_SUGGESTION_COLUMNS`, `app/mariadb_inventory_service.py:782-788`), so a Product's own location would never feed back into it.

**Approach:** Add four nullable columns to `products` (`quantity_on_hand`, `quantity_verified_at`, `location`, `sub_location`) via one Alembic revision, teach `CatalogService` a tri-state write contract where a manual quantity assertion stamps `quantity_verified_at` — an assertion being a *changed* number, or an unchanged one explicitly re-confirmed via a recount checkbox, never merely a form that re-posted its pre-filled value — and clearing the quantity clears the stamp, render the three states as three fixed strings plus an age on the product detail page, put the three controls on both the add and the edit form, and make the existing `location`/`sub_location` autocomplete bidirectional by merging product-sourced values into the item-sourced ones behind the same endpoint and field names.

## Boundaries & Constraints

**Always:**
- The three quantity states render as three distinct fixed strings on the product detail page: `Not tracked` (NULL), `In stock: 0`, `In stock: N`. Never a bare `—`, never `0` for untracked.
- Quantity is written **only** by manual assertion through the product create/edit forms. Nothing on the purchase/receipt path touches either column.
- **What counts as an assertion (the re-stamp rule).** Key presence alone is *not* an assertion — the edit form renders `quantity_on_hand` pre-filled, so every browser edit re-posts the key. `quantity_verified_at` is refreshed to `datetime.now()` when, and only when, one of these holds for a submitted non-blank `quantity_on_hand`:
  1. the submitted value differs from the stored value (this covers first tracking, NULL → `N`);
  2. the submitted value equals the stored value **and** the recount flag `quantity_recounted` is present and truthy in the same POST — the operator recounted and confirmed the same number;
  3. the stored `quantity_on_hand` is non-NULL but the stored `quantity_verified_at` is NULL (repair of a state the write contract otherwise makes impossible).
  In every other case the stamp is left **exactly as stored**. In particular, a submit that carries the pre-filled, unchanged `quantity_on_hand` alongside an edit to some other field — a description typo fix — must not move it. The age FR25 displays is the age of the *count*, never the age of the last edit.
- Clearing the quantity (key present, blank) sets **both** columns to NULL, and `quantity_recounted` is ignored in that case: a recount that finds the product untracked is an untrack, not a verification.
- `quantity_recounted` is a form-only flag: never a `Product` column, never a `_PRODUCT_FIELDS` entry, never accepted as a persisted field. It reaches the service as its own explicit argument, is a no-op for `create_product` (on create every non-blank quantity is a first assertion and always stamps), and is never rendered on the detail page.
- Partial-update rule, unchanged from `product_edit` (`app/main/routes.py:3119-3125`): key absent from the POST body = not provided = untouched; key present but blank = clear to NULL. For `quantity_on_hand` "untouched" means both columns untouched; "present" then defers to the re-stamp rule above for the stamp.
- All four columns are nullable with no server default; new Products get `quantity_on_hand IS NULL`.
- Product location reuses the existing endpoint and the existing public field names `location` / `sub_location` (`GET /api/inventory/field-suggestions/<field>`) — no new field name, no parallel endpoint, no second autocomplete implementation in JS.
- Catalog rows are read by `CatalogService`, item rows by `InventoryService` (AD-1/AD-2); routes hold no ORM/SQL. Field-level validation stays in the route validators, normalization stays in the service (AD-4).
- The three new **fields** (`quantity_on_hand`, `location`, `sub_location`) appear on **both** `product/add.html` and `product/edit.html` with the same names, ids and validation (add/edit parity), and their validation lives in the shared `_validate_product_form`, not the create-only one. The `quantity_recounted` checkbox is the single deliberate exception to parity: it renders on `edit.html` only, because on the add form there is no stored value to re-confirm and every non-blank quantity already stamps. Say so in a comment where the control is added, so the asymmetry reads as intentional.
- Age strings are computed by the route and handed to the template as finished values (AD-5); the template renders, it does not compute.

**Block If:**
- The merged location vocabulary cannot preserve the documented suggestion ordering/dedup contract (`app/mariadb_inventory_service.py:797-826`) without changing the response body of the five pre-existing item fields.
- A migration proves to need anything beyond `op.add_column` on `products` (e.g. a data backfill or a constraint on another table).

**Never:**
- Do not add `reorder_threshold`, `stock_status` or `stock_status_at` — those are Stories 5.2/5.3. Do not compute or render Effective Low, On Order or Recently Received here.
- Do not rename, re-purpose or re-validate the create form's first-receipt `quantity` field; the new control is a separate field named `quantity_on_hand`. None of the three new fields — nor the `quantity_recounted` flag — may be added to `_RECEIPT_TRIGGER_FIELDS` (`app/main/routes.py:1279`); they are Product columns (and a form flag) and must never cause a Purchase to be written.
- Do not add `location`/`sub_location` to `mariadb_catalog_service.FIELD_SUGGESTION_COLUMNS` — that map is the endpoint's dispatch key, and membership in both maps is pinned as an error by `tests/unit/test_catalog_service.py:1704`.
- Do not add a `normalized` key to `location`/`sub_location` responses, and do not enable autocomplete create-mode on them.
- Do not add a JSON endpoint, and therefore no `app/api_client.py` change.
- No `float` anywhere; no `>>>` prompts outside `app/utils/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| New product | `POST /products/add` with only `description` | `quantity_on_hand IS NULL`, `quantity_verified_at IS NULL`; detail shows `Not tracked` | No error expected |
| Assert zero | Untracked Product, edit form posts `quantity_on_hand=0` | Column = `0`, `quantity_verified_at` = now; detail shows `In stock: 0` plus age | No error expected |
| Assert N | Untracked Product, edit form posts `quantity_on_hand=4` | Column = `4`, stamp = now; detail shows `In stock: 4` plus age | No error expected |
| Same value, no recount flag | Product at `4` (stamped 3 months ago), edit posts `quantity_on_hand=4` and no `quantity_recounted` | Column stays `4`, `quantity_verified_at` **unchanged** (still 3 months old) | No error expected |
| Unrelated edit re-posts the form | Product at `4` stamped 3 months ago; edit changes only `description` and re-posts the pre-filled `quantity_on_hand=4` | Both columns unchanged; detail still reads `In stock: 4` with the 3-month age | No error expected |
| Confirming recount | Product at `4`, edit posts `quantity_on_hand=4` **and** `quantity_recounted=on` | Column stays `4`, `quantity_verified_at` moves to now | No error expected |
| Changed value | Product at `4`, edit posts `quantity_on_hand=5` (with or without `quantity_recounted`) | Column becomes `5`, `quantity_verified_at` moves to now | No error expected |
| Recount flag on a blank quantity | Product at `4`, edit posts `quantity_on_hand=''` and `quantity_recounted=on` | Both columns become NULL; the flag is ignored, no stamp is written | No error expected |
| Recount flag alone | Edit posts `quantity_recounted=on` with no `quantity_on_hand` key | Both columns untouched; the flag on its own asserts nothing | No error expected |
| Missing-stamp repair | Product at `4` with `quantity_verified_at IS NULL`, edit posts `quantity_on_hand=4`, no flag | Column stays `4`, `quantity_verified_at` set to now | No error expected |
| Recount flag on create | `POST /products/add` with `quantity_on_hand=4` and `quantity_recounted=on` | Column = `4`, stamp = now — identical to the flag being absent | No error expected |
| Untrack | Product at `4`, edit posts `quantity_on_hand=''` | Both columns become NULL; detail shows `Not tracked`, no age | No error expected |
| Key absent | Edit posts a body with no `quantity_on_hand` key | Both columns untouched | No error expected |
| Bad quantity | `quantity_on_hand` = `-1`, `2.5`, `1_0`, `٥`, `abc`, or > 2147483647 | Form re-renders 200 with a field error; nothing written | Keyed `validation_errors['quantity_on_hand']` |
| Over-long location | `location` 101 chars | Form re-renders 200 with a keyed error; nothing written | Keyed `validation_errors['location']` |
| Location suggestions | Product stored at `Bin 7`, no item has it; `GET /api/inventory/field-suggestions/location?q=bin` | `Bin 7` is offered alongside item-sourced matches, deduped case-insensitively, at most `limit` values, same ordering rule as today | Unsupported field still 400 |
| Sub-location scoping | `?field=sub_location&location=Bin 7` | Only sub-locations recorded under `Bin 7`, from products **and** items | As today |
| Receipt untouched | Recording/receiving a Purchase for a tracked Product | `quantity_on_hand` and `quantity_verified_at` unchanged | No error expected |

</intent-contract>

## Code Map

- `app/database.py:862-956` -- `Product` ORM: add the four columns (table-level `MYSQL_TABLE_OPTIONS` covers collation; no per-column variant) and extend `to_dict()`, which is the audit snapshot.
- `migrations/versions/` -- new revision, `down_revision = 'a977ca7315df'` (current head, `a977ca7315df_pin_explicit_charset_and_collation.py`). `5aeb89e22451_add_products_internal_id.py` is the style reference.
- `app/mariadb_catalog_service.py:45-47` -- `_PRODUCT_FIELDS` update whitelist (unlisted keys are silently dropped). `:123-156` `_clean` (passes `0` through but cannot distinguish absent from zero — the new fields need their own branch). `:361-463` `create_product` (keyword-only). `:465-517` `update_product` (`**fields` loop). `:81-84` catalog `FIELD_SUGGESTION_COLUMNS` — **do not touch**. `:590+` `get_field_value_suggestions` is the catalog-side ordering reference.
- `app/mariadb_inventory_service.py:782-1000` -- item-side `get_field_value_suggestions`: the ordering, guard (`SEARCH_QUERY_MAX_LENGTH`, `is_storable_text`), no-`DISTINCT` and case-insensitive-dedup contract the product-side query must mirror.
- `app/main/routes.py:790-794` `_PRODUCT_FIELD_LIMITS`; `:830-856` `_positive_int_string`; `:879-945` `_validate_product_form` (shared); `:946+` `_validate_product_create_form` (create-only); `:1170` `_product_form_data`; `:1498-1595` `product_add`; `:1670+` `product_detail`; `:3042-3150` `product_edit`; `:4014-4085` `inventory_field_suggestions`.
- `app/templates/product/add.html`, `app/templates/product/edit.html` (`:25-30` `keyed_error_fields`), `app/templates/product/detail.html:38-65` (`<dl class="row">`).
- `app/static/js/field-autocomplete.js:774-814` -- targets are keyed by DOM id and already include `location` and `sub_location` (with `locationFieldId: 'location'` scoping), so markup alone wires the product form. **No JS change expected.**
- `tests/unit/test_product_model.py`, `tests/unit/test_catalog_service.py`, `tests/unit/test_product_routes.py` (`:96` `_rendered_edit_form` hard-codes the field list), `tests/unit/test_routes.py:1654`, `tests/unit/test_autocomplete_markup.py:342` `PRODUCT_DROPDOWNS`, `tests/integration/test_migrations.py`, `tests/e2e/test_autocomplete_aria.py:40` `PRODUCT_FORM_FIELDS`.
- `docs/user-manual.md:717` (Adding a Product), `:1434` (Editing a Product).

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/age_display.py` -- new pure module: `describe_age(then, now)` returning `just now` / `N minute(s) ago` / `N hour(s) ago` / `N day(s) ago` / `N month(s) ago` / `N year(s) ago` (integer arithmetic only, 30-day months, 365-day years), `None` for a `None` input -- the age display FR25 requires; `app/utils/` is the one tree whose `>>>` examples run, so pin the boundaries with doctests.
- [x] `app/utils/suggestion_merge.py` -- new pure module: merge several already-ordered suggestion lists into one under the endpoint's documented order (exact match, then starts-with, then contains, each alphabetized case-insensitively, byte-wise tiebreak deciding which casing survives), deduped case-insensitively, truncated to `limit` -- taking the top-`limit` of each source and re-ranking yields exactly the top-`limit` of the union. Doctest the tiers and the dedup.
- [x] `app/database.py` -- add `quantity_on_hand` (`Integer`, nullable), `quantity_verified_at` (`DateTime`, nullable), `location`/`sub_location` (`String(100)`, nullable) to `Product`; add all four to `to_dict()` (datetime via `.isoformat()`), and update the class docstring's reservation note -- the audit log is blind to columns missing from `to_dict()`.
- [x] `migrations/versions/<rev>_add_product_stock_and_location.py` -- four `op.add_column` calls plus matching `op.drop_column`s, `down_revision = 'a977ca7315df'`; docstring states the story, the tri-state semantics and that metal-stock tables are untouched.
- [x] `app/mariadb_catalog_service.py` -- extend `_PRODUCT_FIELDS` with the four names; add the tri-state coercion branch used by both `create_product` (new keyword-only args) and `update_product`, implementing the re-stamp rule from the intent contract in **one** place: a blank/None quantity clears both columns (ignoring the recount flag), an integer sets the quantity and refreshes `quantity_verified_at = datetime.now()` only when the value differs from the stored one, or the recount flag is truthy, or the stored stamp is NULL -- otherwise the stored stamp is left untouched. `quantity_verified_at` itself is never accepted from a caller, and the recount flag arrives as its own keyword-only argument (default false), never through `**fields`/`_PRODUCT_FIELDS`. `location`/`sub_location` go through `_clean` like other strings. This is the FR23/FR25 write contract.
- [x] `app/mariadb_catalog_service.py` -- add a product-sourced location suggestion method (its own private `location`/`sub_location` column map, deliberately **not** the dispatch whitelist), mirroring the item-side guards, ordering, absence of `DISTINCT` and case-insensitive dedup, with the parent-`location` filter for `sub_location` -- FR27's bidirectional half.
- [x] `app/main/routes.py` -- validation: add `location`/`sub_location` (100) to `_PRODUCT_FIELD_LIMITS`; add a non-negative variant of `_positive_int_string` (share the ASCII-digits/32-bit-bound rule so `_positive_int_string` behaviour is unchanged) and validate `quantity_on_hand` in the **shared** `_validate_product_form` -- both forms carry the field, so the rule cannot live in the create-only validator.
- [x] `app/main/routes.py` -- write path: pass the three fields from `product_add` and `product_edit` into the service (edit keeps absent-vs-blank semantics via its existing present-keys loop) and seed them in `_product_form_data`/the edit render data so a failed submit round-trips them. `product_edit` additionally reads the `quantity_recounted` checkbox from the POST body and passes its truthiness to the service as the dedicated argument -- it never joins `update_fields`, and its checked state round-trips on a failed submit like the other controls. `product_add` does not read it.
- [x] `app/main/routes.py` -- read path: `product_detail` computes and passes the finished quantity string (`Not tracked` / `In stock: 0` / `In stock: N`) and the verified-age string (omitted when no stamp) -- template computes nothing.
- [x] `app/main/routes.py` -- `inventory_field_suggestions`: for `location`/`sub_location` only, query both services and combine via the merge helper; keep the response body shape byte-identical to today (no `normalized`), keep the 400 for unknown fields, and leave the other four item fields on the single-source path.
- [x] `app/templates/product/add.html`, `app/templates/product/edit.html` -- add a Stock & Location block with `quantity_on_hand` (text input, `maxlength="10"`, help text naming the untracked meaning of blank), `location` and `sub_location` (each with its `#<id>-suggestions` div), all with the standard `is-invalid`/`invalid-feedback` pattern; add the three names to `edit.html`'s `keyed_error_fields`; ensure `field-autocomplete.js` is included on both -- ids match the existing JS targets so no JS edit is needed. `edit.html` **only** also gets a `quantity_recounted` checkbox directly under the quantity input, labelled so its effect is unambiguous (e.g. "I recounted this -- refresh the verification date"), with help text saying an unchanged number is otherwise left at its existing verification date; carry a short comment explaining why the control is edit-only.
- [x] `app/templates/product/detail.html` -- render `Quantity on hand` and `Location` rows in the existing `<dl class="row">`, showing the route-computed quantity string with the age appended when present, and `—` for an absent location.
- [x] `tests/unit/test_product_model.py` -- cover the four columns: NULL defaults on a bare insert, persistence of `0` distinctly from `None`, and their presence in `to_dict()`.
- [x] `tests/unit/test_catalog_service.py` -- cover the write contract from the I/O matrix: create defaults, assert 0, assert N, **same value without the recount flag leaves the stamp byte-identical**, same value with the flag moves it, a changed value moves it with or without the flag, the flag is ignored on a blank (both columns NULL), the flag alone with no quantity key changes nothing, a non-NULL quantity with a NULL stamp is repaired, the flag is a no-op on create, absent key untouched, `quantity_verified_at` rejected/ignored as caller input, location blank→NULL; plus the product-sourced suggestion method (ordering tiers, parent scoping, unknown field). The unchanged-stamp assertions must compare against the exact stored datetime captured before the call -- a `>=` or identity comparison passes whether or not the stamp moved and cannot fail.
- [x] `tests/unit/test_product_routes.py` -- cover form round-trip on both add and edit (add the three controls, and the checkbox for edit, to `_rendered_edit_form`'s field list), every bad-input row of the I/O matrix re-rendering 200 with a keyed error and no write, and the three detail strings plus the age. Include the defect this rule exists to prevent as an explicit test: take the rendered edit form verbatim, change **only** `description`, re-post it, and assert `quantity_verified_at` is exactly what it was -- then the same round-trip with the recount box checked, asserting it moved. Assert the checkbox is absent from the add form.
- [x] `tests/unit/test_routes.py` -- extend the field-suggestions tests: a product-only location is offered, an item-only one still is, duplicates across sources collapse case-insensitively, `limit` is respected, `sub_location` scoping filters both sources, and the four untouched item fields' responses are unchanged.
- [x] `tests/unit/test_autocomplete_markup.py` -- add the two new product dropdowns to `PRODUCT_DROPDOWNS`.
- [x] `tests/integration/test_migrations.py` -- no new test is expected: `test_upgrade_head_succeeds_on_a_blank_database`, `test_migrated_schema_matches_the_orm_metadata` and `test_downgrade_to_base_removes_every_application_table` cover any new revision automatically. Confirm by running the session; add a targeted case only if the metadata comparison does not reach the new columns' type/nullability.
- [x] `tests/e2e/test_autocomplete_aria.py` -- add `location` and `sub_location` to `PRODUCT_FORM_FIELDS` (explicit `ids=` on any new parametrization).
- [x] `tests/e2e/test_product_stock.py` -- new e2e: create a product (detail shows `Not tracked`), edit it to `0` then to `4` (detail shows `In stock: 0`, then `In stock: 4` with an age), edit an unrelated field and confirm the displayed age does not reset, tick the recount box on an otherwise unchanged form and confirm it does, clear the quantity back to untracked, and confirm a product-entered location is offered by the location autocomplete on a later form.
- [x] `docs/user-manual.md` -- document the three new fields in the Adding/Editing a Product sections, including what blank means, that receiving a purchase never changes the count, and the recount checkbox: editing anything else leaves the verification date exactly where it was, and the box is how you record "I counted it again and it is still the same number." The manual's existing promise that everything else leaves values as last saved -- including the "counted N ago" age -- must be true as written.

**Acceptance Criteria:**
- Given a Product created through any path, when it is viewed, then its quantity renders as `Not tracked` and no verification age is shown (FR23/FR24).
- Given a Product whose quantity was asserted, when the detail page is viewed, then the age of `quantity_verified_at` is shown alongside the quantity and reflects the most recent assertion (FR25).
- Given a Product whose quantity was counted in the past, when any other field is edited and the form re-posts the unchanged quantity, then `quantity_verified_at` is byte-identical to its stored value and the displayed age continues to reflect the original count (FR25 — staleness is surfaced, not silently corrected).
- Given a Product whose quantity is re-confirmed at the same number with the recount control used, when it is saved, then `quantity_verified_at` moves to now and the displayed age resets (FR25).
- Given a Purchase is recorded or received for a tracked Product, when it is viewed afterwards, then `quantity_on_hand` and `quantity_verified_at` are unchanged (FR25).
- Given a location typed on the product form, when the location autocomplete is next used from either the product or the item form, then that value is offered, and item-sourced values are still offered from both (FR27).
- Given `nox -s tests` and `nox -s doctests`, when they run, then they pass with no new warnings and no marker/doctest-scope violations.

## Spec Change Log

### 2026-07-29 — Intent-gap resolution (human decision, `/bmad-loop-resolve`)

**Gap:** `<intent-contract>` said *"Every assertion (including re-asserting the same number) sets `quantity_verified_at = datetime.now()`"* while making **key presence** the assertion trigger. Because the edit form renders `quantity_on_hand` pre-filled, every browser edit re-posts the key, so a description-only edit re-dated the count — defeating FR25's staleness signal and contradicting the user-manual text shipped with it.

**Decision:** re-stamp on a **changed value**, on an **unchanged value explicitly re-confirmed** via a new edit-form-only `quantity_recounted` checkbox, or when the stored stamp is NULL. Otherwise leave the stamp exactly as stored. Chosen over "value-change only" (which would have made a confirming recount unrecordable) and over a dedicated detail-page recount action (more scope for the same outcome).

**Amended:** Intent → Approach; `Always` (re-stamp rule, blank-clears-and-ignores-flag, flag-is-not-a-column, partial-update deferral, parity exception); `Never` (`_RECEIPT_TRIGGER_FIELDS`); I/O matrix (the `Re-assert same value` row is replaced by eight rows covering unchanged/recounted/changed/blank/flag-alone/missing-stamp/create); three Tasks (service, routes write path, templates) plus the catalog/route/e2e/user-manual test tasks; two new Acceptance Criteria; Design Notes.

**Task checkboxes were reset to `[ ]`** — the prior attempt's implementation was reverted (recoverable in `stash@{0}` on this branch), so nothing in `## Tasks & Acceptance` is actually done. The stash is evidence of the *old* reading and must not be restored wholesale; the migration, ORM columns, merge helper and location work in it are still sound and can be re-derived, but every `quantity_verified_at` write path and its tests are now wrong.

## Review Triage Log

### 2026-07-29 — Review pass
- intent_gap: 1: (high 1, medium 0, low 0)
- bad_spec: 5: (high 0, medium 5, low 0)
- patch: 7: (high 0, medium 1, low 6)
- defer: 1: (high 0, medium 1, low 0)
- reject: 3: (high 0, medium 0, low 3)
- addressed_findings:
  - none

### 2026-07-29 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 0
- reject: 8: (high 0, medium 0, low 8)
- addressed_findings:
  - `[medium]` `[patch]` The recount flag was read by KEY PRESENCE (`'quantity_recounted' in form_data`), not truthiness as the contract requires, so a serializer that posts unticked controls (`quantity_recounted=`) would refresh a verification date nobody earned — and the route then disagreed with `edit.html`, which re-renders that same body with the box unticked. Now `bool((form_data.get(...) or '').strip())`, the template's own test. Pinned by `test_an_empty_recount_key_is_not_a_recount`.
  - `[low]` `[patch]` `product_detail` computed the verification age from the stamp alone, so a row with a stamp but no count (a restored backup, a hand-run `UPDATE`) rendered `Not tracked (counted 3 months ago)` — an age for a count the same line denies. Gated on `quantity_on_hand is not None`. Pinned by `test_a_stamp_without_a_count_shows_no_age`.
  - `[low]` `[patch]` `_apply_quantity_assertion` used a bare `int(value)` while its docstring promised a raise: `2.9` stored `2` and `True` stored `1`, both stamped as freshly verified, and a negative or over-32-bit value reached a column that cannot hold it. It also died on `'0' * 5000`, which the form rule accepts (its bound is on magnitude) but CPython's 4300-digit `int()` limit refuses. Now a type + bounds guard with leading zeros stripped — the service's own contract, deliberately not a second copy of the form rule. Pinned by `test_a_value_the_column_cannot_hold_is_refused_not_truncated` and `test_a_zero_padded_string_is_the_magnitude_it_names`.
  - `[low]` `[patch]` `app/utils/suggestion_merge.py` claimed it reproduced the services' total order "exactly" and that its folded key sorts `cafe` and `café` adjacently. Neither is true under MariaDB's `utf8mb4_unicode_ci`, which folds accents where `str.lower()` does not, so a merged answer can rank an accented value differently from a single UNION. Documented as the known, accepted imprecision it is (ASCII — every realistic location — is unaffected) rather than left as a false equivalence proof.
  - `[low]` `[patch]` Both product templates carried a comment asserting the two forms use "the same help text"; they do not, and the difference is deliberate (only `edit.html` can move an existing verification date, so that explanation lives on its recount control). Comments corrected to claim the parity that actually holds — same names, ids and validation.

### 2026-07-29 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 0, low 3)
- defer: 2: (high 0, medium 0, low 2)
- reject: 18: (high 0, medium 0, low 18)
- addressed_findings:
  - `[low]` `[patch]` `edit.html` re-rendered the recount box using raw truthiness (`{% if form_data.get('quantity_recounted') %}`) while the route tests the *stripped* value, so the two disagreed about a whitespace-only `quantity_recounted='   '`: the route correctly refused to re-stamp, then handed back a form with the box **ticked**, whose next save would refresh a verification date the first save had just declined to touch. The route's comment claimed the two agreed. Template now applies `|trim`, character for character the route's own test. Pinned by `test_a_whitespace_recount_leaves_the_box_unticked_on_re_render`.
  - `[low]` `[patch]` `product_edit`'s degraded-render comment enumerated exactly what a failed stored-value read can cost ("a wiped manufacturer, mpn, category, notes and tag list") and was not updated when this story added three more fields to `_product_form_data`. The omission mattered: a blank `quantity_on_hand` does not clear a string, it **untracks** the product and nulls `quantity_verified_at` with it, and unlike a retypeable category the date somebody counted is not recoverable. Comment now names the full field list and calls out the one irreversible member.
  - `[low]` `[patch]` `app/utils/suggestion_merge.py`'s module docstring promised "no exceptions of its own" while `limit = max(1, int(limit))` raises `TypeError`/`ValueError` on a non-int-like `limit`. Documented as the deliberate boundary it is — a pure merge has no business inventing a page size for a caller who asked for an incoherent one, and both service callers already clamp before they reach it — rather than left as a false totality claim.

## Design Notes

**Why a separate merge helper rather than a UNION.** FR27 wants one vocabulary from two tables. A UNION inside `InventoryService` would put a catalog query in the item service (AD-1/AD-2), and adding `location` to the catalog dispatch whitelist would silently route *item* lookups at `products` — the failure `tests/unit/test_catalog_service.py:1704` exists to prevent. Each service therefore queries its own table under the same ordering rule and a pure function merges the two ordered lists; because both are the top-`limit` under the same total order, re-ranking their union and truncating gives exactly the answer a single query would.

**Tri-state at the boundary.** `_clean` cannot express this: it maps `''`→`None` and passes `0` through, but "absent" and "cleared" arrive at `update_product` looking alike unless the key's presence is what decides. The route already decides that (`routes.py:3119-3125` builds `update_fields` from present keys only), so the service's rule is: key present + blank ⇒ both columns NULL; key present + integer ⇒ quantity set, stamp refreshed **only if this is really an assertion**.

**Why key-presence cannot be the assertion trigger.** The edit form renders `quantity_on_hand` pre-filled, so a browser always re-posts it — key presence is a property of the form's markup, not of operator intent. Making it the trigger meant a description typo fix re-dated the count, which is exactly the signal FR25 exists to preserve ("its staleness is surfaced rather than silently corrected"). The trigger is therefore *a changed value*, plus an explicit `quantity_recounted` checkbox for the one case a value comparison cannot see: the operator who recounted and found the same number. Resolved with the human on 2026-07-29; see the Spec Change Log.

```python
# service, inside the field loop  (recounted: bool, its own keyword-only arg)
if field == 'quantity_on_hand':
    if value is None or (isinstance(value, str) and not value.strip()):
        product.quantity_on_hand = None
        product.quantity_verified_at = None
    else:
        new_quantity = int(value)
        if (new_quantity != product.quantity_on_hand
                or recounted
                or product.quantity_verified_at is None):
            product.quantity_verified_at = datetime.now()
        product.quantity_on_hand = new_quantity
    continue
```

Order matters in that branch: the comparison and the `None` stamp check both read the *stored* values, so the assignment to `quantity_on_hand` comes last.

**Clock.** `datetime.now()` (naive local), matching `mariadb_materials_admin_service.py:173` and `logging_config.py:622`, so the stamp and the age comparison read the same clock; `func.now()` would be the DB's.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all pass (~3550 selected), including the new unit tests.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s doctests` -- expected: the new `app/utils/` examples execute and pass.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` -- expected: pass (needs a 20-minute tool timeout; revert any screenshots it rewrites).
- `venv/bin/python manage.py db upgrade` then `venv/bin/python manage.py db downgrade -1` against a scratch database -- expected: both succeed, columns appear and disappear.

**Manual checks (if no CLI):**
- `nox -s integration` requires Docker; if unavailable, state that the migration round-trip was not executed rather than claiming it passed.


## Auto Run Result

Status: `done` — follow-up review pass over the already-shipped Story 5.1 implementation (`5b67847`). No intent gap, no spec deviation; three low-severity patches applied, two pre-existing issues deferred.

**Implemented change (under review, unchanged by this pass):** four nullable columns on `products` (`quantity_on_hand`, `quantity_verified_at`, `location`, `sub_location`) behind one Alembic revision; the tri-state write contract in `CatalogService` where a manual assertion — a changed number, or an unchanged one re-confirmed via the edit-only `quantity_recounted` checkbox, or a repair of a missing stamp — refreshes `quantity_verified_at` and a blank clears both columns; three fixed detail-page strings plus a verification age; and a location vocabulary merged from products and items behind the existing suggestion endpoint and field names.

**Files changed in this pass:**
- `app/templates/product/edit.html` — recount checkbox re-render now applies `|trim`, matching the route's stripped test exactly.
- `app/main/routes.py` — degraded-render comment in `product_edit` corrected to name all seven seeded fields and the one whose blank is irreversible.
- `app/utils/suggestion_merge.py` — module docstring no longer claims totality over `limit`; states the boundary and why it is the caller's to clamp.
- `tests/unit/test_product_routes.py` — new `test_a_whitespace_recount_leaves_the_box_unticked_on_re_render`, pinning route/template agreement on a whitespace-only recount value.
- `_bmad-output/implementation-artifacts/deferred-work.md` — two new entries (DW-247, DW-248).

**Review findings breakdown:** 3 patches applied (all low, all above); 2 deferred (DW-247 `update_product` logs `item_after` only, so the count history `to_dict()` now carries cannot be read back — verified pre-existing at baseline `4278217`; DW-248 the merged location autocomplete does two unbounded, unindexed, fully-sorted scans per keystroke — `app/database.py` declares one index in the whole module and the new migration adds none); 18 rejected. The rejections were predominantly disagreements with decisions the intent contract makes explicitly — the missing-stamp repair clause, `maxlength="10"`, naive `datetime.now()`, per-service queries plus a pure merge instead of a `UNION`, and the service parse owning type and bounds but deliberately not re-implementing the form's digit grammar — plus the already-documented `str.lower()` vs `utf8mb4_unicode_ci` folding imprecision.

**Verification performed:**
- `nox -s tests` — **3636 passed, 2 skipped, 480 deselected**, 3 warnings (pre-existing count), including the new route test.
- `nox -s doctests` — **25 passed**; `app/utils/suggestion_merge.py`'s examples still execute after the docstring edit.
- `nox -s integration` — **53 passed (7:54)** against the MariaDB testcontainer. This closes the review's one open verification question: the three restructured collation tests in `tests/integration/test_migrations.py` had been flagged as possibly never executed, and they are the tests asserting that `ALTER TABLE … ADD COLUMN` inherits the pinned `utf8mb4_unicode_ci` rather than a contrary database default. They ran and passed, so the new `products.location` / `sub_location` fold identically to `inventory_items.location` — the premise the merge's ordering equivalence rests on.
- `nox -s e2e` — **426 passed, 1 skipped (21:12)**, with the edit-template change in place. The screenshots the session rewrote (`metadata.json`, three user-manual PNGs) were reverted, leaving the tree carrying only the changes above.

**Residual risks:**
- DW-248 is latent, not theoretical: the doubled unindexed scan is free at present catalog volumes and degrades with growth, and the natural place to have added the index (this migration) has passed.
- The recount flag reads any non-blank string as truthy, so a hypothetical non-browser client posting `quantity_recounted=false` would be read as a recount. Rejected rather than patched — no such client exists for this server-rendered form, and making the word `false` falsey would require duplicating a falsey-word list into Jinja, re-creating the route/template divergence this pass just closed.
- FR23/FR24's three distinct strings render on the product detail page only; the list and search views show no quantity, so tracked-zero and untracked are indistinguishable while scanning the catalog. This matches the story's scoping, but the epic's rendering requirement is not fully met by Story 5.1 alone.
