# Contract: Arrival at Capture

**Requirements**: FR-024 – FR-031 | **Research**: research.md §1–§4

Vendor-agnostic. One implementation on the shared flow; **no new `OrderVendor` member**
(research.md §10).

## Form (`app/templates/product/order_review.html`)

Posted to whichever `vendor.confirm_endpoint` the review already posts to. Two new names:

| Name | Kind | Meaning |
|---|---|---|
| `arrived_date` | `date`, order-level, optional | When the order arrived. Blank with any line marked arrived means "use the order's own date" (FR-026). |
| `arrived[{form_key}]` | checkbox, per line | This line arrived. Absent means it did not (FR-029). |

`form_key`, never the item id — two lines can carry the same item, which is why every other
per-line field on this form is keyed this way (`app/product/routes.py:1236`).

**The order-level checkbox** ("This order has already arrived") is a convenience that ticks the
per-line boxes and reveals them. It is **not submitted and not read**: the server reads only
`arrived[{form_key}]`, so what the operator can see ticked is exactly what will be recorded.

**Not the default.** An unticked review records outstanding purchases exactly as it does today
(FR-025).

**The review must say what confirming will do** — that these lines will be recorded as delivered,
and that a counted product's on-hand quantity will not move (FR-028, research.md §2).

## Route (`app/product/routes.py`)

`_order_decisions(form, order)` gains one key, read for every vendor:

```python
'arrived': form.get(f'arrived[{key}]') is not None,
```

Two call sites pass `arrived_date=request.form.get('arrived_date')` through to the service:
`digikey_order_confirm` (`app/product/routes.py:1184`) and `_confirm_page_order`, the one
implementation McMaster and Amazon both confirm through.

**The new fields must survive a refusal.** Both sites re-render the review with
`form_data=request.form` when the service raises, and the template reads every other field back out
of `form_data` — `arrived_date` and `arrived[{form_key}]` do the same, so an A3-style refusal does
not silently untick what the operator had set.

`_order_capture_summary` gains a clause naming how many lines were recorded as already arrived. The
rule that function's docstring states — *every outcome that changed the database has to appear
here* — makes this mandatory, not decorative.

## Service (`app/catalog_service.py`)

```python
def capture_order_lines(
    self, order, vendor, decisions, client=None, arrived_date=None,
) -> OrderCaptureResult:
```

| Behaviour | Rule |
|---|---|
| Date parsing | `_parse_datetime(arrived_date, 'arrived_date')`, **before the session opens** |
| Fallback | No date given, line marked arrived → `order.order_date` (FR-026). Never `datetime.now()`. |
| Validation | `_validate_receipt_order(order.order_date, arrived)` — refused if earlier than the order date. Raised before the session opens, so **nothing is written** |
| The write | `received_date=arrived if decision.get('arrived') else None` in the existing `Purchase(...)` call |
| Product | **Not touched.** No count adjustment, no `quantity_updated_at` change, no `stock_status` clearing (FR-028) |
| Already-captured lines | Unreachable — settled and `continue`d before the include gate (FR-030) |
| Excluded lines | Unreachable — an excluded line produces no purchase, arrived or not |

`OrderCaptureResult` gains `lines_arrived: int` so the route can report it.

## What must still be true afterwards

- An unticked capture is byte-for-byte the capture that shipped in feature 029. The DigiKey,
  McMaster and Amazon unit suites pass **unedited** — that is the gate for this slice.
- `CapturedOrder.is_complete` is true for a fully-arrived order, and the reorder list does not mark
  its products on the way. Both derived, both asserted rather than assumed (research.md §2).
