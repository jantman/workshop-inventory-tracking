---
description: "Task list for feature 044: capture product details for products an order created"
---

# Tasks: Capture Product Details for Products an Order Created

**Input**: Design documents from `/specs/044-order-product-details/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required. Constitution IV requires every change in behavior to land with tests, and
quickstart.md §1 requires the SC-001 regression test to be seen failing first.

**Organization**: Tasks are grouped by user story. US1 and US2 (both P1) together fix the reported
defect. US3 (P2) and US4 (P3) build the guided process on top of them.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1–US4 from spec.md
- **Run commands**:
  - Use `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" /home/jantman/GIT/workshop-inventory-tracking/venv/bin/nox -s <session>`.
  - The worktree has no venv.
  - Never invoke pytest directly.

---

## Phase 1: Setup (operational limits this feature needs)

**Purpose**: The two single settings from research.md §7 and §8. Without them a multi-line order
fails with a 413 or a killed worker.

- [X] T001 [P] Add `MAX_FORM_MEMORY_SIZE = 16 * 1024 * 1024` to the base config class in `config.py`, with a comment citing Werkzeug 3.1's 500 000-byte per-field default and research.md §7 (the order payload now carries a listing per line, and the review posts it back).
- [X] T002 [P] Add `--timeout 600` to the gunicorn `CMD` in `Dockerfile`, with a comment citing research.md §8 (an order confirmation now stores a gallery per line at 8–15 s each; the default is 30 s).
- [X] T003 [P] In `docs/deployment-guide.md`, state that a reverse proxy in front of the app needs a read timeout of at least 600 s, because confirming an Amazon order downloads every line's pictures before it responds.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The in-memory types and the three service methods every story uses
(data-model.md, contracts/details-only-capture.md §5).

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [X] T004 Write the SC-001 regression test **first** in `tests/unit/test_order_product_details.py`. It covers a product created through `CatalogService.capture_order_lines` from an Amazon order holding ASIN X (use the `AMAZON_ORDER_VENDOR` path and a hand-built `AmazonOrder`). It then POSTs a listing capture for X to `/products/capture` with `intent=details` and `details_product_id=<that product>` plus a `listing` payload carrying two specification rows. Assert:
  - the response redirects to that order's page
  - the product has specification rows
  - the product still has exactly one purchase

  Run `nox -s tests -- tests/unit/test_order_product_details.py`, confirm it **fails**, and paste the failure into a new `specs/044-order-product-details/verification.md` under "Red before the fix".
- [X] T005 Refactor `ListingCapture.from_json` in `app/models.py` into `from_data(data: Any) -> Optional[ListingCapture]` (every current check except `json.loads`) plus a thin `from_json` that parses and delegates. Behavior must be byte-for-byte unchanged, so the existing `tests/unit/test_amazon_payload.py` passes unedited.
- [X] T006 Add the frozen dataclasses `ListingMatch` and `ListingDetailsResult` to `app/models.py`, with exactly the fields and properties in data-model.md:
  - `ListingMatch.from_order`
  - `ListingMatch.spec_differences(listing)`, returning `(added, differing)`. Names are case-folded in Python, and `description_text` counts as a row named `Description`.
  - `ListingDetailsResult.changed_anything`
- [X] T007 Add `CatalogService.products_missing_details(product_ids) -> Set[int]` to `app/catalog_service.py`. It is one grouped query over `ProductSpecification.product_id` for the given ids, returns the ids with no row, and returns an empty set for empty input (data-model.md, "Derived: a product's details status").
- [X] T008 Add `CatalogService.find_listing_match(vendor, vendor_item_id, url=None, order_date=None) -> Optional[ListingMatch]` to `app/catalog_service.py`, read-only. It works as follows:
  - Look up the product with `find_product_by_identifier(item_id, id_type=VENDOR, vendor=vendor)`.
  - Call `_find_captured_purchase(vendor, item_id, url, ordered)`, where `ordered` defaults to today at midnight exactly as `capture_order` computes it.
  - Keep the purchase as `order_purchase_id`/`order_reference`/`order_vendor` only when it carries a `supplier_order_reference` and its `product_id` equals the matched product's id.
  - Copy the product's current scalar values and its specification rows (in `display_order`) into the dataclass inside the session.
  - Return None for no item id or no product.
- [X] T009 Add `CatalogService.apply_listing_details(product_id, listing, proposed=None, replace=frozenset()) -> ListingDetailsResult` to `app/catalog_service.py`, per contracts/details-only-capture.md §5 and research.md §4:
  - **Validation.** Validate every non-blank proposed scalar up front with the existing validators: `_validate_description`, `_validate_category_path`, and the lengths `update_product` enforces. A refusal writes nothing.
  - **One session.**
    - Each scalar: a blank proposal changes nothing. A blank current value is filled. A differing current value is replaced only when its field name is in `replace`.
    - Each listing row, plus a `Description` row from `description_text`, row-validated leniently like `merge_specifications`: an absent name (case-folded) is appended after the highest `display_order`. A present name with a different value is overwritten in place only when `spec:<name>` is in `replace`.
  - **After the session.** Pass the added and replaced rows to `_promote_barcode_rows`.
  - **Never touches** purchases, quantity, stock status, their dates, or reorder threshold.
  - **Returns** the result; raises `ItemNotFoundError` for a missing product.
  - **Shared merge code.** Factor the add-only loop of `merge_specifications` into a private helper that works on a loaded `Product` in any session, so the two methods share one rule. `merge_specifications`' own behavior must not change.
- [X] T010 Unit-test T005–T009 in `tests/unit/test_order_product_details.py`:
  - `from_data`/`from_json` parity
  - `spec_differences`
  - `products_missing_details`:
    - an order-created product is missing
    - a listing-captured product is captured
    - an empty list returns an empty set
  - `find_listing_match`:
    - no match
    - a match without an order purchase
    - a match with one
    - an order purchase on a *different* product is ignored
    - outside the 90-day window
  - `apply_listing_details`:
    - fills blanks
    - keeps differing values by default
    - replaces only the named fields and rows
    - a repeat call changes nothing and duplicates no row or GTIN
    - writes no purchase
    - leaves quantity and stock untouched
    - refuses an over-length description with nothing written

**Checkpoint**: `nox -s tests` is green apart from T004, which stays red until US1/US2 land.

---

## Phase 3: User Story 1 — Details without a purchase (Priority: P1) 🎯 MVP

**Goal**: A listing capture whose ASIN names an existing product can update that product's details
without recording a purchase, with per-value show-and-choose (FR-001–FR-008).

**Independent Test**: Seed a thin product with one purchase, capture its listing through the agent,
choose details-only, and confirm. The product gains the listing's details and still has one
purchase.

### Tests for User Story 1

- [X] T011 [P] [US1] Route tests in `tests/unit/test_order_product_details.py` for the landing and details path:
  - **Landing.** A form POST to `/api/capture` whose listing ASIN names a product renders `#listing-match` with `#intent-purchase` checked and `#intent-details` present. One naming no product renders neither.
  - **Details path.** `intent=details` writes no purchase, flashes the result, redirects to the product page, and stores images through a mocked `store_listing_images`.
  - **Replace ticks.** A tick replaces only that value.
  - **Nothing new.** `#nothing-new` renders when the listing holds nothing new.
  - **No `intent`.** Posting without `intent` records a purchase exactly as before (FR-008).
- [X] T012 [P] [US1] E2E journey in `tests/e2e/test_order_product_details.py`:
  - **Setup.** Seed a thin Amazon product (ASIN from `amazon_listing.html`) plus one purchase with `live_server.add_test_data` or the service. Fulfil `/dp/<ASIN>` with the fixture as `test_product_page_capture.py` does, and run the agent.
  - **Landing.** In the new tab, wait on `expect(page.locator('#listing-match')).to_be_visible()`. Check `#intent-details`, then submit.
  - **After submit.** Wait for the product page's specifications list (`#product-specifications`). Then assert its purchase history still shows one row.

### Implementation for User Story 1

- [X] T013 [US1] In `app/product/routes.py`, add a helper `_capture_page(form_data, listing, **extra)` that computes `match = service.find_listing_match(vendor, item_id, url, form_data.get('order_date'))` and renders `product/capture.html` with `match`.
  - **Where `vendor`/`item_id` come from:** the same derivation `product_capture` uses (`vendor` field, else `_vendor_from_url`; `vendor_item_id`, else `_asin_from_url` / `_mcmaster_part_from_url`).
  - **Call sites:** the bookmarklet landing in `api_capture` (form branch), plus the `CaptureDecisionRequired` and `ValidationError` re-renders in `product_capture`. Each keeps its current keyword arguments.
- [X] T014 [US1] In `product_capture` (`app/product/routes.py`), add the `intent == 'details'` branch per contracts/details-only-capture.md §4:
  - **Fields.** Resolve the listing fallbacks for manufacturer and part number exactly as the purchase path does, then call `service.apply_listing_details(int(details_product_id), listing, proposed={...six fields from the form...}, replace=set(request.form.getlist('replace')))`.
  - **Errors.** On `ValidationError` or `ItemNotFoundError`, flash and re-render through `_capture_page`.
  - **Success.**
    - Flash a sentence built from `ListingDetailsResult`, or "Nothing new to add to this product."
    - Add the existing barcode tally from `describe_captured_barcodes`.
    - Call `store_listing_images` with its `_image_tally`.
    - Redirect to `product.product_detail`. US2 adds `return_order`.
  - **Absent `intent`.** Must reach the unchanged purchase code.
- [X] T015 [US1] In `app/templates/product/capture.html`, render the plain-mode `#listing-match` block when `match` is set and not `match.from_order`:
  - **The choice.** Radios `name="intent"`: `#intent-purchase`, checked by default, and `#intent-details`. Include a hidden `details_product_id`, and restore the chosen intent from `form_data` on re-render.
  - **Scalar fields.** Under each of description, manufacturer, part number, and the classification fields: when `match` holds a value, show *"Currently: X"* and an unticked checkbox `name="replace" value="<field>"` with class `.replace-current`. The classification fields come from the shared `_classification_fields.html` include, so put the notes in a small block right after the include rather than editing the include.
  - **`#spec-differences`.** A table built from `match.spec_differences(listing)`, with the added-row count and a checkbox per differing row (`value="spec:<name>"`), restored from `form_data.getlist('replace')` on re-render.
  - **`#nothing-new`.** Rendered per contract §3.
  - **Heading.** The show-and-choose block's heading says it applies only when updating details only.

**Checkpoint**: US1's tests pass, and a thin product can be filled without a purchase.

---

## Phase 4: User Story 2 — One clear question after an order capture (Priority: P1)

**Goal**: When the listing's product also holds an order-captured purchase, the page shows one
message naming the order, with details-only preselected and returning to the order afterwards
(FR-009–FR-013, FR-020).

**Independent Test**: Capture an order containing X, then capture X's listing, and confirm without
changing anything. The product has details and one purchase, and you land on the order page.

### Tests for User Story 2

- [X] T016 [P] [US2] Route tests in `tests/unit/test_order_product_details.py`:
  - **Collapsed landing.** The landing for a listing whose product carries an order-captured purchase renders `#order-item-match`, naming the order reference and the product, with `#intent-details` checked. It does **not** render `#duplicate-warning` or `#identifier-warning`, and it does render the FR-011 sentence.
  - **Confirming as shown.** This makes T004 pass: redirect to `_order_url('Amazon', ref, highlight=asin)`.
  - **Separate purchase.** `intent=purchase` with the hidden answers records exactly one new purchase on that product with no question raised.
  - **Paste path.** A paste-path re-render where `capture_order` raised both questions for that same situation renders the collapsed block instead of the two warnings.
  - **Different product.** `#attach-new` carries the FR-013 consequence sentence.
- [X] T017 [P] [US2] Update the assertions in `tests/unit/test_cross_path_duplicates.py::TestCapturingAListingAfterItsOrder` (around lines 631–742) for FR-009:
  - Expect `#order-item-match` where the class expected both warnings.
  - Keep, unchanged in meaning, every assertion that acknowledging records a separate purchase. It now goes through the collapsed block's hidden answers.
  - Record each edited assertion and why in `specs/044-order-product-details/verification.md`.
- [X] T018 [P] [US2] E2E journey in `tests/e2e/test_order_product_details.py`:
  - **Setup.** Capture `amazon_order.html` through the agent as `tests/e2e/test_amazon_order.py::capture_order` does, with `/dp/<ASIN>` fulfilled by `amazon_listing.html` for the listing capture only, and confirm.
  - **Listing capture.** Run the agent on the first line's listing. Wait for `#order-item-match`, assert `#intent-details` is checked, then submit without changing anything.
  - **After submit.** Wait for the order page (`#order-lines`). Open the product and assert one purchase and non-empty `#product-specifications`.
  - **Negative assertion.** Assert `#duplicate-warning` is absent only after `#order-item-match` is visible.

### Implementation for User Story 2

- [X] T019 [US2] In `app/templates/product/capture.html`, render `#order-item-match` when `match.from_order`, and wrap the existing `#duplicate-warning` and `#identifier-warning` blocks so they do not render in that case:
  - **The choice.** Radios `#intent-details` (checked unless `form_data.intent == 'purchase'`) and `#intent-purchase`.
  - **The FR-011 sentence**, always visible.
  - **Hidden fields:** `acknowledged_duplicate_of=match.order_purchase_id`, `attach_to=match.product_id`, `details_product_id=match.product_id`, `return_order=match.order_reference`.
  - **The show-and-choose section from T015**, reused rather than duplicated. Move it into a `{% macro %}` or a small include in the same template directory if both blocks need it.
  - **`#attach-new`.** Add the FR-013 consequence sentence to its label in the existing identifier block.
- [X] T020 [US2] In the details branch of `product_capture` (`app/product/routes.py`), redirect to `_order_url(vendor, request.form['return_order'], highlight=vendor_item_id)` when `return_order` is present and non-blank; otherwise to the product page (FR-020).

**Checkpoint**: T004 is green, and the reported scenario (SC-001) works end to end. This is a
shippable fix for issue #156 on its own.

---

## Phase 5: User Story 3 — The order's page guides you through details (Priority: P2)

**Goal**: The Amazon order page and the product page say which products still need details and link
to each listing (FR-014–FR-019, FR-021).

**Independent Test**: Capture an order of new items, then open its page. Each line reads "missing"
with an "Open listing" link. Fill one through US2 and the count drops.

### Tests for User Story 3

- [X] T021 [P] [US3] Route tests in `tests/unit/test_order_product_details.py`:
  - **Order page.** `GET /products/orders/Amazon/<ref>` renders:
    - `#details-progress` with the distinct-product count
    - `.details-missing` plus `a.open-listing[href="https://www.amazon.com/dp/<ASIN>"]` on thin lines
    - `.details-captured` on lines with rows
    - "Every product on this order has its details" when none are missing
  - **Other vendors.** A McMaster or DigiKey order page renders none of these.
  - **Product page.** `#details-missing-notice` renders for an Amazon-identified product with no rows, and not for one with rows or without an Amazon identifier.
- [X] T022 [P] [US3] E2E checklist round trip in `tests/e2e/test_order_product_details.py`:
  - **Setup.** Capture an order with every `/dp/<ASIN>` routed to `amazon_robot_check.html` (created in T029; write this test after T029 if doing it in order). Every product is then missing.
  - **Order page.** Wait for `#details-progress`, and assert `a.open-listing` on each line.
  - **One listing.** Capture one listing through the agent, with `/dp/<ASIN>` now fulfilled by `amazon_listing.html`. Confirm the collapsed page, then wait until `#details-progress` shows the reduced count.

### Implementation for User Story 3

- [X] T023 [US3] In `order_detail` (`app/product/routes.py`), when `vendor == AMAZON_VENDOR`, compute `missing = service.products_missing_details({p.product_id for p in lines if p.product_id})` and pass the following to the template:
  - `details_missing` (the set)
  - `details_checklist=True`
  - the distinct missing and total product counts
- [X] T024 [US3] In `app/templates/product/order.html`, when `details_checklist` is set:
  - render `#details-progress` above the table per contracts/order-payload.md §4
  - add a "Details" column with a `.details-captured` or `.details-missing` badge
  - add `a.open-listing` (`target="_blank" rel="noopener"`) built from `purchase.vendor_item_id`, omitted when blank

  Other vendors' markup must be unchanged.
- [X] T025 [US3] In `product_detail` (`app/product/routes.py`), pass `listing_link` when the product has a VENDOR identifier with vendor `Amazon` and `not product.specifications`. In `app/templates/product/detail.html`, render `#details-missing-notice` with that link at the top of the product content (contracts/order-payload.md §5).
- [X] T026 [US3] Rewrite `#order-page-detail-note` in `app/templates/product/order_review.html` (FR-021). Say that new products carry only what the order page stated, that after confirming the order's page lists them with a link to each listing, and that the bookmarklet there adds the details without recording another purchase. Remove the undelivered promise. US4 extends this note. Correct the matching claim in `_create_amazon_product`'s docstring in `app/catalog_service.py`.

**Checkpoint**: The order page is a working checklist, and US1/US2 complete it one product at a
time.

---

## Phase 6: User Story 4 — One order capture reads every listing (Priority: P3)

**Goal**: The order bookmarklet reads each line's listing, and confirmation writes its details.
Unreadable lines fall back to the checklist. Re-capturing fills already-captured lines
(FR-022–FR-030).

**Independent Test**: With listings routed to the fixture, one agent run plus one confirmation
yields products with specification rows. A line routed to the robot-check fixture reads "details
not read" and appears on the checklist.

### Tests for User Story 4

- [X] T027 [P] [US4] Model and service tests in `tests/unit/test_order_product_details.py`:
  - **Payload parsing.** `AmazonOrderLine.from_payload` reads a `listing` object (via `ListingCapture.from_data`) and a `listing_problem`. A malformed `listing` object yields `listing=None` with a problem string, never a refused line. A line with neither key is unchanged.
  - **`line_products`.** `capture_order_lines` reports one entry per NEW, MATCHED, adopted and already-captured line, and none for an excluded line.
  - **`wrote_anything`.** It is true when only `products_detailed` is non-zero.
- [X] T028 [P] [US4] Route tests in `tests/unit/test_order_product_details.py` for `POST /products/amazon/orders/capture`, with `store_listing_images` mocked:
  - **New product.** A NEW line carrying a listing yields a product with the listing's manufacturer, part number and rows.
  - **Matched product.** A MATCHED line fills only blanks; a held manufacturer is kept.
  - **Not read.** A `listing_problem` line yields a thin product that the order page lists as missing.
  - **Shared ASIN.** Two lines with one ASIN are applied once.
  - **Re-capture (FR-030).** Re-posting the same order with listings fills the already-captured lines' products, writes no purchase, and flashes "Details added to N product(s)" without leading on "Nothing new to capture".
  - **Review rendering.** The review renders `.line-listing-summary` and `.details-not-read` with the reason.
- [X] T029 [P] [US4] Create `tests/e2e/fixtures/amazon_robot_check.html`: a minimal page with no `#productTitle`, shaped like a robot-check interstitial.
- [X] T030 [US4] Update `tests/e2e/test_amazon_order.py` and `tests/e2e/test_amazon_receive.py` for research.md §11:
  - In each test that captures an order, fulfil `/dp/<ASIN>` (the `LISTING_ROUTE` pattern from `test_product_page_capture.py`) with `amazon_listing.html`, or assert `.details-not-read` where the test is about the unread state.
  - Rewrite `test_the_review_says_the_products_will_be_thin` against the new `#order-page-detail-note` wording.
  - List each edited test and why in `verification.md`.
- [X] T031 [P] [US4] E2E journeys in `tests/e2e/test_order_product_details.py`:
  - **(a) One click.**
    - Every `/dp/<ASIN>` is fulfilled by `amazon_listing.html`.
    - Wait for `.line-listing-summary` on each review line, then confirm.
    - Wait for `#details-progress` to read "Every product on this order has its details".
    - Record the serialized length of the review's `#order-payload` value in `verification.md` as the measurement behind T001.
  - **(b) One line throttled.**
    - One ASIN is routed to `amazon_robot_check.html`.
    - Wait for `.details-not-read` on that line, then confirm.
    - Wait for `#details-progress` to read "1 of".
    - Assert that line's `a.open-listing`.

### Implementation for User Story 4

- [X] T032 [US4] In `app/models.py`, add `listing: Optional[ListingCapture] = None` and `listing_problem: str = ''` to `AmazonOrderLine`, parsed in `from_payload` per data-model.md.
- [X] T033 [US4] In `app/models.py`, add `line_products: tuple = ()` and `products_detailed: int = 0` to `OrderCaptureResult`, and include `products_detailed > 0` in `wrote_anything`.
- [X] T034 [US4] In `capture_order_lines` (`app/catalog_service.py`), collect `(line.form_key, product_id)` for every created or attached purchase, every adopted purchase, and every already-captured line (`existing.product_id`), and return them as `line_products`. Nothing else in the method changes.
- [X] T035 [US4] In `_confirm_page_order` (`app/product/routes.py`), after `capture_order_lines` succeeds, add a helper `_apply_order_listings(service, order, result)`:
  - **Which lines.** For each distinct product in `result.line_products` whose line carries `listing`: call `service.apply_listing_details(product_id, listing, proposed={'manufacturer': listing.brand, 'manufacturer_part_number': listing.manufacturer_part_number()})` with no replacements, then `store_listing_images(product_id, listing.images, _get_storage_backend(), vendor_item_id=line.asin)`.
  - **Errors.** Catch and log a `ValidationError` or `ItemNotFoundError` per product so it never un-writes the order (FR-031).
  - **What it returns.** `products_detailed` and the summed image counts.
  - **Summary.** Pass `dataclasses.replace(result, products_detailed=...)` to `_order_capture_summary`.
- [X] T036 [US4] In `_order_capture_summary` (`app/product/routes.py`):
  - **"Details added to N product(s)".** Add it inside the "wrote something" block, above the "Nothing new to capture" fallback, per the function's docstring rule.
  - **The image tally.** Add it when pictures were attempted.
  - **The thin-products sentence.** Replace it with "K product(s) still need details — see below" when K > 0, where K is the not-read lines' products still missing. `_confirm_page_order` computes K with `products_missing_details`.
- [X] T037 [US4] In `app/templates/product/order_review.html`, for Amazon lines:
  - **`.line-listing-summary`.** Brand, row count, picture count, and barcode found (a row whose name `_is_barcode_row_name` accepts; expose a template-safe property on `ListingCapture` rather than calling a private function from Jinja).
  - **`.details-not-read`.** The badge, with the reason.
  - **The `#order-page-detail-note` variants.** Extend the note per contracts/order-payload.md §2, with `data-listings-read` and `data-listings-missing`.
- [X] T038 [US4] In `app/static/js/capture-agent.js`, in the `amazon-order` branch:
  - **The loop.** Replace the immediate `submitCapture` with an async function that, for each distinct ASIN among `order.lines`, sequentially calls `fetch(location.origin + '/dp/' + asin, {credentials: 'same-origin'})`.
  - **A listing counts as read only when all three hold:**
    - `response.ok`
    - `response.url` still names that ASIN, matched with `ASIN_PATTERN`
    - `titleFrom(doc)` is non-empty after `DOMParser`
  - **Recording the result.** On success set `line.listing = extract(doc, location.origin + '/dp/' + asin, asin)` on every line with that ASIN. Otherwise set `line.listing_problem` to the contract's wording. A line with no ASIN gets "no item number on the order line".
  - **Progress.** Show `#workshop-capture-progress`, a fixed-position, inline-styled element reading "Workshop capture: reading listing i of n…", updated per fetch and removed before `submitCapture`.
  - **Failure handling.** A thrown error on one ASIN is caught and recorded; it never stops the loop or the submission.
  - **No fixed delay between fetches.**
  - **Comment the design** referencing research.md §5, including why there is no fallback to the open tab.

**Checkpoint**: One click captures a fully detailed order, and failures degrade to the US3
checklist.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T039 [P] Rewrite the Amazon Orders section of `docs/user-manual.md` (anchor `#amazon-orders`) to describe the guided process:
  - the bookmarklet reads each listing
  - what "details not read" means
  - the order page's checklist and "Open listing" links
  - the details-only choice and the collapsed message on a listing capture
  - re-running the order bookmarklet to fill products already captured

  Mention the per-field replace ticks. Keep American spelling ("catalog").
- [X] T040 Run `grep -ric "catalogue" README.md docs/ app/ tests/`; it must print nothing. Then run `grep -rn "catalogd\|catalogng\|uncatalogd" app/ tests/`; it must also print nothing.
- [X] T041 Run `nox -s tests` and fix every failure. Tests outside those edited under T017/T030 must pass **unedited**, notably `tests/unit/test_capture.py` and `tests/e2e/test_repeat_purchase.py` (research.md §11).
- [X] T042 Run `nox -s e2e` detached (`nohup ... > log &`; it takes about 17 minutes, past the Bash tool's 10-minute cap) and wait for it to finish. Fix failures by waiting on state, never on time (CLAUDE.md). Confirm `git status` is clean afterwards.
- [X] T043 Regenerate screenshots with `nox -s screenshots_headless`, then run `nox -s screenshots_verify`. Commit only the screenshots of the pages this feature changed (capture confirmation, order review, order page, product page); revert other churn with `git checkout -- docs/images/screenshots/<file>`.
- [X] T044 Complete `specs/044-order-product-details/verification.md`:
  - the red-then-green record for T004
  - the edited-tests list
  - the payload measurement from T031
  - a line per success criterion (SC-001–SC-007) naming the test that shows it

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none. T001–T003 are independent of each other.
- **Foundational (Phase 2)**: T004 first (red). T005 → T006, both in `app/models.py`. T007 → T008 → T009, all in `app/catalog_service.py`. T010 last.
- **US1 (Phase 3)**: needs Phase 2.
- **US2 (Phase 4)**: needs US1's T013–T015, since it extends the same template block and route branch.
- **US3 (Phase 5)**: needs Phase 2 only (T007). T022 needs US2 and T029.
- **US4 (Phase 6)**: needs Phase 2's `apply_listing_details` (T009) and US3's order page for its fallback assertions.
- **Polish (Phase 7)**: needs every story.

### User Story Dependencies

```text
Phase 2 ──► US1 ──► US2 ──┐
   │                      ├──► Polish
   └──────► US3 ──► US4 ──┘
```

### Within Each Story

The tests are written first and seen failing where they exercise new behavior. Then models,
service, route, and finally template.

## Parallel Opportunities

- **Phase 1**: T001, T002 and T003 can all run at once.
- **US1**: T011 and T012 (test files) can run in parallel with each other. T013 → T014 → T015 run in sequence, because they share `routes.py` and `capture.html`.
- **US2**: T016, T017 and T018 can run in parallel.
- **US3**: T021 and T022 can run in parallel. T023/T025 (routes) and T024 (`order.html`) touch different files.
- **US4**: T027, T028, T029 and T031 can run in parallel. T032 → T033 (same file). T038 (the agent) is independent of T034–T037.

### Parallel Example: User Story 4

```text
Together: T029 (robot-check fixture), T038 (capture-agent.js), T032+T033 (models.py)
Then:     T034 (catalog_service.py) → T035+T036 (routes.py) → T037 (order_review.html)
```

## Implementation Strategy

### MVP (US1 + US2)

1. Phase 1 and Phase 2. T004 is red.
2. US1: details-only works from the landing page.
3. US2: the collapsed message. T004 is green, so **the reported defect is fixed**.
4. Validate with quickstart.md §2's US1/US2 rows before continuing.

### Incremental Delivery

5. US3: the checklist, which also repairs every thin product already in the catalog one listing at a time.
6. US4: auto-fetch, plus re-capture filling (FR-030), which repairs a whole existing order in one click.
7. Polish: docs, the full suites, screenshots and verification.

All stories ship in one pull request, which is this feature's delivery. The phases order the work,
and each checkpoint is a point where the suite is green.
