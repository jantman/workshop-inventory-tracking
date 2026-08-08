# Phase 1 Data Model: Structured Specifications

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

---

## The new table

`product_specifications` — one row per named fact about a product.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | INTEGER, PK, autoincrement | no | Surrogate. Never exposed in a URL or a form. |
| `product_id` | INTEGER, FK → `products.id` `ON DELETE CASCADE` | no | Indexed. A specification belongs to exactly one product and dies with it. |
| `name` | VARCHAR(100) | no | As the operator typed it, trimmed (FR-005). Indexed — the filter looks up by name. |
| `value` | TEXT | no | As the operator typed it, trimmed. TEXT rather than VARCHAR because FR-003 requires it to hold anything the old `products.specifications` column held, including a multi-line paragraph. |
| `display_order` | INTEGER | no | The list index at save time. Mirrors `ProductAttachment.display_order` (FR-006). |

**No `date_added`.** `ProductIdentifier` has one; this does not. Nothing displays it, nothing sorts by it, and nothing has asked when a specification was recorded. Adding a column against a future that has not arrived is what Principle I prohibits.

**No `UniqueConstraint('product_id', 'name')`.** The reasoning is long enough to live in [research.md](./research.md#why-no-unique-constraint); the summary is that under the deployed collation it would enforce something stricter than FR-004 states, under SQLite something looser, and the invariant is cosmetic rather than integrity. `CatalogService._validate_specifications` is the authority.

**Indexes**: `ix_product_specifications_product_id` (the FK, matching `product_identifiers`) and `ix_product_specifications_name` (FR-012's lookup). Nothing on `value` — FR-014 matches with a leading wildcard, which no index serves.

### ORM

```text
ProductSpecification         app/database.py, after ProductIdentifier
    product        -> relationship back to Product

Product.specifications  = relationship(
    'ProductSpecification',
    back_populates='product',
    cascade='all, delete-orphan',
    passive_deletes=True,
    order_by='ProductSpecification.display_order',
)
```

Same shape as `Product.identifiers` and `Product.attachments`, which is the point — a reader who knows one knows this.

### `to_dict`

`Product.to_dict()` replaces the string entry with a list, always present, empty when there are none (FR-011):

```json
"specifications": [
  {"name": "Voltage", "value": "12 V"},
  {"name": "Output current", "value": "3 A"}
]
```

Order is display order. No `id` — nothing addresses a specification individually, and exposing one would invite a per-row edit endpoint this feature does not have.

---

## What leaves

`products.specifications TEXT NULL` is dropped. Nothing replaces it on the `products` table.

---

## Every reader of the old field

Enumerated rather than assumed, because `Product.specifications` keeps its name while changing type. "Loud" means the change raises immediately; "silent" means it would render or store something wrong.

| Site | How it breaks | Disposition |
|---|---|---|
| `app/database.py:841` | column definition | Replaced by the relationship. |
| `app/database.py:963` | `to_dict` entry | Emits the list. |
| `app/catalog_service.py:95,142` | `create_product` kwarg, `_clean(specifications)` | **Loud** — `_clean` on a list. Rewritten to build rows. |
| `app/catalog_service.py:265` | `Product.specifications.like(pattern)` in the free-text branch | **Loud** — `AttributeError` on a relationship. Replaced by an `any()` over both columns (FR-017). |
| `app/catalog_service.py:195-205` | `get_product`'s `selectinload` list | **Loud, but only at runtime** — `DetachedInstanceError` when the detail page or `to_dict` touches the unloaded relationship. `Product.specifications` joins the eager loads there and in `search_products` and `list_products`. Unit tests would not catch this; e2e will. |
| `app/catalog_service.py:457,469,493` | `update_product` docstring, editable set, `_clean` loop | **Loud** — same as create. Moves out of the scalar loop into list replacement. |
| `app/product/routes.py:49` | `_form_product_fields` reads `form.get('specifications')` | **Silent** — would yield `None` and quietly wipe the list. Rewritten to `getlist` pairing. |
| `app/product/routes.py:783` | `/api/products` POST passes `data.get('specifications')` | Passes the list through unchanged; the service validates it. |
| `app/templates/product/_form_fields.html:34-36` | the textarea | Replaced by the row editor. |
| `app/templates/product/edit.html:19` | seeds `values['specifications']` from the product | Passes the row list to the partial. |
| `app/templates/product/detail.html:95-101` | `{% if %}` and `{{ product.specifications }}` | **Silent** — a non-empty list is truthy and would render as a Python repr. Replaced by the `<dl>`. |
| `tests/e2e/test_product_crud.py:31,38`, `test_product_search.py:13-34`, `test_wedge_scan.py:40`, `test_draft_persistence.py:26,36` | fill `#specifications`, assert on `#product-specifications` | **Loud** — the selector stops resolving. All four updated as part of this feature. |
| `tests/unit/test_catalog_service.py:50,56`, `test_product_search.py:26,33` | pass the string kwarg | **Loud.** Updated. |
| `tests/unit/test_capture.py:216` | a docstring mentioning the field | Wording only. |

Nothing outside the repository reads it: `products` is not exported (`app/export_schemas.py` and `app/export_service.py` have no reference), and `app/api_client.py` does not touch the catalogue.

---

## The migration

Revision `b1a0c0d10007`, on `down_revision = 'b1a0c0d10006'` (the current head, `add_product_sub_location`).

### Upgrade

1. Create `product_specifications` with both indexes.
2. For every product where `specifications IS NOT NULL` and the value has non-whitespace content, insert exactly one row: `name = 'Specifications'`, `value =` the column verbatim, `display_order = 0`.
3. Drop `products.specifications`.

Step 2 runs as a Python loop over `op.get_bind()` with bound parameters — see [research.md](./research.md#the-migrations-data-step) for why it is not one `INSERT … SELECT`.

**Verbatim means verbatim.** No splitting at newlines, colons or commas; no case change; no re-wrapping. The value is already whitespace-trimmed because `CatalogService._clean` trimmed it on the way in, so nothing is lost by the trim the new column also applies (FR-022).

A product with a NULL or whitespace-only paragraph gets **no** row, not an empty one (FR-023).

### Downgrade

1. Add `products.specifications TEXT NULL` back.
2. For every product with at least one specification row, ordered by `display_order`:
   - if the product has **exactly one** row and its name is `Specifications`, write the value alone — an untouched carry-across round-trips to the exact original paragraph;
   - otherwise write one `name: value` line per row, joined with newlines.
3. Drop `product_specifications`, indexes and FK first, in the order `b1a0c0d10003`'s downgrade already establishes.

Step 2 also runs in Python: `GROUP_CONCAT` with an `ORDER BY` is spelled differently on MariaDB and SQLite, and this is the wrong place to maintain two spellings.

**What the round-trip guarantees.** Upgrade → downgrade returns every untouched product's paragraph character for character (SC-002). For a product edited into named values in between, it returns a readable block containing every name and every value, which is what FR-024 requires — "no content lost", not "byte-identical". Downgrade → upgrade then collapses that block back to a single `Specifications` row; that is a real loss of *structure*, and it is accepted and stated here rather than discovered later.

---

## Validation rules

All enforced in `CatalogService._validate_specifications`, applied identically by `create_product` and `update_product`.

| Rule | Requirement | Behaviour |
|---|---|---|
| Both fields blank | FR-009 | Entry dropped silently. An unused row on the form is not an error. |
| Name blank, value present | FR-008 | `ValidationError`, naming the value it belongs to. Nothing is saved. |
| Value blank, name present | FR-008 | `ValidationError`, naming the name. Nothing is saved. |
| Surrounding whitespace | FR-005 | Trimmed from both. Interior whitespace, including newlines in a value, is untouched. |
| Name longer than 100 chars | schema | `ValidationError`. A specification name is a label, not prose. |
| Duplicate name within the submitted list | FR-004 | `ValidationError` naming the duplicate. Compared as `strip().lower()`, in Python — never in SQL. `Volt` and `Vôlt` are different names. |
| Order | FR-006 | `display_order` is the surviving list index, assigned after blank rows are dropped, so removing a row leaves no gap. |

`create_product` and `update_product` both run inside the existing `_session()` context manager, so any `ValidationError` rolls the whole save back — a refused specification leaves the product's other fields unchanged too.

**Replacement, not merge.** When `update_product` receives the `specifications` key, the submitted list becomes the product's complete set: existing rows are deleted, the new ones inserted in order. Omitting the key leaves the rows alone, matching the method's existing contract that a caller which knows about three fields cannot blank the other ten.

---

## Query shapes

| Requirement | Clause |
|---|---|
| FR-013, filter by name **and** value | `Product.specifications.any(and_(func.lower(ProductSpecification.name) == name.strip().lower(), ProductSpecification.value.like(f"%{escaped}%", escape='\\')))` |
| FR-012, filter by name alone | the same, without the value predicate |
| value supplied without a name | ignored — no clause added, matching how the existing filters treat unusable input |
| FR-017, free text | `Product.specifications.any(or_(ProductSpecification.name.like(pattern), ProductSpecification.value.like(pattern)))`, added to the existing `or_` beside description and MPN |
| FR-019, names in use | `session.query(ProductSpecification.name)`, optional `LIKE 'prefix%'`, deduped case-insensitively **in Python**, sorted case-insensitively |
| FR-020, values under a name | `session.query(ProductSpecification.value).filter(func.lower(name) == …)`, same dedup |

`func.lower()` on the name rather than `==` because SQLite's `==` is case-sensitive and FR-015 is not; the dedup runs in Python because `SELECT DISTINCT` folds under the deployed collation and does not under SQLite. Both points are argued in [research.md](./research.md#the-collation-question).

---

## Entity summary

- **ProductSpecification** — a name and a value belonging to one product, ordered among that product's others. Created and replaced only through `CatalogService`; deleted with its product. Has no independent identity in any URL, form or API payload.
- **Product** — loses `specifications` as text, gains it as an ordered collection. No other field changes.
- **Specification vocabulary** — not a table. The distinct names, and the values under each, that happen to be recorded. Read-only, derived on demand, exactly like the category and tag vocabularies beside it.
