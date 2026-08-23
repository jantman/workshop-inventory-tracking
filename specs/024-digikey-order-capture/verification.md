# Verification: DigiKey API Access (T001)

**Feature**: `specs/024-digikey-order-capture/` | **Run**: 2026-08-22
**Against**: production `https://api.digikey.com`, sales order `100882558`, part `1866-3027-ND`

**Outcome: (a) — build as planned**, with one addition the plan did not anticipate. Two of the
five risks in [plan.md](./plan.md) are closed, one materialized and is resolved below, and one
new requirement appeared.

---

## 1. Authentication — 2-legged works

```
POST https://api.digikey.com/v1/oauth2/token   grant_type=client_credentials
→ HTTP 200   token_type=Bearer   expires_in=599
```

**R1 is closed.** A personal account can read its own orders. No DigiKey Credit account was
needed, no 3-legged flow, no browser round-trip, no token file on disk. The 599-second lifetime
confirms the 10-minute figure in [research §2](./research.md), so the client's "renew within 30
seconds of expiry" rule is correctly sized.

The registered OAuth callback (`https://localhost`) is never exercised. It stays registered
because the portal requires one.

## 2. NEW REQUIREMENT — `X-DIGIKEY-Account-ID`

A 2-legged token carries no user context, so every order endpoint refused it:

```
GET /orderstatus/v4/salesorder/100882558      → 400  "Account ID must not be 0"
GET /orderstatus/v4/orders                    → 400  "Account ID must not be 0"
```

Adding the account number as a header fixed it outright:

```
GET /orderstatus/v4/salesorder/100882558
    X-DIGIKEY-Account-ID: <account number>    → 200
```

This is DigiKey's documented replacement for `X-DIGIKEY-Customer-Id`, sunset 2025-11-24. It is
**not** a permission problem — the API was reading an account id off the request and finding
zero, because nothing had said which account.

**Consequence**: a third setting, `DIGIKEY_ACCOUNT_ID`, alongside the client id and secret. It
is an account number, not a credential, but it lives in `.env` with the other two rather than
being hard-coded. The header is sent on every request, product endpoints included — DigiKey's
sunset changelog lists ProductDetails among the endpoints that take it.

**Not implemented, worth knowing**: DigiKey has an `AssociatedAccountIds` API that would let the
application discover this value instead of being told it. Its path is not published outside the
portal login and eight candidate paths returned 404. One configured number costs less than the
hunt; revisit only if the account number ever changes.

## 3. R3 is closed — the order date is present

`DateEntered` is on the v4 sales-order response: `"2026-08-07T17:34:04.332-05:00"`. The v3
generated client had no date at the order level, which is why
[contracts/digikey-api.md](./contracts/digikey-api.md) §3 carried a two-step fallback through
the orders-history endpoint. **That fallback is unnecessary and is removed.**

## 4. R2 materialized — v4 renamed most line-item fields

The contract's field names were transcribed from the v3 generated client. Nearly all of them
changed. This is exactly what T001 existed to catch, and it cost one mapping table rather than
a redesign.

### Order level

| v3 (what the contract said) | v4 (actual) | Note |
|---|---|---|
| `SalesorderId` | `SalesOrderId` | capital `O`; an `int`, read as a string |
| — | `DateEntered` | new; closes R3 |
| `PurchaseOrder` | `PurchaseOrder` | unchanged; `""` on this order |
| `Currency` | `Currency` | unchanged; `"USD"` |
| — | `OrderNumber` | **not** the sales order id — a separate 16-digit web order number |
| — | `Status` | `{SalesOrderStatus, ShortDescription, LongDescription}`, e.g. `"Shipped"` |
| — | `TotalPrice` | order total |
| `ShippingDetails[]` | *(gone)* | per-shipment data moved onto each line as `ItemShipments[]` |

Never read, and redacted from the fixture: `Contact` (`Email`, `FirstName`, `LastName`),
`ShippingAddress`, `CustomerId`.

### Line level

| v3 | v4 | Note |
|---|---|---|
| `DigiKeyPartNumber` | `DigiKeyProductNumber` | **renamed** |
| `ManufacturerPartNumber` | `ManufacturerProductNumber` | **renamed** |
| `ProductDescription` | `Description` | **renamed** |
| `Quantity` | `QuantityOrdered` | **renamed** |
| `QuantityBackorder` | `QuantityBackOrder` | capital `O` |
| `Manufacturer` | **ABSENT** | see §5 |
| `PoLineItemNumber` | present but **`null`** | use `DetailId` instead — a 1-based line index |
| `UnitPrice`, `TotalPrice` | unchanged | |
| `CountryOfOrigin`, `CustomerReference`, `QuantityShipped` | unchanged | |
| — | `DetailId`, `PackType`, `QuantityInitialRequested`, `QuantityReserved` | new |
| — | `ItemShipments[]` | `{QuantityShipped, InvoiceId, ShippedDate, TrackingNumber, ExpectedDeliveryDate}` |
| — | `Schedules[]` | empty on this order |

## 5. `Manufacturer` is not on an order line

The v4 order response gives the manufacturer **product number** but not the manufacturer's
**name**. It is available from ProductDetails (`Product.Manufacturer.Name` →
`"MEAN WELL USA Inc."`), which is a separate call per part.

This bears on FR-003, which requires the review to show the manufacturer, and on
[data-model §2](./data-model.md), which maps `products.manufacturer` from the line. **Open
decision — see §9.**

## 6. `Decimal` parsing confirmed on real data

`json.loads(body, parse_float=Decimal)` yields `Decimal('6.5')` and `Decimal('6.9')` for the
two lines' unit prices, and `Decimal('67.0')` for the order total. The prohibition on
`response.json()` in `app/services/digikey.py` is doing real work: these are the values that
would otherwise have been binary floats.

## 7. ProductDetails v4 confirmed

`GET /products/v4/search/1866-3027-ND/productdetails` → 200, 5,092 bytes. Everything US3 needs
is present, though several fields are nested objects rather than the flat strings
[data-model §3](./data-model.md) assumed:

| `DigiKeyPart` field | v4 path |
|---|---|
| `manufacturer` | `Product.Manufacturer.Name` — **nested** |
| `manufacturer_part_number` | `Product.ManufacturerProductNumber` |
| `description` | `Product.Description.ProductDescription` — **nested** |
| `detailed_description` | `Product.Description.DetailedDescription` — **nested** |
| `category_path` | `Product.Category.Name` — **nested**; e.g. `"Power Supplies - Board Mount"` |
| `datasheet_url` | `Product.DatasheetUrl` |
| `photo_url` | `Product.PhotoUrl` |
| `product_url` | `Product.ProductUrl` |
| `unit_price` | `Product.UnitPrice` (`Decimal`) |
| `parameters` | `Product.Parameters[]` → `{ParameterText, ValueText}`; **17 rows** on this part |
| `digikey_part_number` | `Product.ProductVariations[]` — the order line already carries it |

Also present and unused: `ProductStatus`, `Series`, `Classifications`, `OtherNames`,
`QuantityAvailable`, `Discontinued`, `EndOfLife`, `Ncnr`, `BaseProductNumber`,
`PrimaryVideoUrl`.

**Research §11 is confirmed**: `ProductUrl` is
`https://www.digikey.com/en/products/detail/mean-well-usa-inc/IRM-05-5/7704652` — the
second-to-last path segment is the manufacturer part number and the last is an internal product
id. Reading the MPN from the path is right; deriving a part number from the trailing id is not.

## 8. The label in issue #108 cross-validates

Re-splitting the issue's run-together label against this order's real values resolves it
completely, and every field agrees:

| Identifier | Label value | API value |
|---|---|---|
| `1K` | `100882558` | `SalesOrderId: 100882558` ✓ |
| `10K` | `130599231` | `ItemShipments[0].InvoiceId: 130599231` ✓ |
| `Q` | `5` | `QuantityOrdered: 5` ✓ |
| `4L` | `CN` | `CountryOfOrigin: "CN"` ✓ |
| `P` / `30P` | `1866-3032-ND` | line 2's `DigiKeyProductNumber` ✓ |
| `1P` | `IRM-10-5` | line 2's `ManufacturerProductNumber` ✓ |

This settles the ambiguity in [research §4](./research.md) that GitHub's stripping of the `GS`
separators had left: the label carries `30P` as well as `P`, both holding the DigiKey part
number. `app/utils/ecia.py` reads `P` and ignores `30P`, which is correct and needs no change.

**The plan's whole receiving mechanism is confirmed against real data**: `1K` + `P` off a bag
label identify exactly one line of exactly one order.

## 9. Open decision

`Manufacturer` is absent from order lines (§5). Either the review shows no manufacturer at
order capture, or capture makes one ProductDetails call per line. Quota is not the constraint —
120/min and 1,000/day against a 24-line order — but it is 24 extra sequential requests and a
larger failure surface, against a principle that says build for the requirement in front of
you. **Put to the user; the answer amends FR-003 and [data-model §2](./data-model.md).**

## 10. Artifacts

- `tests/fixtures/digikey/salesorder.json` — 2 lines, 5 each; `Contact` removed,
  `ShippingAddress` values and `CustomerId` replaced
- `tests/fixtures/digikey/productdetails.json` — 17 parameters, datasheet, photo, category

**Neither fixture exercises a line with no manufacturer part number** (FR-016), because no order
on this account has one. That test gets a hand-built variant, labelled as such, rather than a
pretend recording.
