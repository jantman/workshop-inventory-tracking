# Contract: search coverage and the code-formed address

Two changes, one line of service code and one new route. No signature changes.

---

## `CatalogService.search_products(...)` — notes join the text clause

```python
def search_products(self, query=None, category=None, tag=None, stock=None,
                    spec_name=None, spec_value=None, limit=500) -> List[Product]
```

Signature, return type, ordering (`Product.description`) and `limit` are all unchanged. One disjunct is added to the existing `or_(...)`:

| Field matched by `query` | Before | After |
|---|---|---|
| `Product.description` | ✓ | ✓ |
| `ProductSpecification.name` / `.value` | ✓ | ✓ |
| `Product.manufacturer_part_number` | ✓ | ✓ |
| `Product.manufacturer` | ✓ | ✓ |
| identifier values (subquery) | ✓ | ✓ |
| **`Product.notes`** | ✗ | **✓ (FR-010)** |

```python
Product.notes.like(pattern)   # pattern is the existing f"%{text}%"
```

### Properties that follow, and why each is structural rather than tested-into-place

- **No duplicate rows (FR-011).** A disjunct on a column of the same `Product` row cannot multiply it. Contrast the identifier clause, which is `Product.id.in_(subquery)` precisely so that a product with three matching identifiers still returns once.
- **Empty and absent notes are inert.** `NULL LIKE '%x%'` is `NULL`, which is not true. A product with no notes is never returned on the strength of the field, and never errors for lacking one.
- **Other filters still bind (FR-013).** Category, tag, stock and specification filters are separate `.filter()` calls, conjoined. A product that matched through notes is narrowed by them like any other.
- **Same matching semantics (FR-012).** `.like()` with the same `%…%` pattern as its five siblings — same substring behaviour, same collation-derived case handling, same treatment of `%` and `_` in the query. Notes get no special-casing and the other fields lose none.

**`ilike()` is wrong here** even though it looks more explicit. It would make notes the one field with semantics of its own, which is the thing FR-012 exists to prevent.

**What a test can and cannot prove.** SQLite and MariaDB *agree* about `LIKE` case-folding, so no suite in this project can distinguish `like` from `ilike` — a case-insensitivity test would pass either way and prove nothing. The property worth asserting is sameness: a query matching product A by description and product B by notes returns both, once each.

---

## `GET /products/<product_code>` — new route

```python
@bp.route('/products/<product_code>')
def product_by_code(product_code): ...
```

| Request | Response |
|---|---|
| a code carried by a product | **302** to `/products/<id>` (`url_for('product.product_detail', …)`) |
| the same code in lower or mixed case | **302** to the same place |
| a well-formed code carried by nothing | whatever an unknown record number does — see below |
| a segment that is not a well-formed code | the same |

**Correction, found during implementation.** This contract first said a missing code returns **404**. It does not, for an HTML request: `app/error_handlers.py:308` answers `ItemNotFoundError` with `jsonify(...), 404` only when `request.is_json`, and otherwise flashes a warning and redirects to the inventory list. That is already what `/products/999999` does today, so the route needs no special handling — FR-016 asks for "the catalogue's existing treatment of a missing product" and this *is* it.

The test asserts the equivalence rather than a literal status code, so the two paths cannot drift:

```python
unknown_code = client.get('/products/WITZZZZZZZZZZ')
unknown_id   = client.get('/products/999999')
assert unknown_code.status_code == unknown_id.status_code
assert unknown_code.headers['Location'] == unknown_id.headers['Location']
```

Worth noting but out of scope: that redirect lands on the *inventory* list, not the product catalogue, which is a slightly odd destination for a missing product. It is pre-existing behaviour for every product-not-found in the app, and changing it belongs to its own change rather than this one.

Handler shape — thin, per Constitution II, with no ORM query of its own:

1. `code = product_code.upper()`
2. `internal_id.is_internal_id(code)` → if not, raise `ItemNotFoundError`
3. `service.find_product_by_identifier(code, id_type=IdentifierType.INTERNAL.value)` → if `None`, raise `ItemNotFoundError`
4. `redirect(url_for('product.product_detail', product_id=product.id))`

### Redirect, not render

FR-015 asks for the same content and the same available actions as the canonical page. A redirect makes that identically true instead of a claim to verify, and avoids a second copy of `product_detail`'s assembly of purchases, photos, purchase attachments and the latest price. FR-017 makes the record number canonical; a redirect is that statement made in the address bar.

### Upper-casing

Crockford base32 omits I, L, O and U so a person can retype a scuffed label, and its alphabet is uppercase-only — so folding is injective and FR-018 is not at risk. `internal_id.is_internal_id` is **not** loosened: `witabc…` stays free text to the scanner, because changing that would move an existing classification and violate FR-008. The tolerance is local to this route.

### The route-shadowing test is part of the work

Werkzeug ranks a rule with no arguments above one with an argument on the same path shape, so these keep their own handlers:

`/products` · `/products/new` · `/products/capture` · `/products/reorder` · `/products/categories` · `/products/tags`

That is defined behaviour, not luck. But it fails silently and far from its cause if it is ever wrong, so **a test enumerating each of those paths and asserting it resolves to its own endpoint ships with this route.** It is the test that would have caught the bug.

---

## `app/templates/product/search.html` — stated coverage

The search input's placeholder currently reads:

```
description, spec, part number or identifier
```

It must name notes (FR-014). A searchable field the operator does not know is searchable buys nothing, and `docs/user-manual.md:749` makes the same list in prose — the two must agree after this change.

This is the feature's only template edit. It touches no page covered by `tests/e2e/screenshot_config.yaml`, so `nox -s screenshots_headless` is expected to leave the working tree clean; a diff under `docs/images/screenshots/` means something unintended changed.
