# Phase 1 — Data model

**There is no schema change in this feature.** No table, column, index or constraint is added,
altered or dropped, so no Alembic revision ships with it. What follows describes the shapes
that do change: one new module of constants, and the entry shape the browse page reads.

## Unchanged persistent state

| Entity | Relevance | Change |
|---|---|---|
| `Product.category_path` | `String(512)`, nullable, indexed. The materialized path, canonical per `app/utils/category.py`. `NULL` means uncategorized. | **None.** Still the only place a category exists as data. |
| `ProductSpecification` | `name`/`value`/`display_order` on the product. | **None.** |
| `Tag`, `ProductTag` | Cross-cutting axes, including the new `security` tag from the record. | **None.** A tag is created by typing it, as before. |

The taxonomy adds **no** persistence. A branch listed in the reference data and occupied by no
product has no row anywhere, which is what keeps FR-016's prohibition on a categories table
and on placeholder products satisfied rather than worked around.

## New: `app/utils/catalog_taxonomy.py`

A pure module — standard library only, no Flask, no database, no I/O — matching the existing
`app/utils/category.py` in kind.

| Name | Type | Content | Invariants |
|---|---|---|---|
| `CATEGORY_PATHS` | `tuple[str, ...]` | The 142 branches of `docs/category-taxonomy.md`: roots, intermediate parents and leaves. | Every element equals `category.canonical(element)` — already lowercase, `/`-joined, no blank segments. At most 3 segments. No element exceeds 512 characters. Every non-root element's parent is also present. No duplicates. Sorted. |
| `SPECIFICATION_KEYS` | `tuple[str, ...]` | The distinct keys named in the record's specification-key registry. | Non-empty, trimmed, no duplicates under case folding, at most 100 characters (the column width). Sorted. |

Both are derived from `docs/category-taxonomy.md`, which stays the authority. The unit suite
enforces the derivation rather than a build step regenerating it (research D5).

## Changed shape: `CatalogService.category_tree()` entries

Today each entry is `{path, depth, name, count}`, one per **distinct in-use path**. After this
change entries come from the union of in-use paths and `CATEGORY_PATHS`, and carry one more
field:

| Field | Type | Meaning | Change |
|---|---|---|---|
| `path` | `str` | Canonical category path. | — |
| `depth` | `int` | Number of segments, 1–3. | — |
| `name` | `str` | Last segment. | — |
| `count` | `int` | Products filed **directly** in this path. | Now `0` for a branch on offer that nobody occupies. Previously an entry could not exist with a count of 0. |
| `in_taxonomy` | `bool` | Whether `path` is in `CATEGORY_PATHS`. | **New.** |

The four states an entry can be in, and what each means:

| `in_taxonomy` | `count` | Meaning |
|---|---|---|
| `true` | `> 0` | A branch of the record, in use. The ordinary case. |
| `true` | `0` | A branch of the record, on offer, nothing filed there yet. Renamed by editing the record, not through the UI — `rename_category` refuses when no product carries the path. |
| `false` | `> 0` | A path somebody typed that the record does not name. Legitimate (FR-015), and the visible signal for the drift FR-019 is about. |
| `false` | `0` | Cannot occur. An entry exists because the record names it or a product carries it. |

## Unchanged shapes

`list_categories()` and `list_specification_names()` keep returning `list[str]`, sorted. Only
their **content** widens — the union adds names that no row yet carries. No caller has to
change to accommodate a new field.
