# Data Model: Whole-Order Capture for Every Vendor

**Feature**: `specs/029-whole-order-capture/` | **Date**: 2026-08-26

Three layers, and the change gets smaller at each one. The **schema** does not change at all.
The **payload** types gain one Amazon pair. The **display and result** types lose a duplicate.

---

## 1. Schema: no change

**This feature ships no Alembic revision.** Every column Amazon needs exists already:

| Column | Added by | What Amazon puts in it |
|---|---|---|
| `purchases.vendor` | original | `'Amazon'` — the value `_vendor_from_url` already derives |
| `purchases.vendor_item_id` | original, indexed | The line's ASIN |
| `purchases.supplier_order_reference` | `f3d21c9a4e10`, indexed | The Amazon order number, `\d{3}-\d{7}-\d{7}` |
| `purchases.order_line_number` | `c9e2a4d70318` | The 1-based row index (research.md §7) |
| `purchases.vendor_order_id` | `d0817b3ea45c` | **NULL.** It exists because McMaster shows no order number; Amazon's is stable, visible and printed on the page |
| `purchases.listing_title` | original | Amazon's title for the line |
| `purchases.order_date`, `.quantity`, `.unit_price`, `.received_date` | original | As for every other vendor |

Worth stating explicitly because both predecessor features needed a migration and a reader would
reasonably expect a third.

---

## 2. The consolidation seam: `OrderVendor`

New, in `app/services/order_vendors.py`. One frozen dataclass, three instances, no subclassing.
Full contract in [contracts/order-vendor.md](./contracts/order-vendor.md).

It carries **only** the eight points of variation measured in research.md §9 — the vendor's
name, the identifier types a captured line writes, and the handful of callables that genuinely
differ. Everything else moves into the shared flow.

```
OrderVendor
├── name                     'DigiKey' | 'McMaster-Carr' | 'Amazon'
├── identifier_types         which ProductIdentifier rows a captured line writes
├── item_id_of(line)         the line's vendor item id  (DKPN / part number / ASIN)
├── suggested_description()  enriched detail | the page | the title
├── find_product(session, line)
├── enrich(client, order)    DigiKey only; a no-op for the other two
├── receive_landing          how a scan of a delivered package resolves
└── review_columns           what extra columns the review and order screens show
```

**The invariant that keeps it honest** (FR-037): adding a vendor means adding one `OrderVendor`
value and one reader. If a future vendor needs a fourth branch *inside* the shared flow, the
seam is in the wrong place and should be re-cut rather than branched.

---

## 3. Payload types: one new pair

New in `app/models.py`, modelled directly on `McMasterOrder` / `McMasterOrderLine`, which are
the right precedent because both are read off a page rather than fetched from a service.

### `AmazonOrderLine`

| Field | Type | Source | Notes |
|---|---|---|---|
| `asin` | `str` | `/dp/<ASIN>` links within the row, deduplicated | May be `''` — FR-019 makes a line capturable on its title alone |
| `title` | `str` | `[data-component="itemTitle"]` | Becomes `listing_title` and the suggested description |
| `quantity` | `Optional[int]` | `[data-component="quantity"]` | **Empty means 1** (research.md §6). `None` only if the component itself is missing |
| `unit_price` | `Optional[Decimal]` | `[data-component="unitPrice"] .a-offscreen` | Already per-unit. **Never `float`** |
| `line_number` | `Optional[int]` | 1-based row index in document order | research.md §7 |

`form_key` → `str(line_number)`, falling back to `asin`. Identical in shape to both existing
line types, and for the same reason: **an item id does not identify a line**, because an order
can carry the same item twice.

**No pack arithmetic.** McMaster's `units_per_pack` / `exact_unit_price` / `price_rounds` have no
Amazon counterpart — the page states a unit price directly.

### `AmazonOrder`

| Field | Type | Source |
|---|---|---|
| `order_number` | `str` | `[data-component="orderId"]` |
| `order_date` | `Optional[datetime]` | `[data-component="orderDate"]`, US long form (`August 22, 2026`) |
| `source_url` | `str` | `location.href` |
| `lines` | `tuple` | One per `[data-component="purchasedItemsRightGrid"]` |
| `lines_read` | `int` | What the agent *saw*, so `is_incomplete` can report "4 of 11" (FR-004) |

`from_payload` follows `McMasterOrder.from_payload` exactly, returning `None` — not raising —
for a payload it cannot read: not an object, an unrecognized `version`, a `vendor` that is not
Amazon's, or a body naming no order number. **An empty `lines` with a valid order number is not
`None`**: it is a real order whose lines could not be read, which FR-023 requires be
distinguishable from an order with nothing in it.

**Deliberately absent**: the shipping address, the buyer, the payment method and the order total.
Not read, rather than read and discarded (research.md §8).

---

## 4. Display and result types: one deletion

### Unchanged, already shared

`OrderCaptureReview`, `ReviewedLine`, `OrderLineState` — both existing flows already build
these. This is why the consolidation is cheap.

Two notes on reuse:

* `ReviewedLine.part` stays `None` for Amazon, as it already does for McMaster. It holds a
  separate part lookup, and only DigiKey has one.
* `ReviewedLine.price_rounds` is `False` for every Amazon line: nothing is divided.

### `DigiKeyCaptureResult` + `McMasterCaptureResult` → `OrderCaptureResult`

The two differ by one field, and it is **the same field wearing two names**:

| DigiKey | McMaster | Meaning |
|---|---|---|
| `lines_unenriched` | `lines_incomplete` | Lines that came back thin, **named rather than counted**, so the operator knows which records to look over after leaving the review |

They merge into one `lines_incomplete`, keeping the shared fields (`purchase_ids`,
`products_created`, `products_attached`, `lines_excluded`, `lines_already_captured`,
`lines_updated`, `orphaned`) as they are.

**The rename is the only externally visible part of the merge**, and it is internal to the
service and its templates — no route signature and no stored value changes.

---

## 5. Derived, not stored: orders and the orders list

Neither an order nor the list of orders becomes a table. Both are queries, which is the
invariant both shipped features already rest on.

**One order** = the purchases where `vendor = ?` and `supplier_order_reference = ?`, ordered by
`order_line_number`. Unchanged from today.

**The captured-orders list** (FR-033) = one aggregate over `purchases`, grouped by
`(vendor, supplier_order_reference)` where the reference is not NULL, yielding per group: the
vendor, the number, the earliest `order_date`, the line count, and the count with
`received_date IS NULL`. Ordered by order date, most recent first.

**Why derived**: an order *is* its purchases. A table would be a second place for the truth to
live and a way for the two to disagree — and there is nothing to put in it that the purchases do
not already carry.

**Why no index work**: `supplier_order_reference` is already indexed and the table holds a few
thousand rows at most. Per Constitution I, no further optimization without a measurement.

---

## 6. What a captured Amazon line writes

One `Purchase`, and either a matched or a newly created `Product`:

| | |
|---|---|
| `Purchase.vendor` | `'Amazon'` |
| `Purchase.vendor_item_id` | the ASIN |
| `Purchase.supplier_order_reference` | the order number |
| `Purchase.order_line_number` | the row index |
| `Purchase.listing_title` | Amazon's title |
| `Purchase.listing_url` | the `/dp/<ASIN>` address |
| `Purchase.order_date` | the order's date |
| `Purchase.quantity`, `.unit_price` | the line's, as shown on the review |
| `Purchase.received_date` | **NULL — outstanding at capture** (FR-011), whatever the page says about delivery |
| `ProductIdentifier` | one, `ASIN` scoped to Amazon — matching what a single Amazon capture writes today |

**A product created this way is thin, and says so** (FR-026): no images, no specifications, no
barcodes, because the order page has none of them. Running the existing single-listing capture
against the same ASIN later fills it in and attaches to the same product rather than creating a
second (FR-027), through the duplicate handling that already exists.
