# Contract: Application Routes

**Feature**: `specs/024-digikey-order-capture/`

Every route below is on the existing `product` blueprint (`app/product/routes.py`), which is
where the catalog's surfaces already live. No new blueprint.

Routes stay thin: they call the client, call a service method, and render. No ORM query and no
raw SQL (Constitution II).

---

## New routes

### `GET /products/digikey/orders` — enter a sales order number

Renders the entry form. When the connection is not configured, renders the form disabled with
the "not configured" message and where to configure it (FR-036). Never 500s.

### `POST /products/digikey/orders` — fetch and review

| Form field | Required | Meaning |
|---|---|---|
| `sales_order_number` | yes | Typed, pasted or scanned (FR-001) |

**Writes nothing** (FR-004). Fetches the order, computes an `OrderCaptureReview`
([data-model §4](../data-model.md)) and renders the review page.

| Outcome | Response |
|---|---|
| Success | 200, the review page |
| Blank order number | 200, the form with a `ValidationError` message |
| Not configured | 200, the "not configured" message (`ConfigurationError`) |
| Authorization refused | 200, the "renew the authorization" message (`AuthenticationError`) |
| Order not found | 200, "not found for this account, or not visible yet" (`ItemNotFoundError`) |
| DigiKey erroring | 200, "could not be read, try again" (`TemporaryError` / `RateLimitError`) |

The four are distinguishable in what the operator is told (FR-038). They render as messages on
a working page rather than as error pages, because the operator's next action is to retype or
retry.

### `POST /products/digikey/orders/capture` — confirm and write

Carries the CSRF token: this is this application's own origin, unlike the Amazon bookmarklet.

| Form field | Repeats | Meaning |
|---|---|---|
| `sales_order_number` | once | Re-fetched and re-reviewed server-side; the fetched order is the authority |
| `include[<digikey_part_number>]` | per line | Absent means excluded (FR-007) |
| `description[<digikey_part_number>]` | per `NEW` line | Blank falls back to DigiKey's (FR-006) |
| `resolution[<digikey_part_number>]` | per `CONFLICT` line | `attach` or `separate`; **required** (FR-015) |
| `apply_change[<digikey_part_number>]` | per changed `CAPTURED` line | Applies the quantity/price change (FR-014) |

One transaction for the whole order (FR-039). On success, redirects to the captured-order
screen with a flash naming what was created. On `ValidationError` — an unresolved `CONFLICT`,
an over-long description — re-renders the review **carrying what was submitted**, so a
description the operator spent time on is not lost. This is the behaviour `purchase_receive`
already has for a refused description.

### `GET /products/digikey/orders/<sales_order_number>` — the captured order

Derived, never stored ([data-model §1](../data-model.md)). Shows every purchase carrying this
sales order number: product, quantity, unit price, and outstanding-or-received (FR-017), with a
count of how many remain outstanding (FR-018). Each outstanding line carries a **Receive**
link to `purchase_receive` (FR-022).

A sales order number with no purchases renders "not captured", with a link to capture it —
not a 404. Nothing dead-ends.

Accepts an optional `?highlight=<digikey_part_number>` used by the ambiguous-scan case
(FR-026) to mark the candidate lines.

### `GET /products/digikey/part` and `POST /products/digikey/part` — capture one part (Story 3)

| Form field | Required | Meaning |
|---|---|---|
| `part_number` | yes | A DigiKey part number, a manufacturer part number, or a DigiKey product-page address (FR-027) |

A product-page address has its manufacturer part number read out of the path
([research §11](../research.md)); anything else is passed through as given. `POST` writes
nothing — it renders the review. Confirmation posts to the existing product-create path with
the reviewed values, so there is one product-creation surface rather than two.

A part number DigiKey does not recognize renders a plain statement and the ordinary product
form carrying what was entered (FR-032).

---

## Changed routes

### `POST /api/scan` — a fourth outcome

The JSON body and the 200-for-every-well-formed-scan rule are unchanged. `outcome` gains
`'receive'`, and the payload gains `purchases`.

```jsonc
{
  "success": true,
  "outcome": "receive",
  "classification": { "kind": "ECIA", "value": "IRM-10-530", "raw": "[)>06…", "ecia_fields": {"P": "1866-3032-ND", "1P": "IRM-10-530", "Q": "10", "1K": "1008825581"} },
  "product": null,
  "prefill": {},
  "purchases": [ { "id": 412, "product_id": 88, "is_outstanding": true, "…": "…" } ],
  "url": "/purchases/412/receive?quantity=10"
}
```

`url` is what the header scan box follows, and `app/static/js/scan-capture.js` already
navigates to `data.url` without inspecting `outcome` — **so this needs no JavaScript change.**

| Matching purchases | `url` | Requirement |
|---|---|---|
| Exactly one outstanding | `purchase_receive` for it, `?quantity=` from ECIA `Q` | FR-019, FR-020 |
| More than one outstanding | The captured-order screen, `?highlight=` the part number | FR-026 |
| None outstanding, some received | The captured-order screen, with an "already received" flash naming the line | FR-023 |
| None at all | Unchanged from today | FR-024, FR-025 |

Existing outcomes `product`, `create` and `search` are byte-for-byte unchanged. Existing
callers that ignore `purchases` behave as they do today.

### `GET /purchases/<id>/receive` — quantity prefill

Accepts an optional `?quantity=` and pre-fills the quantity field with it, editable (FR-020).
Absent, the screen behaves exactly as it does now. `POST` is unchanged — receiving already
does everything FR-021 requires.

---

## Configuration

| Setting | Default | Purpose |
|---|---|---|
| `DIGIKEY_CLIENT_ID` | unset | Its absence *is* "not configured" (FR-036) |
| `DIGIKEY_CLIENT_SECRET` | unset | Untracked, `.env` only |
| `DIGIKEY_API_BASE` | `https://api.digikey.com` | Points at the sandbox during development and at the E2E fake during tests ([research §12](../research.md)) |

Read in `config.py` beside the `GOOGLE_*` settings and following their shape. Secrets never
leave `.env` (Constitution, Operating Context).

The client is built once from config and stashed as `app.config['DIGIKEY_CLIENT']`, mirroring
`app.config['STORAGE_BACKEND']`. A test injects a fake there and no application code learns it
is being tested.
