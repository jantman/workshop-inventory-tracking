# Research: Bulk Receive and Bulk Label Printing on the Order Page

## R1 — How bulk receipt stays identical to single receipt

- **Decision**: Extract the "mark received" effects of `receive_purchase` (set
  `received_date` if not already set; raise a tracked count by `purchase.quantity`; clear a
  manual stock flag and its date) into `CatalogService._apply_receipt(session, purchase,
  product, received)`. `receive_purchase` calls it unchanged in behavior; the new
  `receive_order_lines` calls it per line.
- **Rationale**: SC-003 requires identical end states. One code path guarantees it; the
  existing single-receipt unit tests become the regression gate for the extraction.
- **Alternatives**: Loop calling `receive_purchase` per id — rejected: each call opens and
  commits its own session, so a refusal on line 3 would leave lines 1–2 received (violates
  FR-007).

## R2 — All-or-nothing

- **Decision**: One `_session()` for the whole batch. Validate every ticked line
  (belongs to this order; received date not before its order date) before mutating any;
  any `ValidationError` raised inside the session rolls everything back.
- **Rationale**: `_session()` already commits on success and rolls back on exception.

## R3 — Which ids may be received

- **Decision**: The service takes `vendor`, `order_number`, `purchase_ids`. It loads the
  order's lines (same filter as `find_order_lines_for`) and refuses (`ValidationError`) if
  any posted id is not one of them. No ids → `ValidationError("Tick at least one line…")`.
- **Rationale**: Receiving changes stock; a mistaken id must not silently receive a line of
  another order. Correctness, not defense.

## R4 — Received date default

- **Decision**: The date input is blank by default with "Blank means today", exactly as on
  the receipt screen; blank resolves to `local_now()`.
- **Rationale**: A prefilled `YYYY-MM-DD` parses to midnight, which is *before* an order
  captured earlier today and would be refused by `_validate_receipt_order`. Blank → now
  avoids that and matches the existing screen.

## R5 — Label printing wiring

- **Decision**: Reuse `BulkLabelPrintDialog` and the `bulk_label_modal` macro with prefix
  `order-bulk`, `printOne` posting to `/api/products/<id>/label` via `csrfFetch` — the same
  as `product-list-labels.js`. A new small `order-bulk-actions.js` owns the selection
  (checkbox state, select-all tri-state, count badge, enabling both buttons) and dedupes the
  selection by product id before opening the dialog.
- **Alternatives**: Generalize `ProductListSelection` — rejected: it is IIFE-private, keyed
  on the products table's ids, and does not dedupe; parameterizing it adds more than the
  ~60 lines a dedicated file costs.

## R6 — Receive form transport

- **Decision**: Checkboxes are `<input name="purchase_id" value="{id}" form="order-receive-form">`
  so the receive form (in the toolbar, outside the table) submits them without JS. Each also
  carries `data-product-id` / `data-product-label` for the label dialog.
- **Rationale**: Plain form post + redirect + flash is the app's pattern (purchase delete,
  receipt screen) and needs no fetch or wait-for-response handling.
