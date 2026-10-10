# Contract: Outstanding Products Page

## Page: `GET /products/outstanding`

Title and heading: **Outstanding Products**. It is linked from the Products menu
(`a.dropdown-item[href="/products/outstanding"]`).

When nothing is outstanding: `#nothing-outstanding` (an info alert), and none of the
elements below.

Otherwise:

- `#outstanding-summary`: "N line(s) outstanding across M order(s)." Lines with no order
  are not counted as an order.
- The toolbar from the `order_bulk_toolbar(action)` macro. Its ids are identical to 060's:
  `#order-bulk-toolbar`, `#order-print-labels-btn`, `#order-selected-count`,
  `form#order-receive-form[action=/products/outstanding/receive]` with `csrf_token`,
  `#bulk-received-date[name=received_date]` and `#order-receive-btn`.
- `table#order-lines` with `#order-select-all` in the header. Each outstanding purchase is
  one `tr.order-line.outstanding-line[data-purchase-id]` with these columns:
  - a checkbox (only when the purchase has a product):
    `input.order-line-checkbox[name=purchase_id][form=order-receive-form]`, carrying
    `value=<purchase id>`, `data-product-id` and `data-product-label`
  - Order: `a.order-link` to `/products/orders/<vendor>/<order_number>`, or
    `span.no-order` "no order"
  - Vendor
  - Ordered: the order date `%-d %b %Y`, or "—"
  - Part: `vendor_item_id`, or "—"
  - Product: a link to the product page, or "product deleted"
  - Qty: the quantity, or "—"
  - Receive: `a.receive-line` to `/purchases/<id>/receive`
- The label dialog: `bulk_label_modal('orderBulkLabelPrintingModal', 'order-bulk', 'product', 'products')`
- Scripts: `label-count.js`, `bulk-label-print.js`, `order-bulk-actions.js`

Row order: lines with an order number first, by order date ascending (undated orders
after dated ones), then by vendor, order number and purchase id. Lines with no order
come last.

## Action: `POST /products/outstanding/receive`

Form fields: `purchase_id` (repeated) and `received_date` (`YYYY-MM-DD`, or blank).

- Always redirects (302) to `GET /products/outstanding`.
- Flash messages are worded exactly as on the order page (060):
  - `success`: `Received N line(s).`, with ` M already received, skipped.` appended when
    M > 0
  - `info`: `Nothing to receive: the ticked line(s) were already received.`
  - `error`: `Nothing was received: <reason>`. Nothing is changed. This happens when no
    id is posted, an id does not exist, the date is unreadable, or the date is before any
    ticked outstanding line's order date.

## Service

- `CatalogService.find_outstanding_purchases() -> List[Purchase]`: purchases with
  `received_date IS NULL`, products eager-loaded, in the row order above.
- `CatalogService.receive_purchases(purchase_ids, received_date=None) -> Tuple[int, int]`:
  returns `(received, skipped)`. It raises `ValidationError`, with nothing persisted, under
  the same conditions as the `error` flash above. Its effects are exactly those of
  `receive_order_lines`.
- `CatalogService.receive_order_lines(...)`: signature, behaviour and messages are
  unchanged.
