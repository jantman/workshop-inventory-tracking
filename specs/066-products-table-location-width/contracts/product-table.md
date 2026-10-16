# UI Contract: Product list table (`/products`)

Applies to every request to `/products`, with or without `q`, `category`, `tag`,
`stock`, `spec_name`, `spec_value`, `missing`.

## Page width

- `<main>` carries `container-fluid` on this page (all other pages keep `container`).
- At a 1920×915 viewport, `#product-table` is ≥ 1800px wide.

## Columns (`#product-table thead th`, in order)

| # | Header | Cell content |
|---|---|---|
| 1 | (select-all checkbox) | row checkbox `.product-checkbox` |
| 2 | Description | link + tag badges (`td.product-description`) |
| 3 | Manufacturer | manufacturer or empty |
| 4 | Category | `td.product-category`: category path or empty |
| 5 | Location | `td.product-location`: location or empty |
| 6 | Sub-location | `td.product-sub-location`: sub-location or empty |
| 7 | Quantity | `td.product-quantity` (unchanged rendering) |

## Empty state

`td#no-products` has `colspan="7"` and text "Nothing here matches."
