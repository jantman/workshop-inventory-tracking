# Data Model: Edit Purchases and Orders

No schema change. Existing `purchases` columns, with the rules an edit enforces.

## Purchase (editable fields)

| Field | Edit rule |
|---|---|
| vendor | Required; stripped. Changing it moves the purchase to another vendor's order. |
| vendor_item_id, listing_title, listing_url, order_reference, notes | Free text; blank → NULL. |
| supplier_order_reference | Free text; blank → NULL (purchase on no order). |
| order_line_number | Whole number > 0 or blank. Unique within (vendor, supplier_order_reference) when changed. |
| order_date | Date or blank. Same-day as stored → stored value kept. |
| received_date | Only on a received purchase: date (changes it) or blank (purchase becomes outstanding). Must not precede order_date. Non-empty on an outstanding purchase is refused. |
| quantity | Whole number > 0 or blank. |
| unit_price | Decimal ≥ 0, rounded to the cent, or blank. |
| pack_size, pack_price | Both blank, or size ≥ 2 with price ≥ 0. |

Untouched: `product_id`, `vendor_order_id`, `date_added`, attachments. `last_modified` updates.
Product: never written (quantity, quantity_updated_at, stock_status unchanged).

## Order (derived)

The purchases with one `vendor` and `supplier_order_reference`. Editable as a group:

| Field | Edit rule |
|---|---|
| supplier_order_reference (order number) | Required. If changed, no other purchase of that vendor may already carry the new number. |
| order_date | Date or blank, applied to every line; must not be after any line's received_date; same-day as a line's stored value keeps that line's time. |
| order_reference | Free text or blank, applied to every line. |

All lines updated in one transaction, or none.
