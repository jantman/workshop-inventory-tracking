# Contract: `POST /api/products/<int:product_id>/label`

`app/product/routes.py :: api_print_product_label`. Additive change — every request that works
today continues to work and to mean the same thing.

## Request

```json
{
  "label_type": "Sato 2x4",
  "label_count": 5
}
```

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `label_type` | string | yes | — | Must be a key of `LABEL_TYPES`. Unchanged. |
| `label_count` | integer | **no** | `1` | **New.** 1–99 inclusive. Whole numbers only. |

CSRF token as today, supplied by `csrfFetch`.

### `label_count` validation

Mirrors the item label endpoint's rules and messages exactly:

| Input | Result |
|-------|--------|
| absent | 1 label, current behaviour |
| `1` … `99` | that many labels |
| `0`, `100`, `-1` | `400`, `"label_count must be between 1 and 99"` |
| `2.5`, `"3"`, `null` | `400`, `"label_count must be a whole number"` |
| `true` | `400`, `"label_count must be a whole number"` — `bool` is an `int` in Python and is rejected explicitly |

A rejected request prints nothing.

## Responses

### 200

```json
{
  "success": true,
  "message": "Label printed for Blue widget",
  "product_id": 11,
  "code": "WIT0000000011",
  "label_type": "Sato 2x4",
  "label_count": 5
}
```

`label_count` is new in the response, echoing what was printed. `message` is unchanged for a count
of 1; for a count above 1 it names the count, following the item endpoint's convention of
pluralising the confirmation.

### 400 — bad `label_type` (unchanged) or bad `label_count` (new)

```json
{ "success": false, "error": "label_count must be between 1 and 99" }
```

### 404 — unknown product (unchanged)

### 500 — printing failed (unchanged)

## What the label now carries

Composed from the stored record at request time, so a reprint after an edit reflects the edit
(FR-008, unchanged behaviour):

- the product description,
- **the manufacturer and manufacturer part number, when present** (new),
- the most recent purchase's vendor, order date, and **unit price marked `ea`** (the marker is new),
- the Code128 symbol and the human-readable code, at no less than their current size.

## UI

`app/templates/product/detail.html` — the product label modal gains a number input
(`#product-label-count`, `min=1 max=99 step=1 value=1`), matching the item label modal's control.

`app/static/js/product-label-modal.js` — reads that input and includes `label_count` in the POST
body. The stock choice continues to be remembered in `localStorage`; **the count is not
remembered** — it is per-job, and a remembered 20 would be a nasty surprise on the next print.
