# Contract: Set Category on Several Products

## `POST /api/products/category`

CSRF-protected (sent with `csrfFetch`).

### Request

```json
{ "product_ids": [12, 15, 15, 31], "category_path": "Tools / Hand" }
```

- `product_ids`: a non-empty list of integers. Duplicates are allowed and collapsed.
- `category_path`: a string, normalized as Edit Product normalizes it.

### Responses

| Status | Body | When |
|---|---|---|
| 200 | `{"success": true, "updated": 3, "category_path": "tools/hand"}` | Every product updated. A success flash is queued for the next page render. |
| 400 | `{"success": false, "error": "<message>"}` | Body not JSON, `product_ids` missing, empty or not integers, `category_path` missing, blank or too long. Nothing written. |
| 404 | `{"success": false, "error": "<message naming the missing ids>"}` | Any id does not exist. Nothing written. |

## UI contract (ids read by `bulk-set-category.js`)

| Id | Where |
|---|---|
| `#bulk-category-btn` | The Set Category button. On Products it is in the page actions. On order and outstanding pages it is in `_order_bulk_toolbar.html`. Disabled when nothing is ticked. |
| `#bulkCategoryModal` | The dialog (`_bulk_category_modal.html`). |
| `#bulk-category-summary` | "N products will be given this category." |
| `#bulk-category-input` | The category input, `list="bulk-category-suggestions"`. |
| `#bulk-category-suggestions` | The datalist, filled by `catalog-suggestions.js`. |
| `#bulk-category-error` | The error alert, hidden until a failure. |
| `#bulk-category-submit` | The confirm button. |
