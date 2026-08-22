# Contract: Outbound Calls to DigiKey

**Feature**: `specs/024-digikey-order-capture/`

The whole of this contract is implemented by `app/services/digikey.py` and by nothing else.
That module imports `requests`, the standard library and `app.models` — **not**
`app.database`, not `app.catalog_service`, not Flask. It has no knowledge that a database
exists.

Base URL is `DIGIKEY_API_BASE`, default `https://api.digikey.com`. The sandbox is the same
paths on `https://sandbox-api.digikey.com`.

> **Verified where it says verified.** Paths, quotas and token lifetimes below come from
> DigiKey's developer portal. Response *field names* for Order Status are transcribed from the
> v3 generated client and are re-confirmed against the live v4 API in `T001` before any of this
> is written; see [research §5](../research.md).

---

## Module surface

```python
class DigiKeyClient:
    def __init__(self, client_id: str, client_secret: str,
                 base_url: str = 'https://api.digikey.com',
                 timeout: float = 10.0) -> None: ...

    def get_order(self, sales_order_number: str) -> DigiKeyOrder: ...
    def get_part(self, part_number: str) -> DigiKeyPart: ...
```

Two public methods. Token acquisition and renewal are private and automatic.

`timeout` defaults to 10 seconds, matching `store_listing_images`. A capture is something the
operator waits a couple of seconds for; there is no async path and no retry loop
(Principle I — and `listing_images.py` already argues the same case in its docstring).

---

## 1. Token

```
POST {base}/v1/oauth2/token
Content-Type: application/x-www-form-urlencoded

client_id=…&client_secret=…&grant_type=client_credentials
```

Response carries `access_token` and `expires_in` (seconds). DigiKey documents a **10-minute**
lifetime for the 2-legged access token.

Held in memory on the client instance with its expiry, and renewed when it is within 30
seconds of expiring. **Not written to disk** — there is nothing worth persisting about a
10-minute token, and a file is a secret to keep out of the repository.

If `T001` shows 2-legged cannot read this account's orders, this section is replaced by the
3-legged flow (authorization code, non-expiring refresh token in an untracked
`credentials/digikey_token.json`). Nothing else in this contract changes.

---

## 2. Every request

```
Authorization:            Bearer {access_token}
X-DIGIKEY-Client-Id:      {client_id}
Accept:                   application/json
X-DIGIKEY-Locale-Site:    US
X-DIGIKEY-Locale-Language: en
X-DIGIKEY-Locale-Currency: USD
```

Responses are read as **text** and parsed with `json.loads(body, parse_float=Decimal)`.
Never `response.json()` — that hands back `float` prices, and Constitution III prohibits
binary floating point for a measured quantity. This single line is the whole of the numeric
integrity story and it is the easiest thing in this feature to get wrong.

---

## 3. `GET {base}/orderstatus/v4/salesorder/{salesOrderId}`

Quota 120/min, 1,000/day. Supports 2-legged and 3-legged OAuth.

Fields consumed — everything else in the response is ignored silently, exactly as
`ecia.parse` ignores identifiers it has no home for:

| JSON | → `DigiKeyOrder` |
|---|---|
| `SalesorderId` | `sales_order_number` (as a string) |
| `PurchaseOrder` | `purchase_order` |
| `Currency` | `currency` |
| *(order date — see below)* | `order_date` |
| `LineItems[]` | `lines` |

| JSON (line item) | → `DigiKeyOrderLine` |
|---|---|
| `PoLineItemNumber` | `line_number` |
| `DigiKeyPartNumber` | `digikey_part_number` |
| `ManufacturerPartNumber` | `manufacturer_part_number` |
| `Manufacturer` | `manufacturer` |
| `ProductDescription` | `description` |
| `Quantity` | `quantity` |
| `UnitPrice` | `unit_price` (`Decimal`) |
| `QuantityShipped` | `quantity_shipped` |
| `QuantityBackorder` | `quantity_backorder` |
| `CountryOfOrigin` | `country_of_origin` |

**Never read**, and never stored anywhere: `ShippingAddress`, `BillingAddress`, `Email`,
`CustomerId`, `BillingAccount`, `PaymentMethod`. They are personal details the catalog has no
use for, and the recorded test fixture has them redacted.

**The order date.** The v3 sales-order response carries none; only the history item does
(`DateEntered`). If v4's does not either, the client makes one additional call to
`GET {base}/orderstatus/v4/orders` filtered to that sales order and reads `DateEntered`; if
that also fails, `order_date` is `None` and the write falls back to today, which is what
`capture_order` already does for a capture with no date.

---

## 4. `GET {base}/products/v4/search/{productNumber}/productdetails`

Quota 120/min, 1,000/day. Accepts a DigiKey part number or a manufacturer part number.

Consumed into `DigiKeyPart`: the description (short and detailed), manufacturer name,
manufacturer product number, the DigiKey part number from the product variations, the datasheet
URL, the photo URL, the product URL, the category, the unit price, and the `Parameters` list of
`{ParameterText, ValueText}` pairs.

**The exact field paths are written from the response recorded in `T001`, not from memory.**
A field this endpoint does not return costs that field and nothing else — a missing datasheet
is a product without a datasheet, never a failed capture.

---

## 5. Failure mapping

No new exception class. Every state FR-038 distinguishes already has one in
`app/exceptions.py`, and `create_error_handlers(app)` already handles them
([research §7](../research.md)).

| Condition | Raised |
|---|---|
| `DIGIKEY_CLIENT_ID` unset | `ConfigurationError` |
| Token request rejected; `401`; `403` | `AuthenticationError` |
| `404`, or a `200` naming no order | `ItemNotFoundError` |
| `429` | `RateLimitError` |
| Connection error, timeout, `5xx`, unparseable body | `TemporaryError` |

`RateLimitError` reads `X-RateLimit-Reset` when present, so the operator is told when to try
again rather than guessing.

**The client raises; it does not return a status object.** `StorageResult` is the storage
layer's convention (Constitution II) and this is not the storage layer.

---

## 6. What is deliberately not called

| Endpoint | Why not |
|---|---|
| Barcode API | `app/utils/ecia.py` already parses the label locally and has since the first release. A network round-trip to be told what `1K` means is not an improvement |
| Ordering API | This feature never places an order. It also requires a DigiKey Credit account |
| MyLists, Quote, SupplyChain | Nothing in the spec asks for them |

No retry logic, no request caching, no connection pooling beyond what `requests` does by
default, and no rate-limit scheduler. 1,000 calls a day against a workshop that orders once a
fortnight is not a constraint, and Principle I requires a measured problem before machinery.
