# Implementation Plan: Move Products Between Locations by Scanning

**Branch**: `robot-army/issue-188-location-set-move-for-products` | **Date**: 2026-10-05 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/057-product-location-move/spec.md`

## Summary

The item Move page is one 1,140-line controller, `InventoryMoveManager` in
`app/static/js/inventory-move.js`. About nine-tenths of it has nothing to do with inventory
items: the scanner timing, the `>>DONE<<` handling, the four-state scan machine, the
preselected-group transition, the queue table, the half-entered hint, validation, execution
and alerts. What is item-specific fits in a handful of places: the `JA` pattern, the two
`/api/items/...` URLs, the batch-move URL and its `ja_id` key, and the wording.

The plan splits that file along that seam:

1. **`app/static/js/move-manager.js`** (new): `class MoveManager`. This is the existing
   controller with JA-specific names made generic: `currentJaId` becomes `currentId`, the
   `ja_id` / `ja_id_or_sub_location` states become `id` / `id_or_sub_location`,
   `bulkGroupJaIds` becomes `bulkGroupIds`, and the queue entry's `jaId` becomes `id`. The
   behaviour stays put. Subclasses supply what differs (see
   [contracts/move-manager.md](./contracts/move-manager.md)): the `idLabel` and `noun`, an
   ID pattern (`isSubjectId`, `normalizeId`, optionally `isForeignId`), one `lookup(id)`, the
   execute URL, and the per-move request body.
2. **`app/static/js/inventory-move.js`**: shrinks to `InventoryMoveManager extends
   MoveManager`, about 60 lines.
3. **`app/static/js/product-move.js`** (new): `ProductMoveManager extends MoveManager`, of
   the same size. The ID is the `WIT` internal code, matched case-insensitively. A `JA`
   label is refused as a foreign ID rather than being taken as a sub-location.
4. **One template body**: `app/templates/move/_scan_move.html` is a macro holding the whole
   page body, parameterised by noun, ID label, example and links. `inventory/move.html` and
   the new `product/move.html` each call it. The item page renders the same text it renders
   today.
5. **Server.** There are two new product endpoints:
   - `GET /api/products/by-code/<code>` serves both lookup and validation;
   - `POST /api/products/batch-move` executes the queue.

   There is one new service method, `CatalogService.move_product(code, location,
   sub_location)`, and one new page route, `GET /products/move`, which takes an optional
   `?code=` hand-off for the detail page's Move button. The pieces of request handling that
   both batch-move routes would otherwise duplicate go in a small
   `app/utils/batch_move.py`: reading `moves`, the destination rule (strip; a blank
   sub-location clears it) and the response body. The item route is rewired onto it with
   its audit logging untouched.

Validation now goes through one `lookup()` per entry. For items that is a single
`GET /api/items/<ja_id>`, replacing `/exists` plus the detail GET. This removes the latent
defect at `inventory-move.js:971` (FR-012): the detail response was read without its `item`
envelope, so validation overwrote the real current location with "Unknown".

The e2e waiter `waits.scan_on_move_page` stops mirroring the JS regexes in Python. It asks
the page how it will classify the value (`window.moveManager.classifyInput`) and reads
`idLabel` for the badge wording, so the one waiter serves both pages.

## Technical Context

**Language/Version**: Python 3.13; plain browser JavaScript (ES2020 classes, no build step)

**Primary Dependencies**: Flask 3.1, SQLAlchemy 2.0, Bootstrap 5.3.2. Nothing added.

**Storage**: MariaDB `products.location` / `products.sub_location`, which already exist and
are nullable. No schema change and no migration.

**Testing**: `nox -s tests` (pytest unit, SQLite), `nox -s e2e` (Playwright)

**Target Platform**: LAN-only Linux server; desktop browser with a keyboard-wedge scanner

**Project Type**: Server-rendered web application

**Performance Goals**: None beyond the item page's (one lookup per scan). No batching (Principle I).

**Constraints**:
- Item Move page behaviour must not change (FR-012, SC-004).
- E2E waits follow `CLAUDE.md`: state, never time.

**Scale/Scope**: One user, tens of products per session

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ The issue asks for duplication to be removed. One base class with two subclasses is the smallest structure that has two real implementations. No plugin registry and no configuration object, only overridden methods. Lookups stay per-scan and unbatched, as on the item page. Product hand-off is single-code only (from the detail page). The bulk product hand-off is out of scope. |
| **II. Layered Architecture** | ✅ Routes stay thin: the product batch-move route loops and calls `CatalogService.move_product`, which owns lookup, the destination rule and persistence. No ORM query lives in a route. `app/utils/batch_move.py` is request-shape handling only. |
| **III. Exact Numerics** | ✅ N/A. Location strings only, no measurements. |
| **IV. Test Discipline** | ✅ Unit tests are written for the service method, both new endpoints, the product page route and hand-off, and `batch_move` helpers. E2E tests cover the product page. Existing item e2e tests keep their assertions. Waits are on state via the shared waiter, with no fixed delays. Screenshots are regenerated for the changed templates and JS. |
| **V. MariaDB Source of Truth** | ✅ No schema change. |
| **VI. Item Lifecycle Invariants** | ✅ Item moves still call `service.get_item` (active row) and `update_item` in place. The item batch-move route keeps its logic and audit calls; only payload reading, the destination rule and the response body move into shared helpers with identical behaviour. The existing move e2e tests and `TestBatchMoveAPIWithSubLocation` cover it. |
| **Threat model** | ✅ The new endpoints validate input for correctness only. The product batch-move route does not get `csrf.exempt`, because the page sends `X-CSRFToken`. |

**Post-design re-check**: ✅ Unchanged after Phase 1. No violations, so Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/057-product-location-move/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── product-move-api.md
│   └── move-manager.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── catalog_service.py            # + move_product()
├── main/routes.py                # inventory_move renders shared macro; batch-move uses utils/batch_move
├── product/routes.py             # + /products/move, /api/products/by-code/<code>, /api/products/batch-move
├── utils/
│   ├── batch_move.py             # NEW: parse_moves, destination, batch_result
│   └── handoff.py                # + resolve_product_handoff; rejected entries keyed generically
├── static/js/
│   ├── move-manager.js           # NEW: shared MoveManager (bulk of old inventory-move.js)
│   ├── inventory-move.js         # InventoryMoveManager extends MoveManager
│   └── product-move.js           # NEW: ProductMoveManager extends MoveManager
└── templates/
    ├── base.html                 # Products menu: + Move Products
    ├── move/_scan_move.html      # NEW: shared page-body macro
    ├── inventory/move.html       # calls the macro
    └── product/
        ├── move.html             # NEW: calls the macro
        └── detail.html           # + Move button

tests/
├── unit/
│   ├── test_batch_move_utils.py         # NEW
│   ├── test_product_move.py             # NEW: service, API, page route, hand-off
│   └── test_handoff_parsing.py          # updated for renamed helpers/keys
└── e2e/
    ├── waits.py                         # scan_on_move_page asks the page to classify
    ├── test_product_move.py             # NEW
    └── test_move_long_session.py        # currentJaId → currentId, 'location' state unchanged

docs/user-manual.md                      # + "Moving Products" section
```

**Structure Decision**: The existing Flask layout is kept. New code sits beside its item
counterparts: the product blueprint for routes, `CatalogService` for logic, `app/utils/`
for the request helpers, and `app/static/js/` for the controllers.

## Complexity Tracking

No violations.
