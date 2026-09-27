# Implementation Plan: McMaster Order Details Checklist

**Branch**: `robot-army/issue-170-offer-the-order-page-details-checklist` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/050-mcmaster-details-checklist/spec.md`

## Summary

The order page's details checklist (044 US3) is gated on `vendor == AMAZON_VENDOR`, and its
**Open listing** link is hardcoded to the Amazon address builder. Replace the gate with a
per-vendor capability: an optional `listing_url` builder on `OrderVendor`. Amazon registers
the existing `/dp/<ASIN>` builder, McMaster registers `https://www.mcmaster.com/<part>/`,
DigiKey registers none. The route shows the checklist when the order's vendor has a
builder and passes that builder to the template. The misleading comment is corrected.

## Technical Context

**Language/Version**: Python 3.13, Flask, Jinja2

**Primary Dependencies**: existing only

**Storage**: MariaDB — no schema change

**Testing**: `nox -s tests` (unit, Flask test client), `nox -s e2e` (Playwright)

**Target Platform**: LAN web app

**Project Type**: web application (server-rendered)

**Performance Goals**: N/A

**Constraints**: Amazon order pages must render exactly as before

**Scale/Scope**: one dataclass field, two builder functions, one route, one template line

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Simplicity First | Pass. One optional field on the existing `OrderVendor` seam, which already exists to hold "everything a vendor is allowed to differ in" and has three measured implementations; this puts the variation where the module says it goes rather than adding a second vendor-name branch in a route. No configuration, no new abstraction. |
| II. Layered Architecture | Pass. Builders live beside the other vendor functions in `app/catalog_service.py`; the route stays thin and only reads the registry. No ORM in routes. |
| III. Exact Numerics | N/A — no measurements. |
| IV. Test Discipline Through Nox | Pass. Unit tests for McMaster, DigiKey and an unknown vendor on the order page; e2e mirroring the Amazon checklist test for McMaster plus a DigiKey absence check; run via `nox -s tests` and `nox -s e2e`. E2E seeds through the service and waits on elements, per CLAUDE.md. |
| V. MariaDB Source of Truth | Pass. No schema or data change; "missing details" stays derived. |
| VI. Item Lifecycle / History | N/A — inventory items untouched. |
| Threat model | N/A — the link is built from a stored part number, rendered escaped by Jinja as today. |

**Post-design re-check**: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/050-mcmaster-details-checklist/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/order-page.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
app/services/order_vendors.py        # + OrderVendor.listing_url
app/catalog_service.py               # + _amazon_listing_url, _mcmaster_listing_url; registered
app/product/routes.py                # gate on order_vendor.listing_url; drop local builder
app/templates/product/order.html     # listing_url(...) instead of amazon_listing_url(...)
tests/unit/test_order_product_details.py  # McMaster/DigiKey/unknown vendor order page
tests/e2e/test_order_product_details.py   # McMaster checklist, DigiKey none
```

**Structure Decision**: existing layout; no new modules.

## Complexity Tracking

None.
