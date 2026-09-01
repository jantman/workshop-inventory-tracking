# Phase 1 Data Model: Delete a Purchase

**Feature**: `specs/032-delete-purchase` | **Date**: 2026-08-31

**No schema change.** No table, column, index or constraint is added, altered or dropped,
and there is no Alembic revision. This document describes the existing shapes the feature
operates on, what the deletion does to each, and the one new in-memory value object.

---

## Existing entities

### `purchases` — the row being deleted

`app/database.py:1029`. One acquisition of one product. Relevant properties:

| Column | Note |
|---|---|
| `id` | The deletion target. |
| `product_id` | FK → `products.id`, `ON DELETE CASCADE`. Deleting a **product** takes its purchases; the reverse does not hold and must not. |
| `vendor`, `order_date`, `quantity`, `unit_price` | What the confirmation names (FR-003). `unit_price` is `Numeric(10, 2)` → `Decimal`; render it, never `float()` it. |
| `received_date` | `NULL` *is* the outstanding state — there is no status column, so the two cannot disagree. Both states are deletable (FR-013). |
| `supplier_order_reference` | Indexed. The order screen is keyed by this; it is also what tells the route whether `return_to=order` has anywhere to go (research R3). `NULL` on hand-recorded and listing-captured purchases. |
| `attachments` | `relationship(..., cascade='all, delete-orphan', passive_deletes=True)` — `database.py:1123`. |

**Only one table references a purchase**: `product_attachments.purchase_id`. Verified by
grepping `purchases.id` across `app/database.py` and `migrations/versions/`. Nothing else
can be stranded by this deletion.

### `product_attachments` — deleted with the purchase

`app/database.py:1342`. A file belonging to a product **or** a purchase, never both —
enforced by `ck_attachment_exactly_one_owner`. `purchase_id` is
`ForeignKey('purchases.id', ondelete='CASCADE')`, and the ORM relationship cascades too,
so these rows go on their own at both levels.

Rows with `product_id` set and `purchase_id` `NULL` are untouched: a datasheet belongs to
the product and survives every purchase of it being deleted (FR-005).

### `photos` — deleted only when nothing else wants them

`app/database.py:687`. Holds the bytes behind every attachment and every item photo.
Nothing cascades from a purchase to a photo, which is the one piece of behavior this
feature has to add (FR-006):

> After the attachment rows are gone, a photo is deleted if and only if no
> `ProductAttachment` and no `ItemPhotoAssociation` still references it.

The same rule already governs `PhotoService.delete_attachment` (`photo_service.py:768`)
and the `cleanup_orphaned_photos` sweep (`photo_service.py:327`). This is its third
statement; see research R2 for why it is restated rather than shared.

### `products` — read, never written

`app/database.py:820`. The deletion **must not** write `quantity`,
`quantity_updated_at`, `stock_status` or `stock_status_updated_at` (FR-007). It must not
write `description`, and it must never delete a product (FR-005, and the "last purchase of
a product" edge case).

### `inventory_items` — not engaged at all

Purchases are catalog rows. No JA ID, active-row invariant or parent-child link is read or
written here (Constitution VI). A unit test asserts the table is untouched so that this
stays a checked claim.

### Order — derived, so nothing to update

An order has no table. `find_order_lines_for` (`catalog_service.py:2631`) *is* the order:
the purchases carrying its vendor and `supplier_order_reference`. A deleted purchase
therefore leaves its order with no fix-up step, and deleting the last one leaves the order
screen's existing "no purchase is recorded against this order" state (`order.html:34`)
rather than an error (FR-010).

---

## New value object

### `PurchaseDeletion`

Added to `app/models.py`, alongside `OrderCaptureResult`, `OrderCaptureReview` and
`ScanResolution`. A frozen dataclass — a report of what was removed, not a stored thing.

| Field | Type | Why the route needs it |
|---|---|---|
| `purchase_id` | `int` | Logging; the flash. |
| `product_id` | `int` | Where `return_to=product` redirects. |
| `vendor` | `str` | Names the purchase in the flash (FR-008). |
| `order_date` | `Optional[datetime]` | Same. `None` renders as an em dash, as elsewhere. |
| `quantity` | `Optional[int]` | Same. |
| `unit_price` | `Optional[Decimal]` | Same. **`Decimal`, never `float`** (Constitution III). |
| `supplier_order_reference` | `Optional[str]` | Where `return_to=order` redirects. `None` means there is no order to return to — fall back to the product. |
| `attachments_deleted` | `int` | The flash says how many files went with it (FR-008). |

Every field is captured **before** the row is deleted, inside the same session. The route
is told what vanished by a plain object rather than by a detached, deleted ORM instance.

---

## What the transaction does, in order

One `CatalogService._session()` — commits once or rolls back entirely (FR-012):

1. Load the `Purchase`. Absent → return `None`; the route turns that into
   `ItemNotFoundError` (FR-011).
2. Collect the `photo_id` of each of its attachments, and their count.
3. Build the `PurchaseDeletion` summary from the still-live row.
4. `session.delete(purchase)` — attachment rows cascade.
5. `session.flush()` — so step 6 sees the cascade.
6. For each collected `photo_id`: delete the `Photo` if no `ProductAttachment` and no
   `ItemPhotoAssociation` references it.
7. Commit.

Nothing in this sequence touches `products`, `inventory_items`, `product_identifiers`,
`product_specifications`, `product_tags` or any other table.
