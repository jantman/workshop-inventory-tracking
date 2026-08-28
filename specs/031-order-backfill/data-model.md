# Data Model: Backfilling Past Orders

**Feature**: 031-order-backfill | **Spec**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

## No schema change

`Purchase.received_date` already exists, is already nullable, and is already the sole
representation of "outstanding" everywhere in the application. This feature writes it at a
different moment in a purchase's life; it does not change what it means or what it is.

**No Alembic revision ships with this feature** (research.md §9). Constitution V is satisfied by
there being nothing to migrate.

## Existing entities this feature writes to

### `Purchase` (`app/database.py`)

| Field | Before | After |
|---|---|---|
| `received_date` | Always `NULL` when written by `capture_order_lines` | `NULL`, or the operator's arrival date when the line's decision says the order already arrived |

Nothing else about a `Purchase` changes. Its `quantity`, `unit_price`, `order_date`,
`supplier_order_reference` and vendor fields are written exactly as they are today.

**Invariant preserved**: `received_date >= order_date`. Enforced by
`CatalogService._validate_receipt_order` (`app/catalog_service.py:1661`) — the same check receiving
already uses, called on the arrival date before the write session opens so a refusal leaves
nothing half-written.

### `Product` — deliberately not written

Capture-time arrival does **not** adjust `quantity`, does **not** touch `quantity_updated_at`, and
does **not** clear `stock_status` or `stock_status_updated_at`. This is FR-028 and the reasoning is
in research.md §2: a delivery from two years ago has already been consumed, and a low flag set last
month is a statement about today's shelf.

This is the one place where capture-time arrival and `receive_purchase` deliberately disagree.

## Derived views that become correct for free

Neither is stored and neither changes.

| View | How it is derived | Effect |
|---|---|---|
| Reorder list "on the way" | `Product.purchases.any(Purchase.received_date.is_(None))` (`app/catalog_service.py:597`) | A backfilled order's products stop being marked on the way (FR-027) |
| Captured-orders outstanding count | `case((Purchase.received_date.is_(None), 1), else_=0)` (`app/catalog_service.py:2505`) | `CapturedOrder.outstanding_count` falls to zero, so `is_complete` is true (FR-019, FR-027) |

## New value objects

### `DigiKeyOrderSummary` (`app/models.py`)

One row of DigiKey's order listing. A frozen dataclass with a `from_payload` classmethod, in the
same shape as `DigiKeyOrder` and `DigiKeyPart` beside it.

| Field | Type | Notes |
|---|---|---|
| `sales_order_number` | `str` | What the existing capture screen accepts. The only field the flow strictly needs. |
| `order_date` | `Optional[datetime]` | FR-020 — how the operator tells which orders they have dealt with |
| `customer_reference` | `str` | DigiKey's own name for the order, where the account sets one. Display only. |
| `status` | `str` | The `SalesOrderStatus` description DigiKey returns. Display only. |
| `line_count` | `Optional[int]` | Display only; absent where the listing does not carry it |

**Not persisted.** It exists between the API response and the template, like `DigiKeyOrder`.

**`from_payload` returns `None` for an entry it cannot make sense of**, matching
`DigiKeyOrder.from_payload`. A listing with one unreadable entry renders the rest; it does not
fail.

**Exact source field names are the open input** — closed by the live call in research.md §5 and
recorded in `verification.md` before this dataclass is written.

### `AmazonExportSummary` (`app/services/amazon_order_export.py`)

What the reduction command produces. Never touches the catalog (FR-016).

| Field | Type | Notes |
|---|---|---|
| `orders` | `tuple[AmazonExportOrder, ...]` | De-duplicated, in first-seen order (FR-012) |
| `rows_read` | `int` | FR-013 |
| `rows_unusable` | `int` | Rows whose `Order ID` did not match `\d{3}-\d{7}-\d{7}` — digital orders, blanks (research.md §7) |
| `status_counts` | `tuple[tuple[str, int], ...]` | Each `Order Status` seen and how many orders carry it, most common first. **Reported, never filtered**, and reported only when more than one is present. Replaces the `unusual_status_count` this document first proposed: "unusual" would have meant hard-coding a guess at Amazon's status vocabulary |

### `AmazonExportOrder`

| Field | Type | Notes |
|---|---|---|
| `order_id` | `str` | Matches the capture agent's `AMAZON_ORDER_ID_PATTERN` |
| `website` | `str` | From the row's own `Website` column, so a mixed-marketplace export yields live links |
| `url` | `str` (property) | `https://{website}/gp/css/order-details?orderID={order_id}` |
| `row_count` | `int` | How many item rows named this order. Display only; makes "eleven rows, one order" visible |

## Entities from the spec that are deliberately not modelled

- **Historical order** — not a type. A historical order is an ordinary order whose purchases carry
  a past `received_date`. Giving it a type would mean a flag on a row saying how it was created,
  which nothing would ever read.
- **Selected order list** — a file on the operator's disk. The catalog never sees it (FR-016).
- **Backfilled purchase** — an ordinary `Purchase`. Nothing marks it as backfilled, because
  nothing needs to distinguish it: it is a real purchase that really arrived.

## State transitions

A purchase has exactly two states and this feature adds no third.

```text
                    capture (today)
   [ does not exist ] ─────────────────► [ outstanding: received_date IS NULL ]
            │                                          │
            │  capture, marked already arrived         │  receive_purchase
            │  (FR-024)                                │  (unchanged)
            └──────────────────────────────────────────▼
                                        [ delivered: received_date IS NOT NULL ]
```

The new edge is the diagonal. Both edges write the same column, and the only difference between
them is that the existing one also adjusts the product's count and clears its low flag.

**A re-capture never moves a purchase along either edge**: `capture_order_lines` `continue`s on an
already-recorded line before any write (research.md §3), which is FR-030.
