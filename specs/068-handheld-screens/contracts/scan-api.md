# Contract delta: `POST /api/scan` handheld flag

This amends the contract last changed by [067](../../067-scan-box-ja-id/contracts/scan-contract.md).
Only the changes are listed. `classify()` and `resolve_scan()` are **unchanged**.

## Request

```json
{"scan": "<text>", "handheld": true}
```

- `handheld` is optional. Absent, `false` or any falsy value gives exactly today's behavior.
  The desktop header box never sends it.
- `scan` validation is unchanged: not a string gives 400.

## Response

The response has the same shape and status codes. Only `url` differs, and only for three
outcomes:

| `outcome` | `url` without the flag (unchanged) | `url` with `handheld: true` |
|---|---|---|
| `item` | `/inventory/edit/<JA ID>` | `/h/item/<JA ID>` |
| `product` | `/products/<id>?from_scan=1` | `/h/product/<id>` |
| `receive`, one outstanding line | `/purchases/<pid>/receive[?quantity=Q]` | `/h/receive/<pid>[?quantity=Q]` |
| `receive`, not exactly one outstanding line, vendor landing `LANDING_CHOICE_PAGE` (McMaster, Amazon) | `/products/purchases/receive-choice?scan=<value>` | `/h/receive/choose?scan=<value>` |
| `receive`, not exactly one outstanding line, any other vendor (DigiKey) | `_order_url(vendor, order, P)` | `/h/orders/<vendor>/<order>?highlight=<P>` |
| `create` | create-form URL | **unchanged** (desktop) |
| `search` | `/products?q=…` | **unchanged** (desktop) |

The "none outstanding" case still flashes `That line of <vendor> order <n> is already
received.` from inside `_receive_url`. The flash shows on whichever order screen is opened next.

## Implementation shape

- `api_scan` reads `handheld = bool(data.get('handheld'))`.
- `_receive_url(resolution, handheld: bool = False)` keeps its branching exactly. Only the
  three `url_for` targets switch: `product.purchase_receive` to `handheld.receive`,
  `product.purchase_receive_choice` to `handheld.receive_choose`, and `_order_url(...)` to
  `url_for('handheld.order', vendor=…, order_number=…, highlight=…)`.

## Client

`app/static/js/scan-capture.js` `resolve()` adds `handheld: true` to the body when
`this.input.dataset.scanCapture === 'handheld'`. The body for the desktop's bare
`data-scan-capture` attribute is unchanged: `{"scan": …}`.

## Unit tests (`tests/unit/test_scan_routes.py`)

- For each of `item`, `product`, receive-single, receive-choice and receive-order: with the
  flag, the handheld URL; without it, the existing URL. The existing assertions stay as they
  are.
- `create` and `search` with the flag return the same URL as without it.
