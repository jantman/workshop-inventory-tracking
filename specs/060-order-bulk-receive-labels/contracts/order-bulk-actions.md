# Contract: Order Page Bulk Actions

## Page: `GET /products/orders/<vendor>/<order_number>`

When the order has lines:

- `#order-bulk-toolbar` containing:
  - `#order-print-labels-btn` (disabled until a line is ticked), with `#order-selected-count`
  - `form#order-receive-form` `method=POST` `action=/products/orders/<vendor>/<order_number>/receive`
    with `csrf_token`, `input[type=date][name=received_date]#bulk-received-date` (blank =
    today), and `button#order-receive-btn` (disabled until a line is ticked)
- `#order-select-all` header checkbox (tri-state)
- per line with a product: `input.order-line-checkbox[name=purchase_id][form=order-receive-form]`
  with `value=<purchase id>`, `data-product-id`, `data-product-label`
- the label dialog from `bulk_label_modal('orderBulkLabelPrintingModal', 'order-bulk', 'product', 'products')`

When the order has no lines: none of the above.

## Action: `POST /products/orders/<vendor>/<order_number>/receive`

Form fields: `purchase_id` (repeated), `received_date` (`YYYY-MM-DD` or blank).

- Always redirects (302) to `GET /products/orders/<vendor>/<order_number>`.
- Success flash (`success`): `Received N line(s).` plus ` M already received, skipped.` when
  M > 0; when N = 0: `Nothing to receive: the ticked line(s) were already received.` (`info`).
- Refusal flash (`error`) with the validation message; **nothing is changed**:
  - no `purchase_id` posted
  - any id not on this order
  - unreadable date, or a date before any ticked outstanding line's order date

## Service: `CatalogService.receive_order_lines(vendor_name, order_number, purchase_ids, received_date=None) -> Tuple[int, int]`

Returns `(received, skipped)`. Raises `ValidationError` as above, with nothing persisted.
Each newly received line has exactly the effects of `receive_purchase(id, received_date=…)`
with no amendments and `counted=False`.

## Label printing

Each distinct `data-product-id` among ticked lines → one `POST /api/products/<id>/label`
`{label_type, label_count}` (existing endpoint, unchanged).
