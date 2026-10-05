# Research: Move Products Between Locations by Scanning

## R1. What identifies a product at the scanner

- **Decision**: The `WIT` internal code (`^WIT[0-9A-HJKMNP-TV-Z]{10}$`) is the only product
  identifier the page accepts. It is matched case-insensitively and upper-cased before use.
- **Rationale**:
  - It is what the application prints on product labels.
  - It is unique: one INTERNAL identifier per product.
  - It cannot collide with `JA…`, `M…`, `T…` or `Other`.
  - `product_by_code` already upper-cases a typed code for the same reason: Crockford's
    alphabet is upper-case only, so folding cannot reach a different product.
- **Alternatives considered**: Accepting GTIN, MPN or vendor codes through
  `scan_router.classify`. Rejected because in the sub-location step any free text is a
  sub-location, so a GTIN or MPN would be ambiguous. Those codes are also not
  product-unique in general (MPN).

## R2. How much of the item controller is shareable

- **Decision**: Extract a `MoveManager` base class holding everything except a small set
  of overridable members (see `contracts/move-manager.md`). The item and product
  controllers become thin subclasses.
- **Rationale**: A line-by-line read of `inventory-move.js` puts the item-specific code in
  these places only:
  - `isJaId`;
  - `fetchCurrentLocation`'s URL;
  - `validateMoveItem`'s two URLs;
  - `executeMoves`' URL and `ja_id` key;
  - message wording.

  Everything else — scanner timing, `>>DONE<<`, the #107 wedge fix, bulk groups, the
  half-entered hint, the accumulating alerts — is exactly the behaviour products need.
  Duplicating it would fork every future fix.
- **Alternatives considered**:
  - Copying the file. Rejected: this is the duplication the issue asks to remove.
  - A configuration object passed to one class. Rejected: it carries the same information
    as overridden methods, but behaviour (`lookup`) does not fit in a config literal
    without callbacks, which amounts to a subclass by another name.
  - A mixin or composition "adapter" object. Rejected as one more moving part than
    inheritance for two implementations.

## R3. Generic internal names

- **Decision**: Rename the JA-named internals in the base:
  - `currentJaId` → `currentId`
  - `bulkGroupJaIds` → `bulkGroupIds`
  - the states `ja_id` → `id` and `ja_id_or_sub_location` → `id_or_sub_location`
  - the queue entry `jaId` → `id`
  - `data-ja-ids` / `tr[data-ja-id]` → `data-ids` / `tr[data-id]` in the shared template

  `location` and `bulk_location` stay.
- **Rationale**: A product code stored in `currentJaId` would mislead every reader of the
  shared file. Only `tests/e2e/waits.py` and two lines of `test_move_long_session.py`
  read these names (grep of `tests/`), so the rename is cheap. No test selects on the
  pending-row attribute.
- **Alternatives considered**: Keeping the JA names for test compatibility. Rejected
  because it trades a two-file test edit for a permanently misleading shared class.

## R4. Validation lookup, and the latent item defect

- **Decision**:
  - One `lookup(id)` per subclass returns `{found, location, subLocation, label}` and
    throws on transport or server error.
  - It is used both when a move is queued (current location) and when the queue is
    validated.
  - For items it is `GET /api/items/<ja_id>` (404 → not found).
  - For products it is the new `GET /api/products/by-code/<code>`.
- **Rationale**:
  - The item validator called `/exists` and then `/api/items/<id>`.
  - It read `detailData.location` and `detailData.display_name`, but the response nests
    them under `item`, so every validated entry's current location became "Unknown" and
    its label fell back to the JA ID.
  - One lookup used in both places makes that mismatch impossible, and halves the
    requests.
  - `/api/items/<ja_id>/exists` stays, because `inventory-add.js` uses it.
- **Alternatives considered**: Fixing the two property reads in place. Rejected because it
  keeps two code paths that read the same response differently, which is how the defect
  arose.

## R5. "None" versus "Unknown"

- **Decision**:
  - `lookup` reports an unset location as `null`.
  - The queue renders `null` as muted "None", the same as an unset sub-location already
    renders.
  - "Unknown" is reserved for a lookup that failed.
- **Rationale**:
  - The spec requires a product with no location to read "none", not "Unknown"
    (US1 scenario 1).
  - An item with no location was previously shown as "Unknown", which was also untrue.
    No item test asserts "Unknown" for a null location; `test_move_current_location_bug`
    asserts the opposite.

## R6. Unknown product codes

- **Decision**: A well-formed code that matches no product is queued like any other, with
  current location "Unknown", and is marked `not_found` at validation. This is the item
  page's behaviour.
- **Rationale**: The transition into "waiting for location" is synchronous in the state
  machine, and the e2e waits depend on that (CLAUDE.md patterns B and D). Rejecting at
  scan time would make it async and diverge from items. Validation is required before
  execution anyway, and Execute stays disabled while any entry is not validated.
- **Alternatives considered**: An async existence check at scan time. Rejected because it
  adds a second completion to every product scan for a case validation already catches.

## R7. Foreign IDs

- **Decision**:
  - The base classifier has a fourth class, `foreign`, which the item page never
    produces (`isForeignId` returns false).
  - The product page returns true for `^JA[0-9]+$` and refuses it with a pointer to Move
    Items.
- **Rationale**: Without this, a `JA` label scanned after a location would silently become
  the product's sub-location (spec edge case).
- **Alternatives considered**: Making the item page refuse `WIT` codes too. Rejected
  because FR-012 says the item page is unchanged.

## R8. Server-side sharing

- **Decision**: `app/utils/batch_move.py` holds three functions:
  - `parse_moves(data)` raises `ValueError` with the existing messages "Invalid request
    data" / "No moves provided";
  - `destination(location, sub_location)` returns the stripped location and a stripped
    sub-location or `None`;
  - `batch_result(moved_count, total, failed)` returns the existing response dict.

  Both batch-move routes use them. Product moves call
  `CatalogService.move_product(code, location, sub_location)`, which applies `destination`
  and writes through `update_product(location=…, sub_location=…)`, so only those two
  fields are touched (FR-010).
- **Rationale**:
  - These are the parts of the item route that are not about items.
  - Audit logging stays item-only, because products have no audit trail (spec
    Assumptions).
  - `update_product` already restricts itself to the fields passed.
- **Alternatives considered**: A generic batch-move route with a type switch. Rejected
  because it merges two resources' error handling and audit behaviour into one branchy
  handler.

## R9. Product hand-off

- **Decision**:
  - `GET /products/move?code=WIT…` reuses the `Handoff` dataclass and the comma-split
    parser.
  - A new `resolve_product_handoff(raw, service)` accepts each code that resolves to a
    product and rejects the rest as `not_found`.
  - The detail page's Move button sends one code.
  - `Handoff.rejected_items` entries are keyed `id` rather than `ja_id`, so one template
    renders both pages.
- **Rationale**:
  - A one-product preselection is exactly the item page's `bulk_location` path with a
    group of one: the next location queues it, and a following sub-location applies to
    it. No new state is needed.
  - Products have no inactive rows, so `inactive` never arises.
- **Alternatives considered**: A new "product already current, waiting for location" entry
  state. Rejected because `bulk_location` with one entry already is that state.

## R10. Routing `/products/move`

- **Decision**: A static rule `/products/move`.
- **Rationale**: Werkzeug ranks argument-free rules above `/products/<product_code>`, the
  same property `/products/new` relies on. `tests/unit/test_product_routes.py` already
  pins that behaviour; a unit test will pin `move` too.
