# Contract: HTTP routes

**Feature**: 029-whole-order-capture

Two routes are new, one grows a branch, two converge into one, and one helper states its rule
once instead of branching on a vendor.

---

## Changed

### `POST /api/capture` — grows one branch

`app/product/routes.py`, `api_capture()`. Already `@csrf.exempt` (it is posted cross-origin from
the vendor's page), already accepts a form body, already renders rather than writes.

```
if the form carries an `order` field that parses as a McMaster order payload:  → McMaster review
if it parses as an Amazon order payload:                                       → Amazon review
otherwise:                                                                     → exactly what it does today
```

**Still writes nothing.** The branch is a read of the payload plus a read of the catalog; the
operator can close the tab with no trace (FR-005).

**Regression boundary**: a request with no `order` field must take a path identical to today's —
asserted by `tests/e2e/test_product_page_capture.py` and `test_order_capture.py`, unchanged.

### `_receive_url(resolution)` — one rule, not a vendor branch

Today it branches on `vendor == MCMASTER_VENDOR`. The rule underneath is already vendor-neutral
(research.md §11):

| Outstanding candidates | Landing |
|---|---|
| Exactly one | that line's receipt, quantity pre-filled where the scan carried one |
| More than one | the choice page — the catalog never picks |
| None, some received | said plainly; nothing is received twice |

**DigiKey's landing does not change.** Its "several → the order screen" behaviour is a special
case of the middle row, available because a DigiKey label names its order. FR-041 forbids
changing it and the existing tests measure it.

---

## Converged

### `GET /products/digikey/orders/<n>` + `GET /products/mcmaster/orders/<n>` → `GET /products/orders/<vendor>/<number>`

One route, one template (`order.html`), for every vendor.

**The old addresses must keep working** — they are in the operator's history and are what
`_receive_url` has been redirecting to. They redirect to the new one. FR-044: every order
captured before this feature stays openable.

An order number naming no captured order renders "not captured" with a way forward, never a 404
(FR-032).

---

## New

### `POST /products/amazon/orders/capture` — confirm a reviewed Amazon order

The write. Same-origin, so **CSRF-protected** like every other form in the application — unlike
`/api/capture`, which is not same-origin and cannot be.

Body: the carried payload, plus one decision set per line (`include`, `description`, `quantity`,
`unit_price`, `resolution`, `apply_change`), keyed by `form_key`.

**The payload is carried through the confirmation**, because there is nothing to re-read
(FR-006) — what the review displayed is what gets written. This is the McMaster pattern, not the
DigiKey one.

Success → redirect to the order screen with a summary. Refusal (a conflicted line with no
resolution) → the review, re-rendered, with **nothing written** (FR-020).

### `GET /products/orders` — the captured-orders list

FR-033, FR-034. Every captured order across every vendor: vendor, number, date, line count,
outstanding count. Most recent first, and an order with nothing outstanding is distinguishable at
a glance (US3 scenario 2).

Derived from `purchases` (data-model.md §5) — no table, no stored state.

Reachable from the Products navigation dropdown, alongside the existing capture entries.

---

## Unchanged

`/products/capture`, `/products/digikey/orders`, `/products/digikey/part`,
`/products/mcmaster/orders/capture`, `/products/purchases/receive-choice`,
`/purchases/<id>/receive`, `/api/scan`, and every product and identifier route. FR-041.
