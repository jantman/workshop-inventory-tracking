# Phase 1 — Interface contracts

The application's external interface is its HTTP surface. Three endpoints change **content**;
one page changes **markup**. No request shape, response shape, status code or route changes,
so no consumer has to be updated to keep working.

---

## `GET /api/categories`

Feeds the `category-suggestions` datalist on the product add/edit form
(`app/static/js/catalog-suggestions.js:26`) and the category filter on the search page.

**Request** — unchanged. Optional `prefix` query parameter narrows to a subtree.

**Response** — unchanged shape:

```json
{ "categories": ["electrical/devices/receptacles", "electronics/dev boards/arduino"] }
```

**What changes**: the list is now the union of the distinct `category_path` values in use and
`CATEGORY_PATHS`, deduplicated on the canonical path and sorted. A branch nobody occupies is
returned; a path in use that the taxonomy does not name is still returned. `prefix` filters the
union, not just the in-use half.

**Contract obligations**
- FR-012: every branch of the record is offered before any product occupies it.
- FR-013: the string returned is the record's path exactly, so selecting it and saving stores
  one path rather than two near-identical ones.
- FR-017: an in-use path absent from the taxonomy is never dropped from the response.
- FR-018: a path both offered and in use appears once.

---

## `GET /api/specification-names`

Feeds the `specification-name-suggestions` datalist on the product form
(`app/templates/product/_form_fields.html:96`) and the search page's Specification filter.

**Request and response** — unchanged.

```json
{ "specification_names": ["Drive", "Length", "Material", "Thread"] }
```

**What changes**: the union with `SPECIFICATION_KEYS`, so a key the record names is offered
before any product carries it.

**Contract obligation** — SC-010: near-duplicate keys are prevented at the point of typing,
because there is no `rename_specification` to repair them afterwards.

---

## `GET /products/categories`

The browse page.

**Request and response** — unchanged: HTML, same route, same template.

**What changes**:

1. Rows now include branches nobody occupies, shown with a count of `0`.
2. Each row carries whether the record names it (`in_taxonomy`), rendered as a marker on rows
   it does not.
3. **The Rename button renders only when the row's count is greater than zero.**
   `CatalogService.rename_category` raises `ValidationError` when no product carries the path
   (`app/catalog_service.py:2822`), so offering the control on an unoccupied branch would
   present an action that cannot succeed. An unoccupied branch is renamed by editing
   `docs/category-taxonomy.md` and `app/utils/catalog_taxonomy.py`.
4. The page's explanatory copy is rewritten. It currently asserts *"A category exists because a
   product is in it … There is nothing here to set up,"* which this feature makes false.

**Unchanged**: `POST /products/categories/rename`, its validation, its refusals and its
subtree-carrying behavior. No service code behind it is touched.

---

## Not part of this contract

- `POST /products/new`, `POST /products/<id>/edit` — a category is still free text. A path
  outside the taxonomy is accepted (FR-015) and an empty one is accepted (FR-014).
- The capture endpoints — vendor specification names are **not** rewritten automatically.
  FR-024 requires the record to state the normalization; applying it in code is a separate
  feature.
- `GET /api/tags`, `POST /products/tags/rename` — untouched. The `security` tag the record adds
  is created by typing it, like every other tag.
