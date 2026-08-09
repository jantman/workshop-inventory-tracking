# Contract: service surface

No signature changes. Two methods change what they do, and the change to the second one is a deletion. Everything a caller passes and everything it gets back is the same type it was.

---

## `CatalogService.set_stock_status(product_id, stock_status)` — now dates the flag

```python
def set_stock_status(self, product_id: int, stock_status: Optional[str]) -> Product
```

| `stock_status` argument | `product.stock_status` | `product.stock_status_updated_at` |
|---|---|---|
| `'low'` or `'out'` (any case) | that value | **now** |
| the value it already holds | unchanged | **now** — FR-002, a re-assertion is a fresh look |
| `None` or `''` | `NULL` | `NULL` — FR-003 |
| anything else | unchanged | unchanged; raises `ValidationError` |

Validation is unchanged and still happens before the session opens, so a refused value leaves both fields alone. `ItemNotFoundError` for an unknown product, as before.

**The re-assertion row is the one to test.** Assigning a string equal to the stored one produces no `UPDATE`; the timestamp write is what makes the round trip real.

---

## `CatalogService.receive_purchase(...)` — stops dating the count

```python
def receive_purchase(self, purchase_id, received_date=None, quantity=None,
                     unit_price=None, notes=None, description=None) -> Purchase
```

Signature unchanged. Inside the `if not already_received` block, on the product the purchase belongs to:

| Field | Before | After |
|---|---|---|
| `quantity` | `+= purchase.quantity`, when tracked and the purchase has a quantity | **unchanged behaviour** (FR-007) |
| `quantity_updated_at` | set to now, in the same branch | **not written** (FR-008) |
| `stock_status` | cleared, and logged | unchanged behaviour |
| `stock_status_updated_at` | — | cleared with the flag (FR-006) |

Everything outside that block — the received date, the amended quantity, price and notes, and the description correction that deliberately applies even on a repeat receive — is untouched by this feature.

**Consequences a caller can rely on:**

- Receiving never decreases the reported age of a count (SC-001).
- Receiving against a product with `quantity IS NULL` writes no count and no date (FR-009). This already held; it now holds for a second reason, since the only writer in that branch is gone.
- Receiving an already-received purchase remains a no-op for all four fields above.

---

## `CatalogService.set_quantity(product_id, quantity)` — unchanged

Listed because FR-010 depends on it and it is easy to break by accident while implementing FR-008. A number stamps `quantity_updated_at`; `None` clears the count, the date and the threshold. The `+` and `−` buttons on the product page reach this method through `PATCH /api/products/<id>/quantity` — they are not a separate path and must not become one.

## `CatalogService.create_product(...)` — unchanged

Stamps `quantity_updated_at` when created with a quantity, which is the operator entering a count. Does not accept `stock_status`, so there is no creation-time flag to date.

## `CatalogService.update_product(product_id, **fields)` — unchanged

Its `editable` set excludes `quantity`, `stock_status` and both dates, and raises `ValidationError` for anything outside it. **Do not add the new column to that set.** The dates are written by the two methods above and by nothing else; that is what makes SC-003 checkable by reading four functions.
