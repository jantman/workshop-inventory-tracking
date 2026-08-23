# Contract: Outbound Calls to DigiKey

**Feature**: `specs/024-digikey-order-capture/`

**Status: verified against the live production API on 2026-08-22.** Every path, header, field
name and type below was observed, not transcribed. See [verification.md](../verification.md).

The whole of this contract is implemented by `app/services/digikey.py` and by nothing else.
That module imports `requests`, the standard library and `app.models` — **not**
`app.database`, not `app.catalog_service`, not Flask. It has no knowledge that a database
exists.

Base URL is `DIGIKEY_API_BASE`, default `https://api.digikey.com`. The sandbox is the same
paths on `https://sandbox-api.digikey.com`.

---

## Module surface

```python
class DigiKeyClient:
    def __init__(self, client_id: str, client_secret: str, account_id: str,
                 base_url: str = 'https://api.digikey.com',
                 timeout: float = 10.0) -> None: ...

    def get_order(self, sales_order_number: str) -> DigiKeyOrder: ...
    def get_part(self, part_number: str) -> DigiKeyPart: ...
```

Two public methods. Token acquisition and renewal are private and automatic.

`timeout` defaults to 10 seconds, matching `store_listing_images`. There is no async path and
no retry loop (Principle I — `listing_images.py` argues the same case in its docstring).

---

## 1. Token — 2-legged, verified

```
POST {base}/v1/oauth2/token
Content-Type: application/x-www-form-urlencoded

client_id=…&client_secret=…&grant_type=client_credentials
```

Observed: `HTTP 200`, `token_type=Bearer`, `expires_in=599`.

Held in memory on the client instance with its expiry and renewed within 30 seconds of
expiring. **Not written to disk** — there is nothing worth persisting about a 10-minute token,
and a file is a secret to keep out of the repository.

**No 3-legged flow, no callback, no token file.** The registered OAuth callback
(`https://localhost`) exists because the portal demands one and is never exercised.

---

## 2. Every request

```
Authorization:             Bearer {access_token}
X-DIGIKEY-Client-Id:       {client_id}
X-DIGIKEY-Account-ID:      {account_id}          ← REQUIRED. See below
Accept:                    application/json
X-DIGIKEY-Locale-Site:     US
X-DIGIKEY-Locale-Language: en
X-DIGIKEY-Locale-Currency: USD
```

**`X-DIGIKEY-Account-ID` is not optional.** Without it every order endpoint answers
`400 Account ID must not be 0` — a 2-legged token carries no user context, so nothing has said
which account the request is for. This is DigiKey's replacement for `X-DIGIKEY-Customer-Id`,
sunset 2025-11-24, and their changelog lists ProductDetails among the endpoints that take it,
so it is sent on every request rather than only on order calls.

The value is `DIGIKEY_ACCOUNT_ID`, an account number rather than a credential, kept in `.env`
with the other two settings rather than hard-coded.

> DigiKey publishes an `AssociatedAccountIds` API that would let the application discover this
> value. Its path is not documented outside the portal login and eight candidate paths returned
> 404, so one configured number is the simpler answer. Revisit only if the account changes.

Responses are read as **text** and parsed with `json.loads(body, parse_float=Decimal)`.
Never `response.json()` — that hands back `float` prices, and Constitution III prohibits
binary floating point for a measured quantity. Verified on real data: the two unit prices on
the recorded order come back as `Decimal('6.5')` and `Decimal('6.9')`, and the order total as
`Decimal('67.0')`. This one line is the whole of the numeric integrity story.

---

## 3. `GET {base}/orderstatus/v4/salesorder/{salesOrderId}`

Quota 120/min, 1,000/day. 2-legged plus the account header.

> **The v4 field names are not the v3 field names.** Most were renamed. The table below is what
> the live API returned; anything resembling the old generated client is wrong.

| JSON | → `DigiKeyOrder` | Note |
|---|---|---|
| `SalesOrderId` | `sales_order_number` | capital `O`; an `int`, read as a string |
| `DateEntered` | `order_date` | ISO 8601 with offset. **Present** — no fallback needed |
| `PurchaseOrder` | `purchase_order` | `""` when the operator gave none |
| `Currency` | `currency` | recorded and displayed, never converted |
| `LineItems[]` | `lines` | |

Present and deliberately unused: `OrderNumber` (a separate 16-digit web order number, **not**
the sales order id), `Status` (`{SalesOrderStatus, ShortDescription, LongDescription}`),
`TotalPrice`, `ShipMethod`.

| JSON (line item) | → `DigiKeyOrderLine` | Note |
|---|---|---|
| `DigiKeyProductNumber` | `digikey_part_number` | renamed from v3's `DigiKeyPartNumber` |
| `ManufacturerProductNumber` | `manufacturer_part_number` | renamed from `ManufacturerPartNumber` |
| `Description` | `description` | renamed from `ProductDescription` |
| `QuantityOrdered` | `quantity` | renamed from `Quantity` |
| `QuantityShipped` | `quantity_shipped` | |
| `QuantityBackOrder` | `quantity_backorder` | capital `O` |
| `CountryOfOrigin` | `country_of_origin` | |
| `UnitPrice` | `unit_price` | `Decimal` |
| `DetailId` | `line_number` | **`PoLineItemNumber` is `null`** — use this 1-based index |

**There is no `Manufacturer` field on a line.** The manufacturer's name comes from §4, which is
why capture enriches every line — see §5.

Present and unused: `PackType`, `QuantityInitialRequested`, `QuantityReserved`, `Schedules[]`,
`CustomerReference`, `TotalPrice`, and `ItemShipments[]`
(`{QuantityShipped, InvoiceId, ShippedDate, TrackingNumber, ExpectedDeliveryDate}`).

**Never read**, and redacted from the recorded fixture: `Contact` (`Email`, `FirstName`,
`LastName`), `ShippingAddress`, `CustomerId`. They are personal details the catalog has no use
for.

---

## 4. `GET {base}/products/v4/search/{productNumber}/productdetails`

Quota 120/min, 1,000/day. Accepts a DigiKey part number or a manufacturer part number.

Everything hangs off a top-level `Product` object, and **several fields are nested objects
rather than the flat strings the v3 shape suggested**:

| → `DigiKeyPart` | v4 path |
|---|---|
| `manufacturer` | `Product.Manufacturer.Name` |
| `manufacturer_part_number` | `Product.ManufacturerProductNumber` |
| `description` | `Product.Description.ProductDescription` |
| `detailed_description` | `Product.Description.DetailedDescription` |
| `category_path` | `Product.Category.Name` |
| `datasheet_url` | `Product.DatasheetUrl` |
| `photo_url` | `Product.PhotoUrl` |
| `product_url` | `Product.ProductUrl` |
| `unit_price` | `Product.UnitPrice` (`Decimal`) |
| `parameters` | `Product.Parameters[]` → `{ParameterText, ValueText}` |
| `digikey_part_number` | `Product.ProductVariations[]` — or the order line, which already has it |

Observed on the recorded part: 17 parameters, a manufacturer datasheet URL, a photo URL, and
category `"Power Supplies - Board Mount"`.

Present and unused: `ProductStatus`, `Series`, `Classifications`, `OtherNames`,
`QuantityAvailable`, `Discontinued`, `EndOfLife`, `Ncnr`, `BaseProductNumber`,
`PrimaryVideoUrl`, `ManufacturerLeadWeeks`.

**`ProductUrl` confirms [research §11](../research.md)**: it is
`…/products/detail/mean-well-usa-inc/IRM-05-5/7704652`, so the second-to-last path segment is
the manufacturer part number and the last is an internal product id. Read the MPN from the
path; never derive a part number from the trailing id.

---

## 5. Enrichment: one part call per order line

A capture calls §3 once and then §4 **once per line**, because the order response carries no
manufacturer name and none of the datasheet, photo, category or parametric detail.

For a 24-line order that is 25 calls at review and, after the operator confirms, one more order
call plus one part call per *included* line. Against a quota of 1,000/day and 120/min that is
not a constraint; against wall-clock it is roughly ten to fifteen seconds a page, which is the
same order as the eight to fifteen seconds an Amazon gallery capture already takes and which
the user manual already sets that expectation for.

**No caching between the review and the confirmation.** The order must be re-read because it is
the authority on what was ordered and what is already captured; the parts are re-read because
carrying seventeen parameters per line through a form is worse than asking for them again.
Principle I forbids a cache without a measured problem — if this proves slow in use, that is a
measurement and it can be revisited then.

**The two failure modes are not the same, and must not be conflated:**

| What failed | Consequence |
|---|---|
| The **order** call | The capture fails. Nothing is written (FR-039) |
| A **part** call | That line captures with what the order gave — part numbers, description, quantity, price — and loses only the manufacturer, datasheet, photo, category and parameters. The review says which lines came back thin |

This is the split `app/services/listing_images.py` already documents: an unreachable CDN must
not cost the operator the purchase they just made.

---

## 6. Failure mapping

No new exception class. Every state FR-038 distinguishes already has one in
`app/exceptions.py`, and `create_error_handlers(app)` already handles them
([research §7](../research.md)).

| Condition | Raised |
|---|---|
| `DIGIKEY_CLIENT_ID` or `DIGIKEY_ACCOUNT_ID` unset | `ConfigurationError` |
| Token request rejected; `401`; `403` | `AuthenticationError` |
| `404`, or a `200` naming no order | `ItemNotFoundError` |
| `400 Account ID must not be 0` | `ConfigurationError` — the account id is missing or wrong, which is configuration, not authorization |
| `429` | `RateLimitError` |
| Connection error, timeout, `5xx`, unparseable body | `TemporaryError` |

`RateLimitError` reads `X-RateLimit-Reset` when present, so the operator is told when to try
again rather than guessing.

**The client raises; it does not return a status object.** `StorageResult` is the storage
layer's convention (Constitution II) and this is not the storage layer.

---

## 7. What is deliberately not called

| Endpoint | Why not |
|---|---|
| Barcode API | `app/utils/ecia.py` already parses the label locally and has since the first release. A network round-trip to be told what `1K` means is not an improvement — and §8 of [verification.md](../verification.md) confirms the local parse against a real label and a real order |
| Ordering API | This feature never places an order. It also requires a DigiKey Credit account |
| `AssociatedAccountIds` | One configured account number is simpler than discovering it; see §2 |
| MyLists, Quote, SupplyChain | Nothing in the spec asks for them |

No retry logic, no request caching, no connection pooling beyond what `requests` does by
default, and no rate-limit scheduler.
