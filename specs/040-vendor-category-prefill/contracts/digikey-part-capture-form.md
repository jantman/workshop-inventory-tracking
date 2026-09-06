# Contract: The Single-Part DigiKey Capture Form

**Page**: `app/templates/product/digikey_part_review.html`
**Posts to**: `product.product_new` (POST) — the ordinary product-create route. This page writes
nothing itself; it fills in the one form that makes products.

## Fields posted

| Field | Kind before | Kind after | Note |
|---|---|---|---|
| `csrf_token` | hidden | hidden | Unchanged |
| `description` | visible, pre-filled with DigiKey's | visible, pre-filled with DigiKey's | Unchanged. The description is the label text and the operator's words beat DigiKey's, but DigiKey's is a defensible default and it is also kept as a specification row (024 FR-029) |
| `manufacturer` | hidden, from the part | hidden, from the part | Unchanged. A manufacturer is a fact about the part, not a statement about this workshop |
| `manufacturer_part_number` | hidden, from the part | hidden, from the part | Unchanged, same reason |
| `category_path` | **hidden, from the part** | **visible, empty** | **The change.** See below |
| `identifier_type` / `identifier_value` | hidden | hidden | Unchanged |
| `digikey_part_number` | hidden | hidden | Unchanged |
| `digikey_datasheet_url` / `digikey_photo_url` | hidden | hidden | Unchanged |
| `spec_name[]` / `spec_value[]` | hidden, repeated | hidden, repeated | Unchanged. DigiKey's category is *not* added as a specification row — that would move the problem into a second field rather than solve it |
| `location` | visible, empty | visible, empty | Unchanged |
| `sub_location` | visible, empty | visible, empty | Unchanged |

## The Category field, after

```html
<label for="category_path" class="form-label">Category</label>
<input type="text" class="form-control" id="category_path" name="category_path"
       maxlength="512" list="category-suggestions"
       placeholder="electronics/passives/resistors" value="">
<datalist id="category-suggestions"></datalist>
```

**The ids are a contract, not decoration.** `catalog-suggestions.js` fills
`#category-suggestions` by id on DOM ready; renaming either id silently switches the shop's own
category suggestions off, leaving a field that looks right and offers nothing. The markup above
matches `product/_classification_fields.html` exactly for that reason.

`value` is empty, always. It is never seeded from the part, from a previous capture, or from
anything else. If the operator types nothing, the product is created uncategorized.

## What the page still shows

DigiKey's category remains in the read-only "What DigiKey says" detail list:

```html
<dt class="col-5">Category</dt>
<dd class="col-7">{{ part.category_path or '—' }}</dd>
```

That is information about the vendor's catalog, presented as such, in a block that posts nothing.
Displaying it and recording it are different acts, and only the second one is removed.

## Invariants a test can hold this to

1. The rendered page contains no input named `category_path` carrying the part's category as its
   value — hidden or otherwise.
2. The rendered page contains exactly one input named `category_path`, it is visible, and its value
   is empty.
3. Submitting the form untouched creates a product whose `category_path` is empty.
4. Submitting the form with a typed category creates a product carrying that category.
5. The part's category is still present in the page's read-only detail list.
