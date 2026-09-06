# Data Model: Bulk-Receiving Outstanding Purchases from a Backfill

**Feature**: 042-bulk-receive-outstanding | **Date**: 2026-09-06

**No schema change. No Alembic revision.** Everything this feature needs already exists on
`purchases`. What is new is two in-memory records that describe a sweep before and after it
happens.

---

## Existing tables — what is read and what is written

### `purchases` (`app/database.py:1034`)

| Column | This feature | Note |
|---|---|---|
| `id` | read | Carried through the plan so the write touches exactly the rows the operator saw. |
| `received_date` | **read and written** | The only column this feature writes. `NULL` *is* outstanding; there is no status column to keep in step. |
| `order_date` | read | Both the selection predicate and the value written into `received_date`. |
| `vendor` | read | Case-insensitively filtered; rendered. |
| `supplier_order_reference` | read | Rendered so the operator can recognize the order. |
| `quantity` | read | Rendered only. **Never used in arithmetic** — that is the whole point. |
| `product_id` | read | To reach the product's description for the listing. |
| `last_modified` | written by SQLAlchemy | `onupdate=utc_now` fires because the row changed. Correct: the row did change. |
| everything else | untouched | |

### `products` (`app/database.py`)

| Column | This feature | Note |
|---|---|---|
| `description` | read | Rendered in the listing. |
| `quantity` | **never touched** | FR-009. A 2023 delivery was consumed in 2023. |
| `quantity_updated_at` | **never touched** | FR-010. Nobody counted anything. |
| `stock_status`, `stock_status_updated_at` | **never touched** | FR-011. A flag set last month is about today's shelf. |

Those three rows are the feature. They are also the ones that will silently stop being true if
somebody later routes this through `receive_purchase`, which is why they get their own tests
rather than a comment.

---

## New records (`app/models.py`)

Both frozen dataclasses, beside `CapturedOrder` and `PurchaseDeletion`, which they follow in
shape and for the same stated reason: a service reads what the caller needs *inside* the
session and hands back a plain record, rather than handing back ORM instances whose session has
closed.

### `OutstandingReceipt`

One candidate line, flattened for rendering and for the write.

| Field | Type | Meaning |
|---|---|---|
| `purchase_id` | `int` | The row to write. |
| `vendor` | `str` | As stored, not as typed. |
| `order_date` | `datetime` | Never `None` — an undated purchase is not a candidate (FR-006). This is also the value that becomes `received_date` (FR-008). |
| `order_number` | `Optional[str]` | `supplier_order_reference`. `None` for a hand-recorded purchase, which belongs to no order. |
| `product_description` | `Optional[str]` | For recognizing the line. |
| `quantity` | `Optional[int]` | For recognizing the line. Rendered, never summed. |

`order_date` being non-optional here is a modelled invariant, not a convenience: it is what
makes "the receipt date is the order date" total rather than conditional at the point of the
write.

### `OutstandingReceiptPlan`

What one selection found.

| Field | Type | Meaning |
|---|---|---|
| `receipts` | `tuple[OutstandingReceipt, ...]` | Ordered by `order_date`, then `id`. |
| `undated_count` | `int` | Outstanding purchases excluded for having no order date (FR-006, FR-018). |

| Member | Kind | Meaning |
|---|---|---|
| `purchase_ids` | property → `list[int]` | What the write iterates. |
| `is_empty` | property → `bool` | `not self.receipts`. Drives FR-017: say so, prompt for nothing. |
| `render()` | method → `str` | The operator-facing listing plus its summary line. Following `amazon_order_export`'s summary, which `manage.py` prints the same way — the rendering of a result belongs with the result, not spread through the command body. |

`undated_count` is deliberately a count and not a list. The operator can do nothing about those
rows from this command, and naming them would invite them to try.

---

## State transition

One, per purchase:

```
outstanding  ──(sweep)──▶  received
(received_date IS NULL)     (received_date = order_date)
```

- **The transition is one-way here.** There is no un-receive, in bulk or otherwise. Undoing a
  wrong sweep means deleting the purchase (feature 032) and re-capturing it.
- **A received purchase is never re-dated.** It is not selected (FR-002), and the write re-checks
  `received_date is None` per row before setting it, so a row received between the plan and the
  confirmation is left alone rather than overwritten.
- **The transition is not a receipt in the receiving-desk sense.** Nothing else moves. See the
  `products` table above.

---

## Validation

| Rule | Where | Why |
|---|---|---|
| `--before` is a `YYYY-MM-DD` date | Click, before the command body | FR-019: refused before anything is read, with the value named. |
| `--before` is required | Click | FR-004: the cutoff is the safety rail; an unbounded sweep is not offered. |
| `received_date >= order_date` | Satisfied by construction | The two are set equal, so `_validate_receipt_order`'s rule ("nothing arrives before it is ordered") holds without being invoked. |
| The sweep is atomic | `CatalogService._session()` | FR-020. It already commits on success and rolls back on any exception. |
