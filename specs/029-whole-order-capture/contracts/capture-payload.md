# Contract: the Amazon order payload

**Feature**: 029-whole-order-capture

What `app/static/js/capture-agent.js` posts, and what `AmazonOrder.from_payload` accepts. Rides
the existing `POST /api/capture` as one hidden `order` field holding JSON, exactly as the
McMaster order payload does — because the bookmarklet's text cannot change without the operator
re-dragging it.

---

## Dispatch

```
pageKind(location)                     # NOTE: the location, not location.pathname
  path == '/your-orders/order-details' and search carries orderID=  -> 'amazon-order'
  path matches MCMASTER_ORDER_PATTERN                               -> 'mcmaster-order'
  path matches MCMASTER_PRODUCT_PATTERN                             -> 'mcmaster-product'
  otherwise                                                          -> 'other'
```

**The signature change is the notable part.** `pageKind` takes `location.pathname` today, because
every page it has recognized so far carries its identifier in the path. Amazon's order id is in
the **query string** (research.md §2), so the function must see it. Every existing caller and
every existing return value is otherwise unchanged — this must not disturb the McMaster or
Amazon-listing paths, which FR-041 and SC-011 gate.

`/gp/css/order-details?orderID=…` needs no pattern of its own: it **302s to the canonical path**,
so the agent only ever runs on the canonical one.

`/your-orders/orders` (the list) does not match, and additionally carries none of the components
below — so FR-024 holds on the path alone.

---

## Shape

```json
{
  "version": 1,
  "vendor": "Amazon",
  "order_number": "###-#######-#######",
  "order_date": "August 22, 2026",
  "source_url": "https://www.amazon.com/your-orders/order-details?orderID=...",
  "lines_read": 4,
  "lines": [
    {
      "asin": "B0XXXXXXXX",
      "title": "…",
      "quantity": 1,
      "unit_price": "9.99",
      "line_number": 1
    }
  ]
}
```

`unit_price` is a **string**, never a JSON number: it becomes a `Decimal` server-side and a
float would corrupt it in transit (Constitution III).

`lines_read` is what the agent *saw*, including rows it could not use. `lines_read >
len(lines)` is what makes FR-004's "I could only read 4 of your 11" different from "your order
has 4 lines". A value below `len(lines)` is a malformed claim and is corrected upward.

---

## Extraction rules

| Field | Rule |
|---|---|
| Row | `[data-component="purchasedItemsRightGrid"]` — **not** `purchasedItems`, which is a group of rows |
| `asin` | `/dp/<ASIN>` links **within the row's enclosing `.a-fixed-left-grid`**, deduplicated |
| `title` | `[data-component="itemTitle"]` within the row |
| `quantity` | `.od-item-view-qty` (or `.product-image__qty`) within the row's enclosing `.a-fixed-left-grid` — a badge over the image, in the **left** grid. Absent means 1. **Not `[data-component="quantity"]`**, which is present on every row and always empty, even at quantity 4 |
| `unit_price` | `[data-component="unitPrice"] .a-offscreen` within the row — the visible span is duplicated by an `aria-hidden` twin, so `innerText` yields `"$9.99 $9.99"` |
| `line_number` | 1-based index of the row in document order |
| `order_number` | `[data-component="orderId"]` |
| `order_date` | `[data-component="orderDate"]` |

**Every field read must be scoped to the row.** The page carries ~26 `/dp/` links across ~9
distinct ASINs on a 4-line order; the surplus are recommendations. A document-wide sweep invents
order lines out of Amazon's advertising (research.md §4). This is the single most important rule
here and it has a dedicated fixture and test.

**Nothing below the dispatch may throw.** Every extraction is independent and optional: a
selector that stops matching costs that one field and nothing else (FR-021), and the loss is
reported on the review (FR-022).

---

## Server-side acceptance

`AmazonOrder.from_payload(data)` returns `None` — never raises — for:

* not an object;
* a `version` this server does not read (a stale cached agent is harmless, not a 500);
* a `vendor` that is not Amazon's;
* a body naming no order number.

The first three render today's ordinary confirmation form. The last renders FR-023's "this page
yielded no order" with a way forward.

**An empty `lines` with a valid order number is not `None`** — it is a real order whose lines
could not be read, and FR-023 requires that not look like an order with nothing in it.
