# Research: Edit Purchases and Orders

## R1. One edit screen per purchase, not inline table editing

- **Decision**: A dedicated page (`/purchases/<id>/edit`), reached from both listings.
- **Rationale**: Fourteen fields do not fit a table row; the receive and delete screens are
  already pages reached the same way, with the same `return_to` flag.
- **Alternatives**: Inline/modal editing — needs JS and a JSON endpoint; rejected (Principle I).

## R2. Received date on the edit screen

- **Decision**: Shown only for a purchase already received; may be changed or cleared. An
  outstanding purchase's screen says "Receive it from the Receive screen" instead. The service
  refuses a non-empty received date on an outstanding purchase.
- **Rationale**: Receiving is what raises a stock count; a second, silent way to mark something
  received would record arrivals that never moved the count. Clearing a receipt mirrors delete
  (032 FR-007): the count is left alone because nothing records whether the receipt moved it.
- **Alternatives**: Full freedom — creates two receive paths with different stock behaviour.

## R3. Absent vs blank fields

- **Decision**: `update_purchase` takes every field; `None` (absent from the form) leaves a field
  unchanged, `''` clears it. The edit form always submits every field it shows, so in practice
  blank means "clear". Vendor cannot be cleared.
- **Rationale**: Same rule the capture route uses ("absent, not merely empty"), and it lets the
  outstanding-purchase form omit `received_date` without clearing anything.

## R4. Pack fields

- **Decision**: Pack size and pack price edited directly; both blank → no pack; a pack size of
  two or more with a price → stored; anything else (size without price, price without size,
  size 1) is refused. Quantity and unit price are edited directly and are **not** recomputed
  from the pack (the two pairs record different things, see `Purchase.pack_size` comment).
- **Alternatives**: Reusing `pack-unit-price.js` and "Packs Bought" — that derives values for a
  new record; on an edit it would overwrite a deliberate correction. Rejected.

## R5. Order line number uniqueness

- **Decision**: Refused when the saved (vendor, supplier order number, line number) differs from
  the stored one and another purchase already has it. Not checked when unchanged.
- **Rationale**: Capture pairs lines by this number (024); two lines claiming one number would
  make re-capture write to the wrong row. Checking only on change avoids locking an existing
  row out of editing over a pre-existing duplicate.

## R6. Order rename onto an existing order

- **Decision**: Refused. Edit Order never merges.
- **Rationale**: Merging could produce colliding line numbers and is not what a correction of a
  mistyped number needs. Moving individual purchases between orders is available via R1.

## R7. Dates entered as `YYYY-MM-DD`

- **Decision**: When the submitted date is the same calendar day as the stored datetime, the
  stored value (with its time) is kept.
- **Rationale**: Captures may store a time of day; re-saving an untouched form must not
  truncate it, and truncation could make an unchanged same-day receipt appear to precede its
  order and be refused.

## R8. Where an edit returns to

- **Decision**: `return_to=order` → the order page of the purchase's *saved* vendor and order
  number (if it still has one), else the product page. Cancel returns to the page it came from.
- **Rationale**: Same two-value flag as 032; no caller-supplied URL is followed.
