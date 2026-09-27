# Research: Vendor Links on the Product Page

## R1 — Which identifier types produce a link

**Decision**: Both vendor-scoped types, `VENDOR` and `DISTRIBUTOR`, for every supported vendor.
The same (vendor, value) under both types yields one link.

**Rationale**: The issue names `VENDOR` for Amazon and `DISTRIBUTOR` for McMaster and DigiKey,
but the data does not follow that split. `_mcmaster_product_by_part_number` in
`app/catalog_service.py` already tries both types because McMaster product-page captures wrote
`VENDOR` before 049; the generic listing-capture path (around `catalog_service.py:1579`) writes
`VENDOR` for every vendor except McMaster, so a DigiKey part captured from its product page is
a `VENDOR` row. Keying on the issue's types alone would silently omit links for real products.
The vendor scope — not the type — is what says whose identifier it is.

**Alternatives considered**: Exactly the issue's types (misses legacy McMaster and
page-captured DigiKey rows); a data migration to normalize types (a schema-adjacent rewrite of
history for a display feature — rejected under Principle I and the "does not rewrite history"
stance already recorded beside `DIGIKEY_VENDOR`).

## R2 — Where the address builders live

**Decision**: A module-level `VENDOR_PAGE_URLS` dict in `app/catalog_service.py` mapping
`AMAZON_VENDOR`, `MCMASTER_VENDOR` and `DIGIKEY_VENDOR` to address builders, reusing the
existing `_amazon_listing_url` and `_mcmaster_listing_url` and adding `_digikey_search_url`.

**Rationale**: The Amazon and McMaster builders already exist with exactly the issue's
addresses. The `OrderVendor.listing_url` registry field is *not* reused for DigiKey: its
docstring in `app/services/order_vendors.py` says its presence "is what puts the details
checklist on the order screen", registered only for vendors whose captures lack details.
Registering DigiKey there would add a spurious checklist to DigiKey orders.

**Alternatives considered**: A new `vendor_page_url` field on `OrderVendor` (a new field on a
shared shape for one consumer, and it would only cover vendors with order flows); computing
addresses in the Jinja template (logic in the view, untestable in isolation).

## R3 — Encoding

**Decision**: `urllib.parse.quote(value, safe='')` in each builder.

**Rationale**: ASINs, McMaster part numbers and DigiKey part numbers are alphanumeric plus `-`,
which `quote` leaves untouched, so every real address is byte-identical to the issue's. A hand
-typed value with `/`, `#`, `?`, `&` or a space would otherwise route to a different page or
truncate. Applying it inside the shared builders also makes the existing details-checklist and
"Open listing" links correct for such values, with no change for real ones.

**Alternatives considered**: Jinja's `urlencode` filter in the template (spreads address
construction across two places).

## R4 — DigiKey product page address

**Decision**: Use the keyword-search address from the issue.

**Rationale**: `DigiKeyPart.product_url` is parsed from the API but never persisted; storing it
needs a column, a migration and a back-fill for existing products, which the issue explicitly
does not ask for ("unless we already capture the URL" — we do not).

## R5 — Placement and presentation

**Decision**: A `Vendor Pages` `<dt>`/`<dd>` pair inside the Details card's `<dl>`, after
Manufacturer Part No. Each link reads `<Vendor> <value>` with the external-link icon, opens with
`target="_blank" rel="noopener"`, and is omitted entirely when there are none. Ordering is by
vendor name then value, so the output is deterministic.

**Rationale**: The issue asks for the Details panel near the top. `target`/`rel` matches the
existing "Open listing" button on the same page.
