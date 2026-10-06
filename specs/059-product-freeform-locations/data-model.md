# Data Model: Free-Text Locations on the Product Move Page

There are no stored-data changes. A product's `location` and `sub_location` remain free text.

## Product page scan classification (state-dependent)

Precedence is unchanged: `>>DONE<<`, then product code (`id`), then JA ID (`foreign`), then location, then sub-location.

| State (`currentExpectedInput`) | Free text (e.g. `WoodshopShelf`) | Item-shaped (`M1-A`) |
|---|---|---|
| `id` | `sub_location` → refused (unchanged) | `location` → refused (unchanged) |
| `location` | **`location`** → accepted (was refused) | `location` → accepted |
| `bulk_location` | **`location`** → group queued (was refused) | `location` → group queued |
| `id_or_sub_location` | `sub_location` → accepted (unchanged) | `location` → "two locations in a row" (unchanged) |

The item page is unchanged: free text is always `sub_location`.
