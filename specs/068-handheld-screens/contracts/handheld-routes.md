# Contract: Handheld routes (`handheld` blueprint, prefix `/h`)

Every route renders a template extending `handheld/base.html`. All writes go through existing
APIs or existing service calls; the "Writes via" column names them. No route is exempted
from CSRF. Form POSTs carry `csrf_token`, and `fetch` calls go through `csrfFetch`, or the
hidden `csrf_token` input that `move-manager.js` reads.

| Endpoint | URL | Method | Template | Reads | Writes via | Story |
|---|---|---|---|---|---|---|
| `handheld.landing` | `/h/` | GET | `landing.html` | none | none | US1 |
| `handheld.item` | `/h/item/<ja_id>` | GET | `item.html` | `get_canonical_item` | client: `POST /api/labels/print`; `POST/GET/DELETE /api/items/<ja_id>/photos`, `/api/photos/<id>` | US4 |
| `handheld.product` | `/h/product/<int:product_id>` | GET | `product.html` | `_product_or_404`, `get_purchase_history`, `get_product_attachments` | client: `PATCH /api/products/<id>/quantity`, `PATCH /api/products/<id>/stock-status`, `POST /api/products/<id>/label`, `POST /api/products/<id>/attachments`, `DELETE /api/attachments/<id>` | US2 |
| `handheld.shorten` | `/h/shorten[?ja_id=JA…]` | GET | `shorten.html` | `resolve_handoff` | none | US5 |
| `handheld.shorten` | `/h/shorten` | POST | redirect to `handheld.shorten` | none | `handle_shorten_post(form, 'handheld.shorten')`, the same code as `POST /inventory/shorten` | US5 |
| `handheld.move` | `/h/move?kind=items[&ja_id=…]` | GET | `move.html` | `resolve_handoff` | client: `GET /api/items/<ja_id>`, `POST /api/inventory/batch-move` | US3 |
| `handheld.move` | `/h/move?kind=products[&code=WIT…]` | GET | `move.html` | `resolve_product_handoff` | client: `GET /api/products/by-code/<code>`, `POST /api/products/batch-move` | US3 |
| `handheld.receive` | `/h/receive/<int:purchase_id>[?quantity=Q]` | GET | `receive.html` | `get_purchase`, `_product_or_404` | none | US6 |
| `handheld.receive` | `/h/receive/<int:purchase_id>` | POST | success: redirect to `handheld.product`; `ValidationError`: re-render `receive.html` | none | `_receive_purchase_from_form()` calling `service.receive_purchase(...)` | US6 |
| `handheld.receive_choose` | `/h/receive/choose?scan=…` | GET | `receive_choose.html` | `_receive_choice(scan)` | none | US6 |
| `handheld.orders` | `/h/orders` | GET | `orders.html` | `find_outstanding_purchases`, grouped (data-model.md) | none | US7 |
| `handheld.order` | `/h/orders/<vendor>/<order_number>[?highlight=…]` | GET | `order.html` | `find_order_lines_for` | none | US7 |
| `handheld.order_receive` | `/h/orders/<vendor>/<order_number>/receive` | POST | redirect to `handheld.order` | none | `_flash_bulk_receipt(lambda: service.receive_order_lines(vendor, order_number, form.getlist('purchase_id'), received_date=form.get('received_date')))` | US7 |

## Error behavior

- Unknown product or purchase: the same `ItemNotFoundError` / 404 handling as the desktop
  routes, through the centralized handlers.
- Unknown or inactive JA ID on `/h/item/…`: **200**, rendering the item template in its
  `missing` or `inactive` state. Each states the problem plainly and links to
  `/inventory/edit/<ja_id>`, the desktop page (US4 scenario 6).
- `/h/move` with a missing or unknown `kind`: 404.
- `/h/orders/<vendor>/<order>` with no lines: 200, "not captured" plus a Home link.

## Links between screens

| From | Control | To |
|---|---|---|
| any handheld screen | Home (header) | `/h/` (FR-005) |
| landing | Move items, Move products, Shorten, Orders | `/h/move?kind=items`, `/h/move?kind=products`, `/h/shorten`, `/h/orders` |
| item | Shorten / Move | `/h/shorten?ja_id=<ja>`, `/h/move?kind=items&ja_id=<ja>` (FR-020) |
| item (missing or inactive) | Open desktop page | `/inventory/edit/<ja>` |
| product | Move | `/h/move?kind=products&code=<internal_code>` (FR-020) |
| product | Receive (per outstanding purchase) | `/h/receive/<purchase_id>` (US6 scenario 5) |
| product | Order (per distinct outstanding order) | `/h/orders/<vendor>/<order>` (FR-023b) |
| receive-choice | a candidate | `/h/receive/<purchase_id>` |
| orders | an order | `/h/orders/<vendor>/<order>` |

## Changes to existing desktop routes (no behavior change)

| Route | Change |
|---|---|
| `POST /inventory/shorten` (`main.inventory_shorten`) | Its body moves to `handle_shorten_post(form_data, 'main.inventory_shorten')`. Same validation, audit log entries, flashes and redirects. |
| `POST /purchases/<id>/receive` (`product.purchase_receive`) | The `service.receive_purchase(...)` call moves to `_receive_purchase_from_form(service, purchase_id, request.form)`. Same arguments. |
| `GET /products/purchases/receive-choice` | The candidates and fallback-product lookup move to `_receive_choice(scan)`. |
| `GET /products/<id>` (`product.product_detail`) | `received_total` comes from `_received_total(purchases)`. The template includes `_stock_card.html` and `_label_modal.html`. |
| `POST /api/scan` | See [scan-api.md](scan-api.md). |
