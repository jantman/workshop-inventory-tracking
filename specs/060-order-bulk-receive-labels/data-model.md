# Data Model: Bulk Receive and Bulk Label Printing on the Order Page

No schema change.

## Purchase (order line) — existing

| Field | Use here |
|---|---|
| `id` | posted as `purchase_id` |
| `vendor`, `supplier_order_reference` | must match the order page's vendor / order number |
| `product_id` | label target; lines without one get no checkbox |
| `quantity` | ordered quantity; added to a tracked product count on receipt |
| `order_date` | received date must not be before it |
| `received_date` | `NULL` = outstanding. Set once; never overwritten by a later receipt |

### State transition

`outstanding (received_date NULL)` → `received (received_date = chosen date or now)`.
An already-received line is skipped by bulk receive (counted as skipped).

## Product — existing

On receipt of an outstanding line (via `_apply_receipt`): `quantity += purchase.quantity` if
both are non-null; `quantity_updated_at` unchanged; `stock_status` and
`stock_status_updated_at` cleared if set.

## BulkReceiptResult (return value, not stored)

`(received: int, skipped: int)` — lines newly received, and ticked lines already received.
