---
title: 'Category rename with descendants'
type: 'feature'
created: '2026-07-24'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
baseline_revision: 'b95d233'
final_revision: '6c33564'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** Story 3.1 made `products.category_path` a canonical materialized path that accretes from use, but the tree is now write-once: there is no way to rename a node. A typo or a reorganization (`electronics/power` → `electronics/psu`) can only be fixed by editing every affected product one at a time, and the operator cannot even see which paths exist — there is no category listing page anywhere in the app. FR17's descendant-carrying rename and its collision rejection have no implementation, and `app/utils/category.py`'s docstring already promises this story will add the segment-boundary prefix predicate it deliberately left out.

**Approach:** Add the promised pure predicate to `app/utils/category.py` — segment-boundary containment, the escaped SQL `LIKE` pattern for a subtree, and the per-path prefix rewrite — as the single source of truth Epic 8's faceting will also call (AD-4). Build `CatalogService.rename_category_path(old, new)` on it: one session loads every product at or under the source path, rewrites each path, and commits once, so the whole subtree moves atomically or not at all. Reject a rename whose destination node already exists outside the source subtree with a `ValidationError` naming the conflict, rather than merging two branches. Surface both through two server-rendered pages on the `main` blueprint (`/products/categories` listing paths with product counts, and a rename form that previews exactly what will change), reached from the existing Products navbar dropdown.

## Boundaries & Constraints

**Always:**
- Every new helper in `app/utils/category.py` stays **pure** — stdlib only, no Flask/SQLAlchemy/`app.*` imports (absolute or relative, and no `from .`), no I/O — and keeps the existing module-local `InvalidCategoryPathError(ValueError)` as its only error type. The existing purity-guard test class must still pass unmodified (AD-4, NFR7).
- Segment-boundary semantics are defined **once**, in the util: a path is at-or-under an ancestor when it equals it or starts with `ancestor + '/'`. `thermal/heat` must never match `thermal/heatgun-parts`. The service, the routes and the templates call the util; none of them re-derives `'/'` logic or writes a bare `startswith`.
- The subtree `LIKE` pattern is built by the util with `%`, `_` and the escape character itself escaped, and every `.like()` using it passes the matching `escape=` argument — canonical paths legitimately contain `_` and `%` inside segments.
- `CatalogService.rename_category_path` normalizes **both** arguments through `normalize_category_path` before doing anything, does all its work on one `self.Session()`, and reaches exactly one `commit()`. A rejection or any failure leaves every row untouched.
- Rejections are `app.exceptions.ValidationError` with a `field` of `'old_path'` or `'new_path'` and an operator-readable message, raised past a `session.rollback()` in the `except ValidationError:` arm — the pattern `add_attachment`/`add_identifier` already use (`app/mariadb_catalog_service.py:780-783`). Do **not** adopt `create_product`/`update_product`'s swallow-and-return-`None` convention: the operator must see why a rename was refused.
- The new pages are server-rendered Jinja templates extending `base.html`, POST with a hidden `csrf_token` (`app/templates/admin/add_material.html:55-56`), and report outcomes with `flash()` + redirect on success / re-render with the message on rejection — the `admin.add_material` pattern (`app/admin/routes.py:88-108`). The success flash states how many products were updated.
- The rename form shows the affected paths and product count **before** submission, so the confirmable outcome is the form itself.
- New tests carry `@pytest.mark.unit` or `@pytest.mark.e2e`, use the house parametrize idiom (one case per line with an aligned trailing `#` comment), and cite FR17/AD-4 in docstrings. E2E tests mint a unique path prefix per invocation and assert only positively — `clear_test_data()` never truncates `products` (`tests/e2e/test_server.py:311-332`).

**Block If:**
- `nox -s tests` is already red on this branch before any change — pre-existing breakage, not this story's.
- Implementing the collision rule would require changing what Story 3.1 stores or how it normalizes.

**Never:**
- No schema change and no migration: this story stores nothing new. Do not touch `app/database.py` or `migrations/`.
- No `categories` table, no node entity — the tree is still the distinct set of assigned `products.category_path` values.
- No category **delete**, **merge**, or explicit **move** operation, and no bulk reassignment of products between unrelated paths. Rename is the only mutation.
- No filtering or faceting by category, no clickable category on the product detail page, no change to `app/templates/product/detail.html` — Epic 8 owns retrieval.
- No changes to `app/utils/category.py`'s existing `normalize_category_path` behavior, to `get_field_value_suggestions`/`normalize_suggestion_value`, to `app/static/js/field-autocomplete.js`, to the `/api/inventory/field-suggestions/<field>` endpoint, or to any inventory/metal-stock behavior (NFR9).
- No autocomplete on the new-path input: the destination must not already exist, so offering existing paths would contradict the operation.
- No new JSON API endpoint, no JS file, no new dependency, no build step.
- No `docs/user-manual.md` Products chapter — its absence is already an open deferred-work entry, and authoring it is larger than this story.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Descendant predicate | `is_descendant_path('a/b/c', 'a/b')`, `('a/b', 'a/b')` | `True` — at-or-under is inclusive | No error |
| Segment boundary | `is_descendant_path('thermal/heatgun-parts', 'thermal/heat')`, `('ab', 'a')` | `False` — string prefix is not a path prefix | No error |
| LIKE pattern escaping | `descendant_like_pattern('power_supplies/50%')` | the 22-character pattern `power\_supplies/50\%/%` — every literal `_`, `%` and backslash in the ancestor prefixed with the escape character, then a trailing `/%`; the same character is passed as `.like(…, escape=…)` | No error |
| Path rewrite | `rewrite_category_path('a/b/c', 'a/b', 'x/y')`, `('a/b', 'a/b', 'x/y')` | `'x/y/c'`, `'x/y'` | No error |
| Rewrite of a non-descendant | `rewrite_category_path('a/z', 'a/b', 'x')` | rejected — a caller fault | `InvalidCategoryPathError` |
| Rewrite past the column | result longer than `MAX_CATEGORY_PATH_LENGTH` | rejected | `InvalidCategoryPathError` |
| Rename carries descendants | products at `electronics/power`, `electronics/power/dc-dc`, `electronics/cables`; rename `electronics/power` → `electronics/psu` | first two become `electronics/psu`, `electronics/psu/dc-dc`; `electronics/cables` and every `NULL` row untouched; returns `2` | No error |
| Rename normalizes input | rename `' /Electronics/Power/ '` → `'Electronics / PSU'` | treated as `electronics/power` → `electronics/psu` | No error |
| Source has no products | rename `nosuch/path` → `x` | rejected; nothing changed | `ValidationError(field='old_path')` naming the missing path |
| Destination node exists | products at `electronics/psu` (or at `electronics/psu/xyz`); rename `electronics/power` → `electronics/psu` | rejected; nothing changed; message says the category already exists and names how many products are filed under it | `ValidationError(field='new_path')` |
| Destination shares a parent only | products at `electronics/cables`; rename `electronics/power` → `electronics/psu` | allowed — `electronics/psu` is a fresh node | No error |
| Destination inside the source | rename `a` → `a/b` with rows `a`, `a/x` | allowed — becomes `a/b`, `a/b/x`; well-defined and reversible | No error |
| Promote onto an occupied node | rows `a/b/c` and `a/other`; rename `a/b` → `a` | rejected — node `a` already holds `a/other` | `ValidationError(field='new_path')` |
| No-op rename | rename `electronics/power` → `Electronics/Power/` (same after normalization) | rejected; nothing changed | `ValidationError(field='new_path')` |
| Blank path | either argument normalizes to `None` (`''`, `'   '`, `'/'`, `None`) | rejected | `ValidationError` on the offending field |
| Non-string / over-length argument | `5`, or a value normalizing past 512 chars | rejected as a request error, not a 500 | `ValidationError` (the util's `InvalidCategoryPathError` converted) |
| Descendant would exceed the column | source subtree deep, destination long enough that a rewritten descendant exceeds 512 | rejected before any write; nothing changed | `ValidationError(field='new_path')` |
| Category listing | products at `a/b` (×2), `a` (×1), one `NULL`, one `''` | `list_category_paths()` → `[('a', 1), ('a/b', 2)]` — alphabetical, blanks and `NULL` excluded | No error |
| Listing page | `GET /products/categories` | 200; each assigned path listed with its product count and a Rename link carrying `?path=` | No error |
| Rename form preview | `GET /products/categories/rename?path=electronics/power` | 200; shows the source path, the paths that will move and the total product count, and an empty new-path input | No error |
| Rename form, unknown path | `GET /products/categories/rename?path=nosuch` | flash + redirect to `/products/categories` | No error |
| Rename POST success | valid rename via the form | flash `success` naming old, new and the product count; 302 to `/products/categories` | No error |
| Rename POST rejected | any rejection above | 200 re-rendering the form with the `ValidationError` message and the submitted value retained; no row changed | Message rendered on the page |

</intent-contract>

## Code Map

- `app/utils/category.py` -- the pure util (117 lines). `CATEGORY_PATH_SEPARATOR` (:46), `MAX_CATEGORY_PATH_LENGTH` (:51, mirrors the column), `InvalidCategoryPathError` (:54), `normalize_category_path` (:67). Its docstring (:36-40) already declares that **this** story adds the segment-boundary prefix predicate here. Match the house style: module-level functions, full type hints, `Args:/Returns:/Raises:/Examples:` docstrings.
- `app/mariadb_catalog_service.py` -- `FIELD_SUGGESTION_COLUMNS` (:73), `_clean` (:78), `CatalogService` (:87), `create_product` (:149), `update_product` (:253, normalizes `category_path` at :285), `get_field_value_suggestions` (:358) incl. the local `_escape_like` (:446-451) and its `.like(pattern, escape='\\')` calls (:466-471) — the escaping convention to mirror. `add_attachment` (:729-791) is the `ValidationError`-raising session pattern to copy (`except ValidationError: rollback; raise`, `finally: close`). No method in this file does a multi-row UPDATE today.
- `app/exceptions.py` -- `ValidationError(message, field=None, value=None)` (:17).
- `app/logging_config.py` -- `log_audit_operation(operation_name, phase, item_id=…, changes=…, error_details=…, logger_name=…)` (:255).
- `app/main/routes.py` -- `_get_catalog_service()` (:84), `_PRODUCT_FIELD_LIMITS` (:750), product routes `product_add` (:781), `product_detail` (:819), `product_edit` (:955); `field_suggestions` (:1424) — **do not touch**. Flash+redirect idiom at :810-816.
- `app/admin/routes.py:49-108` + `app/templates/admin/add_material.html` -- the GET-form / POST-handler / flash / re-render-with-`form_data` pattern and the hidden-CSRF markup to follow.
- `app/templates/base.html:57-64` -- the Products navbar dropdown; today one item (`main.product_add` at :62). One `<li>` is added here; nothing else in the shared nav changes, and `tests/e2e/screenshot_config.yaml` contains no product pages.
- `app/templates/product/add.html`, `edit.html`, `detail.html` -- existing product templates for markup conventions (`{% extends "base.html" %}`, card layout, `{% block content %}`). `detail.html:27` renders the category; unchanged by this story.
- `tests/unit/test_category.py` -- `_MATRIX_CASES` table (:25-43), `TestPublicConstants` (:46), `TestNormalizeCategoryPath` (:76), `TestPureModuleHasNoAppImports` (:151) — the purity guard that must keep passing.
- `tests/unit/test_catalog_service.py` -- module fixture `catalog_service` (:13-15) over the shared `test_storage` SQLite fixture; `TestCategoryPathNormalization` (:1076) and `TestCatalogFieldValueSuggestions` (:1131) show the house parametrize idiom and a class-local seeding fixture.
- `tests/unit/test_product_routes.py` -- class-level `@pytest.mark.unit`, per-class `_make_product` helper seeding through `CatalogService`, byte assertions on `resp.data`, 302 + `resp.headers['Location']` checks. CSRF is off in tests (`tests/test_config.py:18`).
- `tests/e2e/test_category_autocomplete.py` -- `_unique_prefix()` (:25-27) and `_add_product()` (:38-45) helpers, flat `@pytest.mark.e2e` functions taking `(page, live_server)`. `tests/e2e/test_server.py:311-332` clears inventory but never `products`.

## Tasks & Acceptance

**Execution:**
- [x] `app/utils/category.py` -- add `CATEGORY_LIKE_ESCAPE_CHAR`, `is_descendant_path(candidate, ancestor) -> bool`, `descendant_like_pattern(ancestor) -> str`, and `rewrite_category_path(path, old_root, new_root) -> str`; all pure, all assuming already-canonical inputs (say so in the docstrings), raising `InvalidCategoryPathError` for a caller fault or an over-length result -- the single source of truth for segment-boundary logic that Epic 8 will also call (FR17, AD-4).
- [x] `tests/unit/test_category.py` -- add classes covering every predicate/pattern/rewrite row of the matrix, including `thermal/heat` vs `thermal/heatgun-parts`, `_`/`%`/backslash escaping, equality-is-inclusive, and rewrite rejections -- the pure util gets exhaustive tests (NFR7).
- [x] `app/mariadb_catalog_service.py` -- add `list_category_paths(self) -> List[Tuple[str, int]]` (assigned paths with product counts, blanks and `NULL` excluded, alphabetical) and `rename_category_path(self, old_path, new_path) -> int` implementing the matrix on one session with a single commit, raising `ValidationError` for every rejection and audit-logging success and failure -- the atomic subtree rewrite lives behind the service seam (FR17, AD-1).
- [x] `tests/unit/test_catalog_service.py` -- add a `TestCategoryRename` class covering the carry-descendants happy path, untouched siblings/`NULL` rows, both argument-normalization cases, and every rejection (missing source, existing destination node, promote-onto-occupied-node, no-op, blank, non-string, over-length rewrite), each asserting the database is unchanged after a rejection; plus a `TestListCategoryPaths` class -- the invariant is enforced in the service (FR17).
- [x] `app/main/routes.py` -- add `GET /products/categories` (`category_list`) and `GET,POST /products/categories/rename` (`category_rename`): the GET form resolves `?path=`, redirects with a flash when the path holds no products, and previews the affected paths and count via `list_category_paths()` + `is_descendant_path`; the POST calls the service, flashes success and redirects to the listing, or catches `ValidationError` and re-renders the form with the message -- no ORM or path logic in routes (AD-1/AD-2, FR17).
- [x] `app/templates/product/categories.html` -- **new**: table of assigned category paths with product counts and a Rename link per row (`?path=…`), plus an empty state when no categories exist -- gives the accreting tree its first visible surface.
- [x] `app/templates/product/category_rename.html` -- **new**: form showing the source path, the paths that will move with their counts, a `new_path` text input retaining the submitted value, hidden `csrf_token`, and Cancel/Rename buttons -- the preview is the confirmation.
- [x] `app/templates/base.html` -- add one "Manage Categories" `<li>` to the existing Products dropdown (:57-64) -- the only nav change; leaves the collapsed navbar and every docs screenshot identical.
- [x] `tests/unit/test_product_routes.py` -- add a `TestCategoryPages` class: listing renders paths and counts, rename GET previews the subtree, rename GET with an unknown path redirects, rename POST persists and redirects, rename POST on a collision returns 200 with the message and leaves every row unchanged -- covers the operator path below the browser.
- [x] `tests/e2e/test_category_rename.py` -- **new**: with a unique prefix, create two products (a parent path and a descendant), rename the parent through the form, and assert both products' detail pages show rewritten paths; second test asserts a colliding rename re-renders with the error and leaves the path intact -- positive-only assertions, since `products` is never cleared.

**Acceptance Criteria:**
- Given products filed at `electronics/power` and `electronics/power/dc-dc`, when the operator renames `electronics/power` to `electronics/psu` on `/products/categories/rename`, then both products are refiled under the new path in a single transaction and a flash reports the number updated (FR17).
- Given a product already filed under the destination path, when the operator submits that rename, then the form re-renders with a message explaining the conflict and no product's `category_path` has changed.
- Given a product filed at `thermal/heatgun-parts`, when the operator renames `thermal/heat`, then that product is not touched.
- Given the whole change, when `nox -s tests` runs, then it is green with no pre-existing test regressed, and `app/utils/category.py` still passes its purity guard.

## Spec Change Log

## Review Triage Log

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 1, medium 2, low 9)
- defer: 2: (high 0, medium 1, low 1)
- reject: 8: (high 0, medium 0, low 8)
- addressed_findings:
  - `[high]` `[patch]` The listing could not reach an interior node, so FR17's own acceptance criterion — "products assigned **under** `electronics/power/`, rename that segment" — had no affordance. `list_category_paths()` returns only paths products carry *directly*, so a catalog whose sole product sits at `electronics/power/dc-dc` listed one row and offered one Rename link; renaming `electronics/power` (which the service handles correctly) required hand-editing the URL. Added the pure `ancestor_paths()` and a `_category_tree()` route helper that recovers every interior node with its filed-here and in-subtree counts.
  - `[medium]` `[patch]` A successful rename could be reported to the operator as a failure: `log_audit_operation` sat inside the `try` *after* `session.commit()`, so an audit-sink failure propagated to the route, which rendered "An error occurred… Please try again" for a rename that had fully committed — sending the operator back to a source path that no longer exists. The success log now sits past the commit boundary and cannot raise. Mutation-verified: the new test fails with the old placement.
  - `[medium]` `[patch]` A row the SQL matched but neither predicate claimed was silently dropped. MariaDB's collation is case-insensitive and the Python predicate is not, so a stored value the collation folds onto either subtree was neither moved (stranding it at the old path) nor counted as a blocker (letting through exactly the branch merge the method exists to refuse). Such rows are now named in a `ValidationError` instead of ignored. Mutation-verified.
  - `[low]` `[patch]` The `ValidationError.field` the service computes was discarded by the route, and the template painted the `new_path` input `is-invalid` for *any* error — so a rejected **source** path marked the destination field red. The form now marks the field the service actually refused and pairs it with an `invalid-feedback` element and `aria-describedby`, matching `add.html`/`edit.html`.
  - `[low]` `[patch]` The docstring stated the collision rejection as an invariant. It is a check-then-write with no constraint behind it (many products legitimately share a path, so there is no uniqueness to enforce); the single-operator assumption is now stated rather than implied.
  - `[low]` `[patch]` The `except ValidationError` and `except Exception` arms were byte-identical, so the first was pure duplication — and it *deviated* from the `add_attachment` pattern the spec named, which deliberately does not audit-error a refused submission. Collapsed; every blank-field submit no longer writes an operational-error audit record. The pure argument checks moved above the `try`, which retired all three `if 'session' in locals()` guards.
  - `[low]` `[patch]` `GET /products/categories/rename` with no `path` argument flashed `No products are filed under category ""`, naming the wrong problem; it now says "Pick a category to rename."
  - `[low]` `[patch]` The generic-failure branch re-ran the preview (a second database trip) *inside* the handler for a database failure, so a dead backend produced a 500 instead of the message the operator needs. Guarded, and covered by a test that kills both service calls.
  - `[low]` `[patch]` A route assertion pinned 27 characters of Jinja indentation across a line break, so any template reflow would redden it; and a count assertion matched `<td…>2</td>` anywhere on the page. Both now read the specific row via a helper that slices it out.
  - `[low]` `[patch]` `test_only_the_trailing_wildcard_is_unescaped` indexed `body[index - 1]`, which wraps to the last character when `index == 0` — the test was weakest at exactly the case a broken escaper produces. Explicit guard plus a leading-metacharacter test.
  - `[low]` `[patch]` Untested branches the spec pins: the destination-side segment boundary (renaming *into* `thermal/heat` while `thermal/heatgun-parts` exists must be allowed), destination-side LIKE escaping, a blocker sitting at exactly the destination node, the `updated_at` bump on every moved row, the route's generic-exception branch, and renaming an interior node with no products of its own. All now covered.
  - `[low]` `[patch]` The e2e success assertion used containment on the listing body, where the child row `…/psu/dc-dc` contains the parent `…/psu` — so it would have passed if only the child had moved. Now asserted on the flash text itself.

### 2026-07-24 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 0, medium 1, low 7)
- defer: 1: (high 0, medium 0, low 1)
- reject: 9: (high 0, medium 0, low 9)
- addressed_findings:
  - `[medium]` `[patch]` `GET /products/categories` — the page the navbar now links to — raised an uncaught `InvalidCategoryPathError` (a 500, not a handled `ValidationError`) for a stored path beginning with `/`. `_category_tree` fed raw stored values to `ancestor_paths`, which assumes canonical input: `ancestor_paths('/a/b')` yields an EMPTY ancestor, which `is_descendant_path` then refuses. Story 3.1's backfill migration *deliberately leaves* any row it could not normalize in place (`skipped_ids`, printed for a manual decision), so this is reachable on exactly the data the listing exists to surface — and the listing is the only place that row could be found. The same defect invented a phantom `a/` node beside the real `a` for a stored `a//b`, complete with its own Rename link that normalized back to `a` and would have moved a subtree the operator never selected. Interior nodes are now derived only from paths that are canonical (asked through `normalize_category_path`, so no rule is re-derived); a non-canonical row is still listed as its own node. Mutation-verified: both new tests fail with the guard removed.
  - `[low]` `[patch]` Every rejection printed its message twice — once in the `#rename-error` alert and again verbatim in an `invalid-feedback` element — since the route always passes `error_message` and `error_field` together. On a one-sentence rejection that reads as two separate problems. The alert is now the single message; the `old_path` feedback element (which decorated a *hidden* input and so marked nothing) is gone, and `#new_path-error` keeps `aria-describedby` a target without restating the sentence.
  - `[low]` `[patch]` The backend-failure page contradicted itself. `_rerender`'s `except Exception:` collapsed the unreadable preview to `(None, [], 0)`, so the template rendered "An error occurred while renaming the category" beside "No products are filed under this category" and "Products affected: 0" — asserting, as fact, something never established, and reading as if the operator's category had just been emptied. The template is now told the preview is *unknown* rather than empty. The pre-existing test claimed to guard this branch but only asserted the error string was present; it now asserts the contradictory text is absent.
  - `[low]` `[patch]` The `except Exception` arm's `log_audit_operation` could replace the very failure it was asked to record: an audit sink that raises propagated in place of the database error, and the real cause was then logged nowhere at all. Wrapped, matching the guarantee the success path already gave. New test fails without the wrap.
  - `[low]` `[patch]` The "What Will Move" table omitted the node being renamed whenever no product was filed at it directly — precisely the interior-node case FR17's own acceptance criterion uses, and the case the previous pass added interior nodes to the listing for. The source path is now always a row. The GET's "nothing to rename" redirect moved from `not affected` to `not total`, which is the condition it always meant.
  - `[low]` `[patch]` `audit_id` was built from the raw, un-normalized (and possibly non-string) argument while the `changes` payload used the canonical form, so one category's history filed itself under `category: /Electronics/Power/ ` or `category:electronics/power` depending on how the operator typed it that day. Keyed on the canonical source now.
  - `[low]` `[patch]` The non-canonical-rows rejection capped its id list at 20 with no ellipsis and no total, so an operator who fixed the twenty named products and hit the identical-looking error again had no way to know the list was ever partial. The cap is now stated, as the Story 3.1 migration already states its own.
  - `[low]` `[patch]` The rename's subtree query hydrated every column of both subtrees, including `Product.notes` (`Text`), to read and write one `varchar` per row. Deferred, following the `defer(Attachment.content)` precedent the same module already sets.

### 2026-07-24 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 1, medium 1, low 2)
- defer: 1: (high 0, medium 0, low 1)
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[high]` `[patch]` The listing's Rename link on a non-canonical row could rename a **different** category than the row the operator clicked. `_category_rename_preview` normalizes `?path=` before matching stored paths, so a legacy `Electronics/Power` (the row class Story 3.1's backfill deliberately leaves in place, and which the previous pass hardened the listing to display) resolved onto the canonical `electronics/power` — rendering a full preview of the twin's subtree and, on submit, moving it, with a flash naming a path the operator never selected. Where no twin existed, the same link dead-ended on "No products are filed under…" beside the non-zero counts the listing had just printed. The previous pass logged the dead-end as a harmless residual risk; the wrong-target rename half was not seen. `_category_tree` now carries a per-row `is_canonical` flag and the template withholds the link (the row stays visible, badged "Not canonical"), and the GET refuses a non-canonical `?path=` outright rather than normalizing it. Mutation-verified: both new tests fail with either guard removed.
  - `[medium]` `[patch]` `list_category_paths` grouped in SQL (`GROUP BY category_path`), which under MariaDB's default case-insensitive PAD SPACE collation folds `Electronics/Power`, `electronics/power ` and `electronics/power` into one row with an arbitrary representative and a summed count — hiding a distinct stored path from the only page that surfaces it and attributing its products to a row a rename would not move. This is the exact hazard Story 3.1's backfill migration documents avoiding (it reads rows individually rather than `SELECT DISTINCT`), and its skipped rows are what make the two spellings coexist. Grouping moved to Python; the SQL now only narrows. Not reachable under the SQLite unit fixture's binary collation, so this one is reasoned from the migration's own precedent rather than test-demonstrated.
  - `[low]` `[patch]` A product already past the 512-character column (again, a row the backfill leaves) refuses every rename of its branch, and the refusal named only `new_path` and the over-long result — sending the operator hunting for a shorter destination when the fix is one specific product. The message now names the product id.
  - `[low]` `[patch]` `test_rename_form_previews_the_subtree` asserted `b'value=""'` page-wide, so it would have passed with the destination input pre-filled from any other empty attribute on the page. Now read off the `new_path` tag itself.

## Design Notes

**The collision rule, precisely.** A rename is rejected when the destination *node already exists*: some product **outside the source subtree** has `category_path == new_path` or is a descendant of it. Excluding the source subtree is what makes a legitimate promote (`a/b` → `a` when nothing else lives under `a`) work while still rejecting the merge cases — the sibling collision the AC names, and promoting onto a node that already holds products. One predicate, applied to the destination exactly as it is applied to the source:

```python
moving   = [p for p in rows if is_descendant_path(p.category_path, old_path)]
blockers = [p for p in rows if is_descendant_path(p.category_path, new_path)
            and not is_descendant_path(p.category_path, old_path)]
```

**Interior nodes are listed, not just assigned paths.** `list_category_paths()` returns exactly what the matrix pins — the paths products carry, with direct counts. But a tree stored only as its leaves hides its own interior: a catalog whose sole product sits at `electronics/power/dc-dc` would list one row, and `electronics/power` — the node FR17's acceptance criterion renames — would have no Rename link at all. The listing page therefore recovers interior nodes through the pure `ancestor_paths()` and shows both a "filed here" and an "in subtree" count, so every node of the tree is renameable. Rows are sorted by segment tuple rather than by byte, because `-` (0x2D) sorts below `/` (0x2F) and plain string ordering wedges `electronics-old` between `electronics` and its children.

**A stored path is not guaranteed canonical.** Story 3.1's backfill migration deliberately leaves any row it could not normalize exactly as it found it — a SQLite-era value past 512 characters, or one whose canonical form is *longer* than the original — and prints those ids for a manual decision. Every helper in `app/utils/category.py` assumes canonical input, so the listing (the one page an operator would use to find such a row) guards the boundary with `_is_canonical_path`, which asks `normalize_category_path` rather than re-deriving any rule. A non-canonical row is still listed as its own node; it just contributes no interior ones. Without that guard `ancestor_paths('/a/b')` yields an empty ancestor, `is_descendant_path` refuses it, and the whole page 500s — and `a//b` invents a phantom `a/` node whose Rename link normalizes back to `a`.

Such a row is also **not renameable through these pages**, and says so. The rename form normalizes its `?path=` before matching anything, so a link built from a non-canonical row can only resolve somewhere else: to nothing (a redirect contradicting the counts the row just showed) or, where the canonical twin also exists, to a real category the operator never picked — which the POST would then move. The listing therefore badges the row "Not canonical" instead of linking it, and the GET refuses a non-canonical `?path=` rather than normalizing it. Fixing such a row means refiling its products from the product form, which canonicalizes on the way in.

That is also why `list_category_paths` groups in **Python**. MariaDB's default collation is case-insensitive and PAD SPACE, so `GROUP BY category_path` folds exactly the spellings that coexist only because of these rows — one arbitrary representative, one summed count, and the other path invisible on the page that exists to find it. Story 3.1's backfill migration reads rows individually for the same reason and says so in a comment. The SQL narrows; Python decides — the division `rename_category_path` already makes with its `LIKE`.

**Why per-row ORM mutation rather than one bulk `UPDATE`.** Each descendant needs a different suffix preserved, so a single statement would need backend-specific `CONCAT`/`SUBSTRING`. Loading the subtree and setting `p.category_path` keeps the code in the file's established style, lets every rewritten path be length-checked *before* the commit, and bumps `updated_at` via the model's `onupdate` — which is correct here (unlike the data migration, which deliberately does not). One transaction covers the whole subtree.

**Case and collation.** Every stored path has been canonical (lowercase) since Story 3.1 and its backfill, so the `LIKE` comparison behaves identically under SQLite's binary collation and MariaDB's case-insensitive one. What does *not* survive collation differences is wildcard escaping — hence `descendant_like_pattern` escapes `%`, `_` and the backslash itself, and every caller passes the matching `escape=` argument.

**Where the pages live.** Categories are a catalog concern, so the pages sit on the `main` blueprint beside the other product routes and reach `CatalogService` through the existing `_get_catalog_service()` — rather than on the `admin` blueprint, which builds the materials-taxonomy service and would need a second service dependency. The Products navbar dropdown already exists and gains one item, so no collapsed-navbar pixels change.

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all green, no pre-existing test regressed.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- -k "category or Category"` -- expected: the new util, service and route classes run and pass.
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e -- -k "category_rename or category_autocomplete"` -- expected: the new rename tests pass and Story 3.1's autocomplete tests still pass. **Set a 20-minute tool timeout for this command.**
- `venv/bin/python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"` -- expected: still exactly `('f8e66632ee42',)` — this story adds no migration.

**Manual checks (if no CLI):**
- `grep -nE "import flask|from flask|sqlalchemy|from app|import app|^from \." app/utils/category.py` returns nothing.
- `grep -rn "startswith('/'\|startswith(.*+ '/')\|+ '/%'" app/main/routes.py app/mariadb_catalog_service.py app/templates/product/` returns nothing — segment-boundary logic exists only in `app/utils/category.py`.
- `git diff --stat` shows no file under `migrations/`, no change to `app/database.py`, and no change to `app/static/js/field-autocomplete.js`.




## Auto Run Result

Status: done — second follow-up review pass over the committed Story 3.2 change (baseline `b95d233`, prior final `29b47b3`). No intent gap and no spec defect: every finding was a localized code fix, so no loopback was triggered.

**Change reviewed:** the segment-boundary predicate set in the pure `app/utils/category.py`, `CatalogService.list_category_paths`/`rename_category_path`, the `/products/categories` listing and `/products/categories/rename` form, and their unit/e2e coverage.

**Files changed in this pass:**
- `app/main/routes.py` — `_category_tree` carries a per-row `is_canonical` flag; the rename GET refuses a non-canonical `?path=` with an explanation instead of normalizing it onto a different category.
- `app/mariadb_catalog_service.py` — `list_category_paths` groups in Python, so MariaDB's case-insensitive PAD SPACE collation can no longer fold two stored paths into one row; the over-length rewrite refusal names the offending product.
- `app/templates/product/categories.html` — a non-canonical row keeps its place but is badged "Not canonical" in place of a Rename link it cannot honor.
- `tests/unit/test_product_routes.py` — the withheld link and the refused `?path=` are covered, including the case where the canonical twin exists; the empty-destination assertion now reads the input's own tag rather than the whole page.
- `tests/unit/test_catalog_service.py` — the over-length refusal is asserted to name the product.

**Review findings:** 4 patched (1 high, 1 medium, 2 low), 1 deferred, 7 rejected. Rejected as noise or as settled spec decisions: renaming into one's own occupied subtree (`a` → `a/b` with `a/b` occupied — the matrix explicitly allows destination-inside-source, and every row moved is inside the subtree being renamed, all of it previewed), the preview not showing destination paths (the destination is typed after the preview renders; a live preview needs the JS the "Never" list forbids), the `unclaimed` guard's field attribution (already rejected in the prior pass), an `old_path` rejection re-rendering the form (the matrix pins 200-re-render for *any* rejection) and its paraphrased duplicate message (both reachable only by a hand-crafted POST), non-canonical descendants being carried along by a rename (they stay with their branch, which is the useful behavior), and subtree counts including rows that derive no interior node (the count is accurate; only the visual nesting is imperfect).

**Verification:**
- `nox -s tests` — 992 passed, 312 deselected. No pre-existing test regressed.
- `nox -s tests -- -k "category or Category"` — 206 passed.
- `nox -s e2e -- -k "category_rename or category_autocomplete"` — 7 passed; Story 3.1's autocomplete tests still green.
- Mutation-verified the high-severity fix: with the route guard and the template guard removed, `test_a_non_canonical_row_offers_no_rename_link` and `test_a_non_canonical_path_cannot_rename_its_canonical_twin` both fail.
- `app/utils/category.py` purity grep — empty. Segment-boundary grep outside the util — empty. Alembic heads still `('f8e66632ee42',)`. `git diff --stat` touches no file under `migrations/`, no `app/database.py`, no `app/static/js/field-autocomplete.js`.

**Residual risks:**
- The `list_category_paths` collation fix cannot be demonstrated by the unit suite: `test_storage` is SQLite, whose binary collation makes SQL grouping and Python grouping identical. It rests on the Story 3.1 migration's documented precedent for the same column on the same backend.
- A non-canonical legacy row is now honestly un-renameable rather than dangerously renameable, but the app still offers no way to *fix* one beyond editing each of its products from the product form.
- The `unclaimed` collation-fold branch remains unreachable under SQLite, so its behavior on MariaDB is covered only by a simulated fold.
- CSRF hidden inputs and the util's docstring `Examples:` blocks remain unexercised by any test layer (both deferred).
