# Tasks: Say When the Image Count Was Swept

**Input**: Design documents from `specs/052-say-swept-image-count/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/listing-payload-images-swept.md, quickstart.md

**Tests**: Included — Constitution IV requires behavior changes to land with tests, and the
issue asks for e2e coverage.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

None — no new dependencies, configuration or migrations.

## Phase 2: Foundational (blocks all stories)

- [ ] T001 In `extension/capture-agent.js`, change `galleryFrom(doc)` to return `{ addresses, swept }`, where `swept` is true only on the branch that emits the existing `console.warn` (sweep supplied ≥1 address); keep the warning text and severity unchanged; return `{ addresses: [], swept: false }` when nothing is found
- [ ] T002 In `extension/capture-agent.js` `extract()`, destructure `galleryFrom(doc)`, pass `addresses` to `addImages`, and set `listing.images_swept = true` only when `swept` (omit the key otherwise); leave `PAYLOAD_VERSION` alone
- [ ] T003 In `app/models.py`, add `images_swept: bool = False` to `ListingCapture` with a comment citing 052/#172, and read it in `from_data` as `data.get('images_swept') is True`; `LISTING_CAPTURE_VERSION` unchanged
- [ ] T004 [P] In `tests/unit/test_order_product_details.py`, add unit tests: `from_data` reads `images_swept: true` as True; absent, `false`, `"true"` and `1` read as False

**Checkpoint**: the flag travels from the agent to `ListingCapture`.

## Phase 3: User Story 1 — the confirmation page says the count is a guess (P1) 🎯 MVP

**Independent test**: capture `amazon_listing_unreadable_gallery.html`; `#summary-images` carries the caveat.

- [ ] T005 [US1] In `app/templates/product/capture.html` `#summary-images`, after the count, render `<span class="images-swept">— the listing's own gallery data could not be read, so this count is a guess</span>` when `listing.images_swept`; nothing extra otherwise
- [ ] T006 [P] [US1] In `tests/unit/test_capture.py`, add tests that a posted payload with `images_swept: true` renders `images-swept` inside the summary, and one without it does not
- [ ] T007 [US1] In `tests/e2e/test_product_page_capture.py`, extend `test_a_gallery_it_cannot_parse_is_swept_loudly_not_silently` to `expect` `#summary-images .images-swept` visible with "count is a guess", keeping the console-warning assertion; assert a normal capture's `#summary-images .images-swept` has count 0 after `#summary-images` is visible

## Phase 4: User Story 2 — the order review says which lines' counts are guesses (P2)

**Independent test**: capture an order where one line's listing is the unreadable-gallery fixture; only that line's summary carries the caveat.

- [ ] T008 [US2] In `app/templates/product/order_review.html` `.line-listing-summary`, directly after the picture count, render `<span class="images-swept">(a guess — the gallery data could not be read)</span>` when `line.listing.images_swept`
- [ ] T009 [P] [US2] In `tests/unit/test_order_product_details.py`, add a test posting an order payload with one line listing carrying `images_swept: true` and one without; assert `images-swept` appears exactly once
- [ ] T010 [US2] In `tests/e2e/test_order_product_details.py`, add an e2e test that routes one ASIN's listing to `amazon_listing_unreadable_gallery.html` and the rest to `amazon_listing.html` (modeled on `serve_listings_except`), captures the order, and expects `.images-swept` on that line only (count 1, inside the right `line(review, n)`)

## Phase 5: User Story 3 — an older extension keeps working (P3)

Covered by T004 (absent key reads False) and T006 (no key → no caveat). No further work.

## Phase 6: Polish

- [ ] T011 [P] In `docs/user-manual.md`, in the paragraph on what the confirmation page reports, add one sentence: when Amazon's gallery data could not be read the image count is a guess and the page says so beside it
- [ ] T012 Run `nox -s tests`; run `nox -s e2e` detached (≈17 min) and confirm green; confirm `git status` clean afterwards
- [ ] T013 Check `grep -ric catalogue README.md docs/ app/ tests/` returns nothing

## Dependencies

- T001 → T002 → T007, T010 (e2e drives the real agent)
- T003 → T004, T005, T006, T008, T009
- US1 and US2 are independent of each other once Phase 2 is done.

## Parallel opportunities

- T004, T006, T009, T011 touch different files and can be written together after T003.

## Implementation strategy

MVP is Phase 2 + US1 (the reported defect). US2 is the issue's "also worth carrying" and is
cheap because the per-line summary already renders from the same `ListingCapture`.
