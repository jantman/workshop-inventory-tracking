# Research: McMaster Details-Only Capture

## R1. Which lookups decide "this item number already names a product"?

**Finding**: Two, both in `CatalogService`, both `VENDOR`-only:

- `find_listing_match` — called by `_capture_page` on every render of the confirmation page;
  a `None` result means no details-only choice.
- `capture_order` — the `match` it uses to attach silently (corroborated) or raise
  `CaptureDecisionRequired` (uncorroborated). A `None` result means a new product.

The issue names only the first. The second is the same defect on the purchase path: after a
McMaster order, a product-page purchase capture creates a second product for the same part.
And once the write becomes `DISTRIBUTOR` (R3), a `VENDOR`-only match would miss even products
`capture_order` itself created, and the next capture of the same page would try to create a
product whose `DISTRIBUTOR` identifier already exists.

**Decision**: Both resolve through one helper over `VENDOR_SCOPED_TYPES`.

**Rationale**: The confirmation page promises what the submit will do; if the two lookups
disagreed, the page could offer details-only for a product the purchase path then ignores.

**Alternatives considered**: widening only `find_listing_match` as the issue proposes —
rejected for the reason above.

## R2. Lookup order when both kinds could match

**Decision**: `VENDOR_SCOPED_TYPES` order — `VENDOR`, then `DISTRIBUTOR`.

**Rationale**: For Amazon every product is found by the first query exactly as today, so
Amazon's answer cannot change (SC-003). Two *different* products holding the same value
under the same vendor as different kinds cannot be produced by any capture path (each path
looks up both kinds before writing); it would take hand entry, and then either answer is
defensible.

**Alternatives considered**: `DISTRIBUTOR` first, as `_mcmaster_product_by_part_number` does —
no behavioural difference for any reachable state, and it would put a second query in front
of every Amazon lookup.

## R3. What `capture_order` writes for McMaster

**Decision**: `DISTRIBUTOR` scoped to `MCMASTER_VENDOR`; `VENDOR` for every other vendor.

**Rationale**: 028 FR-012 / US2 scenario 2 specified `DISTRIBUTOR`; the order path writes it;
`_missing_details_link` and every other `VENDOR`-reading site is Amazon-specific. 028
verification §A6 rejected this for SC-010 ("the shared path must behave identically"), but a
conditional on the vendor leaves every non-McMaster vendor on the identical branch.

**Alternatives considered**: keep `VENDOR` and only widen lookups — works, but leaves the two
McMaster paths writing different kinds for the same fact, which is how this bug was made.

## R4. DigiKey

**Finding**: DigiKey order capture writes `DISTRIBUTOR` scoped `DigiKey`. The extension has no
DigiKey product-page reader (`extension/capture-agent.js` classifies Amazon and McMaster
pages only), and `_capture_page` derives an item number from the URL only for Amazon (ASIN)
and McMaster. A DigiKey product therefore reaches these lookups only via the paste form with
an operator-typed item number, vendor derived as `DigiKey` from the host.

**Decision**: Accept the widening for DigiKey. The operator typed DigiKey's part number on a
DigiKey listing; the product carrying that DigiKey part number is the right answer, and the
previous answer was a silent duplicate product. Uncorroborated matches still ask, as for any
vendor.

## R5. Data

**Finding**: Unique key on identifiers includes the type, so `VENDOR` and `DISTRIBUTOR`
McMaster rows never collide. Live data: only order-created (`DISTRIBUTOR`) McMaster products.

**Decision**: No migration. A `VENDOR` McMaster row written before this feature is still found
by both lookups (and by `_mcmaster_product_by_part_number`, unchanged).
