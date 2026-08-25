# Contract: the McMaster capture payload

**Feature**: 028-mcmaster-order-capture

What `app/static/js/capture-agent.js` posts and what the server accepts. This is the machine
boundary: the agent is cache-busted and updates itself, the server is deployed separately, and
a version of one **will** meet a version of the other. Both sides are written to that.

## The rule both sides obey

> A payload the server cannot read is not an error. It renders today's behaviour.

This is 007 FR-007 and it is what makes a stale cached agent harmless. Every "returns null"
below is that rule, not defensive decoration.

---

## 1. Dispatch — what the agent decides before it reads anything

Keyed on the URL **path**, never the hostname (research.md §3 — the e2e harness serves fixtures
from the app's own origin, so a host gate would leave the McMaster readers with no end-to-end
coverage at all).

| Path shape | Kind | Posts |
|---|---|---|
| `/dp/<ASIN>`, `/gp/product/<ASIN>`, `/product/<ASIN>` | Amazon listing | today's fields, **unchanged** |
| `/<part-number>/` — digits, a letter, then alphanumerics (e.g. `/91290A115/`) | McMaster product | today's fields **plus** `vendor` |
| `/products/<part>/` — the family table `/catalog/<part>` redirects to | *not* dispatched | it lists many part numbers, not one product (research.md §5) |
| `/order-history/` — the order list | *not* dispatched | it names many orders |
| `/order-history/order/<24 hex>` — resolved from the live site, research.md §5 | McMaster order | `url`, `vendor`, `order` |
| anything else | unrecognized | today's behaviour, **unchanged** |

Amazon's row is the one that matters most: it is not "also handled", it is *not touched*. No
edit on that path is what makes SC-010 checkable by running the existing suite.

---

## 2. Transport

Unchanged from today, and unchanged **deliberately**:

* **A form POST into a new tab**, not a `fetch`. The vendor page is HTTPS and this app is plain
  HTTP on the LAN, so a fetch is refused as mixed content before CORS or CSRF are consulted. A
  form submission is a navigation and is exempt.
* **To `/api/capture`**, the endpoint the bookmarklet was already given. The bookmarklet's text
  does not change, so the operator never re-drags it (FR-034, research.md §2).
* `@csrf.exempt`, as today: the POST comes from the vendor's origin, where no token can be had.

---

## 3. Order payload — the `order` form field

One hidden field holding JSON. Present **only** for a McMaster order page.

```json
{
  "version": 1,
  "vendor": "McMaster-Carr",
  "source_url": "https://www.mcmaster.com/<order path>",
  "order_number": "12345678",
  "order_date": "2026-08-10",
  "lines_read": 14,
  "lines": [
    {
      "line_number": 1,
      "part_number": "91290A115",
      "description": "Black-Oxide Alloy Steel Socket Head Screw, M3 x 0.5 mm Thread, 10 mm Long",
      "packs": 2,
      "pack_size": 100,
      "pack_price": "12.34"
    }
  ]
}
```

### Field rules

| Field | Required | Type | Notes |
|---|---|---|---|
| `version` | yes | integer | must be `1`; anything else → the payload is not read |
| `vendor` | yes | string | must equal `McMaster-Carr`; the agent declares what it read (research.md §4) |
| `source_url` | yes | string | the order page's address |
| `order_number` | yes | string | **no order number, no order** — the key everything else hangs off |
| `order_date` | no | string | parsed leniently; unparseable is the same as absent, and absent is ordinary |
| `lines_read` | no | integer | line elements *seen*, including unusable ones. Absent → treated as `len(lines)` |
| `lines` | yes | array | may be empty |

**Prices are strings, always.** JSON's only number type is an IEEE double, so `12.34` sent as a
JSON number would be a `float` before any Python saw it. Constitution III has no exemption for a
value in transit. It stays a string until the server turns it into a `Decimal` — the same path a
hand-typed price already takes.

`packs` and `pack_size` are integers because they are counts. A page stating no pack size means
the item is not pack-priced: `pack_size` is omitted and one unit is one unit.

### Line rules

| Field | Required | Notes |
|---|---|---|
| `line_number` | no | 1-based position as read. Absent → the part number becomes the form key, which is correct for every order that does not repeat a part |
| `part_number` | no | absent for a shipping, handling or service line — kept and capturable on its description (FR-019) |
| `description` | no | McMaster's wording |
| `packs`, `pack_size`, `pack_price` | no | any of them absent leaves that field blank and editable on the review |

**A line is dropped only when it has neither a part number nor a description** — there is nothing
for the operator to decide about. Every drop still counts toward `lines_read`, which is the
whole point of that field.

### What the server does with a bad payload

| Payload | Result |
|---|---|
| absent | today's behaviour: the Amazon/paste-a-URL confirmation form |
| not JSON, not an object, or an unknown `version` | as above — logged, never raised |
| no `order_number` | "this page yielded no order", with the hand-entry way forward (FR-038) |
| `vendor` not `McMaster-Carr` | not treated as a McMaster order |
| `lines: []` with a valid order number | the review, stating **0 of `lines_read`** — never an empty review that reads like an empty order (FR-004, FR-038) |
| one malformed line | that line dropped, every other line offered (FR-036) |

---

## 4. Product payload — `listing`, plus `vendor`

The existing `listing` field and the existing `ListingCapture` shape, with McMaster's values in
it. The server side needs no change to parse it.

| Key | From a McMaster product page |
|---|---|
| `vendor_item_id` | the McMaster part number |
| `listing_title` | McMaster's description of the part |
| `price` | string, as always |
| `brand` | usually absent — McMaster mostly names no manufacturer, and that is a fact rather than a miss |
| `description_text` | the page's prose, where there is any |
| `specifications` | `[{"name": ..., "value": ...}]` from the page's specification table |
| `images` | absolute `http(s)` addresses |

Two additions to the transport, neither changing the type:

* **`vendor`** — its own form field, `McMaster-Carr`. `product_capture()` already prefers a
  submitted vendor over a derived one (`app/product/routes.py:468`), so this is the agent
  filling a field that already exists.
* **`pack_price` / `pack_size`** — form fields feature 017 already put on the confirmation page.
  UI-only, recorded nowhere; what is stored is a unit price.

---

## 5. Server-side URL reading

Parallel to `_asin_from_url` (`app/product/routes.py:841`), and for the same reason: a URL path
is a contract, so the paste-a-URL form can read it with no agent involved (FR-025).

| Input | Yields |
|---|---|
| `https://www.mcmaster.com/91290A115/` | `91290A115` |
| `https://www.mcmaster.com/91290A115/socket-head-screws/` | `91290A115` |
| anything else | `''` — blank for the operator to fill in, never an error |

The pattern is **deliberately duplicated** between the agent and the server rather than shared.
They live on opposite sides of a machine boundary; the agent's copy is what the McMaster reader
dispatches on, and the server's is what the paste-a-URL form uses. The Amazon pair carries the
same note at `capture-agent.js:38`.

---

## 6. Compatibility

| Situation | Behaviour |
|---|---|
| Old bookmarklet, new agent | Works. The bookmarklet is a loader and its text does not change. |
| New agent, old server | The server sees a form field it does not read. The Amazon path behaves exactly as before; the McMaster order posts land on the ordinary confirmation form. Nothing 500s. |
| Old cached agent, new server | Cannot happen — `?v=' + Date.now()` means the browser never serves a cached agent — and is harmless if it did: no `order` field, today's behaviour. |
