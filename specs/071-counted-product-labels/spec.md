# Feature Specification: COUNTED Marking on Product Labels

**Feature Branch**: `071-counted-product-labels`

**Created**: 2026-11-26

**Status**: Implemented

**Input**: User description: "When a product label is printed for a product whose quantity is
tracked, the label must say COUNTED in white bold text on black, and on non-flag stocks also
show the current count and the last count date. Flag stocks show only COUNTED. Labels for
untracked products must be unchanged."

## Background

A product's quantity is either tracked (`Product.quantity` is a number, zero included) or not
(`NULL`). Nothing on a printed label says which, so a bin whose count is maintained looks the
same on the shelf as one that is not. Product labels are composed by
`app/services/product_label.py` (spec 038) and printed through the shared
`_print_product_label`, which serves both `POST /api/products/<id>/label` and the MCP tool
`print_product_labels` (spec 070).

## Requirements

- **FR-001**: A label printed for a tracked product carries the word `COUNTED`, white bold on
  black.
- **FR-002**: On the single-panel stocks (Sato 1x2, 2x4, 4x6) it also shows the current count
  and the date of the last count, `YYYY-MM-DD`.
- **FR-003**: On the Flag stocks it shows only `COUNTED`.
- **FR-004**: A label printed for an untracked product is byte-identical to what it was before
  this feature.
- **FR-005**: The date is the operator's local calendar day of `quantity_updated_at` (a naive
  UTC instant), converted on the server's local clock — the same convention as
  `local_now()`. The conversion lives in `app/utils/clock.local_date`.
- **FR-006**: The human-readable code is never given up for the marking (038 FR-012); the panel
  is composed into the width the marking leaves, and the barcode keeps at least 10 modules of
  quiet zone before the black marking.
- **FR-007**: The web endpoint and the MCP tool both print the marking, because both go through
  `_print_product_label`.

## Layout

- **Single panel**: a black block at the right end, 24% of the label's length, full height.
  Top ~20%: `COUNTED`, white bold. Middle 22–78%: an inset white window with the count in
  black bold, as large as fits. Bottom ~20%: the date, white regular. The existing panel
  (description, provenance, barcode and code text) is composed into the remaining width with
  its barcode length limit scaled to match.
- **Flag**: each half gets a black stripe 16% of the half's width at its outer end, with
  `COUNTED` running vertically in white bold; the rest of the half is the normal panel. The
  right half is the left turned 180°, so the stripes sit at both ends of the label, not at the
  fold.

## Edge Cases

- **Tracked, never counted** (`quantity_updated_at` is NULL): the count prints, the date line
  is left off; no placeholder.
- **Count 0** is tracked and prints `0`.
- **Large counts** (e.g. `12345`) shrink to fit the window.
- **Evening counts**: a count recorded at 02:30 UTC is printed as the previous day when the
  server is in a zone behind UTC.
- The count and date are a snapshot at print time; reprinting after a recount updates them.

## Out of Scope

- Configuration of the marking's size, position or wording.
- Any change to item (JA ID) labels. The 4x6 fix below changes their canvas, not what prints:
  the same 656 px barcode, centered, at the same physical size.
- **Sato 1x2 Flag product labels.** A 13-character Code128 needs about 378 px at a one-dot
  module; half of a 1x2 flag has about 287 px, so the barcode is downscaled below one dot and
  does not scan, with or without the marking. That predates this feature.
- **Sato 4x6 Flag** was not test-printed and keeps its 2:1 canvas.

## Stock fix: Sato 4x6 canvas

`Sato 4x6` composed at 2436 x 1218 (2:1) on a 6 x 4 in (3:2) label. CUPS scales to the label's
height and crops the excess, cutting about 304 px off each end of a full-width product label,
the block included. `fixed_len_px` is now 1827 (3:2). Verified by test print 2026-11-27.

## Verification

Test-printed 2026-11-27 with real products: Sato 1x2, 2x4, 2x4 Flag and 4x6 (after the canvas
fix) all print cleanly and scan.
