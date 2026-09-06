# Contract: committing a typed count

**Feature**: 039-typed-quantity-entry

## The endpoint — unchanged

`PATCH /api/products/<int:product_id>/quantity` (`app/product/routes.py:2241`).

Request body:

```json
{ "quantity": 40 }
```

| `quantity` | Meaning | Result |
|---|---|---|
| a whole number `>= 0` | set the count to exactly this | `200`, count set, `quantity_updated_at` stamped |
| `null` | stop counting | `200`, count and its date cleared, reorder threshold cleared |
| absent | — | `400`, `"Request body must include \"quantity\"..."` |
| negative, fractional, or non-numeric | — | `400`, the `ValidationError` message |

Response on success: `{"success": true, "product": {...}}`. On refusal:
`{"success": false, "error": "<message>"}`.

**This feature sends no request the endpoint does not already accept.** `{"quantity": 40}` is
already valid; nothing has ever sent it. No route, service or validator changes.

### One value the client must never send

`{"quantity": ""}`. `CatalogService._validate_quantity()` maps `''` to `None`, so an empty string
would be read as **stop counting**. That mapping is correct for the product form, which posts `''`
for a blank field, and it is not being changed (`research.md` §2). The browser therefore refuses an
empty entry before it becomes a request.

## The client — `app/static/js/product-stock.js`

`StockControls` gains one commit path. Everything else in the class is untouched.

### Reading the entry

The typed value is read from `#quantity-input`. It is **not** read from `#quantity-value`;
`currentQuantity()` continues to parse that rendered text for the steppers only, and continues to
fall back to `0` when the text is a badge rather than a number.

### Validation, before any request is made

In order:

1. **Empty** (after trimming) —
   - from `#quantity-set-btn`: refused. Message names that a count is needed and that stopping is a
     separate button.
   - from `#start-tracking-btn`: **not** a refusal. Sends `{"quantity": 0}`, which is exactly what
     it sends today.
2. **Not a whole number** (non-numeric text, a decimal point, a sign that is not a leading `-`) —
   refused. Message names that the count must be a whole number.
3. **Negative** — refused. Message names that a count cannot be negative.
4. Otherwise — `PATCH` with `{"quantity": <the integer>}`.

### What a refusal does

- Writes the message into `#stock-alerts` through the existing `showAlert()`, producing
  `#stock-alert`.
- **Does not** reload the page, so the displayed count, the typed entry, and any correction the
  operator makes all survive (FR-008).
- **Does not** send a request, so nothing is stored and no count date is stamped.

### What a success does

- Reloads the page, as every other control on this card already does. The reloaded
  `#quantity-value` and `#quantity-age` are the observable completion signal.

### A server-side refusal

Reaches `showAlert()` by the class's existing `.then()` branch, unchanged. The client-side checks
are the fast path and the useful message; they are not the only guard.

## Behavioral equivalences that must hold after the change

| Action | Request sent | Same as today? |
|---|---|---|
| `+` on a count of 5 | `{"quantity": 6}` | yes |
| `−` on a count of 0 | `{"quantity": 0}` | yes — floored |
| "Start counting this", field untouched | `{"quantity": 0}` | yes |
| "Stop counting this" | `{"quantity": null}` | yes |
| "Start counting this", field reads `12` | `{"quantity": 12}` | new |
| "Set", field reads `40` | `{"quantity": 40}` | new |
| "Set", field reads `40`, count already 40 | `{"quantity": 40}` | new — and it re-stamps the date |
| "Set", field empty | *none* | new — refused locally |
