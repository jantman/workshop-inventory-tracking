# Tasks: An Explicit "I Counted the Shelf" at Receipt

**Feature**: `specs/041-counted-at-receipt` | **Branch**: `robot-army/issue-149-explicit-i-counted-the-shelf-option`

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/receive-purchase.md](./contracts/receive-purchase.md), [quickstart.md](./quickstart.md)

**Tests**: Included, and not optional here. Constitution IV requires that "changes that alter
behavior MUST land with tests covering that behavior", and this feature's whole risk is that the
*unticked* path silently stops matching feature 008. That path is guarded by leaving roughly two
dozen existing `receive_purchase` call sites untouched (they pass no `counted`), plus the
explicit assertions below.

## Format

`- [ ] [ID] [P?] [Story?] Description with file path`

`[P]` marks tasks that touch different files and depend on nothing incomplete.

---

## Phase 1: Setup

Nothing to set up. No new dependency, no new directory, no migration, no new pytest marker. The
feature branch already exists and the work happens on it.

- [X] T001 Confirm the working tree is clean and on `robot-army/issue-149-explicit-i-counted-the-shelf-option`, and that `venv/bin/nox -s tests` is green before any change, so a later failure is attributable

---

## Phase 2: Foundational (blocking prerequisites)

The service rule is the one thing every user story depends on: the route has nothing to pass
until the parameter exists, and the template has nothing worth showing until the parameter does
something. Everything in Phase 2 must land before Phase 3.

- [X] T002 Add `counted: bool = False` as the last keyword parameter of `CatalogService.receive_purchase` in `app/catalog_service.py` (~line 1571), with a type hint and a `Args:` entry saying it is the operator asserting they counted what is on the shelf — an act, not a number
- [X] T003 In `CatalogService.receive_purchase` in `app/catalog_service.py`, add the conditional write `product.quantity_updated_at = utc_now()` when `counted` is true and `product.quantity is not None`. Place it **outside** the `if product is not None and not already_received:` block, next to the description amendment, and extend the existing comment there so it names both reasons a write lives outside the guard. Do **not** guard it on `purchase.quantity`
- [X] T004 Amend the existing comment inside the `not already_received` block in `app/catalog_service.py` — the one reading "The count's age is deliberately *not* touched (008 FR-008)" — so it states the rule and its one named exception (041 FR-003/FR-004) rather than an absolute that the code a few lines below now contradicts
- [X] T005 [P] Narrow the warning in the `Product.quantity_age` docstring in `app/database.py` (~line 951). It currently says "Do not restore a timestamp write to `receive_purchase`"; after T003 there is one. Make it forbid the *unconditional* write that feature 008 removed, and point at the operator's explicit assertion as the one write that is legitimate

**Checkpoint**: `venv/bin/nox -s tests` still green — every existing caller passes no `counted`, so nothing should have moved.

---

## Phase 3: User Story 1 — Receiving a box and checking the drawer at the same time (P1)

**Goal**: The operator can tick a box on the receive screen and have the count's age record that
they counted.

**Independent test**: Seed a product with a tracked count whose age is months old, receive an
outstanding purchase against it with the control ticked, and verify the count rose by the
received quantity *and* the displayed age reset to just now.

- [X] T006 [US1] In `app/product/routes.py`, `product.purchase_receive` (~line 957): read `counted=request.form.get('counted') == 'on'` and pass it to `service.receive_purchase(...)`, matching the `identifier_override` parse already in this file (~line 226)
- [X] T007 [US1] In `app/templates/product/receive.html`, add a Bootstrap `form-check` with `id="counted" name="counted"` inside the "What actually arrived" card, below the Notes field. Wrap it in `{% if product.quantity is not none %}`. Label it as the operator's claim — that they counted what is on the shelf — with a `form-text` line saying that leaving it alone still adds what arrived to the count and leaves the counted date where it is
- [X] T008 [P] [US1] Add unit tests to `tests/unit/test_stock_status.py` for contract tests C1, C4 and C6 of [contracts/receive-purchase.md](./contracts/receive-purchase.md): ticked against a tracked count moves both the count and the age; ticked against a purchase with no quantity moves the age and not the count; ticked against a tracked count of zero moves both
- [X] T009 [P] [US1] Add an E2E test to `tests/e2e/test_stock_age.py`, beside `test_receiving_does_not_reset_a_counted_age`, that seeds a tracked count backdated 100 days via `live_server.backdate_product`, opens the receive screen, checks `#counted`, submits, and asserts `#quantity-value` contains the increased count and `#quantity-age` reads "just now". Wait with `expect()` only — the increased count is the signal the round trip landed, exactly as the neighbouring test uses it

**Checkpoint**: Story 1 is independently demonstrable — tick the box, the age moves.

---

## Phase 4: User Story 2 — The default is still the honest one (P1)

**Goal**: Prove the unticked path is bit-for-bit what feature 008 shipped, and that the tick is
never sticky and never survives into a write that was refused.

**Independent test**: Run feature 008's receive behaviour end to end without touching the
control and verify every outcome is unchanged.

- [X] T010 [US2] In `app/templates/product/receive.html`, drive the checkbox's `checked` attribute from `form_data` — `{% if form_data and form_data.get('counted') %}checked{% endif %}` — so a tick survives a validation refusal (FR-009) and is absent on every GET (FR-002)
- [X] T011 [P] [US2] Add unit tests to `tests/unit/test_stock_status.py` for contract tests C2 and C8: receiving without `counted` leaves a backdated `quantity_updated_at` exactly as seeded; and `receive_purchase(..., counted=True)` raising `ValidationError` on a bad unit price leaves count, age and received date all untouched
- [X] T012 [P] [US2] Add unit tests to `tests/unit/test_stock_status.py` for contract tests C5 and C7: a second receipt with `counted=True` leaves the received date and the count alone but records the age; and the manual low/out flag and its date are cleared identically whether or not `counted` is set
- [X] T013a [P] [US2] Add form-rendering tests to `tests/unit/test_capture.py`, beside the existing `TestTheReceiveForm`, covering contract tests R1–R5: the control is offered unticked on a GET, absent for an untracked product, present for a tracked count of zero, and comes back ticked or unticked after a refusal exactly as it was submitted. Added during implementation — the E2E test covers R1–R3 but not the refusal round trip, and this is the file that already knows how to assert against that form's markup
- [X] T013 [US2] Verify — do not edit — that no existing `receive_purchase` call site in `tests/` was changed by this feature. `git diff --stat` on `tests/unit/` should show only additions to `test_stock_status.py`. Those unedited call sites are the regression net for this story

**Checkpoint**: `venv/bin/nox -s tests` green, including every pre-existing feature-008 assertion.

---

## Phase 5: User Story 3 — The control is not offered where it would do nothing (P2)

**Goal**: The checkbox appears only where there is a count for it to act on, and the service
refuses to create one regardless.

**Independent test**: Open the receive screen for a purchase against an untracked product and
verify the control is absent.

- [X] T014 [P] [US3] Add a unit test to `tests/unit/test_stock_status.py` for contract test C3: `receive_purchase(id, counted=True)` against a product with `quantity is None` leaves both `quantity` and `quantity_updated_at` as `None` — receiving never begins tracking a count
- [X] T015 [P] [US3] Add an E2E test to `tests/e2e/test_stock_age.py` asserting `#counted` has count 0 on the receive screen for an untracked product, and count 1 for a product whose tracked count is `0`. Establish the page with an `expect()` on `#confirm-receive-btn` before the negative assertion, so it cannot pass against a page that has not loaded

**Checkpoint**: All three stories complete; the feature is functionally done.

---

## Phase 6: Documentation and the feature-008 amendment

Issue #149 asks for the 008 amendment explicitly, and spec SC-006 makes it checkable. These are
prose changes and none of them blocks another.

- [X] T016 [P] Amend `specs/008-trustworthy-stock-age/spec.md` **FR-008** so the carve-out stands with its one named exception: receiving must not present a count as more recently counted than it was, **except** where the operator explicitly asserts at receipt that they counted the stock (feature 041). Do not weaken the default
- [X] T017 [P] Amend `specs/008-trustworthy-stock-age/spec.md` **SC-001** and **SC-003** to match. SC-001 becomes "receiving a purchase never reduces the reported age of a count *unless the operator asserts they counted*"; SC-003's list of the only actions that reset a count's age gains that assertion. Leave FR-015 and SC-007 alone — a count still carries exactly one age, and this feature adds no second date
- [X] T018 [P] Amend the three passages of `specs/008-trustworthy-stock-age/spec.md` prose that state the absolute rule: the Overview sentence about receiving "stamping the count as freshly updated", User Story 1's framing, and the Assumption about receiving continuing to increment a tracked count. Each gains a pointer to feature 041 as the operator's way to say they looked. Do **not** touch that feature's `plan.md`, `tasks.md`, `data-model.md` or checklists — those record how it was built and were accurate
- [X] T019 [P] Amend `docs/user-manual.md` at the "Where a quantity is tracked, it is always shown with its age" paragraph (~line 1966): the sentence "Receiving an order adds to the count without touching the age, because a packing slip is not you looking in the drawer" gains the opt-in — that the receive screen offers a box to tick when you did look, and that ticking it is what moves the date
- [X] T020 [P] Amend `docs/user-manual.md` at the reorder-list paragraph (~line 1996) beginning "Receiving an order clears both kinds of low": its "What receiving deliberately leaves alone is the *count's* age" becomes the rule plus the exception, worded so the default is clearly the unticked one
- [X] T021 [P] Amend `docs/user-manual.md` where the receive screen itself is described (~lines 1393, 1475, 1638 — the order-screen and scanned-bag receive flows all land on the same screen) so the operator learns the control exists in the place they will meet it. One mention, not three: add it where the receive screen's fields are described and cross-reference from the others only if they already enumerate fields

---

## Phase 7: Polish and gates

- [X] T022 Run `venv/bin/nox -s tests` with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"` and confirm green
- [X] T023 Run `venv/bin/nox -s e2e` **detached** (`nohup ... &`, then poll the log) — it takes ~14 minutes warm and exceeds the usual 10-minute shell cap. Confirm green, and confirm the working tree is still clean afterwards per Constitution IV
- [X] T024 Run `venv/bin/nox -s screenshots_headless` then `venv/bin/nox -s screenshots_verify`, because `app/templates/**` changed. Then `git status --short docs/images/screenshots/`: no PNG should differ, since no documentation screenshot shows the receive screen. Commit only images that genuinely changed; leave `metadata.json`'s `generated_at` churn out of the commit
- [X] T025 Walk `quickstart.md`'s five manual scenarios against a running app (`venv/bin/python app.py`), confirming in particular Scenario 4 (a refusal keeps the tick and writes nothing) and Scenario 5 (a second submission records the age), which no automated test drives through the browser
- [X] T026 Re-read the diff for the one thing this feature must not do: confirm no path writes `quantity_updated_at` without `counted` being true, and that `git diff app/` touches only `catalog_service.py`, `database.py`, `product/routes.py` and `templates/product/receive.html`
- [X] T027 Commit, push `robot-army/issue-149-explicit-i-counted-the-shelf-option` to `origin`, and open the pull request

---

## Dependencies

```text
Phase 1 (T001)
   └─▶ Phase 2 (T002 → T003 → T004; T005 [P])       ← blocking: the service rule
          ├─▶ Phase 3 US1 (T006 → T007; T008 [P], T009 [P])
          │      └─▶ Phase 4 US2 (T010; T011 [P], T012 [P], T013)   ← T010 edits the file T007 created
          │             └─▶ Phase 5 US3 (T014 [P], T015 [P])
          └─▶ Phase 6 (T016–T021, all [P])          ← prose only; no code dependency
                 └─▶ Phase 7 (T022 → T023 → T024 → T025 → T026 → T027)
```

**Story independence**: US1 is the feature and stands alone. US2 is a proof about the path US1
does not take — its one code task (T010) edits the template US1 creates, so it follows US1 in
file order, but its value is independent. US3 refines where US1's control appears and can be
skipped without breaking either.

**Phase 6 is genuinely parallel with Phases 3–5**: it changes no code and reads no code that is
in flight.

## Parallel execution examples

**Phase 2**: T005 (`app/database.py` docstring) runs alongside T002–T004 (`app/catalog_service.py`).

**Phase 3**: after T006 and T007 land, T008 (`tests/unit/`) and T009 (`tests/e2e/`) run together.

**Phase 4**: T011 and T012 both append to `tests/unit/test_stock_status.py` — parallel in
principle, but they touch one file, so run them as one edit if working sequentially.

**Phase 6**: T016–T021 span two files (`specs/008-trustworthy-stock-age/spec.md` and
`docs/user-manual.md`) and are all independent of the code phases entirely.

## Implementation strategy

**MVP is Phase 2 + Phase 3** — the parameter, the write, the route, the control and its tests.
That is a shippable, demonstrable feature: tick the box, the age moves.

**Phase 4 is not optional despite being a proof rather than a capability.** The risk this feature
carries is entirely on the untried path, and Constitution IV plus spec Story 2 both make it a
gate.

**Phase 6 is what issue #149 asked for by name.** A shipped feature whose governing spec still
forbids it is the state this issue exists to end, so it does not get deferred to a follow-up.

## Task count

| Phase | Tasks |
|---|---|
| 1 — Setup | 1 |
| 2 — Foundational | 4 |
| 3 — US1 (P1) | 4 |
| 4 — US2 (P1) | 5 |
| 5 — US3 (P2) | 2 |
| 6 — Docs and the 008 amendment | 6 |
| 7 — Polish and gates | 6 |
| **Total** | **28** |
