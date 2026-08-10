---

description: "Task list for the Product Catalog Documentation Overhaul (#53)"
---

# Tasks: Product Catalog Documentation Overhaul

**Input**: Design documents from `/specs/011-catalog-docs-overhaul/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: No test tasks are generated. The specification requests no tests for the
documentation changes, and there is no application behavior to cover — the only code this
feature writes *is* test code (six screenshot-generation tests), which appears below as
implementation, not as tests-for-the-feature.

**Organization**: Tasks are grouped by user story so each can be implemented and validated
independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

Existing repository layout. Documentation under `docs/`, screenshot suite under `tests/e2e/`,
templates under `app/templates/`. No new directories.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture the baselines that FR-012 and SC-010 are measured against. These numbers
cannot be recovered after the work starts.

- [X] T001 Record the unit-test collection baseline by running `nox -s tests` and noting the collected count; expected **1216** per `specs/011-catalog-docs-overhaul/quickstart.md`. If it differs, update the baseline table in that file before proceeding.
- [X] T002 Record the e2e baseline by running `nox -s e2e` (15-minute bash timeout required); expected **459 passed**. Confirm `git status --porcelain` is empty afterwards — this establishes that the tree is clean *before* any screenshot test is added, so a later dirty tree is attributable to this feature.
- [X] T003 [P] Record the screenshot inventory baseline: `find docs/images/screenshots -name '*.png' | wc -l` — expected **12** (1 `readme/`, 11 `user-manual/`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**None.** There is no cross-story infrastructure to build.

This is a deliberate finding, not an omission. The feature touches four independent surfaces
(the manual, the README, the screenshot suite, the spelling of one word), and the only
ordering constraints are between stories rather than beneath them:

- **US4 must run last.** Doing the spelling sweep before the manual rework means editing the
  same prose twice — the rework rewrites most of the lines the sweep would touch.
- **US2's screenshot task consumes a US3 output** (`product_search.png`), so US3 is sequenced
  ahead of US2 despite both being P2.
- **US3's embedding tasks need US1's sections to exist**, so US3's captures can be written any
  time but its embeds come after US1.

The screenshot seed helper is shared across all six captures but is used by nothing outside
US3, so it belongs inside that story's phase rather than here.

**Checkpoint**: Baselines recorded — user story work can begin.

---

## Phase 3: User Story 1 - The catalog reads as a peer of inventory (Priority: P1) 🎯 MVP

**Goal**: The catalog's capabilities become top-level manual sections, the manual reads as two
contiguous halves, and the contents page shows that at a glance.

**Independent Test**: Read the reworked table of contents cold and name the catalog's major
capabilities and the section documenting each, without scrolling into the body. Every contents
link resolves.

**Scope note**: This story does **not** embed screenshots — that is US3, and it keeps US1
deliverable on its own (the manual is usable, if plainer, without pictures). It also does
**not** fix spelling; `## Product Catalogue` headings become `Catalog` here only because the
heading text is being rewritten anyway, and body prose keeps the British spelling until US4.

All tasks in this phase edit `docs/user-manual.md`, so none are parallelizable.

- [X] T004 [US1] Rewrite `## Overview` (currently line 41) in `docs/user-manual.md` to state that the application has two halves — inventory of physical stock, and a catalog of what you bought — and what distinguishes them, carrying forward the framing currently at lines 483–485 (*a product is a kind of thing you buy; an inventory item is a specific piece of stock with a JA ID and a cutting history*). Satisfies FR-005.
- [X] T005 [US1] Move the whole catalog block (currently lines 475–836) in `docs/user-manual.md` to sit after `## Batch Operations` and before `## Data Export`. Do not reorder any inventory section — see `data-model.md` "Movement decision" for why the block moves rather than the inventory sections.
- [X] T006 [US1] Dissolve the `## Product Catalogue` container in `docs/user-manual.md` and give the orphaned intro prose (currently lines 477–485) its own heading, `## The Product Catalog`.
- [X] T007 [US1] Promote eleven `###` subsections to `##` in `docs/user-manual.md`, applying the renames in the `data-model.md` old→new map: *Identifiers* → **Product Identifiers**, *Scanning* → **Scanning Products**, *Labels* → **Printing Product Labels**, *Quantity, and Knowing What to Reorder* → **Stock Levels and Reordering**, *Attachments* → **Product Attachments**, *Finding Things* → **Finding Products**, *Fixing a Misspelled Category or Tag* → **Categories and Tags**, *One Vocabulary for Locations and Vendors* → **Locations and Vendors: One Shared Vocabulary**. *Adding a Product*, *Recording Purchases* and *Capturing an Order When You Place It* keep their titles.
- [X] T008 [US1] Keep `### Distributor Labels` at `###` in `docs/user-manual.md`, nested under `## Scanning Products` — it is a sub-case of scanning, not a peer capability.
- [X] T009 [US1] Split the old *Finding Things* content in `docs/user-manual.md`: move the browse paragraphs (*Products → Categories*, *Products → Tags*) into `## Categories and Tags`, joining the rename rules already there; leave the search prose, the code-as-address note and the filter list in `## Finding Products`. No sentence is deleted.
- [X] T010 [US1] Add reciprocal cross-references in `docs/user-manual.md` between `## Label Printing` (inventory labels) and `## Printing Product Labels` (catalog labels), so a reader who lands on either knows the other exists.
- [X] T011 [US1] Rebuild the table of contents in `docs/user-manual.md` with the four groupings from `data-model.md` ("Getting oriented", "Inventory — tracking physical stock", "Product Catalog — what you bought, what it cost, where it came from", "Across both halves"), covering all 25 `##` sections including `Quick Reference Card`, which the current TOC omits. Satisfies FR-002, FR-003.
- [X] T012 [US1] Verify anchors: run the SC-004 extraction script in `quickstart.md`; expect `broken anchors: none`. Then run `grep -rn "user-manual.md#" --exclude-dir=.git --exclude-dir=venv .` and confirm nothing outside the manual points at a catalog anchor. Satisfies FR-006, FR-007.
- [X] T013 [US1] Verify no guidance was dropped: run the SC-003 phrase loop in `quickstart.md`; every one of the thirteen phrases must report `present`. Then run the two split checks confirming the Categories/Tags browse material and the search material each landed in the right section. Satisfies FR-004.

**Checkpoint**: The manual reads as two halves and every link resolves. US1 is independently deliverable.

---

## Phase 4: User Story 3 - The catalog is pictured (Priority: P2)

**Goal**: Six catalog screenshots, generated by the existing automated suite, embedded in the
reworked manual.

**Independent Test**: Delete the six PNGs, run `nox -s screenshots_headless`, confirm they
reappear identically and pass `nox -s screenshots_verify`.

**Sequenced ahead of US2** (both P2) because US2's FR-017 embeds `product_search.png`, which
this story produces.

Full capture parameters — route, wait target, seed, embed point — are in
[contracts/screenshot-manifest.md](./contracts/screenshot-manifest.md). Every new test carries
**both** `@pytest.mark.screenshot` and `@pytest.mark.e2e`; the marker is already registered in
`pytest.ini`.

T015–T020 all add functions to the same file and so are not parallelizable, though their
content is independent.

- [X] T014 [US3] Add a shared catalog seed helper to `tests/e2e/test_screenshot_generation.py` building the six products in the manifest's seed table via `live_server.add_test_products(...)`. Set ages with `live_server.backdate_product(...)` so at least two products show a backdated `quantity_updated_at` and the flagged one a backdated `stock_status_updated_at` — without this every capture reads *"counted today"*, picturing the age feature at the one value where it looks pointless. Add purchases through `CatalogService(live_server.storage).record_purchase(...)`. Prices must be `Decimal`, never `float` (Principle III).
- [X] T015 [US3] Add `test_screenshot_product_search` to `tests/e2e/test_screenshot_generation.py`: seed, `goto /products`, wait on `#product-table`, capture `user-manual/product_search.png` at 1920×1080 `full_page=True`, hiding `.toast-container`.
- [X] T016 [US3] Add `test_screenshot_product_detail` to `tests/e2e/test_screenshot_generation.py`: seed, open the *Blue thread locker* product, wait on `#stock-card` then `#identifier-list`, capture `user-manual/product_detail.png`. This is the longest page of the six — if it exceeds the 500 KB gate, drop to `full_page=False` at 1920×1080 rather than raising the ceiling.
- [X] T017 [US3] Add `test_screenshot_product_add_form` to `tests/e2e/test_screenshot_generation.py`: seed first (so location/sub-location autocomplete has something to offer), `goto /products/new`, wait on `#product-form`, capture `user-manual/product_add_form.png`.
- [X] T018 [US3] Add `test_screenshot_order_capture` to `tests/e2e/test_screenshot_generation.py`: `goto /products/capture`, wait on `#capture-form`, capture `user-manual/order_capture.png`. Leave `#bookmarklet-http-warning` **visible** — the test server runs over HTTP and the manual devotes a block quote to that exact warning, so hiding it would picture a state the manual then explains.
- [X] T019 [US3] Add `test_screenshot_reorder_list` to `tests/e2e/test_screenshot_generation.py`: seed, `goto /products/reorder`, assert `#reorder-table` is present (not `#nothing-to-reorder`), capture `user-manual/reorder_list.png`. The assertion also fails loudly if the seed ever stops qualifying for the reorder list.
- [X] T020 [US3] Add `test_screenshot_category_tree` to `tests/e2e/test_screenshot_generation.py`: seed, `goto /products/categories`, wait on `#category-tree`, capture `user-manual/category_tree.png`. The seed's `electronics/passives/resistors` path is what makes the three-level nesting — and therefore the "renaming carries everything beneath it" rule — legible.
- [X] T021 [US3] Run `nox -s screenshots_headless` and confirm all 18 screenshots are produced (12 existing + 6 new).
- [X] T022 [US3] Run `nox -s screenshots_verify` and confirm all 18 pass: valid PNG, RGB mode, under 500 KB. Apply the `product_detail.png` fallback from T016 if needed and regenerate.
- [X] T023 [US3] Embed the six screenshots in `docs/user-manual.md`, each with a caption, following the existing `![Alt](images/screenshots/user-manual/name.png)` + italic caption convention: `product_detail.png` → *The Product Catalog*; `product_add_form.png` → *Adding a Product*; `order_capture.png` → *Capturing an Order When You Place It*; `reorder_list.png` → *Stock Levels and Reordering*; `product_search.png` → *Finding Products*; `category_tree.png` → *Categories and Tags*. Depends on T007 having created those sections.
- [X] T024 [US3] Update `docs/images/screenshots/GENERATION_GUIDE.md`: the user-manual list gains the six new entries and the counts go from "User Manual Screenshots (11)" / "**Total:** 12" to (17) / 18.
- [X] T025 [US3] Regenerate `docs/images/screenshots/VERIFICATION.md` from the actual files. It currently claims 8 screenshots dated 2025-12-17 while 12 are on disk — it is rewritten with all 18 and their real sizes and dimensions, not appended to. Satisfies FR-023.
- [X] T026 [US3] Confirm the markers are right: run `nox -s e2e` (15-minute bash timeout) followed by `git status --porcelain`. Empty output proves the six new tests are excluded by `-m "e2e and not screenshot"`. Any PNG or `metadata.json` appearing means a missing `@pytest.mark.screenshot`. Satisfies FR-021, SC-010.

**Checkpoint**: Catalog is pictured, images regenerate from scratch, e2e still leaves the tree clean.

---

## Phase 5: User Story 2 - The README says the application has a catalog (Priority: P2)

**Goal**: A first-time reader of the README alone learns the application catalogs purchased
products, and knows where to read more.

**Independent Test**: Read `README.md` with no other file open and answer "does this track what
I purchased and what it cost?" and "where do I read more?"

- [ ] T027 [US2] Add the product catalog to the Features list in `README.md`, naming its principal capabilities — cataloging what you buy with identifiers and barcodes, scanning to find or create, purchase and order tracking with reorder lists, categories and tags. Match the existing bullet style (bold lead-in, then description). Satisfies FR-015.
- [ ] T028 [US2] Ensure the Documentation section of `README.md` points a reader at the catalog guidance — the User Manual entry gains a mention of the catalog half, or a direct link to `docs/user-manual.md#the-product-catalog`. If an anchor is used, it must match the heading created in T006. Satisfies FR-016.
- [ ] T029 [US2] Embed `docs/images/screenshots/user-manual/product_search.png` in `README.md` with a caption, alongside the existing `readme/inventory_list.png`. Reuse rather than a seventh capture — the README already reuses `user-manual/add_item_form.png` the same way. Depends on T021. Satisfies FR-017.

**Checkpoint**: The front door mentions both halves of the application.

---

## Phase 6: User Story 4 - One spelling, and it stays that way (Priority: P3)

**Goal**: `catalog` everywhere a human reads prose in this repository; `catalogue` preserved
only in the frozen records under `specs/` and `migrations/`.

**Independent Test**: `grep -ric "catalogue" README.md CLAUDE.md docs/ app/ tests/` returns
nothing; the same grep over `specs/` and `migrations/` still returns matches.

**Runs last deliberately.** US1 rewrites most of the manual prose this sweep would otherwise
touch; doing the sweep first means editing the same lines twice.

Exact per-file counts, the rename list and the two traps are in
[contracts/spelling-scope.md](./contracts/spelling-scope.md).

- [ ] T030 [P] [US4] Replace `catalogue` → `catalog` throughout `docs/spec-product-catalog.md` (22 occurrences, all prose).
- [ ] T031 [P] [US4] Replace `catalogue` → `catalog` throughout `docs/product-functionality-gap.md` (5 occurrences, all prose).
- [ ] T032 [P] [US4] Replace the remaining `catalogue` occurrences in `docs/user-manual.md` body prose. Most headings were already rewritten in T007; this catches the sentences.
- [ ] T033 [P] [US4] Fix the two user-visible strings: `app/templates/product/reorder.html:15` ("worked out from what the catalogue already knows") and `app/templates/product/detail.html:29` ("This scan matched a product already in the catalogue"). Confirmed at planning time that no test asserts on either. Satisfies FR-009.
- [ ] T034 [P] [US4] Replace `catalogue` → `catalog` in comments and docstrings under `app/` — 29 Python comments/docstrings plus 4 Jinja comments in `_layout.html`, `_rename_modal.html` and `detail.html`. Satisfies FR-010 for `app/`.
- [ ] T035 [US4] Replace `catalogue` → `catalog` in comments and docstrings under `tests/`. Do this **before** the identifier renames below so the two passes do not collide in the same files.
- [ ] T036 [P] [US4] Rename the pytest fixture `catalogue` → `catalog` in `tests/unit/test_product_search.py` (definition at line 22, 71 references in the file). A missed reference fails immediately with `fixture 'catalogue' not found`.
- [ ] T037 [P] [US4] Rename the pytest fixture `catalogued` → `cataloged` in `tests/unit/test_capture.py` (definition at line 435, 20 references in the file).
- [ ] T038 [P] [US4] Rename the eight test functions listed in `contracts/spelling-scope.md` across `tests/unit/test_scan_resolution.py`, `tests/unit/test_vocabulary.py` (×2), `tests/unit/test_catalog_service.py` (×2), `tests/e2e/test_reorder_view.py`, `tests/e2e/test_product_specifications.py` and `tests/e2e/test_product_crud.py`. **`test_an_uncatalogued_barcode_...` becomes `test_an_uncataloged_barcode_...`** — one `g`, one `e`. A blind substitution produces `uncatalogd`.
- [ ] T039 [US4] Add the standing spelling rule to `CLAUDE.md`: American "catalog", never British "catalogue", **and** name the exclusions — files under `specs/` and Alembic revision docstrings under `migrations/` are frozen records and must not be swept. Without the exclusions, the next contributor running the same grep "fixes" the history. Satisfies FR-014.
- [ ] T040 [US4] Verify the sweep: `grep -ric "catalogue" README.md CLAUDE.md docs/ app/ tests/` returns nothing; `grep -ric "catalogue" specs/ migrations/` still returns matches; `grep -rn "uncatalogd\|uncatalogued" app/ tests/` returns nothing. Satisfies SC-005.
- [ ] T041 [US4] Verify the renames changed no behavior: `nox -s tests` must report **1216 passed** and collect **1216** — a green run alone is insufficient, because a function renamed out of pytest collection passes silently with less in the suite. Then `nox -s e2e` (15-minute timeout) must report **459 passed**. Satisfies FR-012, SC-006.

**Checkpoint**: One spelling, the frozen records intact, and the suites unchanged in size.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T042 Run the full merge gate from `quickstart.md`: `nox -s tests` (1216), `nox -s e2e` (459), `git status --porcelain` empty after both, `nox -s screenshots_headless` (18 regenerated), `nox -s screenshots_verify` (all valid, all under 500 KB).
- [ ] T043 Run the SC-008 regeneration proof: delete the six new PNGs, run `nox -s screenshots_headless`, confirm they reappear with no manual step and pass verification.
- [ ] T044 Run the SC-001 human check: open `docs/user-manual.md` and, from the table of contents alone, name four things the catalog does and the section documenting each, in under 30 seconds. This is the criterion the whole feature exists for and it is not scriptable.
- [ ] T045 Confirm `nox -s lint` produces no findings that did not exist at baseline. The session is red at baseline from pre-existing flake8 E501 and is not a merge gate — the check is that nothing new was added.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies; must run before anything is modified, since T001–T003 capture baselines that cannot be recovered later.
- **Foundational (Phase 2)**: empty — see the phase for why.
- **US1 (Phase 3)**: depends only on Setup. **This is the MVP.**
- **US3 (Phase 4)**: T014–T022 depend only on Setup and can be written alongside US1. T023 (embedding) depends on **T007**, which creates the sections the images go into.
- **US2 (Phase 5)**: T027–T028 depend only on Setup (T028 on **T006** if an anchor is used). T029 depends on **T021**, which produces the PNG.
- **US4 (Phase 6)**: depends on **US1 complete** — T032 sweeps prose that T004–T011 rewrite.
- **Polish (Phase 7)**: depends on all stories.

### Recommended execution order

`Setup → US1 → US3 → US2 → US4 → Polish`

US3 precedes US2 despite equal priority because T029 consumes T021's output. US4 is last by
design, not by priority alone.

### Within each story

- **US1**: strictly sequential — every task edits `docs/user-manual.md`. Structural moves (T005–T009) before the TOC rebuild (T011), because the TOC is written against the final heading set. Verification (T012, T013) last.
- **US3**: T014 (seed helper) before T015–T020 (captures, which use it). T021 (generate) before T022 (verify) before T023 (embed). T024–T025 (inventory docs) after T021, since they record what was actually produced.
- **US4**: T035 (tests/ prose) before T036–T038 (tests/ identifiers) — they touch overlapping files. T040–T041 last.

### Parallel Opportunities

- **T003** with T001/T002 in Setup.
- **US1**: none. One file, sequential edits.
- **US3**: none within the phase — T015–T020 are independent in content but all append to `tests/e2e/test_screenshot_generation.py`, so they serialize on the file.
- **US2**: T027 and T028 touch different regions of `README.md`; safe together but small enough not to matter.
- **US4**: the widest parallelism in the feature — **T030, T031, T032, T033, T034** are five different files with no interdependency, and **T036, T037, T038** are three disjoint file sets. T035 must complete before that second group starts.
- **Across stories**: US3's T014–T022 can proceed while US1 is in flight, since they touch only `tests/` and `docs/images/`.

---

## Parallel Example: User Story 4

```bash
# First wave -- five independent files:
Task: "T030 catalogue -> catalog in docs/spec-product-catalog.md"
Task: "T031 catalogue -> catalog in docs/product-functionality-gap.md"
Task: "T032 catalogue -> catalog in docs/user-manual.md body prose"
Task: "T033 user-visible strings in app/templates/product/{reorder,detail}.html"
Task: "T034 comments and docstrings under app/"

# Then T035 (tests/ prose) alone, then a second wave -- three disjoint file sets:
Task: "T036 rename fixture in tests/unit/test_product_search.py"
Task: "T037 rename fixture in tests/unit/test_capture.py"
Task: "T038 rename the eight test functions"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 Setup (T001–T003) — capture baselines.
2. Phase 3 US1 (T004–T013) — re-level the manual.
3. **STOP and validate**: T012 reports zero broken anchors, T013 reports all thirteen phrases present, and the contents page reads as two halves.

That is a shippable increment. The manual is restructured and correct; it simply has no
catalog pictures yet and still spells the word the British way in body prose.

### Incremental delivery

1. Setup → baselines recorded.
2. **US1** → manual re-levelled → validate → commit. *(MVP)*
3. **US3** → screenshots generated and embedded → validate → commit.
4. **US2** → README updated → validate → commit.
5. **US4** → spelling swept, suites unchanged in size → validate → commit.
6. Polish → full gate.

Each step leaves the repository in a shippable state. Stopping after step 2 delivers the
substance of issue #53's first point; stopping after step 4 delivers three of its four points.

### Notes

- Commit after each story, not each task — the stories are the reviewable units.
- `nox -s e2e` needs a **15-minute** bash timeout (T002, T026, T041). This is constitutional, not advisory.
- Never invoke `pytest` directly; always go through `nox`.
- No fixed-duration waits in any new e2e code (`wait_for_timeout`, `time.sleep`, `networkidle` are prohibited). All six captures wait on a named element — the targets are listed in the manifest.
- `tests/e2e/screenshot_config.yaml` is deliberately **not** touched. It is dead config that nothing reads; see `research.md` Finding 3.
