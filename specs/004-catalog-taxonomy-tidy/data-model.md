# Phase 1 Data Model: Keep the Catalogue Tidy

Three of the four slices change no schema at all — they add operations over data that already exists. The one schema change is a single nullable column. This document records the delta, the semantics of the two rename operations, and the shape of the derived vocabulary.

---

## Schema delta

### `products.sub_location` (new)

| Property | Value |
|---|---|
| Type | `VARCHAR(100)` |
| Nullable | Yes |
| Default | `NULL` |
| Index | None |

Mirrors `inventory_items.sub_location` (`app/database.py:60`) exactly, because the two feed one shared suggestion vocabulary and a value storable on one side must be storable on the other.

`NULL` means "no sub-location recorded", which is an ordinary state and not an error (FR-023) — the same convention `location` already follows. Every product that exists before this migration keeps `NULL`; there is no backfill and no attempt to split existing `location` text into a pair.

**Alembic revision**: `b1a0c0d10006_add_product_sub_location`, following the catalogue's existing `b1a0c0d1000N` series. `upgrade()` adds the column; `downgrade()` drops it. Both must be exercised (Principle V) — a plain nullable column add has no index or foreign key ordering to get wrong on MariaDB, which is the failure mode revision `8213852b0b94` hit.

**Threads through**: `Product` model, `Product.to_dict()`, `CatalogService.create_product()` and `update_product()`, `_form_product_fields()` in `app/product/routes.py`, `_form_fields.html`, `detail.html`.

### Everything else — unchanged

`products.category_path`, `tags`, `product_tags`, `inventory_items` and `purchases` keep their current definitions. The rename operations rewrite rows; they do not alter structure.

---

## Category rename semantics

A category has no row of its own. `products.category_path` holds a canonical materialized path (`app/utils/category.py`), so the set of categories is the distinct set of those strings, and renaming one means rewriting a prefix across a set of products.

### Selection

Given a canonical source path `S`, the affected rows are:

```
category_path = S  OR  category_path LIKE <descendant_like_pattern(S)> ESCAPE '\'
```

This is the same pair of conditions `CatalogService.list_categories()` already uses for subtree filtering, and `descendant_like_pattern()` already escapes `%`, `_` and `\` appearing inside a real category name.

### Rewrite

For each affected row, the new value replaces the leading `S` with the canonical target `T`, preserving everything from the separator onward:

| Before | Rename | After |
|---|---|---|
| `elctronics` | `elctronics` → `electronics` | `electronics` |
| `elctronics/passives` | `elctronics` → `electronics` | `electronics/passives` |
| `elctronics/passives/resistors` | `elctronics` → `electronics` | `electronics/passives/resistors` |
| `elctronics-surplus` | `elctronics` → `electronics` | *(untouched — the boundary is the separator, not the character count)* |

The last row is the property `is_descendant()` already enforces and the rename inherits: a category that merely starts with the same letters is a different category.

Renaming a deeper path works the same way. `power/dc dc` → `power/converters` rewrites only that subtree and leaves `power` and its other children alone.

### Validation, in order

Each check below refuses the whole rename by raising `ValidationError`; nothing is written until all of them pass.

| # | Condition | Refusal reason | FR |
|---|---|---|---|
| 1 | `canonical(S)` or `canonical(T)` is `None` | A rename needs a source and a target; blank is not a category. | — |
| 2 | `canonical(S) == canonical(T)` | Nothing to rename — the names differ only in case or spacing, which normalization already collapses. | Edge case |
| 3 | `is_descendant(T, S)` | The target would sit inside the category being renamed. | FR-005 |
| 4 | A product **outside** the `S` subtree has a path equal to `T` or beneath `T` | Collision: that category already exists. The message names the colliding path. | FR-004 |
| 5 | Any rewritten path exceeds `MAX_CATEGORY_PATH_LENGTH` (512) | The rename would overflow a path beneath it. Names the offending path. | FR-004 note / D4 |
| 6 | No product carries `S` | There is no such category to rename. | Edge case |

Check 4's exclusion is load-bearing: renaming `a` → `b` when `a/b` exists must succeed, because `a/b` is inside the source subtree and becomes `b/b`.

Check 3 subsumes the `S == T` case, so check 2 runs first purely to produce the clearer message.

### Result

`rename_category` returns a report the route flashes:

```
{
    'from': str,             # canonical source
    'to': str,               # canonical target
    'products': int,         # rows rewritten
    'categories': int,       # distinct paths rewritten (the renamed level plus its descendants)
}
```

### Atomicity

One `CatalogService._session()` block. Validation happens inside it, before the update. Any raise rolls the transaction back, so a refused rename leaves every product exactly as it was (FR-007, SC-005).

---

## Tag rename and merge semantics

Tags do have rows. `Tag.name` is `VARCHAR(64) NOT NULL UNIQUE`, stored lowercase-normalized, and `product_tags` is a composite-primary-key association with `ON DELETE CASCADE` on both foreign keys.

### Normalization

The target name goes through the same treatment `_attach_tag()` already applies: trim, lowercase, and reject over `MAX_TAG_LENGTH` (64). This is what makes `Surplus` and `surplus` the same tag, and therefore what makes "rename to a different case" a no-op rather than a rename.

### The two outcomes

| Target state | Outcome | What happens |
|---|---|---|
| No tag with the target name | **Rename** | `tag.name = T`. Associations are untouched — every product carrying it now carries the new name. |
| A tag with the target name exists | **Merge** | Every product of the source that does not already carry the survivor gains it; the source tag row is deleted, taking its associations with it via cascade. |

The membership check is what makes FR-010 hold. `product_tags`' composite primary key makes a duplicate association impossible at the database level, but inserting one raises rather than succeeding — so a product already carrying both tags has to be skipped, not attempted.

The result of a merge does not depend on which of the two tags was the one being renamed: one tag remains, carrying the union.

### Validation

| # | Condition | Refusal reason | FR |
|---|---|---|---|
| 1 | Source or target normalizes to empty | A tag needs a name. | — |
| 2 | Source and target normalize to the same string | Nothing to rename. | Edge case |
| 3 | Target exceeds `MAX_TAG_LENGTH` | Over-length is a rejection, not a truncation — as it already is on `_attach_tag`. | — |
| 4 | No tag with the source name exists | There is no such tag to rename. | Edge case |

### Result

```
{
    'from': str,
    'to': str,
    'merged': bool,          # True when the target already existed
    'products': int,         # products that ended up carrying the survivor because of this operation
}
```

`products` counts the products moved, which for a merge excludes those that already carried the survivor — that is the number that answers "what did this change".

### Atomicity

As for categories: one session, validation inside it, rollback on refusal (FR-012).

---

## Tag listing with counts

FR-013 needs a view of tags in use with their product counts, because near-duplicate spellings cannot be corrected until they can be seen next to each other.

`CatalogService.tag_list_with_counts()` returns, alphabetically by name:

```
[{'id': int, 'name': str, 'count': int}, ...]
```

`count` is the number of products carrying the tag. A tag with a count of zero is possible — `Tag`'s docstring already records that unused tags are not garbage-collected — and is shown, because an orphan tag is exactly the kind of debris this page exists to reveal.

This mirrors `category_tree()`, which returns path, depth, name and direct count for the categories page.

---

## The location and vendor vocabulary

Not an entity and not a table. The vocabulary is the distinct set of values already recorded, computed on demand:

| Field | Sources | Scoping |
|---|---|---|
| `location` | `inventory_items.location`, `products.location` | none |
| `sub_location` | `inventory_items.sub_location`, `products.sub_location` | optional `location=`, applied per source against that source's own location column |
| `vendor` | `inventory_items.vendor`, `purchases.vendor` | none |
| `thread_size` | `inventory_items.thread_size` | none — nothing in the catalogue records one |
| `purchase_location` | `inventory_items.purchase_location` | none — likewise |

**Properties that follow from this being derived rather than curated**:

- There is no way to add a name except by recording it on something, and no way to remove one except by removing the last thing that carries it. This mirrors how categories already behave.
- A name recorded on either half is immediately available on the other, with no publishing step (FR-017) — because the query reads the source tables directly, there is nothing to keep in sync.
- Inactive `inventory_items` history rows contribute, as they already do today. A name is not withdrawn because the item carrying it was deactivated (FR-019).
- Nothing constrains what may be entered. The suggestion list is advisory; the underlying inputs stay plain text (FR-018), and no side validates against the other's naming conventions.

**Ordering and deduplication** are unchanged from the existing single-source behaviour: with a query, exact matches first, then starts-with, then contains, alphabetized within each tier; without one, alphabetized. Deduplication is case-insensitive across sources, so `Amazon` on metal stock and `amazon` on a purchase offer one suggestion.

---

## Entity relationship summary

Nothing new is related to anything. For orientation:

```
Product ──< ProductIdentifier
   │
   ├──< Purchase            (Purchase.vendor feeds the vendor vocabulary)
   ├──< ProductAttachment
   ├──── category_path      (a string; renaming rewrites it in bulk)
   ├──── location           (feeds the location vocabulary)
   ├──── sub_location       (NEW; feeds the sub-location vocabulary)
   └──>< Tag  via product_tags   (renaming writes Tag.name; merging moves associations)

InventoryItem
   ├──── location, sub_location, vendor    (feed the same three vocabularies)
   ├──── thread_size, purchase_location    (feed their own, unchanged)
   └──── (active and inactive rows both contribute)
```
