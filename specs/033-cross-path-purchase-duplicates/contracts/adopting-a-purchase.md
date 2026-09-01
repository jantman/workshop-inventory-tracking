# Contract: Adopting an Existing Purchase into an Order

**Feature**: `specs/033-cross-path-purchase-duplicates` | **Date**: 2026-09-01

This is a server-rendered Flask application, so its contract is its HTTP surface plus the
service methods the routes are thin over. No route is added, no route is removed, and no URL
changes. What changes is what three existing forms carry and what two existing service methods
consider.

---

## 1. The order review form — one new input

**Rendered by** `app/templates/product/order_review.html`, **posted to** each vendor's existing
confirm endpoint (`vendor.confirm_endpoint`): `product.digikey_order_confirm`,
`product.mcmaster_order_confirm`, `product.amazon_order_confirm`.

| Field | Value | When rendered |
|---|---|---|
| `same_purchase[{form_key}]` | `adopt` \| `separate` | On every line where `reviewed.needs_same_purchase_answer` is true |

Radio group, no default selected. Re-rendered from `form_data` on a refused submission, the way
`resolution[...]`, `include[...]`, `description[...]` and `apply_change[...]` already are — an
answer given to one line must survive a refusal caused by another.

**Deliberately not `resolution[...]`.** That input already answers the CONFLICT question with
`attach`/`separate`, and a line can be both contradicted and adoptable. Two questions, two
inputs.

The line also renders, from `reviewed.candidate`: the candidate's order date, quantity, unit
price and product description, and — where `candidate.is_received` — a plain statement that
adopting will not un-receive it.

`apply_change[{form_key}]` is now rendered for an adoptable line too, on the same condition it
already uses (`reviewed.has_change`).

**Unchanged**: every other field, the hidden `order` payload for page-read vendors, the hidden
`sales_order_number` for DigiKey, `arrived_date`, and the CSRF token.

## 2. `_order_decisions(form, order)` — one new key

`app/product/routes.py:1366`. Built by walking the **order**, not the form. Each per-line dict
gains:

```python
'same_purchase': form.get(f'same_purchase[{key}]') or '',
```

Read for every vendor and ignored by lines with no candidate, exactly as `resolution` already
is. No branch, no vendor-specific handling.

## 3. `CatalogService.review_order(order, vendor, client=None)` — unchanged signature

Still writes nothing. Each `ReviewedLine` it returns may now carry a `candidate`.

**Candidate selection** (research.md §2, §6), inside the existing session:

1. Query purchases where `vendor == vendor.name`, `vendor_item_id IN {vendor.item_id_of(line)
   for line in order.lines}`, `supplier_order_reference IS NULL`, and `order_date` within
   `CANDIDATE_WINDOW` of the order's date. Rows with `order_date IS NULL` are excluded.
2. Walk `order.lines` in order. A line already paired exactly (state CAPTURED) takes nothing.
   Every other line whose item id matches is offered the row closest in date to the order's
   date, ties broken by lowest `id`. **The row is offered to every matching line, not to the
   first only** — see research.md §13: draining it into one line let an exclusion lose the
   question and silently duplicate. Which line actually gets it is settled at claim time.

An order with no date has no candidates at all: FR-006, and it follows from step 1 rather than
from a special case.

## 4. `CatalogService.capture_order_lines(order, vendor, decisions, client=None, arrived_date=None)` — unchanged signature

Still one session for the whole order, still all-or-nothing.

**Per line, after the CAPTURED `continue` and the include gate:**

| Condition | Behavior |
|---|---|
| No candidate | Exactly today's behavior. |
| Candidate, `same_purchase == 'adopt'`, row unclaimed | Claim it (§5). No product resolution, no new `Purchase`. |
| Candidate, `same_purchase == 'adopt'`, row already claimed by an earlier line | Ordinary line: one purchase cannot be two lines of an order, so this one records its own. |
| Candidate, `same_purchase == 'separate'` | Exactly today's behavior; the candidate is untouched. |
| Candidate, anything else | `ValidationError`, `field=f'same_purchase[{line.form_key}]'`, **nothing written** — the session rolls back whole. |

The refusal is raised inside the session, for the reason `_product_for_order_line` already gives
for an unanswered CONFLICT: the operator answered a question about an order, and half an order
is worse than none.

**Excluded lines are never asked** and never claim anything (FR-008b).

## 5. Claiming — what is written to the adopted row

In this order, on the `Purchase` the candidate names:

1. `supplier_order_reference` ← the order's, and `order_line_number` ← the line's. Always.
2. `order_date` ← the order's — **unless** that would place it after a recorded
   `received_date`, in which case it is left alone (research.md §5).
3. Every other key of `vendor.order_fields(order)` — `vendor_order_id`, `order_reference`,
   `listing_url` — **only where the purchase currently holds NULL**.
4. If `decision['apply_change']`, `_apply_order_change(purchase, line, decision, vendor)`,
   counting into `lines_updated` exactly as it does for a CAPTURED line.

Never written: `product_id`, `received_date`, `notes`, `listing_title`, and — absent
`apply_change` — `quantity` and `unit_price`.

## 6. `OrderCaptureResult` — one new field

`purchases_adopted: tuple` — the ids claimed. `purchase_ids` keeps meaning "created".

Both tuples are passed to `_orphaned_order_purchases(..., also_claimed=...)`. **Omitting the
adopted ids reports every adopted row as orphaned**, because claiming stamps the order reference
inside the same session the orphan re-query runs in (research.md §8).

`wrote_anything` gains `or bool(self.purchases_adopted)`, and `_order_capture_summary` gains a
matching clause above the "Nothing new to capture" fallback — both, or
`test_the_fallback_agrees_with_wrote_anything` fails, which is what it is for.

## 7. `CatalogService.capture_order(...)` — unchanged signature, widened recognition

`_find_captured_purchase(vendor, vendor_item_id, listing_url, order_date)` keeps its existing
same-day query verbatim and, **only when that returns nothing**, tries once more:

- `vendor == vendor`, `vendor_item_id == vendor_item_id` (never the `listing_url` fallback —
  research.md §7), `supplier_order_reference IS NOT NULL`, `order_date` within
  `CANDIDATE_WINDOW`. Nearest by date wins, ties by lowest `id`.

A hit raises the **existing** `CaptureDecisionRequired` with the **existing**
`acknowledged_duplicate_of` escape, carrying a `CaptureAssessment` whose new
`duplicate_order_reference` names the order. Nothing about the flow, the exception, the route
handling or the checkbox changes.

## 8. `/api/capture` (JSON)

`CaptureAssessment.to_dict()` gains `duplicate_order_reference`. Additive — no existing key
changes name, type or meaning.

## 9. What is explicitly **not** in this contract

- No new route, and no change to any URL or endpoint name.
- No change to `OrderVendor`. The candidate lookup is vendor-agnostic (research.md §2), so no
  member is added and `tests/unit/test_order_vendors.py` — the seam's own test — is untouched.
- No schema change and no Alembic revision.
- No way to un-adopt. Feature 032's delete is the recovery path.
