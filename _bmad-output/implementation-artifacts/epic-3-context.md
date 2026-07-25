# Epic 3 Context: Taxonomy & Tagging

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic lets the operator classify Products without designing a taxonomy up front. Categories are a materialized-path tree of arbitrary depth (e.g. `electronics/power/dc-dc-converters`) stored as a single canonical string on the Product; the tree ships empty and accretes purely from use, with new paths created inline during product entry via autocomplete-with-create. Tags are free-form labels that cut across the category tree for retrieval of sets a hierarchy can't express. Renaming a category segment carries its descendants and every assigned Product with it, so reorganizing never strands records. The canonical path form and the shared normalization/prefix-match helper introduced here are the substrate Epic 8's faceted filtering later reuses.

## Stories

- Story 3.1: Materialized-path categories with inline create
- Story 3.2: Category rename with descendants
- Story 3.3: Free-form tags

## Requirements & Constraints

- A Product carries at most one Category, expressed as a materialized path of arbitrary depth. Category assignment is optional — the catalog must stay fully usable with no taxonomy at all.
- Category paths are normalized to a canonical form: lowercase, `/`-separated, no leading or trailing slash. All storage, lookup, and comparison use the canonical form.
- Typing a never-before-seen path during product entry creates and assigns it without leaving the form; the path is then offered by autocomplete on subsequent entry. No taxonomy is pre-populated — a fresh install offers nothing until the operator creates something.
- Renaming a path segment must update all descendant paths and every Product assigned to them, atomically. A rename whose result collides with an existing sibling path is rejected with a clear message rather than silently merging the two branches.
- A Product carries zero or more free-form Tags, independent of Category. A tag is unique per Product (no duplicates on the same record). Filtering by a tag returns exactly the tagged Products regardless of their categories.
- Prefix filtering on a category path must match on segment boundaries only — a filter on `thermal/heat` must not match `thermal/heatgun-parts`.
- The normalization helper is a pure function with exhaustive unit tests; category/tag work adds no new datastore and no new service.

## Technical Decisions

- **Pure util (AD-4).** `app/utils/category.py` holds `normalize_category_path()` as a module-level pure function with no Flask or DB imports, following the existing `location_validator.py` pattern. It is the single source of truth for canonical form and for building the segment-boundary prefix predicate (`path = X OR path LIKE 'X/%'`). Both this epic and Epic 8's category facet call it; routes and templates never re-derive path logic.
- **Storage shape.** Category is the `products.category_path` materialized-path string — no separate node table is required by the architecture. Tags live in a `product_tags` table (`product_id`, `tag`) with a uniqueness constraint on the pair. Whether rename-with-descendants warrants a helper index or a `categories` table is explicitly left as an implementation decision for this epic, not a cross-epic invariant — a bulk path-prefix update over `products` is within the design envelope.
- **Layering (AD-1, AD-2).** ORM classes live on the shared `Base` in `app/database.py`; enums/value objects in `app/models.py`; all mutation and query go through `mariadb_catalog_service.py`. No ORM or SQL in routes; routes build the standard `{success, …}` envelope and surface rejections (collision on rename, duplicate tag) as domain errors, never raw integrity errors.
- **Autocomplete reuse (AD-14).** The category and tag inputs use the existing field-autocomplete mechanism, extended with an autocomplete-*with-create* variant in `app/static/js/field-autocomplete.js`. The existing field-suggestions source query/whitelist is extended in place — do not fork it. This mirrors the established thread-size / vendor / location suggestion pattern.
- **Migrations (AD-14).** Any schema change is an Alembic migration chained from the current HEAD (via `manage.py db`, never `create_all`). Existing metal-stock tables and behavior stay untouched.

## UX & Interaction Patterns

- There is no separate UX design contract; the UI is the existing responsive Bootstrap 5.3.2 codebase and must stay usable from 360 px up.
- Category and tag entry happen inline on the product create/edit form — the operator never leaves the form to define a taxonomy term first. Autocomplete offers existing values while still accepting a novel one as a create.
- Rename is an explicit operation with a confirmable outcome; a colliding rename surfaces a message explaining the conflict rather than failing silently or merging.

## Cross-Story Dependencies

- Builds on Epic 1: the Product entity, its `category_path` column, and the catalog service/create-edit forms already exist; this epic gives those fields real behavior.
- Story 3.1 establishes the canonical form and normalization helper that Story 3.2 (rename/collision detection) depends on.
- Epic 8 consumes this epic's output directly: faceted filtering by category path prefix and by tag reuses `normalize_category_path()` and the segment-boundary predicate, and tag/category text feeds the single shared search entrypoint.
- The category-suggestion field of the no-op enrichment interface (Epic 7) targets this same canonical path form.
