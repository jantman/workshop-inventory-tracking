---
description: "Task list for 031-order-backfill"
---

# Tasks: Backfilling Past Orders

**Input**: Design documents from `/specs/031-order-backfill/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: **Included, and not optional here.** Constitution IV requires that changes altering
behavior land with tests covering that behavior, and `nox -s tests` / `nox -s e2e` must pass before
merge. Two of this feature's requirements — FR-028 and FR-030 — are true *by construction* rather
than by any statement in the code, so their tests are the only thing that will keep them true.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story the task serves (US1, US2, US3)
- Every task names the exact file it touches

## Path Conventions

Server-rendered Flask application plus a `click` management CLI; existing layout kept exactly
(plan.md → Structure Decision): `app/` for source, `manage.py` for the CLI, `docs/` for the manual,
`tests/unit/` and `tests/e2e/` for tests. **No new directory.**

## A note on story-to-phase mapping

**The phases are not in story-priority order, and US1 spans two of them.** The plan says why: the
story priorities order by *value*, the phases order by *dependency and risk*.

- **US3 (P3) is Phase 2**, first, because it touches the one flow all three vendors confirm
  through and therefore carries the only real regression risk in the feature.
- **US1 (P1) is Phases 4 and 5.** Its enumeration half — the DigiKey listing — is Phase 4. Its
  procedure half — the documentation — is Phase 5 and lands **last**, because it describes the
  other three slices and cannot be written honestly before they exist. This is the one place the
  stories are genuinely not independent.

**Phase 1 is a gate, not setup.** It decides whether Phase 4 exists at all.

---

## Phase 1: Gate — does DigiKey's order listing work on the token we hold?

**Purpose**: research.md §5 is the feature's only unverified premise. The path
`GET /orderstatus/v4/orders` is established from DigiKey's own changelog, but the query parameter
names, the response field names, and — the thing that matters — **whether a 2-legged token may list
a whole account's orders at all** are not.

**This phase blocks Phase 4 only.** Phases 2 and 3 do not depend on it and should proceed
concurrently.

- [X] T001 Make one live call to `GET https://api.digikey.com/orderstatus/v4/orders` using the configured `DIGIKEY_CLIENT_ID` / `DIGIKEY_CLIENT_SECRET` / `DIGIKEY_ACCOUNT_ID`, and record in `specs/031-order-backfill/verification.md`: the exact date-range and paging parameter names, the per-order response field names, whether the 2-legged token is accepted, and how far back the listing reaches
- [X] T002 Record the consequence in `specs/031-order-backfill/research.md` §5 — either the confirmed parameter names that Phase 4 is written against, or the decision to drop FR-018 through FR-022 to the documented browser fallback

**If the call is refused on a 2-legged token**: Phase 4 does not happen. FR-018–FR-022 are dropped,
the operator reads sales order numbers off DigiKey's own order-history page, and T034 in Phase 5
documents that instead. **Do not build a 3-legged OAuth flow** — it means a browser redirect, an
HTTPS callback and a refresh token on disk, which is a login system for an application whose
constitution says it has none (research.md §5).

**Checkpoint**: Phase 4's scope is known.

---

## Phase 2: User Story 3 — arrival at capture (Priority: P3) 🎯 first by dependency

**Goal**: A review can say *this order has already arrived*, and confirming it records the kept
lines delivered rather than outstanding — so a backfill leaves the captured-orders list and the
reorder list still telling the truth about what is on its way.

**Independent Test**: Capture an order dated in the past with the arrival box ticked; every kept
line is delivered with the date given, the order reads complete on `Products → Captured Orders`,
and no product of it is marked *on the way* on the reorder list.

**Contract**: [contracts/arrival-at-capture.md](./contracts/arrival-at-capture.md)

### Implementation

- [X] T003 [US3] Add `arrived_date=None` to `CatalogService.capture_order_lines` and replace the hard-coded `received_date=None` in its `Purchase(...)` call with the line's arrival decision, in `app/catalog_service.py`
- [X] T004 [US3] Parse and validate the arrival date **before the session opens** — `_parse_datetime`, then `_validate_receipt_order(order.order_date, arrived)`, with a blank date falling back to `order.order_date` and never to `datetime.now()` — in `app/catalog_service.py`
- [X] T005 [P] [US3] Add `lines_arrived: int = 0` to `OrderCaptureResult` in `app/models.py`, and populate it in `capture_order_lines`
- [X] T006 [US3] Add `'arrived': form.get(f'arrived[{key}]') is not None` to `_order_decisions` in `app/product/routes.py`
- [X] T007 [US3] Pass `arrived_date=request.form.get('arrived_date')` to the service from both confirm sites — `digikey_order_confirm` and `_confirm_page_order` — in `app/product/routes.py`
- [X] T008 [US3] Add the arrived-line count to `_order_capture_summary` in `app/product/routes.py`, per that function's own rule that every outcome which changed the database appears there
- [X] T009 [US3] Add the order-level *This order has already arrived* checkbox, the `arrived_date` input, and the per-line `arrived[{form_key}]` checkboxes to `app/templates/product/order_review.html`, reading all of them back out of `form_data` so a refusal does not untick what the operator set
- [X] T010 [US3] State on the review what confirming will do — that these lines will be recorded delivered, and that a counted product's on-hand quantity will **not** move — in `app/templates/product/order_review.html`

### Tests

All in one new file, so none of these run in parallel with each other.

- [X] T011 [US3] Test that a ticked line records the given date, in `tests/unit/test_order_backfill.py`
- [X] T012 [US3] Test that a blank date falls back to the order's own date and is never today's, in `tests/unit/test_order_backfill.py`
- [X] T013 [US3] Test that an arrival date earlier than the order date is refused with **no product and no purchase written**, in `tests/unit/test_order_backfill.py`
- [X] T014 [US3] Test that a line held back from the arrival mark stays outstanding while the rest are delivered, in `tests/unit/test_order_backfill.py`
- [X] T015 [US3] **Test FR-028**: a matched product whose stock is counted and whose manual Low flag is set has its quantity, its `quantity_updated_at`, its `stock_status` and that flag's age **all unchanged** after an arrived capture, in `tests/unit/test_order_backfill.py`
- [X] T016 [US3] **Test FR-030**: re-capturing an order whose lines are already delivered leaves their received dates untouched and receives nothing twice, in `tests/unit/test_order_backfill.py`
- [X] T017 [US3] Test FR-027 as an assertion rather than an assumption: `find_captured_orders` reports the order complete and `get_reorder_products` does not mark its products on the way, in `tests/unit/test_order_backfill.py`
- [X] T018 [US3] Test that an **unticked** review records outstanding purchases exactly as before, in `tests/unit/test_order_backfill.py`
- [X] T019 [US3] E2E: capture an order with the arrival box ticked and assert against the order screen and the captured-orders list, in `tests/e2e/test_order_backfill.py` — waiting on the landed page after the confirm POST (pattern C) and establishing the orders table with `expect(...)` before any negative assertion about outstanding lines

### Gate

- [X] T020 [US3] Run `venv/bin/nox -s tests` and confirm `tests/unit/test_digikey_capture.py`, `tests/unit/test_mcmaster_capture.py` and `tests/unit/test_amazon_capture.py` pass **unedited** — a present-day capture must be the capture that shipped in feature 029

**Checkpoint**: US3 is independently deliverable. A backfill is now safe to run even though nothing
has been made easier yet.

---

## Phase 3: User Story 2 — the Amazon reduction command (Priority: P2)

**Goal**: An edited Amazon order-history export becomes the distinct order addresses it names, each
one once, without opening a single order page to find out.

**Independent Test**: Run the command over an export where one order contributed eleven item rows;
that order is emitted exactly once, as an address that opens a real order page.

**Contract**: [contracts/amazon-export-command.md](./contracts/amazon-export-command.md)

**Fully independent of every other phase** — nothing it does can affect the running application.

### Implementation

- [X] T021 [P] [US2] Create `app/services/amazon_order_export.py` with `AmazonExportOrder`, `AmazonExportSummary` and a pure `summarize(rows)` over what `csv.DictReader` yields — no Flask, no ORM, no network, `csv` from the standard library only
- [X] T022 [US2] Implement the rules in `app/services/amazon_order_export.py`: require only `Order ID` and `Website`; de-duplicate in first-seen order; emit only ids matching `\d{3}-\d{7}-\d{7}`; build `https://{website}/gp/css/order-details?orderID={id}` from each row's own `Website`; count rows read, unusable ids, and orders carrying an unusual `Order Status` **without filtering any of them**
- [X] T023 [US2] Refuse an unrecognized file by naming the missing column and listing the columns found, emitting no addresses, in `app/services/amazon_order_export.py`
- [X] T024 [P] [US2] Add an `orders` group with an `amazon-urls <path>` command to `manage.py` — open the file, call `summarize`, print addresses to stdout and the summary to stderr, exit non-zero on refusal; the callback stays thin, with no logic of its own

### Tests

- [X] T025 [US2] Test that eleven rows naming one order yield that order once, and the summary reports rows read and distinct orders, in `tests/unit/test_amazon_order_export.py`
- [X] T026 [US2] Test that a missing `Order ID` column is refused by name with the found columns listed and no addresses produced, in `tests/unit/test_amazon_order_export.py`
- [X] T027 [US2] Test that a row whose `Website` is `www.amazon.co.uk` yields an address against that host, in `tests/unit/test_amazon_order_export.py`
- [X] T028 [US2] Test that a `D01-` digital order id is not emitted and is counted as unusable, in `tests/unit/test_amazon_order_export.py`
- [X] T029 [US2] Test that an unusual `Order Status` is counted and reported but **never dropped**, in `tests/unit/test_amazon_order_export.py`

### Verification

- [ ] T030 [US2] Paste one emitted address into the browser, land on the order, click the capture bookmarklet, and confirm the existing Amazon order review appears — proving FR-015 and that the legacy `/gp/css/` path still redirects to the one the capture agent runs on. **Needs a signed-in Amazon session, so it is the operator's to do.** The machine-checkable half is covered: `test_the_address_carries_an_id_the_capture_agent_recognizes` asserts an emitted address against the agent's own `AMAZON_ORDER_ID_PATTERN`

**Checkpoint**: US2 is independently deliverable.

---

## Phase 4: User Story 1a — the DigiKey order listing (Priority: P1)

**Goal**: Backfilling DigiKey needs no sales order number read off DigiKey's website and typed back
in.

**Independent Test**: Open `Products → Capture a DigiKey Order`; past orders are listed with their
numbers and dates, and clicking one reaches the review that already exists.

**Contract**: [contracts/digikey-order-listing.md](./contracts/digikey-order-listing.md)

**⚠️ Gated by Phase 1.** If T001 found the endpoint unreachable on a 2-legged token, **skip this
entire phase** and go to Phase 5.

### Implementation

- [X] T031 [P] [US1] Add a frozen `DigiKeyOrderSummary` dataclass with a `from_payload` classmethod that returns `None` for an entry it cannot parse, in `app/models.py`, against the field names recorded in `verification.md`
- [X] T032 [US1] Add `DigiKeyClient.list_orders(days=365)` calling `GET /orderstatus/v4/orders` through the existing `_get`, in `app/services/digikey.py` — one page, no retries, no cache, and **no `.json()`**, so `Decimal` survives per that module's own docstring
- [X] T033 [US1] Render the listing above the existing form on `GET /products/digikey/orders` in `app/product/routes.py`, catching a `WorkshopInventoryError` from `list_orders` into a message that leaves the capture-by-number form working
- [X] T034 [US1] Add the recent-orders table to `app/templates/product/digikey_order_entry.html` — sales order number, date, DigiKey's reference, status — each row a submit posting `sales_order_number` to the same route, with a plain "no orders" line when the listing is empty

### Tests

- [X] T035 [US1] Test `list_orders` against a mocked response in `tests/unit/test_digikey_client.py`: the path called, `Decimal` in the parsed result, an unparseable entry skipped rather than losing the listing, and each error mapped the way `get_order`'s are
- [X] T036 [US1] Test the route's three states — listed, not configured, listing failed — and that the sales-order-number form is present and functional in all three, in `tests/unit/test_digikey_failures.py`
- [X] T037 [US1] E2E: the listing renders against the loopback DigiKey fake and a row click reaches the review, in `tests/e2e/test_digikey_order.py`

**Checkpoint**: US1's enumeration half is deliverable.

---

## Phase 5: User Story 1b — the documented procedure (Priority: P1)

**Goal**: A written, followable backfill procedure covering all three vendors, discoverable from
the user manual.

**Independent Test**: Someone who has never backfilled reads the chapter cold and can complete a
backfill of one vendor without asking a question the chapter does not answer.

**⚠️ Depends on Phases 2, 3 and 4.** This chapter describes them; it cannot be written honestly
before they exist.

- [X] T038 [US1] Add a **Backfilling Past Orders** chapter to `docs/user-manual.md`, after the three vendor chapters and before *Printing Product Labels*, with its table-of-contents entry
- [X] T039 [US1] Document the Amazon path in that chapter (FR-009, FR-010): requesting the data export, roughly how long Amazon takes, which file to use, editing it down, and running `python manage.py orders amazon-urls`
- [X] T040 [US1] Document the McMaster path in that chapter (FR-023): enumerating Order History in the browser and clicking the bookmarklet on each order's own page
- [X] T041 [US1] Document the DigiKey path in that chapter (FR-018–FR-022) — the order listing on the capture screen — **or**, if Phase 4 was skipped, reading sales order numbers off DigiKey's order-history page and typing them into the screen that already exists
- [X] T042 [US1] Document arrival in that chapter (FR-024–FR-028): the *already arrived* mark, that the date defaults to the order's own, holding a line back, and that a counted product's quantity deliberately does not move
- [X] T043 [US1] State per vendor how far back its order history reaches and what to do about anything older (FR-004), in `docs/user-manual.md`
- [X] T044 [US1] State per vendor what a backfilled record does and does not contain — in particular that an Amazon order capture yields title, quantity and price but no images, specifications or barcodes — and how to fill one in later by capturing its listing page (FR-008), in `docs/user-manual.md`
- [X] T045 [US1] State that a backfill is interruptible and resumable because a re-capture records nothing new, and that meeting an already-captured order partway through is expected rather than a fault (FR-005), in `docs/user-manual.md`
- [X] T046 [US1] Describe how the Amazon and McMaster page-opening steps can be driven mechanically rather than by hand (FR-007), noting that the application itself does not drive a browser, in `docs/user-manual.md`
- [X] T047 [P] [US1] Add a one-line cross-reference to the new chapter from each of the *Amazon Orders*, *DigiKey Orders* and *McMaster-Carr Orders* sections of `docs/user-manual.md`

**Checkpoint**: US1 is complete and the feature is whole.

---

## Phase 6: Polish & the merge gate

- [X] T048 [P] Confirm `grep -ric "catalogue" README.md docs/ app/ tests/` returns nothing and `grep -rn "catalogd\|catalogng\|uncatalogd" app/ tests/` returns nothing
- [X] T049 [P] Run `venv/bin/nox -s lint`
- [X] T050 Run `venv/bin/nox -s tests`
- [X] T051 Run `nohup venv/bin/nox -s e2e > /tmp/e2e.log 2>&1 &` detached and poll — the suite takes about 14 minutes warm and will not fit inside a 10-minute tool timeout. **732 passed in 15m27s**, cold; a targeted re-run of the seven order-review files after a late template change passed 104
- [X] T052 Confirm `git status --porcelain` is empty after the test runs — a test session must leave the working tree clean
- [X] T053 Walk `specs/031-order-backfill/spec.md` FR-001 through FR-031 and confirm each is either implemented, tested, documented, or recorded as dropped with its reason in `research.md` §5

---

## Requirement coverage (T053)

Walked 2026-08-28. FR-001 through FR-031 of [spec.md](./spec.md):

| Requirements | Where they landed |
|---|---|
| FR-001 – FR-008 (the procedure) | `docs/user-manual.md` → **Backfilling Past Orders**, with a table-of-contents entry and a cross-reference from each of the three vendor chapters. Per-vendor *How far back* and *What you get* answer FR-004 and FR-008; *Doing the opening for you* answers FR-006 and FR-007 |
| FR-009 – FR-016 (Amazon selection) | `app/services/amazon_order_export.py` and `manage.py orders amazon-urls`, documented in the chapter's Amazon section; 28 cases in `tests/unit/test_amazon_order_export.py` |
| FR-017 (per-line exclusion) | Unchanged — the existing `include[...]` control, deliberately not touched |
| FR-018 – FR-022 (DigiKey listing) | `DigiKeyClient.list_orders`, `DigiKeyOrderSummary`, the entry screen and its template; `tests/unit/test_digikey_client.py::TestListingTheAccountsOrders`, `tests/unit/test_digikey_failures.py::TestTheOrderListing`, `tests/e2e/test_digikey_order.py` |
| FR-023 (McMaster enumeration) | Documentation only, as specified — no McMaster connection introduced |
| FR-024 – FR-031 (arrival) | `capture_order_lines`, `_resolve_arrival_date`, `_order_decisions`, `order_review.html`; 19 cases in `tests/unit/test_order_backfill.py` and 5 in `tests/e2e/test_order_backfill.py` |

**One item is not closed by this session: T030.** Its machine-checkable half is —
`test_the_address_carries_an_id_the_capture_agent_recognizes` asserts an emitted address against
the capture agent's own `AMAZON_ORDER_ID_PATTERN`, so a dead link would fail the suite. Its other
half is opening one of those addresses in a signed-in Amazon session and clicking the bookmarklet,
which needs the operator's own browser and account. It is left unticked rather than claimed.

---

## Dependencies

```text
Phase 1 (gate) ─────────────────────────► Phase 4 (US1a, DigiKey listing) ─┐
                                                                            │
Phase 2 (US3, arrival) ────────────────────────────────────────────────────┤
                                                                            ├──► Phase 5 (US1b, docs) ──► Phase 6
Phase 3 (US2, Amazon command) ─────────────────────────────────────────────┘
```

- **Phases 1, 2 and 3 have no dependency on each other** and can run concurrently.
- **Phase 4 needs Phase 1** and nothing else.
- **Phase 5 needs 2, 3 and 4**, because it documents them. This is the only cross-story dependency
  in the feature.
- **Phase 6 needs everything.**

### Within a phase

- Phase 2: T003 → T004 (same function). T005, T006 are independent of those. T007 follows T006
  (same file, and it is the caller). T009 → T010 (same template). Tests T011–T018 all share one new
  file and are sequential with each other; T019 is a different file.
- Phase 3: T021 → T022 → T023 (one file, built up). T024 needs T021's names. Tests T025–T029 share
  one file.
- Phase 4: T031 → T032 (the client returns the model) → T033 → T034.

## Parallel opportunities

- **Across phases**: Phases 1, 2 and 3 are three independent tracks. Phase 3 in particular touches
  no file any other phase touches.
- **T005 ∥ T006**: `app/models.py` and `app/product/routes.py`.
- **T021 ∥ T024**: the module and the CLI entry point, once the names are agreed.
- **T031 ∥ anything in Phase 2 or 3**: different files entirely.
- **T047 ∥ T048/T049**: the cross-references touch prose the checks only read.

Everything else in a given phase shares a file with its neighbour, which is why `[P]` is sparse
here. That is honest rather than pessimistic — five tasks marked parallel that all edit
`app/catalog_service.py` would be a lie about what can actually run at once.

## Implementation strategy

**The minimum safe increment is Phase 2 + Phase 5, not Phase 5 alone.** Documentation on its own
would be a real deliverable — a McMaster backfill needs no new code at all — but it would send the
operator into a procedure that leaves several hundred lines claiming to be in transit on the two
screens that exist to answer *what is still coming*. The spec's own words: it ships with this
feature or the feature makes the catalog less trustworthy than it was before.

**Suggested delivery order**:

1. **Phase 1** immediately, in parallel with everything, because it is the only thing that can
   change the shape of the work and it costs one HTTP call.
2. **Phase 2**, alone and carefully. It is the only slice that touches shared behaviour, and T020
   is its gate.
3. **Phase 3** whenever convenient — it is isolated enough to be picked up and put down.
4. **Phase 4** once Phase 1 has reported, or skipped entirely if it reported badly.
5. **Phase 5**, last, describing what actually got built rather than what was planned.

**Two things to watch while implementing**:

- **T015 is the test that matters most.** FR-028 is satisfied by construction — a purchase created
  with `received_date` already set never passes through `receive_purchase`, so no count moves and
  no flag clears. Nothing in the code *says* that. If a later change routes arrival through
  `receive_purchase` for convenience, T015 is the only thing that will notice.
- **T020 is not a formality.** Feature 029 consolidated three captures into one flow, and two
  defects in its review were behaviours one copy had that another had lost. The three capture
  suites passing unedited is what says this feature did not do the same thing again.
