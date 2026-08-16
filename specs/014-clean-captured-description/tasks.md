---

description: "Task list for Clean Captured Description"
---

# Tasks: Clean Captured Description

**Input**: Design documents from `/specs/014-clean-captured-description/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/text-extraction.md](./contracts/text-extraction.md), [quickstart.md](./quickstart.md)

**Tests**: Required, not optional. Principle IV: "Changes that alter behavior MUST land with tests covering that behavior." Every requirement in this feature is a behavior change to extracted text, and the only place it is observable is an e2e capture run.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Server-rendered Flask app with one browser-side script. Real paths only:

- `app/static/js/capture-agent.js` — the entire implementation
- `tests/e2e/fixtures/amazon_listing_aplus.html`, `tests/e2e/fixtures/amazon_listing.html` — the fixtures
- `tests/e2e/test_product_page_capture.py` — every test

## A note on how this feature splits

**The code does not split three ways; the tests do.** The implementation is one helper in one file becoming four helpers in the same file — roughly 40 lines. Splitting that edit across three story phases would mean three passes over the same thirty lines, which is worse than one pass, not better.

So Phase 2 carries the whole code change, and Phases 3–5 carry each story's fixture cases, assertions and independent verification. Each story's phase remains independently testable and independently valuable, which is what the story split is for. **Parallelism is close to zero** for the same reason: one JS file, two fixtures, one test file. `[P]` appears only where two tasks genuinely touch different files; do not invent more.

---

## Phase 1: Setup

**Purpose**: Record what "unchanged" means before changing anything, so SC-003 and SC-006 are checkable rather than remembered.

- [X] T001 Capture and record the current baseline: run `nox -s e2e -- tests/e2e/test_product_page_capture.py`, and from a temporary print or debugger in `tests/e2e/test_product_page_capture.py` record today's exact `description_text` for both fixtures, the image list, the brand, the price, the title and the full list of specification names. Save them into the scratchpad (not into the repo) — they are the comparison values for T013, T014 and T024. Remove any temporary printing before committing.
- [X] T002 Read [contracts/text-extraction.md](./contracts/text-extraction.md) end to end, in particular the normalization order table and the call-site table. The four normalization steps are order-dependent and the call-site assignment is what keeps `brandFrom` working; both are easy to get subtly wrong from memory.

**Checkpoint**: The pre-change behavior is written down.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The whole code change. Every user story depends on it.

**⚠️ CRITICAL**: No story phase can begin until this phase is complete.

All tasks in this phase edit the "Reading the page" section of `app/static/js/capture-agent.js`. **None of them are parallel** — they are sequential edits to the same thirty lines.

- [X] T003 Add the non-content selector constant and `contentClone(node)` to `app/static/js/capture-agent.js`, returning `node.cloneNode(true)` with every `style, script, noscript, template` descendant removed from the clone. The original must not be touched — `canonicalDocument()` falls back to the operator's live `document`, so an in-place removal would edit the page they are looking at (FR-003, contract G2). Document that reason in the docstring; it is not obvious from the call site.
- [X] T004 Add the block-boundary and line-break element sets as module-level constants in `app/static/js/capture-agent.js`: block = `P, DIV, LI, TR, H1, H2, H3, H4, H5, H6`, matched on `nodeName` (upper-case for HTML elements); line break = `BR`. Not configurable and not extended — see research.md §4 for the wider sets that were rejected.
- [X] T005 Add `proseFrom(clone)` to `app/static/js/capture-agent.js`: recurse over child nodes, appending each text node's data **with `/\s+/g` collapsed to a single space as it is appended**, `'\n'` for a `<br>`, and `'\n\n'` both before and after a block element. The text-node collapse is the load-bearing part — markup is indented, so without it a paragraph's own source newlines come through as line breaks the reader never saw (contract G5).
- [X] T006 Add the four-step normalization to the end of `proseFrom` in `app/static/js/capture-agent.js`, in this exact order: `replace(/[^\S\n]+/g, ' ')`, then `replace(/ *\n */g, '\n')`, then `replace(/\n{3,}/g, '\n\n')`, then `trim()`. Step 2 must precede step 3 or a line holding only spaces defeats the fold, which is the spec's "whitespace-only block" edge case. Comment the ordering constraint at the call site.
- [X] T007 Add `proseOf(node)` (`node ? proseFrom(contentClone(node)) : ''`) and redefine `textOf(node)` as `proseOf(node).replace(/\s+/g, ' ').trim()` in `app/static/js/capture-agent.js`. `textOf`'s contract is unchanged — one line, collapsed, trimmed, `''` for a missing node, never null, never a throw (contract G3). Keep its existing docstring line and add why it is now defined in terms of `proseOf`.
- [X] T008 Rewire the call sites in `app/static/js/capture-agent.js` per the contract's call-site table: `extract`'s `description_text` and `rowsFrom`'s table-cell **value** move to `proseOf`; `priceFrom`, `brandFrom`, `titleFrom`, `descriptionBlock`'s emptiness test and every specification **name** stay on `textOf`. `brandFrom` matching `^Visit the (.+?) Store$` is the reason names and bylines must not gain newlines — JavaScript's `.` does not match `\n` (FR-009).
- [X] T009 Replace the detail-bullet value arithmetic in `rowsFrom` in `app/static/js/capture-agent.js`: instead of `whole.slice(textOf(bold).length)`, take `contentClone(items[i])`, remove `.a-text-bold` from the clone, and read `proseFrom(clone).replace(/^[\s:]+/, '')`. The slice assumes the name is a character-for-character prefix, which stops being true the moment either side can hold a newline, and it fails silently rather than throwing.
- [X] T010 Confirm `descriptionImages(block)` in `app/static/js/capture-agent.js` still receives the **original** block and not a clone. `knownEdges()` reads `img.naturalWidth`, which is 0 on a detached clone, so passing it a clone would silently change which images survive the size filter (contract, `contentClone` notes). No code change expected — this is a read-and-verify task.

**Checkpoint**: The agent produces clean, line-structured text. Nothing proves it yet.

---

## Phase 3: User Story 1 - The stored description is the listing's words, not its markup (Priority: P1) 🎯 MVP

**Goal**: A captured description contains the manufacturer's copy and none of the stylesheet or script text that A+ blocks carry.

**Independent Test**: Capture from a listing whose description block contains an inline stylesheet and inline script code, and read the stored `Description`. It holds the block's visible copy and nothing else. Provable without any assertion about line structure.

**Fixture and tests are in different files, so T011 and T012 are parallel with each other. The test tasks are not — they all edit `tests/e2e/test_product_page_capture.py`.**

- [X] T011 [P] [US1] Add an inline `<style>` (a rule with braces and semicolons), an inline `<script>` (with a `var` and a `function`), and a `<noscript>` block inside `#aplus` in `tests/e2e/fixtures/amazon_listing_aplus.html`. Extend the fixture's header comment to say what each is there to prove, in the style of the existing image table.
- [X] T012 [P] [US1] Add `tests/e2e/fixtures/amazon_listing_markup_only.html` — a listing whose `#aplus` block contains nothing but a `<style>` and a `<script>`, with a readable `#productDescription` present as well, so the fall-through in FR-004 is observable rather than just "nothing captured".
- [X] T013 [US1] Add a test to `tests/e2e/test_product_page_capture.py` capturing the enriched A+ fixture and asserting that the parsed `listing` payload's `description_text` contains none of the stylesheet text, none of the script source, and not the `<noscript>` text (test table rows 1–3, FR-001). Establish the landed page with an `expect(...)` before reading `input[name='listing']` — `input_value()` is a snapshot and does not wait.
- [X] T014 [US1] Add a test to `tests/e2e/test_product_page_capture.py` capturing `amazon_listing_markup_only.html` and asserting that the `#aplus` block is skipped and the `#productDescription` copy is what lands in `description_text` (test table row 11, FR-004).
- [X] T015 [US1] Add a test to `tests/e2e/test_product_page_capture.py` capturing the plain `amazon_listing.html` and asserting `description_text` equals the baseline string recorded in T001, character for character (test table row 12, FR-010, SC-003, contract G6). This is the test that stops the fix becoming a truncation.
- [X] T016 [US1] Extend the existing `test_the_rich_description_is_kept_and_its_furniture_is_not` in `tests/e2e/test_product_page_capture.py` to also assert the title, brand, price, image list and the full set of specification names against the T001 baseline (test table row 16, FR-014, SC-006). The image assertion is already there; the others are new.
- [X] T017 [US1] Add a test to `tests/e2e/test_product_page_capture.py` that captures twice from the same tab and asserts both payloads are identical, proving the extraction did not mutate the page it read (FR-003, contract G2).

**Checkpoint**: The defect that inflated two descriptions past 21,000 characters is fixed and proved. This alone is worth shipping.

---

## Phase 4: User Story 2 - The description keeps its paragraphs, and shows them (Priority: P2)

**Goal**: A captured description breaks where the listing breaks, and the product page displays those breaks.

**Independent Test**: Capture from a listing whose description has explicit line breaks and multiple paragraphs, open the product page, and confirm the displayed value breaks where the listing does. Provable independently of any stylesheet stripping.

**No new code is expected in this phase.** `app/templates/product/detail.html:106` already carries `white-space: pre-wrap` and `app/templates/product/_form_fields.html:59` already switches to a textarea for any value containing a newline; both are already tested against a multi-line value in `tests/e2e/test_product_specifications.py`. What is missing is a test joining those to a *captured* description. If T020 or T021 fails, that finding is real and the template work becomes part of this phase — do not assume it away.

- [X] T018 [US2] Extend `#aplus` in `tests/e2e/fixtures/amazon_listing_aplus.html` with the remaining structure cases: a paragraph containing a `<br>`, a paragraph whose source is indented across three lines, a three-deep nesting of `<div>` around a paragraph followed by a sibling paragraph, a `<div>` containing only whitespace between two paragraphs, and a list item containing a `<br>` (test table rows 4–10).
- [X] T019 [US2] Add a test to `tests/e2e/test_product_page_capture.py` asserting the parsed payload's `description_text` equals one exact expected string covering rows 4–10 together — the `<br>` as a single `\n`, the heading and paragraphs separated by a blank line, list items on their own lines, the indented paragraph on one line, the nesting producing exactly one blank line, and the whitespace-only division producing none (FR-005 to FR-008). One string assertion reads better than seven substring ones and catches ordering bugs the substrings miss.
- [X] T020 [US2] Add a test to `tests/e2e/test_product_page_capture.py` that captures the enriched A+ fixture, confirms, opens the product detail page and asserts the rendered `Description` value contains its line breaks — read through `inner_text()`, which respects `white-space: pre-wrap` (FR-011). Establish `#product-specifications` with an `expect(...)` before reading; a snapshot read against a table that has not rendered returns empty and the assertion passes for the wrong reason.
- [X] T021 [US2] Add a test to `tests/e2e/test_product_page_capture.py` that opens the captured product for editing, changes an unrelated field, saves, and asserts the `Description` value still holds its line breaks (FR-012). This is the round trip that an `<input>` would silently destroy.

**Checkpoint**: A captured description reads as the listing reads, on the page and through an edit.

---

## Phase 5: User Story 3 - A specification row is prose too (Priority: P3)

**Goal**: The same treatment reaches product-information rows — the `Customer Reviews` cell on `B09GM8FB3X` and anything shaped like it.

**Independent Test**: Capture from a listing whose product-information table has a cell containing an inline stylesheet or script, and read that row on the product page. Its value is the cell's visible text only.

- [X] T022 [US3] Extend the product-information table in `tests/e2e/fixtures/amazon_listing_aplus.html` with three rows: a `Customer Reviews` cell holding rating text plus an inline `<style>` and `<script>`, a cell whose value spans two `<p>` elements, and a `<th>` name cell containing a `<br>` (test table rows 13–15).
- [X] T023 [US3] Add a test to `tests/e2e/test_product_page_capture.py` asserting the parsed payload's `Customer Reviews` specification value is the rating text alone, with no stylesheet or script text (FR-002, SC-005).
- [X] T024 [US3] Add a test to `tests/e2e/test_product_page_capture.py` asserting that the two-paragraph cell's value contains the paragraph break, and that the `<th>` containing a `<br>` yields a single-line name that still merges as one name rather than two (FR-009, data-model S1).
- [X] T025 [US3] Add a test to `tests/e2e/test_product_page_capture.py` asserting the detail-bullet rows in `tests/e2e/fixtures/amazon_listing.html` still extract the same name/value pairs as the T001 baseline, after the T009 rewrite. The rewrite removed the slice arithmetic; this is what proves the removal was equivalent.

**Checkpoint**: All three stories independently proved.

---

## Phase 6: Polish & Verification

**Purpose**: The gates, the manual pass, and the discipline checks that apply across all three stories.

- [X] T026 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests`. No Python ships with this feature, so this is a regression gate; it must be green and fast.
- [X] T027 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` **detached, with at least a 15-minute allowance** — it outlasts a 10-minute shell cap on a cold start. Then confirm `git status` is clean; if `docs/images/screenshots/` changed, screenshot tests leaked into the run and the changes must be reverted.
- [X] T028 Review the new tests in `tests/e2e/test_product_page_capture.py` against the checklist in `CLAUDE.md` "Reviewing a new e2e test": every wait names an element and not a number; every `input_value()`, `count()` and `inner_text()` has an `expect(...)` establishing its region first; every negative assertion would fail against a page that has not loaded.
- [X] T029 Settle the screenshot question. `.github/workflows/screenshots.yml` fires on `app/static/js/**` and this PR touches it, but the workflow is informational (issue #77) and leaves the judgment to the author. If no template changed — which is the plan's expectation — record that judgment in the PR description and regenerate nothing. If a template did change, run `nox -s screenshots` and `nox -s screenshots_verify` and commit `docs/images/screenshots/`.
- [X] T030 Confirm the diff contains no Python change, no Alembic revision, no new dependency in `requirements.txt`, and no new pytest marker. Any of those means the plan was departed from and the departure needs a stated reason.
- [ ] T031 **Optional, owner-gated**: with the owner present, drive their Chrome to `B0DMNXC4CD`, `B09GM8FB3X` and `B0FX4PDW6M` and look at how a real A+ block is built — where the stylesheets sit relative to the copy, whether the prose is in paragraphs or table cells, how deep the nesting runs. Fold anything learned back into `tests/e2e/fixtures/amazon_listing_aplus.html` as markup shaped like the real thing, with a note in the header comment saying why. This is fixture fidelity, not a prerequisite; it can happen after the code is green.
- [ ] T032 Run the manual six-listing pass in [quickstart.md](./quickstart.md), "Verifying against the real listings". **Remove each A+ product's existing `Description` row before re-capturing** — `merge_specifications` is already-present-wins, so re-capturing onto the existing product keeps the contaminated value and looks like the fix failed. Check SC-001, SC-002 and SC-005 on the three A+ listings and SC-003 on the three plain ones, and read one A+ description against the live page to confirm it got shorter by losing markup and not by losing prose.
- [ ] T033 Open the pull request from `issues/91`, referencing issue #91 and #80. Note in the description which of SC-001 to SC-007 were verified by test and which by the manual pass, and record the screenshot judgment from T029.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. T001 must happen **before** any Phase 2 edit, or the baseline it records is already the new behavior.
- **Foundational (Phase 2)**: Depends on Phase 1. Blocks all three stories.
- **User Stories (Phases 3–5)**: All depend on Phase 2. Independent of each other and may be done in any order, though P1 → P2 → P3 is the value order.
- **Polish (Phase 6)**: T026–T030 depend on whichever stories are being shipped. T031 and T032 need the owner and can trail the code.

### Within Phase 2

Strictly sequential, T003 → T010. Every task edits the same region of one file, and T007 through T009 depend on the helpers T003 through T006 create.

### Within each story phase

Fixture task first, then the tests that read it. Within US1, T011 and T012 are the only genuinely parallel pair in this feature — different fixture files, no shared state.

### Parallel Opportunities

Almost none, and that is a property of the feature rather than an oversight. One implementation file, one test file, two fixtures. The complete list:

- T011 and T012 (two different fixture files).
- T026 and T031 (a test run and an owner-driven browser session share nothing).

Do not mark the test tasks `[P]`. They all edit `tests/e2e/test_product_page_capture.py` and would conflict.

---

## Implementation Strategy

### MVP (User Story 1)

1. Phase 1 — record the baseline.
2. Phase 2 — the whole code change.
3. Phase 3 — the fixture cases and tests for contamination.
4. **STOP and VALIDATE**: `nox -s e2e -- tests/e2e/test_product_page_capture.py`, then re-capture `B0DMNXC4CD` by hand and read the result.

That is a shippable fix for the defect that made two descriptions exceed 21,000 characters. The line structure is an improvement on top of a value that is already usable.

### Incremental delivery

1. Phases 1–2 → the agent behaves correctly, nothing proves it.
2. Phase 3 → US1 proved. **Ship-worthy.**
3. Phase 4 → US2 proved. The description reads as it reads on the listing.
4. Phase 5 → US3 proved. The contaminated specification row is clean.
5. Phase 6 → gates and the manual pass.

### Notes

- Commit after each phase, not each task — Phase 2's tasks are sequential edits to one function and intermediate commits would not build a coherent history.
- Never invoke `pytest` directly; every run goes through `nox` (Principle IV).
- No `wait_for_timeout`, no `time.sleep`, no `networkidle` in any new test. The rule binds every call site, not only new ones.
- If Phase 4 reveals that FR-011 or FR-012 does **not** already hold, say so and fix the template in that phase. The plan's finding that both already work is a reading of the code, and a test disagreeing with a reading means the test is right.
