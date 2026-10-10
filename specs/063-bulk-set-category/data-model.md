# Data Model: Bulk Set Category

No schema change.

## Product (existing, `products`)

| Field | Change |
|---|---|
| `category_path` | Set to the canonical form of the entered category on every selected product. |

No other column on `products`, and nothing on `purchases`, is written.

### Validation (same as Edit Product)

- Canonicalized by `category_utils.canonical`: segments trimmed and lowercased, empty
  segments dropped, joined with `/`.
- A canonical result of `None` (blank, whitespace, bare `/`) is **refused**. It is not stored
  as "no category".
- Longer than `MAX_CATEGORY_PATH_LENGTH` (512) is refused.

### Selection → products

- On the Products page, each ticked row names one product id.
- On an order page or Outstanding Products, each ticked line names its `product_id`. Lines
  with no product have no checkbox. Repeated product ids collapse to one.
