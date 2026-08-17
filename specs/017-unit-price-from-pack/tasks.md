---

description: "Task list for feature implementation"
---

# Tasks: Unit Price From a Multi-Pack

**Input**: Design documents from `/specs/017-unit-price-from-pack/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/README.md](./contracts/README.md), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are **included and required**, not optional. Constitution Principle IV:
"Changes that alter behavior MUST land with tests covering that behavior." The arithmetic is
JavaScript and this repository has no JS test runner (and is not getting one — see
[research.md](./research.md) §"Testing the arithmetic"), so the rounding table is driven from
Playwright with `page.evaluate` against `window.unitPriceFromPack`, and the operator-facing
behavior is driven through the form. Everything runs under `nox -s e2e`.

**Organization**: Tasks are grouped by user story so each can be implemented, tested and shipped on
its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are in every task

Very little here is `[P]`, and that is not an oversight: the feature is three files, and every
test lands in the same test file. Parallelism has nothing to bite on.

## Path Conventions

Flask web application, server-rendered. This feature lives in exactly four files:
`app/static/js/pack-unit-price.js` (new), `app/templates/product/capture.html`,
`tests/e2e/test_order_capture.py` and `docs/user-manual.md`. **No route, no service, no model, no
migration.** If a task has you editing `app/product/routes.py`, `app/catalog_service.py`,
`app/database.py` or `migrations/`, stop and re-read [plan.md](./plan.md) — the route already
carries arbitrary form fields through a re-render, and this feature stores nothing.

---

## Phase 1: Setup

**Purpose**: One new file and the tag that loads it. No dependency, no configuration, no scaffold.

- [X] T001 Confirm work is on feature branch `issues/97` (cut during `/speckit-specify`), not `main` — constitution: non-trivial code changes go through a branch and a PR
- [X] T002 Create `app/static/js/pack-unit-price.js` with its header docstring and nothing else: state that it is a plain global rather than an ES module (matching `app/static/js/label-count.js`, and because `capture.html` loads plain scripts), and that the arithmetic is `BigInt` so that Principle III holds by construction rather than by care
- [X] T003 [P] Load it from `app/templates/product/capture.html` — add `<script src="{{ url_for('static', filename='js/pack-unit-price.js') }}"></script>` to the `scripts` block beside `field-autocomplete.js`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The arithmetic, and the fields it reads and writes. Every story needs both.

**⚠️ No user story work can begin until this phase is complete.**

- [X] T004 Implement `window.unitPriceFromPack(paid, packSize)` in `app/static/js/pack-unit-price.js`, pure and DOM-free, exactly to [contracts/README.md](./contracts/README.md#unitpricefrompackpaid-packsize): trim both; reject `paid` not matching `^\d+(\.\d+)?$` with `field: 'pack_price'`; return `paid` **verbatim** when `packSize` is empty or `1` (FR-010, FR-015 — no parse, no reformat); reject `packSize` not matching `^\d+$` or not greater than zero with `field: 'pack_size'`; otherwise `A = N * 100n`, `B = BigInt(packSize) * 10n ** BigInt(s)`, `q = A / B`, `r = A % B`, `if (2n * r >= B) q += 1n`, value `` `${q / 100n}.${String(q % 100n).padStart(2, '0')}` ``, `exact = (r === 0n)`. **No `Number`, no `parseFloat`, no `toFixed` anywhere in the file** (FR-006, FR-007)
- [X] T005 Add the two inputs to `app/templates/product/capture.html`, regrouping the Order Date / Quantity / Unit Price row so the derivation reads left to right: `#pack_price` (`name="pack_price"`, `inputmode="decimal"`, value `form_data.get('pack_price') or (listing.price if listing else '') or ''`) and `#pack_size` (`name="pack_size"`, `type="number"`, `min="1"`, `step="1"`, value `form_data.get('pack_size') or '1'`). Leave `#unit_price` and its existing `listing.price` prefill **exactly as they are** — at a pack size of 1 the two agree, which is what keeps a single-unit capture and the assertions in `tests/e2e/test_product_page_capture.py` untouched (FR-013, FR-015). Reading both values out of `form_data` is what satisfies FR-012 with no route change
- [X] T006 Add the two message elements beneath the Unit Price field in `app/templates/product/capture.html`, both hidden by default: `#unit-price-inexact` (FR-008) and `#unit-price-error` (FR-011), as `form-text` lines
- [X] T007 Comment, at the `#pack_price` field, why the extracted listing price prefills it *and* `#unit_price`: without JavaScript the page must still be today's page, and a capture that never touches the pack fields must record what it records today

**Checkpoint**: `nox -s e2e` still green — the page has two new inputs that do nothing yet, and no existing behavior has moved.

---

## Phase 3: User Story 1 - Record a multi-pack without reaching for a calculator (Priority: P1) 🎯 MVP

**Goal**: The operator states what the pack cost and how many units it held, and the unit price is
worked out in the page, editable, before anything is captured.

**Independent Test**: Open `/products/capture`, enter `29.97` and a pack of `3`, read `9.99` off
the Unit Price field, and capture. Delivers the whole of issue #97 on its own.

### Tests for User Story 1 ⚠️

> Write these first and watch them fail. They all land in `tests/e2e/test_order_capture.py`, so
> they are sequential with each other, not `[P]`.

- [X] T008 [US1] Add the rounding table test to `tests/e2e/test_order_capture.py`: load `/products/capture`, then drive `page.evaluate("([p, n]) => window.unitPriceFromPack(p, n)", [...])` over the table in [contracts/README.md](./contracts/README.md#the-table-this-must-satisfy) — `29.97/3 → 9.99` exact, `17.99/3 → 6.00` inexact, `0.01/3 → 0.00` inexact, `10.00/4 → 2.50` exact, `17.995/2 → 9.00` inexact, `1249.50/1` and `1249.50/''` verbatim, `9/2 → 4.50` exact — plus the rejections: `1,249.50`, `$5`, `''`, `5.` name `pack_price`; `0`, `-1`, `2.5`, `three` name `pack_size`
- [X] T009 [US1] Add the operator-flow test: fill `#pack_price` `29.97` and `#pack_size` `3`, `expect(page.locator("#unit_price")).to_have_value("9.99")`, capture, and assert `9.99` on the receive screen (US1 scenarios 1 and 4)
- [X] T010 [US1] Add the override test: derive `9.99`, `fill("#unit_price", "9.95")`, capture, assert the recorded price is `9.95` — what the operator typed is what is recorded (FR-004, US1 scenario 2)
- [X] T011 [US1] Add the recompute-from-inputs test: derive `9.99`, type `1.00` over it, change `#pack_size` to `6`, and expect `#unit_price` to hold `5.00` — derived from `29.97 ÷ 6`, never from the `1.00` that was in the field (FR-005, US1 scenario 3)
- [X] T012 [US1] Add the nothing-destroyed test: type `4.00` into `#unit_price` by hand, then put `0` in `#pack_size`; expect `#unit-price-error` visible and naming the pack size, and `#unit_price` **still** `4.00` (FR-011)

### Implementation for User Story 1

- [X] T013 [US1] Wire the recompute in `app/static/js/pack-unit-price.js`: `input` listeners on `#pack_price` and `#pack_size` that call `unitPriceFromPack` with both current values and, on `ok`, write `value` into `#unit_price`. **Nothing listens on `#unit_price`** — an override is an override (FR-004, FR-005)
- [X] T014 [US1] On `ok: false`, show `#unit-price-error` with the message and leave `#unit_price` untouched; hide it again on the next successful computation (FR-011)
- [X] T015 [US1] Guard the whole wiring on the fields being present, so the script is inert on every other page that might later load it, and returns early rather than throwing

**Checkpoint**: Issue #97 is closed by this phase alone. The calculator is gone; the rounding is not yet explained.

---

## Phase 4: User Story 2 - See when the division did not come out even (Priority: P2)

**Goal**: A unit price that does not multiply back to what was paid says so, in place, before
capture.

**Independent Test**: Enter `17.99` and a pack of `3`; read `6.00` and the statement that three of
them do not come back to `17.99`, without submitting anything.

### Tests for User Story 2 ⚠️

- [X] T016 [US2] Add the note test to `tests/e2e/test_order_capture.py`: `17.99` over a pack of `3` shows `#unit-price-inexact` naming the pack size, the unit price and the amount paid; `29.97` over `3` does not show it (FR-008, FR-009, US2 scenarios 1 and 2)
- [X] T017 [US2] Add the note-clears test: with the note showing, change `#pack_size` to `1`, and expect `#unit-price-inexact` hidden and `#unit_price` back to `17.99` verbatim (US2 scenario 3, FR-010)
- [X] T018 [US2] Add the load-time test: `GET /products/capture?pack_price=17.99&pack_size=3` — the route renders with `form_data=request.args`, so both fields arrive populated — and expect `#unit-price-inexact` visible on a page nobody has typed into

### Implementation for User Story 2

- [X] T019 [US2] Show and hide `#unit-price-inexact` from the `exact` flag on every recompute in `app/static/js/pack-unit-price.js`, and word it with the three numbers that make it checkable: the pack size, the derived unit price, and the amount paid it does not add back up to
- [X] T020 [US2] Evaluate the note **on page load** as well, and — the part that matters — do **not** write `#unit_price` on that path: a re-render may be carrying a unit price the operator typed before the form came back with a question, and a load-time write would silently discard it ([data-model.md](./data-model.md#state-transitions))

**Checkpoint**: The rounding is visible rather than silent. US1 still passes unchanged.

> **Ordering note, recorded rather than tidied away.** T019 and T020 were written in the same
> edit as T013, before the US2 tests existed, because all three are branches of one
> `recompute()` function and splitting them across two edits would have meant writing the
> function twice. The US1 tests were written first and watched fail; the US2 tests were written
> after the code they cover and passed on their first run. T020 also came out slightly different
> from how it was specified: the **error** line is not evaluated on load, only the inexactness
> note, because every fresh capture page has an empty pack price and greeting the operator with
> an error for that is noise. [data-model.md](./data-model.md#state-transitions) and
> [contracts/README.md](./contracts/README.md#dom-contract-on-productscapture) were corrected to
> match what was built.

---

## Phase 5: User Story 3 - The pack inputs survive a question (Priority: P3)

**Goal**: A capture that comes back asking about a duplicate or a recycled item number still shows
what the unit price was derived from.

**Independent Test**: Capture the same listing twice with the pack fields filled in; on the second,
the duplicate warning appears and both pack fields are still populated.

**Note**: T005 already reads both fields out of `form_data`, so this story is expected to pass on
arrival. The test is not redundant — it is what stops a later edit to that template from quietly
taking it away, which is precisely the failure the existing `listing` hidden field carries a
comment about.

### Tests for User Story 3 ⚠️

- [X] T021 [US3] Add the survives-a-question test to `tests/e2e/test_order_capture.py`: capture a listing, then capture it again with `#pack_price` `29.97` and `#pack_size` `3` filled in; expect `#duplicate-warning` visible and `#pack_price`, `#pack_size` and `#unit_price` all still holding their values (FR-012, US3 scenario 1)

### Implementation for User Story 3

- [X] T022 [US3] If T021 fails, fix it in `app/templates/product/capture.html` only — the route must not learn about either field (FR-014). If it passes, record in the task list that no code change was needed and why — **it passed on arrival; no code change was needed.** `product_capture` re-renders with `form_data=request.form` and the template reads both fields out of `form_data` (T005), so the derivation survives the duplicate question with nothing in the route knowing either field exists. That is also FR-014 satisfied by omission: a field the route never reads is a field it cannot store

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T023 [P] Document the pack fields in `docs/user-manual.md`, "Capturing an Order When You Place It" (around line 896): what the two fields are for, and one sentence stating the rounding and its consequence — a pack price that does not divide evenly leaves the unit price a fraction of a cent off what was paid, and the page says so
- [X] T024 Regenerate the capture screenshot with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless` — `capture.html` changed, so `docs/images/screenshots/user-manual/order_capture.png` is stale, and the constitution makes regenerating it part of the change rather than a follow-up
- [X] T025 `venv/bin/nox -s screenshots_verify` — valid PNG, RGB/RGBA, under 500KB
- [X] T026 `venv/bin/nox -s tests` — unchanged by this feature and must stay green; if anything here moved, something was edited that this feature has no business editing
- [X] T027 `venv/bin/nox -s e2e` with a **15-minute** tool timeout (constitution Principle IV; run it detached and poll if the runner caps shorter). Confirm `tests/e2e/test_product_page_capture.py` still asserts `#unit_price` of `24.99` and `1249.50` — those assertions are the regression gate on FR-015
- [X] T028 Confirm the test session left the working tree clean (`git status --short` empty apart from intended edits) — a test run that rewrites screenshots is a failed run
- [X] T029 Review the diff against [quickstart.md](./quickstart.md#what-to-check-in-the-diff): no `parseFloat`, `toFixed` or arithmetic on a `Number` in `pack-unit-price.js`; no change to `app/product/routes.py`; no Alembic revision; no `wait_for_timeout` or `networkidle` in the new tests
- [ ] T030 Walk the eight manual checks in [quickstart.md](./quickstart.md#manual-validation), including the no-JavaScript check and one real bookmarklet capture — the bookmarklet path prefills `#pack_price` and cannot be exercised from CI
- [ ] T031 Open the pull request for `issues/97` referencing issue #97, stating the rounding decision and its consequence in the description so the choice is reviewable where the code is

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: needs T002; blocks all three stories
- **US1 (Phase 3)**: needs Phase 2. No dependency on US2 or US3
- **US2 (Phase 4)**: needs Phase 2. Reads the `exact` flag T004 already returns, so it does not depend on US1's wiring existing — but in practice it is written after it, in the same file
- **US3 (Phase 5)**: needs Phase 2 (specifically T005's `form_data` reads). Independent of US1 and US2
- **Polish (Phase 6)**: after every story that is going in. T024/T025 need the final template; T031 needs everything

### Within Each User Story

Tests first, and failing, before the implementation task that makes them pass. Within a story the
implementation tasks are sequential — they edit one file.

### Parallel Opportunities

- T003 is `[P]` with T002: different files
- T023 is `[P]` with the test tasks: `docs/user-manual.md` is touched by nothing else
- Everything else is sequential by file. `app/static/js/pack-unit-price.js`,
  `app/templates/product/capture.html` and `tests/e2e/test_order_capture.py` each take one editor
  at a time

## Implementation Strategy

### MVP (User Story 1 only)

Phases 1 → 2 → 3, then stop and validate. That is issue #97 closed: the pack price and pack size
are entered, the unit price appears, the operator can override it, and nothing reaches for a
calculator. US2 and US3 improve the explanation, not the capability.

### Incremental delivery

1. Setup + Foundational → the page has the inputs and the arithmetic exists
2. US1 → the unit price is worked out (MVP — ship-able)
3. US2 → the rounding stops being silent
4. US3 → the derivation survives a question
5. Polish → manual, screenshot, full suites, PR

## Notes

- Every task names its file. Nothing in this feature touches a route, a service, a model or a
  migration
- Commit per phase, or per logical group within a phase
- The one thing to be careful about is T004: it is the only arithmetic in the feature, and the
  reason it is the only arithmetic is so that there is exactly one place to get it wrong
