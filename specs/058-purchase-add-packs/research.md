# Research: Pack Quantity on Record a Purchase

## R1 — Reuse `pack-unit-price.js` as-is

- **Decision**: Load the existing script on `purchase_add.html`, and give the fields the same
  ids as on `capture.html`: `packs`, `pack_price`, `pack_size`, `quantity`, `unit_price`,
  `unit-price-inexact` and `unit-price-error`.
- **Rationale**: The script looks its fields up by id and is inert where they are absent. It
  already writes nothing on load, which protects a re-rendered form, and it never listens
  on Quantity or Unit Price, so the owner's override is kept. That is exactly FR-002 and
  FR-003.
- **Alternatives**: A second script for this page would duplicate the `BigInt` arithmetic,
  so it was rejected.

## R2 — When the server derives

- **Decision**: For a pack size of 2 or more, an **empty** Quantity becomes packs × pack
  size, with Packs Bought defaulting to 1. An **empty** Unit Price with a pack price becomes
  pack price ÷ pack size, rounded to the cent. A non-empty value is always the owner's.
- **Rationale**: `capture_order` also treats a value equal to the *rendered* default as
  untouched, because that page is pre-filled from a listing. Record a Purchase is never
  pre-filled. A fresh render has empty Quantity and Unit Price, and a re-render after an
  error carries exactly what the owner submitted, so "empty" is the whole of "untouched".
  The shared helper takes the rendered defaults as optional arguments. Capture passes them,
  and this path passes none.
- **Alternatives**: Deriving inside `record_purchase` itself was rejected. It is called by
  every capture path with already-derived values, and changing its contract risks those
  paths.

## R3 — The 046 contract's "hand-recorded purchases hold NULL" (P5)

- **Decision**: Record a Purchase becomes a writer of the pack columns when, and only when,
  the owner states a pack of 2 or more with a price. The 046 contract under `specs/` is a
  frozen record, so it is not edited. This feature's contract records the new writer.
- **Rationale**: P5 and P6 exist so that a pack is never *inferred*. A pack typed by the
  owner is stated, which is the same footing as a capture-form confirmation. The
  "both or neither, never 1" invariant is enforced by the same `_pack_fields`.

## R4 — Error messages

- **Decision**: Use the same validators as capture (`_validate_pack_size`, `_validate_price`,
  `_validate_purchase_quantity`), so the messages match the capture page. The route
  already re-renders `form_data=request.form`, so every field comes back as entered.
