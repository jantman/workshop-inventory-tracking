# Data Model: Capture McMaster Variant Product Pages

No stored entity changes. What changes is which addresses are recognized.

## McMaster product address

| Shape | Example | Page kind | Part number |
|---|---|---|---|
| `/<part>/` | `/91290A115/` | `mcmaster-product` | the address's (unchanged) |
| `/<part>-<part>/` | `/3408A521-3408A523/` | `mcmaster-product` | the page's displayed number if it is one of the two, else the first |

`<part>` is unchanged: `\d{1,5}[A-Z][0-9A-Z]{0,6}` — digits, an upper-case letter, then
alphanumerics.

Still **not** product pages: `/products/<part>/` (family table), `/order-history/`,
`/order-history/order/<id>`, `/`, and any hyphenated path that is not exactly two part
numbers (`/91290A115-/`, `/91290A115-91290A116-91290A117/`, lower-case).

The server's `_mcmaster_part_from_url` answers the first part number for the two-part
shape; it has no page to consult.
