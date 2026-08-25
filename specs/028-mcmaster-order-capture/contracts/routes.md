# Contract: HTTP routes

**Feature**: 028-mcmaster-order-capture

Three routes are new, one grows a branch, and one helper changes what it reads. Everything else
in `app/product/routes.py` is untouched.

---

## Changed

### `POST /api/capture` — grows one branch

`app/product/routes.py:698`, `api_capture()`. Already `@csrf.exempt`, already accepts a form
body, already renders rather than writes.

```
if the form carries an `order` field that parses as a McMaster order payload:
    render the McMaster order review
otherwise:
    exactly what it does today
```

**Still writes nothing.** The branch is a read of the payload plus a read of the catalog; the
operator can close the tab with no trace left (FR-005).

**Why here and not on a route of its own**: the bookmarklet's text cannot change without the
operator re-dragging it (FR-034), and this is the endpoint it already names. research.md §2.

**Regression boundary**: a request with no `order` field must take a code path identical to
today's. That is what `tests/e2e/test_product_page_capture.py` and `test_order_capture.py`
already assert, unchanged.

---

## New

### `POST /products/mcmaster/orders/capture` — confirm a reviewed order

The write. Same-origin, so **CSRF-protected** like every other form in the application — unlike
`/api/capture`, which cannot be.

| Field | Meaning |
|---|---|
| `order` | the same payload the review was built from, carried in a hidden field |
| `include[<form_key>]` | present ⇒ capture this line |
| `description[<form_key>]` | the operator's label description for a line that creates a product |
| `quantity[<form_key>]`, `unit_price[<form_key>]` | the computed values, overruled if edited (FR-020a) |
| `resolution[<form_key>]` | `attach` or `separate`, for a `CONFLICT` line (FR-018) |
| `apply_change[<form_key>]` | present ⇒ apply a changed quantity or price to an already-captured line (FR-017) |

**The payload is re-parsed here, not trusted from the review's rendering.** It is also the
authority on what the order contains: decisions are collected by walking the *payload's* lines,
so a decision submitted for a line the payload does not carry is ignored rather than acted on —
the rule `_digikey_decisions` already follows (`app/product/routes.py:1132`).

**This is the FR-006 route.** DigiKey's equivalent re-reads the order from DigiKey and treats
the fetched order as authority. There is nothing here to re-read, so what the review displayed
is what this writes.

| Outcome | Response |
|---|---|
| success | redirect to the order screen, flashing what was written — every outcome that changed the database named, including a bare change application |
| `ValidationError` (e.g. an over-long description) | re-render the review **carrying what was submitted**, so an authored description is not lost |
| unreadable payload | the "no order on this page" statement and the hand-entry way forward (FR-038) |

### `GET /products/mcmaster/orders/<order_number>` — a captured order

Derived, never stored: the order **is** the purchases carrying its number.

Renders every line with its product, quantity, unit price and state, the outstanding count
(FR-028), and a receive control per outstanding line (FR-029). An order number nothing was
captured against renders **"not captured"** with a way forward — not a 404 (FR-031). Nothing
dead-ends.

`?highlight=<part number>` marks a line, for arriving here from a scan.

### `GET /products/purchases/receive-choice` — the candidate chooser

Where a scanned part number names more than one outstanding McMaster line (FR-032a).

Query: `?scan=<the scanned value>`. Lists one row per candidate — order number, order date,
quantity, unit price, product — each linking to its own `purchase_receive`.

**Why this exists rather than reusing DigiKey's answer**: DigiKey's candidates are two lines of
*one* order, so the order screen shows them both. McMaster's can be on two orders placed weeks
apart, and no single order screen shows both. research.md §11.

Zero candidates by the time it loads (received in another tab) renders "nothing outstanding for
this part" and offers the product. Never an empty list, never a 404.

---

## Changed helper

### `_receive_url(resolution)` — reads the purchases, not the scan

`app/product/routes.py:1495`. Today it takes the order number from
`resolution.classification.ecia_fields['1K']`, which is populated for an ECIA label scan and
**empty for a free-text part-number scan** — so as it stands a McMaster match would build an
order URL with a blank order number.

It reads the vendor and the order number off the matched purchases instead. Better for DigiKey
too: the purchases carry it either way, and it is the record rather than the scan.

| Vendor | one candidate | several | none outstanding |
|---|---|---|---|
| DigiKey | its receipt — **unchanged** | its order screen, candidates marked — **unchanged** | its order screen, "already received" — **unchanged** |
| McMaster-Carr | its receipt, quantity pre-filled | the chooser | *not reachable* — the scan never became `receive` |

`app/static/js/scan-capture.js` navigates to whatever this returns without inspecting the
outcome, so it needs no change (as it did not for feature 024).

---

## Unchanged, and asserted to be

FR-033 and SC-010 name these. Every one of them has existing tests, and those tests are the
check:

`GET|POST /products/capture` (paste-a-URL and the Amazon landing) · `POST /api/scan` for every
scan that is not an outstanding McMaster part number · `GET|POST /purchases/<id>/receive` ·
`GET|POST /products/<id>/purchases/new` · every `/products/digikey/*` route · every
`/api/products*` route · the bookmarklet's text.
