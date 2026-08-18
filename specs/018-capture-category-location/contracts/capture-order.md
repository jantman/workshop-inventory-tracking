# Contract: `CatalogService.capture_order`

**Module**: `app/catalog_service.py`

Three keyword parameters are added. All default to `None`, so every existing caller —
`product_capture`, `/api/capture`, and the tests — keeps working untouched (FR-004).

## Signature change

```python
def capture_order(
    self,
    vendor: str,
    vendor_item_id: Optional[str] = None,
    listing_title: Optional[str] = None,
    url: Optional[str] = None,
    unit_price: Optional[Any] = None,
    quantity: Optional[int] = None,
    order_date: Optional[datetime] = None,
    description: Optional[str] = None,
    manufacturer: Optional[str] = None,
    manufacturer_part_number: Optional[str] = None,
    acknowledged_duplicate_of: Optional[Any] = None,
    attach_to: Optional[Any] = None,
    listing: Optional[ListingCapture] = None,
    category_path: Optional[str] = None,     # NEW
    location: Optional[str] = None,          # NEW
    sub_location: Optional[str] = None,      # NEW
) -> Purchase:
```

## Parameter semantics

- **`category_path`** — where the operator files the product. Normalized and length-checked
  up front, alongside `unit_price` and `quantity`, so an over-length path is refused before
  any question is raised and before anything is written.
- **`location`** — the storage location. Stripped; blank is "not stated".
- **`sub_location`** — the bin or drawer. Stripped; blank is "not stated". Accepted with or
  without a `location`.

None of the three is ever populated from `listing`. `ListingCapture` carries no such field
and no fallback may be added (FR-013).

## Behaviour

| | Product is created | Product already exists |
|---|---|---|
| Value stated | Stored on the new product | **Overwrites** what the product held (FR-009) |
| Value blank | Column stays `NULL` (FR-003) | **Leaves the existing value alone** (FR-010) |

The existing-product rule matches `description`, which `capture_order` already writes through
to a matched product. It deliberately does **not** match `manufacturer` and
`manufacturer_part_number`, which are never written to an existing product because a mismatch
there is the evidence the recycled-identifier question depends on. Filing carries no such
evidential role.

## Raises

| Exception | When | State |
|---|---|---|
| `ValidationError` | Vendor missing; a price, quantity or date that will not parse; **a canonical category path longer than 512 characters** | Nothing written |
| `CaptureDecisionRequired` | Probable duplicate, or an item id already naming a product without corroboration | Nothing written — unchanged guarantee |

## Callers

| Caller | Change |
|---|---|
| `app/product/routes.py::product_capture` | Reads the three names off `request.form` and passes them straight through. No fallback, no default, no listing consultation. |
| `app/product/routes.py::/api/capture` | **None.** It does not pass the new parameters, so it keeps today's behaviour exactly. |

## Unchanged

`create_product`, `update_product`, `record_purchase`, `_apply_listing`,
`_promote_barcode_rows`, `find_product_by_identifier` and `_find_captured_purchase` keep their
current signatures and behaviour. `update_product`'s `editable` set already contains all three
field names and is not extended.
