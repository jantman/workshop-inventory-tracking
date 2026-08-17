# Phase 1 Data Model: A Captured Barcode Becomes a Scannable Identifier

## No schema change. No Alembic revision.

Stated first because it is the most important fact in this document, and because Principle V makes
"did you need a migration?" the first question anyone will ask. Everything this feature writes is a
row in a table that already exists, with a shape that table already enforces. If a task starts
writing `migrations/versions/*.py`, the plan has been misread.

## What gets written

### `product_identifiers` — one new row per promoted barcode

Unchanged table (`app/database.py:1123`). Promotion inserts through the existing
`CatalogService.add_identifier`, so the column values are whatever that method already produces:

| Column | Value on a promoted row | Why |
|---|---|---|
| `product_id` | The product the capture resolved to | FR-008 |
| `id_type` | `'GTIN'` | The only kind promotion creates |
| `value` | The 14-digit key from `gtin.normalize_and_validate` | FR-002. Storing the normalized key is what makes UPC-A `012345678905` and EAN-13 `0012345678905` one identifier rather than two |
| `vendor` | `''` | GTIN is not vendor-scoped; `''` rather than NULL, because SQL treats NULLs as distinct and the uniqueness rule would become a convention |
| `validation_overridden` | `False`, always | FR-004. Promotion has no override path, so this column can never be `True` on a row it created |
| `date_added` | Server default | Untouched |

The constraint that does the work is already there:

```sql
UNIQUE (id_type, value, vendor)   -- uq_identifier_type_value_vendor
```

FR-006 (another product holds it) and FR-007 (this product holds it) are both *consequences* of that
constraint plus the existing `_add_identifier` logic, not new rules to implement. See
[research.md](./research.md) §6.

### `product_specifications` — unchanged in every respect

FR-005: the barcode-named row lands as an ordinary specification row exactly as it does today,
whatever promotion decides. Promotion never deletes, moves, renames or filters one. The only change
near this table is that `merge_specifications` now *reports* which rows it added instead of counting
them; what it writes is identical.

## What gets read

- The product's identifiers, to classify each barcode-named row for the report
  (`find_product_by_identifier(key, id_type='GTIN')` — an existing method, indexed on
  `product_identifiers.value`).

Nothing else. No external request (SC-006).

## Transient objects

### `CapturedBarcode` (new, `app/models.py`)

A display-only value object, not persisted, produced by `describe_captured_barcodes` and consumed by
the route's message builder. It sits beside `CaptureAssessment`, which is the established home for
"a plain-value summary a capture hands to a page".

| Field | Type | Meaning |
|---|---|---|
| `row_name` | `str` | The specification row's name as the listing gave it (`UPC`, `EAN`, …), for the "not examined" message |
| `value` | `str` | The 14-digit key when the value is a valid barcode, otherwise the raw value as the listing gave it |
| `outcome` | `str` | One of `recorded`, `unusable`, `taken`, `not_examined` |
| `holder_id` | `Optional[int]` | Set only for `taken`: the product that holds the barcode |
| `holder_description` | `Optional[str]` | Set only for `taken`: that product's description, so the message can name it |

Everything is a plain value rather than an ORM row, for the reason `CaptureAssessment`'s docstring
already gives: a relationship that was not eagerly loaded does not survive the session, and a
display object has no business carrying that hazard.

**The four outcomes are exclusive and exhaustive**, tested in that order:

1. `gtin.normalize_and_validate(value)` returns `None` → `unusable`
2. this product holds the key → `recorded`
3. another product holds the key → `taken`
4. otherwise → `not_examined`

(4) is an inference, and the one place a reader needs a comment: a valid barcode that no product
holds can only be a row the merge dropped, because every row the merge *added* was either promoted —
so this product holds it — or collided, so another product does.

### `merge_specifications` return value (changed)

`int` → `List[Dict[str, str]]`, the validated `{'name', 'value'}` entries it appended, in the order
appended. `len()` of the new value is the old value. This is the carrier for FR-003: promotion reads
this list, so a dropped row is unreachable rather than filtered out.

## Entity relationships (unchanged)

```text
Product 1 ──── * ProductIdentifier      (GTIN row added by promotion)
        1 ──── * ProductSpecification   (the barcode-named row, always, either way)
        1 ──── * Purchase               (untouched by this feature)
```
