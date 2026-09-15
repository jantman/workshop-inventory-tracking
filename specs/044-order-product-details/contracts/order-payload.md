# Contract: Amazon Order Payload, Review, Confirmation and Order Page

## 1. Agent → `/api/capture`: additions to each `lines[]` entry

The order payload stays `version: 1`, with vendor `Amazon`. Each line may now carry **one** of:

| Key | Type | When |
|---|---|---|
| `listing` | object: the single-listing payload `extract()` builds, `version` included | the line's `/dp/<ASIN>` was read (research.md §5) |
| `listing_problem` | string, one short sentence | it was not |

A line with neither key is what an older agent sends, and it reads exactly as it does today.

`listing_problem` values the agent produces:

- `"no item number on the order line"`
- `"the listing could not be fetched (HTTP 503)"`, or `(network error)`
- `"the listing now shows a different item (B0XXXXXXXX)"`
- `"the page was not a listing — Amazon may be asking to sign in or check for a robot"`

A server that does not know these keys ignores them, because `from_payload` reads only the keys it
names. So a new agent against an old server captures the order as today.

**Progress:** while it reads, the agent shows a fixed element `#workshop-capture-progress` on the
Amazon page, reading "Workshop capture: reading listing *i* of *n*…". It is removed before the
form submits.

## 2. The review (`order_review.html`), Amazon lines

- **A line carrying `listing`:** below its part number, `.line-listing-summary`:
  - *"Listing read: \<brand\> · N specification rows · M pictures · barcode found"*
  - Each segment appears only when non-empty. It is the same vocabulary as `capture.html`'s
    `#capture-summary`.
- **A line carrying `listing_problem`:** a `badge text-bg-warning .details-not-read`, *"details
  not read"*, with the reason as visible small text.
- **The `#order-page-detail-note`** is rewritten (FR-021). It carries `data-listings-read="<n>"`
  and `data-listings-missing="<m>"`, and says:
  - **All read:** *"Each new product will carry its listing's details. Products already in the
    catalog only gain what they lack — nothing they hold is overwritten; capture a listing on its
    own to review differences."*
  - **Some or none read:** additionally, *"\<m\> line(s) could not be read. After confirming, this
    order's page lists them with a link to each listing, where the capture bookmarklet adds the
    details without recording another purchase."*
- **Existing states** (NEW, MATCHED, CAPTURED, CONFLICT, same-purchase) and their controls are
  unchanged (FR-029).

## 3. Confirmation (`POST /products/amazon/orders/capture`)

1. `capture_order_lines(...)` runs, unchanged, apart from returning `line_products`.
2. For each `(form_key, product_id)` in `line_products` whose line has a `listing`:
   - `apply_listing_details(product_id, line.listing, proposed={manufacturer: listing.brand,
     manufacturer_part_number: listing.manufacturer_part_number()}, replace=∅)`
   - then `store_listing_images(product_id, listing.images, ...)`
   - A line whose product appears twice (two lines, one ASIN) is applied once.
3. `products_detailed` is the number of those calls whose result `changed_anything`.
4. The flash (`_order_capture_summary`) adds, inside the "wrote something" block:
   - *"Details added to N product(s)"*
   - *"M picture(s) stored"*, plus failures, in `_image_tally`'s wording
   - It replaces the old "carry only what the order page stated" sentence with: *"K product(s)
     still need details — see below"*, where K is the not-read lines' products still missing.
5. Redirect to the order page, as today (FR-019).

A failure in step 2 for one product is logged and counted as not detailed. It never un-writes the
order (FR-031).

## 4. The order page (`GET /products/orders/Amazon/<order_number>`)

These additions apply only when the vendor is Amazon:

- **`#details-progress` alert.** Either *"N of M products still need details. Open each listing
  and click the capture bookmarklet — it adds the details without recording another purchase."*
  or *"Every product on this order has its details."* (FR-016)
- **Per line, in a new "Details" column:**
  - `badge .details-captured`: *"captured"*, or
  - `badge .details-missing`: *"missing"*, plus `a.open-listing`
    (`href="https://www.amazon.com/dp/<ASIN>"`, `target="_blank"`, `rel="noopener"`), reading
    *"Open listing ↗"*. It is absent when the line has no ASIN.
- **The count is of distinct products**, not lines. Two lines naming one product count once.

For every other vendor the page is unchanged.

## 5. The product page (`GET /products/<id>`)

`#details-missing-notice` renders when the product carries an Amazon VENDOR identifier and has no
specification rows. It reads: *"This product has only what an order page stated. Open its listing
and click the capture bookmarklet to add pictures, specifications and barcodes."* It includes the
same `a.open-listing`.
