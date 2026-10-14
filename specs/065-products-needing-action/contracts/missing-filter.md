# Contract: `missing` product-list filter

## Query parameter

`GET /products?missing=<value>` and `GET /api/products/search?missing=<value>`

| Value | Products returned |
|---|---|
| *(absent or empty)* | No narrowing (unchanged behavior) |
| `category` | `category_path` is NULL or blank |
| `location` | `location` is NULL or blank (sub-location ignored) |
| `either` | matches `category` OR `location` |
| anything else | Page: flash error listing valid values, empty list. API: `400 {"success": false, "error": ...}` |

Combines (AND) with `q`, `category`, `tag`, `stock`, `spec_name`, `spec_value`.

## Service

`CatalogService.search_products(..., missing: Optional[str] = None)` — raises
`ValidationError(field='missing')` for an unknown value.

## UI

- Filter form: `<select id="filter-missing" name="missing">` with options
  `""` Any, `category` No category, `location` No location, `either` Category or location;
  the current value is `selected`.
- Navbar: Products dropdown entry "Needs Action" with `href="/products?missing=either"`.
