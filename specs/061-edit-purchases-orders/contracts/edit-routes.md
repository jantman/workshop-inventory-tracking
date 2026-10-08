# Contract: Edit routes

## `GET /purchases/<purchase_id>/edit[?return_to=order|product]`

Renders `product/purchase_edit.html`, every field pre-filled. An unknown id is reported "not found" through the app-wide handler (flash + redirect), as `purchase_delete` does.

## `POST /purchases/<purchase_id>/edit`

Form fields: `vendor`, `vendor_item_id`, `listing_title`, `listing_url`, `order_date`,
`received_date` (sent only when the purchase is received), `quantity`, `unit_price`,
`pack_size`, `pack_price`, `order_reference`, `supplier_order_reference`,
`order_line_number`, `notes`, `return_to`, `csrf_token`.

- Success → flash "Purchase updated." (success) and 302 to the order page
  (`return_to=order` and the saved purchase has an order number) or the product page.
- `ValidationError` → 200, form re-rendered with submitted values, flash names the problem;
  nothing written.
- Purchase gone → reported "not found" the same way.

## `GET /products/orders/<vendor>/<order_number>/edit`

Renders `product/order_edit.html` with the order number, order date and customer reference
pre-filled (and a note where lines disagree). An order with no lines → reported the same way.

## `POST /products/orders/<vendor>/<order_number>/edit`

Form fields: `order_number`, `order_date`, `order_reference`, `csrf_token`.

- Success → flash "Updated N line(s) of the order." and 302 to
  `/products/orders/<vendor>/<new order number>`.
- `ValidationError` → 200, form re-rendered with submitted values; nothing written.
- No lines → reported the same way.

## Service

```python
CatalogService.update_purchase(purchase_id: int, **fields) -> Optional[Purchase]
    # None when the purchase does not exist; ValidationError on any bad field.
CatalogService.update_order(vendor_name: str, order_number: str, new_order_number: Any,
                            order_date: Any, order_reference: Any) -> int
    # lines updated; 0 when the order has no lines; ValidationError otherwise.
```

## Entry points

- `product/detail.html` purchase history: `.edit-purchase-btn` → `/purchases/<id>/edit`.
- `product/order.html` each line: `.edit-purchase-btn` → `/purchases/<id>/edit?return_to=order`;
  page action `#edit-order-btn` → the order edit route (only when the order has lines).
