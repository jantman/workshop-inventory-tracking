---

description: "Task list for 019-capture-mpn-default"
---

# Tasks: The Captured Listing Fills In the Manufacturer Part Number

**Input**: Design documents from `/specs/019-capture-mpn-default/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/README.md](./contracts/README.md),
[quickstart.md](./quickstart.md)

**Branch**: `issues/90` — already created, spec artifacts uncommitted on it.

**Tests**: **Required, not optional.** Constitution IV: "Changes that alter behavior MUST land with
tests covering that behavior," and `nox -s tests` and `nox -s e2e` MUST both be green before merge.

**Organization**: Grouped by user story. US1 and US2 are both P1 and both required for the feature
to be safe to ship — see the spec's "Why this priority" on US2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1, US2, US3 from [spec.md](./spec.md)

## Path Conventions

Flask app at the repository root: `app/` for source, `tests/unit/` and `tests/e2e/` for tests,
`docs/` for documentation. There is no `src/`. Paths below are exact and repository-relative.

---

## Phase 1: Setup

**Purpose**: Nothing to install, nothing to scaffold. This phase exists to confirm the ground is
where the plan says it is before anything is edited.

- [X] T001 Confirm the working tree is clean apart from `specs/019-capture-mpn-default/` and `.specify/feature.json`, and that the branch is `issues/90`, with `git status --short && git branch --show-current`
- [X] T002 Establish the green baseline with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — it must pass in about a second before anything is changed

**No dependency is added and no package is installed.** If `requirements.txt` appears in the diff,
the plan has been misread.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared name-folding helper. **No behavior changes in this phase** — it is a
verbatim move, and the existing barcode tests staying green untouched is the proof.

**⚠️ BLOCKS**: every user story. `PART_NUMBER_ROW_NAMES` is stored pre-normalized, so nothing can be
matched until the normalizer exists.

- [X] T003 Add `normalized_row_name(name: Optional[str]) -> str` to `app/models.py`, near `LISTING_CAPTURE_VERSION` (line 599) — body lifted **verbatim** from `_is_barcode_row_name`: `return ' '.join((name or '').split()).upper()`. Docstring must say it trims, collapses internal whitespace runs, and upper-cases, and that it is shared with the barcode-row matcher (FR-001)
- [X] T004 Rewrite `_is_barcode_row_name` in `app/catalog_service.py:2541` to `return normalized_row_name(name) in BARCODE_ROW_NAMES`, importing `normalized_row_name` from `.models` in the existing import block at line 38. Keep the existing docstring — its reasoning about whole-name matching is still exactly right
- [X] T005 Verify the move was verbatim: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests -- tests/unit/test_capture.py -k Barcode`. `TestWhichRowNamesMeanABarcode` (`tests/unit/test_capture.py:1762`) must pass **with no edit to that file**. A red result here means the move changed behavior; fix the move, do not touch the test

**Checkpoint**: nothing observable has changed. `nox -s tests` is green and no test file was edited.

---

## Phase 3: User Story 1 — The part number the listing published is already in the field (Priority: P1) 🎯 MVP

**Goal**: The confirmation form's Manufacturer Part Number field arrives holding the part number the
listing's own rows name, on both first-render paths, with nothing typed.

**Independent Test**: Capture a listing whose product information carries a `Mfr Part Number` row.
The field arrives holding that row's value; submitting without touching it stores it; every captured
row is still in the product's specification list.

### Implementation for User Story 1

- [X] T006 [US1] Add `PART_NUMBER_ROW_NAMES` to `app/models.py` as a **tuple** in priority order, entries stored pre-normalized: `('MANUFACTURER PART NUMBER', 'MFR PART NUMBER', 'PART NUMBER', 'MODEL NUMBER', 'ITEM MODEL NUMBER')`. Comment must say order is the specification (FR-002), and that this is a tuple where `BARCODE_ROW_NAMES` is a frozenset because order matters here and does not there
- [X] T007 [US1] Add `MANUFACTURER_PART_NUMBER_MAX_LENGTH = 100` to `app/models.py`, with a comment naming `app/database.py:838` (`String(100)`) as the column it mirrors, and stating that an over-long default would fail the write at the end of a fifteen-second capture because nothing in the stack checks length ([research.md](./research.md) §4)
- [X] T008 [US1] Add `ListingCapture.manufacturer_part_number(self) -> Optional[str]` to `app/models.py` (class at line 603): walk `PART_NUMBER_ROW_NAMES` outer, `self.specifications` inner, return the first row whose `normalized_row_name(name)` matches **and** whose stripped value is non-empty and at most `MANUFACTURER_PART_NUMBER_MAX_LENGTH`; return the stripped value; return `None` when nothing qualifies. Must be pure — no I/O, no mutation — because a Jinja template calls it. Docstring must say it is a default, never an assertion
- [X] T009 [US1] Change the `manufacturer_part_number` input in `app/templates/product/capture.html:163-165` from `value="{{ form_data.get('manufacturer_part_number') or '' }}"` to a **presence test on the key**, falling back to `listing.manufacturer_part_number()` when `listing` is set — the exact expression is in [research.md](./research.md) §5. Add a Jinja comment explaining that the test is on presence rather than truthiness because a cleared field must stay cleared (FR-006), and that this deliberately differs from the `manufacturer` field ten lines above

### Tests for User Story 1

- [X] T010 [P] [US1] Add `TestWhichRowNamesMeanAPartNumber` to `tests/unit/test_capture.py`, beside `TestWhichRowNamesMeanABarcode` (line 1762): each of the five names recognized; case, surrounding whitespace and **internal** whitespace runs folded (`'Mfr  Part   Number'`); the whole name must match, not a part of it (`'Vendor Part Number'`, `'Part Numbers'` do not); `None` and `''` are not part-number names; and a guard asserting every `PART_NUMBER_ROW_NAMES` entry equals its own `normalized_row_name` — a typo there would make an entry permanently unmatchable, and silently so (FR-001)
- [X] T011 [P] [US1] Add `TestThePartNumberTheListingNames` to `tests/unit/test_capture.py`, beside `TestTheListingPayload` (line 952): construct `ListingCapture` directly, no app and no database. Cover each recognized name yielding its value; **priority beats page order** (a `Model Number` row first and a `Mfr Part Number` row second yields the second — FR-002, US1 scenario 3); two rows sharing a name yield the first in captured order; the value is returned trimmed and otherwise unaltered (FR-004); and a listing with no rows, and one with no recognized name, both yield `None`
- [X] T012 [US1] Add `TestThePartNumberFillsTheForm` to `tests/unit/test_capture.py`, beside `TestTheListingFillsTheForm` (line 1064), reusing its `payload`/`capture` helper shape: a POST carrying the payload and **no** `manufacturer_part_number` field stores the derived value; the same POST carrying a value stores that value instead; and `GET /products/capture?listing=...` renders the derived value into the field (FR-002)
- [X] T013 [P] [US1] Add a `Mfr Part Number` row with a real value to the `productDetails_techSpec_section_1` table in `tests/e2e/fixtures/amazon_listing.html`, beside the `UPC` row at line 120. The fixture has no part-number row at all today. Comment it the way the `UPC` row is commented, naming issue #90
- [X] T014 [US1] Add an E2E test to `tests/e2e/test_product_page_capture.py`: capture from the fixture, assert `#manufacturer_part_number` already holds the fixture's value with nothing typed, then `confirm(landed)` and assert the stored product carries it. Follow `test_the_agent_fills_in_the_price_and_the_brand` (line 169) exactly — same helpers, same assertion style. **No fixed wait**: the form is server-rendered, so `expect(...).to_have_value(...)` is the whole wait (`CLAUDE.md` Pattern C)
- [X] T015 [US1] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — green, sub-second, network blocked

**Checkpoint**: US1 is complete and independently demonstrable end to end. **This alone closes what
issue #90 reported.**

---

## Phase 4: User Story 2 — The operator overrules the listing (Priority: P1)

**Goal**: A value the operator typed or cleared is what gets captured, on the first submission and
after a capture question.

**Independent Test**: Capture a listing that produces a derived default, replace the value, submit,
and confirm the product carries the typed one. Repeat, clearing the field, and confirm the product
carries no part number — including when the capture comes back asking a question first.

**Note on ordering**: most of US2 is already true after Phase 3, because the form submits what it
displays and `_clean('')` is `None`. What is left is the two rules that are not automatic: the
absent-versus-empty distinction on the write, and the re-render.

### Implementation for User Story 2

- [X] T016 [US2] In `app/product/routes.py`, `product_capture` POST branch, add `manufacturer_part_number` to the absent-versus-empty fallback block at lines 415–421 — read it with `request.form.get(...)`, and fall back to `listing.manufacturer_part_number()` **only when it is `None`** (FR-005). Pass the local into the `capture_order` call at line 434, replacing the inline `request.form.get('manufacturer_part_number')`. Extend the existing comment above the block to name the third field rather than writing a second comment
- [X] T017 [US2] Verify no change was made to the `manufacturer` or `unit_price` handling in that same block, and none to the `manufacturer` input at `app/templates/product/capture.html:154`, with `git diff app/product/routes.py app/templates/product/capture.html`. Those two still use `or` on re-render; that wart is out of scope by a stated spec assumption and **must not appear in this diff**

### Tests for User Story 2

- [X] T018 [P] [US2] Add `TestAClearedPartNumberStaysCleared` to `tests/unit/test_capture.py`, beside `TestThePayloadSurvivesAQuestion` (line 1579), reusing its `payload`/`post` helper shape: a POST submitting an **empty** `manufacturer_part_number` stores no part number and the derived value is not silently restored (FR-005, US2 scenario 2); a POST that triggers `CaptureDecisionRequired` re-renders with the field **empty**, not refilled (FR-006, US2 scenario 3); and the same re-render with a *typed* value shows the typed value
- [X] T019 [US2] Add an E2E test to `tests/e2e/test_product_page_capture.py`: capture from the fixture, clear the field with `confirm(landed, manufacturer_part_number="")`, and assert the stored product carries no part number. Establish the region with `expect(...)` before any snapshot read — a negative assertion against a region that has not rendered passes trivially (`CLAUDE.md`)
- [X] T020 [US2] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — green

**Checkpoint**: US1 and US2 both work. The feature is now safe to ship: the default exists and it can
always be overruled.

---

## Phase 5: User Story 3 — A useless candidate is passed over (Priority: P3)

**Goal**: Empty, whitespace-only and over-long candidates supply no default and do not end the
search.

**Independent Test**: A listing whose highest-priority part-number row has an empty value and whose
next one has a real value yields the second.

**Note**: US3's *implementation* landed in T008 — the usability test is part of the same walk, and
splitting it out would mean editing one method twice. What is genuinely separate is its coverage.

- [X] T021 [US3] Extend `TestThePartNumberTheListingNames` (created in T011) in `tests/unit/test_capture.py` with FR-003's cases: a row whose stripped value exceeds `MANUFACTURER_PART_NUMBER_MAX_LENGTH` yields nothing from that row **and the search continues to the next recognized name**; a value at exactly the limit is accepted; a row whose value is empty or whitespace-only is passed over rather than ending the search (US3 scenarios 1 and 2); and the returned value is trimmed (US3 scenario 3)
- [X] T022 [US3] Add a second part-number row to `tests/e2e/fixtures/amazon_listing.html`, higher-priority than T013's row but with an **empty** value, so the browser path exercises the pass-over and not only the happy case. Comment it naming issue #90 and FR-003
- [X] T023 [US3] Add an E2E test to `tests/e2e/test_product_page_capture.py` asserting the confirmation form skips the empty higher-priority row and shows T013's usable lower-priority value, via `capture_from_listing` and `expect(landed.locator("#manufacturer_part_number")).to_have_value(...)`

**Checkpoint**: all three stories are independently demonstrable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T024 [P] Update the bookmarklet paragraph in `docs/user-manual.md` (around line 905 — "for an Amazon page that means the price, the brand, the description, every *Product information* row, and every image...") to name the manufacturer part number, and say it is a default the operator can change or clear
- [X] T025 Run the E2E suite: `nohup env PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e > /tmp/e2e-019.log 2>&1 &` then poll. **It outlasts a 10-minute command cap — run it detached.** Constitution IV requires a 15-minute allowance
- [X] T026 Regenerate screenshots: `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_headless`, then `venv/bin/nox -s screenshots_verify`. `docs/images/screenshots/user-manual/order_capture.png` is the capture page's screenshot (written by `tests/e2e/test_screenshot_generation.py::test_screenshot_order_capture`) and 018 regenerated exactly that file when it last edited this template. Screenshots churn on every run — inspect what actually differs and commit `order_capture.png` plus anything whose content genuinely moved, **not** the whole directory
- [X] T027 Confirm the working tree is clean after a plain `nox -s tests` and `nox -s e2e` run (Constitution IV: a test session must leave the tree clean) with `git status --short`
- [X] T028 Walk [quickstart.md](./quickstart.md) sections 1–3 and 5 end to end, and section 6 by hand against `B0CZ72JRHP` and `B0FX4PDW6M` if a TLS-served instance is available. SC-001 is the acceptance: the field arrives filled with zero keystrokes
- [X] T029 Review the full diff against the file list in [plan.md](./plan.md): `app/models.py`, `app/catalog_service.py`, `app/product/routes.py`, `app/templates/product/capture.html`, `tests/unit/test_capture.py`, `tests/e2e/test_product_page_capture.py`, `tests/e2e/fixtures/amazon_listing.html`, `docs/user-manual.md`, one screenshot, and this spec directory. **Anything else in the diff is a defect**: no migration, no `requirements.txt`, no JavaScript, no `app/database.py`, no `_form_fields.html`
- [X] T030 Open the pull request against `main` referencing issue #90, and note in the body the FR-006 scope call — this field's cleared value survives a re-render, `manufacturer` and unit price still do not, and aligning them is deliberately a separate change

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Foundational)**: after Phase 1. **Blocks everything** — `PART_NUMBER_ROW_NAMES` is stored pre-normalized, so nothing matches until `normalized_row_name` exists
- **Phase 3 (US1)**: after Phase 2
- **Phase 4 (US2)**: after T008 for the write rule and after T009 for the re-render. Its E2E test (T019) additionally needs T013's fixture row
- **Phase 5 (US3)**: after T011 (it extends that class) and after T013 (its fixture row is the fallback the pass-over lands on)
- **Phase 6**: after Phases 3, 4 and 5

### Task Dependencies Worth Naming

- T004 depends on T003 — the function must exist before the caller is rewritten
- T005 is the gate on Phase 2 and must be green before T006
- T008 depends on T003, T006 and T007; it uses all three
- T009 and T016 both depend on T008 and are independent of each other
- T014, T019 and T023 all depend on T013 (the fixture row) and on T009 (the template change)
- T021 extends the class T011 creates, so it is sequential with respect to T011
- T022 depends on T013 — the empty row is only meaningful with a usable row below it
- T026 depends on T009: the template change is what makes regeneration necessary

### Within Each User Story

Implementation before tests here, not after. This is not TDD by choice of the spec — the
constitution requires tests to *land with* behavior, not to precede it, and every one of these tests
asserts against a helper whose signature the implementation task defines.

### Parallel Opportunities

This is a solo project on a small feature, so **most tasks are sequential and marking them `[P]`
would only create conflicts**. What genuinely can run at the same time:

- **T010 and T011** — two new test classes touching no implementation file and not depending on each other. Same file, so commit them together
- **T013** — the E2E fixture, disjoint from all Python
- **T018** — a test class no implementation task is editing at that moment
- **T024** — documentation, disjoint from everything

`app/models.py` carries T003, T006, T007 and T008; those four are strictly sequential. Four tasks
add classes to `tests/unit/test_capture.py` (T010, T011, T012, T018) and one extends a class there
(T021), so they conflict on that file even where they are logically independent.

## Implementation Strategy

### MVP First (User Story 1 only)

1. T001–T005 — foundational, no behavior change
2. T006–T015 — the derivation, the render, the unit tests, the fixture, one E2E test
3. **STOP and VALIDATE**: capture the fixture listing and look at the field
4. That alone closes what issue #90 reported

### Incremental Delivery

1. Foundational → one folding rule, two callers, nothing observable
2. US1 → the field arrives filled (MVP)
3. US2 → what the operator decided is what gets captured, including "nothing"
4. US3 → a useless candidate is provably passed over rather than offered
5. Polish → user manual, full suites, screenshot, by-hand pass, diff review, PR

---

## Notes

- `[P]` = different files, no dependency on an incomplete task
- Commit after each task or logical group
- **No migration, no new dependency, no JavaScript, no payload version bump.** If any appears in the
  diff, the plan has been misread. `LISTING_CAPTURE_VERSION` stays at `1` — bumping it makes every
  cached bookmarklet capture with no payload at all
- **Do not touch the `manufacturer` or unit price fields** (T017). They re-apply their default over a
  cleared field on re-render; that is a known wart, out of scope by a stated spec assumption
- **Do not unify `normalized_row_name` with `_fold`** (`app/catalog_service.py:2536`). They answer
  different questions and `_fold` deliberately does not collapse internal whitespace
- **Do not condition the default on the merge outcome** by analogy with 016. This feature writes
  nothing; it fills a form field in front of the operator. See [research.md](./research.md) §6
- **Do not truncate an over-long value to fit** (FR-003). A truncated part number is a wrong part
  number, and a wrong one corroborates a later repeat buy against the wrong product
- E2E waiting rules are not style: `CLAUDE.md` and Constitution IV. Both pages here are
  server-rendered, so `expect(locator).to_have_value(...)` is the whole wait

---

## What changed during implementation

Recorded here rather than silently, because three of these change what the tasks said.

- **The recycled-identifier question stops being asked on a re-capture.** Not anticipated anywhere in
  the planning documents, and found by two E2E tests failing. `_corroborates` requires the
  manufacturer **and** the part number to agree before a capture may attach to a product whose
  identifier it landed on; the capture has always supplied the first and never the second, so the
  pair never corroborated and every re-capture raised the question. Filling the part number supplies
  the missing half. `test_a_hand_edited_value_survives_a_re_capture` and
  `test_a_repeat_buy_merges_and_stores_no_second_copy` both used that question to reach their
  subject; both now clear the field on their first capture, with a comment saying why.
  `test_a_repeat_buy_no_longer_has_to_answer_the_identifier_question` pins the new behaviour, and
  the spec gained an edge case and SC-006a. This is the outcome US1 is named for — it is the payoff,
  not a regression.
- **T022/T023 changed shape.** The plan called for an *empty* higher-priority row in the E2E
  fixture. The capture agent drops a row with no value before the payload is built
  (`specificationsFrom`, `capture-agent.js:295`), so an empty cell never reaches Python and a test
  built on one proves nothing. The fixture row is *over-long* instead, at 101 characters against a
  ceiling of 100, which does survive the agent and does exercise FR-003. The empty and
  whitespace-only cases are covered in the unit tests, where they can be reached.
- **T012 was narrowed and T018 widened.** T012 was written to cover the write-path fallback, whose
  implementation is T016 in the next phase. The render assertions stayed in T012; the
  absent-versus-empty write assertions moved into `TestAClearedPartNumberStaysCleared` alongside the
  code that makes them pass.
- **T026 commits no screenshot.** `order_capture.png` came back byte-identical: the template edit
  adds a Jinja comment and an expression that yields the same empty string in a scenario with no
  listing. Nine unrelated images churned by a few hundred bytes each and were reverted. Details in
  [quickstart.md](./quickstart.md) §5.
- **The quickstart's test selectors were wrong** and are corrected. `-k part_number` matches test
  function names only and picks up eight of the forty-eight; the class names are what select the
  feature.
- **T015/T020's "sub-second" is inherited from the constitution and is stale.** The unit suite runs
  in about 23 seconds, 44 with nox's overhead. Not this feature's to fix.

**Verification at the end**: `nox -s tests` 1432 passed; `nox -s e2e` 558 passed, 0 failed;
`nox -s screenshots_verify` 18 verified. A mutation check confirmed the FR-006 guard bites — rewriting
the template expression with `or` fails `test_a_cleared_field_comes_back_cleared` and nothing else.
