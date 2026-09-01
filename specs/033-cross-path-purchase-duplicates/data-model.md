# Data Model: Recognize a Listing Capture and an Order Line as One Purchase

**Feature**: `specs/033-cross-path-purchase-duplicates` | **Date**: 2026-09-01

## Persistent schema: unchanged

**No new column, no new table, no Alembic revision.** research.md §12. Every fact this feature
reasons about is already recorded by both capture paths:

| Column on `purchases` | Written by the listing path | Written by the order path | Role here |
|---|---|---|---|
| `vendor` | `capture_order` → `record_purchase` | `OrderVendor.name` | Both halves of the candidate key |
| `vendor_item_id` | `capture_order` (`:1284`) | `vendor.line_fields` | Both halves of the candidate key |
| `order_date` | operator's, or today | the order's | The 90-day window |
| `supplier_order_reference` | **NULL, always** | the order's number | What makes a row a candidate — and what stops it being one for a *different* order |
| `order_line_number` | NULL, always | the line's number | Stamped on adoption |
| `received_date` | receiving | arrival at capture | Preserved by adoption; guards the `order_date` stamp |
| `listing_url`, `vendor_order_id`, `order_reference` | listing address / NULL | the order's | Gap-filled on adoption, never overwritten |

## In-memory model changes

### `CandidatePurchase` — new, `app/models.py`

A frozen dataclass, display-only, plain values rather than an ORM row — the reason
`ReviewedLine` and `CaptureAssessment` already give: a relationship that was not eagerly loaded
does not survive its session closing, and a template has no business carrying that hazard.

| Field | Type | Meaning |
|---|---|---|
| `purchase_id` | `int` | The row that would be adopted |
| `order_date` | `datetime \| None` | What it records as the order date — the value that disagrees with the vendor's |
| `quantity` | `int \| None` | What it records |
| `unit_price` | `Decimal \| None` | What it records |
| `product_id` | `int` | The product it is attached to; adoption never moves it (FR-015) |
| `product_description` | `str \| None` | So the review can name it |
| `is_received` | `bool` | Rendered as a warning: adopting a received row will not un-receive it (FR-014) |

### `ReviewedLine` — extended, `app/models.py:1921`

Four new fields, all defaulting to "no candidate" so every existing construction site is
unchanged:

- `candidate: Optional[CandidatePurchase] = None`

and three derived properties:

- `has_candidate` → `candidate is not None`
- `needs_same_purchase_answer` → `has_candidate and state is not OrderLineState.CAPTURED`
- `has_change` — **widened**. Today it returns False unless `state is CAPTURED`
  (`app/models.py:1967`). It must also fire for a line with a candidate, comparing the order's
  quantity and price against the candidate's, so the existing "Update it?" tick renders for an
  adoptable line (FR-009). The rounding and unread-field guards it already carries are kept
  verbatim; they are two separate PR-review fixes and neither is re-derived.

`state` is **not** extended. research.md §3: the four states stay exclusive and exhaustive, and
a line answered "separate" is whatever it already was.

### `OrderCaptureResult` — extended, `app/models.py:2050`

- `purchases_adopted: tuple = ()` — the ids of purchases this capture claimed rather than
  created. A tuple rather than a count because `_orphaned_order_purchases` needs the ids
  (research.md §8) and the flash needs the length.
- `wrote_anything` gains `or bool(self.purchases_adopted)`. It and `_order_capture_summary` are
  changed in the same commit; `test_the_fallback_agrees_with_wrote_anything` is what holds them
  in step.

`purchase_ids` keeps its meaning — **purchases created**. An adopted line must not inflate
"Captured N line(s)".

### `CaptureAssessment` — extended, `app/models.py:501`

- `duplicate_order_reference: Optional[str] = None` — the supplier order number the recognized
  purchase carries, so the warning panel can name the order (FR-018). Added to `to_dict()`
  beside the other `duplicate_*` keys, which is what carries it into `/api/capture`'s JSON.

### The decision dict — extended

`_order_decisions` (`app/product/routes.py:1366`) gains one key, read for every vendor the way
`resolution` and `apply_change` already are:

- `same_purchase`: `''` | `'adopt'` | `'separate'`, from `same_purchase[{form_key}]`.

## Relationships and invariants

- **A candidate belongs to at most one line** of an order, assigned deterministically at review
  time (research.md §6). The review and the confirmation compute the assignment the same way, so
  the row the operator was shown is the row that gets claimed.
- **A candidate never carries a supplier order number**, so it can never be a line of some other
  order (FR-002) and can never appear in `_orphaned_order_purchases`' input.
- **Adoption preserves `product_id`.** The line's product resolution — `_product_for_order_line`,
  including its create path — is **skipped entirely** for an adopted line: there is no new
  purchase to attach, and creating a product for one would be the duplicate this feature exists
  to stop. `products_created` and `products_attached` therefore do not move for an adopted line.
- **`received_date` is never written by adoption**, and the `order_date` stamp is skipped where
  it would violate `_validate_receipt_order` (research.md §5).

## State transitions

One transition, on one row:

```
listing-captured purchase                     adopted purchase
  supplier_order_reference: NULL      ──▶      the order's number
  order_line_number:        NULL               the line's number
  order_date:               operator's         the order's  (unless that would
                                                post-date received_date)
  vendor_order_id / order_reference / listing_url:
                            as recorded        gap-filled only
  quantity / unit_price:    as recorded        unchanged unless "Update it?" is ticked
  received_date / product_id / notes:          unchanged, always
```

There is no reverse transition and none is specified. A purchase adopted in error is corrected
with feature 032's delete, which is the recovery path this feature deliberately does not
duplicate.
