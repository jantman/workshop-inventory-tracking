# Phase 0 Research: Keep the Catalogue Tidy

The spec left no `[NEEDS CLARIFICATION]` markers, so this is not a list of unknowns resolved. It is the set of design decisions the plan rests on, each with what was rejected and why — recorded so that planning does not get re-litigated during implementation.

Everything here was established by reading the code as it stands on `main`, not by assumption. File and line references are to that state.

---

## D1 — A category rename is a bulk column update, not a tree operation

**Decision**: Rename by rewriting `products.category_path` for every product whose path equals the source or begins with the source plus `/`. The path arithmetic lives in `app/utils/category.py` as pure functions.

**Rationale**: `app/utils/category.py:1-15` states the model plainly: a category is a materialized path stored on the product, there is no categories table, and an empty category cannot exist. That means there is no node to rename — only strings to rewrite. `descendant_like_pattern()` (line 99) already exists and already escapes LIKE wildcards, so the "find the subtree" half of the problem is solved; the rename adds the "rewrite the prefix" half.

Doing the arithmetic in the pure module keeps it unit-testable without a database, which is how `is_descendant` and `canonical` are already tested in `tests/unit/test_category.py`.

**Alternatives considered**:

- *Introduce a categories table so a rename is a single row update.* Rejected. It reintroduces the CRUD, the empty-category state and the orphan-cleanup story the current design deliberately does not have, and it would require migrating every existing path into rows. The rename is the only operation that would benefit, and a bulk `UPDATE` over tens of products is not a problem worth a schema for.
- *Rewrite paths in Python by loading every product.* Rejected as unnecessary; the filter is expressible in SQL and the existing helper already builds it.

---

## D2 — "Collision" means a product outside the source subtree already sits at or under the target

**Decision**: A rename `old → new` is refused when there exists a product whose category path is `new` or a descendant of `new`, *excluding* products that are within the `old` subtree.

**Rationale**: The exclusion is what makes the obvious cases behave. Renaming `a` to `b` where `a/b` exists must succeed — `a/b` becomes `b/b`, and `b` did not previously exist. Without the exclusion, `a/b` would be seen as "already under `b`" and the rename would be refused for no reason the operator could understand.

FR-004 requires refusal rather than merging, and requires the conflict to be named. The check therefore returns *which* path collided so the message can say so.

**Alternatives considered**:

- *Refuse only on an exact path match.* Rejected: renaming `a` to `b` when `b/c` exists would silently graft `a`'s products into an existing subtree — the merge FR-004 exists to prevent.
- *Offer to merge on collision.* Rejected: the spec settles this explicitly (issue #61 describes the plan as refusing a colliding category rename), and merging categories has no observed need.

---

## D3 — Self-nesting and no-op are distinct refusals, checked in that order

**Decision**: Canonicalize both paths, then: equal → report "nothing to rename"; target is a descendant of the source → report self-nesting; otherwise continue.

**Rationale**: Both are edge cases the spec calls out. `canonical()` lowercases and trims, so `Resistors` → `resistors` is genuinely a no-op at the data level; accepting it silently would leave the operator believing a correction was applied. And `power → power/supplies` would make every path infinitely re-prefixable, so it must be caught before any rewrite. Ordering matters only in that equality is the more specific case and produces the clearer message.

---

## D4 — Path length is validated across the whole subtree before anything is written

**Decision**: Compute every rewritten path; if any exceeds `MAX_CATEGORY_PATH_LENGTH` (512, `app/catalog_service.py:42`), refuse the entire rename.

**Rationale**: `_validate_category_path` (line 1344) already treats over-length as a rejection rather than a truncation, and a silently truncated path is a corrupted one. The deepest descendant is the one at risk when a short parent is renamed to a long name, and it is not the row the operator is looking at — so the check has to cover the subtree, not the renamed level.

---

## D5 — Atomicity comes from the existing session context manager, not new machinery

**Decision**: Each rename runs inside one `CatalogService._session()` block, with all validation performed inside it before any mutation. A refusal raises `ValidationError`, which the context manager turns into a rollback.

**Rationale**: `_session()` (`app/catalog_service.py:75-86`) already commits on success and rolls back on any exception. FR-007 and FR-012 are satisfied by using it correctly rather than by adding a transaction wrapper, a two-phase apply, or a dry-run mode.

---

## D6 — Tag merge moves products through the relationship, with a membership check

**Decision**: When the target tag name already exists, iterate the source tag's products and append the survivor to any that do not already carry it, then delete the source tag.

**Rationale**: `product_tags` has a composite primary key over `(product_id, tag_id)` (`app/database.py:1157-1170`), so a duplicate association is impossible at the database level — but inserting one would raise rather than succeed. The membership check is what turns "already carries both" from an error into the no-op FR-010 requires. Deleting the source tag removes its remaining associations through the `ondelete='CASCADE'` already declared on the association's foreign keys.

Product counts here are small enough that iterating the relationship is the readable choice; a bulk `UPDATE product_tags SET tag_id = ...` would need an anti-join to avoid the duplicates and would be harder to follow for no measured gain.

**Alternatives considered**:

- *Bulk UPDATE with `WHERE NOT EXISTS`.* Rejected on readability grounds per Principle I; revisit only if a measurement ever says otherwise.
- *Keep both tags and record an alias.* Rejected: aliasing is exactly the machinery the spec declines for renamed categories, and the operator asked for a merge.

---

## D7 — The rename confirmation is computed in the browser from the already-rendered page

**Decision**: No preview endpoint. The categories page renders every path with its direct product count, and the new tags page renders every tag with its count; the confirmation modal sums the subtree and pre-detects a conflict from that data. The server re-validates on submit and is authoritative.

**Rationale**: FR-006 and FR-011 require the operator to be told the impact before committing. The data needed to tell them is already on the page — adding an endpoint would mean a route, a service method and a contract that exist to populate one modal. The failure mode of a stale page is a refusal the operator did not expect, not a corrupted catalogue, because the server checks again.

**Alternatives considered**:

- *`GET /api/categories/rename-preview?from=&to=`.* Rejected as above. If the categories page ever stops rendering the full tree, this decision should be revisited.
- *Skip the confirmation and offer an undo.* Rejected: undo is more machinery than the preview it replaces, and the spec asks for confirmation.

---

## D8 — The suggestion query moves to a shared service and gains a second source

**Decision**: Move `FIELD_SUGGESTION_COLUMNS` and `get_field_value_suggestions` out of `MariaDBInventoryService` (`app/mariadb_inventory_service.py:776-908`) into a new `app/services/vocabulary.py`. Widen `location`, `sub_location` and `vendor` to also read `products.location`, `products.sub_location` and `purchases.vendor`. Leave `thread_size` and `purchase_location` reading `inventory_items` alone — nothing in the catalogue records either.

**Rationale**: The method is about to have two callers on two halves of the application and to read from three tables. Leaving it on the metal stock service would make that service the owner of the catalogue's vocabulary, which is the wrong place for it to live and the wrong file to look in. The constitution designates `app/services/` for services shared between blueprints, so this is a relocation into the home the project already defines — not a new layer.

Moving rather than duplicating matters: two copies of the ranking, LIKE-escaping and case-insensitive dedup logic would drift, and the existing unit tests cover exactly those behaviours.

**Alternatives considered**:

- *Widen the method in place on `MariaDBInventoryService`.* Rejected on ownership grounds above, though it would have been the smaller diff.
- *Give the catalogue its own parallel suggestion endpoint.* Rejected outright — two endpoints reading two halves is the drift FR-016 and FR-017 exist to prevent.

---

## D9 — Multi-source results are merged and re-ranked in Python, not by a SQL UNION

**Decision**: Run the existing single-column ranked query once per source column, then merge the results in Python: re-rank by exact / starts-with / contains, alphabetize within each tier, dedupe case-insensitively, truncate to the limit.

**Rationale**: The existing query ranks with a SQL `CASE` and over-fetches to give a Python dedup pass headroom (lines 876-908) precisely because DISTINCT depends on the column's collation. Wrapping two or three of those in a UNION and re-ranking over the union is materially harder to read than doing the same merge in Python over at most a few dozen rows. The limit is clamped to 50, so the Python pass is trivially bounded.

The case-insensitive dedup is what makes this correct across sources: `Amazon` recorded on metal stock and `amazon` recorded on a purchase must offer one suggestion, not two.

**Alternatives considered**:

- *A single SQL UNION with an outer ranking CASE.* Rejected on readability; no measurement suggests the Python merge is a problem.

---

## D10 — The endpoint path stays `/api/inventory/field-suggestions/<field>`

**Decision**: Keep the existing URL and JSON shape. The catalogue forms call the same endpoint the inventory forms call.

**Rationale**: The `inventory` segment is historical rather than descriptive, but renaming it would touch a route, two templates, `field-autocomplete.js`, and the e2e tests that exercise it — for no user-visible change. Principle I and the workflow rule against gratuitous churn both point at leaving it. Keeping the shape unchanged is also what lets slice 3 add no JavaScript at all.

**Consequence to accept**: a product page issuing a request to `/api/inventory/...` reads oddly in the network tab. That is the whole cost.

---

## D11 — The catalogue forms need markup, not JavaScript

**Decision**: Wire the catalogue's location, sub-location and vendor inputs by adding the `position-relative` wrapper and the `<div id="{field}-suggestions" class="dropdown-menu ...">` that `app/templates/inventory/add.html:253-261` already uses, and by including `field-autocomplete.js`.

**Rationale**: The component's DOM-ready block (`app/static/js/field-autocomplete.js:218-240`) already binds `#location`, `#sub_location` scoped by `#location`, and `#vendor`, and skips any target whose input or dropdown is absent. The catalogue's inputs already carry exactly those ids (`_form_fields.html:61`, `purchase_add.html:31`, `capture.html:31`). Supplying the dropdown element is the entire integration.

**Verified, not assumed**: the ids match, and the auto-init guard means adding the script to a page without those inputs is harmless.

---

## D12 — Renames are form posts, not a JSON API

**Decision**: `POST /products/categories/rename` and `POST /products/tags/rename` accept form fields, flash a result, and redirect back to the listing.

**Rationale**: Both pages are server-rendered, CSRF is already wired for product forms (`{{ csrf_token() }}` appears in every one), and flash-and-redirect is the pattern the rest of the blueprint uses. A fetch-based API would need client-side re-rendering of the list for no gain. The `/api/*` surface in this blueprint exists for the things a scan or a bookmarklet calls, which these are not.

---

## D13 — `products.sub_location` mirrors the inventory column exactly

**Decision**: `VARCHAR(100) NULL`, matching `inventory_items.sub_location` (`app/database.py:60`). No backfill of existing `products.location` values.

**Rationale**: The two columns feed one shared suggestion vocabulary, so a value valid on one side must be storable on the other. Splitting existing location text into a location/sub-location pair would require guessing where the boundary is in strings like `Bin 4` — the spec rules this out explicitly, and a wrong guess is silent.

---

## D14 — Test placement follows the existing seams

**Decision**: Pure path arithmetic into `tests/unit/test_category.py`; service behaviour into `tests/unit/test_catalog_service.py`; the relocated suggestion tests into a new `tests/unit/test_vocabulary.py`; one e2e file per rename story, plus additions to `tests/e2e/test_field_autocomplete.py` and `tests/e2e/test_product_crud.py`.

**Rationale**: This is where the equivalent tests already live. The e2e rename tests need several products seeded across a category subtree, and driving the add-product form for each costs about three seconds apiece — so they need a direct seeding path. `tests/e2e/test_server.py:134` provides `add_test_data` for inventory items and `add_material_taxonomy` for the taxonomy, but nothing for products; a matching `add_test_products` helper built on `CatalogService` is needed before the rename e2e tests can follow CLAUDE.md's "seed data directly" rule.

**Waiting strategy**, per CLAUDE.md's taxonomy:

- The rename submit is a form post that navigates; `expect()` on the resulting page's content is the signal. There is nothing async to race.
- The suggestion dropdown is pattern C (render-implies-completion): `render()` appends the items only after `await fetch(...)` resolves, so `expect(dropdown.locator('.dropdown-item')).to_have_count(n)` is a complete wait and nothing further is needed.
- The negative case — "no suggestions when nothing matches" — must not be asserted with `count()` against a region nothing has established. It is asserted as `expect(dropdown).not_to_be_visible()` after a positive assertion has established that the component is live.
