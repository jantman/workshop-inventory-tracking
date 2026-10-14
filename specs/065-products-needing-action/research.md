# Research: Products Needing Action

## R1 — One select, not two checkboxes

- **Decision**: A single `missing` parameter with values `category`, `location`, `either`
  (empty = any).
- **Rationale**: Every other product-list filter ANDs with its neighbors. Two checkboxes
  "No category" + "No location" would read as AND (missing both), but the Needs Action view
  needs OR. An explicit `either` value removes the ambiguity and mirrors the `stock` select.
- **Alternatives**: Two boolean params plus a mode flag (more surface, no benefit); a
  separate `/products/needs-action` page (duplicates the list and its bulk actions).

## R2 — What counts as "missing"

- **Decision**: `IS NULL` or trimmed value equal to `''`, for both `category_path` and
  `location`. `sub_location` is ignored.
- **Rationale**: The service writes `None` for blanks (`_clean`, category canonicalization),
  but older rows or imports could hold `''`; treating both as missing is cheap and matches
  what the operator sees (an empty cell). A sub-location without a location is still not
  somewhere you can find the product.

## R3 — Unknown values

- **Decision**: Raise `ValidationError` naming the valid values, exactly as
  `_apply_stock_filter` does; the page flashes it and shows an empty list, the API returns 400.
- **Rationale**: Nearest existing code. Spec FR-008 was aligned to this.

## R4 — JSON API

- **Decision**: `/api/products/search` also accepts `missing`.
- **Rationale**: The page and API pass the same filter set today and an e2e test asserts they
  agree; leaving one out would make them drift. One line.

## R5 — Menu placement

- **Decision**: In the Products dropdown, directly after "All Products", label
  "Needs Action", icon `bi-exclamation-circle`, href `url_for('product.product_search', missing='either')`.
- **Rationale**: It is a view of the product list, so it sits beside it.
