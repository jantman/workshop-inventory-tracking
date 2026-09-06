---

description: "Task list for 039-typed-quantity-entry"
---

# Tasks: Type a tracked count instead of clicking to it

**Input**: Design documents from `/specs/039-typed-quantity-entry/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Required, not optional. Constitution IV: "Changes that alter behavior MUST land with
tests covering that behavior", and `nox -s tests` and `nox -s e2e` must both be green before merge.

**Organization**: Grouped by user story. US1 and US2 are both P1 and both deliver on their own once
Phase 2 is in place; US3 is P2 and depends on neither.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different file, no dependency on an incomplete task
- **[Story]**: US1, US2, US3 per [spec.md](./spec.md)

## Path Conventions

Server-rendered Flask app, existing layout. Application code in `app/`, tests in `tests/unit/` and
`tests/e2e/`. All paths below are repository-relative.

## The three files that change

| File | What happens to it |
|---|---|
| `app/templates/product/detail.html` | Three new elements inside `#stock-card`. No existing element removed, renamed or resized. |
| `app/static/js/product-stock.js` | One entry reader, one validator, one commit method on the existing `StockControls` class. |
| `app/product/routes.py` | One derived value in `product_detail`. `api_set_quantity` is **not** touched. |

`app/catalog_service.py`, `app/database.py` and `migrations/` are **not** modified. There is no
Alembic revision.

---

## Phase 1: Setup

**Purpose**: Establish the baseline so a later failure is attributable to this change.

- [ ] T001 Confirm a green baseline before touching anything: run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` from the repository root and record that it passes. Nothing to install and no project to initialize — this feature adds no dependency.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The typed input itself and the code that reads and judges it. Both P1 stories commit
through this, so it lands once and neither story duplicates it.

**⚠️ Blocks US1 and US2. US3 does not depend on it.**

- [ ] T002 Add `#quantity-input` to the Stock card in `app/templates/product/detail.html`, immediately below the existing `.btn-group` holding `#quantity-decrement` and `#quantity-increment`. Numeric entry with `min="0"`, `step="1"`, `inputmode="numeric"`, Bootstrap `form-control form-control-lg`. Pre-filled with `product.quantity` when `product.quantity is not none`; empty with a "Starting count" placeholder and label when it is none. Do not remove, reorder, resize or rename any existing element in the card — see `contracts/stock-card-ui.md` for the ids the E2E suite binds to. Add a comment saying why the steppers stay: they are the right control for "I just used one" and the only one that works with no keyboard.

- [ ] T003 Add an entry reader and validator to the `StockControls` class in `app/static/js/product-stock.js`. A method that reads `#quantity-input`, trims it, and returns either the integer or a refusal reason: empty, not a whole number, or negative — in that order, per `contracts/quantity-commit.md`. It must **never** produce an empty string as a value to send: `CatalogService._validate_quantity` maps `''` to `None`, which means "stop counting" (`research.md` §2). Leave `currentQuantity()` exactly as it is; it parses `#quantity-value` for the steppers and must keep its fallback to `0` when that text is a badge rather than a number.

**Checkpoint**: The field renders on both a tracked and an untracked product, and nothing on the card behaves differently yet.

---

## Phase 3: User Story 1 — Record a count that was just taken (Priority: P1) 🎯 MVP

**Goal**: On a product already being counted, type an exact number and commit it in one action.

**Independent test**: On a product tracked at 3, type 40, press Set, and both the displayed count
and its age update. This alone closes the reported defect.

### Implementation

- [ ] T004 [US1] Add `#quantity-set-btn` to `app/templates/product/detail.html`, adjacent to `#quantity-input` and rendered **only** when `product.quantity is not none`. Label it "Set". Size it like the rest of the card's controls so it clears 44px on a touch viewport (`btn-lg`). It is absent, not disabled, on an untracked product — `#start-tracking-btn` is the commit control there, and two commit buttons in one state would be ambiguous (FR-011).

- [ ] T005 [US1] Wire `#quantity-set-btn` in `app/static/js/product-stock.js`: read the entry with the T003 validator; on a refusal call the existing `showAlert()` and send nothing; on success `PATCH` `{quantity: <int>}` through the existing `setQuantity()`. Commit an unchanged value too — re-entering the same count is the operator saying they have just looked again, and it must re-stamp the date (FR-003). Do not reload on a refusal, so the displayed count and the operator's correction both survive (FR-008).

### Tests

- [ ] T006 [P] [US1] Create `tests/unit/test_typed_quantity.py` and cover the endpoint path this story sends: `PATCH /api/products/<id>/quantity` with `{"quantity": 40}` on a product at 3 sets it to 40 and stamps `quantity_updated_at`; `{"quantity": 0}` leaves the product counted rather than untracked; `{"quantity": null}` is the only thing that stops counting (FR-005); a negative and a non-numeric value each return 400 with the count unchanged. Build fixtures through `tests/conftest.py` (`test_storage` → `app` → `client`), per Constitution IV.

- [ ] T007 [P] [US1] Create `tests/e2e/test_typed_quantity.py` with the US1 cases: seed a product counted at 3 via `live_server.add_test_data`, fill `#quantity-input` with 40, click `#quantity-set-btn`, and `expect(page.locator("#quantity-value")).to_contain_text("40")` — the page reloads on success, so the rendered value is the completion signal and cannot predate the request (`CLAUDE.md` pattern C). Add: committing an unchanged value leaves `#quantity-age` reading as freshly counted; the `−` button still reads one lower afterwards. **No `wait_for_timeout`, no `time.sleep`, no `networkidle`.**

- [ ] T008 [US1] Add the refusal cases to `tests/e2e/test_typed_quantity.py`: clear `#quantity-input`, click `#quantity-set-btn`, and `expect(page.locator("#stock-alert")).to_be_visible()` while `#quantity-value` still reads the original count. The refusal does not reload, so the alert is the only signal — do not wait on anything else. Then type a valid number into the same still-loaded page and confirm it commits (FR-008). Add a negative entry and a non-numeric entry as further refusals.

**Checkpoint**: The reported defect is fixed. Forty is one entry and one press.

---

## Phase 4: User Story 2 — Start counting at the number it is actually at (Priority: P1)

**Goal**: Beginning a count starts it at a stated number instead of always at zero.

**Independent test**: On an untracked product, enter 12, begin counting, and it is tracked at 12.

**Depends on**: Phase 2 only. Independent of US1 — the two stories touch different buttons.

### Implementation

- [ ] T009 [US2] In `app/static/js/product-stock.js`, change the `#start-tracking-btn` handler to read `#quantity-input` through the T003 validator instead of sending a hardcoded `0`. **An empty field here is not a refusal** — it sends `{quantity: 0}`, exactly as today (FR-004), because the button the operator pressed says "Start counting this" and an untouched field is the absence of an entry rather than an entry of nothing. A non-empty but invalid entry (negative, fractional, non-numeric) is still refused through `showAlert()`. Keep the `#stop-tracking-btn` handler untouched: it still sends an explicit `null`.

### Tests

- [ ] T010 [US2] Add the US2 cases to `tests/e2e/test_typed_quantity.py`: on an untracked product, fill `#quantity-input` with 12, click `#start-tracking-btn`, and `expect(page.locator("#quantity-value")).to_contain_text("12")`. Then, on a second untracked product, click `#start-tracking-btn` with the field untouched and expect the "None on hand" badge — the existing behavior, re-asserted because the field now sits next to that button. Add: an invalid non-empty starting entry raises `#stock-alert` and leaves the product untracked.

- [ ] T011 [US2] Verify the three existing E2E tests that press `#start-tracking-btn` still pass unmodified: `tests/e2e/test_touch_readiness.py::test_quantity_is_adjustable_by_tapping`, `test_the_stock_controls_are_large_enough_to_hit`, and `tests/e2e/test_reorder_view.py` (line ~193). If any needs changing, the change to `#start-tracking-btn` went too far — the button's untouched-field behavior is supposed to be identical.

**Checkpoint**: Both P1 stories are delivered. Every count state is reachable in one action.

---

## Phase 5: User Story 3 — Be told what was already received (Priority: P2)

**Goal**: An untracked product that has had stock received into it says how much, where the
starting count is entered.

**Independent test**: Receive a purchase into an untracked product; the product page states the
received total. Depends on neither P1 story.

### Implementation

- [ ] T012 [P] [US3] In `product_detail` in `app/product/routes.py`, add `received_total` to the `render_template` context: the sum of `purchase.quantity` over `purchases` where `not purchase.is_outstanding` and `purchase.quantity` is truthy. Put it directly beside the existing `outstanding=[p for p in purchases if p.is_outstanding]` line — it is arithmetic over the list `get_purchase_history` already returned, not a new query, so Constitution II's "no ORM queries in routes" is not engaged. Do not add a service method for it (`research.md` §5).

- [ ] T013 [US3] Render `#received-total` in `app/templates/product/detail.html`, beside `#quantity-input`, **only** when `product.quantity is none` and `received_total > 0`. Plain text stating the received total — not a link, not a button, and nothing that fills the input. Suppressed on a counted product because receiving already adds to that count and restating it invites double-counting (FR-013). No "0 received" rendering exists (FR-014). Comment the suppression rule at the call site; it is the non-obvious half.

### Tests

- [ ] T014 [P] [US3] Add the `received_total` cases to `tests/unit/test_typed_quantity.py`: two received purchases of 60 and 40 give 100; one received and one outstanding counts only the received one; a received purchase with a `NULL` quantity contributes nothing and does not suppress the others; no purchases gives 0. Then assert what is rendered from `client.get(f'/products/{product.id}')`: the received line is present on an untracked product with a non-zero total, and absent when the total is zero, when there are no received purchases, and when the product is being counted.

- [ ] T015 [US3] Add the US3 case to `tests/e2e/test_typed_quantity.py`: seed an untracked product with a received purchase of 100, and `expect(page.locator("#received-total")).to_contain_text("100")`. Then confirm it is advisory — pressing `#start-tracking-btn` with the field untouched still yields "None on hand", not 100. For the absent case on a counted product, **first** establish the card with `expect(page.locator("#quantity-value")).to_contain_text(...)` and only then assert `#received-total` has count 0; a bare negative assertion passes against a page that has not rendered.

**Checkpoint**: All three stories delivered.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T016 Add `#quantity-set-btn` to the selector list in `tests/e2e/test_touch_readiness.py::test_the_stock_controls_are_large_enough_to_hit`. Extend the existing list rather than writing a new test — the 44px floor is one rule and it belongs in one place.

- [ ] T017 Run the unit suite: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`. Must pass.

- [ ] T018 Run the E2E suite detached and poll — it takes roughly 14 minutes and outlasts a 10-minute tool cap: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" nohup venv/bin/nox -s e2e > /tmp/e2e-039.log 2>&1 &`. Must pass. A failure in `test_touch_readiness.py` or `test_reorder_view.py` means the typed entry displaced something it should not have.

- [ ] T019 Grep the new E2E file for prohibited waits and fix any hit: `grep -n "wait_for_timeout\|time.sleep\|networkidle" tests/e2e/test_typed_quantity.py` must return nothing. Constitution IV admits one exception — a condition that genuinely cannot be observed, justified in writing at the call site — and this feature has none: every action here either reloads the page or writes `#stock-alert`.

- [ ] T020 Regenerate documentation screenshots, which `app/templates/**` and `app/static/js/**` changes require: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless`, then `venv/bin/nox -s screenshots_verify`. Inspect `git status --short docs/images/screenshots/` and commit **only** screenshots whose content actually changed — the output churns byte-for-byte between runs regardless of content, and `tests/e2e/screenshot_config.yaml` has no product-detail entry, so no content change is expected. Confirm the working tree is otherwise clean: a test run must not modify tracked files.

- [ ] T021 Walk `quickstart.md`'s nine by-hand steps against a running app (`venv/bin/python -m flask --app app run`), including the handheld check in a browser's device emulation. This is what catches a control that passes its test and is still wrong to use.

- [ ] T022 Check spelling per `CLAUDE.md`: `grep -ric "catalogue" README.md docs/ app/ tests/` must return nothing.

---

## Dependencies & Execution Order

```text
Phase 1 (T001)
   │
Phase 2 (T002, T003)  ── blocks US1 and US2, not US3
   │
   ├─── Phase 3: US1 (T004 → T005 → T006, T007, T008)   ← MVP
   │
   ├─── Phase 4: US2 (T009 → T010, T011)
   │
Phase 5: US3 (T012 → T013 → T014, T015)   ── independent of Phases 2–4
   │
Phase 6: Polish (T016 → T017 → T018 → T019 → T020 → T021 → T022)
```

**Story independence**:

- **US1** and **US2** share Phase 2 and then diverge — US1 adds a button, US2 rewires an existing
  one. Either can be finished and shipped without the other.
- **US3** touches `app/product/routes.py` and a different template region. It shares no code with
  US1 or US2 and can be built first, last, or not at all.

**Within-file serialization**: T002/T004/T013 all edit `app/templates/product/detail.html`, and
T003/T005/T009 all edit `app/static/js/product-stock.js`. Tasks touching the same file run in
sequence even where their stories are independent, which is why only T006, T007, T012 and T014
carry `[P]`.

## Parallel Opportunities

- **T006 and T007** — the unit file and the E2E file are different files with no dependency on each
  other once T005 lands.
- **T012 and T014** — the route change and its unit test, and neither touches the template.
- **Phase 5 alongside Phases 3–4** — US3's only application file is `app/product/routes.py` plus a
  template region the other stories do not occupy. If T013 is sequenced after T004 to avoid an edit
  collision in `detail.html`, the rest of US3 is fully parallel.

## Implementation Strategy

**MVP is Phase 1 + Phase 2 + Phase 3 (T001–T008).** That is the reported defect fixed: a counted
quantity of any size becomes one entry and one press. Everything after it is worth having and none
of it is what issue #139 is about.

**Then Phase 4**, which is small — one handler reads a field instead of a constant — and closes the
"receive 100, then start counting" path the issue calls the more likely way to meet the problem.

**Then Phase 5**, which is the answer to the issue's open question, deliberately scoped down: the
received total is *stated*, never pre-filled. A years-old total committed unread would write a
count nobody verified, which is a worse outcome than the clicking (`research.md` §6).

**Phase 6 is not optional.** The screenshot regeneration and the full E2E run are merge gates under
the constitution, and T011 and T016 are what prove the typed entry did not cost the card its
touch behavior.
