# Contract: `CatalogService` bulk-receipt methods

**Feature**: 042-bulk-receive-outstanding | **File**: `app/catalog_service.py`

Two methods: one reads, one writes. The split is what makes `--dry-run` and the confirmation
prompt fall out rather than becoming conditionals, and it makes the write explicit about which
rows — the caller passes back the plan it showed the operator.

---

## `plan_outstanding_receipts(vendor=None, before=...) -> OutstandingReceiptPlan`

```python
def plan_outstanding_receipts(
    self,
    before: datetime,
    vendor: Optional[str] = None,
) -> OutstandingReceiptPlan:
```

**Reads only. Writes nothing.**

### Selection

A purchase is a candidate when all of:

- `received_date IS NULL` — outstanding (FR-002).
- `order_date IS NOT NULL` — there is a date to receive it at (FR-006).
- `order_date < before` — strictly before the cutoff (FR-004).
- `LOWER(TRIM(vendor)) = LOWER(TRIM(:vendor))`, when `vendor` is given (FR-003, FR-005).

Provenance is not part of the predicate: a hand-recorded outstanding purchase from 2023 is the
same wrong state as a captured one and is eligible (FR-007).

Ordered by `order_date`, then `id`. The product is eager-loaded, so rendering the listing does
not fire a query per row.

### Returns

An `OutstandingReceiptPlan` (see `data-model.md`) carrying one `OutstandingReceipt` per
candidate and `undated_count` — outstanding purchases matching the vendor filter that were
excluded for having no order date. A plan with no receipts is the ordinary "nothing to do"
answer, not an error.

### Raises

Nothing of its own. `before` is validated by the caller before it gets here.

---

## `apply_outstanding_receipts(plan) -> int`

```python
def apply_outstanding_receipts(self, plan: OutstandingReceiptPlan) -> int:
```

**Writes `purchases.received_date` and nothing else.**

### Behaviour

Inside one `self._session()` block — which commits on success and rolls back on any exception,
which is FR-020 in full — for each of `plan.purchase_ids`:

- Load the purchase. A row that has since vanished is skipped.
- Skip it if `received_date` is already set: an existing receipt is never overwritten (FR-002).
- Skip it if `order_date` is `None`: there is no date to write.
- Otherwise set `received_date = order_date` (FR-008).

Returns how many purchases it wrote.

### What it must not do

This list is the feature, and it is the thing that will silently stop being true if somebody
routes this through `receive_purchase` later. `tests/unit/test_bulk_receive.py` is what will
notice.

| Must not | Requirement | Why |
|---|---|---|
| Change `product.quantity` | FR-009 | Goods delivered in 2023 were consumed in 2023. Adding them now inflates every counted quantity in the catalog. |
| Change `product.quantity_updated_at` | FR-010 | Nobody counted anything; the operator is at a terminal, not at the shelf. |
| Change `product.stock_status` or its date | FR-011 | A low flag set last month is a statement about today's shelf, not about a 2023 delivery. |
| Change the purchase's quantity, price or notes, or the product's description | FR-012 | Not asked for and not knowable in bulk. |

This is the same position `capture_order_lines` takes for a line captured as already-arrived
(031 FR-028), reached the same way: by writing the column directly rather than calling
`receive_purchase`.

### Raises

Nothing of its own. A database failure propagates after `_session()` has rolled back, so a
failed sweep has written nothing.
