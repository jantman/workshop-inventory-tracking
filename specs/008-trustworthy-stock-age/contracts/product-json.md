# Contract: the product JSON

`Product.to_dict()` gains one field. Purely additive: no field is renamed, removed or given a new meaning, and every existing consumer keeps working without knowing the field exists.

## The addition

```diff
   "quantity": 12,
   "quantity_updated_at": "2026-05-02T09:14:03",
   "reorder_threshold": 5,
   "stock_status": "low",
+  "stock_status_updated_at": "2026-08-09T18:22:41",
   "notes": null,
```

ISO 8601, or `null` — the same shaping as `quantity_updated_at` immediately above it, and it sits next to `stock_status` for the same reason that one sits next to `quantity`.

`null` carries two meanings, distinguished by `stock_status`:

| `stock_status` | `stock_status_updated_at` | Meaning |
|---|---|---|
| `null` | `null` | No flag |
| `"low"` / `"out"` | a timestamp | Flagged, and when |
| `"low"` / `"out"` | `null` | Flagged before this feature; the date was never recorded |

## Where it appears

Everywhere `to_dict()` already goes, with no route change:

- `GET /api/products/<id>` (via `include_related=True`)
- `PATCH /api/products/<id>/quantity`
- `PATCH /api/products/<id>/stock-status`
- and anywhere else a product is serialized, since the field is on the model method rather than on a route.

## What does not change

- **No new endpoint.** The two PATCH endpoints already accept exactly what this feature needs; the flag's date is derived from the act, never supplied by the caller. There is no way to set `stock_status_updated_at` over HTTP and there should not be — a client-supplied date for "when somebody looked" is the same lie in a different place.
- **No request body changes.** `PATCH /api/products/<id>/stock-status` still takes `{"stock_status": "low" | "out" | null}` and still 400s on a missing key or an unknown value.
- **`app/api_client.py` is untouched.** It is the standalone inventory-item client and knows nothing about products; its `__all__` surface is unaffected.
- **No JavaScript consumes the new field.** `product-stock.js` reloads the page on success and reads nothing out of the response body but `success` and `error`.
