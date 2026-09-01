# Research: Recognize a Listing Capture and an Order Line as One Purchase

**Feature**: `specs/033-cross-path-purchase-duplicates` | **Date**: 2026-09-01

Everything below was established by reading the code, not assumed. Line numbers are as of
`de97597`.

---

## §1 — Where the blind spot actually is

`capture_order_lines` never asks whether a purchase for this *item* exists. It asks whether a
purchase for this *order* exists, and that question is delegated to
`OrderVendor.order_purchases`, which every vendor implements as a filter on
`supplier_order_reference`:

- `_amazon_order_purchases` — `app/catalog_service.py:4269`: `vendor == Amazon` and
  `supplier_order_reference == cleaned`. One pass.
- `_digikey_order_purchases` — `:4068`: the same shape on the sales order number.
- `_mcmaster_order_purchases` — `:2260`: two passes, but both inside
  `vendor_order_id`/`supplier_order_reference`.

`capture_order` reaches `record_purchase` (`:1281`) passing neither `supplier_order_reference`
nor `order_line_number`, so a listing-captured row has both NULL and matches none of the three
queries. `_recorded_order_lines` (`:2186`) then runs both of its passes over that empty result
set — including pass two, which exists precisely for "purchases carrying no line number".

**Conclusion**: the defect is one missing input, not a wrong algorithm. Pass two already knows
how to claim a row by item id; it is never handed a row to claim.

## §2 — The candidate query is vendor-agnostic, so no `OrderVendor` member is needed

The three facts a candidate needs — `vendor`, `vendor_item_id`, `order_date` — are written
identically by every path, and the two the vendor would otherwise disagree about do not appear:

- `Purchase.vendor` holds the same string for both paths. `OrderVendor.name` "must equal what
  `_vendor_from_url` derives" (`app/services/order_vendors.py`, `name`), and `capture_order`
  writes exactly what `_vendor_from_url` derived.
- `Purchase.vendor_item_id` is written by `capture_order` (`:1284`) and by every vendor's
  `line_fields`. The vendors differ in what *product identifier type* they claim
  (`DISTRIBUTOR` vs `VENDOR` — see `_mcmaster_product_by_part_number`, `:2513`), but that is a
  `product_identifiers` concern and this lookup does not touch it.
- The line's item id is already available generically as `vendor.item_id_of(line)`.

**Decision**: one new private helper on the service —
`_candidate_order_purchases(session, order, vendor, order_date)` — filtering
`vendor == vendor.name`, `vendor_item_id IN (the order's item ids)`,
`supplier_order_reference IS NULL`, and the date window. No new `OrderVendor` member, and
FR-021 (all three vendors) is satisfied by construction rather than by three edits.

**Alternative rejected**: widening each vendor's `order_purchases` to return these rows. It
would have put candidates into `_orphaned_order_purchases` (§8), which reports "purchases
recorded against this order that no line claims" — a listing capture is not recorded against
this order and reporting it as a stale line of one would be a new false alarm.

## §3 — Adoption is a decision layered on the existing state, not a fifth `OrderLineState`

`OrderLineState` is documented as "exclusive and exhaustive, tested in this order"
(`app/models.py:1908`), and `_review_order_line` (`:2399`) tests CAPTURED → CONFLICT → MATCHED
→ NEW. A fifth value would have to be inserted into that order, and it would have to answer
"what happens if the operator says *separate*?" — at which point the line is whatever it would
have been anyway (NEW, MATCHED or CONFLICT), and the state has been thrown away.

**Decision**: `ReviewedLine` keeps its four states and gains candidate fields. The review
renders the adopt/separate choice *in addition to* whatever the state renders, and a line
answered "separate" runs today's code path untouched.

This also settles the interaction with CONFLICT: a line can be both contradicted and have a
candidate, and the two questions are then asked side by side — the shape `capture_order`
already uses, where "two questions can be open at once … neither implies the other"
(`CaptureAssessment`, `app/models.py:501`).

**Form key**: `same_purchase[{form_key}]`, values `adopt` / `separate`. Deliberately *not*
`resolution[...]`, which CONFLICT already owns with values `attach`/`separate` — one input
answering two different questions on the same line is how the wrong answer gets applied.

## §4 — What claiming writes: the order's fields, not the line's

`OrderVendor` already splits Purchase fields into `order_fields(order)` and
`line_fields(service, line, decision)`. That split is exactly the rule this feature needs:

- **Order-level fields are the order's.** The purchase is now a line of that order, and every
  sibling row carries them. `supplier_order_reference` and `order_line_number` are stamped
  unconditionally — that is FR-012, and it is what makes a *second* capture of the same order
  pair exactly and ask nothing.
- **Line-level fields stay the operator's**, changed only through the existing
  `apply_change` tick (`_apply_order_change`, `:2367`). The operator has had the box in their
  hands; the page has not.

The remaining `order_fields` keys — `vendor_order_id` and `order_reference` for McMaster,
`listing_url` for both McMaster (`:4153`) and Amazon — are written **only where the purchase
holds NULL**. Amazon's
`order_fields` sets `listing_url` to the *order page* address (`:4294`), and overwriting a
listing capture's `/dp/B0G43FCHFX` with it would destroy the one field that says where the item
can be bought again. "Fill gaps only" is not invented here: it is the documented rule for
`OrderVendor.enrich_product`.

## §5 — `order_date`, and the one invariant that can bite

`find_captured_orders` (`:2667`) derives an order's date as `func.min(Purchase.order_date)`
across its rows. Leaving a claimed purchase on the operator's typed date would make the order
list report an order as older than it is — in the reported case, 2026-07-23 becoming
2026-07-27's sibling with the order itself dated 07-23 and one line dated 07-27.

**Decision**: claiming stamps the order's `order_date`.

**With one guard.** `_validate_receipt_order` (`:1750`) is the standing invariant "nothing
arrives before it is ordered". A claimed purchase may already be received, and an order date
later than its `received_date` would create exactly the row every other write path refuses. So
the stamp is skipped when it would push `order_date` past a recorded `received_date`, and the
purchase keeps the date it has. One branch, one test.

## §6 — One candidate per line, chosen deterministically at review time

> **Revised in review of PR #144.** The design below — draining a pool as lines
> matched, so a candidate was offered to exactly one line — was implemented and was
> wrong. See §13.


FR-004 says a candidate is claimable by at most one line. Two mechanisms are needed and both
already have precedent in `_recorded_order_lines`:

1. **A candidate is assigned to exactly one line**, walking `order.lines` in order and removing
   each claimed row from the pool — the identical shape to pass two (`:2236`). Two lines
   carrying the same item id therefore see one candidate between them, so they cannot both
   adopt it.
2. **A line that already paired exactly is never offered one.** CAPTURED is settled before
   anything else in `_review_order_line`, and `capture_order_lines` `continue`s on it before the
   include gate (`:2066`) — so an already-captured line never reaches the adoption question.

Where one line has **two** candidates (the same item bought twice inside the window, both
listing-captured), the one **closest in date to the order's date** is offered, ties broken by
lowest `id`. Deterministic, and the review shows the candidate's date, quantity and price so
the operator can see which row they are being asked about.

## §7 — The reverse direction is one extra arm on one query

`_find_captured_purchase` (`:1465`) narrows to a single calendar day:

```python
day_start = order_date.replace(hour=0, minute=0, second=0, microsecond=0)
day_end = day_start + timedelta(days=1)
```

**Decision**: keep that query exactly as it is and try a second one only when it finds nothing —
same vendor, same `vendor_item_id`, `supplier_order_reference IS NOT NULL`, `order_date` within
the window. Restricting the widened arm to rows that carry an order number is what keeps the
blast radius to this feature: an ordinary repeat capture of a listing months later still sees
only the same-day rule and still records a second purchase without a question.

The listing-URL fallback is not widened. An Amazon order capture writes the *order page* address
into `listing_url`, never the listing's, so there is nothing there for it to match.

`CaptureAssessment` gains `duplicate_order_reference` so the warning panel can say *which*
order the existing row belongs to (FR-018). The panel and its "This is a separate order — record
it anyway" checkbox already exist (`app/templates/product/capture.html:27`), as does
`acknowledged_duplicate_of`, so FR-019 is wording plus one field — not a new flow.

## §8 — The orphan trap, which this feature walks straight into

`_orphaned_order_purchases` (`:2465`) re-queries inside the open session and subtracts
`paired` plus `also_claimed`; its docstring records that omitting `also_claimed` made "every
line of a brand-new order reported as orphaned by the capture that created it".

An adopted purchase is stamped with the order reference **inside that session**, so it comes
back from the re-query — and it is not in `paired`, which was built before the loop. Adopted
purchase ids must therefore be added to `also_claimed` alongside `purchase_ids`. Missing this
produces a flash telling the operator the row they just adopted is stale.

## §9 — The flash and `wrote_anything` must learn about adoption together

`_order_capture_summary` (`app/product/routes.py:1402`) leads with "Nothing new to capture" when
nothing was written, and `OrderCaptureResult.wrote_anything` (`app/models.py:2100`) answers the
same question independently. `test_the_fallback_agrees_with_wrote_anything`
(`tests/unit/test_mcmaster_routes.py:600`) is parametrized over result shapes and exists
specifically to catch a new kind of write added to one and not the other.

An adopt-only capture writes rows and creates no purchase, so both must count it. The
parametrize list gains a case; no existing assertion changes.

## §10 — Where the 90-day window lives

One module-level constant beside the other capture constants in `app/catalog_service.py`, read
by both directions (§2 and §7). Not configuration — Constitution I forbids a knob for a future
that has not arrived, and there is one operator with one answer.

`timedelta(days=90)` either side of the order's date, compared against `Purchase.order_date`.
A purchase or an order with no date is not a candidate: FR-006, and it falls out of the
comparison rather than needing a rule.

## §11 — Regression surface: nothing existing exercises both paths

Checked directly: no unit test calls both `capture_order(...)` and one of the order-capture
entry points, and `tests/e2e/test_amazon_order.py` is the only e2e file touching
`/products/*/orders/capture` — it never visits `/products/capture`.

The two tests that looked most at risk are both safe:

- `tests/unit/test_amazon_capture.py::TestMatchingAProductAlreadyHeld::test_a_known_asin_attaches_rather_than_duplicating`
  captures order A then order B carrying the same ASIN. A's purchase carries an order number, so
  it is **not** a candidate (FR-002) and B behaves exactly as it does today.
- `tests/unit/test_capture.py::test_the_same_item_on_a_different_day_is_a_different_purchase`
  captures the same listing twice, months apart. Neither row carries an order number, so the
  widened arm of §7 never applies.

FR-022 is therefore achievable rather than aspirational. The one file that gains a line is the
parametrize list in §9.

## §12 — No schema change

`vendor`, `vendor_item_id`, `order_date`, `supplier_order_reference` and `order_line_number` all
exist on `purchases` and all are already written by both paths. `supplier_order_reference` is
indexed; `vendor_item_id` is indexed. Nothing here needs a column, so nothing here needs an
Alembic revision — the third consecutive order feature to ship none.

## §13 — Why the candidate is offered to every matching line (PR #144 review)

§6 above assigned each candidate to exactly one line, draining a pool as it walked
``order.lines``. That satisfied "a row is claimable once" at the point of *offering*, and it
had a hole:

The assignment cannot see the operator's decisions. ``review_order`` has none, and
``capture_order_lines`` computes candidates before it reads them — deliberately, because a
capture that asked about a line the review never rendered a control for would be
unanswerable (§5's sibling trap). So the pool drained by line order alone. Give an order two
lines carrying one item id and the catalog one listing-captured purchase, and the row was
offered to line 1 only. **Exclude line 1 and capture line 2**, and line 2 found no candidate,
fell through to the ordinary write path, and recorded a second purchase for the same physical
purchase — with no question raised. The feature reproduced the bug it exists to prevent.

Reproduced against the implementation before fixing: two purchases, `order_ref` set on the
new one and still NULL on the original.

**The fix moves the "claimed once" rule from offer time to claim time.** Every line that could
be a candidate's line is offered it, so no exclusion can lose the question; a `claimed` set in
``capture_order_lines`` gives the row to the first line that answers "same purchase", and a
second line wanting the same row is an ordinary line that records its own purchase. That is
the true answer as well as the safe one: two lines of an order are two purchases, and one
purchase cannot be both of them.

Where one item has two candidates, the nearer by date is the one offered, and the other is
left alone rather than handed to a second line. A purchase this capture does not claim stays
exactly as it was — the conservative half of every choice in this flow.
