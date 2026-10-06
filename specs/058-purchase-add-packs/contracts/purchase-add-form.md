# Contract: Record a Purchase form (`POST /products/<id>/purchases/new`)

## Fields added

| Name / id | Label | Type | Default |
|---|---|---|---|
| `packs` | Packs Bought | number, min 1, step 1 | `1` |
| `pack_price` | Paid for the Pack | text, `inputmode=decimal` | empty |
| `pack_size` | Units in the Pack | number, min 1, step 1 | `1` |

Plus `#unit-price-inexact` and `#unit-price-error` notes under Unit Price. The page loads
`js/pack-unit-price.js`. These are the same ids, names, labels and defaults as `capture.html`.

## Server behaviour

`CatalogService.record_purchase_with_pack(product_id, packs, pack_size, pack_price, quantity,
unit_price, **other record_purchase fields)`:

1. `pack_count = _validate_pack_size(pack_size)` (blank → 1; `0` or non-integer → `ValidationError`).
2. `paid = _validate_price(pack_price)`.
3. `count = _validate_purchase_quantity(quantity)`, `price = _validate_price(unit_price)`.
4. When `pack_count > 1`:
   - If `count is None`, it becomes `(_validate_purchase_quantity(packs) or 1) * pack_count`.
   - If `paid is not None` and `price is None`, it becomes `_validate_price(paid / pack_count)`.
5. `record_purchase(..., quantity=count, unit_price=price, **_pack_fields(self, pack_count, paid))`.

Steps 4 and 5 are the helper `_apply_pack`, shared with `capture_order`, which also passes
its rendered defaults.

## Writer added to the 046 pack-column contract

| Writer | Source | Notes |
|---|---|---|
| `record_purchase_with_pack` (Record a Purchase) | The form's `pack_size` and `pack_price`, as typed by the owner | Only when pack size ≥ 2 and a pack price is given. Otherwise both stay NULL, so a hand purchase with no pack is unchanged |
