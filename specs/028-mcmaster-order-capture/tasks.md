---

description: "Task list for 028-mcmaster-order-capture"
---

# Tasks: McMaster-Carr Order and Product Capture

**Input**: Design documents from `/specs/028-mcmaster-order-capture/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Included, and **not optional here**. Constitution IV: "Changes that alter behavior
MUST land with tests covering that behavior", and `nox -s tests` / `nox -s e2e` must pass before
a change is merged. Write the test that would have caught the bug, and stop — coverage is
deliberately not a target.

**Organization**: By user story, so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable — different files, no dependency on an incomplete task
- **[Story]**: US1–US4, mapping to the user stories in [spec.md](./spec.md)

## Path Conventions

Server-rendered Flask app, four layers (Constitution II): `app/models.py` (domain dataclasses),
`app/database.py` (ORM), `app/catalog_service.py` (business logic), `app/product/routes.py`
(thin routes), `app/templates/product/`, `app/static/js/`. Tests in `tests/unit/` and
`tests/e2e/`. Run everything through `nox`, never bare `pytest`.

Prefix every nox invocation: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`.

---

## Phase 1: Gate — the fixtures

**Purpose**: No selector in this feature can be written before these exist. This is an *input*,
not an artifact of the work — research.md §5.

**⚠️ This phase blocks Phases 3, 4, 5 and 6 entirely.** Phase 2 can proceed without it.

- [X] T001 Save one order from McMaster's **order history** — the page FR-001 names, not the checkout confirmation — fully rendered, to `tests/e2e/fixtures/mcmaster_order.html`. Save as complete HTML from the browser: McMaster builds pages client-side, so "view source" yields a shell and not the document the agent reads. Choose an order with several lines and at least one pack-priced line
- [X] T002 **Scrub `tests/e2e/fixtures/mcmaster_order.html` before it is committed.** It carries the ship-to address, and possibly a name, a phone number or the last digits of a card. None of it is read by this feature and none of it belongs in the repository. Part numbers, descriptions, quantities and prices are the fixture; everything else comes out. Verify by reading the file, not by grepping for a pattern you guessed
- [X] T003 [P] Save one McMaster product page, fully rendered, to `tests/e2e/fixtures/mcmaster_product.html`. Prefer a pack-priced item so FR-020's arithmetic has something real to run against, and one whose page shows a specification table and an image
- [X] T004 Record what the fixtures actually show in [research.md](./research.md) §5, closing the plan's one TBD: the **order-page path shape** (the dispatch in [contracts/capture-payload.md](./contracts/capture-payload.md) §1 is marked TBD pending this), confirmation that the product path is `/<part-number>/`, and the per-line element structure the order reader will walk

**Checkpoint**: The unknown is closed. Every selector below now has something to be written against.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The schema change and the agent's dispatch. Everything here is shared by more than
one story, or is a schema change that should land on its own.

**Independent of Phase 1** — none of it reads McMaster's markup.

### The column rename (research.md §8, data-model.md §1)

- [X] T005 Create an Alembic revision under `migrations/versions/` renaming `purchases.digikey_line_number` to `purchases.order_line_number`. `down_revision` is the current head; the `downgrade` renames it back. Type, nullability and the absence of an index are unchanged. Do **not** edit `a7c4e1b0f221`, the revision that created the column — shipped migrations are frozen (`CLAUDE.md`)
- [X] T006 Rename the column in `app/database.py:1102` and the corresponding key in `Purchase.to_dict()`. Rewrite the comment above it so it explains the *general* rule — a part number does not identify a line, and pairing positionally corrupted data — rather than naming DigiKey. Keep the "must match migration ... exactly" warning and point it at the new revision: the unit suite builds its schema with `create_all` and never runs Alembic, so drift passes `nox -s tests` and fails on the real database
- [X] T007 Rename the call sites in `app/catalog_service.py` — `_recorded_digikey_lines` (`:1939`) and the write in `capture_digikey_order`. Mechanical; no behaviour changes
- [X] T008 [P] Update `tests/unit/test_digikey_capture.py` for the new column and `to_dict` key. These tests are the check that the rename did not disturb line-to-purchase pairing
- [X] T009 Exercise the migration **both ways** against the real database (Constitution V): `venv/bin/python manage.py db upgrade`, then `db downgrade -1`, then `db upgrade` again. A `downgrade` that has not been run is not reversible

### The agent's dispatch (research.md §3, contracts/capture-payload.md §1)

- [X] T010 Add the page dispatch at the entry point of `app/static/js/capture-agent.js`, keyed on the **URL path** and never the hostname. Three outcomes: McMaster order page, McMaster product page, and everything else — which runs today's Amazon path. **Do not edit the Amazon section**; the dispatch wraps it. Path-keying is what makes the e2e harness able to drive the McMaster readers at all, since it serves vendor fixtures from the application's own origin
- [X] T011 Extend `submitCapture()` in `app/static/js/capture-agent.js` to add a `vendor` hidden field, populated **only** when a McMaster page was recognized. `product_capture()` already prefers a submitted vendor over a derived one (`app/product/routes.py:468`), so nothing on the server changes for the product path. An Amazon capture must send no `vendor` field and be byte-identical to today
- [X] T012 [P] Add `MCMASTER_VENDOR = 'McMaster-Carr'` in `app/catalog_service.py` beside `DIGIKEY_VENDOR` (`:83`). It must equal what `_vendor_from_url` derives from `mcmaster.com` (`app/product/routes.py:831`) — the two are compared, and a mismatch would make every captured order unfindable
- [X] T013 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and the existing capture e2e (`tests/e2e/test_product_page_capture.py`, `test_order_capture.py`) and confirm the Amazon path is untouched. This is the first of the SC-010 checks and the cheapest place to catch a dispatch that fires when it should not

**Checkpoint**: The schema is renamed and reversible, the agent knows what page it is on, and
nothing the application did before behaves differently.

---

## Phase 3: User Story 1 — Capture a whole McMaster order (Priority: P1) 🎯 MVP

**Goal**: Click the bookmarklet on a McMaster order page, review every line, confirm, and get
one outstanding purchase per included line — with the order number, quantity and unit price
McMaster stated, and nothing typed that the page already said.

**Independent Test**: With `mcmaster_order.html` served locally, run the capture, confirm the
review, and verify every included line became exactly one outstanding purchase against a product
carrying that line's McMaster part number, at the quantity and unit price the page stated.

### Tests for User Story 1

- [X] T014 [P] [US1] Write `tests/unit/test_mcmaster_payload.py` for `McMasterOrder.from_payload` / `McMasterOrderLine.from_payload`: a well-formed order; an unknown `version`; a non-object; a body with no `order_number`; `lines: []` with a valid order number; one malformed line dropped while the rest survive; a line with a part number and no description, and the reverse; a line with neither, dropped. Assert `lines_read` stays what the agent reported and does not collapse to `len(lines)` — that difference is the whole of FR-004
- [X] T015 [P] [US1] In the same file, test the pack arithmetic (FR-020): `packs × pack_size` is the recorded quantity in **units**; `unit_price` is `price_to_cents(pack_price / pack_size)`; an absent `pack_size` means one unit is one unit; `price_rounds` is true exactly when the division loses precision to the cent. Assert prices arrive as **strings** and become `Decimal` — a JSON number would already be a `float` before any assertion could see it (Constitution III)
- [X] T016 [P] [US1] Write `tests/unit/test_mcmaster_capture.py` for `review_mcmaster_order`: each of the four `OrderLineState` values, tested in the order CAPTURED → CONFLICT → MATCHED → NEW, plus a line with no part number, and a suggested description that exceeds `MAX_DESCRIPTION_LENGTH` being pre-filled with a value that fits rather than silently truncated
- [X] T017 [P] [US1] In the same file, test `capture_mcmaster_order`: one purchase per included line with vendor, order number, line number, units, unit price and order date; an excluded line writing nothing; a `NEW` line creating a product with a `DISTRIBUTOR` identifier scoped to McMaster-Carr; an `MPN` written **only** when the page stated a manufacturer part number; a re-capture recording nothing (SC-003); a changed quantity applied only with `apply_change`; a recorded purchase no line claims reported and not deleted; and a `ValidationError` leaving the database unchanged (SC-009)

### Implementation for User Story 1

- [X] T018 [US1] Implement `McMasterOrderLine` and `McMasterOrder` as frozen dataclasses in `app/models.py`, per [data-model.md](./data-model.md) §2. `from_payload` **never raises on a JSON value** — a field McMaster stops emitting costs that field alone. Derived properties: `quantity`, `unit_price`, `price_rounds`, `form_key`. `form_key` is `str(line_number)` falling back to the part number: keying a form by part number gave two lines of one order a single shared set of controls (024, PR #116 review), and the same trap exists here
- [X] T019 [US1] Write the McMaster **order** reader in `app/static/js/capture-agent.js`, against the fixture from T001. Every extraction step independent and optional (FR-036); nothing may throw. Count **every** line element seen into `lines_read`, including ones it cannot use — that is what makes "three of your fourteen lines" sayable
- [X] T020 [US1] Branch `api_capture()` in `app/product/routes.py:698` on an `order` form field that parses as a McMaster order, per [contracts/routes.md](./contracts/routes.md). It still **writes nothing**. A request with no `order` field must take a path identical to today's
- [X] T021 [US1] Implement `review_mcmaster_order` in `app/catalog_service.py`, returning `ReviewedLine` values (reused unchanged — `ReviewedLine.part` stays `None` for every McMaster line, because the page *is* the detail). Reads only
- [X] T022 [US1] Implement `_recorded_mcmaster_lines` in `app/catalog_service.py`, pairing an order's lines to purchases already recorded for it **by `order_line_number`** — never by position, never by part number. Model it on `_recorded_digikey_lines` (`:1939`) and keep its second pass for purchases carrying no line number
- [X] T023 [US1] Create `app/templates/product/mcmaster_order_review.html`: every line with its part number, McMaster's description, packs, pack size, pack price, computed units and computed unit price (both editable), its state, an include checkbox, an authored description for `NEW` lines, and a resolution choice for `CONFLICT` lines. Carry the payload through in a hidden `order` field — this is the FR-006 mechanism, and there is nothing to re-read if it is lost
- [X] T024 [US1] Add `POST /products/mcmaster/orders/capture` and `_mcmaster_decisions(form, order)` in `app/product/routes.py`. Build decisions by walking the **payload's** lines, so a decision submitted for a line the payload does not carry is ignored rather than acted on. CSRF-protected — it is same-origin, unlike `/api/capture`
- [X] T025 [US1] Implement `capture_mcmaster_order` in `app/catalog_service.py`: one transaction, one purchase per included line, `received_date` NULL (FR-011). Written as its own method beside `capture_digikey_order`, **not** by refactoring it — research.md §7
- [X] T026 [US1] Write the identifiers (FR-012): `DISTRIBUTOR` scoped to `McMaster-Carr` for the part number, `MPN` **only** where the page actually stated a manufacturer part number. This is the inverse of the DigiKey case, and inventing an `MPN` McMaster never stated would collide with a real one later
- [X] T027 [US1] Implement the re-capture reconciliation (FR-015 – FR-017): already-captured lines shown and not re-written; a changed quantity or price shown against what is recorded and applied only on `apply_change`; an unclaimed purchase reported and never deleted. Compare **both sides rounded** — the recorded price has been through a `Numeric(10, 2)` column and the fresh one has not, and comparing raw against stored made "Update it?" reappear forever on a sub-cent line (PR #116 review). Pack division reaches the same trap
- [X] T028 [US1] Add a capture summary flash naming **every** outcome that changed the database, including a capture that only applied a quantity change — leading on the purchase count alone would report "Nothing new" over the top of a write that landed. Model it on `_digikey_capture_summary` (`app/product/routes.py:1150`)
- [X] T029 [US1] Implement `find_mcmaster_order_lines` in `app/catalog_service.py` and `GET /products/mcmaster/orders/<order_number>` in `app/product/routes.py`. Derived, never stored: the order **is** the purchases carrying its number. An order number nothing was captured against renders "not captured" with a way forward, not a 404 (FR-031)
- [X] T030 [US1] Create `app/templates/product/mcmaster_order.html`: every line with its product, quantity, unit price and state, and the outstanding count (FR-027, FR-028). `?highlight=<part number>` marks a line, for arriving here from a scan
- [X] T031 [US1] Write `tests/e2e/test_mcmaster_order.py`, reusing `run_bookmarklet` from `tests/e2e/test_product_page_capture.py`: serve `mcmaster_order.html` from the app's own origin at the order path, click the **real** bookmarklet, land on the review, confirm, and assert the purchases. Waits name elements, never durations — the landing is a full navigation, so the review form's presence is the completion signal (pattern C in `CLAUDE.md`)
- [X] T032 [US1] Add the E2E cases that prove nothing was written when nothing should have been: closing the review without confirming leaves the product and purchase counts unchanged (FR-005); an excluded line produces neither a product nor a purchase (FR-009); a second capture of the same order records nothing (SC-003). Establish the review region with `expect(...)` before any negative assertion — a count read against a page that has not rendered passes trivially
- [X] T033 [US1] Add the E2E case for the order screen: every line's state and the outstanding count, reached by capturing and then opening the order (US1 scenario 8)

**Checkpoint**: A fourteen-line order is captured in one click plus the descriptions, and the
issue's second half is delivered. This is the MVP.

---

## Phase 4: User Story 2 — Capture one McMaster part (Priority: P2)

**Goal**: The same bookmarklet on a McMaster **product** page fills in the confirmation form —
part number, description, price, pack size, specifications, image — with nothing typed.

**Independent Test**: With `mcmaster_product.html` served locally, click the bookmarklet and
verify the confirmation page arrives carrying those values, and that confirming creates the
product with them.

**Independent of US1**: it uses `ListingCapture` and the confirmation form that already exist.

### Tests for User Story 2

- [X] T034 [P] [US2] Add `_mcmaster_part_from_url` cases to `tests/unit/test_routes.py`: `https://www.mcmaster.com/91290A115/` and `.../91290A115/socket-head-screws/` both yield `91290A115`; an Amazon address, a bare host and an empty string yield `''`. Blank is the ordinary answer, never an error
- [X] T035 [P] [US2] Add a unit test asserting a McMaster product capture writes a `DISTRIBUTOR` identifier scoped to `McMaster-Carr` and writes **no** `MPN` when the page named no manufacturer

### Implementation for User Story 2

- [X] T036 [US2] Implement `_mcmaster_part_from_url` in `app/product/routes.py` beside `_asin_from_url` (`:841`), and use it in `product_capture()` the way the ASIN reader is used (FR-025). The pattern is **deliberately duplicated** between agent and server — they are on opposite sides of a machine boundary, and `capture-agent.js:38` carries the same note for the Amazon pair
- [ ] T037 [US2] Write the McMaster **product** reader in `app/static/js/capture-agent.js` against the fixture from T003: part number as `vendor_item_id`, McMaster's description as `listing_title`, the price, the specification table as `specifications`, the image addresses. Leave `brand` empty when the page names no manufacturer — that is a fact about McMaster, not a miss
- [X] T038 [US2] Have the product reader also send `pack_price` and `pack_size`, which pre-fill the confirmation form's existing pack fields from feature 017. They are **UI-only and recorded nowhere** (`app/templates/product/capture.html:212`); what is stored is a unit price
- [ ] T039 [US2] Write `tests/e2e/test_mcmaster_product.py`: bookmarklet on the product fixture → the confirmation form pre-filled → confirm → the product carries the values and the scoped identifier. Reuses the same harness as T031
- [ ] T040 [US2] Add the E2E case for the paste-a-URL path with no agent involved: a McMaster address gives vendor `McMaster-Carr` and the part number (FR-025)
- [ ] T041 [US2] Add the E2E case that the existing duplicate handling applies unchanged when the part number already names a product — the operator is shown the match and must choose before anything is written (FR-026)

**Checkpoint**: The issue's first half is delivered, and the visibly-broken case — the bookmarklet
yielding nothing but a URL on a McMaster page — is fixed.

---

## Phase 5: User Story 3 — Receive the box (Priority: P3)

**Goal**: Scan the part number off a bag and land on the receipt for the outstanding line it
belongs to; where several match, choose; where none match, nothing changes.

**Independent Test**: Capture an order, scan one line's part number, and verify the scan lands on
that line's receipt rather than the product page; confirm it and verify the purchase is received,
the counted quantity rose, and the outstanding count fell by one.

**Depends on US1** — there is no line to receive until an order has been captured. The only
genuine cross-story dependency in this feature.

### Tests for User Story 3

- [ ] T042 [P] [US3] Write `tests/unit/test_mcmaster_receive.py` for `find_mcmaster_receivable`: one outstanding match; two outstanding matches across two orders; a received-only match returning nothing; a part number with no McMaster purchase at all
- [ ] T043 [P] [US3] In the same file, test the `resolve_scan` branch for all three FR-032 cases, **and** the non-regressions that matter more: an ASIN still resolves to `product`, an ECIA label still takes the ECIA branch, a GTIN and an internal code never reach the free-text branch, and a McMaster part number with no outstanding line falls through byte-for-byte to today's answer
- [ ] T044 [P] [US3] Add a test that `_receive_url`'s three DigiKey outcomes are unchanged after it stops reading `ecia_fields` — this helper is shared, and the DigiKey behaviour is what FR-033 protects

### Implementation for User Story 3

- [ ] T045 [US3] Implement `find_mcmaster_receivable` in `app/catalog_service.py`: outstanding McMaster purchases whose `vendor_item_id` equals the scanned value. Filters to **outstanding only** — unlike DigiKey's `find_receivable`, which deliberately includes received rows so it can distinguish "already received" from "no such line" for a label that names an order. A bare part number names no order, so there is no such distinction to draw
- [ ] T046 [US3] Add the branch to `resolve_scan`'s **FREE_TEXT** case in `app/catalog_service.py`, **before** the vendor-scoped identifier lookup. The precedence is load-bearing and the ECIA branch already documents why (`:2333`): capturing an order creates products carrying these part numbers, so the identifier lookup would match happily and a bag for a part you have bought before would open the product page instead of its receipt
- [ ] T047 [US3] Change `_receive_url` in `app/product/routes.py:1495` to read the vendor and the order number off the **matched purchases** instead of `resolution.classification.ecia_fields` (`:1515`), which is empty for a free-text scan. Better for DigiKey too: the purchases carry it either way. `app/static/js/scan-capture.js` navigates to whatever this returns without inspecting the outcome, so it needs no change
- [ ] T048 [US3] Add `GET /products/purchases/receive-choice` in `app/product/routes.py` and `app/templates/product/receive_choice.html`: one row per candidate — order number, order date, quantity, unit price, product — each linking to its own receipt. The catalog does not pick one (FR-032a). Zero candidates by the time it loads renders "nothing outstanding for this part" and offers the product; never an empty list, never a 404
- [ ] T049 [US3] Add a receive control per outstanding line on `app/templates/product/mcmaster_order.html`, with an editable quantity, routing to the existing `purchase_receive` (FR-029). Receiving itself is untouched: the purchase is marked received, a counted product's quantity rises, a manual low/out flag is cleared
- [ ] T050 [US3] Write `tests/e2e/test_mcmaster_receive.py`: capture an order, scan one line's part number, land on **its receipt**, amend the quantity, confirm, and assert the purchase, the product quantity and the outstanding count. A click that fires a `fetch` has not finished when `click()` returns — wait for what the response changes on the page
- [ ] T051 [US3] Add the E2E case for two candidates: capture a second order carrying the same part, scan it, and assert the chooser lists both and nothing was received (FR-032a)
- [ ] T052 [US3] Add the E2E case for the fall-through: scanning a part number with no outstanding McMaster line behaves exactly as it does today (FR-032b), and scanning an already-received line receives nothing twice

**Checkpoint**: The box can be unpacked a bag at a time, and what is left outstanding is what
McMaster did not ship.

---

## Phase 6: User Story 4 — Say what the page did not give up (Priority: P4)

**Goal**: A capture that read less than the page shows says so, on the review, before anything is
confirmed — and still captures everything that did read.

**Independent Test**: Capture against an order fixture with the price markup stripped: every line
still reads, prices are blank and editable, and the review states that prices could not be read.

**Depends on US1** for the review to state anything on.

- [ ] T053 [P] [US4] Create two stripped fixtures from T001's page: `tests/e2e/fixtures/mcmaster_order_no_prices.html` (price markup removed, lines intact) and `tests/e2e/fixtures/mcmaster_order_unreadable.html` (no recognizable lines at all)
- [ ] T054 [US4] Render the line tally on `mcmaster_order_review.html`: how many lines were read and how many are offered (FR-004). Equal, it says nothing; different, it is the difference between "your order has three lines" and "I could only read three of your fourteen", and those must not look the same
- [ ] T055 [US4] Mark, per line, which fields came back empty, and leave them editable (FR-037). A blank price on one line of fourteen is not something the operator will notice unaided
- [ ] T056 [US4] Handle a payload with a valid order number and **no readable lines**: a plain statement and the hand-entry way forward (FR-038). Never an empty review that reads like an empty order, and never an error page
- [ ] T057 [US4] Carry the incompleteness into the post-confirm flash, so the record of which lines came back thin survives leaving the review page (FR-037)
- [ ] T058 [US4] Add the E2E degradation cases against both stripped fixtures, asserting the statements appear and that the readable lines still capture with their part numbers and quantities intact

**Checkpoint**: A markup change costs fields, not silence.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T059 [P] Document the feature in `docs/user-manual.md`: capturing a McMaster order from order history, the order screen, receiving by scanning a bag, and capturing a single part. Note explicitly that McMaster needs no configuration — unlike DigiKey — because there is nothing to set up
- [ ] T060 [P] Update `_bmad-output/project-context.md` if the stack summary there is now incomplete
- [ ] T061 Run the SC-010 regression set and read the results as this feature's own: `tests/e2e/test_product_page_capture.py`, `test_order_capture.py`, `test_digikey_order.py`, `test_digikey_part.py`, `test_digikey_receive.py`, `test_ecia_scan.py`, `tests/unit/test_digikey_capture.py`. Also confirm by hand that scanning an Amazon ASIN still opens its product page
- [ ] T062 [P] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s lint`
- [ ] T063 Run the full gates: `nox -s tests`, then `nox -s e2e` **detached** (`nohup ... &` and poll) — it takes about 13m 45s warm and **outlasts a ten-minute agent bash timeout**, so a foreground run reports a false timeout on a passing suite. Confirm the working tree is clean afterwards, and that `grep -rn "wait_for_timeout\|time.sleep" tests/e2e/` finds nothing new
- [ ] T064 Work through [quickstart.md](./quickstart.md) against the real thing — the checks only reality can make: a real order captured and reconciled line by line, a real bag scanned and received, a re-capture of an order that changed, and the bookmarklet clicked on a real HTTPS McMaster page against this app over plain HTTP (the cross-origin half no local test can reach). Record the results in `specs/028-mcmaster-order-capture/verification.md`, as `specs/023-restore-forwarded-port/` did
- [ ] T065 [P] Confirm `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing, and that `.env`, `credentials.json` and `token.json` are still untracked

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Gate)** — no dependencies. **Blocks Phases 3–6.** Nothing that reads McMaster's markup can start until the fixtures exist
- **Phase 2 (Foundational)** — no dependencies, and **independent of Phase 1**. Can be done first, or in parallel with saving the fixtures. Blocks all stories
- **Phase 3 (US1)** — depends on Phases 1 and 2
- **Phase 4 (US2)** — depends on Phases 1 and 2. **Parallel with Phase 3**
- **Phase 5 (US3)** — depends on **Phase 3**: there is no line to receive until an order has been captured
- **Phase 6 (US4)** — depends on Phase 3, for a review to state anything on
- **Phase 7 (Polish)** — depends on everything shipped

```
Phase 1 (fixtures) ──┬──▶ Phase 3 (US1) ──┬──▶ Phase 5 (US3) ──┐
                     │                    └──▶ Phase 6 (US4) ──┤
Phase 2 (foundation)─┴──▶ Phase 4 (US2) ───────────────────────┴──▶ Phase 7
```

### Within each story

- Tests before the implementation they cover
- Domain types (`app/models.py`) before services (`app/catalog_service.py`) before routes and templates
- The agent reader can be written in parallel with the server side — they meet only at the payload contract

### Parallel opportunities

- **T003 with T001/T002** — the product fixture is independent of the order fixture
- **All of Phase 2 with all of Phase 1** — the rename and the dispatch read no McMaster markup
- **T008, T012** within Phase 2
- **T014–T017** — four test files' worth of cases, no shared state
- **Phase 3 with Phase 4** — US1 and US2 touch different readers, different routes and different templates. Their only overlap is the Phase 2 dispatch, which is already done
- **T042–T044** within Phase 5
- **T059, T060, T062, T065** within Phase 7

---

## Parallel Example: Phase 1 and Phase 2 together

```bash
# One person saves and scrubs the fixtures (T001-T004).
# Meanwhile, the whole of Phase 2 proceeds — it reads no McMaster markup:
Task: "Alembic revision renaming purchases.digikey_line_number to order_line_number"
Task: "Rename the ORM column and the to_dict key in app/database.py"
Task: "Add the path-keyed page dispatch to app/static/js/capture-agent.js"
Task: "Add MCMASTER_VENDOR beside DIGIKEY_VENDOR in app/catalog_service.py"
```

## Parallel Example: User Story 1 tests

```bash
Task: "Payload parsing cases in tests/unit/test_mcmaster_payload.py"
Task: "Pack arithmetic cases in tests/unit/test_mcmaster_payload.py"
Task: "review_mcmaster_order state cases in tests/unit/test_mcmaster_capture.py"
Task: "capture_mcmaster_order write cases in tests/unit/test_mcmaster_capture.py"
```

---

## Implementation Strategy

### MVP: Phases 1 + 2 + 3

The whole of the issue's second half — capture a McMaster order — and the part the operator
cannot work around by hand. Stop here and validate: capture a real order, reconcile it line by
line, and check that abandoning a review leaves nothing behind.

### Incremental delivery

1. **Phases 1–2** → the schema is renamed, the agent knows what page it is on, nothing else changed
2. **+ Phase 3** → orders capture (**MVP** — ship it)
3. **+ Phase 4** → single parts capture; the bookmarklet stops being useless on a McMaster product page
4. **+ Phase 5** → the box can be unpacked by scanning
5. **+ Phase 6** → a markup change costs fields, not silence
6. **+ Phase 7** → documented, regressed, and verified against reality

### If the fixtures are slow to arrive

Phase 2 is the answer: it is real, shippable work — a reversible migration and a dispatch that
changes no behaviour — and none of it needs McMaster's markup. Do it first and the gate costs
nothing.

---

## Notes

- **Every nox invocation needs** `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`, and `e2e`
  must be run detached — it outlasts a ten-minute tool timeout
- **No new pytest markers**, so `pytest.ini` is untouched under `--strict-markers`
- **No fixed waits in e2e, ever.** Wait for state; the suite executes zero `wait_for_timeout` and
  must go on executing zero. `CLAUDE.md` is the normative source for finding the condition
- **Seed through `live_server.add_test_data`** unless the form is what is under test — driving
  the Add Item form costs about three seconds against milliseconds
- **`Decimal`, never `float`**, on every price, including in JSON transit (strings on the wire)
- The one cross-story dependency is US3 on US1. Everything else is independent
- Commit after each task or logical group
