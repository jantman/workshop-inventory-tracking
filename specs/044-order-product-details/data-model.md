# Data Model: Capture Product Details for Products an Order Created

**No schema change.** No table, column, index or Alembic revision is added. Everything below is
either a derived reading of existing rows or an in-memory frozen dataclass in `app/models.py`,
following `CaptureAssessment`, `CandidatePurchase` and `ReviewedLine`. A template never holds an
ORM row across a closed session.

## Derived: a product's details status

| Reading | Rule |
|---|---|
| **captured** | the product has one or more `product_specifications` rows |
| **missing** | it has none |

- **Batch form:** `CatalogService.products_missing_details(product_ids) -> Set[int]`. One grouped
  query over `product_specifications` for the ids given, returning the ids with no row. Used by the
  order page.
- **Single form:** `not product.specifications` on a product the page has already loaded. Used by
  the product page, together with "carries an Amazon VENDOR identifier" (research.md §10).

research.md §2 explains why this is derived rather than stored, and the two edge readings it
accepts deliberately.

## New in-memory types (`app/models.py`)

### `ListingMatch` (frozen)

This is what a listing capture's item number matched, for the confirmation page. It is built by
`CatalogService.find_listing_match(vendor, vendor_item_id, url, order_date=None)`, which writes
nothing.

| Field | Type | Meaning |
|---|---|---|
| `product_id` | int | The product holding the VENDOR identifier `(vendor, vendor_item_id)` |
| `description` | str | Current value |
| `manufacturer` | Optional[str] | Current value |
| `manufacturer_part_number` | Optional[str] | Current value |
| `category_path` | Optional[str] | Current value |
| `location` | Optional[str] | Current value |
| `sub_location` | Optional[str] | Current value |
| `specifications` | tuple of `(name, value)` | Current rows, in display order |
| `order_purchase_id` | Optional[int] | An order-captured purchase *on this product* that `_find_captured_purchase` recognizes as possibly this capture (spec 033 window). None otherwise |
| `order_reference` | Optional[str] | That purchase's `supplier_order_reference` |
| `order_vendor` | Optional[str] | That purchase's vendor, for building the order address |

Derived properties:

- **`from_order`**: `order_purchase_id is not None`. When true, the confirmation page shows the
  collapsed message with details-only preselected (FR-009, FR-010).
- **`spec_differences(listing)`**: returns `(added, differing)`.
  - `added` is the listing's rows whose names the product does not hold, compared case-folded in
    Python, which is `merge_specifications`' rule.
  - `differing` is `(name, current, proposed)` for rows whose names match but whose values differ.
  - The listing's `description_text` counts as a row named `Description`, as `_apply_listing` treats
    it.

Returns None when the capture has no item id, or when no product holds it.

### `ListingDetailsResult` (frozen)

This is what `apply_listing_details` did, for the flash message.

| Field | Type |
|---|---|
| `product_id` | int |
| `fields_filled` | tuple of field names |
| `fields_replaced` | tuple of field names |
| `specifications_added` | int |
| `specifications_replaced` | int |

Property `changed_anything`: true if any of the four is non-empty or non-zero.

### `AmazonOrderLine`: two new fields

| Field | Type | Meaning |
|---|---|---|
| `listing` | Optional[`ListingCapture`] | The line's own listing, when the agent read it (US4) |
| `listing_problem` | str (default `''`) | Why it was not read, in the agent's words |

- Both are parsed in `from_payload` from the payload keys `listing` and `listing_problem`
  (contracts/order-payload.md).
- `listing` is built by a new `ListingCapture.from_data(dict)`, and `from_json` becomes
  `json.loads` followed by `from_data`, so there is one parser.
- An unreadable `listing` object yields `listing=None`. `listing_problem` then reads "the listing
  read was unusable" unless the agent gave a reason. It never refuses the line.

### `OrderCaptureResult`: two new fields

| Field | Type | Meaning |
|---|---|---|
| `line_products` | tuple of `(form_key, product_id)` | The product each written, adopted or already-captured line is on (research.md §6) |
| `products_detailed` | int | Set by the confirm route after `apply_listing_details`, not by the service. `wrote_anything` counts it |

- `products_detailed` is filled in after the fact with `dataclasses.replace`. The dataclass stays
  frozen, and `_order_capture_summary` still takes one result.

## State: a product's details, across this feature

```text
created by an order line ── missing ──┬── details-only capture (US1/US2) ──► captured
                                      ├── order re-capture with listing (FR-030) ──► captured
                                      └── order capture with listing read (US4) ──► captured
created by a listing capture ── captured (unchanged)
```

- Any path whose listing yielded no rows leaves the product **missing**. That is deliberate, see
  research.md §2.
- No path moves a product from captured back to missing. Rows are only removed by the operator's
  own edit form.

## Invariants this feature preserves

- **A details-only capture never creates, changes or deletes a `purchases` row.** It never writes
  `quantity`, `stock_status`, their dates or `reorder_threshold` (FR-002). `update_product`
  refuses those keys by construction (`app/catalog_service.py:644-653`).
- **Specification rows are only removed by the operator's edit form.** A replacement changes a
  value in place and keeps `display_order` (FR-005).
- **An order's purchases still write in one session or not at all** (`capture_order_lines`,
  unchanged apart from reporting `line_products`).
- **VENDOR identifiers still name at most one product per vendor.** Details-only never adds or
  moves a VENDOR identifier. GTINs are promoted through the existing `_promote_barcode_rows`, whose
  refusal rules are unchanged (spec 016 FR-006).
