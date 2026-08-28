# Contract: The Vendor Capability Matrix

**Feature**: 030-product-docs-refresh | Satisfies spec FR-009 through FR-017

What the user manual's summary, the README bullet and the troubleshooting guide must agree on. Established from the code — see `research.md` §2 for the file and line behind each cell.

## The matrix

| | **Amazon** | **DigiKey** | **McMaster-Carr** | **Any other site** |
|---|---|---|---|---|
| **Whole order** | Bookmarklet, on the order's own page in *Your Orders* | *Products → Capture a DigiKey Order*, by sales order number | Bookmarklet, on the order page | Not supported |
| **One item, page read** | Yes — price, brand, description, *About this item*, every *Product information* row, every image the page names | Not by page read; the part lookup below is better | Yes — title, price, pack size, specifications, images | No |
| **One item, address only** | Yes; the ASIN comes out of the `/dp/` path | Yes | Yes; the part number comes out of the path | Yes — the address and a vendor name, nothing more |
| **Detail backfill** | No | Yes — manufacturer, category, datasheet, photograph, parametric specifications | No | No |
| **Configuration needed** | None | `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, `DIGIKEY_ACCOUNT_ID` | None | None |

## The four capabilities, defined

The summary must distinguish these; collapsing any two is the failure mode this contract exists to prevent.

1. **Whole-order capture** — one action records every line of an order as an outstanding purchase.
2. **Single-item capture that reads the page** — the bookmarklet runs against the listing in front of you and brings back what the page states.
3. **Single-item capture from the address alone** — the paste-a-URL form. Works for anything; brings back what the *address* yields and nothing off the page. Only the vendor name, an Amazon ASIN and a McMaster part number are derived from a URL (`app/product/routes.py:869-876,894,929`); a listing title is not, and must not be claimed for this row.
4. **Detail backfill** — the application fetches part detail from the vendor and writes it into the catalog, both when cataloging a part on its own and when filling gaps on a product an order line matched. A value the operator has already set is never overwritten.

## Where DigiKey's backfill happens

Both places, named:

- *Products → Capture a DigiKey Part* — a DigiKey part number, a manufacturer part number, or a product-page address yields a filled-in product.
- An order line that **matched** a product already in the catalog — the same detail fills that product's blanks, gaps only.

## The vendor-name table, stated as what it is

An address is turned into a vendor name from a closed list: **Amazon, DigiKey, Mouser, eBay, McMaster-Carr, AliExpress**. Any other host becomes the vendor name verbatim.

**Mouser, eBay and AliExpress appear here and nowhere else.** Being listed buys a tidier name than the bare host and nothing else: no reader is written for their markup, so they get what an unlisted site gets — the general reader on the bookmarklet path, and no page read at all on the paste-a-URL path. The summary must not let a reader infer more than that, and must not overstate it as "no reading of any kind" either. This is the sentence most likely to be written wrongly, and FR-013 exists for it.

## Required statements

- **FR-014**: DigiKey is the only vendor requiring configuration; without it, both DigiKey screens say so and everything else works. Link to the deployment guide's DigiKey entry.
- **FR-011**: The page reader is written against Amazon's markup and is what runs on an unrecognized page too, so an unrecognized site yields roughly its title and address — not a failure, just less.
- **FR-015**: The README names the vendors for all three capture capabilities and for backfill, and links to this summary in the manual rather than repeating it.
- **FR-017**: The troubleshooting guide's capture diagnosis names the same vendors and the same capabilities. A thin capture from a page-read vendor is the documented signal that the vendor changed their markup; a thin capture from any other site is the expected result.

## Vendor names are literal

`Amazon`, `DigiKey`, `McMaster-Carr` — as the application spells them, because it compares those strings and files purchases under them. Not "Digi-Key", not "McMaster".
