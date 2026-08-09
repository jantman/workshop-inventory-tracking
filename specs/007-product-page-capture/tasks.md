---

description: "Task list for Product Page Capture"
---

# Tasks: Product Page Capture

**Input**: Design documents from `specs/007-product-page-capture/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Branch**: `issues/57`

**Tests**: Included, and **not optional here**. Constitution IV requires that "changes that alter behavior MUST land with tests covering that behavior", and every task below alters behavior. One existing E2E test asserts the opposite of what this feature makes true and is rewritten by a numbered task. Coverage is *not* a target — write the test that would have caught the bug, and stop.

**Organization**: Grouped by user story. The foundational phase builds the transport — the loader, the agent skeleton, the payload type and the hidden field that carries it — because every story rides it and none of them can be demonstrated without it. The migration belongs to US4 and nothing else needs it, so the MVP and the two stories after it ship without touching the schema.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: Which user story the task serves (US1–US6)
- Every task names the file it changes

## Path Conventions

Existing Flask app at the repository root: `app/` for source, `app/static/js/` for browser code, `tests/unit/` and `tests/e2e/` for tests, `migrations/versions/` for Alembic. No new top-level directory.

---

## Phase 1: Setup

**Purpose**: Know that anything that breaks later, this feature broke.

- [X] T001 Establish a green baseline on `issues/57` before changing anything: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and the same for `-s e2e` (15-minute tool timeout). Record any pre-existing failure rather than silently inheriting it.
- [X] T002 Add `requests==2.33.1` to `requirements.txt` after `PyMuPDF`. **This is not a new dependency** — it is installed today as a transitive of `google-api-python-client` and already imported by `app/api_client.py:20`; pinning what we import is a correction. Re-run `nox -s tests` to confirm the pin resolves.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The transport. A loader bookmarklet, an agent that posts a payload, a type that parses it, and a hidden field that carries it across every re-render. Every story depends on all four; none can be shown working without them.

**⚠️ CRITICAL**: No user story work begins until T003–T008 are done.

- [X] T003 Add the `ListingCapture` dataclass to `app/models.py` alongside `CaptureAssessment` (line 484), with the fields in [data-model.md](./data-model.md#listingcapture) — all `Optional`/defaulted except `source_url`, and `price` typed `Optional[str]`. Add the `from_json(raw)` classmethod, which returns **`None` rather than raising** for an absent, empty, non-object, or wrong-`version` payload, and which drops malformed `specifications` entries and non-`http(s)` `images` entries individually instead of refusing the whole payload ([contracts/capture-payload.md](./contracts/capture-payload.md#what-the-server-guarantees)). A capture whose payload cannot be read must still work exactly as it does today — that is FR-007, and it is the reason this parses leniently rather than strictly.
- [X] T004 Rewrite `_capture_bookmarklet` in `app/product/routes.py:399` as a **loader**: it creates a `<script>` element pointing at `url_for('static', filename='js/capture-agent.js', _external=True)` with `'?v=' + Date.now()` appended, sets `dataset.endpoint` to `url_for('product.api_capture', _external=True)`, and appends it to the body. The cache-buster is what makes FR-024 true — the operator never re-drags the bookmarklet and never runs a stale agent. Rewrite the docstring: it no longer reads `location.href` or builds a form, and the TLS caveat it already documents still applies unchanged.
- [X] T005 Create `app/static/js/capture-agent.js` with the transport half only — no extraction yet. It reads its endpoint from `document.currentScript.dataset.endpoint`, builds a form with `method=POST`, `target=_blank` and hidden inputs for `url`, `listing_title` and `listing` (the last holding `JSON.stringify({version: 1, source_url: location.href})`), appends it, submits, and removes it. Match the file style of the twenty-two scripts already in `app/static/js/` — IIFE, `'use strict'`, a docstring comment naming what it does and why it submits a form rather than issuing a `fetch`.
- [X] T006 Add a hidden `listing` input to `app/templates/product/capture.html` inside the form (after the CSRF token at line 10), valued `{{ form_data.get('listing') or '' }}`. **This one line is the whole of FR-016**: the template already re-emits `form_data` on a `CaptureDecisionRequired` re-render, so the payload survives the decision round trip with no code of its own. Do not put it inside any `{% if %}`.
- [X] T007 In the form branch of `api_capture` (`app/product/routes.py:486`), pass `data.get('listing') or ''` through into the `form_data` dict handed to the template. **Do not parse it here** — nothing is written by this representation, so there is nothing yet to validate, and parsing belongs at the point of use ([contracts/http-routes.md](./contracts/http-routes.md#post-apicapture--form-representation)).
- [X] T008 Unit tests in `tests/unit/test_capture.py` (new `TestTheListingPayload` class): `ListingCapture.from_json` returns `None` for `None`, `''`, `'not json'`, `'[]'` and a `version: 2` payload; drops a specification entry that is not a `{name, value}` pair while keeping its siblings; drops a `javascript:` image address while keeping the `https:` ones; and a form-encoded `POST /api/capture` carrying a `listing` field renders the capture form with that field's value echoed back in the HTML. Assert `service.list_products()` is still empty afterwards — a payload arriving must still write nothing.

**Checkpoint**: `nox -s tests` green. The bookmarklet loads a script that posts a near-empty payload, the form echoes it back, and nothing about the captured record has changed yet.

---

## Phase 3: User Story 1 — The listing fills the form in (Priority: P1) 🎯 MVP

**Goal**: Price and brand arrive from the listing without the operator typing them, read from the canonical page for the item rather than whatever variant the tab drifted to. Closes issue #56 points 2 and 3.

**Independent Test**: Capture from a listing page that shows a price and a byline brand; the confirmation page arrives with both pre-filled; confirm and verify both are recorded. Then capture from a page the agent cannot read and verify the form arrives exactly as it does today.

### Implementation for User Story 1

- [X] T009 [US1] In `app/static/js/capture-agent.js`, add canonical resolution: pull the ASIN from `location.pathname` with the same `/(?:dp|gp/product|product)/([A-Z0-9]{10})` shape `_asin_from_url` uses at `app/product/routes.py:572`, same-origin `fetch('/dp/<ASIN>')`, and parse with `DOMParser`. **Every failure falls back to the live `document`** — no ASIN, a failed fetch, a failed parse. Set `source_url` to the document actually read from. This is FR-002, and its fallback is FR-007; a tab that has silently picked up `?th=1` is the case it exists for ([research.md](./research.md#reading-the-canonical-listing-rather-than-the-open-tab)).
- [X] T010 [US1] In the same file, extract `price` from `.a-price .a-offscreen` and `brand` from the byline, and emit both into the payload. **`price` must be serialized as a JSON string, never a number** — strip the currency symbol and thousands separators and keep the digits and the decimal point as text. A JSON number is an IEEE double and would be a `float` before any Python here sees it, which Principle III prohibits with no in-transit exemption ([contracts/capture-payload.md](./contracts/capture-payload.md#price-is-a-string-and-this-is-not-negotiable)). Omit a key entirely when the selector finds nothing; never emit `""`.
- [X] T011 [US1] In `product_capture` in `app/product/routes.py:349`, parse the payload with `ListingCapture.from_json(request.form.get('listing'))` and use it to fill **only the blanks**: where `request.form['manufacturer']` is empty and `listing.brand` is set, pass the brand; same for `unit_price` and `listing.price`. A value the operator typed always wins (US1 scenario 3). `listing is None` must leave every existing line of this handler behaving as it does now.

### Tests for User Story 1

- [X] T012 [P] [US1] Rewrite `test_the_bookmarklet_is_offered_and_points_at_this_server` at `tests/e2e/test_order_capture.py:278`. Its three content assertions — `location.href`, `document.title`, `createElement('form')` — are all false of a loader and must not simply be deleted: replace them with the properties that now matter, that the href still starts with `javascript:`, that it names `capture-agent.js`, that it carries the external `/api/capture` endpoint, that it cache-busts, and that `fetch(` still does not appear in the bookmarklet itself. The form submission moved into the agent; assert it there, not here.
- [X] T013 [P] [US1] Add `tests/e2e/fixtures/amazon_listing.html` — a snapshot page carrying the structures the six sampled listings exhibited: an inline gallery data block naming **more images than there are thumbnails**, a `.a-price .a-offscreen` price, a byline brand, both description forms (only one active at a time is fine — add a second fixture or a query flag), and at least two product-information containers. It is a fixture, not a copy: hand-write the minimum structure rather than saving a real page.
- [X] T014 [US1] Add `tests/e2e/test_product_page_capture.py` with the US1 scenarios, using `page.route` to fulfil a fake `https://www.amazon.com/dp/...` address with the fixture (the mechanism is already used at `tests/e2e/test_label_printing.py:283`), then injecting the agent from the live server. Assert the confirmation page arrives with `#unit_price` and `#manufacturer` populated. Wait on `expect(page.locator("#capture-form"))` before reading any field — the landing is a navigation, so the form's presence is the completion signal (pattern C), and a `get_attribute` on a page that has not landed reads empty.
- [X] T015 [US1] Unit tests in `tests/unit/test_capture.py` (`TestTheListingFillsTheForm`): posting `/products/capture` with a `listing` carrying a price and brand records both; the same post with `manufacturer` and `unit_price` filled by the operator records **the operator's** values; a post with no `listing` field behaves identically to today (assert against the existing capture test's expectations, not a new baseline); and a `listing` whose `price` is a JSON *number* is still handled without a `float` reaching storage.

**Checkpoint**: One click on a real listing fills in the price and the brand. Nothing else is captured yet. Shippable, and it closes #56 points 2 and 3 on its own.

---

## Phase 4: User Story 2 — Every gallery image, at full resolution (Priority: P2)

**Goal**: All gallery images the listing's page data names — not just the thumbnails on screen — stored at original resolution against the product, and browsable as a grid.

**Independent Test**: Capture from the fixture whose data names more images than thumbnails; confirm; verify the stored count matches the data's count, that each stored file is the untokened original, and that the product page shows them as a grid.

### Implementation for User Story 2

- [X] T016 [P] [US2] Add the `ImageCaptureResult` dataclass to `app/models.py` — `stored`, `duplicates`, `skipped`, `failed` as `int`, `cap_reached` as `bool`, all defaulted to zero/False. Counts and one flag, no per-image error list: nothing would consume one, because the operator's next action is the same whichever way an image failed ([data-model.md](./data-model.md#imagecaptureresult)).
- [X] T017 [P] [US2] In `app/photo_service.py`, raise `MAX_ATTACHMENTS_PER_PRODUCT` from 25 to 100 (line 57). Leave `MAX_PHOTOS_PER_ITEM` at 10 and leave the comment above it explaining why the two are separate constants — that reasoning is unchanged.
- [X] T018 [US2] In `_upload_attachment` in `app/photo_service.py:620`, populate `sha256_hash=hashlib.sha256(file_data).hexdigest()` on the `Photo` at line 643. Hash the **bytes as received**, which is what `_process_photo` returns unchanged as `original_data` (line 486) — hashing a Pillow output would not be stable across Pillow versions. This closes the note the column has carried since `8213852b0b94`. **Do not change `upload_photo`** (line 114): nothing deduplicates inventory item photos and no requirement asks for it.
- [X] T019 [US2] Add `upload_product_attachment_if_new` to `app/photo_service.py` next to `upload_product_attachment` (line 569): hash the bytes, query for a `ProductAttachment` on this product joined to a `Photo` with a matching `sha256_hash`, return `None` if one exists, otherwise delegate to `upload_product_attachment` so validation, processing, the cap and the `ValueError` contract are shared rather than reimplemented ([contracts/catalog-service.md](./contracts/catalog-service.md#upload_product_attachment_if_new--new)). Scope the query to the product; cross-product blob sharing is an optimization nothing has asked for.
- [X] T020 [US2] Create `app/services/listing_images.py` with `store_listing_images(product_id, urls, storage_backend, timeout=10.0) -> ImageCaptureResult`, following the per-image sequence in [data-model.md](./data-model.md#image-storage-path): skip an address already seen in this call, fetch with `requests.get(..., timeout=timeout)`, count and continue past a non-200/timeout/connection failure, count and continue past an unsupported content type or an oversize body, and stop with `cap_reached` on the `ValueError` naming the cap. **It never raises for a per-image problem** — that is FR-020, and it is what allows the capture to have already succeeded before the first image is attempted. Derive filenames as `{vendor_item_id or 'listing'}-{index:02d}{ext}`; Amazon's own filenames are opaque hashes.
- [X] T021 [US2] In `app/static/js/capture-agent.js`, extract the gallery: read the hi-res addresses out of the page's **inline image data block**, not out of the DOM — the thumbnail strip shows a subset and the full-size images are not in the DOM until the gallery is interacted with, which is the finding that ruled out every archiving approach (FR-003). Strip the transform token by replacing the `\._[^./]*_\.` segment before the extension with `.` (FR-004). Emit them into `images`, gallery first.
- [X] T022 [US2] In `product_capture` in `app/product/routes.py`, call `store_listing_images(purchase.product_id, listing.images, ...)` **after `capture_order` returns** and before the redirect, and flash the tally — stored, and any of failed/skipped/duplicates/cap that are non-zero (FR-020, FR-021, FR-022). The ordering is the contract: the operator lands on a finished capture. This is what makes the POST take 8–15 seconds for a full gallery, which is expected, not a defect ([research.md](./research.md#why-image-retrieval-is-synchronous)).
- [X] T023 [US2] Add a "what will be written" panel to `app/templates/product/capture.html`, above the submit button at line 179, rendering counts from the parsed payload — for now, the number of images (FR-017). Rows and description are added to this same panel by T031 and T038. It must render nothing at all when there is no payload, so the paste-a-URL path is visually unchanged.
- [X] T024 [P] [US2] Replace the attachment list in `app/templates/product/detail.html:194–209` with a thumbnail grid: each attachment an `<img>` sourced from `url_for('main.get_photo_data', photo_id=...) + '?size=thumbnail'` — the route already accepts `thumbnail`, `medium` and `original` (`app/main/routes.py:2729`) — wrapped in the existing link to the original, with the delete button retained. PDFs already have rendered thumbnails via `_process_pdf`, so a datasheet appears as its first page rather than a broken image. Keep `#attachment-list`, `.attachment-row` and `#no-attachments` as ids/classes so `tests/e2e/test_product_attachments.py` and `product-attachments.js` keep working.

### Tests for User Story 2

- [X] T025 [P] [US2] Create `tests/unit/test_listing_images.py` covering every branch of `store_listing_images` with `requests.get` patched: success; timeout; non-200; unsupported content type; body over `MAX_FILE_SIZE`; the same address twice in one list fetched once; identical bytes at two different addresses stored once; and the cap reached mid-list setting `cap_reached` and stopping. Assert `timeout` is actually passed to `requests.get`. The unit suite blocks the network, so an unmocked call fails loudly — do not add a network marker to work around that.
- [X] T026 [P] [US2] Unit tests in `tests/unit/test_product_attachments.py`: an uploaded attachment now carries a non-null `sha256_hash`; `upload_product_attachment_if_new` returns `None` for a second upload of identical bytes to the same product and an attachment for the same bytes on a *different* product; and the cap refuses at 100 rather than 25.
- [X] T027 [US2] Add a local image host to the E2E fixtures — a stdlib `http.server` thread serving `tests/e2e/fixtures/images/` (six real JPEGs already in the repository), started and stopped by a fixture. The application must perform a genuine HTTP fetch of genuine bytes from an origin the test controls; `page.route` cannot help here because the *server* does the fetching, not the browser.
- [X] T028 [US2] E2E in `tests/e2e/test_product_page_capture.py`: a capture whose payload names six images stores six attachments on the product; the product page shows six thumbnails in the grid; a payload naming one unreachable address stores the rest and the flash names the failure; and a payload naming the same image twice stores it once. Establish the grid with `expect(...).to_have_count(...)` before any `count()` read — a JS-free server-rendered grid still must not be snapshot-read before the navigation lands.

**Checkpoint**: A capture brings the whole gallery with it, at full resolution, browsable on the product page. Still no schema change.

---

## Phase 5: User Story 3 — "Product information" becomes something you can filter on (Priority: P3)

**Goal**: The listing's product-information rows become named specifications on the product, merged so that nothing the operator typed is touched.

**Independent Test**: Capture a listing carrying product information onto a new product and verify each row is a filterable specification. Then hand-edit one, re-capture, and verify the edit survives and nothing was removed.

### Implementation for User Story 3

- [X] T029 [US3] Add `merge_specifications(product_id, entries) -> int` to `app/catalog_service.py` near `update_product` (line 539). Validate through the existing `_validate_specifications` (line 1965) **row by row rather than as a batch**, so one over-length name costs one row and not the other twenty-four (US3 scenario 8). Fold names with `str.lower()` **in Python, never in SQL** — the deployed collation folds accents as well as case and would call `Volt` and `Vôlt` one name while SQLite calls them two, which is the reasoning `ProductSpecification`'s own docstring already gives. Drop a captured row whose folded name the product already carries, value and all. Append survivors after the highest existing `display_order` so no existing row moves. **Remove nothing, ever** — FR-011 is a property of this method, not of its callers. Leave `update_product`'s replace-on-write (line 589) untouched; the form posts a complete set and a capture does not.
- [X] T030 [US3] Add the `listing: Optional[ListingCapture] = None` parameter to `capture_order` in `app/catalog_service.py:877`, after the existing ones so no positional caller breaks, and apply it **after the product is resolved and before `record_purchase`** (line 1053). The merge target is not known until the recycled-identifier question has been settled, so applying it any earlier applies it to the wrong product. Call `merge_specifications` when `listing.specifications` is non-empty. Do not write `manufacturer` onto an existing product here — `capture_order` already deliberately does not (line 1046), because a mismatch there is the evidence the recycled-identifier question depends on. Forward the parsed payload from `product_capture`.
- [X] T031 [US3] In `app/static/js/capture-agent.js`, extract product information: gather rows from **all** of the containers the listing carries — issue #57 found `#prodDetails` on all six sampled listings ranging 6–25 rows, `overview` on four, `techSpec` on two, `poExpander` on one — merge them into one list, fold duplicate names case- and whitespace-insensitively with first occurrence winning, and emit as `specifications`. **Filter nothing by name**: Best Sellers Rank, Customer Reviews and Date First Available are emitted like everything else (FR-008). Extend the T023 panel to state how many rows will be written.

### Tests for User Story 3

- [X] T032 [P] [US3] Unit tests in `tests/unit/test_capture.py` (`TestCapturedSpecifications`): rows land as specifications in order; a capture onto a product with an existing `Material` row leaves that value untouched while adding the names it does not have; nothing is ever removed; a row whose name exceeds 100 characters is dropped while its siblings land; names differing only in case or surrounding whitespace collapse to one; and a bookkeeping row such as `Best Sellers Rank` is stored rather than filtered.
- [X] T033 [P] [US3] A unit test asserting the fold happens in Python: two rows named `Volt` and `Vôlt` on the same product remain two distinct specifications. This is the test that fails if the comparison ever migrates into SQL, and it passes under SQLite for the same reason it passes under MariaDB only when the comparison is Python-side.
- [X] T034 [US3] E2E in `tests/e2e/test_product_page_capture.py`: capture a payload with product-information rows, confirm, and verify they appear on the product page and that a specification filter returns that product. Then re-capture with a changed value for a name the product already has and verify the stored value did not change.

**Checkpoint**: A capture produces filterable catalogue data rather than an archive. Still no schema change.

---

## Phase 6: User Story 4 — Keep the description the listing was sold on (Priority: P4)

**Goal**: The listing's description text — either form — is kept with the product, along with the images that are genuinely part of it.

**Independent Test**: Capture from a listing with a plain description and from one with a rich block; verify in each case the text is stored and readable on the product page, and that layout furniture from the rich block was not stored.

### Implementation for User Story 4

- [X] T035 [US4] Change `ProductSpecification.value` in `app/database.py:1180` to `Column(Text().with_variant(MEDIUMTEXT, 'mysql'), nullable=False)`, following the dialect-variant pattern `Photo.medium_data` already uses at line 707. Under SQLite it stays `TEXT`, which is unbounded there, so the unit suite is unaffected and proves nothing about the widening — that is expected, because the limit being lifted is a MariaDB limit.
- [X] T036 [US4] Add Alembic revision `b1a0c0d10009` on head `b1a0c0d10008` in `migrations/versions/b1a0c0d10009_widen_specification_value.py`. `upgrade`: `MODIFY value MEDIUMTEXT NOT NULL` — no backfill, because every existing value already fits the larger type; restate `NOT NULL` because MariaDB's `MODIFY` replaces the whole column definition and would otherwise silently make it nullable. `downgrade`: **count rows over 65,535 bytes first with `LENGTH(value)` and raise naming their ids and products rather than performing the `MODIFY`** — `LENGTH` and not `CHAR_LENGTH`, because the type bounds bytes and counting characters would wave multi-byte text through into a silent truncation. Principle I never licenses losing data. Wrap raw SQL in `sa.text(...)`.
- [X] T037 [US4] Exercise the migration both ways against a **disposable MariaDB container**, never the deployment, following [quickstart.md](./quickstart.md#exercise-the-migration-both-ways). Both directions, then the guard: a 70,000-byte value must make `downgrade` fail, name the row, and leave the data intact. **Neither test suite runs Alembic and the change is MariaDB-only, so this task is the only coverage this revision will ever have.** It is not optional.
- [X] T038 [US4] In `app/static/js/capture-agent.js`, extract the description. It is strictly either/or — issue #57 found the plain block on three sampled listings and the rich block on the other three, never both — so read whichever is present and emit its text as `description_text`, uncapped (FR-006; the widening in T036 is what makes "uncapped" safe). For a rich block, also emit its images into `images`, keeping only those measuring **at least 300 pixels on both edges**, read from the address's dimension token or the element's width/height attributes; where the dimensions cannot be established at all, **keep the image** (FR-019). Gallery images are exempt from this filter — the filter runs here, in the browser, which is what lets the server carry one flat list and not be trusted with the distinction. Extend the T023 panel to say a description was found.
- [X] T039 [US4] In `capture_order` in `app/catalog_service.py`, write `listing.description_text` as one further merged row named `Description`, through the same `merge_specifications` call as T030 so it obeys the same "already present wins" rule. A product that already has a `Description` keeps the one it has.

### Tests for User Story 4

- [X] T040 [P] [US4] Unit tests in `tests/unit/test_capture.py` (`TestCapturedDescription`): a plain description lands as a `Description` specification; a rich one lands the same way; a payload with no description records nothing and is not refused; a description far longer than the product's own 255-character `description` field is stored in full and does **not** displace the operator's label wording; and a product already carrying a `Description` row keeps its existing value.
- [X] T041 [P] [US4] Unit tests for the size filter's server-side consequence in `tests/unit/test_listing_images.py`: the fetcher stores whatever addresses it is given without re-filtering. The filter itself is browser-side and is covered by T042; asserting it twice in two places would make the server look like it enforces something it does not.
- [X] T042 [US4] E2E in `tests/e2e/test_product_page_capture.py` against a fixture rich-description block containing a 1×1 spacer, a 970×20 rule, a 16×16 bullet, a 150 px mark and two ≥300 px content images: exactly the two content images are stored, and the description text appears on the product page.

**Checkpoint**: A capture keeps everything the listing said. The schema change has landed on its own, where a rollback is a single revision.

---

## Phase 7: User Story 5 — A question in the middle does not lose the capture (Priority: P5)

**Goal**: A capture that stops to ask a question keeps its whole payload, and a re-capture does not duplicate what the product already holds.

**Independent Test**: Capture the same listing twice on the same day so the duplicate question is raised, answer it, and verify the second capture writes the same images and specification rows the first one would have — and no second copy of any image.

**Note**: The round-trip half of this story should already work, because T006 put the payload in a field the template re-emits. These tasks are what make that a *tested property* rather than a happy accident — the failure mode being guarded against is a later change to `capture.html` quietly dropping the field.

### Tests and verification for User Story 5

- [X] T043 [P] [US5] Unit tests in `tests/unit/test_capture.py` (`TestThePayloadSurvivesAQuestion`): a `POST /products/capture` carrying a `listing` that triggers `CaptureDecisionRequired` re-renders the form with the payload still present in the HTML, and writes nothing; re-posting with the decision answered writes the images and rows once, not twice; and a capture that raises **both** questions at once and is answered lands the payload exactly once.
- [X] T044 [P] [US5] E2E in `tests/e2e/test_product_page_capture.py`: capture a listing, then capture it again the same day to raise the duplicate question, answer "record it anyway", and verify the second purchase exists with the specifications merged and **no second copy of any image** on the product.
- [X] T045 [US5] E2E for abandonment: land a bookmarklet capture carrying a full payload, navigate away without submitting, and verify no product, no purchase, no specification and no photo row exists. Assert the *absence* against an established page — per `CLAUDE.md`, a negative assertion against a list that has not rendered passes trivially, so establish the product list with `expect(...)` first and only then assert the item is absent.

**Checkpoint**: The capture is reliable in exactly the case it is most often used — buying something again.

---

## Phase 8: User Story 6 — Paste an image straight onto a product (Priority: P6)

**Goal**: An image on the clipboard becomes an attachment on the product being viewed.

**Independent Test**: With an image on the clipboard, paste on a product page and verify it is stored and appears.

- [X] T046 [US6] Add a `paste` handler to `initProductAttachments` in `app/static/js/product-attachments.js:37`: read `event.clipboardData.items`, take the first entry whose `type` starts with `image/`, and hand its `getAsFile()` to the existing `upload()` helper against `/api/products/${productId}/attachments`. No new endpoint and no route change — the same `FormData` shape the file picker already posts, through `csrfFetch`, same-origin so the token travels. Clipboard content holding no image must upload nothing **and report nothing**: a rejection message on every ordinary text paste is noise.
- [X] T047 [US6] E2E in `tests/e2e/test_product_attachments.py`: write an image to the clipboard, paste on a product page, and assert the new card appears with `expect(cards).to_have_count(n)`. The upload POST is awaited before the card is appended, so the rendered card is a complete signal on its own — pattern C in `CLAUDE.md`, the cheapest correct wait there is. Also assert a text paste leaves the count unchanged, establishing the count first.

**Checkpoint**: All six stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

- [X] T048 [P] Update `docs/user-manual.md`, Product Catalogue → *Capturing an Order When You Place It*: the bookmarklet now brings the gallery, the specifications, the description, the price and the brand, and it still needs TLS. Say what the confirmation page shows before it writes, and that an abandoned capture leaves nothing.
- [X] T049 [P] Update the bookmarklet explanation in `app/templates/product/capture.html` (the card at line 190). Its current text says the bookmarklet "reads the page's URL and title and nothing else -- no page markup, which is not a contract and changes without warning". That is now false, and it is false *deliberately*: say that it reads the page, that the page's markup is not a contract, and that a capture which comes back thin is the signal — which is why the confirmation page tells you what it found before you commit it.
- [X] T050 Regenerate documentation screenshots (`nox -s screenshots_headless`) and commit them alongside, since `app/templates/product/**` and `app/static/js/**` both changed. Confirm `nox -s screenshots_verify` passes. The diff carries no signal — regeneration is not byte-reproducible, as recorded in feature 006's plan — and the workflow that checks it is informational.
- [X] T051 Run the full gate: `nox -s tests` and `nox -s e2e` (15-minute tool timeout), both green, working tree clean afterwards.
- [ ] T052 Work through [quickstart.md](./quickstart.md#what-no-suite-can-check) sections A and B by hand against real Amazon listings — the bookmarklet reaching the app over TLS with no `securitypolicyviolation`, an edit to `capture-agent.js` taking effect without a re-drag, and the six probed ASINs each reporting an image count matching issue #57's *page data* column rather than its thumbnail column. Verify one stored original is 1601×1601 / 358,055 bytes for `B0CKXJLP4B` rather than the 1446×1500 tokened rendition; the smaller one means T021's token stripping is not working and FR-004 is not met.

  **Not done, and not doable from here.** Every part of this task needs something
  only the operator has: this application served over TLS at its own address, the
  bookmarklet dragged into their own browser's bookmarks bar, and real Amazon
  listings. It is the acceptance step this feature was always going to end on --
  quickstart.md calls it "what no suite can check" for exactly this reason, and
  nothing in the automated suites substitutes for it. Everything it checks is
  implemented and covered against a fixture; what it establishes is that the
  fixture resembles Amazon.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001–T002)**: no dependencies.
- **Foundational (T003–T008)**: depends on Setup. **Blocks every user story** — there is no way to demonstrate any story without the transport.
- **US1 (T009–T015)**: depends on Foundational only.
- **US2 (T016–T028)**: depends on Foundational. Independent of US1.
- **US3 (T029–T034)**: depends on Foundational. Independent of US1 and US2.
- **US4 (T035–T042)**: depends on US3 — T039 calls the `merge_specifications` T029 adds and the `listing` parameter T030 adds. This is the one genuine cross-story dependency.
- **US5 (T043–T045)**: depends on US2 and US3 for anything to assert about; the round-trip half depends on Foundational alone.
- **US6 (T046–T047)**: depends on Foundational only, and barely — it touches no capture code at all and could be done first if it were more valuable.
- **Polish (T048–T052)**: after every story that is going to ship.

### Parallel opportunities

- T016 ‖ T017 ‖ T024 — `app/models.py`, `app/photo_service.py` and `detail.html`, no shared symbol.
- T025 ‖ T026 — different test files.
- T032 ‖ T033, T040 ‖ T041 — different classes; sequence them if same-file edits bother you.
- **US2 ‖ US3** is the real one: different service methods, different tests, no shared task. Two people could take them at once.
- US1, US3 and US4 all edit `capture-agent.js`, and US2/US3/US4 all extend the same panel in `capture.html`, so they parallelize poorly despite US1–US3 having no logical dependency on each other.
- US6 is fully independent of everything after Foundational.

### Within each story

- Agent before route before template, and service before route. The template renders what the service produced; building it first means building against a guess.
- The rewritten E2E bookmarklet test (T012) lands with the loader (T004), not after it. A commit where it still asserts `createElement('form')` against a loader is a commit where the suite is lying.

---

## Implementation Strategy

### MVP — User Story 1 only

1. T001–T002 (setup) → T003–T008 (foundational) → T009–T015 (US1).
2. **Stop and validate**: click the bookmarklet on a real Amazon listing over TLS and confirm the price and the brand arrive without typing.
3. Shippable. No schema change, no migration, and it closes issue #56 points 2 and 3.

### Incremental delivery

1. Foundational → US1 → **the listing fills the form in** (and #56 points 2 and 3 close).
2. + US2 → **the gallery survives the listing** — the requirement that ruled out every other approach, and the one the operator cannot reproduce later.
3. + US3 → **a capture becomes catalogue data** rather than an archive. Still no migration.
4. + US4 → **the description is kept**, and the schema change lands last among the capture stories, on its own, where a rollback is a single revision.
5. + US5 → **the repeat buy is safe**.
6. + US6 → paste-to-attach, independent of all of it.

Deferring the migration to US4 is deliberate: it is the only phase that touches the database and it belongs to the fourth-priority story. Three stories ship and can be lived with before it is exercised.

### Single-developer ordering

T001 → T052 in number order. The numbering is already a valid serial schedule; the [P] markers only matter if someone is working alongside.

---

## Notes

- **One existing test asserts the opposite of this feature.** `tests/e2e/test_order_capture.py:278` checks the bookmarklet contains `location.href`, `document.title` and `createElement('form')`; all three are false of a loader. T012 rewrites it. If a task deletes it instead, the property it protected — that the bookmarklet points at *this* server and is not a `fetch` — needs re-asserting somewhere or it has been quietly dropped.
- **Two rules that look alike and are not.** The agent folds specification names against *each other*, across the page's containers (T031). `merge_specifications` folds them against *the product's existing rows* (T029). Both are case-and-whitespace folds in the same feature and they answer different questions; a single shared helper would be a coincidence, not a reuse.
- **The size filter has exactly one home.** It runs in the agent (T038) because that is where dimensions are knowable, and T041 exists to assert the server does *not* re-filter. Two implementations of one rule is how the gallery exemption silently stops being an exemption.
- **The migration has no automated coverage.** T037 is the coverage. It runs against a throwaway container, and it is not optional.
- **`price` must be quoted in the JSON.** T010 is where this is won or lost, and the reviewer's whole check is whether the value has quotes around it.
- [P] means different files and no dependency on an incomplete task. Commit after each task or logical group.
