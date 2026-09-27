# Contract: Order page details checklist

`GET /products/orders/<vendor>/<order_number>`

When the vendor has a listing address **and** the order has lines:

- `#details-progress` — `N of M product(s) still need details.` (M = distinct products),
  or `Every product on this order has its details.`
- `#order-lines` gains a **Details** column. Per line:
  - product lacks details → `.details-missing` badge; if the line has an item id, an
    `a.open-listing` with `href` = the vendor's listing address, `target="_blank"`.
  - product has details → `.details-captured` badge, no link.
  - no product → empty cell.

Otherwise (DigiKey, unknown vendor, no lines): no `#details-progress`, no Details column.

| Vendor | `a.open-listing` href |
|---|---|
| Amazon | `https://www.amazon.com/dp/<ASIN>` |
| McMaster-Carr | `https://www.mcmaster.com/<part>/` |
