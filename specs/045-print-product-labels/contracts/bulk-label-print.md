# Contracts: Print labels for selected products

Three contracts matter here. Two are HTTP endpoints that **already exist and are not modified** —
they are documented because this feature's correctness depends on consuming them exactly as they
stand. The third is new and internal: the shared dialog's interface between the two pages that use
it.

---

## 1. `GET /api/labels/types` — unchanged

`app/main/routes.py:1877`. The single source of the label stocks, read by every print dialog in the
app.

**Response 200**

```json
{
  "success": true,
  "label_types": [
    "Sato 1x2", "Sato 1x2 Flag",
    "Sato 2x4", "Sato 2x4 Flag",
    "Sato 4x6", "Sato 4x6 Flag"
  ]
}
```

**Why it matters here**: SC-006 requires the products list and the items list to offer the same
stocks. Both read this endpoint, so they agree by construction. Neither page may hardcode a stock
list.

---

## 2. `POST /api/products/<int:product_id>/label` — unchanged

`app/product/routes.py:2560`. CSRF-protected (no `@csrf.exempt`), so callers must go through
`window.csrfFetch`, which `base.html` loads globally.

**Request**

```json
{ "label_type": "Sato 2x4", "label_count": 3 }
```

- `label_type` — required, must be a key of `LABEL_TYPES`. Otherwise `400` with
  `"Invalid label type. Available types: [...]"`.
- `label_count` — optional, defaults to `1`. Must be a non-boolean `int` in `1..99`. Otherwise `400`
  with `"label_count must be a whole number"` or `"label_count must be between 1 and 99"`.

**Response 200**

```json
{
  "success": true,
  "message": "3 labels printed for Carbon film resistor, 10k",
  "product_id": 42,
  "code": "P000042",
  "label_type": "Sato 2x4",
  "label_count": 3
}
```

**Response 400 / 404 / 500**

```json
{ "success": false, "error": "..." }
```

**Why it matters here**:

- FR-009 (bulk labels identical to single-product labels) holds because this is the *same* endpoint
  the product detail page posts to. There is no second composition path to keep in sync.
- FR-008 (a reprint reflects an edit) holds because the endpoint composes from the stored record on
  every call.
- The copy count is applied server-side as `num_copies`, so one product's copies are **one** print
  job with one exit code — which is why a failed product contributes zero labels to the reported
  total rather than a partial figure.

**One request per selected product.** There is no batch form of this endpoint and this feature does
not add one.

---

## 3. `BulkLabelPrintDialog` — new, internal

`app/static/js/bulk-label-print.js`. A plain global class (not an ES module) for the same reason
`label-count.js` documents: `inventory-list.js` is loaded with `type="module"` while the products
page script is a plain script, and a global is readable from both.

### Construction

```js
new BulkLabelPrintDialog({
  modalId:    'listBulkLabelPrintingModal',   // the modal element's id
  prefix:     'list-bulk',                    // every other element is `${prefix}-...`
  noun:       'item',                         // singular, for user-visible strings
  nounPlural: 'items',
  printOne:   (entry, labelType, labelCount) => Promise<Response>
})
```

`printOne` is the only behaviour that differs between callers. It receives one `Entry` and returns
the `fetch`/`csrfFetch` promise; the dialog interprets `response.ok` and reads `{error}` from the body
on failure. It must not catch its own errors — a rejected promise is reported as that entry's
failure and the run continues.

### Methods

| Method | Contract |
|---|---|
| `init()` | Wires the stock `<select>`'s change, the print button's click, and the modal's `hidden.bs.modal`. Called once on page load. Tolerates the elements being absent. |
| `open(entries)` | `entries` is `[{id, label}]`. Fills the summary and the selected-things list, loads the stocks if not already loaded, resets to `idle`, shows the modal. Async. |
| `reset()` | Returns the dialog to `idle`: stock cleared, count `1`, progress and error regions hidden and emptied, progress bar back to 0% and re-animated, print button shown and disabled, Done hidden, Cancel shown. |
| `printAll()` | Runs the selection. Async. |

### Element ids the dialog reads

Given `prefix`, every one of these must exist — which the Jinja macro guarantees:

```
${prefix}-print-summary      ${prefix}-label-items-list
${prefix}-label-type         ${prefix}-label-count
${prefix}-print-progress     ${prefix}-print-progress-bar     ${prefix}-print-status
${prefix}-print-errors
${prefix}-print-all-btn      ${prefix}-print-done-btn         ${prefix}-print-cancel
```

### User-visible strings

Parameterized by `noun`/`nounPlural` and **otherwise byte-identical to what the inventory list emits
today**. The inventory list's E2E suite asserts these, so they are a contract, not a detail.

| Moment | String |
|---|---|
| Summary on open | `You have selected N {noun}(s) to print labels for.` |
| Progress, count 1 | `Printing i of N: {entry.label}` |
| Progress, count > 1 | `Printing i of N: {entry.label} (C labels)` |
| Completion | `Complete: L labels for A {nounPlural}, F failed` (singular `label` / `{noun}` when the respective number is 1) |
| Failures | `Warning: F label(s) failed to print:` then `• {entry.label}: {reason}` per line |
| Refused count | `Warning: Label count must be a whole number between 1 and 99` |

### Invariants

1. **The count is read before anything prints.** A refused count shows the warning, prints nothing at
   all — not even the first entry — and leaves the dialog otherwise untouched (FR-007). The error
   region therefore lives *outside* the progress region in the markup, because it must be able to
   appear before a run has begun.
2. **A stale warning is cleared at the start of every run**, so a refusal's message cannot sit above
   a subsequent success line.
3. **One failure never aborts the run** (FR-011). Every remaining entry is still attempted.
4. **The reported total is `successCount * labelCount`** — a failed entry contributes zero, never a
   partial figure (see contract 2).
5. **The stock is remembered across opens within a page; the count is not.** The count resets to `1`
   because the modal node is reused rather than recreated.

---

## 4. Jinja macro `bulk_label_modal` — new, internal

`app/templates/_bulk_label_modal.html`.

```jinja
{% from "_bulk_label_modal.html" import bulk_label_modal %}
{{ bulk_label_modal('listBulkLabelPrintingModal', 'list-bulk', 'item', 'items') }}
{{ bulk_label_modal('productBulkLabelPrintingModal', 'product-bulk', 'product', 'products') }}
```

**Contract**: emits exactly the element ids listed in contract 3 for the given `prefix`, and a modal
whose id is `modal_id`. It exists so that the ids the shared JS reads and the ids the templates write
are one fact rather than two.

**Compatibility requirement**: called with `('listBulkLabelPrintingModal', 'list-bulk', 'item',
'items')`, it must render markup indistinguishable — in ids, classes, and visible text — from the
block currently inline at `app/templates/inventory/list.html:199-266`. That page's E2E suite is the
check.
