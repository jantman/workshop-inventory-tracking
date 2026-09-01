# Contract: Delete a Purchase

**Feature**: `specs/032-delete-purchase` | **Date**: 2026-08-31

This is a server-rendered Flask application, so its external contract is its HTTP surface
plus the service method the routes are thin over. Both are specified here.

---

## HTTP — `GET /purchases/<int:purchase_id>/delete`

Renders the confirmation. Reads nothing, writes nothing.

**Blueprint**: `product` (`app/product/routes.py`), sitting beside
`purchase_receive` at `/purchases/<int:purchase_id>/receive`.

| | |
|---|---|
| **Path param** | `purchase_id` — the purchase to delete. |
| **Query param** | `return_to` — `product` (default) or `order`. Any other value is treated as `product`. |
| **200** | `product/purchase_delete.html`. |
| **404** | `ItemNotFoundError` through the existing centralized handler, when no such purchase exists (FR-011). No new error machinery. |

**The page MUST show** (FR-003, FR-004):

- The product it belongs to, linked.
- Vendor, order date, quantity, unit price, and — when present — the supplier order
  reference and line number. Enough to tell two near-identical rows apart.
- Whether it is outstanding or received, and the received date if it has one.
- **The number of attached files that will be deleted with it.** Read via
  `PhotoService.get_purchase_attachments(purchase_id)`. Say so plainly when it is zero
  rather than omitting the line — the operator should not have to infer silence.
- **A statement that the product's counted quantity will not change** (FR-007).
- A **Delete** submit and a **Cancel** that returns where the operator came from, changing
  nothing (FR-002).

`unit_price` is rendered from its `Decimal`. It is never passed through `float`
(Constitution III).

---

## HTTP — `POST /purchases/<int:purchase_id>/delete`

Performs the deletion.

| | |
|---|---|
| **Form field** | `csrf_token` — required; CSRF stays enabled (tests set `WTF_CSRF_ENABLED = False`). |
| **Form field** | `return_to` — `product` (default) or `order`. |
| **302 → product** | `product.product_detail(product_id=...)` when `return_to` is `product`, unrecognized, or absent. |
| **302 → order** | `product.order_detail(vendor=..., order_number=...)` when `return_to` is `order` **and** the deleted purchase carried a `supplier_order_reference`. Both values come from the `PurchaseDeletion` summary, never from the request (research R3). |
| **302 → product (fallback)** | `return_to=order` on a purchase with no supplier order reference. Not an error — there is no order to go back to. |
| **404** | `ItemNotFoundError` when the purchase is already gone. Changes nothing (FR-011). |

**Flash on success** (FR-008): names the vendor, the order date and the quantity, and
states how many attached files went with it. Category `success`, matching
`purchase_receive`'s `flash('Received.', 'success')`.

**Atomicity**: the purchase, its attachment rows and any newly-unreferenced photos are
removed in one transaction, or none of them are (FR-012).

---

## Service — `CatalogService.delete_purchase`

```python
def delete_purchase(self, purchase_id: int) -> Optional[PurchaseDeletion]:
```

**Returns** a `PurchaseDeletion` describing what was removed, or `None` when no such
purchase existed. Returning `None` rather than raising matches `get_purchase` and
`remove_identifier`, which leave the not-found decision to the route.

**Guarantees**:

1. The `purchases` row is gone.
2. Every `product_attachments` row owned by it is gone.
3. Every `photos` row that those attachments were the last reference to is gone; a photo
   still referenced by another attachment or by an `ItemPhotoAssociation` survives
   (FR-006).
4. Nothing else is written. Specifically: the product's `quantity`,
   `quantity_updated_at`, `stock_status`, `stock_status_updated_at` and `description` are
   untouched (FR-007), the product itself survives (FR-005), its other purchases survive,
   and no `inventory_items` row is read or written (Constitution VI).
5. All of 1–3 commit together or not at all (FR-012).
6. Works regardless of received state, order reference, line number or attachment count
   (FR-013).

**Raises**: nothing on the not-found path. Storage failures propagate after the session
rolls back, as everywhere else in this service.

---

## UI entry points

Both are plain links to `GET .../delete` — no JavaScript, no dialog.

### `app/templates/product/detail.html` — purchase history (US1, FR-001)

A **Delete** control on each `.purchase-row`, in the existing **Status** cell. Putting it
there rather than in a new column keeps the six-column layout and the empty-state row's
`colspan="6"` correct.

Links to `GET /purchases/<id>/delete` with no `return_to` (the default is `product`).

### `app/templates/product/order.html` — order lines (US2, FR-014)

A **Delete** control on each `.order-line`, beside the existing Receive link, which today
appears only on outstanding lines. Delete appears on **every** line, received or not.

Links to `GET /purchases/<id>/delete?return_to=order`.

Both controls must be reachable by a stable selector for the E2E tests — a class such as
`delete-purchase-btn`, following `attach-to-purchase-btn` and `add-purchase-to-this-btn`
in the same files.
