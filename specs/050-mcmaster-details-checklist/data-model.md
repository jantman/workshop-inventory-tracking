# Data Model: McMaster Order Details Checklist

No persisted data changes. One in-memory field is added:

## OrderVendor (app/services/order_vendors.py)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `listing_url` | `(item_id: str) -> str`, optional | `None` | Builds the vendor's product-listing address from a line's item id. Its presence means the vendor's order page offers the details checklist. |

| Vendor | `listing_url` |
|---|---|
| Amazon | `https://www.amazon.com/dp/<ASIN>` |
| McMaster-Carr | `https://www.mcmaster.com/<part>/` |
| DigiKey | none |
| any unregistered vendor | none (no `OrderVendor`) |

"Missing details" remains derived: a product with no specification rows
(`CatalogService.products_missing_details`).
