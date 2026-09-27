# Research: McMaster Order Details Checklist

## R1 — Where the per-vendor listing address lives

- **Decision**: An optional `listing_url: Callable[[str], str] | None` on `OrderVendor`,
  registered per vendor in `app/catalog_service.py`.
- **Rationale**: `order_vendors` is documented as the one place a vendor may differ in
  order capture and display (`receive_landing`, `carries_payload`, `adopts_renames`
  already drive the same order page). A name check in the route would be the second
  special case the issue warns against. Presence of the builder *is* the capability flag,
  so no separate boolean is needed; DigiKey answers "no" by registering none.
- **Alternatives**: a `vendor in (AMAZON, MCMASTER)` check plus a dict of builders in the
  route — rejected, it duplicates the registry. A boolean flag plus separate builder —
  rejected, two members that must agree.

## R2 — The Amazon builder's home

- **Decision**: Move `_amazon_listing_url` from `app/product/routes.py` to
  `app/catalog_service.py` beside the other Amazon vendor functions; the product page's
  missing-details link (044 FR-018) reads it through `AMAZON_ORDER_VENDOR.listing_url`.
- **Rationale**: the registration lives in the service module, which cannot import
  routes. One builder, two readers.

## R3 — McMaster address form

- **Decision**: `https://www.mcmaster.com/<part>/` with the part number as stored on the
  purchase (`vendor_item_id`, set from `line.part_number` by `_mcmaster_line_fields`).
- **Rationale**: issue #170 and 028 research §6; the trailing slash is McMaster's
  canonical product path. No escaping: part numbers are alphanumeric, same as ASINs.

## R4 — Automatic listing reads (044 US4)

- **Decision**: untouched. They run in the Amazon order confirmation, not off the order
  page's checklist gate, so changing the gate cannot enable them for McMaster.

## R5 — Product page link (044 FR-018)

- **Decision**: out of scope (spec Assumptions). Behaviour unchanged; only the builder's
  location moves.
