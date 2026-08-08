# Contract: CatalogService

**Feature**: [../spec.md](../spec.md) | **Data model**: [../data-model.md](../data-model.md)

Changed and new methods on `app/catalog_service.py`. Shapes only; behaviour rationale lives in the data model and research documents.

---

## The specification entry shape

Every method below that accepts or returns specifications uses one shape:

```python
{'name': str, 'value': str}
```

No `id`, no `display_order` on the way in — order is the list order. Extra keys are ignored rather than rejected, matching how `create_product` already treats its `identifiers` dicts.

---

## Changed: `create_product`

```python
def create_product(
    self,
    description: str,
    ...
    specifications: Optional[List[Dict[str, str]]] = None,   # was Optional[str]
    ...
) -> Product:
```

The only change is the parameter's type. The list is passed through `_validate_specifications` and the surviving entries become rows with `display_order` equal to their index, inside the same transaction as the product itself — so a refused specification means no product is created.

`None` and `[]` both mean "no specifications" and are not distinguished.

**Raises**: `ValidationError` for any of the rules in [data-model.md](../data-model.md#validation-rules), in addition to the existing description/category/quantity validation.

---

## Changed: `update_product`

```python
def update_product(self, product_id: int, **fields: Any) -> Product:
```

`'specifications'` stays in the `editable` set. Its handling moves out of the scalar `_clean` loop:

- **key absent** — the product's rows are untouched.
- **key present** — the submitted list replaces the complete set. Existing rows are deleted, validated entries inserted in list order. `[]` and `None` clear them.

Replacement rather than merge: the form always posts the complete set, and no row has an identity to diff against.

**Raises**: `ValidationError` as above. The existing `_session()` context manager rolls back the whole update, so a refusal leaves the product's other fields unchanged as well as its specifications.

---

## Changed: `search_products`

```python
def search_products(
    self,
    query: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    stock: Optional[str] = None,
    spec_name: Optional[str] = None,     # new
    spec_value: Optional[str] = None,    # new
    limit: int = 500,
) -> List[Product]:
```

| Arguments | Result |
|---|---|
| `spec_name` only | Products recording that name, any value (FR-012). |
| `spec_name` + `spec_value` | Products recording that name with a value containing the text (FR-013, FR-014). |
| `spec_value` only | Ignored. No clause added — a value filter without a name is not offered, and unusable input is dropped rather than raising, matching the other filters. |
| Combined with `query`/`category`/`tag`/`stock` | All narrow together (FR-016). |

Name matching is whole-name and case-insensitive (FR-015); value matching is contained and case-insensitive (FR-014), with LIKE wildcards in the operator's text escaped. Clauses are in [data-model.md](../data-model.md#query-shapes).

The existing `query` branch changes too: `Product.specifications.like(...)` becomes an `any()` over both specification columns, so free text still reaches everything it reached before (FR-017).

Results stay ordered by description, and `selectinload(Product.specifications)` joins the existing eager loads — the search results page and the API both read them off detached instances.

---

## Changed: every method that returns a Product

`CatalogService._session()` closes the session before the caller sees the result, so any relationship not eager-loaded raises `DetachedInstanceError` when the template or `to_dict` touches it. `Product.specifications` is now such a relationship, and it must join the `selectinload` list in each of:

| Method | Reader that would fail |
|---|---|
| `get_product` (`catalog_service.py:195-205`) | the detail page's `<dl>` and `GET /api/products/<id>` |
| `search_products` | `GET /api/products/search` → `to_dict` |
| `list_products` | any caller serializing the result |
| `create_product` / `update_product` | both return through `get_product`, so they inherit its loads |

This is easy to miss because the unit tests construct products inside a live session and would not notice. The e2e tests will, immediately and loudly.

---

## New: `list_specification_names`

```python
def list_specification_names(self, prefix: Optional[str] = None) -> List[str]:
```

Every specification name in use, for the name datalist on the forms and on the filter (FR-019). Optional `prefix` narrows to names starting with it, case-insensitively.

Deduplicated **case-insensitively in Python** — `Voltage` and `voltage` collapse to one, first spelling encountered in sort order winning — because `SELECT DISTINCT` folds under the deployed MariaDB collation and does not under SQLite. Sorted case-insensitively.

Returns `[]` when nothing is recorded. Sits beside `list_tags` and `list_categories` and behaves like them.

---

## New: `list_specification_values`

```python
def list_specification_values(
    self, name: str, prefix: Optional[str] = None
) -> List[str]:
```

Every value recorded under one specification name, for that row's value datalist (FR-020). `name` is matched whole and case-insensitively, the same way the filter matches it. Optional `prefix` narrows the values.

Same Python-side case-insensitive dedup and sort. Returns `[]` for a blank or unrecorded name — an unknown name is an ordinary state, not an error.

---

## New: `_validate_specifications`

```python
def _validate_specifications(
    self, entries: Optional[List[Dict[str, str]]]
) -> List[Dict[str, str]]:
```

Private, called by both `create_product` and `update_product` so there is one definition of what a valid specification list is. Returns the surviving entries, trimmed, in order; the caller assigns `display_order` from the index.

Rules and their requirement references are tabulated in [data-model.md](../data-model.md#validation-rules). The two worth restating here:

- A fully blank entry is dropped, not rejected — an untouched row on the form is not an error (FR-009).
- Duplicate detection compares `name.strip().lower()` in Python. It never issues a query, and it never lets the database decide, because the deployed collation also folds accents and would call `Volt` and `Vôlt` the same name when FR-004 does not.

**Raises**: `ValidationError` with `field` set to the offending entry's name (or its value, when the name is what is missing).
