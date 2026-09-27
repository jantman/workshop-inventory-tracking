# Data Model: Vendor Links on the Product Page

No schema change. No new table, column or migration.

## Input — `ProductIdentifier` (existing, `app/database.py`)

| Field | Use here |
|-------|----------|
| `id_type` | Only `VENDOR` and `DISTRIBUTOR` are considered |
| `vendor` | Must be exactly `Amazon`, `McMaster-Carr` or `DigiKey` (the `*_VENDOR` constants) |
| `value` | The item id placed in the address |

## Derived — vendor link (not stored)

A `(vendor, value, url)` tuple returned by `vendor_page_links(identifiers)`:

| Field | Rule |
|-------|------|
| `vendor` | The identifier's vendor, verbatim |
| `value` | The identifier's value, verbatim (display) |
| `url` | `VENDOR_PAGE_URLS[vendor](value)`, value percent-encoded |

- One entry per distinct `(vendor, value)`; the type does not distinguish entries.
- Sorted by `(vendor, value)`.
- Empty list when no identifier qualifies.
