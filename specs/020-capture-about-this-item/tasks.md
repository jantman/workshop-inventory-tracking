---

description: "Task list for 020-capture-about-this-item"
---

# Tasks: Capture Reads the "About this item" Bullets

**Input**: Design documents from `/specs/020-capture-about-this-item/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **Required, not optional.** Constitution Principle IV: "Changes that alter behavior MUST
land with tests covering that behavior." Every test below is an e2e test, because the thing under
test is a browser script reading a DOM — there is no Python behavior here to unit-test.

**Organization**: Grouped by user story. Read the two notes below before starting; this feature's
shape does not match the template's default assumptions.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to (US1–US4)
- Exact file paths are in every task

## Two notes on this feature's shape

**1. `[P]` is rare here, and that is not an oversight.** The entire production change lives in one
file (`app/static/js/capture-agent.js`) and every new test lives in one other
(`tests/e2e/test_product_page_capture.py`). Two tasks touching the same file are not parallel. The
only genuinely parallel work is the three fixture files. Marking more than that `[P]` would be a
lie that costs a merge conflict.

**2. US2 has no implementation task, and that is the finding.** Re-capture idempotency is delivered
by `CatalogService.merge_specifications`, which already drops a captured name the product carries,
plus the fold seeding done once in Phase 2. US2's phase is therefore all test — the work is proving
the existing machinery covers the new row, not writing new machinery. Resist the urge to add code
there; if a test fails, the fix belongs in Phase 2's seeding, not in a new rule.

---

## Phase 1: Setup

**Purpose**: A branch, and a known-green starting point to measure against.

- [X] T001 Create and switch to feature branch `issues/92` from `main` (constitution requires a
      feature branch and PR for non-trivial code changes)
- [X] T002 Establish the baseline: run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
      venv/bin/nox -s tests` and confirm green before changing anything
- [X] T003 Establish the e2e baseline: run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"
      venv/bin/nox -s e2e` detached (it runs ~8m15s and exceeds a 10-minute command cap; allow
      ≥15 minutes per Principle IV) and record which tests pass, so a later failure is attributable
- [X] T004 Confirm `git status` is clean after T003 — an e2e run that dirties the working tree means
      a screenshot test leaked into the selection, which must be fixed before proceeding

**Checkpoint**: Branch exists, suite is green, and any later red is this feature's doing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The function and its call site exist and are wired, producing *nothing* yet. This is
what every user story builds on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 In `app/static/js/capture-agent.js`, add a `BULLET_CONTAINER` constant (`'#feature-bullets'`)
      next to `SPECIFICATION_CONTAINERS`, with a comment recording what research.md §1 observed:
      the container also holds an `h2` heading and a trailing "See more product details" `div`,
      both outside the `<ul>`, which is why the reader is `li`-scoped
- [X] T006 In `app/static/js/capture-agent.js`, add `bulletsRow(doc)` returning `null` for every
      input — absent container, container with no list, document that is not a listing — and
      never throwing (contract [`bullets-reader.md`](contracts/bullets-reader.md) R-5, R-6;
      FR-008, FR-011)
- [X] T007 In `app/static/js/capture-agent.js`, call `bulletsRow(doc)` at the top of
      `specificationsFrom(doc)` and, when it returns a row, seed **both** the `entries` array and
      the `seen` map with it before the container loop. Seeding the fold — not merely prepending —
      is what makes FR-009 and contract C-5 true (FR-010)
- [X] T008 Re-run `venv/bin/nox -s e2e` (detached, ≥15 min) and confirm it is still green: with
      `bulletsRow` returning `null` the capture must be byte-for-byte what it was at T003

**Checkpoint**: The seam is in place and the application is unchanged. US4's guarantee (FR-008,
FR-012) is already true at this point and T029 will prove it.

---

## Phase 3: User Story 1 - The listing's own description of the product survives the capture (Priority: P1) 🎯 MVP

**Goal**: The About this item bullets reach the catalog as one `About this item` specification row,
one bullet per line, in the listing's order.

**Independent Test**: Capture a listing whose About this item content appears nowhere in its
product-details tables; confirm the saved product carries an `About this item` row holding every
bullet, each on its own line, and that no other captured field moved.

### Fixtures for User Story 1

- [X] T009 [P] [US1] Add an About this item block to `tests/e2e/fixtures/amazon_listing.html` in the
      shape research.md §1 observed on `B01N4OSKWE`: `div#feature-bullets` containing
      `hr.a-divider-normal[aria-hidden]`, `h2.a-size-base-plus.a-text-bold` reading "About this
      item", `ul.a-unordered-list.a-vertical.a-spacing-mini` of
      `li.a-spacing-mini > span.a-list-item`, and a trailing `div.a-section` holding
      "› See more product details". The heading and the trailing div are not decoration — they are
      the two things the reader must exclude, and a fixture without them tests nothing
- [X] T010 [P] [US1] Add the same block to `tests/e2e/fixtures/amazon_listing_aplus.html`, so both
      description forms are covered (the bullets are independent of which form a listing uses).
      Give this one bullets whose text does **not** duplicate the description, so the two are
      distinguishable in an assertion
- [X] T011 [US1] Update the fixture header comment in both files to say what the new block is
      for and that its markup was observed live on 2026-08-19, matching the existing comments'
      practice of recording *why* each structure is present

### Implementation for User Story 1

- [X] T012 [US1] In `app/static/js/capture-agent.js`, implement `bulletsRow`'s reading: take
      `container.querySelectorAll('li')`, run each through the existing `proseOf` so #91's
      stripping and line handling apply unchanged, drop the ones yielding empty text, and join the
      rest with a **single** `\n` — one, not two, because these are list items and `proseFrom`
      already emits paragraph breaks around a `LI` (FR-003, FR-004, FR-007; R-2, R-4)
- [X] T013 [US1] In `app/static/js/capture-agent.js`, return `{name: 'About this item', value: …}`
      when at least one line survived and `null` otherwise (FR-002, FR-008; R-5)
- [X] T014 [US1] Add the function docstring in the file's established voice: what it reads, why it
      is `li`-scoped rather than visibility-filtered, and the fact that `canonicalDocument()` hands
      it a detached `DOMParser` document with no layout — so `offsetHeight` and `getComputedStyle`
      are unavailable, not merely unused (research.md §1, Correction 2)

### Tests for User Story 1

- [X] T015 [US1] In `tests/e2e/test_product_page_capture.py`, add a test that captures
      `amazon_listing.html` and asserts `payload_of(landed)["specifications"][0]` is the
      `About this item` row and that its value splits on `\n` into exactly the fixture's bullets in
      order (US1 scenarios 1–3; FR-001..FR-004, FR-010)
- [X] T016 [US1] In the same file, add a test that confirms the row survives to the product page:
      after `confirm(...)`, navigate to the product and assert `#product-specifications` contains a
      row named `About this item` whose value carries a bullet's text. Establish the region with
      `expect(...)` before any `count()` or `text_content()` read — `#product-specifications` is
      server-rendered but the rule is not conditional
- [X] T017 [US1] Update the exact-order assertion at ~line 508
      (`[row["name"] for row in payload["specifications"]] == [...]`) to lead with
      `"About this item"`. **Update it; do not loosen it to a membership check** — it is #91's
      "nothing else moved" guard and it is what makes FR-010 testable (research.md §5)
- [X] T018 [US1] In the same file, extend or add a test asserting the unchanged fields alongside the
      new row — `listing_title`, `brand`, `price`, `images` — so FR-012 has an assertion and not
      just an intention

**Checkpoint**: US1 is complete and demonstrable. This is the MVP: the bullets are in the catalog.

---

## Phase 4: User Story 2 - Re-capturing does not accumulate copies (Priority: P1)

**Goal**: One `About this item` row per product, no matter how many times the listing is captured.

**Independent Test**: Capture a listing, capture it again onto the same product, confirm exactly one
`About this item` row exists holding the first capture's value.

**Note**: no implementation task. See "Two notes" above — this story is delivered by
`merge_specifications` plus T007's seeding. Every task here is a test.

- [X] T019 [US2] In `tests/e2e/fixtures/amazon_listing_aplus.html`, add a product-details table row
      whose name is `about this item` in a *different case* from the heading, so the agent-side fold
      has a real collision to resolve (US2 scenario 3, FR-009 first half, contract C-5)
- [X] T020 [US2] In `tests/e2e/test_product_page_capture.py`, add a test asserting that capturing
      `amazon_listing_aplus.html` yields exactly one entry whose name folds to `about this item`,
      and that its value is the bullets rather than the table row's — proving the seeding in T007
      put the bullets first
- [X] T021 [US2] In the same file, add a re-capture test: capture, confirm, then capture the same
      listing again through the duplicate/identifier questions (follow the existing
      `test_a_repeat_buy_merges_and_stores_no_second_copy` for the click sequence) and assert the
      product still has exactly one `About this item` row (US2 scenarios 1–2)
- [X] T022 [US2] Extend T021 to edit the row's value by hand between the two captures and assert the
      edited value survives the second capture untouched (US2 scenario 2 — `merge_specifications`
      drops the incoming duplicate rather than overwriting, and that must stay true)

**Checkpoint**: US1 and US2 both hold independently.

---

## Phase 5: User Story 3 - What the shopper cannot see is not captured (Priority: P2)

**Goal**: The heading, the "See more product details" link and empty bullets contribute no lines.

**Independent Test**: Capture a fixture whose bullet container carries all three, and confirm the
row's value holds the bullets and nothing else.

- [X] T023 [US3] In `tests/e2e/fixtures/amazon_listing.html`, add to the bullet list one `li` whose
      span holds only whitespace and one holding only an `<img>` with no text, so FR-006 has cases
- [X] T024 [US3] In `tests/e2e/test_product_page_capture.py`, add a test asserting the row's value
      does **not** contain `"About this item"` (the `h2`, which sits inside `#feature-bullets` and
      would be captured by any container-text reader) nor `"See more product details"` (the
      trailing `div`) — FR-005, R-1
- [X] T025 [US3] In the same file, assert the value contains no empty line and no leading or
      trailing newline, and that its line count equals the number of *non-empty* fixture bullets —
      FR-006, R-3, R-4
- [X] T026 [US3] In the same file, assert the value carries no stylesheet or script text, following
      the existing `test_a_specification_value_carries_no_stylesheet_or_script`; add a `<style>` or
      `<script>` inside one fixture bullet in T023 so the assertion has something to catch
      (FR-007, R-2)

**Checkpoint**: The row reads like the listing, with none of the page's furniture in it.

---

## Phase 6: User Story 4 - A listing with no bullets captures exactly as it does today (Priority: P2)

**Goal**: No bullet list means no row, no empty row, no error, and no other change.

**Independent Test**: Capture a fixture with no About this item section; confirm no such row exists
and every other field is what it was before this feature.

- [X] T027 [US4] Confirm `tests/e2e/fixtures/amazon_listing_markup_only.html` still has **no**
      `#feature-bullets` block — it is deliberately the no-bullets case and must not acquire one
      from T009/T010's edits
- [X] T028 [US4] In `tests/e2e/test_product_page_capture.py`, add a test capturing
      `amazon_listing_markup_only.html` and asserting no entry in `payload["specifications"]` is
      named `About this item`, and that no entry anywhere in the payload has an empty `value`
      (US4 scenarios 1–2; FR-008)
- [X] T029 [US4] In the same file, assert the rest of that capture is unchanged — the existing
      assertions for that fixture at ~line 631 should still pass untouched; if any of them needed
      editing, FR-012 has been violated and the reader is doing more than it should
- [X] T030 [US4] Add a test that a document whose bullet container exists but holds no `<ul>` at all
      yields no row and no error, either by a fourth small fixture or by an extra container in an
      existing one (FR-011, R-6 — the case that proves a moved selector costs one row and nothing
      else)

**Checkpoint**: All four stories hold independently.

---

## Phase 7: Polish, Gates & Verification

**Purpose**: The gates the constitution requires, and the one check no local test can perform.

- [X] T031 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — expected
      green and **unchanged**. If a unit test moved, the change has escaped its scope
- [X] T032 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` detached with a
      ≥15-minute allowance; all new and existing tests green
- [X] T033 Confirm `git status` is clean after T032 (Principle IV: a test run must leave the working
      tree clean)
- [X] T034 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify`.
      `app/static/js/**` is touched so the workflow rule fires, but `capture-agent.js` is never
      loaded by an application template — the run establishes that rather than asserting it. If it
      reports staleness, measure whether the diff has anything to do with this change before
      regenerating; screenshots in this repository churn for unrelated reasons
- [X] T035 Run `venv/bin/nox -s lint` (advisory) on the changed files only; do not reformat
      surrounding code — mass reformatting destroys review signal
> **T036-T039 are only half done, and the half that is missing needs a running
> instance.** The bookmarklet requires the application served over HTTPS against
> MariaDB, so the capture -> store -> display path could not be driven here. What
> *was* verified, on 2026-08-19: the reader's own code, verbatim, run against both
> live listings in the browser. `B01N4OSKWE` yields its five bullets including
> `Main Body Size: 15 x 7 x 7mm/0.59"x0.28"x0.28"(L*W*H)`; `B0FX4PDW6M` yields its
> six. Neither leaked the heading or the "See more product details" link, neither
> produced a blank line, both came back trimmed. That is the half the fixtures
> cannot prove. The end-to-end half remains for the operator.

- [ ] T036 Manual verification, quickstart §4 step 4: capture `https://www.amazon.com/dp/B01N4OSKWE`
      against a running instance and confirm the `About this item` row holds all five bullets, in
      particular `Main Body Size: 15 x 7 x 7mm/0.59"x0.28"x0.28"(L*W*H)` — **SC-001**, and the
      dimensions that appear nowhere else on that listing
- [ ] T037 Manual verification: capture `https://www.amazon.com/dp/B0FX4PDW6M` and confirm its six
      bullets are present and readable — **SC-002**
- [ ] T038 Manual verification: capture `B01N4OSKWE` a second time onto the same product and confirm
      exactly one `About this item` row remains — **SC-004**
- [ ] T039 Manual verification: confirm the stored row renders one bullet per line on the product
      page, and that opening the product's edit form shows it in a `<textarea>` (not an `<input>`)
      and saving does not flatten it — **FR-013**, which #91 already delivered and this confirms
- [X] T041 Update the bookmarklet's list of what it reads in `docs/user-manual.md`, and
      describe where the bullets land, alongside the paragraph 019 added for the part number.
      **Not in the original task list** -- found while the suite was running. That passage
      enumerates what the capture reads, so a feature that adds to the reading and leaves it
      alone makes the manual quietly wrong
- [ ] T040 Open the pull request against `main`, referencing issue #92, and note in the description
      the two premises of the issue that the live probe corrected (research.md §1) so the record
      travels with the change

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Foundational)**: needs Phase 1 — **blocks every user story**
- **Phase 3 (US1)**: needs Phase 2
- **Phase 4 (US2)**: needs Phase 2; its collision test (T020) is only meaningful once T012–T013
  actually produce a row, so in practice it follows Phase 3
- **Phase 5 (US3)**: needs Phase 3 — its assertions are about the value US1 produces
- **Phase 6 (US4)**: needs Phase 2 only. It is genuinely independent of US1 and could be done
  straight after the foundation
- **Phase 7 (Polish)**: needs every story phase intended for the release

### Within each story

- Fixtures before the tests that read them
- Implementation before the tests that assert on it, **except** where a test is being written to
  fail first — T015 and T024 are both worth writing before T012 to watch them fail
- T017 must land in the same commit as T012–T013, or the suite is red between them

### Parallel opportunities

Genuinely parallel:

- **T009, T010** — two different fixture files, no shared content. T011 edits both, so it is
  **not** parallel with either and must follow them
- **T031, T034, T035** — three independent nox sessions, if the machine can carry them

Everything else is serial by file:

- **T005, T006, T007, T012, T013, T014** all edit `app/static/js/capture-agent.js`
- **T015–T018, T020–T022, T024–T026, T028–T030** all edit
  `tests/e2e/test_product_page_capture.py`
- **T009, T019, T023** all edit fixtures, and T019/T023 both touch files T009/T010 created

---

## Implementation Strategy

### MVP (Phases 1–3)

Setup, the foundation, and US1. That is the whole point of issue #92: `B01N4OSKWE`'s dimensions in
the catalog. Stop at the Phase 3 checkpoint, run T036, and the feature has already paid for itself.

### Incremental delivery

1. Phases 1–2 → the seam exists, nothing has changed, suite still green
2. Phase 3 → **MVP**: the bullets are captured (SC-001, SC-002)
3. Phase 4 → re-capture proven idempotent (SC-004)
4. Phase 5 → the row reads like the listing rather than like the page (SC-003)
5. Phase 6 → the no-bullets path proven unchanged (SC-005, SC-006)
6. Phase 7 → gates, manual verification, PR

### Not a parallel-team feature

One file of production code and one file of tests. Splitting this across people produces conflicts,
not throughput. The fixture tasks are the only place a second pair of hands helps.

---

## Notes

- `[P]` means different files and no dependency on incomplete work. It is used sparingly here on
  purpose; see "Two notes" at the top
- Commit after each logical group; keep T012, T013 and T017 in one commit so the suite is never red
- **Do not add visibility filtering.** `canonicalDocument()` yields a detached document with no
  layout — `offsetHeight` is 0 and `getComputedStyle` is meaningless. FR-005 is met structurally,
  by reading `li` only. This is research.md §1's Correction 2 and it is the single easiest way to
  get this feature wrong
- **Do not add hidden-class filtering** (`aok-hidden`, `[hidden]`, `[aria-hidden]`) either. No
  bullet on any of the three probed listings carries one; Principle I forbids machinery for a case
  with no observed instance
- **Do not parse bullet text into fields.** `B01N4OSKWE`'s bullets are full of `Name: Value; Name:
  Value` and it is tempting. The spec rules it out and it is a much harder problem
- No Alembic revision, no schema change, no Python change. If a task seems to need one, the scope
  has slipped
