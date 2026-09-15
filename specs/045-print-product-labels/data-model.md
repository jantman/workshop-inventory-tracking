# Phase 1 Data Model: Print labels for selected products

## Persistent data: none

**This feature adds no table, no column, no index, and no Alembic revision.** Nothing it does writes
to the database. Constitution V has nothing to bind here beyond that statement.

The records it reads are read through endpoints that already exist and are not modified:

- **Product** — `app/database.py`. The label needs `id`, `description`, `internal_code`,
  `manufacturer`, `manufacturer_part_number`. All are already loaded by
  `POST /api/products/<id>/label`, which composes from the stored record at print time.
- **Purchase** — supplies the provenance line via `service.get_latest_purchase(product_id)`. Also
  already handled inside that endpoint.

The products list page itself continues to render from `service.search_products(...)` exactly as it
does today; the only change to what a row needs is that it must expose the product's `id` and its
description to the page, which it already has in hand.

## Transient data: the selection and the run

These live in the browser for as long as the page is open, and nowhere else.

### Entry

What the shared dialog is handed, one per selected thing. Deliberately the smallest shape that
serves both pages.

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Passed back to `printOne`. A JA ID on the inventory list; a product id on the products list. |
| `label` | string | What the operator sees in the selected-things list and in the progress line. The JA ID itself on the inventory list; the description on the products list. |

**Invariant**: `entries` is built fresh every time the dialog opens, from what the page currently
shows. It is never cached between opens, which is what makes FR-015 hold — a product filtered out of
the list has no checkbox, so it cannot appear in a later `entries`.

### Selection (products list)

Not a stored structure. The selection *is* the set of checked
`input.product-checkbox[data-product-id]` elements in the rendered table. Derived values:

| Derived | From | Used for |
|---|---|---|
| selected count | number of checked boxes | the count badge (FR-001) |
| has selection | count > 0 | enabling the Print Labels action (FR-004) |
| select-all state | count vs. total boxes | none / indeterminate / all (FR-003) |

**Validation rules**: none — a checkbox is either checked or not. The only rule worth stating is the
consequence of deriving rather than storing: there is no code path by which the selection can name a
product that is not on the page.

### Print run

Exists only for the duration of one `printAll()` call.

| Field | Type | Rules |
|---|---|---|
| `labelType` | string | One of the six stocks from `GET /api/labels/types`. Empty disables the print button, so a run cannot start without one. |
| `labelCount` | integer | Read once, before anything prints, via `window.readLabelCount`. Whole number, 1–99 inclusive. A refusal ends the call having printed nothing (FR-007). |
| `successCount` | integer | Entries whose POST returned ok. |
| `failureCount` | integer | Entries whose POST failed or threw. |
| `errors` | list of string | `"<entry.label>: <reason>"`, one per failure. Every failure is named (FR-012). |

**Reported total**: `successCount * labelCount`.

This is the rule worth preserving verbatim from the inventory implementation, which documents it at
`inventory-list.js:270`: a failed entry contributes **zero** labels, not a partial figure, because
one entry's copies are one `lp` job with one exit code. The total must never claim more labels than
actually came out of the printer.

**State sequence**, and therefore what an E2E test can wait on:

```
idle ──(stock chosen)──> armed ──(Print All)──> validating
                                                   │
                       refused ←──(count rejected)──┤      nothing printed, dialog otherwise untouched
                                                    │
                                                    └──> running ──> complete
```

- `idle → armed` is observable as the print button losing `disabled`.
- `validating → refused` is observable as the error region losing `d-none`, with the progress region
  still hidden.
- `armed → running` is observable as the progress region losing `d-none`.
- `running → complete` is observable as the Done button losing `d-none` and the status line starting
  with `Complete:`.

**Reset**: closing the dialog returns it to `idle` — stock cleared, count back to `1`, progress and
error regions hidden and emptied (FR-013). The count reset is not incidental: the modal node is
reused rather than recreated, so the markup's `value="1"` only ever applies on the very first open.
All four existing print dialogs reset theirs for this reason and say so in comments.

## Contracts consumed, unchanged

Both are used exactly as they stand; neither is edited. Full shapes in
[contracts/bulk-label-print.md](./contracts/bulk-label-print.md).

- `GET /api/labels/types` → `{success, label_types: [...]}` — the six stocks. Because both pages read
  this same endpoint, SC-006 ("no size present on one list and absent from the other") holds by
  construction rather than by test.
- `POST /api/products/<id>/label` with `{label_type, label_count}` → `{success, message, product_id,
  code, label_type, label_count}` or `{success: false, error}`. CSRF-protected, so the caller uses
  `csrfFetch`.
