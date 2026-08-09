---

description: "Task list for Order Capture Confirmation"
---

# Tasks: Order Capture Confirmation

**Input**: Design documents from `specs/006-order-capture-confirmation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Branch**: `issues/58`

**Tests**: Included, and **not optional here**. Constitution IV requires that "changes that alter behavior MUST land with tests covering that behavior", and every task below alters behavior. Two of them alter behavior an existing test currently asserts the opposite of. Coverage is *not* a target — write the test that would have caught the bug, and stop.

**Organization**: Grouped by user story. The foundational phase is small on purpose: the schema change belongs to US3 and nothing else needs it, so the MVP (US1) ships without a migration.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: Which user story the task serves (US1–US4)
- Every task names the file it changes

## Path Conventions

Existing Flask app at the repository root: `app/` for source, `tests/unit/` and `tests/e2e/` for tests, `migrations/versions/` for Alembic. No new top-level directory.

---

## Phase 1: Setup

**Purpose**: Know that anything that breaks later, this feature broke.

- [ ] T001 Establish a green baseline on `issues/58` before changing anything: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and the same for `-s e2e` (15-minute tool timeout). Record any pre-existing failure rather than silently inheriting it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The confirm-then-write move, and the two type definitions the decision stories both need. T004 is here rather than in US1 because every story depends on the bookmarklet no longer writing on click — US1 cannot author a description on a purchase that already exists, and US3/US4 cannot ask a question about a write that has already happened.

**⚠️ CRITICAL**: No user story work begins until T002–T006 are done.

- [ ] T002 [P] Add the `CaptureAssessment` dataclass to `app/models.py` alongside the existing domain types — `duplicate_purchase_id`, `duplicate_order_date`, `duplicate_vendor`, `matched_product_id`, `matched_product_description`, `matched_product_manufacturer`, `matched_product_part_number`, all `Optional` and defaulting to `None`, plus `has_duplicate` and `has_uncorroborated_match` properties. **Plain values only, never ORM rows**: `CatalogService` methods close their session on the way out, so a `Product` handed to a template would lazy-load after close ([data-model.md](./data-model.md#captureassessment--the-new-in-memory-type)). Both flags can be true at once and the type must not assume otherwise.
- [ ] T003 [P] Add `CaptureDecisionRequired(WorkshopInventoryError)` to `app/exceptions.py`, taking `(message, assessment)` and exposing `assessment`. **Do not register a handler for it in `app/error_handlers.py`** — there is no handler for the base class today, so an unhandled one reaching the 500 page is the intended signal that a caller forgot to answer the question ([contracts/catalog-service.md](./contracts/catalog-service.md#new-capturedecisionrequired)).
- [ ] T004 Change the **form representation** of `api_capture` in `app/product/routes.py:406` to render `product/capture.html` pre-filled from the derived `vendor`, `vendor_item_id`, `url` and `listing_title` instead of calling `capture_order` and redirecting (FR-008, FR-009). Status 200, nothing written. The JSON representation still writes and still returns 201 in this task — its 409 arrives in T035. Leave `_capture_bookmarklet` (line 377) **byte-identical**: same endpoint, same two fields, same form-into-a-new-tab payload, so `test_the_bookmarklet_is_offered_and_points_at_this_server` stands. Rewrite the docstring's CSRF justification: the exempt path that arrives from a vendor's origin now writes nothing at all, which narrows the exemption rather than widening it.
- [ ] T005 Unit tests for T004 in `tests/unit/test_capture.py` (new `TestTheBookmarkletLanding` class): a form-encoded `POST /api/capture` returns 200, the body contains `id="capture-form"`, and `service.list_products()` is still empty afterwards. Assert the *absence of a write*, not just the status — a 200 that also created a purchase would pass a status-only test.
- [ ] T006 Confirm `tests/unit/test_product_csrf.py` still passes untouched: the JSON `POST /api/capture` still returns 201, and the `@csrf.exempt` count is still exactly 1. If either moved, T004 went further than it should have.

**Checkpoint**: `nox -s tests` green. Clicking the bookmarklet lands on a form and files nothing. No user-visible field has been added yet.

---

## Phase 3: User Story 1 — Author the description at capture (Priority: P1) 🎯 MVP

**Goal**: The operator writes the label description, and optionally the manufacturer and part number, while the vendor's listing is still on screen. The vendor's title is kept as the record of what the listing said, and is no longer what the operator has to live with.

**Independent Test**: Capture a listing URL, enter a description that differs from the listing title, submit, and confirm the product carries the entered description while the purchase still records the listing title verbatim. Then capture with the description blank and confirm the listing title is used instead.

### Implementation for User Story 1

- [ ] T007 [US1] Add `description`, `manufacturer` and `manufacturer_part_number` parameters to `capture_order` in `app/catalog_service.py:866`, after the existing ones so no positional caller breaks. Validate the description **only when it is non-blank** — `_clean` it first, then `_validate_description` (line 1795), which already gives FR-006's over-255 refusal and names the field. A blank description must fall back to the listing title and then to the existing `f"{vendor_name} item ..."` string at line 931 (FR-003), **not** raise. This is the opposite of the receipt rule in T014; getting the two the same way round is the point.
- [ ] T008 [US1] In the same method, apply the description at write time: a newly created product takes it via `create_product(description=..., manufacturer=..., manufacturer_part_number=...)`, and a product being attached to has its description updated **only when a non-blank description was supplied and differs** (FR-005). Never write `manufacturer` or `manufacturer_part_number` onto an existing product — a mismatch there is the evidence US4 depends on, and overwriting evidence is how the corruption comes back.
- [ ] T009 [US1] Parse the three new fields in both capture handlers in `app/product/routes.py` — `product_capture` (line 333, the POST branch at 342) and the JSON branch of `api_capture` (line 406) — and forward them to `capture_order`. The routes forward and render; they do not validate, trim, or decide.
- [ ] T010 [US1] Add the fields to `app/templates/product/capture.html`: `#description` as a text input with `maxlength="255"` placed directly under the listing-title field (lines 47–52) so the operator reads the vendor's wording and writes their own beneath it, and `#manufacturer` plus `#manufacturer_part_number` as an adjacent pair in a new row before the date/quantity/price row (line 54). Each pre-filled from `form_data`. Adjacency for the two is deliberate: the corroboration rule in US4 fires only when both are present. No new JavaScript — the page keeps loading `field-autocomplete.js` and nothing else.

### Tests for User Story 1

- [ ] T011 [P] [US1] Unit tests in `tests/unit/test_capture.py` (new `TestDescriptionAtCapture`): an entered description becomes the product's description while `purchase.listing_title` keeps the vendor's wording verbatim (FR-004); a blank description falls back to the listing title; no description and no listing title falls back to the generated string; a 300-character description raises `ValidationError` naming `description` and creates nothing (FR-006); a whitespace-only description is treated as blank; manufacturer and part number are stored on a newly created product; and attaching to an existing product with a changed description updates it (FR-005) while leaving that product's manufacturer and part number alone.
- [ ] T012 [P] [US1] Rewrite `test_attaching_does_not_overwrite_the_operators_own_description` at `tests/unit/test_capture.py:155` to assert the narrower property that is still true: the **vendor's listing title** never replaces the operator's description. It does not protect the operator's wording from the operator, which FR-005 now explicitly allows.
- [ ] T013 [US1] E2E in `tests/e2e/test_order_capture.py`: capture with a description differing from the listing title and assert the product page shows the operator's wording while the purchase history shows the vendor's; capture with the description blank and assert the fallback. Extend the existing `capture()` helper (line 15) rather than writing a second one — it already forwards `**fields` by element id, so `description=` works once T010 lands. Wait with `expect(...)`; these are full-page form navigations, so the assertion on the landed page is the whole wait.

**Checkpoint**: US1 ships on its own. No schema change, no migration, no new exception in play. The description is authored where the listing is.

---

## Phase 4: User Story 2 — Confirm or correct the description at receipt (Priority: P2)

**Goal**: The description is editable in place on the receive screen and is applied in the same submission that marks the purchase received.

**Independent Test**: Open a purchase's receive screen, change the description, press Mark Received once, and confirm the product carries the new description and the purchase is received. Then clear the description and submit, and confirm the submission is refused with nothing changed.

**Independent of US1** — different method, different template, and it works on purchases recorded by hand as well as captured ones (FR-025).

### Implementation for User Story 2

- [ ] T014 [US2] Add `description: Optional[str] = None` to `receive_purchase` in `app/catalog_service.py:971`. Validate through `_validate_description` **whenever the parameter is not `None`**, so a blank refuses the whole submission (FR-024) — the opposite of T007's capture rule, because at receipt there is no listing title to fall back to. Validate **before `with self._session()` opens**, matching how `update_product` does it, so a refusal leaves the received state untouched as well as the description.
- [ ] T015 [US2] Apply the description **outside** the `if not already_received:` guard at `app/catalog_service.py:1019`, next to the quantity/price/notes amendments which are also unguarded, and only when it differs from the product's current value (FR-026). This is the single easiest thing in the feature to put in the wrong place: inside the guard, correcting a description on an already-received purchase silently does nothing (FR-025).
- [ ] T016 [US2] Pass `description=request.form.get('description')` from `purchase_receive` in `app/product/routes.py:521` (POST branch, line 537). Forward unconditionally — the form always renders the field, and the blank case is the service's to refuse.
- [ ] T017 [US2] In `app/templates/product/receive.html`, move the description out of the read-only "What was ordered" block (the `#receive-product` row, line 22) and into the form as `#description`, `maxlength="255"`, pre-filled with `product.description` (FR-022). **Keep `purchase.listing_title` in the read-only block** — having both is the point, since the operator compares the vendor's wording with their own against the thing in hand. Also correct the `#already-received` banner at line 52: "Submitting again changes nothing" was already an overstatement (quantity, price and notes are amended on re-submit today) and the description makes it wrong; say what re-submitting does and does not change.

### Tests for User Story 2

- [ ] T018 [US2] Unit tests in `tests/unit/test_capture.py` (extend `TestAmendmentAtReceipt`) plus e2e in `tests/e2e/test_order_capture.py`. Unit: a supplied description updates the product in the same call that sets `received_date`; a blank one raises `ValidationError` and leaves **both** the description and `received_date` unchanged (FR-024); an omitted one changes nothing (FR-026); a description on an already-received purchase is applied while `received_date` does not move (FR-025) — the test that fails if T015 puts the assignment inside the guard; and a purchase created by `record_purchase` rather than `capture_order` behaves identically. E2E: edit the description on the receive screen, press Mark Received once, and assert the product detail page shows the new description with the purchase no longer outstanding. Seed with `live_server.add_test_products` and `record_purchase`; do not drive the capture form, which is not what this story is about.

**Checkpoint**: US1 and US2 both work, independently. The loop the feature is named for is closed.

---

## Phase 5: User Story 3 — Don't file the same order twice, and don't merge two orders (Priority: P3)

**Goal**: A repeat capture raises a warning naming the existing purchase and lets the operator decide; two genuinely separate orders of the same item on the same day can both be recorded.

**Independent Test**: Capture the same listing address twice on the same day. The second submission comes back with a warning naming the first purchase and writes nothing; ticking "record it anyway" produces a second purchase against the same product.

**Carries the schema change.** Everything in this phase after T023 depends on `listing_url` existing.

- [ ] T019 [US3] Add `listing_url = Column(String(1000), nullable=True)` to `Purchase` in `app/database.py:995`, next to `listing_title` (line 1018), and emit it from `Purchase.to_dict` (line 1059) alongside `listing_title`. **No index** — argued in [research.md](./research.md#why-listing_url-is-not-indexed), and at 1000 × utf8mb4 the column exceeds InnoDB's 3072-byte key limit anyway. No default; nothing here depends on NULL-versus-empty behaving a particular way.
- [ ] T020 [P] [US3] Create `migrations/versions/b1a0c0d10008_add_purchase_listing_url.py` with `down_revision = 'b1a0c0d10007'`. `upgrade()`: add the column, then backfill `SET listing_url = notes WHERE listing_url IS NULL AND notes LIKE 'http%'` — a **copy, not a move**, so nothing the operator wrote is destroyed and the statement is safe to re-run. `downgrade()`: `SET notes = listing_url WHERE listing_url IS NOT NULL AND (notes IS NULL OR notes = '')` *before* dropping the column, which is what makes the round trip lossless for rows this feature created. Raw SQL wrapped in `sa.text(...)` per the technology constraints. **Decide row C explicitly** — notes reading `https://… — arrived dented` matches `LIKE 'http%'` and would be copied whole; either tighten the predicate or state in the docstring that it is accepted ([quickstart.md](./quickstart.md#seed-rows-worth-losing)).
- [ ] T021 [US3] Exercise the revision against **MariaDB** following [quickstart.md](./quickstart.md#3-exercise-the-migration-both-ways) exactly: a throwaway `mariadb:11.8` container, **never the database in `.env`**. Seed rows A–D including row C, then `db upgrade`, `db downgrade b1a0c0d10007`, `db upgrade`, checking `DESCRIBE purchases` and the row contents at each step rather than trusting the exit code. Use the explicit revision id — `db downgrade -1` fails with `Error: No such option '-1'` in this Flask-Migrate CLI. Constitution V requires the downgrade to have been *run*, and **no automated test covers this revision**: both suites build the schema with `Base.metadata.create_all` (`tests/conftest.py:51`, `tests/e2e/test_server.py:62`).
- [ ] T022 [US3] Add `listing_url: Optional[str] = None` to `record_purchase` in `app/catalog_service.py:724`, positioned after `listing_title`, and change `capture_order`'s call at line 940 to pass `listing_url=url` and **stop passing `notes=url`** (line 948). Notes become the operator's notes. Update the docstring, which currently says the URL is "kept in the notes for later reference".
- [ ] T023 [US3] Rewrite `test_the_url_is_kept` at `tests/unit/test_capture.py:75` to assert `purchase.listing_url == AMAZON_URL` and that `purchase.notes` is empty. The old assertion (`AMAZON_URL in purchase.notes`) documents the placement this task deliberately changes.
- [ ] T024 [US3] Change `_find_captured_purchase` at `app/catalog_service.py:951` to take `listing_url` and use it as the fallback key: item id present → match on `vendor` + `vendor_item_id` + the day, as now; item id absent but URL present → match on `vendor` + `listing_url` + the day (FR-013); neither → `None`. Keep the existing midnight-to-midnight window so time of day still does not matter. The URL is compared with `==` after stripping and is **not normalized** — [research.md](./research.md#why-the-url-is-compared-exactly) says why, and the docstring should say it too, because the next reader will want to add a normalizer.
- [ ] T025 [US3] Replace the silent short-circuit in `capture_order` (`app/catalog_service.py:914–920`, which logs and returns the existing purchase) with the decision protocol: add `acknowledged_duplicate_of: Optional[int] = None`; when a duplicate is found and the acknowledgement does not name that exact purchase id, build a `CaptureAssessment` and raise `CaptureDecisionRequired` **before anything is written**; when it does name it, proceed and create a second purchase (FR-012, FR-014, FR-015). A stale acknowledgement naming a different purchase re-raises with the freshly detected one. Resolution table in [contracts/catalog-service.md](./contracts/catalog-service.md#acknowledged_duplicate_of).
- [ ] T026 [US3] Catch `CaptureDecisionRequired` in `product_capture` (`app/product/routes.py:333`) in the same `try` that already catches `ValidationError`, and re-render `product/capture.html` with `assessment=e.assessment` and `form_data=request.form`. Status 200, nothing flashed as an error — this is a step in a flow, not a failure. Forward `acknowledged_duplicate_of` from the form. The route detects nothing itself.
- [ ] T027 [US3] Add the `#duplicate-warning` block to `app/templates/product/capture.html`, rendered when `assessment and assessment.has_duplicate`. It names the existing purchase with its order date, links to it (a plain `GET`, so choosing it writes nothing), and offers a checkbox named `acknowledged_duplicate_of` valued with that purchase id: *"This is a separate order — record it anyway."* Place it above the form's fields so it cannot be missed.
- [ ] T028 [US3] Rewrite `TestIdempotency` at `tests/unit/test_capture.py:82` as `TestDuplicateDetection` — **rewritten, not deleted**: its four surviving properties (same day matches, a different day does not, a different vendor does not, time of day is irrelevant) are all still true, and only the outcome changes from "returns the same purchase" to "raises with an assessment naming it". Add: an acknowledgement naming the detected purchase proceeds and yields a second purchase against one product; a stale acknowledgement re-raises; a capture with no item id but a matching `listing_url` is detected (FR-013); one with neither is not; and a raise leaves `list_products()` and the purchase count untouched. Then rewrite `test_capturing_the_same_listing_twice_creates_nothing_new` at `tests/e2e/test_order_capture.py:48` for the warn-and-choose flow, and add an e2e for the no-item-number URL fallback using an address such as `https://www.mcmaster.com/91290A115/`. Use `expect(...).to_have_count(...)` for the product-count assertions in new tests rather than `.count()`.

**Checkpoint**: a double click costs one extra click and files one purchase; two real orders on one day are two purchases. `nox -s tests` and `nox -s e2e` green.

---

## Phase 6: User Story 4 — Be told when a vendor's item number already names something else (Priority: P4)

**Goal**: A captured item number that already names a product produces a named choice rather than a silent attach — unless the manufacturer and part number both corroborate.

**Independent Test**: Record a product carrying a vendor item number and a part number, then capture a listing with that same item number and no manufacturer. The confirmation step names the existing product, shows its part number, and requires a choice before anything is written.

**Depends on T002 and T003 only** — it does not need the schema change from US3, and can ship before it.

- [ ] T029 [US4] Add the module-level helpers `_fold(value)` (`(value or '').strip().casefold()`) and `_corroborates(product, manufacturer, part_number)` to `app/catalog_service.py`, near `_clean` (line 1978). Corroboration requires **both** values present and both fold-equal to the product's (FR-019). **Python-side, never a `WHERE` clause**: this is the one comparison in the feature that acts without asking the operator, and the deployed collation folds accents where SQLite folds nothing ([research.md](./research.md#the-collation-question)). Case-fold only — do not strip accents, because `Würth` and `Wurth` are not reliably one manufacturer.
- [ ] T030 [US4] Add `attach_to: Optional[Union[int, str]] = None` to `capture_order` and replace the unconditional attach at `app/catalog_service.py:922–938` with the resolution table in [contracts/catalog-service.md](./contracts/catalog-service.md#product-resolution-in-full): no item id or no match → create; match corroborated → attach silently; match uncorroborated → raise `CaptureDecisionRequired` with the matched product's description, manufacturer and part number in the assessment (FR-017, FR-018); `attach_to='new'` → create regardless, leaving the matched product and **its identifiers** untouched (FR-020); `attach_to=<id>` → attach, or fall back to creating and log it if that product has vanished; `attach_to=<id>` naming a product other than the detected match → re-raise as stale.
- [ ] T031 [US4] Forward `attach_to` from the form in `product_capture` (`app/product/routes.py:333`) and from the JSON body in `api_capture`. The `CaptureDecisionRequired` catch added in T026 already handles the render; if US4 ships before US3, add that catch here instead and T026 becomes a no-op.
- [ ] T032 [US4] Add the `#identifier-warning` block to `app/templates/product/capture.html`, rendered when `assessment and assessment.has_uncorroborated_match`. Show the matched product's description and part number, and a radio pair named `attach_to` — the product's id (*"Add this purchase to it"*) and `new` (*"This is a different product"*). **No option pre-selected**, so a submit that skips the question comes straight back: FR-018 says the capture is not written until they choose. Both this and `#duplicate-warning` can render at once; do not make them exclusive.
- [ ] T033 [P] [US4] Rewrite `test_capture_attaches_to_a_product_that_already_owns_the_identifier` at `tests/unit/test_capture.py:143` — it asserts the silent attach this story removes. The new form: an uncorroborated match raises with the product named and writes nothing; the same capture with `attach_to=<id>` attaches; with `attach_to='new'` creates a second product while the first keeps its `VENDOR` identifier and its purchases; and `attach_to` naming a deleted product creates rather than raising. Add a `TestCorroboration` class: both values matching (including differing case and surrounding whitespace) attaches silently; manufacturer only asks; part number only asks; neither asks; and a matched product carrying no manufacturer never corroborates.
- [ ] T034 [US4] E2E in `tests/e2e/test_order_capture.py`, replacing the attach test at line 92: seed a product with a `VENDOR` identifier, manufacturer and part number via `live_server.add_test_products`; capture the same item number with no manufacturer and assert `#identifier-warning` names the product and that `/products` still shows one row; submit without choosing and assert it comes back unwritten; choose "different product" and assert two products with the first's identifier and history intact; then capture again supplying both values in the wrong case and assert it attaches with no warning shown.

**Checkpoint**: all four stories done. A recycled identifier can no longer corrupt a price history without the operator having seen the product and chosen.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T035 Return **409** with `{'success': False, 'error': ..., 'assessment': {...}}` from the JSON representation of `api_capture` (`app/product/routes.py:406`) when `CaptureDecisionRequired` is raised, serializing the dataclass fields directly. The 201 and 400 paths keep their current shapes, which is what keeps `tests/unit/test_product_csrf.py` passing. Add a unit test for the 409 and for the re-post that resolves it.
- [ ] T036 [P] Update `docs/product-functionality-gap.md`: the four paragraphs under "Order capture" describing the missing description at capture, the read-only description at receipt, the duplicate cases and the recycled identifier now describe built behaviour. Leave the price paragraph, which is still #56. That document is a record of what was planned and not built — leaving shipped work in it makes it wrong, not merely stale.
- [ ] T037 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless`, then `git status --porcelain`. `app/templates/product/**` changed, so the Development Workflow gate applies — but the screenshot set covers inventory-item pages only, so the **expected result is an empty diff**. A diff here means something unrelated moved and needs explaining before the PR.
- [ ] T038 Walk [quickstart.md](./quickstart.md#4-manual-validation-one-section-per-user-story) section 4 end to end, including the bookmarklet landing **over TLS against a real vendor listing** — the one path with no automated coverage, because CI has neither TLS nor a vendor's content policy.
- [ ] T039 Final gate: `nox -s tests` and `nox -s e2e` green, and grep `tests/e2e/test_order_capture.py` for `wait_for_timeout`, `time.sleep` and `networkidle` — all three are prohibited outright by Constitution IV, with no exemption for a call site that was convenient.

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (T001)**: no dependencies.
- **Foundational (T002–T006)**: blocks every story. T002 and T003 are two type definitions and are trivially parallel; T004 is the behaviour change and T005/T006 prove it.
- **US1 (T007–T013)**: needs T004. Needs nothing else — no migration, no exception in play. **This is the MVP.**
- **US2 (T014–T018)**: needs nothing from Foundational at all in principle, and nothing from US1. It could ship first; it is second because US1 is the headline.
- **US3 (T019–T028)**: needs T002, T003 (the assessment and the exception) and carries the schema change.
- **US4 (T029–T034)**: needs T002 and T003. **Does not need US3** — it can ship before the migration.
- **Polish (T035–T039)**: T035 needs T025 or T030 (something must be able to raise); the rest need everything.

### File-level conflicts to sequence

Four files are touched by more than one story. Nothing here is a logical dependency — it is a merge-conflict warning for whoever works out of order.

| File | Tasks | Note |
|---|---|---|
| `app/catalog_service.py` (`capture_order`) | T007, T008, T025, T030 | Four tasks in one method. Do them in task order; T025 and T030 each replace a different block. |
| `app/product/routes.py` (`product_capture`, `api_capture`) | T004, T009, T026, T031, T035 | T026 and T031 both add to the same `try`; whichever lands first, the other checks rather than duplicates. |
| `app/templates/product/capture.html` | T010, T027, T032 | T010 adds fields; T027 and T032 add sibling warning blocks above them. |
| `tests/unit/test_capture.py` | T005, T011, T012, T018, T023, T028, T033 | Seven tasks, mostly in different classes. T012, T023, T028 and T033 rewrite existing tests — read the old assertion before replacing it, because each documents a behaviour this feature deliberately inverts. |

### Parallel opportunities

- T002 ‖ T003 — two files, no shared symbol.
- T011 ‖ T012 — different classes in the same file; sequence if that bothers you.
- T020 can be written while T019 is in progress; T021 cannot start until both are done.
- **US2 ‖ US4** is the real one: different service methods, different templates, no shared task. Two people can take them at once.
- US3 and US4 both edit `capture_order` and `capture.html`, so they parallelize poorly despite having no logical dependency.

### Within each story

- Service before route before template. The template renders what the service produced; building it first means building against a guess.
- Rewritten tests land with the change that inverts them, never after. A commit where `TestIdempotency` still asserts the old contract against the new code is a commit where the suite is lying.

---

## Implementation Strategy

### MVP — User Story 1 only

1. T001 (baseline) → T002–T006 (foundational) → T007–T013 (US1).
2. **Stop and validate**: capture a real listing, write a description, confirm the product carries it. Click the bookmarklet and confirm the new tab holds a form rather than a filed purchase.
3. Shippable. No schema change, no migration, nothing to roll back but code.

### Incremental delivery

1. Foundational → US1 → **the description is authored where the listing is** (the headline).
2. + US2 → **the loop closes** — correct it with the thing in hand, in one submission.
3. + US4 → **the invisible failure is gone** — a recycled identifier can no longer corrupt a price history silently. Still no migration.
4. + US3 → **duplicates are the operator's call**, and the schema change lands last, on its own, where a rollback is a single revision.

Deferring US3 to last is deliberate: it is the only phase that touches the database, and it is the lowest-priority story. Everything above it ships and can be lived with while the migration is exercised properly.

### Single-developer ordering

T001 → T002 → T003 → T004 → T005 → T006 → T007 … T039 in number order. The numbering is already a valid serial schedule; the [P] markers only matter if someone else is working alongside.

---

## Notes

- **Two rules that look alike and are not**: a blank description at capture falls back to the listing title (T007); a blank description at receipt is refused (T014). There is no listing title to fall back to at receipt. Both are tested.
- **One placement that is easy to get wrong**: the description assignment in `receive_purchase` goes *outside* the `already_received` guard (T015). Inside it, FR-025 fails silently and the only test that catches it is the one written for exactly that.
- **Four existing tests assert behaviour this feature inverts**: `tests/unit/test_capture.py:75`, `:82` (the whole class), `:143` and `:155`, plus `tests/e2e/test_order_capture.py:48` and `:92`. Every one is rewritten by a numbered task. If a task deletes one instead, the property it protected needs to be re-asserted somewhere or it has been quietly dropped.
- **The migration has no automated coverage.** T021 is the coverage. It runs against a throwaway container, and it is not optional.
- [P] means different files and no dependency on an incomplete task. Commit after each task or logical group.
