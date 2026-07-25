---
title: 'Materialized-path categories with inline create'
type: 'feature'
created: '2026-07-24'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
baseline_revision: '481c643'
final_revision: 'a6367a2'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `products.category_path` has existed since Story 1.1 as a plain 512-char column with an index, but nothing gives it meaning: the product form renders a bare text input with a placeholder, the service applies only `_clean()` (trim + blank→NULL), and no canonical form exists — so `Electronics/Power/`, `electronics//power` and `electronics/power` are three different categories today. FR14's inline create has no implementation at all: the category field is the one product field with no autocomplete, so a path typed once is never offered again and the tree cannot accrete (FR15).

**Approach:** Add `app/utils/category.py` with a pure `normalize_category_path()` as the single source of truth for the canonical form (AD-4), apply it in `CatalogService.create_product`/`update_product` — the only write paths — so every stored path is canonical or NULL, and source the category vocabulary from the distinct set of stored paths through the **existing** `/api/inventory/field-suggestions/<field>` endpoint (AD-14: extend the whitelist, never fork a parallel field set), dispatched to `CatalogService` so no product SQL lands in the inventory service. `field-autocomplete.js` gains an opt-in `allowCreate` variant whose "create" entry displays the canonical form **echoed by the server**, so the browser never reimplements normalization.

## Boundaries & Constraints

**Always:**
- `app/utils/category.py` is **pure**: stdlib only, no Flask/SQLAlchemy/`app.*` imports (absolute or relative), no I/O. It carries the copied purity-guard test class (`tests/unit/test_gtin.py:157-178`) and its own module-local `InvalidCategoryPathError(ValueError)` — never `app.exceptions.ValidationError` (AD-4, NFR7).
- Every `products.category_path` that reaches the database is canonical or `NULL`. Normalization happens in `CatalogService.create_product` and `update_product` (the sole writers) — never in routes, templates, or JavaScript.
- The canonical form is exactly: lowercase, `/`-separated, no leading/trailing slash, no empty segments, each segment stripped of surrounding whitespace. Normalization only ever shortens or lowercases; it never rewrites segment contents (no space→hyphen, no slugging, no Unicode folding beyond `str.lower()`).
- **One** suggestions surface: `GET /api/inventory/field-suggestions/<field>` gains `category_path` via a catalog-side whitelist that mirrors `MariaDBInventoryService.FIELD_SUGGESTION_COLUMNS` in name, signature, `ValueError`-on-unknown-field, `[1,50]` limit clamp, LIKE escaping, and exact→startswith→contains ranking. No second suggestions URL, no `products` query inside `MariaDBInventoryService` (AD-1/AD-2 layering), no ORM in routes.
- The five existing suggestion fields keep byte-identical request handling and response bodies — the new `normalized` key appears **only** for catalog-sourced fields.
- `FieldAutocomplete` is extended **in place** with an opt-in `allowCreate` (default `false`), so all five existing instances behave exactly as today. The create entry is rendered as one more `.dropdown-item` carrying `data-value`, so `onKeyDown()`/`highlight()`/`selectValue()` need no changes.
- Schema stays as-is; the one migration is **data-only**, chained from current head `5aeb89e22451`, authored in the recent hand-written style (prose docstring citing the story, `sa.table`/`sa.column` stubs, never the ORM) and run via `manage.py db` (AD-14).
- New tests carry `@pytest.mark.unit` (or `@pytest.mark.e2e`), use the house parametrize idiom (one case per line with an aligned trailing `#` comment), and cite FR13/FR14/FR15/AD-4/AD-14 in docstrings.

**Block If:**
- `nox -s tests` is already red on this branch before any change — that is pre-existing breakage, not this story's.
- The e2e harness cannot serve `/products/add` for reasons predating this story (missing route or missing `products` schema in the E2E server) — that is an Epic 1 regression to surface, not something to work around.

**Never:**
- No `categories` table, no category node entity, no materialized ancestor rows. The tree **is** the distinct set of assigned `products.category_path` values — this story's resolution of the storage-depth question the architecture deferred to Epic 3.
- No rename, move, merge, or delete of categories; no descendant propagation; no sibling-collision detection (Story 3.2).
- No tags and no `product_tags` table (Story 3.3).
- No filtering or faceting by category, no segment-boundary prefix predicate (`path = X OR path LIKE 'X/%'`), no clickable category on the detail page — Story 3.2 and Epic 8 own those and will add the predicate to this same util when they need it.
- No JS-side normalization, no new JS/Python dependency, no build step, no framework; no changes to the inventory forms, the inventory service, or metal-stock behavior (NFR9).
- No new user-facing validation error for category shape — every string either normalizes to a path or to nothing. Do not change `_PRODUCT_FIELD_LIMITS` or the route's existing 512-char message.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Canonical passthrough | `normalize_category_path('electronics/power/dc-dc-converters')` | unchanged; `normalize(normalize(x)) == normalize(x)` for every case in this table | No error |
| Case and outer whitespace | `'  Electronics/Power  '` | `'electronics/power'` | No error |
| Slash noise | `'/electronics//power/'`, `'electronics///power'` | `'electronics/power'` | No error |
| Whitespace around separators | `'Electronics / Power / DC-DC'`, `'a\t/\nb'` | `'electronics/power/dc-dc'`, `'a/b'` | No error |
| Intra-segment characters preserved | `'Power Supplies/DC DC'`, `'thermal/heat-sinks'` | `'power supplies/dc dc'`, `'thermal/heat-sinks'` | No error |
| Nothing left | `''`, `'   '`, `'/'`, `'///'`, `' / / '`, `None` | `None` — blank means "no category", never an error | No error |
| Non-string input | `5`, `['a']`, `b'a'`, `Decimal('1')` | rejected — a caller-type fault, not scan/form data | `InvalidCategoryPathError` (a `ValueError` subclass) |
| Over-length result | normalized value longer than `MAX_CATEGORY_PATH_LENGTH` (512, mirroring the column) | rejected | `InvalidCategoryPathError` |
| Create stores canonical | `create_product(description='x', category_path='Electronics/Power/')` | row persists `category_path='electronics/power'` | Returns `None` only on genuine failure (unchanged contract) |
| Update stores canonical | `update_product(id, category_path=' /Thermal/Heat Sinks ')` | row holds `'thermal/heat sinks'` | Returns `False` on failure (unchanged) |
| Update clears | `update_product(id, category_path='   ')` | row holds `NULL` | No error |
| Update omits field | `update_product(id, description='y')` | `category_path` untouched (existing rule preserved) | No error |
| Form round-trip | POST `/products/add` with `category_path='Electronics/Power/'` | product detail shows `electronics/power`; edit form prefills the canonical value | Existing flash/redirect behavior |
| Suggestions, catalog field | `GET /api/inventory/field-suggestions/category_path?q=Elec` with `electronics/power` stored | `{"success": true, "field": "category_path", "suggestions": ["electronics/power"], "normalized": "elec"}` | 200 |
| Suggestions, blank query | same endpoint, no `q` (focus event) | distinct stored paths, alphabetical, `"normalized": null` | 200 |
| Suggestions, no match | `?q=Zzz/Nope` | `{"suggestions": [], "normalized": "zzz/nope"}` — the create affordance's source of truth | 200 |
| Suggestions, limit clamp | `?limit=999`, `?limit=abc` | at most 50 / default 10; NULL and blank paths never offered; case-insensitive dedup | 200 |
| Suggestions, existing fields | `?field=vendor`, `thread_size`, `location`, `sub_location&location=…`, `purchase_location` | responses identical to today, **no** `normalized` key | 200 |
| Suggestions, unknown field | `/api/inventory/field-suggestions/bogus` | unchanged | 400 `{"success": false, "error": …}` |
| Create affordance | operator types `Electronics/Power` on the product form, nothing stored matches | dropdown shows a `+ Create "electronics/power"` entry; choosing it (click, or ArrowDown+Enter) fills the input with `electronics/power` | No error |
| No redundant create | typed value normalizes to a path already in `suggestions` | no create entry — it already exists | No error |
| Create off by default | the five inventory fields | never show a create entry | No error |
| Backfill | pre-existing row `category_path='Electronics/Power/'` at migration time | becomes `'electronics/power'`; rows already canonical and `NULL` rows are left untouched | Downgrade is a documented irreversible no-op |

</intent-contract>

## Code Map

- `app/utils/category.py` -- **new** pure util; canonical-form single source of truth (AD-4). Model it on `app/utils/gtin.py` (module docstring with explicit purity declaration, module-level functions, module-local `ValueError` subclass, full type hints, `Args:/Returns:/Raises:/Examples:` docstrings, public constants).
- `app/mariadb_catalog_service.py` -- `_PRODUCT_FIELDS` (:37), `_clean` (:65), `create_product` (:136, `category_path=_clean(...)` at :167), `update_product` (:235, the `setattr` loop at :252-255). Per-method `session = self.Session()` / `try/except-log/finally: close()` — no context manager.
- `app/mariadb_inventory_service.py` -- `FIELD_SUGGESTION_COLUMNS` (:776-785) and `get_field_value_suggestions` (:787-871) incl. `_escape_like` (:846) and the exact→startswith→contains `case()` ranking: the contract the catalog-side source must mirror. **Do not edit this file.**
- `app/main/routes.py` -- `field_suggestions` route (:1421-1466), `_get_catalog_service()` (:81), product routes `product_add` (:779, `category_path` at :800), `product_edit` (:940, update-only-present-fields at :983-986), `_PRODUCT_FIELD_LIMITS` (:749), `_validate_product_form` (:757), `_product_form_data` (:768).
- `app/static/js/field-autocomplete.js` -- `FieldAutocomplete` class: constructor opts (:49-76), `buildUrl` (:97), `fetchAndRender` (:111), `render` (:133-166), `selectValue` (:168), `onKeyDown` (:180), auto-init list (:218-240).
- `app/templates/product/add.html` / `edit.html` -- category input at :43-49 in both (no wrapper, no dropdown div, no `{% block scripts %}`). Wiring pattern to copy: `app/templates/inventory/add.html:189-194` (`.position-relative` + `#<id>-suggestions`) and its script tag at :369.
- `app/api_client.py` -- `SUGGESTABLE_FIELDS` (:38-44) and its comment (:34-36); `FieldSuggestionsResult` (frozen, exposes the whole body via `.raw`); `get_field_suggestions` (:260-363).
- `app/database.py` -- `Product.category_path = Column(String(512), nullable=True, index=True)` (:852). Unchanged by this story.
- `migrations/versions/5aeb89e22451_add_products_internal_id.py` -- current head and the template for a hand-authored data migration (pure-util import at :26, `sa.table` stubs at :46-60).
- `tests/unit/test_gtin.py:157-178` -- the purity-guard class to copy verbatim (including its explanatory comment).
- `tests/e2e/test_field_autocomplete.py` -- e2e idioms (`_expect_dropdown_visible`, `page`/`live_server` fixtures). Note `tests/e2e/test_server.py:311` `clear_test_data()` does **not** truncate `products`.

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/category.py` -- create the pure module: `InvalidCategoryPathError(ValueError)`, `CATEGORY_PATH_SEPARATOR = '/'`, `MAX_CATEGORY_PATH_LENGTH = 512`, and `normalize_category_path(value: Optional[str]) -> Optional[str]` implementing the matrix -- single source of truth for the canonical form (FR13, AD-4).
- [x] `tests/unit/test_category.py` -- exhaustive unit tests for every matrix row incl. idempotence, `issubclass(InvalidCategoryPathError, ValueError)`, and the copied `TestPureModuleHasNoAppImports` guard -- pure utils get exhaustive tests (NFR7).
- [x] `app/mariadb_catalog_service.py` -- normalize `category_path` in `create_product` and in `update_product`'s field loop; add module-level `FIELD_SUGGESTION_COLUMNS = {'category_path': 'category_path'}`, `get_field_value_suggestions(field, query=None, limit=10) -> List[str]` (mirroring the inventory contract, normalizing the query for category), and `normalize_suggestion_value(field, value) -> Optional[str]` -- keeps normalization and the product query on the service side of the seam (FR13, FR15, AD-1).
- [x] `app/main/routes.py` -- in `field_suggestions`, dispatch fields present in the catalog whitelist to `_get_catalog_service()` and include `normalized` in that response; leave the inventory path and the 400/500 branches untouched -- one endpoint, two sources (FR14, AD-14).
- [x] `app/api_client.py` -- add `'category_path'` to `SUGGESTABLE_FIELDS` and update its comment/docstring to say the whitelist mirrors both server-side sources; do not change `FieldSuggestionsResult` (the new key is already reachable via `.raw`) -- keeps the requests-only client in sync (NFR10, AD-13).
- [x] `app/static/js/field-autocomplete.js` -- add `allowCreate` (default `false`); capture the response's `normalized` in `fetchAndRender`; in `render`, append a `+ Create "<canonical>"` `.dropdown-item` with `data-value` when `allowCreate` and the candidate is non-empty and not already among the suggestions; render the dropdown even when suggestions are empty in that case; add `{inputId: 'category_path', field: 'category_path', allowCreate: true}` to the auto-init list -- FR14 inline create without forking the component.
- [x] `app/templates/product/add.html` + `app/templates/product/edit.html` -- wrap the category input in `.position-relative`, add the `#category_path-suggestions` dropdown div matching the inventory markup, and add a `{% block scripts %}` loading `js/field-autocomplete.js` -- wires the field with no new JS file.
- [x] `migrations/versions/<new12hex>_normalize_existing_category_paths.py` -- hand-authored data-only migration chained from `5aeb89e22451`: read distinct non-NULL `products.category_path`, rewrite any value that differs from its normalized form, leave canonical and NULL rows untouched; `downgrade()` a documented irreversible no-op -- makes "every stored path is canonical" true for pre-existing rows too (AD-14).
- [x] `tests/unit/test_catalog_service.py` -- add classes covering create/update normalization (canonical, noisy, blank→NULL, omitted-field-unchanged) and the suggestion source (unknown field `ValueError`, ranking order, limit clamp, dedup, NULL/blank exclusion, distinctness, normalized query matching) -- the service is where the invariant is enforced.
- [x] `tests/unit/test_routes.py` -- extend `TestFieldSuggestionsRoute` with `category_path` cases (shape incl. `normalized`, blank/no-match/limit) plus a regression assertion that a vendor response has no `normalized` key -- protects the shared endpoint's existing consumers.
- [x] `tests/unit/test_product_routes.py` -- add/edit form posts with a non-canonical category persist the canonical value and the edit form prefills it -- covers the FR13 path end-to-end below the browser.
- [x] `tests/e2e/test_category_autocomplete.py` -- **new**: (1) type a novel path on `/products/add`, assert the `+ Create "<canonical>"` entry, select it, submit, assert the detail page shows the canonical path; (2) reopen `/products/add`, type a prefix, assert the stored path is offered as a suggestion. Use a path prefix unique to each test (e.g. `e2ecat-<something>/…`) and assert only positively, because `clear_test_data()` leaves `products` populated for the session -- the create affordance has no unit-test surface (no JS test infra).

**Acceptance Criteria:**
- Given no categories exist, when the operator types `Electronics/Power/DC-DC Converters` into the category field on the product form and saves, then the product is stored with `category_path='electronics/power/dc-dc converters'` without leaving the form (FR13, FR14, FR15).
- Given that product exists, when the operator opens a new product form and types `elect`, then `electronics/power/dc-dc converters` is offered as a suggestion (FR15).
- Given a database containing products with non-canonical `category_path` values, when `manage.py db upgrade` runs, then every non-NULL `category_path` is canonical and no other column or table is modified (AD-14, NFR9).
- Given the five pre-existing autocomplete fields, when they are used on the inventory add/edit forms, then their requests, responses, and dropdown behavior are unchanged and no create entry ever appears (NFR9).
- Given the whole change, when `nox -s tests` runs, then it is green with no pre-existing test regressed — including `tests/unit/test_product_model.py`'s exact column-set and `to_dict()` key-set assertions, which must still pass untouched.

## Spec Change Log

## Review Triage Log

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 13: (high 0, medium 2, low 11)
- defer: 2: (high 0, medium 1, low 1)
- reject: 6: (high 0, medium 0, low 6)
- addressed_findings:
  - `[medium]` `[patch]` The backfill migration drove off `SELECT DISTINCT category_path`, which MariaDB's case-insensitive collation folds to one arbitrary representative — when the canonical spelling survived, mixed-case siblings were skipped and left non-canonical, defeating the migration's own acceptance criterion. Rewritten to read `id, category_path` per row (collation-independent), group the rows needing change by target value, and update by primary key.
  - `[medium]` `[patch]` Selecting a dropdown entry re-opened the dropdown ~200 ms later — for a create entry, re-offering to create the value just accepted, on top of the Save button. Three causes closed in `selectValue`: a debounced fetch already scheduled (added `debounce().cancel()`), a fetch already in flight (request-sequence bump), and the `input` event `selectValue` itself dispatches (`suppressNextFetch`). Caught by the new e2e assertion, not by inspection.
  - `[low]` `[patch]` A query the util rejects (over-length) fell through to `q = ''`, silently dropping the filter and returning the entire vocabulary — contradicting the docstring directly above it. `get_field_value_suggestions` now returns `[]` for an unmatchable query; a query that merely normalizes away (`/`, `///`, whitespace) still means "no filter", now pinned by tests.
  - `[low]` `[patch]` One legacy row longer than 512 characters would abort the whole migration; unnormalizable values are now skipped and left as-is.
  - `[low]` `[patch]` `normalize_suggestion_value`'s unreachable `_clean` fallback advertised non-canonical semantics for a hypothetical second catalog field that the SQL and the browser both assume is canonical — replaced with a loud `NotImplementedError`.
  - `[low]` `[patch]` The JS create-suppression check compared `s.toLowerCase() === candidate`, assuming the server candidate is lowercase — now lowercases both sides.
  - `[low]` `[patch]` Nothing enforced that the catalog and inventory suggestion whitelists are disjoint, though the endpoint dispatch depends on it — added a unit test.
  - `[low]` `[patch]` Out-of-order responses (undebounced `focus` fetch racing a debounced keystroke fetch) could render an older query's suggestions and create candidate — added a request-sequence guard that drops stale responses.
  - `[low]` `[patch]` The "No redundant create" matrix row had no coverage at any level — the e2e test now types a full existing path and asserts no create entry appears.
  - `[low]` `[patch]` `docs/user-manual.md`'s endpoint reference still described the suggestions endpoint as five inventory-only fields with no `normalized` key — updated the source description, field table, and response documentation.
  - `[low]` `[patch]` A comment justified the design as a "DISTINCT query over the already-indexed column", which the leading-wildcard `LOWER(...) LIKE` cannot use — reworded to state what the index actually serves.
  - `[low]` `[patch]` `FieldSuggestionsResult` exposed the new key only via `raw['normalized']` — added a documented `normalized` property (additive, AD-13-safe).
  - `[low]` `[patch]` Test noise: a no-op `assert first is not None` (with its unused variable) and a whole-page `b'Electronics/Power' not in detail.data` assertion that any unrelated markup could turn red — both tightened.

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 1, low 8)
- defer: 1: (high 0, medium 1, low 0)
- reject: 11: (high 0, medium 0, low 11)
- addressed_findings:
  - `[medium]` `[patch]` The previous pass closed the dropdown's re-open paths in `selectValue` but not in the three other places the interaction ends. Escape, blur and outside-click called plain `hide()`, leaving a keystroke's debounced fetch (and any in-flight response) to re-render the dropdown ~200 ms later with the field no longer focused — over the Save button, where a click meant for Save lands on a dropdown item's `mousedown` instead. `allowCreate` widened this to the case where the server matched nothing, i.e. every brand-new category path. Added `dismiss()` (cancel the debounce, invalidate in-flight responses, hide) and routed Escape, the blur timeout, the outside-click handler and `selectValue` through it. Pinned by a new e2e test verified to fail 4/4 (including all reruns) with the fix reverted.
  - `[low]` `[patch]` The backfill migration built one `UPDATE ... WHERE id IN (...)` per distinct canonical path with no chunking. The number of distinct paths is small by construction, but the number of *rows* per path is not — one miscapitalized category across 100k products would exceed MariaDB's `max_allowed_packet` and SQLite's bound-parameter limit. Now chunked at 500 ids; re-verified against a scratch SQLite database with 1200 rows sharing one non-canonical value.
  - `[low]` `[patch]` The migration's comment justified skipping canonical rows so as to leave "its `updated_at`, which the model bumps onupdate, completely alone" — implying rewritten rows *are* bumped. They are not: the statements run against the `sa.table()` stub, which carries no `onupdate`. Comment corrected to state (and justify) what actually happens.
  - `[low]` `[patch]` `normalize_suggestion_value`'s `Raises:` section listed only `ValueError` while the method deliberately raises `NotImplementedError` for a whitelisted-but-unregistered field — which the route does *not* convert to a 400. Documented, including why it is not the request-error path.
  - `[low]` `[patch]` `get_field_value_suggestions`'s `else` arm read `self.normalize_suggestion_value(field, query) or ''`, which looks like a working generic path but answers a different question (what to *echo*, where a rejected query is `None`) — reading that `None` as "no filter" is exactly the whole-vocabulary leak the `category_path` arm was patched to prevent last pass. Replaced with a loud `NotImplementedError` matching its sibling.
  - `[low]` `[patch]` `update_product`'s docstring still described only `_clean` semantics ("blank strings become NULL") though it is now one of the two writers that canonicalize `category_path`.
  - `[low]` `[patch]` `docs/user-manual.md` said `normalized` is null "when `q` is omitted or carries no path"; it is *also* null for an unmatchable (over-length) query, where `suggestions` is `[]` rather than the unfiltered vocabulary. Both cases now documented.
  - `[low]` `[patch]` `app/api_client.py` gained `category_path` and a `normalized` accessor with no test, in a file whose suite already asserts `SUGGESTABLE_FIELDS` membership — and whose comment claims the tuple mirrors *both* server whitelists with nothing enforcing it. Added the membership and accessor assertions, plus a mirror test beside the existing disjointness test (kept out of `test_api_client.py`, which deliberately imports no runtime modules).
  - `[low]` `[patch]` The e2e "no redundant create" assertion could pass vacuously: focusing the field fires an immediate *unfiltered* fetch whose render also carries no create entry, so `to_have_count(0)` could succeed without the typed query ever being answered. Now waits for a single-item dropdown — the unique path matches exactly one row — which can only be the filtered response.

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 1, low 7)
- defer: 1: (high 0, medium 0, low 1)
- reject: 18: (high 0, medium 0, low 18)
- addressed_findings:
  - `[medium]` `[patch]` The previous pass's `dismiss()` could not run on the case it was written for. `onKeyDown` returns early when the dropdown is not currently visible, *above* the Escape branch — so Escape pressed during the ~200 ms debounce window, while the dropdown is still hidden, did nothing at all, and the pending fetch opened it a moment later over the Save button. The e2e test added last pass waits for the dropdown to be visible before pressing Escape, so it passed over the uncovered branch rather than through it. Escape is now handled before the visibility guard. Pinned by a new e2e test (type-then-Escape dispatched together, entirely inside the hidden window) verified to fail 4/4 including all reruns with the fix reverted.
  - `[low]` `[patch]` The blur handler's 150 ms timeout was never cancelled, so re-focusing the field within that window let the stale `dismiss()` land *after* the focus fetch started and invalidate it — leaving the field with no dropdown at all. Harmless while the timeout only called `hide()`; a regression once it began bumping the request sequence. The handle is now kept and cleared on focus.
  - `[low]` `[patch]` The migration's skip comment claimed an unnormalizable value is "only reachable if a pre-MariaDB SQLite-era row stored more than the column's 512 characters". False: lowercasing can *lengthen* a string, so a row well within 512 characters can normalize past it — verified by re-driving the migration against a scratch database with a 300-character `'İ' * 300` row, which is skipped. Comment corrected.
  - `[low]` `[patch]` Skipped rows were passed over in total silence: the upgrade reported success while leaving `category_path` values that violate the invariant it exists to establish, and that the operator cannot fix through the form either. The migration now prints a warning naming the affected product ids.
  - `[low]` `[patch]` `test_max_length_mirrors_the_column` asserted `MAX_CATEGORY_PATH_LENGTH == 512` — a literal against a literal, which mirrors nothing and would still pass if the column were widened. It now reads the length off `Product.__table__.c.category_path`, which is the only thing keeping the pure util's constant in step with the schema.
  - `[low]` `[patch]` Three of the seven `test_limit_clamp` cases (`999`, `'abc'`, `None`) ran against a four-path fixture, so they would pass identically with no 50-ceiling and no 10-default. Added a test seeding 60 distinct paths, where both numbers are actually observable.
  - `[low]` `[patch]` Both `NotImplementedError` arms — added last pass precisely so a future catalog field cannot silently inherit category semantics — had no test, and the existing 500-path test monkeypatches the *other* method so it never reaches them. Added a test that whitelists a second field and asserts both refuse it.
  - `[low]` `[patch]` `get_field_value_suggestions`'s docstring claimed "the column's index serves the unfiltered ordering"; the unfiltered branch orders by `LOWER(category_path)`, which cannot use it either. Corrected to state that neither ordering uses the index and what the index is actually for — fixing, in the same edit, the 135-character line the previous pass's rewording left behind.

## Design Notes

**Why the server echoes `normalized`.** The create affordance must show the operator the value that will actually be stored, and AD-4 makes the pure util the single source of truth for that value. Mirroring the rules in JavaScript would create a second implementation that silently drifts; instead the suggestions response the component already fetches carries the canonical form of the current query, so the browser only ever *displays* a server-computed string.

**Why the create entry is just another `.dropdown-item`.** Keyboard navigation, highlighting, and selection all key off `.dropdown-item` + `dataset.value` (`field-autocomplete.js:180-212`), so adding one more such element buys ArrowDown/Enter/Escape/click for free and keeps the diff to `render()` plus one option:

```js
// after rendering suggestions, inside render()
if (this.allowCreate && this.createCandidate &&
    !suggestions.some(s => s.toLowerCase() === this.createCandidate)) {
    const a = this.buildItem(suggestions.length, this.createCandidate);
    a.textContent = `+ Create "${this.createCandidate}"`;
    a.classList.add('fw-semibold');
}
```

**Canonicalization example** (`normalize_category_path`):

```python
>>> normalize_category_path('  /Electronics // Power/DC-DC Converters/ ')
'electronics/power/dc-dc converters'
>>> normalize_category_path('   ') is None
True
```

**No `categories` table.** The architecture left "helper index vs `categories` table" to this epic. Distinct-value queries over the already-indexed `products.category_path` serve FR14/FR15 directly, and Story 3.2's rename is a prefix-scoped bulk `UPDATE` over the same column — a node table would add a second source of truth for a value the products already carry, plus lifecycle questions (orphan pruning, empty ancestors) that no requirement asks for.

**Ancestors are not synthesized.** Typing `a/b/c` makes `a/b/c` available; bare `a` and `a/b` are offered only once some product uses them. That is exactly "the tree accretes from use" (FR15), and it keeps the suggestion source a single `DISTINCT` query.

**E2E isolation.** `tests/e2e/test_server.py:311` clears photos, inventory items, and the material taxonomy but not `products`, so product rows accumulate across the session. New e2e tests must therefore use a distinctive path prefix and assert containment, never absence.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all green, no pre-existing test regressed.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- -k "category or Category or FieldSuggestions or Product"` -- expected: the new util, service, and route classes run and pass.
- `venv/bin/python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"` -- expected: exactly one head, the new revision.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- -k "category_autocomplete"` -- expected: both new e2e tests pass. **Set a 20-minute tool timeout for this command.**

**Manual checks (if no CLI):**
- `grep -nE "import flask|from flask|sqlalchemy|from app|import app" app/utils/category.py` returns nothing, and `grep -n "normalize" app/static/js/field-autocomplete.js` shows no normalization logic — only use of the server-supplied value.
- No screenshot regeneration is required: `tests/e2e/screenshot_config.yaml` contains no product pages.



## Auto Run Result

Status: done
Blocking condition: none

### Implemented change

Second follow-up review pass over the already-implemented story. No code was re-derived: there were no intent gaps and no bad-spec findings, so the intent contract and the spec sections outside it are untouched. Eight patches applied, all caused or exposed by this story's diff — one medium behavioral defect in the shared autocomplete component (the *previous* pass's fix could not run on the case it was written for), one regression the same previous fix introduced, two migration-honesty fixes, three test-quality fixes, and one docstring correction. One finding deferred, eighteen rejected.

### Files changed

- `app/static/js/field-autocomplete.js` — Escape is now handled *before* `onKeyDown`'s "dropdown not visible" early return, so it cancels a pending debounced fetch instead of being a no-op during the exact ~200 ms window `dismiss()` exists for; the blur timeout handle is kept and cleared on focus, so a fast blur→refocus can no longer invalidate the fetch the refocus just started.
- `migrations/versions/f8e66632ee42_normalize_existing_category_paths.py` — the skip comment's false claim (that only a >512-character legacy row can fail to normalize) corrected, since lowercasing can lengthen a string; skipped rows are now collected and reported by a warning naming the product ids rather than passed over silently.
- `app/mariadb_catalog_service.py` — `get_field_value_suggestions`'s docstring no longer claims the column index serves the unfiltered ordering (it orders by `LOWER(...)` and cannot use it); the 135-character line left by the previous pass's rewording is gone.
- `tests/unit/test_category.py` — `test_max_length_mirrors_the_column` reads the length off `Product.__table__` instead of asserting `512 == 512`.
- `tests/unit/test_catalog_service.py` — new test seeding 60 distinct paths so the 50 ceiling and 10 default are observable; new test whitelisting a second field to pin both `NotImplementedError` arms.
- `tests/e2e/test_category_autocomplete.py` — new Escape-while-hidden test (mutation-verified); new ArrowDown+Enter test covering the matrix's keyboard path to the create entry.

### Review findings breakdown

8 patches applied (1 medium, 7 low) — see the Review Triage Log for each. 1 item deferred to `deferred-work.md` (the user manual has no Products chapter at all, so this story's operator-visible canonicalization is documented only inside the REST API reference; closing it means authoring a chapter Epic 1 never wrote). 18 findings rejected, the substantive ones being: the migration reading all non-NULL rows into memory (the write chunking it is contrasted against guards a different limit — IN-clause size — and this catalog is orders of magnitude below either); the ~90 lines mirrored from the inventory service, the single shared endpoint URL, and the response body carrying `normalized` only for catalog fields (all three are explicit intent-contract mandates, not drift); the absence of a migration-runner test and the raw-vs-normalized 512-character asymmetry (both already on the ledger); `?location=` being ignored for catalog fields (documented); a label-click race (the HTML spec runs label activation *after* click dispatch, so the focus fetch starts after the dismissal, and a guard would change behavior for all six fields); `suppressNextFetch` sticking (`dispatchEvent` is synchronous, so the flag is always consumed by the listener it was set for); non-string input no longer passing through to storage (the contract specifies rejection); and the story's own in-flight frontmatter/`final_revision` values, which this section is what updates.

### Verification performed

- `nox -s tests` — **871 passed**, 310 deselected (up from 866: five new unit tests). No pre-existing test regressed.
- `nox -s e2e -- -k "category_autocomplete or field_autocomplete"` — **12 passed**, no reruns consumed: 5 category tests plus all 7 pre-existing field-autocomplete tests, confirming the two component changes did not alter behavior for the five item fields.
- The new Escape-while-hidden test verified non-vacuous: with the guard reinstated above the Escape branch it failed 4/4 (initial run plus all 3 reruns) with "Locator expected to be hidden"; restored, it passes.
- Migration re-driven against a scratch SQLite database (1206 rows): the three spellings of one category collapsed to `electronics/power` across 1200 rows via chunked UPDATEs, an already-canonical row and a NULL row untouched, a separators-only row nulled, and **both** unnormalizable rows — a 600-character one and a 300-character `'İ' * 300` one that fits the column but lowercases to 600 — skipped and named in the new warning. This is what confirmed the old comment was wrong.
- No template, CSS or screenshot-relevant file was touched in this pass.

### Residual risks

- Both behavioral changes are in the component behind all six autocomplete fields, and this is the second consecutive pass to find a live defect in it. It is covered by 12 e2e tests, but there is still no JS unit-test infrastructure, so the component is pinned only at browser level and only where a test thought to look — this pass's finding was precisely a branch an existing test stepped over.
- The migration's skip warning goes to stdout. `manage.py db upgrade` run non-interactively (a deploy script capturing output) could still lose it.
- Carried forward unchanged: no test executes an Alembic migration (on the ledger); all unit tests run on SQLite's binary collation while production is MariaDB case-insensitive; the create affordance has no unit-test surface.
