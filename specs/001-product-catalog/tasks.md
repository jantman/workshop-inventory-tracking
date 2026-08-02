---

description: "Task list for Product Catalog & Purchase Tracking"
---

# Tasks: Product Catalog & Purchase Tracking

**Input**: Design documents from `/specs/001-product-catalog/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included and **not optional for this project**. The template treats tests as opt-in,
but Constitution IV overrides that: *"Changes that alter behavior MUST land with tests covering
that behavior, and `nox -s tests` and `nox -s e2e` MUST pass before a change is merged."* Test
tasks are therefore first-class here, not a nice-to-have.

**Organization**: Tasks are grouped by user story so each can be implemented and verified as an
increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Touches different files from its neighbours and has no incomplete dependency — safe to
  reorder or batch.
- **[Story]**: Which user story the task serves (US1…US7).
- Every task names its exact file path.

## Path Conventions

Single project, existing Flask layout (see [plan.md](./plan.md) § Project Structure). Application
code in `app/`, tests in `tests/unit/` and `tests/e2e/`, migrations in `migrations/versions/`.

## Standing rules for every task

These come from the constitution and apply throughout; they are not repeated per task.

- Run tests via `venv/bin/nox`, never `pytest` directly. Prefix with
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`. `nox -s e2e` needs a **20-minute** timeout.
- `Decimal` for every price. **Never `float`.**
- Routes stay thin: no ORM queries and no raw SQL in `app/product/routes.py`.
- Do not touch `inventory_items` or JA-ID history behaviour.
- Any new pytest marker must be registered in `pytest.ini` first (`--strict-markers` is on).

---

## Phase 1: Setup

**Purpose**: Wire the new blueprint into the app so later phases have somewhere to land.

- [ ] T001 Create `app/product/__init__.py` defining `Blueprint('product', __name__)` and register it in `create_app()` in `app/__init__.py` alongside `main_bp` and `admin_bp`
- [ ] T002 [P] Create `app/templates/product/` with a shared layout extending `app/templates/base.html`, and add a "Products" entry to the nav in `app/templates/base.html`
- [ ] T003 [P] Establish the baseline: run `nox -s tests` and `nox -s e2e` on the untouched tree and record that both are green, so any later failure is attributable to this feature

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, service, and the minimum product record. Every user story needs a product to
exist before it can scan one, label one, or file a purchase against one.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

**Covers**: FR-001, FR-002, FR-003, FR-007 (storage side), FR-015 (code generation side)

### Domain types

- [ ] T004 [P] Add `IdentifierType`, `ScanKind`, and `StockStatus` enums to `app/models.py` per [data-model.md](./data-model.md) §8
- [ ] T005 [P] Add frozen `ScanClassification` and `ScanResolution` dataclasses to `app/models.py` per [contracts/scan-contract.md](./contracts/scan-contract.md)

### ORM models

- [ ] T006 Add `Product` ORM model to `app/database.py` per [data-model.md](./data-model.md) §1 — nullable `quantity` (tri-state), `quantity_updated_at`, `reorder_threshold`, `stock_status`, check constraints, indexes on `category_path` and `description`
- [ ] T007 Add `Purchase` ORM model to `app/database.py` per [data-model.md](./data-model.md) §2 — `unit_price` as `Numeric(10, 2)`, `received_date` nullable as the outstanding/complete state, indexes on `(product_id, order_date)` and `received_date`
- [ ] T008 Add `ProductIdentifier` ORM model to `app/database.py` per [data-model.md](./data-model.md) §3, including the `uq_identifier_type_value_vendor` unique constraint that makes FR-009 a database property rather than a convention
- [ ] T009 [P] Add `Tag` and `ProductTag` ORM models to `app/database.py` per [data-model.md](./data-model.md) §4
- [ ] T010 [P] Add `ProductAttachment` ORM model to `app/database.py` per [data-model.md](./data-model.md) §6, with the exactly-one-owner check constraint `(product_id IS NOT NULL) <> (purchase_id IS NOT NULL)`

### Migrations

- [ ] T011 Create Alembic revision for `products` in `migrations/versions/`
- [ ] T012 Create Alembic revision for `purchases` (FK → products) in `migrations/versions/`
- [ ] T013 Create Alembic revision for `product_identifiers` (FK → products, unique index) in `migrations/versions/`
- [ ] T014 [P] Create Alembic revision for `tags` and `product_tags` in `migrations/versions/`
- [ ] T015 [P] Create Alembic revision for `product_attachments` (FKs → photos, products, purchases) in `migrations/versions/`
- [ ] T016 Exercise **every** new revision's `downgrade` against a real MariaDB via `venv/bin/python manage.py db downgrade` — indexes and foreign keys must drop before the tables they depend on. SQLite will not catch this ordering fault and this repository has hit it before (Constitution V)

### Internal identifier

- [ ] T017 [P] Implement `app/utils/internal_id.py` — a pure module generating and validating `WIT` + 10 Crockford-base32 characters per [research.md](./research.md) §2. No Flask, no DB, no config imports
- [ ] T018 [P] Unit tests for `app/utils/internal_id.py` in `tests/unit/test_internal_id.py` — alphabet excludes I/L/O/U, generated values validate, malformed values reject

### Service and routes

- [ ] T019 Create `app/catalog_service.py` with a `CatalogService` class following the `InventoryService` session pattern (`storage.engine` → `sessionmaker`), as recorded in [plan.md](./plan.md) § Note on the Storage ABC
- [ ] T020 Implement product create / get / update in `app/catalog_service.py`, assigning an `INTERNAL` identifier at creation time so every product is scannable before any label exists
- [ ] T021 Implement product create, edit, and detail routes in `app/product/routes.py`, delegating all logic to `CatalogService`
- [ ] T022 [P] Create `app/templates/product/add.html`, `edit.html`, and `detail.html`

### Tests

- [ ] T023 [P] Unit tests for the new ORM models and their validation in `tests/unit/test_product_model.py` — including that `quantity` defaults to `NULL` (FR-023) and that price round-trips as `Decimal`
- [ ] T024 [P] Unit tests for `CatalogService` product CRUD in `tests/unit/test_catalog_service.py`, built through the `test_storage` → `app` → `client` fixtures in `tests/conftest.py`
- [ ] T025 [P] E2E test for product create / edit / detail in `tests/e2e/test_product_crud.py`

**Checkpoint**: A product can be created, edited, and viewed, and carries an internal code. User
stories can now begin.

---

## Phase 3: User Story 1 — Identify a part in hand (Priority: P1) 🎯 MVP

**Goal**: A scan answers "what is this thing" — description, specifications, purchase history,
location — and an unknown scan offers creation rather than an error.

**Independent Test**: `POST /api/scan` with a product's internal code returns that product. With
an uncatalogued but valid GTIN, it returns an offer to create with the identifier attached. With
junk, it returns a search. **No label printing is required** — the internal code exists from
Phase 2, so this story stands alone; printing it onto a label is US2.

**Covers**: FR-007, FR-009, FR-010, FR-014, FR-015, FR-018, SC-001, SC-008

### Pure modules and their tests

- [ ] T026 [P] [US1] Implement `app/utils/gtin.py` — normalize lengths 8/12/13/14 to a 14-digit key by left-zero-padding, GS1 mod-10 check digit, outright refusal of the all-zero key (the wedge no-read), per [research.md](./research.md) §3
- [ ] T027 [P] [US1] Unit tests for `app/utils/gtin.py` in `tests/unit/test_gtin.py` — UPC-A and its EAN-13 form normalize to the same key, bad check digits reject, all-zero refuses with no override
- [ ] T028 [US1] Implement `app/utils/scan_router.py` `classify()` with rules 1, 3, and 5 from [contracts/scan-contract.md](./contracts/scan-contract.md) (rule 2, ECIA, is added in US4). Pure module — stdlib, `app.models`, `app.utils.gtin`, `app.utils.internal_id` only
- [ ] T029 [P] [US1] Unit tests for `classify()` in `tests/unit/test_scan_router.py` — **never raises on any `str`** (empty, 4 KB of control characters, lone surrogate), internal code outranks a check-digit-valid all-digit string, everything unmatched lands on `FREE_TEXT`

### Service and endpoint

- [ ] T030 [US1] Implement `CatalogService.resolve_scan()` in `app/catalog_service.py` returning `outcome` of `product` / `create` / `search` per [contracts/scan-contract.md](./contracts/scan-contract.md) §2, including the vendor-identifier lookup that runs after a `FREE_TEXT` classification
- [ ] T031 [P] [US1] Unit tests for `resolve_scan()` in `tests/unit/test_scan_resolution.py` — a miss yields `create` with the identifier pre-attached, never a `404`
- [ ] T032 [US1] Add `POST /api/scan` to `app/product/routes.py` — returns `200` for every well-formed request; `4xx` only for a malformed request body, never for an unrecognized scan
- [ ] T033 [US1] Implement identifier add and remove in `app/catalog_service.py` and `app/product/routes.py`, including the FR-010 operator override path recorded via `validation_overridden`

### UI

- [ ] T034 [US1] Create `app/static/js/scan-capture.js` — buffer rapid wedge keystrokes and flush on Enter or inter-key timeout, following the pattern in `app/static/js/inventory-add.js`. **Must preserve control characters** (`GS` 0x1d, `RS` 0x1e, `EOT` 0x04); stripping them silently breaks US4 and nothing else will catch it
- [ ] T035 [US1] Render the scan outcome: resolve to the product detail view, to a create form, or to search results, from `app/product/routes.py` and `app/templates/product/`
- [ ] T036 [US1] Implement the create-with-prefilled-identifier path so an unknown scan lands on a create form carrying the scanned identifier (FR-018)

### Tests

- [ ] T037 [P] [US1] Route tests for `POST /api/scan` in `tests/unit/test_scan_routes.py`
- [ ] T038 [P] [US1] E2E test in `tests/e2e/test_wedge_scan.py` — scan an internal code and land on the product; scan an unknown GTIN and land on a create form with it attached; scan junk and land on search

**Checkpoint**: US1 is independently functional. This is the MVP.

---

## Phase 4: User Story 2 — Capture a purchase and produce a label (Priority: P1)

**Goal**: Record what arrived and print a durable label carrying the description, the provenance,
and a code that scans back.

**Independent Test**: Record a purchase, print a label with printing disabled, and confirm the
composed image carries all three elements. Reprint and confirm no data re-entry is needed.

**Covers**: FR-004, FR-005, FR-011, FR-012, FR-013, FR-037, SC-003

- [ ] T039 [US2] Implement purchase recording in `app/catalog_service.py` — vendor, item identifier, order date, received state, quantity, price as `Decimal`; reject a `received_date` earlier than its `order_date`
- [ ] T040 [US2] Add the purchase-record route to `app/product/routes.py` and create `app/templates/product/purchase_add.html`
- [ ] T041 [US2] Implement `app/services/product_label.py` `compose_product_label()` — Pillow canvas with a wrapped description band, a provenance line, and the Code128 symbol **plus** the code as text, sized to the chosen `LABEL_TYPES` entry, returning a PNG `BytesIO`. Per [contracts/label-contract.md](./contracts/label-contract.md); the human-readable code is never dropped to gain space, the description truncates first
- [ ] T042 [US2] Add `POST /api/products/<id>/label` to `app/product/routes.py`, passing the composed PNG to the existing `LpPrinter.print_images()` with unchanged `lp_options` from `app/services/label_printer.py`. Reject an unknown label type with `400` listing the valid keys
- [ ] T043 [US2] Add a label-print control to `app/templates/product/detail.html` reusing the existing `GET /api/labels/types` endpoint and `app/static/js/label-printing-modal.js` patterns, offering all six stocks (FR-037)
- [ ] T044 [P] [US2] Unit tests for label composition in `tests/unit/test_product_label.py` — output dimensions match the stock, description and code both present, a long description truncates rather than overflowing, a product with no purchases composes with no provenance band. **No test may reach `LpPrinter.print_images()`**
- [ ] T045 [P] [US2] E2E test in `tests/e2e/test_label_print.py` — the print request reaches the `TESTING` / `DISABLE_LABEL_PRINTING` short-circuit with the expected product and label type, and reprint requires no re-entry

**Checkpoint**: The full core loop works — create, print, scan back.

---

## Phase 5: User Story 3 — Capture order details when the order is placed (Priority: P2)

**Goal**: Capture vendor, item identifier, listing title, order date, and price while the listing
is on screen, so nothing must be reconstructed at unboxing.

**Independent Test**: Trigger capture from a listing, confirm an unreceived purchase exists with
the right details, capture the same listing again and confirm nothing new is created, then
complete it on arrival.

**Covers**: FR-020, FR-021, SC-002

- [ ] T046 [US3] Implement capture in `app/catalog_service.py` — attach to an existing product when the captured identifier matches one, otherwise create a product (FR-021); idempotent on `(vendor, vendor_item_id, order_date)`
- [ ] T047 [US3] Add `POST /api/capture` to `app/product/routes.py` and exempt **only this endpoint** from CSRF, with an inline comment explaining that the bookmarklet posts from the vendor's origin and why that is proportionate under the constitution's stated threat model
- [ ] T048 [US3] Create the bookmarklet — reads `location.href`, `document.title`, and the ASIN from an Amazon `/dp/<ASIN>/` URL path, and POSTs to `/api/capture`. Reads the URL, never DOM selectors; anything it cannot find is left blank for the operator
- [ ] T049 [US3] Add the paste-a-URL fallback page at `/products/capture` with `app/templates/product/capture.html` — the path that cannot break when a vendor changes their site
- [ ] T050 [US3] Implement the receive flow in `app/catalog_service.py` and `app/product/routes.py` — present the captured details for confirmation or amendment, allow quantity and price to differ from what was ordered, and set `received_date`
- [ ] T051 [P] [US3] Unit tests in `tests/unit/test_capture.py` — idempotency, attach-vs-create, amendment at receipt
- [ ] T052 [P] [US3] E2E test in `tests/e2e/test_order_capture.py` covering the paste-a-URL path end to end

**Checkpoint**: Order-time capture removes the manual transcription step.

---

## Phase 6: User Story 4 — Catalogue a distributor part from its own label (Priority: P2)

**Goal**: Scan a DigiKey/Mouser 2D label and get an editable draft, with no new label printed.

**Independent Test**: Scan a format-06 envelope and confirm manufacturer part number, quantity,
and order references are extracted and editable. Scan a corrupted envelope and confirm the raw
scan is surfaced rather than failing silently.

**Covers**: FR-016, FR-017, SC-004

- [ ] T053 [P] [US4] Implement `app/utils/ecia.py` — ISO/IEC 15434 format-06 grammar extracting `P`, `1P`, `Q`, `K`, `1K`, `9D`, `10D` as **uncoerced strings**, ignoring every other legal MH10.8.2 identifier silently. Pure module; never raises on a `str`. Per [research.md](./research.md) §4
- [ ] T054 [P] [US4] Unit tests for `app/utils/ecia.py` in `tests/unit/test_ecia.py` — including the two edge cases from research: a character glued onto the format indicator is not an envelope, and a half-delivered trailer (`<data> EOT` with no `RS`) must not read `EOT` as data
- [ ] T055 [US4] Add rule 2 to `classify()` in `app/utils/scan_router.py` — a format-06 envelope carrying **at least one recognized identifier** classifies `ECIA`; a well-formed envelope carrying nothing readable falls through to `FREE_TEXT`
- [ ] T056 [US4] Extend `CatalogService.resolve_scan()` with the ECIA branch — look up by `1P`, and on a miss return `create` with every extracted field in `prefill`
- [ ] T057 [US4] Render the pre-filled draft in `app/templates/product/add.html` with every extracted value editable before saving (FR-017)
- [ ] T058 [P] [US4] E2E test in `tests/e2e/test_ecia_scan.py` — a real-shaped envelope produces a populated editable draft; a corrupted one surfaces the raw scan

**Checkpoint**: Distributor parts enter the catalogue cheaply.

---

## Phase 7: User Story 5 — Recognize repeat purchases and track price history (Priority: P2)

**Goal**: A second purchase of a known product joins one history rather than creating a duplicate.

**Independent Test**: Record two purchases of one product at different prices and dates; confirm
one chronological history with the most recent price visible and no duplicate product.

**Covers**: FR-006, FR-019, SC-005

- [ ] T059 [US5] Implement purchase history retrieval in `app/catalog_service.py` — chronological by `order_date`, with the most recent `unit_price` exposed as the latest price (FR-006)
- [ ] T060 [US5] Render the purchase history and latest price in `app/templates/product/detail.html`
- [ ] T061 [US5] Wire the receiving path so a scan resolving to an existing product offers *add a purchase to this product* rather than *create a new product* (FR-019)
- [ ] T062 [P] [US5] Unit tests in `tests/unit/test_purchase_history.py` — ordering, latest price, and that two variants deliberately kept distinct stay distinct
- [ ] T063 [P] [US5] E2E test in `tests/e2e/test_repeat_purchase.py`

**Checkpoint**: Repeat buying builds price history instead of duplicates.

---

## Phase 8: User Story 6 — Know what to reorder (Priority: P3)

**Goal**: One view showing everything low, with items already on the way marked.

**Independent Test**: Flag an untracked product low, set a tracked product at or below threshold,
leave one order outstanding. Both appear in the reorder view; the outstanding one is marked on the
way. Mark it received and confirm it clears — **both** for the tracked product and the manually
flagged one.

**Covers**: FR-022 – FR-029, SC-006, SC-007

- [ ] T064 [US6] Implement tri-state quantity in `app/catalog_service.py` — `NULL` not tracked, `0` none on hand, and set `quantity_updated_at` on every change; clear it when tracking is switched off (FR-022, FR-023)
- [ ] T065 [US6] Add `PATCH /api/products/<id>/quantity` to `app/product/routes.py` accepting an explicit `null` to stop tracking, distinct from omitting the field
- [ ] T066 [US6] Implement the quantity age display in `app/templates/product/detail.html` — render relative age ("counted 8 months ago"), never the bare number (FR-024)
- [ ] T067 [US6] Implement the manual stock flag and `PATCH /api/products/<id>/stock-status` in `app/catalog_service.py` and `app/product/routes.py` (FR-025)
- [ ] T068 [US6] Implement the derived reorder queries in `app/catalog_service.py` — `is_threshold_low`, `is_manually_low`, `is_effectively_low`, `is_on_order` per [data-model.md](./data-model.md) §7. **Computed at query time; no stored status column and no background job**
- [ ] T069 [US6] Add the reorder view route and `app/templates/product/reorder.html`, combining manual and threshold-derived low products with on-order ones marked (FR-027, FR-028)
- [ ] T070 [US6] **Clear the manual low flag explicitly in the receive path** in `app/catalog_service.py`. A threshold-derived low clears itself once the receipt updates the quantity, but a manually flagged product stays flagged until something clears it — this asymmetry is the subtle point of FR-029 ([research.md](./research.md) §10)
- [ ] T071 [US6] Make quantity adjust and stock-status set **touch targets** on `app/templates/product/detail.html`, not keyboard-only affordances (FR-036, SC-010)
- [ ] T072 [P] [US6] Unit tests in `tests/unit/test_stock_status.py` — the three quantity states are distinguishable, threshold derivation, and **both halves** of FR-029
- [ ] T073 [P] [US6] E2E test in `tests/e2e/test_reorder_view.py` — including that `quantity = 0` and `quantity = NULL` are visibly different everywhere quantity is shown (SC-007)

**Checkpoint**: The handful of parts where a stockout costs something are covered.

---

## Phase 9: User Story 7 — Classify and find things (Priority: P3)

**Goal**: Categories, tags, and search that scale as the catalogue grows.

**Independent Test**: Assign products to nested categories and cross-cutting tags; confirm a
category filter includes sub-categories, a tag filter ignores category, and search matches
description, specification, and identifier.

**Covers**: FR-030, FR-031, FR-032, SC-009

- [ ] T074 [P] [US7] Implement `app/utils/category.py` — canonical materialized path (lowercase, `/`-separated, no empty segments, stripped), the `path = X OR path LIKE 'X/%'` segment-boundary predicate, and blank/`None` yielding "no category" rather than an error. Normalization only shortens or lowercases; **never slugs** (research §6)
- [ ] T075 [P] [US7] Unit tests for `app/utils/category.py` in `tests/unit/test_category.py` — canonicalization, boundary predicate does not match `foo-bar` when filtering `foo`, blank inputs are not errors
- [ ] T076 [US7] Implement inline category creation during product entry in `app/catalog_service.py` and `app/templates/product/add.html` — typing a new category creates it with no separate setup step (FR-030)
- [ ] T077 [US7] Implement tag create / attach / detach in `app/catalog_service.py` with lowercase normalization, plus `GET /api/tags` in `app/product/routes.py` (FR-031)
- [ ] T078 [US7] Implement search in `app/catalog_service.py` across description, specifications, identifiers, and part numbers (FR-032)
- [ ] T079 [US7] Add `GET /api/products/search` and the catalogue list page with category, tag, and stock filters — including the `tracked` / `untracked` / `none-on-hand` values that keep SC-007 unambiguous — in `app/product/routes.py` and `app/templates/product/search.html`
- [ ] T080 [US7] Add `GET /api/categories` and the category browse page `app/templates/product/categories.html`
- [ ] T081 [P] [US7] Unit tests in `tests/unit/test_product_search.py` — subtree filtering, tag filtering across categories, search across all four fields
- [ ] T082 [P] [US7] E2E test in `tests/e2e/test_product_search.py`

**Checkpoint**: All seven user stories are functional.

---

## Phase 10: Cross-Cutting Concerns

**Purpose**: The remaining requirements that belong to no single story, plus the merge gates.

**Covers**: FR-033, FR-034, FR-035, FR-036

- [ ] T083 [P] Implement optional storage location on the product form and detail view in `app/catalog_service.py` and `app/templates/product/` (FR-033)
- [ ] T084 Implement attachments on a product or a purchase by extending `app/photo_service.py` and reusing the existing `photos` BLOB table — PDF datasheets already work via PyMuPDF. Use a **separate** per-product cap constant rather than reusing `MAX_PHOTOS_PER_ITEM` (FR-034, research §7)
- [ ] T085 [P] Add attachment upload and listing routes to `app/product/routes.py` and the attachment section to `app/templates/product/detail.html`
- [ ] T086 Create `app/static/js/product-form.js` persisting in-progress form state to `localStorage` on input, offering restore on load, and clearing on successful submit (FR-035). Follow the existing label-type persistence precedent; **not** a service worker and not offline sync
- [ ] T087 [P] Unit tests for attachments in `tests/unit/test_product_attachments.py` — including that the exactly-one-owner constraint holds
- [ ] T088 [P] E2E test in `tests/e2e/test_draft_persistence.py` — compose text, simulate the interruption, reload, confirm restore is offered
- [ ] T089 [P] E2E test in `tests/e2e/test_touch_readiness.py` — drive scan-and-act and the reorder view on a touch viewport with no keyboard (SC-010)

### Merge gates

- [ ] T090 Regenerate documentation screenshots with `nox -s screenshots_headless` and commit them. This feature changes `app/templates/**`, `app/static/css/**`, and `app/static/js/**`, so **CI blocks the merge on stale screenshots**
- [ ] T091 Verify screenshots with `nox -s screenshots_verify` — valid PNG, RGB/RGBA, under 500 KB each
- [ ] T092 [P] Update `docs/user-manual.md` with the product catalogue workflows, matching how the original label-printing feature documented itself
- [ ] T093 Run the full `quickstart.md` validation — all nine scenarios and the pre-merge checklist
- [ ] T094 Confirm `nox -s tests` and `nox -s e2e` are green, and open the pull request

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup — **blocks every user story**
- **US1 (Phase 3)**: depends on Phase 2 only
- **US2 (Phase 4)**: depends on Phase 2 only
- **US3 (Phase 5)**: depends on Phase 2; T050 (receive) shares ground with US6's T070
- **US4 (Phase 6)**: depends on Phase 2 **and on US1's T028** — it adds a rule to the classifier US1 creates
- **US5 (Phase 7)**: depends on Phase 2 and on US2's T039 (a purchase must be recordable before there is a history)
- **US6 (Phase 8)**: depends on Phase 2; T070 depends on US3's T050 if order capture is built first
- **US7 (Phase 9)**: depends on Phase 2 only
- **Cross-cutting (Phase 10)**: depends on the stories whose surfaces it touches

**US4 is the one story that is not independent of another.** It extends `scan_router.classify()`
rather than standing beside it, because a second classifier would be exactly the drift the pure
module exists to prevent. Everything else can be built in any order after Phase 2.

### Within each story

- Pure `app/utils/` modules and their unit tests come first — they need no app context and are the
  cheapest place to be wrong.
- Models → service → routes → templates.
- E2E last, once there is a UI to drive.

### Parallel opportunities

This is a single-developer project, so `[P]` means "independent, reorder freely or batch into one
commit" rather than "hand to another developer". The genuinely independent clusters:

- **Phase 2**: T004/T005 (enums and dataclasses), T009/T010 (tag and attachment models),
  T014/T015 (their migrations), T017/T018 (internal id) — all touch different files
- **Phase 3**: T026/T027 (GTIN) can be written before or after T028/T029 (router)
- **Phase 9**: T074/T075 (category) are independent of the tag work in T077
- **Test tasks** marked `[P]` throughout can be batched with their implementation task

---

## Implementation Strategy

### MVP: Phases 1–3

Setup → Foundational → US1. At that point a product can be created and a scan of its internal
code identifies it, which is the feature's central value (SC-001, SC-008). Stop and validate here.

### Recommended increment order

1. **Phases 1–3** — MVP: create a product, scan it back
2. **Phase 4 (US2)** — closes the physical loop: print the label that gets scanned
3. **Phase 6 (US4)** — cheapest remaining value; distributor parts need no label at all
4. **Phase 5 (US3)** — removes the manual transcription step
5. **Phase 7 (US5)** — price history
6. **Phase 9 (US7)** — retrieval, as the catalogue grows past browsing
7. **Phase 8 (US6)** — reorder signals, deliberately narrow
8. **Phase 10** — cross-cutting and merge gates

US4 is promoted above US3 and US5 because it reuses US1's scan path almost entirely and delivers
a whole acquisition channel for one pure module plus a classifier rule.

### Notes

- Commit after each task or logical group.
- `nox -s e2e` needs a 20-minute timeout and rewrites screenshots as a side effect — revert those
  unless T090 is the task in hand.
- Stop at any checkpoint; every phase boundary leaves the application working.
