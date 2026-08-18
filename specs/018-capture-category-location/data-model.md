# Phase 1 Data Model: Category and Location on the Capture Confirmation Page

## Schema changes

**None.** No table is added, no column is added, altered or dropped, and there is no Alembic
revision in this feature. This section exists to record that the check was made, not to
describe work.

## Entities touched

### Product (`app/database.py`, table `products`)

Three existing columns become writable from a second place. Nothing about them changes.

| Column | Type | Null | Written by, before this feature | Written by, after |
|---|---|---|---|---|
| `category_path` | `String(512)`, indexed | yes | `create_product`, `update_product`, the category rename/merge paths | + `capture_order` |
| `location` | `String(100)` | yes | `create_product`, `update_product` | + `capture_order` |
| `sub_location` | `String(100)` | yes | `create_product`, `update_product` | + `capture_order` |

`NULL` on any of the three means "not stated" and is an ordinary state (FR-003). No default
is introduced; there is no `Uncategorized` sentinel value and must not be one.

### Purchase (`app/database.py`, table `purchases`)

**Unchanged.** FR-012: filing is a property of the thing, not of the order that brought it.
`capture_order` still calls `record_purchase` with exactly the arguments it does today.

### InventoryItem (`app/database.py`, table `inventory_items`)

**Read-only, and only indirectly.** `VocabularyService` reads `inventory_items.location` and
`inventory_items.sub_location` to build the suggestion lists this feature's fields consume
(FR-008). Nothing in this feature writes to `inventory_items`, so Constitution Principle VI's
lifecycle and history invariants are not in play.

FR-007's symmetry is a schema fact rather than a rule to enforce: `products.sub_location` and
`inventory_items.sub_location` are both `String(100)`, and any change to one without the other
would break it.

## Validation rules

Carried over verbatim from the product form. This feature adds no rule and relaxes none.

| Field | Rule | Enforced by | On failure |
|---|---|---|---|
| `category_path` | Normalized to canonical form: segments split on `/`, stripped, lowercased, empties dropped, rejoined | `category_utils.canonical` | — (normalization, not rejection) |
| `category_path` | Canonical length ≤ 512 | `CatalogService._validate_category_path` | `ValidationError`; the capture form re-renders with the value as typed (FR-005 — rejection, never truncation) |
| `category_path` | Blank, whitespace, or separators only → `None` | `category_utils.canonical` | — (that is "uncategorized") |
| `location` | Stripped; blank → `None`; ≤ 100 chars by column width | `_clean` | — |
| `sub_location` | Stripped; blank → `None`; ≤ 100 chars by column width | `_clean` | — |
| all three | Optional, independently. None requires any other | — | — (FR-003) |

A sub-location with no location is accepted, because the catalog accepts one today and this
page does not invent a constraint the rest of the app does not have.

## Write semantics

The one behaviour worth stating precisely, because the two paths differ (FR-009/FR-010).

### Path A — the capture creates a product

All three values are passed to `create_product` unconditionally. `None` stores `NULL`, which
is "uncategorized/unlocated" and is not an error.

```
create_product(…, category_path=<canonical or None>,
                  location=<cleaned or None>,
                  sub_location=<cleaned or None>)
```

### Path B — the capture attaches to a product that already exists

Each field is added to the `update_product` call **only if the operator stated it**. A field
left blank contributes no key, and `update_product` touches only the keys it is given.

```
changes = {}
if wording is not None and wording != product.description:
    changes['description'] = wording          # unchanged, existing behaviour
if canonical(category_path) is not None:
    changes['category_path'] = category_path
if _clean(location) is not None:
    changes['location'] = location
if _clean(sub_location) is not None:
    changes['sub_location'] = sub_location
if changes:
    update_product(product.id, **changes)
```

| Existing value | Operator states | Result |
|---|---|---|
| `NULL` | `shelf a` | `shelf a` — the product is filed |
| `shelf b` | `shelf a` | `shelf a` — re-filed (FR-009: the operator is holding the thing) |
| `shelf b` | blank | `shelf b` — untouched (FR-010: blank is "I am not saying") |
| `NULL` | blank | `NULL` |

**Why presence and not value**: `_clean('')` and `canonical('')` both return `None`, and
`update_product` writes `None` as `NULL`. Passing the key unconditionally would erase an
existing product's filing on every capture that left the field alone. See
[research.md](./research.md) §3.

**Why the category test is `canonical(...)` and not `_clean(...)`**: `_clean('///')` returns
`'///'`, which reads as "stated", but `canonical('///')` is `None` — so the write would set
`NULL` and clear the column. The two normalizers must be matched to their own fields.

## Ordering within `capture_order`

Unchanged except for one insertion. The contract that a refused capture writes nothing is
preserved: the category path is validated in the block that already validates price and
quantity, before either question is raised.

```
1. validate vendor, dates, price, quantity      ← + validate/canonicalize category_path
2. work out the duplicate and recycled-identifier questions
3. raise CaptureDecisionRequired if either is open   (nothing written)
4. create_product  (Path A)  or  update_product  (Path B)
5. _apply_listing — specification rows and description merge (untouched)
6. record_purchase (untouched)
```
