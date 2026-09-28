# Tasks: Capture McMaster Variant Product Pages

**Input**: Design documents from `/specs/056-mcmaster-variant-urls/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: Included — the constitution requires behavior changes to land with tests, and
the defect is only observable through them. Written first and seen failing.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

None — existing project, no dependencies added.

## Phase 2: Foundational

None — each story touches its own side of the machine boundary.

## Phase 3: User Story 1 — Capture after choosing a variant (P1) 🎯 MVP

**Goal**: the extension reads `/<part>-<part>/` as a McMaster product page, under the part
number the page shows.

**Independent Test**: serve `mcmaster_product.html` (which displays `91290A115`) at a
two-part address and capture it; the confirmation form carries the right part number.

- [X] T001 [US1] Tests in `tests/e2e/test_mcmaster_product.py`: serve the product fixture at (a) `/91290A115-91290A116/` → `#vendor_item_id` is `91290A115`, title and vendor filled; (b) `/91290A116-91290A115/` → `91290A115` (the page's number wins when it is the second); (c) `/91290A117-91290A118/` → `91290A117` (page names neither, so the first); (d) the 2-D drawing is attached on a variant address. Generalize `serve_product`/`capture_product` to take the path rather than adding copies
- [X] T002 [US1] Test in `tests/e2e/test_capture_extension.py`: capturing `/91290A115-91290A116/` through the loaded extension opens the confirmation form with `91290A115` and shows no "not a page it can read" message. Widen `MCMASTER_PRODUCT_ROUTE` to also serve the two-part path
- [X] T003 [US1] In `extension/capture-agent.js`: `MCMASTER_PRODUCT_PATTERN` becomes `/^\/(PART)(?:-(PART))?\/$/` with its comment covering the variant address (research.md §1); add `mcmasterPartNumber(doc, match)` returning the `[class*="_productDetailPartNumber_"]` text when it equals one of the matched numbers, else the first; `capture()` uses it

**Checkpoint**: T001/T002 pass; existing McMaster and extension tests unchanged and passing.

## Phase 4: User Story 2 — Paste a variant address (P2)

**Goal**: the paste-a-URL form prefills the first part number from a two-part address.

**Independent Test**: `_mcmaster_part_from_url('https://www.mcmaster.com/3408A521-3408A523/') == '3408A521'`.

- [X] T004 [P] [US2] Tests in `tests/unit/test_mcmaster_routes.py`: add `/3408A521-3408A523/` (with and without trailing slash, and on `127.0.0.1`) → `3408A521` to the positive parametrization; add `/91290A115-/`, `/91290A115-91290A116-91290A117/` and a lower-case second part to the blank parametrization; one form-level test posting the variant address to `/products/capture`
- [X] T005 [US2] `_mcmaster_part_from_url` in `app/product/routes.py`: same optional `-<part>` group, returns the first; docstring notes the variant address

## Phase 5: Polish

- [X] T006 `nox -s tests` (full unit suite) passes
- [ ] T007 `nox -s e2e` (detached, ~20 min) passes and leaves the tree clean
- [X] T008 Check user docs for a list of the address shapes the extension reads (`grep -rn "91290A115\|product page" docs/ README.md`) and update any that enumerate them

## Dependencies

- T001, T002 before T003 (seen failing first). T004 before T005.
- US1 and US2 are independent: different files, different sides.

## Parallel Example

T001–T003 (agent) and T004–T005 (server) can proceed in parallel.

## Implementation Strategy

US1 alone fixes the reported defect and is the MVP; US2 keeps the form in agreement with it.
