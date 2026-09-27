# Tasks: Vendor Links on the Product Page

**Input**: Design documents from `specs/054-product-vendor-links/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/details-panel.md

**Tests**: Included — Constitution IV requires behaviour changes to land with tests.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

None — existing project, no new dependency.

## Phase 2: Foundational

- [ ] T001 In `app/catalog_service.py`, percent-encode the value (`urllib.parse.quote(value, safe='')`) in the existing `_mcmaster_listing_url` and `_amazon_listing_url`, add `_digikey_search_url(part_number)` returning `https://www.digikey.com/en/products/result?keywords=<encoded>`, and add module-level `VENDOR_PAGE_URLS = {AMAZON_VENDOR: _amazon_listing_url, MCMASTER_VENDOR: _mcmaster_listing_url, DIGIKEY_VENDOR: _digikey_search_url}` after the three builders are defined (research R2, R3). Do **not** register DigiKey's builder as `OrderVendor.listing_url`.
- [ ] T002 In `app/catalog_service.py`, add public `vendor_page_links(identifiers) -> List[Tuple[str, str, str]]`: for each identifier whose `id_type` is `VENDOR` or `DISTRIBUTOR` and whose `vendor` is a key of `VENDOR_PAGE_URLS`, yield `(vendor, value, url)`, de-duplicated on `(vendor, value)` and sorted (data-model.md).

**Checkpoint**: the function is callable and unit-testable on its own.

## Phase 3: User Story 1 — Open a product's vendor page from its Details panel (P1) 🎯 MVP

**Goal**: The Details panel links to Amazon, McMaster-Carr and DigiKey pages for the product.

**Independent Test**: A seeded product per vendor shows one correct link that opens in a new tab.

- [ ] T003 [P] [US1] Unit tests in `tests/unit/test_vendor_page_links.py` for `vendor_page_links`: each vendor's exact address from contracts/details-panel.md; `VENDOR` and `DISTRIBUTOR` both produce a link; the same value under both types gives one link; encoding of `/`, `#` and space; MPN/GTIN, unsupported vendor (`Mouser`) and legacy `Digi-Key` give nothing; empty input gives `[]`.
- [ ] T004 [US1] In `app/product/routes.py` `product_detail`, pass `vendor_links=vendor_page_links(product.identifiers)` to the template (import from `app.catalog_service`).
- [ ] T005 [US1] In `app/templates/product/detail.html`, add the `Vendor Pages` `<dt>`/`<dd id="product-vendor-links">` row after Manufacturer Part No., rendered only when `vendor_links` is non-empty, each link `class="vendor-link"`, `data-vendor`, `target="_blank" rel="noopener"`, text `{vendor} {value}` plus `bi-box-arrow-up-right` icon (contracts/details-panel.md).
- [ ] T006 [US1] Route tests in `tests/unit/test_vendor_page_links.py` using the `client` fixture: a product with an Amazon `VENDOR` identifier renders `#product-vendor-links` with the address, `target="_blank"` and `rel="noopener"`; a product with only an MPN renders no `product-vendor-links`.
- [ ] T007 [P] [US1] E2E test in `tests/e2e/test_product_vendor_links.py` (marker `e2e`), seeding via `live_server.add_test_data` one product per vendor (McMaster as `VENDOR` to cover the legacy type), then `expect()` each `.vendor-link[data-vendor=...]` to have the right `href`, `target` and `rel`; plus one product with only an MPN asserting `#product-vendor-links` has count 0 **after** `expect()` establishes `#product-description` (CLAUDE.md, negative assertion rule).

**Checkpoint**: US1 fully functional.

## Phase 4: User Story 2 — A product from several vendors links to each (P2)

**Goal**: Every supported vendor identifier gets its own link.

**Independent Test**: A product with DigiKey and McMaster-Carr identifiers shows both links.

- [ ] T008 [US2] In `tests/unit/test_vendor_page_links.py`, add tests: a DigiKey plus a McMaster identifier yields two links in `(vendor, value)` order; two different Amazon ASINs yield two Amazon links. (Behaviour is delivered by T002; this pins it.)

## Phase 5: Polish & Cross-Cutting

- [ ] T009 [P] In `docs/user-manual.md`, under "The Product Catalog" after the product detail screenshot, add a short paragraph: the Details panel's **Vendor Pages** row links to Amazon, McMaster-Carr and DigiKey pages built from the product's identifiers (DigiKey's goes via its search, which redirects to the part). No history of why.
- [ ] T010 Run `nox -s tests` (with the pyenv 3.13 PATH prefix, main-checkout venv) and fix failures, including any existing test asserting an unencoded listing address.
- [ ] T011 Regenerate screenshots with `nox -s screenshots_headless`; commit only `docs/images/screenshots/user-manual/product_detail.png` (and any other file whose change is caused by this feature), revert the rest; run `nox -s screenshots_verify`.
- [ ] T012 Run `nox -s e2e` detached (≥20 min) and confirm it passes and leaves the tree clean.
- [ ] T013 Verify spelling rule: `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing.

## Dependencies & Execution Order

- T001 → T002 → T004 → T005 → T006/T007.
- T003 may be written alongside T001–T002 (same file as T006/T008, so those are sequential with it).
- US2 (T008) depends only on T002.
- Polish after both stories; T011 needs T005; T012 last.

## Parallel Opportunities

- T003 and T007 are in different files from the implementation and each other.
- T009 is independent of all code tasks.

## Implementation Strategy

MVP is Phase 2 + US1 (T001–T007): the issue is satisfied at that point. US2 adds test coverage for
behaviour US1's function already provides. Then polish, screenshots and the full e2e run.
