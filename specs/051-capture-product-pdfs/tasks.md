# Tasks: Capture Product PDFs

**Input**: Design documents from `specs/051-capture-product-pdfs/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/listing-images.md

**Tests**: Required — Constitution IV: behaviour changes land with tests.

## Phase 1: Setup

- [X] T001 Add a one-page PDF the e2e image host can serve, at `tests/e2e/fixtures/images/product_manual_sample.pdf`, and a second distinct one for the McMaster drawing route, `tests/e2e/fixtures/images/mcmaster_drawing_sample.pdf`

## Phase 2: Foundational (server accepts and reports PDFs — blocks both stories)

- [X] T002 [P] Unit tests: `_payload_images` keeps `data:application/pdf;base64,` entries and drops other `data:` entries, in `tests/unit/test_listing_images.py` (or the existing payload-parsing test module)
- [X] T003 [P] Unit tests: `store_listing_images` stores a `data:` PDF without calling `requests.get`, counts it in `pdfs`, fails an undecodable one, dedups a repeat, counts a fetched `application/pdf` in `pdfs`, and never logs the whole `data:` address, in `tests/unit/test_listing_images.py`
- [X] T004 [P] Unit tests: `_image_tally` names PDFs when `pdfs` > 0 and is unchanged otherwise, in `tests/unit/test_listing_images.py`
- [X] T005 Accept `data:application/pdf;base64,` in `_payload_images` and add `pdfs: int = 0` to `ImageCaptureResult` in `app/models.py`
- [X] T006 Decode `data:` entries instead of requesting them, count stored PDFs, shorten log labels in `app/services/listing_images.py`
- [X] T007 Name PDFs in `_image_tally` and carry `pdfs` through the order-listings sum in `app/product/routes.py`

**Checkpoint**: `nox -s tests` green.

## Phase 3: User Story 1 — McMaster capture keeps the 2-D drawing (P1) 🎯 MVP

**Independent test**: capture the McMaster fixture whose CAD picker shows 3-D PDF; the payload carries one `data:application/pdf` entry, the picker is closed and still reads 3-D PDF, and confirming stores a PDF attachment.

- [X] T008 [US1] Add a scripted CAD picker to `tests/e2e/fixtures/mcmaster_product.html`: combobox showing "3-D PDF", download anchor, and an option list rendered only while open, with ids `dropdown-<label><path>`; document it in the fixture's header comment
- [X] T009 [US1] E2E tests in `tests/e2e/test_mcmaster_product.py`: drawing is in the payload as a PDF `data:` address (route the drawing path to the sample PDF); the picker is left closed showing 3-D PDF; confirming stores a PDF attachment and the flash names it; a page with no CAD control captures as before (existing tests cover this)
- [X] T010 [US1] Implement `mcmasterDrawing(doc)` (find the 2-D PDF path via `aria-activedescendant` or by opening/closing the picker, fetch with the session, return a data URL or '') and have the `mcmaster-product` branch of `capture()` await it, in `extension/capture-agent.js`

## Phase 4: User Story 2 — Amazon capture keeps the listing's documents (P2)

**Independent test**: capture the Amazon fixture with a Product-guides PDF, its quick-view repeat, and a brand-story PDF; the payload carries the product PDF once and not the cross-sell one; confirming stores it.

- [X] T011 [US2] Add "Product guides and documents", a quick-view repeat and a brand-story PDF link to `tests/e2e/fixtures/amazon_listing.html` (and the A+ fixture if the brand story lives only there)
- [X] T012 [US2] E2E tests in `tests/e2e/test_product_page_capture.py`: PDF captured once, cross-sell PDF excluded, confirming stores it; update any exact image-list/count assertions the new entry changes
- [X] T013 [US2] Implement `documentLinks(doc, baseUrl)` and append its result in `extract()` in `extension/capture-agent.js`

## Phase 5: Polish

- [X] T014 [P] Docs: say "images and PDFs" where capture is described in `docs/user-manual.md`, `docs/capture-extension.md`, `README.md`
- [X] T015 Run `nox -s tests` and `nox -s e2e` (detached); record results in `specs/051-capture-product-pdfs/quickstart.md`
- [X] T016 Validate against the real `https://www.mcmaster.com/91074A329/` by running the agent's drawing reader in the owner's browser (SC-001)

## Dependencies

- T001 → T008/T011. T002–T004 → T005–T007. Phase 2 → Phases 3 and 4 (confirming stores the PDF only once the server accepts it).
- US1 and US2 are independent of each other; both touch `extension/capture-agent.js`, so do them sequentially.

## Parallel Opportunities

- T002, T003, T004 (one file, independent test classes, written together).
- T014 alongside Phase 3/4.

## Implementation Strategy

MVP is Phase 2 + US1 — the reported defect. US2 follows in the same PR, as the issue asks.
