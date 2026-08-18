# Contract: the capture confirmation form

**Route**: `GET|POST /products/capture` (`app/product/routes.py`, `product.product_capture`)

No route is added, removed or renamed. This is the POST field set, which gains three names.

## Fields added

| Name | Type | Required | Max | Notes |
|---|---|---|---|---|
| `category_path` | text | no | 512 after normalization | Backed by the `#category-suggestions` datalist. Typing a path that does not exist creates it (FR-006). Over-length is rejected, not truncated (FR-005). |
| `location` | text | no | 100 | Autocompleted from `GET /api/inventory/field-suggestions/location`. |
| `sub_location` | text | no | 100 | Autocompleted from `GET /api/inventory/field-suggestions/sub_location`, scoped by `?location=` from the `location` field's current value. |

All three are free-form: the suggestion lists never restrict what may be submitted (FR-008).
All three are optional and independent (FR-003).

## Fields unchanged

`csrf_token`, `listing`, `url`, `vendor`, `vendor_item_id`, `listing_title`, `description`,
`manufacturer`, `manufacturer_part_number`, `order_date`, `quantity`, `pack_price`,
`pack_size`, `unit_price`, `acknowledged_duplicate_of`, `attach_to`.

## Element ids (a contract, because JS binds by id)

| id | Bound by |
|---|---|
| `#category_path` + `<datalist id="category-suggestions">` | `catalog-suggestions.js` |
| `#location` + `<div id="location-suggestions">` | `field-autocomplete.js` auto-init |
| `#sub_location` + `<div id="sub_location-suggestions">` | `field-autocomplete.js` auto-init, `locationFieldId: 'location'` |

Renaming any of these silently disables the suggestions — the autocomplete skips a target
whose dropdown sibling is absent, and it does so without erroring.

## Responses

Unchanged in shape.

| Outcome | Response | The three fields |
|---|---|---|
| Capture succeeds | `302` → `/purchases/<id>/receive` | Written to the product |
| Duplicate or recycled-identifier question | `200`, `capture.html` re-rendered with `assessment` | Re-rendered with what the operator typed (FR-011) |
| `ValidationError` (incl. over-length category) | `200`, `capture.html` re-rendered with a flashed message | Re-rendered with what the operator typed (FR-011) |
| `GET` (incl. bookmarklet landing) | `200`, `capture.html` | Empty — nothing in a listing may fill them (FR-013) |

## Suggestion endpoints consumed

Both already exist, are already app-global, and are **not modified**:

- `GET /api/categories` → `{"success": true, "categories": [...]}`
- `GET /api/inventory/field-suggestions/<field>?q=&limit=&location=` →
  `{"success": true, "field": "...", "suggestions": [...]}` for `location` and `sub_location`

## Templates

`app/templates/product/_classification_fields.html` is new and is the single definition of
these three inputs. It is included by `_form_fields.html` (add/edit, via `values`) and by
`capture.html` (via `{% with values = form_data %}`). The markup must not be duplicated: the
shared partial is what makes the two pages' vocabularies provably the same one (FR-007,
FR-008).
