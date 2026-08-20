---

description: "Task list for 021-fix-aplus-image-selection"
---

# Tasks: A+ Description Images — Keep the Product's, Drop the Vendor's

**Input**: Design documents from `/specs/021-fix-aplus-image-selection/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: **Required, not optional.** Constitution Principle IV: "Changes that alter behavior MUST
land with tests covering that behavior." Every test here is an e2e test, because the thing under
test is a browser script reading a DOM — there is no Python behavior in this feature to unit-test.

**Organization**: Grouped by user story. Read the three notes below before starting; this feature's
shape does not match the template's default assumptions in two places.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to (US1–US4)
- Exact file paths are in every task

## Three notes on this feature's shape

**1. `[P]` is almost absent, and that is not an oversight.** The whole production change lives in
one file (`app/static/js/capture-agent.js`), every new test lives in one other
(`tests/e2e/test_product_page_capture.py`), and every fixture change lives in a third
(`tests/e2e/fixtures/amazon_listing_aplus.html`). Three files, so at most three things can ever run
at once. Marking more `[P]` would be a lie that costs a merge conflict.

**2. US2 comes before US1, and US2 alone is the MVP.** The spec lists US1 (the spec table survives)
first, but the probe showed both symptoms have one cause, and the *exclusion* is the half that fixes
both. Skip the brand story in `descriptionBlock()`'s loop and the loop falls through to
`#aplus_feature_div` — the cross-sells stop being captured **and** the spec table starts being
captured, from one change. US1's phase then makes that robust: `querySelectorAll` so a second
`id="aplus"` is reachable even without a brand story to skip, and `addressOf()` so a deferred
address is not lost. Doing US1 first would be actively worse than doing nothing: gathering all
containers *without* the exclusion captures the brand story **and** the real block — 68 images
instead of 61. Order matters here.

**3. The fixture is Phase 2, not US4's phase.** US4 is "the automated test is anchored to a real
listing", but the fixture has to exist before any US1 or US2 test can be written against it, so its
construction is foundational. US4's phase is what is left over and what actually matters: proving
the fixture can *fail*. T010 is the same idea applied early — if the existing suite stays green
after the fixture gains a brand story, the fixture did not reproduce anything and the rest of the
feature is being tested against a page that cannot exhibit the bug. That is exactly how this defect
shipped the first time.

---

## Phase 1: Setup

**Purpose**: A branch, and a known-green starting point to measure against.

- [X] T001 Create and switch to feature branch `issues/94` from `main` (constitution requires a
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

**Purpose**: Give the suite a fixture that reproduces the real listing's structure. Nothing in
Phase 3 or 4 can be tested without it. Shapes come from [research.md](research.md) §8; the source
of every one of them is the 2026-08-19 probe.

**⚠️ Blocks all user stories.**

- [X] T005 In `tests/e2e/fixtures/amazon_listing_aplus.html`, wrap the existing
      `<div id="aplus" class="aplus-v2">` in a new `<div id="aplus_feature_div">` — the nesting
      `B09GM8FB3X` and `B0DMNXC4CD` both have. Change nothing inside it.
- [X] T006 In the same file, add a `<div id="aplusBrandStory_feature_div">` containing **its own**
      `<div id="aplus" class="aplus-v2">`, placed **before** the block from T005 in document order.
      The duplicate `id` in the earlier position is the defect; a fixture without it tests nothing.
      Give it brand prose ("From the brand …") distinct from the product description so a text
      assertion can tell them apart.
- [X] T007 In the same file, give the brand-story block three cross-sell `<img>` elements that
      **clear** 300 px on both edges (e.g. `_SR800,600_` tokens) — they must be indistinguishable
      from content by size, or they prove nothing about FR-005.
- [X] T008 In the same file, add a deferred-loading image to the real block: `class="a-lazy-loaded"`,
      `src` pointing at a grey-pixel placeholder address, the real address in `data-src`, plus its
      `<noscript>` twin carrying the same address in a plain `src` — the pairing Amazon actually
      emits (research §2).
- [X] T009 In the same file, give at least one content image a real double-underscore transform
      token (`.__CR0,0,1464,600_PT0_SX1464_V1___.jpg`) so `withoutTransform()`'s handling of the
      token shape that actually ships is covered rather than assumed (research §4).
- [X] T010 Add the image files the new addresses need under `tests/e2e/fixtures/images/` — the
      `image_host` fixture serves real bytes and the application really fetches them, so a missing
      file surfaces as a confusing capture failure rather than a 404.
- [X] T011 **Prove the fixture can fail.** With the fixture changed and **no** production change,
      run the A+ tests and confirm `test_the_rich_description_is_kept_and_its_furniture_is_not`
      now **FAILS** — capturing the brand story's images and none of the real block's. Record the
      failing output. If it passes, T006's ordering is wrong and Phases 3–4 would be tested against
      a page that cannot exhibit the bug.

**Checkpoint**: The suite is red for the right reason, and the reason is written down.

---

## Phase 3: User Story 2 — The vendor's other products stay out of the catalog (P1) 🎯 MVP

**Goal**: A capture never stores an image from the brand-story region, and never stores that
region's prose as the product's description.

**Independent test**: Capture the A+ fixture. No cross-sell image is in the payload; the content
images from the same block still are; `description_text` is the product's, not the brand's.

**Why this is the MVP**: see note 2. This phase alone turns `B0FX4PDW6M` from 61 images to 7 and
recovers the spec table, because excluding the brand story lets `descriptionBlock()`'s existing
loop fall through to the container it always should have reached.

### Implementation

- [X] T012 [US2] Add `CROSS_SELL_CONTAINER = '#aplusBrandStory_feature_div'` and
      `isCrossSell(node)` to `app/static/js/capture-agent.js`, per contract C-1 and C-2: true for
      the container and anything inside it at any depth, false (never throwing) when no such
      container exists. Comment it with the observed fact that two of three probed listings carry
      it present-but-empty.
- [X] T013 [US2] In `descriptionBlock()` in `app/static/js/capture-agent.js`, skip a matched block
      for which `isCrossSell` is true and **continue the loop** rather than returning it (C-7).
      This is the one-line change that carries the MVP.
- [X] T014 [US2] In `descriptionImages()` in `app/static/js/capture-agent.js`, skip an image for
      which `isCrossSell` is true **before** any size test (C-10). Not redundant with T013: it
      covers a listing that nests the carousel inside the real description block, and it is what
      makes FR-006 checkable at the image level.

### Tests

- [X] T015 [US2] In `tests/e2e/test_product_page_capture.py`, assert no cross-sell address from the
      brand-story block appears in the payload's `images` (FR-004, SC-002)
- [X] T016 [US2] In the same file, assert the content images from the real block **are** present in
      the same capture — the exclusion removed a region, not the block (FR-006)
- [X] T017 [US2] In the same file, assert `description_text` contains the product description's
      wording and **not** the brand-story prose (FR-011 as amended, C-16). This is the assertion
      that would have caught the company-bio-as-description defect.
- [X] T018 [US2] In the same file, assert a capture of a fixture whose brand-story container is
      absent behaves exactly as it did before this feature (C-2, spec US2 scenario 3)

**Checkpoint**: `B0FX4PDW6M`'s reported symptoms are both fixed. Stop here and the feature has
already paid for itself.

---

## Phase 4: User Story 1 — The specification picture survives the capture (P1)

**Goal**: The correction does not depend on there being a brand story to skip, and no image is lost
to a deferred address or stored as a placeholder.

**Independent test**: Capture the A+ fixture. The deferred-loading image is captured at its real
address; the grey placeholder is not captured at all; images from every A+ region are present.

**Depends on**: Phase 3. Gathering containers without the exclusion in place captures the brand
story *and* the real block — strictly worse than today (note 2).

### Implementation

- [X] T019 [US1] Replace `descriptionBlock(doc)` with `descriptionBlocks(doc)` in
      `app/static/js/capture-agent.js`, per contracts C-6 to C-9: `querySelectorAll` over
      `DESCRIPTION_CONTAINERS`, every match with text, document order, cross-sell blocks excluded,
      `[]` rather than null. `DESCRIPTION_CONTAINERS` itself is **unchanged** — `#aplus_feature_div`
      was always in it and was simply unreachable.
- [X] T020 [US1] Add `PLACEHOLDER_ADDRESS` and `addressOf(img)` to
      `app/static/js/capture-agent.js`, per contracts C-3 to C-5: `data-src` else `src`, then `''`
      for a known deferred-loading placeholder. Comment it with why it matters despite the
      `<noscript>` twins making it redundant today (research §2: the twins may go away).
- [X] T021 [US1] In `descriptionImages()` in `app/static/js/capture-agent.js`, take the address
      from `addressOf(img)` instead of `getAttribute('src')`, and feed that one address to the
      `/^https?:/` test, `knownEdges()` and `withoutTransform()` alike (C-11 to C-13).
      **Do not change `knownEdges()`, `MIN_DESCRIPTION_EDGE` or `withoutTransform()`.**
- [X] T022 [US1] Update the call site in `app/static/js/capture-agent.js`: `description_text` from
      the **first** block `descriptionBlocks()` returns (C-15, preserving 007 FR-005), images
      gathered from **all** of them (C-17), and the no-blocks case leaving the capture otherwise
      intact (C-18).

### Tests

- [X] T023 [US1] In `tests/e2e/test_product_page_capture.py`, assert the image whose address is only
      in `data-src` is captured at that address (FR-002, spec US1 scenario 2)
- [X] T024 [US1] In the same file, assert the grey-pixel placeholder address appears **nowhere** in
      the payload and no placeholder attachment is stored (FR-013 as amended, C-4)
- [X] T025 [US1] In the same file, assert images from every A+ region are captured — the nested
      `#aplus`-inside-`#aplus_feature_div` shape and the separate-sibling shape both (FR-003,
      spec US1 scenario 3)
- [X] T026 [US1] In the same file, assert an image reachable from two overlapping blocks yields one
      payload entry and one stored attachment (C-14, FR-008, spec US1 scenario 5)
- [X] T027 [US1] In the same file, assert the double-underscore transform token is stripped, so the
      captured address is the full-resolution original (FR-007, C-13)

**Checkpoint**: Both halves fixed, and fixed structurally rather than by luck of selector order.

---

## Phase 5: User Story 3 — Neither correction is bought at the other's expense (P1)

**Goal**: Prove the two corrections did not trade one defect for the other, and that the listings
that already worked still do.

**Independent test**: The full suite, plus two deliberate reverts that must each turn it red.

- [X] T028 [US3] In `tests/e2e/test_product_page_capture.py`, confirm the existing furniture
      exclusions still hold — the 1×1 spacer, the 970×20 rule, the 16×16 bullet and the 150 px mark
      are still absent. The 300-pixel rule must survive the block-selection change untouched
      (FR-005, spec US2 scenario 3).
- [X] T029 [US3] In the same file, confirm the four pre-#91 guard assertions are **unchanged**:
      `listing_title`, `brand`, `price` and the exact ordered list of specification names. If these
      need editing, block selection has gone wrong somewhere the image list does not show
      (quickstart §2).
- [X] T030 [US3] In the same file, confirm an image with no establishable dimensions is still
      **kept** — the wider reading must not turn "unknown" into "discard" (007 FR-019, FR-012)
- [X] T031 [US3] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and
      confirm green (no Python changed; this is a guard against accidental scope creep)
- [X] T032 [US3] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s e2e` detached
      (≥15-minute allowance) and confirm every test that passed at T003 still passes
- [X] T033 [US3] **SC-006 revert check A**: temporarily remove the `isCrossSell` checks (T013, T014)
      and confirm a test fails naming the cross-sell images. Restore. A green suite here means the
      over-capture half is untested.
- [X] T034 [US3] **SC-006 revert check B**: temporarily restore `descriptionBlock()`'s
      first-match-wins behavior and confirm a test fails naming the real block's images. Restore. A
      green suite here means the under-capture half is untested.
      **Ran, and the task's premise was wrong.** With the exclusion (T013) in place, first-match-wins
      still reaches the real block — `#aplus` matches the brand story, which is now skipped, and the
      loop falls through to `#aplus_feature_div`. So this revert does *not* reproduce the
      under-capture on these listings. What it does break is the case `descriptionBlocks()` actually
      protects: two *legitimate* regions, where reading only the first loses the second. Exactly one
      test failed — `test_images_are_gathered_from_every_region_not_only_the_first` — which is the
      precise and correct coverage claim. The check passes; its stated reason did not.

**Checkpoint**: Both halves are covered by tests that actually fail when the fix is removed.

---

## Phase 6: User Story 4 — The automated test is anchored to a real listing (P2)

**Goal**: The fixture's fidelity is verified rather than asserted, and its provenance is recorded so
the next reader knows it was observed and when.

- [X] T035 [US4] Run quickstart §3's grep over
      `tests/e2e/fixtures/amazon_listing_aplus.html` and confirm all five shapes are present:
      `aplusBrandStory_feature_div`, two `id="aplus"`, `a-lazy-loaded`, `noscript`, and a
      `__CR0,0` token
- [X] T036 [US4] **The ordering check.** *(Run as: unmodified production code from `HEAD`, brand
      story moved after the real block. Result: the capture takes the real block's four images and
      **no cross-sells at all** — #94's defect is completely unreproducible. Against the same code
      with the brand story first, T011 captured only cross-sells and lost the real block entirely.
      The ordering is load-bearing, demonstrated rather than asserted. It also showed the grey-pixel
      defect reproduces in both orders, confirming research §2's finding that it is a separate,
      pre-existing bug.)* Swap the brand-story block after the real block in the
      fixture, re-run the A+ tests, and confirm the new tests still pass while the original defect
      becomes unreproducible. Restore the order. This is what distinguishes a fixture that catches
      the bug from one that merely contains the right elements (quickstart §3).
- [X] T037 [US4] Add a comment at the top of the brand-story block in
      `tests/e2e/fixtures/amazon_listing_aplus.html` recording that the shape was observed on
      `B0FX4PDW6M` on 2026-08-19, with the counts (126 images / 60 unique in the real one), matching
      how the existing fixture comments cite issue #91 and #57

**Checkpoint**: The fixture is provably able to fail, and says where it came from.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T038 Update the block comments in `app/static/js/capture-agent.js` around
      `DESCRIPTION_CONTAINERS` and `descriptionImages()`: the existing text says the two description
      forms are "never both" (from #57) and that the reader takes whichever is present. That is now
      only true of the *text*; the images are gathered from all. A stale comment here is what the
      next reader will trust.
- [X] T039 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s screenshots_verify`
      and confirm it is a no-op. `capture-agent.js` is never loaded by an application template, so
      no screenshot can depend on it — establish that rather than assume it, and measure any diff
      before committing an image
- [X] T040 Confirm `git status` is clean after the full test run (Principle IV: a test session must
      leave the working tree clean)
- [X] T041 **The manual real-listing check** (quickstart §5) — the one no suite can do.
      *(Run at algorithm level, by the owner's choice: the shipped functions were extracted verbatim
      from `capture-agent.js` and replayed in Chrome against the three real fetched documents. No
      writes to the catalog. Results exactly as predicted — 61→7, 15→14, 3→2, no placeholder in any
      of them. Driving the full bookmarklet-and-confirm path against the live app remains the
      owner's to run.)* Capture
      `B0FX4PDW6M`, `B09GM8FB3X` and `B0DMNXC4CD` through the bookmarklet and read the confirmation
      page before confirming. Expect 7 description images (from 61), 14 (from 15) and 2 (from 3);
      each of the latter two loses exactly one image and it must be the grey placeholder
      (SC-003, SC-004)
- [X] T042 *(Verified at algorithm level with T041; all seven captured addresses load at
      1464×600, the description now opens "Product description …" rather than "From the brand — As a
      global leader …".)* On `B0FX4PDW6M` specifically, confirm the captured images include the 1464×600
      specification table (SC-001), no picture of another vendor product appears (SC-002), and the
      captured description opens with "Specification of 5.79inch E-Paper HMI Display…" rather than
      "From the brand — As a global leader…" (SC-005). That last one is the amended requirement; if
      the description still reads as the company bio, block selection is only half fixed
      (spec FR-011 as amended)
- [ ] T043 Open the PR against `main` from `issues/94`, referencing issue #94, and say plainly in
      the body that the cause was a duplicated `id="aplus"` rather than any of the three causes the
      issue proposed — the issue's diagnosis is what the next reader will otherwise believe
- [ ] T044 Note for the owner, not an agent action: #80 §1b's expected-image-count table and its
      "anything near 57" warning are now stale for `B0FX4PDW6M` (the real number was 61, and the
      size filter was never the problem). Worth a comment on #94 or #80 when this lands

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies
- **Phase 2 (Foundational)**: depends on Phase 1 — **blocks everything after it**
- **Phase 3 (US2)**: depends on Phase 2. **Independently shippable** — the MVP
- **Phase 4 (US1)**: depends on Phase 3, genuinely and not just conventionally. See note 2:
  gathering containers before the exclusion exists makes the over-capture worse
- **Phase 5 (US3)**: depends on Phases 3 and 4 — it is the check that both landed
- **Phase 6 (US4)**: depends on Phase 2 for the fixture and on Phases 3–4 for tests to run against.
  T035 could run right after Phase 2; T036 cannot
- **Phase 7 (Polish)**: last

### Within-phase order

- T005 before T006 (the wrapper must exist before a sibling is placed relative to it)
- T012 before T013 and T014 (the predicate before its call sites)
- T019 before T022 (the function before the call site that consumes its array)
- T020 before T021 (the address helper before the loop that uses it)
- Every implementation task in a phase before that phase's tests

### Parallel opportunities

Genuinely parallel:

- **T031, T039** — two independent nox sessions, if the machine can carry both
- **T010** — image files under `tests/e2e/fixtures/images/`, a different directory from every other
  fixture task; can run alongside T005–T009

Everything else is serial by file:

- **T005–T009, T037** all edit `tests/e2e/fixtures/amazon_listing_aplus.html`
- **T012–T014, T019–T022, T038** all edit `app/static/js/capture-agent.js`
- **T015–T018, T023–T030** all edit `tests/e2e/test_product_page_capture.py`

---

## Implementation Strategy

### MVP (Phases 1–3)

Setup, the fixture, and US2. Excluding `#aplusBrandStory_feature_div` fixes both reported symptoms
on the motivating listing, because the exclusion is what lets the existing loop reach the container
it should always have reached. Stop at the Phase 3 checkpoint, run T041, and issue #94 is
substantively resolved.

### Incremental delivery

1. Phases 1–2 → the fixture reproduces the defect and the suite is red for the right reason
2. Phase 3 → **MVP**: cross-sells out, spec table in, description is the product's (SC-001, SC-002,
   SC-005)
3. Phase 4 → the fix stops depending on selector order and the stored placeholder is killed
   (SC-003, and the defect the issue never reported)
4. Phase 5 → both halves proven by tests that fail without the fix (SC-004, SC-006)
5. Phase 6 → the fixture proven able to fail (FR-015, FR-016)
6. Phase 7 → gates, the manual real-listing check, PR

### Not a parallel-team feature

Three files, one of which is production code. Splitting this across people produces conflicts, not
throughput.

---

## Notes

- `[P]` means different files and no dependency on incomplete work. It is used sparingly here on
  purpose; see note 1
- Commit after each logical group; keep T013 and T015–T017 in one commit so the suite is never red
  between the exclusion landing and its tests
- **Do not raise `MIN_DESCRIPTION_EDGE`, and do not touch `knownEdges()`.** Spec FR-005 forbids it
  and research §4 shows nothing about the size rule is implicated. The cross-sells clear 300 px
  comfortably and always will — they are real product photographs, just of the wrong product
- **Do not add `data-a-hires` or `srcset` handling.** Neither appears on any probed A+ image;
  Principle I forbids machinery for a case with no observed instance. `addressOf()` handles
  `data-src` because a placeholder `src` was actually observed
- **Do not edit `_KNOWN_EXTENSIONS`** in `app/services/listing_images.py`. A GIF is a legitimate
  product image; the placeholder is wrong because it is a placeholder, which is knowable only in
  the browser (contracts/listing-payload.md)
- **Do not touch gallery selection.** #95 owns the gallery counts falling short of #80 §1b, and the
  before/after numbers in T041 assume the gallery behaves exactly as it does today
- No Alembic revision, no schema change, no Python change. If a task seems to need one, the scope
  has slipped
