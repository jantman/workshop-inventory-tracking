---

description: "Task list for DigiKey Order Capture and Receiving"
---

# Tasks: DigiKey Order Capture and Receiving

**Input**: Design documents from `specs/024-digikey-order-capture/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Required, not optional. Constitution IV: "Changes that alter behavior MUST land with
tests covering that behavior, and `nox -s tests` and `nox -s e2e` MUST pass before a change is
merged." Coverage is deliberately not a target — write the test that would have caught the bug.

**Organization**: Grouped by user story so each can be implemented, tested and shipped on its
own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: `[US1]`–`[US4]`, mapping to the spec's user stories
- Exact file paths in every description

## Conventions

- Run project commands through the repository virtualenv: `venv/bin/python`, `venv/bin/nox`.
- `nox` needs pyenv's 3.13 on `PATH`:
  `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`
- **`nox -s e2e` needs a 15-minute tool timeout** (Constitution IV).
- Non-trivial code goes on branch `issues/108` and merges by pull request.
- American spelling: `catalog`, never `catalogue`.

---

## Phase 1: The Gate (Setup)

**Purpose**: Find out whether the feature is buildable as specified, and record the real
responses everything else is written from. **This is the highest-risk hour of the project and
it comes first** — see [research §2](./research.md) and R1 in [plan.md](./plan.md).

**✅ COMPLETE 2026-08-22 — outcome (a), build as planned.** See
[verification.md](./verification.md). R1 and R3 closed; R2 materialized (v4 renamed most line
fields); `X-DIGIKEY-Account-ID` is required and adds a third setting. Fixtures are recorded and
redacted at `tests/fixtures/digikey/`.

- [x] T001 Verify DigiKey API access by hand, following [quickstart.md](./quickstart.md) §0: register the application at `developer.digikey.com`, subscribe it to Product Information and Order Status, get a 2-legged token, and read back a real sales order number with `curl`. Record the outcome in a new `specs/024-digikey-order-capture/verification.md`, including whether the v4 sales-order response carries an order date and whether its line-item field names match the v3 record in [research §5](./research.md)
- [x] T002 Act on T001's answer before continuing: **(a)** order returned → proceed unchanged; **(b)** `401`/`403`/empty → add the 3-legged flow to the plan (authorization-code route plus an untracked `credentials/digikey_token.json`), amend [contracts/digikey-api.md](./contracts/digikey-api.md) §1 and note it in `verification.md`; **(c)** refused for the account type → **stop, and report to the user that User Story 1 is not buildable as specified.** Do not substitute page scraping
- [x] T003 [P] Record the two API responses as fixtures — `tests/fixtures/digikey/salesorder.json` and `tests/fixtures/digikey/productdetails.json` — redacting `ShippingAddress`, `BillingAddress`, `Email`, `CustomerId`, `BillingAccount` and `PaymentMethod`. Prefer an order with at least one multi-quantity line and one line with no manufacturer part number
- [x] T004 [P] Add `DIGIKEY_CLIENT_ID`, `DIGIKEY_CLIENT_SECRET`, `DIGIKEY_ACCOUNT_ID` and `DIGIKEY_API_BASE` (default `https://api.digikey.com`) to `config.py`, in both `Config` and `TestConfig`, following the shape of the adjacent `GOOGLE_*` settings. All four are already set in the developer's `.env`
- [x] T005 [P] Document the four settings in `.env.example` with the registration steps as comments. Confirm `.env` stays gitignored

**Checkpoint**: The API is known to work, its real responses are on disk, and configuration
exists. Everything below is written from the fixtures rather than from memory.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The column, the dataclasses and the client. Every user story needs all three.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Schema

- [x] T006 Add `supplier_order_reference = Column(String(200), nullable=True, index=True)` to `Purchase` in `app/database.py`, with a comment stating it holds the **supplier's** order number (ECIA `1K`) as distinct from the adjacent `order_reference` (the customer's, ECIA `K`). Add it to `Purchase.to_dict()`
- [x] T007 Generate the migration with `venv/bin/python manage.py db migrate -m "add supplier_order_reference to purchases"`, then hand-check the generated revision in `migrations/versions/`: `add_column` then `create_index` in `upgrade`, `drop_index` then `drop_column` in `downgrade` — MariaDB will not drop a column an index still covers
- [x] T008 Exercise the migration both ways per [quickstart.md](./quickstart.md) §1 (`db upgrade`, `db downgrade -1`, `db upgrade`) and confirm the `create_all`-vs-Alembic drift trap: `grep -n "supplier_order_reference" app/database.py migrations/versions/*.py` must show the same name, type, nullability and index in both

### Domain models

- [x] T009 [P] Add frozen dataclasses `DigiKeyOrderLine` and `DigiKeyOrder` to `app/models.py` per [data-model §3](./data-model.md), beside `ListingCapture` and following its `from_json` precedent. Construction must never raise on a well-formed JSON object; a missing field becomes `''`/`None`, never a `KeyError`
- [x] T010 [P] Add `OrderLineState` (`Enum`: `NEW`, `MATCHED`, `CONFLICT`, `CAPTURED`) and the frozen dataclasses `ReviewedLine` and `OrderCaptureReview` to `app/models.py` per [data-model §4](./data-model.md). Carry plain values, never ORM rows — the reason `CaptureAssessment` already documents

### The client

- [x] T011 Create `app/services/digikey.py` with `DigiKeyClient.__init__` (taking `account_id`) and private 2-legged token acquisition per [contracts/digikey-api.md](./contracts/digikey-api.md) §1–2. **`X-DIGIKEY-Account-ID` goes on every request** — without it the order endpoints answer `400 Account ID must not be 0`, which maps to `ConfigurationError`, not `AuthenticationError`. Imports are `requests`, the standard library and `app.models` **only** — no Flask, no `app.database`, no `app.catalog_service`. Cache the token in memory with its expiry; renew within 30 seconds of expiring; never write it to disk
- [x] T012 Implement `DigiKeyClient.get_order(sales_order_number) -> DigiKeyOrder` in `app/services/digikey.py` per [contracts/digikey-api.md](./contracts/digikey-api.md) §3, mapping fields from the recorded `salesorder.json`. **Use the v4 names, not v3's** — `DigiKeyProductNumber`, `ManufacturerProductNumber`, `Description`, `QuantityOrdered`, `QuantityBackOrder`, `DetailId` (because `PoLineItemNumber` is `null`), and `DateEntered` for the order date. **Parse with `json.loads(body, parse_float=Decimal)`; `response.json()` is prohibited in this module** (Constitution III). Never read `Contact`, `ShippingAddress` or `CustomerId`
- [x] T013 Implement the failure mapping in `app/services/digikey.py` per [contracts/digikey-api.md](./contracts/digikey-api.md) §6 — `ConfigurationError`, `AuthenticationError`, `ItemNotFoundError`, `RateLimitError`, `TemporaryError`, all imported from `app/exceptions.py`. **Add no new exception class.** Read `X-RateLimit-Reset` when present so a `429` says when to retry
- [x] T014 Build the client from config in `create_app()` (`app/__init__.py`) and stash it as `app.config['DIGIKEY_CLIENT']`, mirroring `app.config['STORAGE_BACKEND']`. An unset `DIGIKEY_CLIENT_ID` means no client, which is how "not configured" is detected. Add a `_get_digikey_client()` helper to `app/product/routes.py` alongside the existing `_get_catalog_service()`

### Foundational tests

- [x] T015 [P] Write `tests/unit/test_digikey_client.py` against `tests/fixtures/digikey/salesorder.json`: the order and its lines map correctly; **`isinstance(line.unit_price, Decimal)`** and an exact value assertion (write this one first and never delete it); a line with no manufacturer part number still parses; a response missing a field costs that field and nothing else; each failure condition raises the exception §6 names. Network stays blocked — no real call
- [x] T016 [P] Extend `tests/unit/test_database.py` (or add to the nearest existing purchase test) so `Purchase.to_dict()` round-trips `supplier_order_reference`, including when it is `NULL`

**Checkpoint**: `nox -s tests` green. The column exists on both sides, the client turns real
DigiKey JSON into dataclasses, and prices are `Decimal`.

---

## Phase 3: User Story 1 — Capture a whole order (Priority: P1) 🎯 MVP

**Goal**: One sales order number becomes a reviewed, confirmed set of outstanding purchases —
one per line, attached to matched or newly created products.

**Independent Test**: Capture a known sales order number, confirm the review, and verify every
line became an outstanding purchase against a product carrying the line's manufacturer part
number and DigiKey part number, with the quantity and unit price DigiKey reported.

### Tests for User Story 1

> Write these first and watch them fail.

- [x] T017 [P] [US1] Write `tests/unit/test_digikey_capture.py` for the review: the four `OrderLineState` values are assigned in the documented order (FR-005, FR-012, FR-015); a line whose MPN matches an existing product is `MATCHED`; a line whose DigiKey part number names a product with a contradicting MPN is `CONFLICT`; a line already captured for this sales order is `CAPTURED`; `orphaned` names a recorded purchase the fetched order no longer contains (FR-013). **Assert the review writes nothing** — product and purchase counts unchanged (FR-004)
- [x] T018 [P] [US1] Extend `tests/unit/test_digikey_capture.py` for the write: one outstanding purchase per included line with the right vendor, quantity, price and both order references (FR-008, FR-009); an excluded line writes nothing (FR-007); re-capturing an unchanged order writes nothing (FR-012, SC-003); an unresolved `CONFLICT` refuses the **whole** capture with `ValidationError` (FR-015); a line with no MPN still captures (FR-016); a blank description falls back to DigiKey's (FR-006)
- [x] T019 [P] [US1] Add the atomicity test to `tests/unit/test_digikey_capture.py`: force a failure part-way through a multi-line order and assert the product and purchase counts are exactly what they were before (FR-039, SC-009)

### Implementation for User Story 1

- [x] T019a [P] [US1] Add the enrichment tests to `tests/unit/test_digikey_capture.py`: every line is enriched from its part detail (FR-040); a line whose part lookup fails is still capturable on what the order gave and is marked as thin (FR-041); a failed *part* call never rolls back the capture, while a failed *order* call writes nothing
- [x] T019b [US1] Implement `DigiKeyClient.get_part()` in `app/services/digikey.py` per [contracts/digikey-api.md](./contracts/digikey-api.md) §4, writing the **nested** paths from the recorded `productdetails.json` — `Product.Manufacturer.Name`, `Product.Description.ProductDescription`, `Product.Category.Name`, `Product.Parameters[]`. Moved here from US3: US1 needs it, because a v4 order line carries no manufacturer
- [x] T019c [US1] Enrich each reviewed line with one `get_part()` call in `app/catalog_service.py`, populating `ReviewedLine.part` ([data-model §3a](./data-model.md)). A lookup that fails sets `part = None` and is an ordinary state, never an exception that reaches the route
- [x] T020 [US1] Implement `CatalogService.review_digikey_order(order: DigiKeyOrder) -> OrderCaptureReview` in `app/catalog_service.py` per [data-model §4](./data-model.md). **Read-only** — one `_session()`, no writes. Assign `OrderLineState` in the documented order, trim `suggested_description` to the 255-character column limit, and compute `orphaned`
- [x] T021 [US1] Implement `CatalogService.capture_digikey_order(order, decisions) -> ...` in `app/catalog_service.py`, writing **every line in one `_session()`** (FR-039 — see [research §9](./research.md)). Reuse the existing primitives (`create_product`, `record_purchase`, `_add_identifier`); do **not** call `capture_order`, whose same-day duplicate heuristic is wrong here because a sales order number is an exact idempotency key. Re-check the `CAPTURED` state inside the session. Write the field mapping in [data-model §2](./data-model.md), including `MPN` and DigiKey-scoped `DISTRIBUTOR` identifiers
- [x] T022 [P] [US1] Implement `CatalogService.find_order_lines(sales_order_number)` in `app/catalog_service.py` — the purchases with `vendor = 'DigiKey'` and that reference, ordered for display, with the outstanding count. This is the derived order (FR-017, FR-018); nothing is stored
- [x] T023 [US1] Add `GET`/`POST /products/digikey/orders` to `app/product/routes.py` per [contracts/routes.md](./contracts/routes.md): fetch, review, render. Writes nothing. Catch each of the five exceptions and render its own message on a working page, never an error page
- [x] T024 [US1] Add `POST /products/digikey/orders/capture` to `app/product/routes.py`: re-fetch the order (the fetched order is the authority), re-review, apply the submitted per-line decisions, write. On `ValidationError`, re-render the review **carrying what was submitted** so an authored description is not lost. Redirect on success to the captured-order screen
- [x] T025 [US1] Add `GET /products/digikey/orders/<sales_order_number>` to `app/product/routes.py` — the derived order screen. A sales order number with no purchases renders "not captured" with a link to capture it, never a 404
- [x] T026 [P] [US1] Create `app/templates/product/digikey_order_entry.html` — the sales order number form, extending `product/_layout.html`
- [x] T027 [US1] Create `app/templates/product/digikey_order_review.html` — every line with its state, DigiKey's values, the per-line include checkbox, the description field for `NEW` lines, the required choice for `CONFLICT` lines, and the change display for `CAPTURED` lines. Show `orphaned` lines as a notice. State the currency; never convert it
- [x] T028 [P] [US1] Create `app/templates/product/digikey_order.html` — the captured order: every line with product, quantity, price and outstanding-or-received, the *n* of *m* outstanding count, and a **Receive** link per outstanding line to `purchase_receive` (FR-022). Honour `?highlight=`
- [x] T029 [P] [US1] Add "Capture a DigiKey Order" to the Products dropdown in `app/templates/base.html`, beside the existing "Capture an Order" item
- [x] T030 [US1] Write `tests/e2e/test_digikey_order.py` per [quickstart.md](./quickstart.md) §3, with a stdlib `ThreadingHTTPServer` serving `tests/fixtures/digikey/` and `DIGIKEY_API_BASE` pointed at it — the pattern `tests/e2e/test_product_page_capture.py` already uses. Cover: review lists every line and writes nothing; confirm creates one outstanding purchase per line; a matched line attaches rather than duplicating; an excluded line writes nothing; re-capture records nothing new. **Wait on state, never on a duration**; the capture confirmation does network work before redirecting, so wait for the order screen's heading, not the button

**Checkpoint**: US1 ships on its own. Orders are recorded, the reorder list stops suggesting
what is on the way, and parts are cataloged before they arrive.

---

## Phase 4: User Story 2 — Receive by scanning (Priority: P2)

**Goal**: A scanned bag label lands on the receipt for its own line of its own order.

**Independent Test**: Capture an order, scan a label carrying that sales order number and one of
its DigiKey part numbers, and verify the scan lands on the receipt for that specific outstanding
line rather than on a blank product draft.

### Tests for User Story 2

- [x] T031 [P] [US2] Extend `tests/unit/test_scan_resolution.py`: a label whose `1K` and `P` match an outstanding captured line resolves to `outcome='receive'` carrying that purchase; **the order-line lookup wins over the existing `1P` → MPN product lookup** for a part already in the catalog; two outstanding lines for one part return both (FR-026); an already-received line returns the purchase with nothing outstanding (FR-023); no captured order, or a part the order does not contain, resolves exactly as it does today (FR-024, FR-025)
- [x] T032 [P] [US2] Extend `tests/unit/test_scan_router.py` or the nearest API test so `POST /api/scan` returns the right `url` for each of the four receive cases in [contracts/routes.md](./contracts/routes.md)

### Implementation for User Story 2

- [x] T033 [US2] Add the `'receive'` outcome and the `purchases: List[Any]` field to `ScanResolution` in `app/models.py`, including `to_dict()`. Type it loosely for the reason `product` already is — `app/models.py` must not import `app/database.py`
- [x] T034 [P] [US2] Implement `CatalogService.find_receivable(sales_order_number, digikey_part_number)` in `app/catalog_service.py`, returning matching purchases regardless of received state so the route can distinguish "already received" from "no such line"
- [x] T035 [US2] Extend the ECIA branch of `CatalogService.resolve_scan()` in `app/catalog_service.py`: when the label carries both `1K` and `P`, look for matching purchases **before** the existing `1P` → MPN lookup, and return `outcome='receive'` when any match. Zero matches must fall through to today's behaviour byte for byte
- [x] T036 [US2] Update the `resolve_scan` docstring in `app/catalog_service.py` — it currently says "Three outcomes and no fourth" — and the matching note in `app/utils/scan_router.py`. State that the fourth answer does not weaken 001 FR-018/SC-008: nothing dead-ends, because the free-text rule still always matches
- [x] T037 [US2] Add the `'receive'` branch to `api_scan` in `app/product/routes.py`, building `url` per [contracts/routes.md](./contracts/routes.md): one outstanding → the receive screen with `?quantity=` from ECIA `Q`; several → the order screen with `?highlight=`; none outstanding but some received → the order screen with an "already received" flash naming the line. **No JavaScript change is needed** — `app/static/js/scan-capture.js` already navigates to `data.url` without inspecting the outcome
- [x] T038 [US2] Accept an optional `?quantity=` on `GET /purchases/<id>/receive` in `app/product/routes.py` and pre-fill the quantity field with it, editable (FR-020). Absent, the screen behaves exactly as it does now; `POST` is unchanged
- [x] T039 [US2] Write `tests/e2e/test_digikey_receive.py`: scan a bag label for an outstanding line → the receive screen with the label's quantity; confirm → received, count up, flag cleared (FR-021); scan the same bag again → "already received" and nothing received twice; the order screen shows *n* of *m*. The scan box fires a `fetch` then navigates — wait for the receive screen's own content, not for `click()` returning

**Checkpoint**: US1 and US2 both work independently. The workflow the issue asked for is
complete end to end.

---

## Phase 5: User Story 3 — Capture a single part (Priority: P3)

**Goal**: A DigiKey part number, product URL or bag scan yields a fully populated product.

**Independent Test**: Enter a DigiKey part number for a part not in the catalog and verify the
draft carries the manufacturer, manufacturer part number, DigiKey part number and description
with nothing typed, and that confirming creates the product with those values.

*Does not depend on US1 or US2 — buildable in parallel once Phase 2 is done.*

### Tests for User Story 3

- [ ] T040 [P] [US3] Extend `tests/unit/test_digikey_client.py` against `tests/fixtures/digikey/productdetails.json` for the paths US1's enrichment does not exercise: a part number DigiKey does not recognize raises `ItemNotFoundError`; a `Product` object missing `Manufacturer`, `Category` or `Parameters` yields empty values rather than a `KeyError`
- [ ] T041 [P] [US3] Add URL-parsing tests to `tests/unit/test_capture.py` beside the existing `_asin_from_url` cases: a DigiKey product address yields the manufacturer part number from its second-to-last path segment; a numeric product id is **not** mistaken for a part number; an unrecognized address yields nothing rather than a guess

### Implementation for User Story 3

> `DigiKeyPart` and `get_part()` moved to US1 (T019b) — enrichment needs them. So did the
> specifications merge and the attachment handling. What is left here is the entry point.

- [ ] T044 [P] [US3] Add a `_digikey_part_from_url()` helper to `app/product/routes.py` per [research §11](./research.md): read the manufacturer part number from the path, never the trailing numeric product id. Anything unrecognized returns empty for FR-032 to handle
- [ ] T045 [US3] Add `GET`/`POST /products/digikey/part` to `app/product/routes.py` per [contracts/routes.md](./contracts/routes.md). `POST` renders a review and writes nothing; confirmation posts to the existing product-create path so there is one product-creation surface. An unrecognized part number renders a plain statement plus the ordinary product form carrying what was entered (FR-032)
- [ ] T046 [US3] Create `app/templates/product/digikey_part_review.html`, following the shape of `app/templates/product/capture.html`: the operator's description over DigiKey's (FR-029), the parameters as specifications, the datasheet and photo shown as what will be attached
- [ ] T047 [US3] Record `parameters` as product specifications through the existing merge rule — **a specification the operator has edited wins and is not examined** (FR-030) — in `app/catalog_service.py`, reusing the captured-listing merge rather than writing a second one
- [ ] T048 [US3] Attach the photo and datasheet via `store_listing_images` in `app/services/listing_images.py`, **after** the transactional write, per [research §10](./research.md). `.pdf` is already in its `_KNOWN_EXTENSIONS`; a datasheet DigiKey cannot serve must cost the datasheet and nothing else
- [ ] T049 [US3] Enrich the ECIA create-draft path in `app/catalog_service.py` / `app/product/routes.py` so a scanned bag for an uncataloged part with no captured order is filled in from DigiKey's data for that part number, not only from the label's own values (FR-033). When DigiKey is unavailable, fall back silently to today's label-only draft
- [ ] T050 [US3] Extend `tests/e2e/test_digikey_order.py` or add `tests/e2e/test_digikey_part.py`: capture a part by number and by product URL; confirm the product carries the manufacturer, part numbers, description and specifications; an unrecognized part number offers the ordinary form

**Checkpoint**: All three capture paths work. US3 also makes the pre-existing bag-scan draft
substantially richer.

---

## Phase 6: User Story 4 — The connection, and its failures (Priority: P4)

**Goal**: Set up once; when it is not working, be told which of the four states it is in, with
every other workflow unaffected.

**Independent Test**: With no DigiKey configuration present, open each DigiKey entry point and
verify each states that the connection is not configured and where to configure it, while
product search, scanning, manual purchases, receiving and the existing listing capture are all
unchanged.

- [ ] T051 [P] [US4] Add a shared "connection not configured" partial or macro under `app/templates/product/` and render it on every DigiKey entry point when `app.config['DIGIKEY_CLIENT']` is absent — with where to configure it, and never an error page (FR-036)
- [ ] T052 [US4] Audit each DigiKey route in `app/product/routes.py` so all five exceptions from [contracts/digikey-api.md](./contracts/digikey-api.md) §6 produce **distinguishable** operator-facing messages (FR-038): not configured; authorization expired or refused; order or part not found (including "may not be visible yet" for a just-placed order); throttled, with the retry time when `X-RateLimit-Reset` is present; unreachable or erroring
- [ ] T053 [P] [US4] Confirm a missing or wrong `DIGIKEY_ACCOUNT_ID` reports as **configuration**, not as an authorization failure: DigiKey answers `400 Account ID must not be 0`, which is the operator having not said which account, and telling them to renew an authorization would send them somewhere useless (FR-038)
- [ ] T054 [P] [US4] Write the unit tests for the failure paths in `tests/unit/test_digikey_capture.py`: each exception renders its own message and writes nothing (FR-039); a capture retried after the cause is fixed succeeds with no cleanup
- [ ] T055 [US4] Add the not-configured E2E case: with `DIGIKEY_CLIENT_ID` unset, every DigiKey screen states it, and product search, the scan box, manual purchase entry, receiving and the Amazon listing capture all behave exactly as they do today (FR-037, SC-008)

**Checkpoint**: Every failure state is legible, and the application without DigiKey is the
application as it was.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T056 [P] Document the feature in `docs/user-manual.md`: capturing a DigiKey order, the order screen, receiving by scanning a bag, capturing a single part, and setting up the connection. Correct the existing claim at `specs/001-product-catalog/data-model.md:70` that `order_reference` is "also filled from ECIA `K` / `1K`" — only `K` ever reached it, and now `1K` has its own column
- [ ] T057 [P] Update `_bmad-output/project-context.md` with the new configuration settings and the `app/services/digikey.py` module boundary, if the stack summary there is now incomplete
- [ ] T058 Regenerate documentation screenshots for the three new templates: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless`, then `nox -s screenshots_verify`. Screenshots churn on every run — review the diff and commit only what actually changed
- [ ] T059 Run the full gates: `nox -s tests` and `nox -s e2e` (**15-minute tool timeout**). Confirm `nox -s e2e` leaves the working tree clean
- [ ] T060 Work through [quickstart.md](./quickstart.md) §5 — the checks only reality can make: capture a real order and reconcile it line by line; **receive a real bag with the real wedge** (the only proof the scanner transmits the `GS` separators); a partially shipped order; a re-capture of an order that changed; and revoked credentials. Record the results in `specs/024-digikey-order-capture/verification.md` the way `specs/023-restore-forwarded-port/` did
- [ ] T061 [P] Confirm `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing, and that `.env`, `credentials.json` and `token.json` are still untracked

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Gate)** — no dependencies. **Blocks everything.** T002 can end the project's US1 scope
- **Phase 2 (Foundational)** — depends on Phase 1. Blocks all user stories
- **Phase 3 (US1)** — depends on Phase 2
- **Phase 4 (US2)** — depends on **Phase 3**: there is no line to receive until an order has been captured. The only genuine cross-story dependency in this feature
- **Phase 5 (US3)** — depends on Phase 2 only. **Parallel with Phases 3–4**
- **Phase 6 (US4)** — depends on whichever entry points exist; do it after 3–5
- **Phase 7 (Polish)** — depends on everything shipped

```
Phase 1 ──▶ Phase 2 ──┬──▶ Phase 3 (US1) ──▶ Phase 4 (US2) ──┐
                      │                                      ├──▶ Phase 6 (US4) ──▶ Phase 7
                      └──▶ Phase 5 (US3) ─────────────────────┘
```

### Within each story

- Tests are written first and must fail before the implementation lands
- Models before services, services before routes, routes before templates
- `app/models.py` tasks are parallel with each other; two tasks touching `app/catalog_service.py`, `app/product/routes.py` or `app/services/digikey.py` are **not** parallel

### Parallel opportunities

- **Phase 1**: T003, T004, T005 after T002
- **Phase 2**: T009 ∥ T010 (both `app/models.py`, different additions — sequence them if that file is contended); T015 ∥ T016
- **Phase 3**: T017 ∥ T018 ∥ T019 (all tests); T026 ∥ T028 ∥ T029 (different templates)
- **Phase 4**: T031 ∥ T032
- **Phase 5**: T040 ∥ T041; T042 ∥ T044
- **Phase 6**: T051 ∥ T053 ∥ T054
- **Phase 7**: T056 ∥ T057 ∥ T061

### Parallel example: User Story 1 tests

```bash
# Write all three US1 unit-test tasks together, then watch them fail:
T017  review states and the no-write assertion   tests/unit/test_digikey_capture.py
T018  the write: per-line outcomes                tests/unit/test_digikey_capture.py
T019  atomicity across a failing line             tests/unit/test_digikey_capture.py
# (Same file — write them as one sitting, three test classes.)

# And the three templates, which really are independent:
T026  app/templates/product/digikey_order_entry.html
T028  app/templates/product/digikey_order.html
T029  app/templates/base.html
```

---

## Implementation Strategy

### MVP first

1. **Phase 1** — the gate. If T002 lands on outcome (c), stop and report; do not build around it
2. **Phase 2** — column, dataclasses, client
3. **Phase 3** — US1
4. **Stop and validate**: capture a real order and reconcile it against DigiKey's own order page
5. Ship. Orders are recorded and the reorder list is correct about what is on the way

### Incremental delivery

| Increment | Delivers |
|---|---|
| Phases 1–2 | Nothing user-visible; everything below rests on it |
| + Phase 3 | **MVP** — capture an order, see it, receive lines by hand |
| + Phase 4 | Receiving by scanning — the workflow the issue asked for |
| + Phase 5 | Rich part data, and a much better bag-scan draft for uncaptured orders |
| + Phase 6 | Legible failures and a safe unconfigured state |
| + Phase 7 | Docs, screenshots, and the checks only reality can make |

### Notes

- `[P]` means different files and no dependency on an incomplete task
- Commit after each task or logical group; branch `issues/108`, merge by pull request
- **Never add a fixed wait to an E2E test.** Wait on an element; the rules and the worked
  examples are in `CLAUDE.md`
- **Never use `response.json()` in `app/services/digikey.py`.** It is the one line that would
  quietly turn every price into a float
