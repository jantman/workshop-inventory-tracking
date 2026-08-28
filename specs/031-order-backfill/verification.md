# Verification: DigiKey Order Listing

**Feature**: 031-order-backfill | **Task**: T001 | **Date**: 2026-08-28

Closes the one unverified premise in [research.md](./research.md) §5, against the live DigiKey API
with this installation's configured credentials.

## Result: the endpoint works on the 2-legged token

`GET https://api.digikey.com/orderstatus/v4/orders` returns **200** with a `client_credentials`
token plus `X-DIGIKEY-Account-ID`, using exactly the headers `DigiKeyClient._headers()` already
sends. **No 3-legged OAuth is required.** The fallback in research.md §5 is not taken, and Phase 4
of tasks.md proceeds as planned.

## Parameters

| Parameter | Verified behaviour |
|---|---|
| `startDate`, `endDate` | `YYYY-MM-DD`. Accepted, and they are what widen the window. Case-insensitive — `StartDate`/`EndDate` returned identical results. |
| *(no parameters)* | Returns a **narrow default window** — one order on an account holding six. A listing that omits the range is therefore wrong, not merely unfiltered. |
| `limit`, `offset` | Accepted without error. Their effect could not be observed: the account holds six orders in six years, so nothing paginates. **Not used** — one call, one window, per Constitution I. |
| `daysBack` | Not a parameter. Accepted and ignored — the response was the narrow default. Recorded so nobody tries it again. |

## Response shape

```text
{
  "TotalOrders": int,
  "Orders": [
    {
      "OrderNumber":  int,          # the web order number, NOT what capture takes
      "CustomerId":   int,
      "DateEntered":  str,          # ISO 8601 with offset, e.g. 2026-08-07T17:34:04.332-05:00
      "Currency":     str,
      "PONumber":     str,          # '' when none was given at checkout
      "EntireOrderStatus": { "OrderStatus": str, "ShortDescription": str, "LongDescription": str },
      "SalesOrders": [
        {
          "SalesOrderId":   int,    # <<< THIS is what /orderstatus/v4/salesorder/{id} takes
          "Status":         { "SalesOrderStatus": str, "ShortDescription": str, "LongDescription": str },
          "PurchaseOrder":  str,
          "TotalPrice":     Decimal,
          "DateEntered":    str,
          "OrderNumber":    int,
          "ShipMethod":     str,
          "Currency":       str,
          "LineItems":      [ ... ],
          "CustomerId":     int,
          "Contact":        { "FirstName", "LastName", "Email" },
          "ShippingAddress":{ "FirstName", "LastName", "CompanyName", "AddressLine1..3",
                              "City", "State", "County", "ZipCode", "IsoCode", "Phone", "InvoiceId" }
        }
      ]
    }
  ]
}
```

## Three findings that change the implementation

**1. `SalesOrderId` is the identifier, and it is nested one level down.** The top-level
`OrderNumber` is DigiKey's web order number (a 16-digit value); `SalesOrderId` is the 9-digit sales
order number that `DigiKeyClient.get_order` takes and that
`app/templates/product/digikey_order_entry.html` already shows as its placeholder. Reading the
outer number would produce a listing whose every row 404s.

**2. One order can hold several sales orders.** DigiKey splits an order — a backorder, a separate
shipment — into multiple `SalesOrders` entries under one `OrderNumber`. **The listing must flatten
to one row per sales order**, because a sales order is the unit the capture screen accepts and the
unit a bag label's `1K` field names. `DigiKeyOrderSummary.from_payload` therefore parses a
*sales order* entry, and `list_orders` iterates the nested list.

**3. `line_count` is free.** Each sales order carries its `LineItems`, so the count needs no second
call. Everything else in that array is ignored — the listing is a chooser, not a review.

## Privacy

The response carries `Contact` (name, email) and `ShippingAddress` for every order.
**`DigiKeyOrderSummary` carries none of it** — it takes `SalesOrderId`, `DateEntered`,
`PurchaseOrder`, the status description and the line count, and drops the rest at the client
boundary rather than passing it to a template. This is not a hardening measure; it is the model
being the five fields the screen shows.

## Method

One `client_credentials` token, then `GET /orderstatus/v4/orders` with and without parameters,
inspecting key names and types rather than values. Six orders exist on the account across the
window tested. Probe scripts were run from the session scratchpad and are not part of the
repository.
