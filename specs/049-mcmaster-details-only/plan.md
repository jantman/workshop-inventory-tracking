# Implementation Plan: McMaster Details-Only Capture

**Branch**: `robot-army/issue-171-mcmaster-order-products-can-t-have` | **Date**: 2026-09-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/049-mcmaster-details-only/spec.md`

## Summary

A McMaster order records each part number as a `DISTRIBUTOR` identifier; the single-listing
capture (`capture_order`) records a `VENDOR` one, and both of its "does this item number
already name a product?" lookups — `find_listing_match` (the confirmation page's details-only
offer) and the match inside `capture_order` (attach vs. ask) — look only for `VENDOR`. So an
order-created McMaster product is invisible to the product-page capture.

Three changes in `app/catalog_service.py`, and no others in application code:

1. One private helper, `_find_listing_product(item_id, vendor)`, tries each of
   `VENDOR_SCOPED_TYPES` in order, scoped to the vendor. Both lookups call it, so they cannot
   disagree (FR-001, FR-002, FR-005).
2. `capture_order` writes `DISTRIBUTOR` when the vendor is `MCMASTER_VENDOR`, `VENDOR`
   otherwise (FR-003, FR-004).
3. `_mcmaster_product_by_part_number`'s docstring, which explains the split this removes, is
   brought up to date. Its behaviour (both types) stays: a product recorded as `VENDOR` before
   this feature must still be found (FR-007).

Tests: new unit tests for both directions of McMaster details-only and for a McMaster
purchase capture after an order; the three `test_mcmaster_routes.py` assertions that pin
`VENDOR` for the product-page write move to `DISTRIBUTOR`.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask, SQLAlchemy (existing; nothing added)

**Storage**: MariaDB (SQLite in unit tests). No schema change, no migration.

**Testing**: pytest via `nox -s tests` (unit) and `nox -s e2e`

**Target Platform**: Linux server, LAN-only

**Project Type**: web-service

**Performance Goals**: N/A — at most one extra indexed identifier lookup per capture page
render, and only when the first lookup misses.

**Constraints**: Amazon capture behaviour byte-for-byte unchanged (spec SC-003).

**Scale/Scope**: ~20 lines of application code, one test module extended.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Simplicity First | Pass. One helper replacing two copies of the same lookup; one inline conditional on the write. No per-vendor table, no configuration, no new abstraction. The helper exists because two call sites must agree, not for a future vendor. |
| II. Layered Architecture | Pass. All changes are in the service layer; routes untouched. |
| III. Exact Numerics | N/A — no measurements touched. |
| IV. Test Discipline Through Nox | Pass. Behaviour change lands with unit tests that fail before the fix; run via `nox -s tests` and `nox -s e2e`. No e2e test is added: the defect is a service lookup, fully observable through the Flask test client, and the e2e suite's cost is what CLAUDE.md says to budget for. |
| V. MariaDB Source of Truth | Pass. No schema change; FR-007 — no data migration because both identifier kinds remain findable. |
| VI. Item Lifecycle / History | N/A — products and purchases only; inventory item history untouched. Details-only still records no purchase (044 FR-002). |
| Threat model | N/A — no new input surface. |

**Post-design re-check**: unchanged; the design added nothing beyond the above.

## Project Structure

### Documentation (this feature)

```text
specs/049-mcmaster-details-only/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

No `contracts/`: no route, form field, payload or template changes. The confirmation page
renders the existing 044 choice; it simply now has a `ListingMatch` to render it from.

### Source Code (repository root)

```text
app/catalog_service.py                   # helper, two lookups, one write, one docstring
tests/unit/test_mcmaster_details_only.py # new: US1–US3 and the DigiKey/Amazon edges
tests/unit/test_mcmaster_routes.py       # VENDOR → DISTRIBUTOR on the product-page write
```

**Structure Decision**: existing single Flask project; nothing new at the structure level.

## Complexity Tracking

No violations to justify.
