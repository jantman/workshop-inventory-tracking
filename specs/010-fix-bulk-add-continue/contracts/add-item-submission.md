# Contract: `POST /inventory/add`

**Status for this feature: unchanged.** This document records the existing contract so the client
change can be checked against it, and so the one genuinely surprising property — the response type
depends on a *request field* — is written down somewhere. No field is added, removed, or
reinterpreted by feature 010.

Handler: `inventory_add()`, `app/main/routes.py:550`.

## Request

`Content-Type: application/x-www-form-urlencoded`, submitted by `#add-item-form`
(`app/templates/inventory/add.html:30`).

### Fields that govern control flow

| Field | Required | Values | Meaning |
|-------|----------|--------|---------|
| `quantity_to_create` | no (defaults to `"1"`) | integer 1–100 | Selects the response type. `1` → redirect; `> 1` → JSON. Outside the range → 400. |
| `submit_type` | no | `add` \| `continue` | Where to send the user after a **single-item** success. **Consulted only when `quantity_to_create == 1`** (`routes.py:601`); the bulk branch returns at `routes.py:577` before reading it. Absent or any other value is treated as `add`. |

`submit_type` reaches the server through a hidden field rather than the pressed button's
`name`/`value`, because the quantity-1 path submits via `form.submit()`, which is programmatic and
carries no submitter. Feature 010 changes that hidden field from one created per submission to one
declared in the template — the wire format is identical.

### Item fields

Required: `ja_id` (`JA######`), `item_type`, `shape`, `material`, `location`. `material` must
match the taxonomy case-insensitively.

Optional: `sub_location`, `notes`, `vendor`, `vendor_part_number`, `purchase_location`,
`purchase_date`, `purchase_price`, `length`, `width`, `thickness`, `wall_thickness`, `weight`,
`thread_series`, `thread_handedness`, `thread_size`, `active`, `precision`.

Also carried: `csrf_token` (a hidden field inside the form, so it rides along in the `FormData`
built for the AJAX path without special handling).

For `quantity_to_create > 1`, the submitted `ja_id` acts as a **floor**, not as the literal first
ID: the server allocates from `max(get_max_ja_id_number() + 1, int(ja_id[2:]))` and assigns
sequentially (`routes.py:314-329`).

## Responses

### `quantity_to_create == 1` — redirect

| Outcome | Status | Location | Flash |
|---------|--------|----------|-------|
| Success, `submit_type == "continue"` | 302 | `/inventory/add` | `Item added successfully!` |
| Success, otherwise | 302 | `/inventory` | `Item added successfully!` |
| Validation failure | 400 | — | JSON body `{"success": false, "error": "..."}` |
| Persistence failure | 302 | `/inventory/add` | `Failed to add item. Please try again.` |

### `quantity_to_create > 1` — JSON

| Outcome | Status | Body |
|---------|--------|------|
| All created | 200 | `{"success": true, "count": N, "ja_ids": [...], "message": "Successfully created N items: JA000101 - JA000106"}` |
| Some created | 500 | `{"success": false, "count": M, "ja_ids": [...], "error": "Created M of N items. Some items failed."}` |
| None created | 500 | `{"success": false, "error": "Failed to create any items"}` |
| Validation failure | 400 | `{"success": false, "error": "..."}` |

Note the partial case returns **500 with a populated `ja_ids`**. Callers must read `ja_ids`
even on a non-2xx response; treating any error status as "nothing happened" would understate what
was recorded. This is what FR-009's "the count stated matches the inventory" depends on.

## Consumer obligations (what feature 010 must honor)

1. **One request per user action.** The contract is not idempotent — it has no request key and no
   deduplication. Two identical submissions mean two batches, or a JA-ID collision, depending on
   interleaving. Safety lives entirely on the client. This is the obligation the current code
   breaks and FR-001 restores.
2. **Read the response type from the quantity you sent.** A client that sends
   `quantity_to_create > 1` and expects a redirect will hang; one that sends `1` and calls
   `response.json()` will get the redirect target's HTML.
3. **`submit_type` is inert above quantity 1.** A client wanting continue-like behavior after a
   bulk creation must implement it itself. Feature 010 does, via navigation after the label dialog
   closes (research.md D4).

## Related: `POST /api/inventory/items`

`app/main/routes.py:470` exposes the same `_process_item_creation` to JSON callers, allocating the
JA ID server-side and mapping status to 200/207/400/500. Used by `app/api_client.py` and covered by
`tests/e2e/test_api_client.py`. **Out of scope** — it does not go through the form's submit
controls and does not exhibit the defect.
