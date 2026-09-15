# Contract: Details-Only Capture and the Confirmation Page

This covers the single-listing confirmation page (`app/templates/product/capture.html`), the two
routes that render and submit it, and the service methods behind them.

## 1. When the "What should this capture do?" block renders

The block renders whenever the page's context holds a `match` (a `ListingMatch`). The page gets
one from:

| Render | Where `match` comes from |
|---|---|
| Bookmarklet landing: `POST /api/capture`, form body without `order` | `find_listing_match(vendor, vendor_item_id, url)` when the payload names an item id |
| Re-render after `CaptureDecisionRequired` or `ValidationError`: `POST /products/capture` | The same call, with the form's `order_date` |
| `GET /products/capture` (paste form, empty) | Never. No item is known yet |

A JSON body to `/api/capture` is unchanged. It never takes the details path.

## 2. Form fields (all posted to `POST /products/capture`)

| Field | Values | Meaning |
|---|---|---|
| `intent` | `purchase` (default when absent) \| `details` | What the capture does |
| `details_product_id` | int | The product `match` named; required when `intent=details` |
| `replace` | repeated; `description`, `manufacturer`, `manufacturer_part_number`, `category_path`, `location`, `sub_location`, or `spec:<name>` | The values the operator chose to replace (FR-004). Absent means keep |
| `return_order` | an order reference | Present when `match.from_order`. Only the details path reads it |
| `acknowledged_duplicate_of` | int | Existing field. In collapsed mode it is rendered **hidden**, set to `match.order_purchase_id` |
| `attach_to` | product id \| `new` | Existing field. In collapsed mode it is rendered **hidden**, set to `match.product_id` |

- **`intent` absent** is today's request exactly. That keeps every existing test and the JSON body
  on the old path.
- **In collapsed mode the hidden answers are inert for `intent=details`** and are exactly the
  operator's answers for `intent=purchase`. `capture_order` then raises no question, and no
  JavaScript is needed.

## 3. What the page shows

**Collapsed mode** (`match.from_order`) replaces both `#duplicate-warning` and
`#identifier-warning` with one block, `#order-item-match`:

> **This is the item from order `<order_reference>`** — *\<product description\>*.
> ( • ) Add the listing's details to it — don't record a purchase   `#intent-details`
> (   ) I bought it again — record a separate purchase of it          `#intent-purchase`
> *Recording a separate purchase adds a second purchase of this item alongside the one order
> `<ref>` recorded.* (FR-011, always visible)

**Plain mode** (a match with no order purchase) renders `#listing-match` above the existing
warnings:

> **This listing is *\<product description\>*, already in the catalog.**
> ( • ) Record a purchase of it   `#intent-purchase`
> (   ) Update its details only — don't record a purchase   `#intent-details`

The existing `#identifier-warning` gains a consequence sentence on its `#attach-new` option
(FR-013): *"The new product will not carry item `<id>`, so later captures will not find it, and
`<existing>` keeps its current details."*

**Show-and-choose** is rendered in both modes and applies only when details-only is chosen, which
its heading says:

- **Scalar fields.** Under each of description, manufacturer, part number, category, location and
  sub-location, when `match` holds a value: *"Currently: X"* and a checkbox `replace=<field>`,
  unticked (`.replace-current`).
- **Specification rows.** `#spec-differences` is a table with one row per `differing` entry: name,
  current value, listing's value, and a checkbox `replace=spec:<name>`, unticked. Above it, a count
  of `added` rows: *"N rows will be added."*
- **Nothing new.** When `added` is empty, `differing` is empty, and no scalar proposal would fill a
  blank or differ, the page shows `#nothing-new`: *"The listing has nothing this product does not
  already hold."* (FR-007)

## 4. The details path in `product_capture`

When `intent=details`:

1. Resolve `listing`, `manufacturer`, `unit_price` and `manufacturer_part_number` exactly as
   today. The listing fills absent fields.
2. `service.apply_listing_details(details_product_id, listing, proposed={description, manufacturer,
   manufacturer_part_number, category_path, location, sub_location}, replace=set(form.getlist('replace')))`.
3. On `ValidationError` (an over-length value, a product that no longer exists), re-render with
   the flash, as the purchase path does. Nothing is written.
4. On success, flash the result:
   - *"Details updated: filled manufacturer, part number; 12 specification rows added; 1
     replaced."*
   - or *"Nothing new to add."*
   - The barcode tally is added (`describe_captured_barcodes`), unchanged.
5. `store_listing_images(details_product_id, listing.images, ...)` and its tally, unchanged.
6. Redirect:
   - `return_order` present: `_order_url(vendor, return_order, highlight=vendor_item_id)`.
   - Otherwise: `product.product_detail`.

No purchase is created on this path, at any step.

## 5. Service methods

```text
find_listing_match(vendor, vendor_item_id, url=None, order_date=None) -> Optional[ListingMatch]
    Read-only. Product by VENDOR identifier. The order purchase is _find_captured_purchase's
    result, kept only when it carries a supplier_order_reference and sits on that same product.

apply_listing_details(product_id, listing, proposed=None, replace=frozenset()) -> ListingDetailsResult
    Scalars: fill blank; replace only if named. Rows: add absent; replace only if 'spec:<name>'
    named. Then _promote_barcode_rows over the rows added or replaced. Never touches purchases,
    quantity, stock or reorder threshold. Validates every proposed scalar before writing anything.
    Raises ItemNotFoundError / ValidationError.

products_missing_details(product_ids) -> Set[int]
    Read-only. The ids among those given with no specification row.
```
