# Contract: Product Move HTTP Interface

## `GET /products/move`

Renders the product Move page.

- Optional `?code=` takes a comma-separated list of internal codes. Elements are trimmed,
  empty ones are discarded, duplicates collapse, and each one is upper-cased.
- Each code that resolves to a product (INTERNAL identifier) is preselected. Anything else,
  including a value that is not shaped like a `WIT` code, is listed as rejected with
  `reason: not_found`. Nothing is silently dropped.
- Preselected codes render into `#preselected-section[data-ids]` exactly as the item page
  renders JA IDs.

The detail page's **Move** button links to `/products/move?code=<internal_code>`. The
button is shown only when the product has an internal code, and every product gets one when
it is created.

## `GET /api/products/by-code/<code>`

Looks up a single product by its internal code. Case-insensitive.

**200**
```json
{"success": true, "product": {"id": 7, "internal_code": "WIT0123456789", "description": "M3 nuts",
                              "location": "M2" , "sub_location": null, "...": "rest of to_dict()"}}
```

**404**: the value is not a `WIT` code, or no product carries it.
```json
{"success": false, "error": "No product carries the code WITXXXXXXXXXX"}
```

## `POST /api/products/batch-move`

The request matches `/api/inventory/batch-move`, except that each move is keyed by `code`.

```json
{"moves": [{"code": "WIT0123456789", "new_location": "M1-A", "new_sub_location": "Drawer 3"},
           {"code": "WIT9876543210", "new_location": "T-3", "new_sub_location": null}]}
```

**Per move**:
- A missing `code` or a blank `new_location` fails with "Missing product code or location".
- An unknown code fails with "Product not found".
- Otherwise `location` becomes the stripped `new_location`, and `sub_location` becomes the
  stripped `new_sub_location`. When `new_sub_location` is absent, null or blank, it becomes
  `NULL`.
- No other field changes.
- One failure does not stop the others.

**200**: response body (same shape as items):
```json
{"success": true, "moved_count": 2, "total_count": 2, "failed_moves": []}
```
When any move failed: `"success": false`, `"error": "N items failed to move"`, and
`failed_moves: [{"code": "...", "error": "..."}]`.

**400**: the body is missing `moves`, or `moves` is empty or not a list.
```json
{"success": false, "error": "Invalid request data" | "No moves provided"}
```

CSRF: the route is not exempt. The page sends `X-CSRFToken` from its hidden `csrf_token`
input, as the item page already does.

## `app/utils/batch_move.py` (shared by both batch-move routes)

```python
def parse_moves(data) -> list[dict]          # ValueError('Invalid request data' | 'No moves provided')
def destination(location: str, sub_location: str | None) -> tuple[str, str | None]
def batch_result(moved_count: int, total: int, failed: list[dict]) -> dict
```

Behaviour is byte-for-byte that of the current item route. `TestBatchMoveAPIWithSubLocation`
is the regression net.
