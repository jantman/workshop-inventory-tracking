# Research: Bulk Set Category

## R1. Request shape: JSON fetch, not a form POST

- **Decision**: The dialog sends `csrfFetch('POST /api/products/category')` with JSON. On
  success it unticks every box and calls `window.location.reload()`. On failure it shows the
  error inside the dialog.
- **Rationale**: FR-011 requires a failed update to keep the selection. A plain form POST
  with a redirect, which is how Receive Selected works, loses the checkboxes on every outcome.
  With fetch and reload the selection survives a failure, and success still ends on a
  server-rendered page with fresh values and a flash. The boxes are unticked *before* the
  reload because Firefox restores checkbox state across a reload. Unticking first means the
  restored state is "nothing ticked". The reload keeps the query string, so the Products
  filters are kept (FR-010). `product-identifiers.js` and `product-attachments.js` already
  follow the same "fetch, then reload" pattern.
- **Alternatives**: (a) A form POST with `next` and a redirect. It is simpler, but it violates
  FR-011. (b) Patch the Category cells in place and show an inline alert. That means more JS
  and a page that disagrees with its own filter until reloaded.

## R2. Success message: `flash()` from the JSON route

- **Decision**: The API route calls `flash(..., 'success')` before returning JSON. The
  reload that follows renders it through `base.html` like any other flash.
- **Rationale**: This is the one message system the app has. The client needs no extra
  plumbing to carry a message across the reload.
- **Alternatives**: Pass the message in `sessionStorage` and render it in JS. That would be a
  second message system.

## R3. Validation: reuse `_validate_category_path`

- **Decision**: `set_category` calls `self._validate_category_path(category_path)`, which
  canonicalizes and rejects over-length input. A `None` result (blank) is refused with a
  `ValidationError`.
- **Rationale**: SC-002 requires bulk and Edit Product to store the same value for every
  input. Calling the same function makes that true by construction.

## R4. All-or-nothing and missing ids

- **Decision**: Within one `_session()`, load `Product` rows `WHERE id IN (ids)`. If any
  requested id is missing, raise `ItemNotFoundError` naming the missing ids. The context
  manager rolls back and nothing is written. Otherwise set `category_path` on each row.
  Ids are de-duplicated server side too.
- **Rationale**: This matches `receive_purchases` (062) and `rename_category`: check
  everything, then write, in one transaction.

## R5. Category suggestions in the dialog

- **Decision**: The modal input uses its own datalist, `#bulk-category-suggestions`, and
  `catalog-suggestions.js` fills it from `/api/categories` exactly as it fills
  `#category-suggestions`. All three pages load `datalist.js` and `catalog-suggestions.js`.
- **Rationale**: The Products page already has `#category-suggestions` for its filter, so
  reusing that id inside the modal would create a duplicate id. Edit Product uses this same
  datalist mechanism, so the dialog autocompletes "the way the Edit Product page does".

## R6. Where the selection logic lives

- **Decision**: `BulkSetCategoryDialog` (in `bulk-set-category.js`) owns the modal: open it
  with a list of product ids, submit, show an error, and on success call a `clearSelection`
  callback and then reload. The existing page scripts already own the selection. They enable
  or disable `#bulk-category-btn` in `onSelectionChange` and call `dialog.open(ids)` on
  click, passing the same distinct-product list they hand the label dialog.
- **Rationale**: It mirrors `BulkLabelPrintDialog` exactly. One selection model per page,
  and no second listener on the checkboxes.
