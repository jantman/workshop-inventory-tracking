# Data Model: Handheld Screens

**This feature adds no tables, columns, migrations or stored state.** Every handheld screen
reads and writes through existing service methods (spec FR-024; constitution V and VI).

What follows is the view model each screen renders: the template context the route builds,
and where each value comes from. "Same as desktop" means the same service call the matching
desktop route makes.

## Shared (every handheld template)

| Name | Source | Use |
|---|---|---|
| `title` | route | `<title>` |
| `scan_input_id` | template block | Which input `handheld.js` focuses and wires to the keyboard button: `handheld-scan-input`, or `barcode-input` (Move) or `source-ja-id` (Shorten). |
| flashed messages | `base.html` | Confirmations after a POST redirect, and `_receive_url`'s "already received" flash. |

## Landing: `handheld/landing.html`

No data. A scan entry and four buttons: Move items, Move products, Shorten, Orders (FR-004).

## Item: `handheld/item.html`

| Name | Source |
|---|---|
| `ja_id` | URL |
| `item` | `InventoryService.get_canonical_item(ja_id)`, as on the desktop edit page (`app/main/routes.py:672`). `None` gives the not-found state. |
| `state` | `'missing'` if `item is None`, `'inactive'` if `not item.active`, else `'active'` (US4 scenario 6). |

Fields shown (FR-010): `item.ja_id`, `item.item_type`, `item.shape`, `item.material`, the
non-empty `item.dimensions` (`width`, `thickness`, `wall_thickness`, `length`), `item.location`
and `item.sub_location`. Photos are loaded client-side by `PhotoManager` from
`GET /api/items/<ja_id>/photos`.

## Product: `handheld/product.html`

| Name | Source |
|---|---|
| `product` | `_product_or_404(service, product_id)` (404 as on desktop) |
| `purchases` | `service.get_purchase_history(product_id)` |
| `received_total` | `_received_total(purchases)`, extracted from `product_detail`, so both routes share it. It is needed by `_stock_card.html`. |
| `attachments` | `PhotoService.get_product_attachments(product_id)`, as `.to_dict()`, same as desktop |
| `outstanding` | `[p for p in purchases if p.is_outstanding]` |
| `outstanding_orders` | distinct `(p.vendor, p.supplier_order_reference)` over `outstanding` where the reference is non-blank, in first-seen order (FR-023b) |

Fields shown first (FR-014): `description`, `location`, `sub_location`, then the Stock card,
which shows `quantity`, `quantity_age`, `stock_status` and `stock_status_age`.

## Shorten: `handheld/shorten.html`

| Name | Source |
|---|---|
| `preselected_ja_id` | `resolve_handoff(request.args.get('ja_id'), inventory_service).first_accepted`, same as desktop |
| `rejected_items` | same hand-off |

The item itself is loaded client-side by `inventory-shorten.js` from `GET /api/items/<ja_id>`.

## Move: `handheld/move.html`

| Name | Source |
|---|---|
| `kind` | `request.args['kind']`: `'items'` or `'products'`. Anything else is a 404. |
| `preselected_items`, `rejected_items` | `resolve_handoff(ja_id)` for items, `resolve_product_handoff(code)` for products, same as desktop |
| wording | `noun`, `nouns`, `id_label`, the same strings the desktop wrappers pass to the move macro |

The queue is client state in `MoveManager`, unchanged.

## Receive: `handheld/receive.html`

| Name | Source |
|---|---|
| `purchase` | `service.get_purchase(purchase_id)`. Missing raises `ItemNotFoundError`, as on desktop. |
| `product` | `_product_or_404(service, purchase.product_id)` |
| `scanned_quantity` | `request.args.get('quantity', '')` on GET, the submitted value after a refusal |
| `form_data` | `request.form` after a refusal, else `None` |

Visible: product description, ordered quantity, pack note when `purchase.pack_size` is set,
`quantity`, and `counted` (only when `product.quantity is not None`, as on desktop). Hidden,
carrying the desktop defaults: `description`, `unit_price`, `notes`, and a blank
`received_date`.

## Receive-choice: `handheld/receive_choose.html`

| Name | Source |
|---|---|
| `scan` | `request.args['scan']` |
| `candidates`, `product` | `_receive_choice(scan)`, extracted from `purchase_receive_choice`: `find_mcmaster_receivable`, then the vendor-scoped product fallback |

## Order list: `handheld/orders.html`

The one new derivation in this feature. It is read-only and computed in the route from an
existing service call, the same way `outstanding_products()` derives its order count
(`app/product/routes.py:1937-1940`):

```python
lines = service.find_outstanding_purchases()   # received_date IS NULL, sorted oldest order first
orders: dict[tuple[str, str], OrderSummary] = {}
for line in lines:
    reference = (line.supplier_order_reference or '').strip()
    if not reference:
        continue                      # no order screen exists; reachable from its product
    key = (line.vendor or '', reference)
    summary = orders.setdefault(key, OrderSummary(vendor=key[0], order_number=reference,
                                                  order_date=line.order_date, outstanding=0))
    summary.outstanding += 1
```

`OrderSummary` is a small local `@dataclass` in `app/handheld/routes.py` with `vendor: str`,
`order_number: str`, `order_date: datetime | None` and `outstanding: int`. Insertion order
keeps the service's sort, so the order that has waited longest comes first. An order with
nothing outstanding has no outstanding purchases, so it never appears (FR-023a).

If unit-testing it in isolation is wanted, it may live as a pure function
`group_outstanding_orders(purchases) -> list[OrderSummary]` in the same module. That is still
not a service method: it is presentation grouping.

## Order: `handheld/order.html`

| Name | Source |
|---|---|
| `vendor`, `order_number` | URL |
| `lines` | `service.find_order_lines_for(vendor, order_number)`, same as desktop |
| `highlight` | `request.args.get('highlight', '')`, matched against `line.vendor_item_id` |

Per card: `line.product.description` (or `line.listing_title` when there is no product),
`line.quantity`, `line.pack_size` and `line.order_line_number` if present, and the state.
An outstanding line gets a checkbox `name="purchase_id" value="{{ line.id }}"`. A received
line shows its received date and has no checkbox.

An empty `lines` list renders "No order <n> from <vendor> was captured" with a Home link,
never a 404. This mirrors the desktop "nothing dead-ends" rule.
