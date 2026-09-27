# Implementation Plan: Vendor Links on the Product Page

**Branch**: `robot-army/issue-180-clickable-links-for-products` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/054-product-vendor-links/spec.md`

## Summary

Add a **Vendor Pages** row to the product page's Details panel with one link per Amazon,
McMaster-Carr or DigiKey identifier the product carries, built from the addresses in issue
#180. The links are derived at render time from the product's existing vendor-scoped
identifiers by one small function in `app/catalog_service.py`, which reuses the Amazon and
McMaster listing-address builders already there and adds DigiKey's search address. No schema
change, no new dependency, no JavaScript.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1, Jinja2, Bootstrap 5.3 (all existing); `urllib.parse.quote` (stdlib)

**Storage**: MariaDB — read only; no migration

**Testing**: pytest via `nox -s tests` (unit) and `nox -s e2e`; screenshots via `nox -s screenshots_headless`

**Target Platform**: Linux server, LAN browser

**Project Type**: Server-rendered web application

**Performance Goals**: N/A — a loop over a product's identifiers, which are already loaded for the Identifiers card

**Constraints**: Must not alter the 044 details-checklist behaviour, which keys off `OrderVendor.listing_url` being registered only for Amazon and McMaster

**Scale/Scope**: One function, one template row, one route argument

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| I. Simplicity First | ✅ A dict of three vendor → address-builder entries and one function over the product's identifiers. No new module, no configuration, no registry hook: DigiKey's address is *not* registered as `OrderVendor.listing_url`, because that field's presence switches on the details checklist (044), which DigiKey must not get. No new dependency. |
| II. Layered Architecture | ✅ The derivation lives in `app/catalog_service.py` beside the builders it reuses; the route only passes its result to the template. No query in the route — `product.identifiers` is already loaded by `_product_or_404`. |
| III. Exact Numerics | ✅ Not touched. |
| IV. Test Discipline | ✅ Unit tests for the function (each vendor, both types, dedupe, encoding, unsupported vendor, none) and for the rendered row. One e2e test seeding via `live_server.add_test_data`, asserting with `expect()` on server-rendered HTML — no waits needed. All through `nox`. |
| V. MariaDB Source of Truth | ✅ No schema change; nothing written. |
| VI. Item History Invariants | ✅ Not touched (catalog side only). |
| Technology Constraints | ✅ Server-rendered Jinja, type-hinted public function. |
| Screenshots gate | ⚠️→✅ `app/templates/product/detail.html` changes, and the screenshot product (threadlocker) carries an Amazon ASIN, so `user-manual/product_detail.png` gains the row. Regenerate with `nox -s screenshots_headless`, commit only files whose content actually changed because of this feature, and pass `screenshots_verify`. |
| Threat model | ✅ Links use `rel="noopener"` because that is the existing convention for external links on this page (the "Open listing" button), not as hardening. Encoding the identifier is a correctness matter: a `/` or `#` would otherwise reach the wrong page. |

No violations; Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/054-product-vendor-links/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── details-panel.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
app/
├── catalog_service.py          # + _digikey_search_url, VENDOR_PAGE_URLS, vendor_page_links()
├── product/routes.py           # product_detail passes vendor_links=
└── templates/product/detail.html  # + Vendor Pages row in the Details <dl>

tests/
├── unit/test_vendor_page_links.py   # new: function + rendered page
└── e2e/test_product_vendor_links.py # new: click-through target and new-tab attributes

docs/
├── user-manual.md                          # one paragraph under The Product Catalog
└── images/screenshots/user-manual/product_detail.png  # regenerated
```

**Structure Decision**: Existing single Flask application; the feature touches the catalog
service, the product blueprint and one template.

## Complexity Tracking

None.
