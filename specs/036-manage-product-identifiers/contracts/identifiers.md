# Contracts: Manage Product Identifiers After Creation

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Date**: 2026-09-02

Two contracts matter here, and only one of them is new.

1. **The HTTP contract** already exists and this feature **consumes it unchanged**. It is
   documented here because the browser code has to handle every branch of it, including two
   different JSON shapes, and because the unit tests pin it.
2. **The DOM contract** is new: the ids, classes and data attributes the templates owe the
   e2e tests.

---

## 1. HTTP — consumed as-is, not modified

### `POST /api/products/<product_id>/identifiers`

`app/product/routes.py:2392`. CSRF-protected; call it through `csrfFetch`.

**Request** — `Content-Type: application/json`

```json
{ "id_type": "GTIN", "value": "687117723741", "vendor": null, "override": false }
```

| Field | Required | Notes |
|---|---|---|
| `id_type` | yes | One of `OPERATOR_IDENTIFIER_TYPES`. |
| `value` | yes | As typed. The server normalizes. |
| `vendor` | for `VENDOR`/`DISTRIBUTOR` | Omitted or `null` elsewhere. |
| `override` | no | `true` only when the operator ticked the box. |

**Responses**

| Status | Body | Meaning | Requirement |
|---|---|---|---|
| `201` | `{"success": true, "identifier": {...}}` | Stored. `identifier.value` is the **normalized** value. | FR-005, FR-012 |
| `201` | `{"success": true, "identifier": {...}}` | The product already had this exact identifier; the existing row is returned and nothing is duplicated. Indistinguishable from a fresh add by design. | FR-010 |
| `400` | `{"success": false, "error": "..."}` | Empty value, unknown type, missing vendor, bad check digit without override, or an all-zero no-read. | FR-006, FR-007, FR-008, FR-011 |
| `409` | `{"success": false, "error": "...", "owning_product_id": N}` | Another product holds this value. | FR-009 |
| `404` | `{"success": false, "message": "...", "error_code": "...", ...}` | No such product. **Note the key is `message`, not `error`** — this one comes from the central handler, not the route. | FR-019 |

### `DELETE /api/products/<product_id>/identifiers/<identifier_id>`

`app/product/routes.py:2420`. CSRF-protected.

| Status | Body | Meaning | Requirement |
|---|---|---|---|
| `204` | *(empty)* | Removed. | FR-016 |
| `404` | `{"success": false, "message": "...", ...}` | Not on this product — including "already removed". **Treat as success.** | FR-018 |

Since #132 closed, this 404 is a real JSON 404 rather than a 302 to `/inventory`, so
`response.ok || response.status === 404` is a live branch and not a coincidence.

### Not part of this feature's contract

No endpoint is added, renamed or changed. `app/api_client.py` is untouched, so its `__all__`
surface is unaffected.

---

## 2. DOM — what the templates owe the tests

### Existing, unchanged

| Selector | What it is |
|---|---|
| `#internal-code` | The internal code. Must gain **no** remove control (FR-014). |
| `#identifier-list` | The `<ul>` of non-internal identifiers. |

### New

| Selector | Element | Purpose |
|---|---|---|
| `#identifier-alerts` | `<div>` | Where refusals are rendered. Empty on load. FR-011. |
| `#add-identifier-btn` | button | Toggles the form open (`data-bs-toggle="collapse"`). |
| `#add-identifier-form` | collapse container | Holds the four inputs below. |
| `#new-identifier-type` | `<select>` | Options from `OPERATOR_IDENTIFIER_TYPES`, in enum order, `INTERNAL` absent. FR-003. |
| `#new-identifier-value` | `<input type="text">` | `maxlength="128"`, matching the column. |
| `#new-identifier-vendor` | `<input type="text">` | `maxlength="200"`. |
| `#new-identifier-override` | `<input type="checkbox">` | The explicit opt-in. FR-006. |
| `#save-identifier-btn` | button | Submits. |
| `.identifier-row` | `<li>` | One per non-internal identifier — the count the e2e tests assert on. |
| `.identifier-value` | element | The stored value, for asserting normalization. |
| `.remove-identifier-btn` | button | One per row, carrying `data-identifier-id`. FR-013. |

**Constraints on the markup**

- The card lives in the narrow right-hand column. At a 390px viewport the page must not scroll
  sideways — `tests/e2e/test_touch_readiness.py:145` asserts this globally, so a wide row or a
  non-wrapping input fails an existing test rather than a new one.
- The `<select>` is rendered from the passed `identifier_types`, never from a literal.
- The form is inside the card, not a modal, and its collapse is markup-driven — no JS toggle.

### Behavior the JS owes

| Event | Behavior |
|---|---|
| Save, success | `window.location.reload()`. |
| Save, refusal | Render the message into `#identifier-alerts`; **do not** reload; leave the inputs as typed. |
| Save, 409 | Render the message plus a link to `/products/<owning_product_id>`. |
| Save, 404 | Render `data.message` (not `data.error`, which is absent). |
| Remove, clicked | `window.confirm(...)` first; a decline does nothing at all. |
| Remove, `ok` or `404` | `window.location.reload()`. |
| Remove, anything else | Render a message; do not reload. |

### Message reading

```js
const message = data.error || data.message || 'Could not add that identifier';
```

Both keys, in that order. The route's own refusals use `error`; the central handler's 404 uses
`message`. Reading only one shows the operator `undefined` in the other case — see
research [D4](../research.md).
