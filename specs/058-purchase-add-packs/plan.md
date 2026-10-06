# Implementation Plan: Pack Quantity on Record a Purchase

**Branch**: `robot-army/issue-191-add-a-purchase-pack-quantity` | **Date**: 2026-10-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/058-purchase-add-packs/spec.md`

## Summary

The capture page already has everything this feature needs. It has three pack fields:
`packs`, `pack_price` and `pack_size`. `pack-unit-price.js` derives Quantity and Unit Price
from them in the browser using `BigInt` arithmetic, and it is inert on any page without
those fields. On the server, `capture_order` re-derives an untouched Quantity or Unit Price
and stores the vendor line through `_pack_fields`. Record a Purchase gets the same pieces:

1. **Template**: `product/purchase_add.html` gains the same three fields plus the two note
   elements `pack-unit-price.js` writes to. It uses the same ids, names, labels and defaults
   as `capture.html`, and it loads `pack-unit-price.js`. The script needs no change.
2. **Service**: the pack arithmetic in `capture_order` moves into one private helper,
   `CatalogService._apply_pack(...)`, so both paths use one rule. A new public method,
   `record_purchase_with_pack(product_id, packs, pack_size, pack_price, **fields)`, validates
   the pack fields, derives any empty Quantity or Unit Price, and calls the unchanged
   `record_purchase` with `_pack_fields(...)`.
3. **Route**: `purchase_new` forwards `packs`, `pack_size` and `pack_price` and calls the
   new method. The route stays thin.

## Technical Context

**Language/Version**: Python 3.13 (Flask), vanilla JavaScript

**Primary Dependencies**: Flask, SQLAlchemy, Bootstrap 5. Nothing new.

**Storage**: MariaDB. The existing `purchases.pack_size` and `purchases.pack_price` columns
are used, and there is no schema change.

**Testing**: pytest unit tests via `nox -s tests`; Playwright e2e tests via `nox -s e2e`

**Target Platform**: LAN web app

**Project Type**: web application (server-rendered)

**Performance Goals / Constraints / Scale**: N/A. This is one form on a single-user app.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ This reuses the existing JS file and the existing `_pack_fields` without change. The one new helper replaces duplicated arithmetic and does not add an abstraction. There are no new dependencies. |
| **II. Layered Architecture** | ✅ The derivation lives in `CatalogService`. The route only forwards form fields. |
| **III. Exact Numerics** | ✅ Prices are `Decimal` via `_validate_price`, and the division is `Decimal / int` rounded half-up to the cent. The browser side is the existing `BigInt` code, so there is no float anywhere. |
| **IV. Test Discipline** | ✅ There are unit tests for the route and service: derivation, overrides, no-pack parity, a pack of one, and refusal. An e2e test covers live derivation on the form. Waits are on field values via `expect`. Screenshots are regenerated if any of them shows this form. |
| **V. MariaDB Source of Truth** | ✅ No schema change. |
| **VI. Item Lifecycle Invariants** | ✅ N/A. This touches purchases, not JA-ID inventory items. |
| **Threat model** | ✅ Input is validated for correctness only. |

**Post-design re-check**: ✅ Unchanged after Phase 1. There are no violations.

## Project Structure

### Documentation (this feature)

```text
specs/058-purchase-add-packs/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── purchase-add-form.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── catalog_service.py              # _apply_pack (extracted), record_purchase_with_pack (new)
├── product/routes.py               # purchase_new forwards the pack fields
├── templates/product/purchase_add.html   # three pack fields + notes + script tag
└── static/js/pack-unit-price.js    # unchanged; header comment notes its second host

specs/046-*/contracts/purchase-pack-fields.md   # (frozen, not edited — see research R3)

tests/
├── unit/test_purchase_add_packs.py # new
└── e2e/test_purchase_add_packs.py  # new
docs/                               # user manual: Record a Purchase gains the pack fields
```

**Structure Decision**: This uses the existing single Flask app layout and adds no new
modules beyond the two test files.

## Complexity Tracking

No violations.
