---

description: "Task list for 022-reconcile-gallery-counts"
---

# Tasks: Gallery Image Counts — Reconcile the Expectation with the Listing

**Input**: Design documents from `/specs/022-reconcile-gallery-counts/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/](contracts/gallery-reading.md), [quickstart.md](quickstart.md)

**Tests**: **Required, not optional.** Constitution Principle IV: "Changes that alter behavior MUST
land with tests covering that behavior." Every test here is an e2e test — the thing under test is a
browser script reading a DOM, and there is no Python behavior in this feature to unit-test.

**Organization**: Grouped by user story. Read the four notes below first; this feature's shape
departs from the template's assumptions in three places, and one of them will waste an afternoon if
it is missed.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to (US1–US5)
- Exact file paths are in every task

## Four notes on this feature's shape

**1. US1 is already done.** The probe ran during `/speckit-plan` on 2026-08-20 with the owner
present, as FR-001 requires. Phase 3 is recorded complete rather than omitted, because the record of
*what was measured and when* is a deliverable of this feature and not a step towards one.

**2. The fixture change must be made — and proved to fail — before the fix.** This is Phase 2, and
it is the single most important ordering constraint here. The current fixture writes the gallery as
a bare array literal, which no real listing does; that is exactly why the suite stayed green while
production ran a fallback path for an entire release. Writing the fix first and the fixture second
would reproduce the original mistake at greater length.

**3. Rewriting the fixture's wrapper is not enough on its own, and this is the trap.** The fixture's
`hiRes` and `large` share a filename stem — `steel_rod_sample._AC_SL1500_.jpg` and
`steel_rod_sample._AC_SX679_.jpg` — so `withoutTransform()` collapses them to one address and the
duplicate-emitting sweep produces the *same six images* the parse does. Change only the wrapper and
the suite stays green, proving nothing. Real Amazon gives each rendition **its own asset id**
(`81flPsAWG-L` against `512DrDtlPkL`), which is precisely why the doubling reaches the database. The
fixture has to do the same on at least two entries, or T008's red gate cannot go red.

**4. `[P]` is nearly absent, and that is not an oversight.** The production change is one file
(`app/static/js/capture-agent.js`), the tests are one file
(`tests/e2e/test_product_page_capture.py`), the fixture is a third. Three files, so at most three
things can run at once. Marking more `[P]` would buy a merge conflict.

---

## Phase 1: Setup

**Purpose**: A branch and a known-green starting point to measure against.

- [X] T001 Create and switch to feature branch `issues/95` from `main` (constitution requires a
      feature branch and PR for non-trivial code changes)
- [ ] T002 Establish the baseline: run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox
      -s e2e` **detached** (`nohup … &`, then poll) with a ≥15-minute allowance, and record that it
      is green before anything is touched. It outruns the 10-minute Bash cap; do not run it in the
      foreground.

---

## Phase 2: Foundational — make the fixture able to exhibit the defect

**Purpose**: Put the vendor's real markup shape into the fixture and prove the current code fails
against it. Nothing in Phase 4 means anything until T008 has gone red.

**⚠️ Do not start Phase 4 before T008 fails.** A green T008 means the fixture still cannot reproduce
the defect and the fix would be validated against a page that cannot exhibit it.

- [ ] T003 [P] Add two low-resolution twin images to `tests/e2e/fixtures/create_sample_images.py`
      and regenerate into `tests/e2e/fixtures/images/`: `steel_rod_sample_small.jpg` and
      `steel_plate_sample_small.jpg`, visibly smaller than their originals. They stand for Amazon's
      separate `large` asset id — see note 3. Commit the generated files alongside the script.
- [ ] T004 Rewrite the `colorImages` block in `tests/e2e/fixtures/amazon_listing.html` into the form
      the vendor actually serves: `'colorImages': { 'initial': A.$.parseJSON('[…]') }`, the array as
      a JSON string inside single quotes. Keep the six entries, their order, their `variant` values
      and the `"hiRes":null` sixth entry exactly as they are. Add a comment saying this shape was
      read from all six probed ASINs on 2026-08-20 and citing [research.md](research.md) §1, so the
      next person does not "tidy" it back into a literal.
- [ ] T005 In the same fixture, point the `large` of the first two entries at the T003 twins, so
      those entries name two *different* asset stems the way a real listing does. Leave the other
      entries sharing a stem — a fixture where every entry behaves the same way tests less than one
      where they differ.
- [ ] T006 [P] Add `tests/e2e/fixtures/amazon_listing_unreadable_gallery.html` — a copy of the
      listing whose `colorImages` payload is present but malformed (truncated JSON), for US5's
      degradation test and for the "a structural surprise costs images, never the capture" rule in
      [contracts/gallery-reading.md](contracts/gallery-reading.md) §5.
- [ ] T007 Update the fixture's own thumbnail-strip comment in
      `tests/e2e/fixtures/amazon_listing.html` — it says reading the gallery from the strip "is
      precisely the mistake this fixture exists to catch", which is now only half the story. Record
      that on five of the six real listings the gallery and the strip are the same number, so a
      count alone cannot catch that mistake ([contracts/gallery-reading.md](contracts/gallery-reading.md),
      "checkable consequences").
- [ ] T008 **RED GATE.** Run `nox -s e2e` (detached, ≥15 min) and confirm
      `test_the_whole_gallery_comes_across_not_just_the_thumbnails` **fails**, reporting **8** images
      where it expects `GALLERY_IMAGE_COUNT` (6): five distinct `hiRes` stems, plus the two twins
      from T005, plus the sixth entry's `large`. If it passes, stop — the fixture did not reproduce
      the defect and note 3 has been missed. Record the observed number in the PR description.

**Checkpoint**: The suite is red for the right reason, and the reason is written down.

---

## Phase 3: User Story 1 — The question is settled by looking (Priority: P1) ✅ DONE

**Goal**: Establish, in the owner's signed-in browser with the owner present, what these listings
actually publish — before touching the extractor or the record.

**Independent test**: The three numbers per listing exist, dated, and decide the rest of the work.

- [X] T009 [US1] Probe `B0CKXJLP4B` and `B099F4X4Q9` in the owner's Chrome, reading from the
      **fetched** `/dp/<ASIN>` document; record gallery entries, thumbnails, and what the agent
      returns, separately (FR-002). → [research.md](research.md) §0
- [X] T010 [US1] Widen to all six of #57's ASINs once the first two show the cause is structural
      rather than listing-specific. → [research.md](research.md) §0, §1
- [X] T011 [US1] Establish the variant situation on `B0CKXJLP4B` (FR-003). →
      [research.md](research.md) §4
- [X] T012 [US1] Re-measure the FR-004 anchor from the CDN in the same session (FR-017). →
      [research.md](research.md) §5
- [X] T013 [US1] Amend `spec.md` where the probe falsified it, as dated amendments beside the
      original text (FR-016), and re-validate `checklists/requirements.md`.

**Checkpoint**: The cause is known and written down. Both of issue #95's candidate explanations are
dead, and the one thing the probe could not settle is recorded as open ([research.md](research.md) §8).

---

## Phase 4: User Story 2 — A capture collects every gallery image, once (Priority: P1)

**Goal**: One address per gallery entry, naming the largest rendition that entry offers.

**Independent test**: Against the T004 fixture, the capture yields six images — the five `hiRes`
originals and the sixth entry's `large` — and neither twin.

- [ ] T014 [US2] In `app/static/js/capture-agent.js`, make `initialImageArray()` locate the array
      when it is the argument of a `parseJSON` call inside a quoted string, as well as when it is a
      bare literal (FR-022). Both forms must work: real listings serve the first, the fixture's
      history and any future change may serve the second. The existing bracket-matching and
      `JSON.parse` are correct and stay — the payload inside the quotes is plain JSON and parses
      cleanly on all six probed listings ([research.md](research.md) §1).
- [ ] T015 [US2] In the same file, make `sweepImageAddresses()` emit **one** address per entry
      rather than one per `hiRes`-or-`large` key (FR-021). It is the last resort for a block the
      parser does not understand; a last resort that doubles every gallery is worse than one that
      returns the `hiRes` addresses alone, because a missed `hiRes: null` entry costs one image
      where today's behavior costs a duplicate of every image. Do not delete the function — see
      [research.md](research.md) §6 for why the fallback is kept.
- [ ] T016 [US2] **GREEN GATE.** Re-run `nox -s e2e` (detached) and confirm T008's test passes again
      at 6, and that the whole suite is green.
- [ ] T017 [P] [US2] Add an e2e test to `tests/e2e/test_product_page_capture.py` asserting the
      payload's `images` for the `parseJSON`-wrapped fixture is **exactly** the five `hiRes`
      originals plus `spec_sheet_preview.jpg`, and that neither `steel_rod_sample_small.jpg` nor
      `steel_plate_sample_small.jpg` appears. Assert membership, not just the count — a count alone
      would pass against a reading that swapped an original for its twin.
- [ ] T018 [P] [US2] Add an e2e test asserting the `"hiRes":null` entry is captured by way of its
      `large`, and is not skipped. This is the case `initialImageArray()`'s docstring was written for
      and which has never once executed against a real listing.
- [ ] T019 [P] [US2] Add an e2e test asserting a **bare-literal** gallery array is still read
      correctly, so T014 widens the reading rather than moving it. Use a small dedicated fixture or
      a `.replace()` on the existing one, matching the file's existing style.

**Checkpoint**: FR-021 and FR-022 hold, and reverting either T014 or T015 turns the suite red.

---

## Phase 5: User Story 5 — A degraded reading is visible (Priority: P2)

**Goal**: When the gallery array cannot be read in the expected form, the operator can tell.

**Independent test**: Capture the T006 unreadable fixture and observe the console says so; capture a
normal listing and observe it says nothing new.

- [ ] T020 [US5] In `galleryFrom()` (`app/static/js/capture-agent.js`), emit one `console.warn`
      naming the listing when the sweep answered rather than the parse — beside the existing
      `console.warn` in `canonicalDocument()` and in the same voice. One line. Not a counter, not a
      payload field, not a setting; Principle I, and [plan.md](plan.md)'s Constitution Check.
- [ ] T021 [US5] Add an e2e test capturing `amazon_listing_unreadable_gallery.html` and asserting
      (a) the capture still completes and still carries the description and the specification rows,
      and (b) the warning was emitted. Wait on observable state — the landing page — never on a
      duration.

**Checkpoint**: The silence that hid this defect for a release is gone.

---

## Phase 6: User Story 4 — The original-resolution check has evidence behind it (Priority: P2)

**Goal**: FR-004's check is runnable and unambiguous. The numbers are already confirmed; the wording
is what changes.

**Independent test**: Follow #80 §1b B4 as written and reach a verdict without deciding which stored
image to measure.

- [ ] T022 [P] [US4] Verify — do not rewrite — that `app/static/js/capture-agent.js`'s
      `withoutTransform()` comment still states the right figures (1446×1500 / 345,670 against
      1601×1601 / 358,055). The probe re-measured both on 2026-08-20 and they are unchanged
      ([research.md](research.md) §5). If it matches, change nothing and tick this task.
- [ ] T023 [US4] Correct #80 §1b's **B4** so it names the image by its filename stem
      (`81flPsAWG-L`) rather than saying "check a stored original", and record the 500×500 / 62,467
      figure of the `512DrDtlPkL` twin as a third row, so a verifier measuring a pre-existing
      duplicate recognises what they are looking at instead of reporting a failure.

---

## Phase 7: User Story 3 — The record states what is true, and when it was read (Priority: P1)

**Goal**: Nobody re-derives this in six months. Every corrected figure carries its date and the way
to re-read it.

**Independent test**: Read the corrected record cold, without a browser, and know which number to
compare against and how old it is.

**Do this after Phase 4**, so the "after" numbers are measured rather than predicted.

- [ ] T024 [US3] Rewrite #80 §1b's table with the 2026-08-20 numbers, replacing the single expected
      column with **three**: gallery entries, thumbnails on screen, and whole-document `hiRes`
      labelled as *not* the requirement. Say plainly that the old column was the third of those and
      that it is family-wide, not aged (FR-014, FR-015). Include all six ASINs.
- [ ] T025 [US3] Correct #80 §1b's **B1** instruction. It currently tells a verifier that landing on
      the thumbnail number proves a DOM read; on five of six listings the gallery and the strip are
      the same number, so as written it can only be failed by being correct (FR-023,
      [research.md](research.md) §3). Point it at quickstart §B instead.
- [ ] T026 [US3] Add a note to #80 §1b — or to §6, "expected surprises" — that captures made before
      this feature carry roughly twice the gallery images they should, half of them ~500-pixel
      copies; that nothing is lost or corrupt; and that removing them is bulk photo deletion (#96),
      pointing at [quickstart.md](quickstart.md) §F. Without this the next pass files the halved
      counts as a regression.
- [ ] T027 [P] [US3] Amend `specs/007-product-page-capture/quickstart.md` §B — the sentence naming
      "the two listings whose page data names more than twice what the thumbnail strip shows", and
      any expected count that came from #57's column. **Dated amendment beside the original, never an
      overwrite** (FR-016): `specs/` is the frozen record of what was specified at the time.
- [ ] T028 [P] [US3] Amend `specs/007-product-page-capture/tasks.md` T052 the same way — it requires
      "an image count matching issue #57's *page data* column rather than its thumbnail column",
      which is the instruction that produced this issue. It is still an open task, so it will be read
      again.
- [ ] T029 [P] [US3] Check `specs/007-product-page-capture/research.md` (the token-stripping
      measurement, ~line 95). The probe re-measured it and it is correct; if so, change nothing and
      tick. Recorded as a task so "did anyone check?" has an answer.

**Checkpoint**: SC-003 and SC-007 hold — no surviving expectation is undated, and each says how to
re-derive it.

---

## Phase 8: Polish & verification

- [ ] T030 Run one **real capture** of `B0CKXJLP4B` through the bookmarklet against the running app
      and record the confirmation panel's image count. Expect **7**. This also settles
      [research.md](research.md) §8 — the one thing the probe could not reproduce, issue #95's
      "Captured 7" — as a by-product. Whatever it shows, write the answer into research §8 rather
      than leaving the question open.
- [ ] T031 [P] Repeat T030 for `B099F4X4Q9` (expect 7) and `B01N4OSKWE` (expect 3) — the three
      plain-description listings, where the panel count should equal the gallery exactly. The three
      A+ listings are floors, not equalities, because #94's feature contributes description images.
- [ ] T032 Confirm SC-010 on a captured product: measure a stored gallery image and get the
      dimensions the listing's data names for that entry, never 500×500. `identify` the file or read
      `Photo.file_size`.
- [ ] T033 [P] Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` — expected
      to be unaffected; this feature changes no Python.
- [ ] T034 Run the full `nox -s e2e` detached, ≥15 minutes, green, and confirm it left the working
      tree **clean** (Principle IV — a test run must not modify tracked files).
- [ ] T035 [P] Run `nox -s screenshots_verify`. `app/static/js/**` is touched, which triggers the
      screenshot gate, but `capture-agent.js` is never loaded by an application template so no
      screenshot can depend on it. Establish that rather than assert it, and **measure any diff
      before committing an image** — regeneration is not reproducible (#80 §6).
- [ ] T036 Open the pull request from `issues/95`, summarising: the cause (a marker that never
      matched), the doubling it caused, that #80 §1b was never a gallery count, the six before/after
      counts, and the fact that already-captured products keep their duplicates until the operator
      prunes them.

---

## Dependencies

```text
Phase 1 (T001–T002)
      ↓
Phase 2 (T003–T008)  ← the fixture, and the RED GATE
      ↓
Phase 4 (T014–T019)  ← the fix. MUST NOT start before T008 is red
      ↓
Phase 5 (T020–T021)  ← independent of Phase 6/7; touches galleryFrom() so it follows T014
      ↓
Phase 6 (T022–T023) ─┬─ both are record-only and mutually independent
Phase 7 (T024–T029) ─┘   both need Phase 4's measured "after" numbers
      ↓
Phase 8 (T030–T036)

Phase 3 (T009–T013) is complete and blocks nothing — it is what produced Phases 2 and 4.
```

**The one hard ordering rule**: T008 red → T014/T015 → T016 green. Everything else is convenience.

## Parallel opportunities

Genuinely parallel, by file:

- **Phase 2**: T003 (`create_sample_images.py` + images) alongside T006 (a new fixture file). T004,
  T005 and T007 all edit `amazon_listing.html` and must be sequential.
- **Phase 4**: T017, T018 and T019 are three tests in one file — parallel to *write*, sequential to
  commit. Run them as one edit if that is simpler.
- **Phase 7**: T027, T028 and T029 are three different files under `specs/007-product-page-capture/`
  and are fully parallel. T024–T026 are all the #80 issue body and must be one edit.
- **Phase 8**: T033 and T035 alongside T034's long detached run.

## Implementation strategy

**MVP is Phase 2 + Phase 4** — the fixture that can fail, and the two edits that make it pass. That
alone stops every future capture storing each photograph twice, which is the operator-visible half of
this feature.

**Phase 7 is not optional polish.** It is a P1 story, and skipping it leaves #80 §1b telling the next
verifier that a correct capture is a defect — which is exactly the loop this feature exists to break.
If the work has to stop somewhere, stop after Phase 7, not before it.

**Phases 5 and 6 are small and independent**, one console line and one wording correction. Either can
be dropped into a later PR without disturbing anything, though both are cheap enough that there is no
reason to.
