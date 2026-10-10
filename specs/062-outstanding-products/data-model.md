# Data Model: Outstanding Products Page

No schema change. Nothing is stored. The page is computed from existing rows each time it
loads.

## Purchase (existing, `purchases`)

Fields this feature reads:

| Field | Use |
|---|---|
| `id` | checkbox value; receive target |
| `product_id`, `product` | row's product (link, label); no product means no checkbox |
| `vendor` | shown; part of the order link |
| `supplier_order_reference` | order number; NULL or blank means "no order" |
| `order_date` | shown; sort key; floor for the received date |
| `vendor_item_id` | vendor part number, shown |
| `quantity` | ordered quantity; what a receipt adds to a tracked count |
| `received_date` | NULL means outstanding (listed). Set by a receipt. |

Fields this feature writes, only through `_apply_receipt`: `received_date`. On the product:
`quantity` (+= purchase quantity, if tracked and the purchase has a quantity), and
`stock_status` / `stock_status_updated_at` (cleared). `quantity_updated_at` is never
touched.

## State transition

`outstanding (received_date NULL)` → `received (received_date = chosen date)`. This happens
only when the date is not before `order_date`, and for the whole batch or for none of it.
An already-received line stays as it is and counts as skipped.
