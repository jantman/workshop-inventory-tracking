# Tasks: Find By Any Code Or Note

**Feature**: `specs/009-find-by-code-or-note/` | **Branch**: `issues/62`

**Input**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Format: `[ID] [P?] [Story] Description`

- **[P]** — parallelizable: a different file from every other task running with it, and no dependency on incomplete work.
- **[US1] / [US2] / [US3]** — the user story from `spec.md` the task serves. Setup and Polish tasks carry no story label.

## Path Conventions

Repository root is `/home/jantman/scratch/rm_me/workshop-inventory-tracking`; paths below are relative to it. Source the virtualenv (`venv/`) first, and put pyenv's Python 3.13 ahead of the system Python on `PATH` — the nox sessions pin 3.13 and the system Python is 3.14. Run tests through `nox`, never `pytest` directly.

**Tests are not optional here.** Constitution IV requires a change that alters behaviour to land with tests covering that behaviour, so every story carries its tests as ordinary tasks.

**Two FR namespaces.** Code in `app/` already cites feature 001's FR numbers (FR-009, FR-017, FR-018, FR-032) in docstrings and comments. This feature has its own FR-001…FR-018, and the numbers overlap. Qualify every new citation — `009 FR-002` — so the next reader is not sent to the wrong spec.

**Nothing is stored.** No table, no column, no Alembic revision. If a task seems to need a migration, the design has been misunderstood — stop and re-read [data-model.md](./data-model.md).

---

## Phase 1: Setup

**Purpose**: establish the ground the change stands on, so any later failure belongs to this feature.

- [ ] T001 Create branch `issues/62` from `main`, matching the repo's existing convention (`git log` shows `issues/59` for feature 008)
- [ ] T002 Run `nox -s tests` and record it green, and run `git status --porcelain` and record it empty; both are the baseline every later checkpoint compares against

**Checkpoint**: baseline established. Note that `nox -s lint` is **red at baseline** on this repo (pre-existing flake8 E501) — it is advisory, not a gate, so do not try to fix it.

---

## Phase 2: Foundational (Blocking Prerequisites)

**None.**

The three stories share an issue, not a mechanism. US1 adds a pure module and one classifier rule; US2 adds one disjunct to a query; US3 adds one route. No story reads or writes anything another story creates, and there is no shared scaffolding for them to wait on. A foundational phase would only serialize genuinely independent work.

**Checkpoint**: proceed directly to Phase 3, or to any phase — see [Implementation Strategy](#implementation-strategy).

---

## Phase 3: User Story 1 - A manufacturer's 2D barcode finds the product (Priority: P1) 🎯 MVP

**Goal**: a scan carrying a trade item number in a GS1 element string resolves to exactly the product the bare retail barcode resolves to, through exactly the same validation.

**Independent test**: seed a product carrying GTIN `00012345678905`, scan `0100012345678905` into the header scan box, and land on that product's page rather than on a search.

**Why it stands alone**: it adds one file and one rule inside `app/utils/`. No service, route, template or JavaScript changes, so nothing else in the feature — or the application — can be waiting on it.

### Tests for User Story 1

- [ ] T003 [P] [US1] Create `tests/unit/test_gs1.py` covering `decode_trade_item_number` against every row of the input matrix in [contracts/scan-classification.md](./contracts/scan-classification.md): the three transmission shapes (bare, FNC1, AIM prefix) and their combination; abutted and GS-separated trailing element strings; the non-element-string tail rejections (`EL + 'ABC'`, `EL + ' RES 10K'`, `EL + '\x04'`); wrong digit counts; non-ASCII (Arabic-Indic) digits; other AIs; AI 01 not in first position; and the never-raises set including a non-`str`, which returns `None` rather than raising. Match the house style of `tests/unit/test_gtin.py` — `Test*` classes, fixture-free, one case per parametrize line with an aligned trailing `#` saying why the case exists
- [ ] T004 [P] [US1] In the same file, add the three assertions that pin the extraction/validation seam and are the most likely thing to be got wrong: `decode_trade_item_number('0109506000134353')` returns `'09506000134353'` (bad check digit, **returned anyway**), `decode_trade_item_number('0100000000000000')` returns fourteen zeros (the no-read value, **returned anyway**), and a comment stating that validity is `app/utils/gtin.py`'s alone. If either returns `None`, extraction has started judging and `gtin.py` has stopped being the single source of truth
- [ ] T005 [P] [US1] In `tests/unit/test_scan_router.py`, add a `TestTradeItemElementString` class covering every `classify` row of the contract's before/after table, including the bad-check-digit and all-zero fall-throughs to `FREE_TEXT` and the AIM/FNC1 combinations. Add one **equivalence** test — `classify('0109506000134352')` and `classify('9506000134352')` agree on `kind` and `value` and differ only in `raw` — which is `009 FR-002` stated as behaviour. Do **not** add source-inspection assertions (`inspect.getsource(...).count(...)`): `test_gtin.py` and `test_ecia.py` are behaviour-only and such a test would be the first of its kind in the suite; the single-arm property is a code-review item, recorded in the contract
- [ ] T006 [P] [US1] In `tests/unit/test_scan_router.py`, extend `TestPrecedence` with a case proving rule 1 still beats the new rule, and add a regression parametrize asserting that `'9506000134352'`, `'00012348'`, `'012345678905'`, `'9506000134353'`, `'00000000'`, a `WIT…` code, `'[)>\x1e06\x1dP123\x1e\x04'`, `'B0ABC12345'` and `'M3 standoff'` all classify exactly as they do on `main` today (`009 FR-008`)
- [ ] T007 [P] [US1] In `tests/e2e/test_wedge_scan.py`, add `test_scanning_a_manufacturers_2d_barcode_lands_on_its_product`: seed with `live_server.add_test_products([...])` carrying a GTIN identifier (not the Add Product form — it costs ~3s per product), drive the existing module-level `scan()` helper with `'0100012345678905'`, and `expect(page.locator("#product-description")).to_have_text(...)`. One e2e case only; the grammar is covered exhaustively by the unit suite and a browser adds nothing to it

### Implementation for User Story 1

- [ ] T008 [US1] Create `app/utils/gs1.py` with module constants `_TRADE_ITEM_AI = '01'` and `_TRADE_ITEM_LENGTH = 14`, an ASCII-digit pattern (copy the reasoning in `gtin.py`'s `_ASCII_DIGITS` — `str.isdigit()` accepts Arabic-Indic digits), and one public `decode_trade_item_number(raw: str) -> Optional[str]`. Steps in order: non-`str` → `None`; `raw.strip()`; remove at most one AIM identifier (`]` + one ASCII letter + one ASCII digit); remove at most one leading FNC1 (`\x1d`); require the remainder to open with `01` + exactly 14 ASCII digits; require what follows to be end-of-input, a GS, or an ASCII digit; return the digits verbatim. Module docstring must state: pure (standard library only, no Flask/database/config, like its three siblings); that AI 01 is predefined-length so nothing delimits it; that the returned digits are **unjudged** and `gtin.py` alone decides validity; that only a payload *opening* with AI 01 is read (`009 FR-007`); and that it never raises on anything
- [ ] T009 [US1] In `app/utils/gs1.py`, add a comment at the FNC1-removal step recording **why it is not redundant** with the preceding `strip()`: `'\x1d'.isspace()` is `True`, so a bare leading GS is already gone — the explicit removal exists for the case where an AIM identifier preceded the GS, leaving it interior at the moment `strip()` ran. Without this comment the line reads as dead code and will be deleted
- [ ] T010 [US1] In `app/utils/scan_router.py`, add `gs1` to the `from app.utils import ...` line (currently line 19) and insert the new rule ahead of the existing GTIN rule at line 66, sharing **one** arm: `trade_item = gs1.decode_trade_item_number(scan)` then `gtin_key = gtin.normalize_and_validate(scan if trade_item is None else trade_item)`. Exactly one `normalize_and_validate` call and exactly one `kind=ScanKind.GTIN` construction must remain in the module — that single arm is what makes `009 FR-002` and `009 FR-006` true by construction rather than by test
- [ ] T011 [US1] In `app/utils/scan_router.py`, add a comment at the new rule recording **why it cannot capture a scan that resolves today**: a match needs ≥16 characters and `gtin.ACCEPTED_LENGTHS` is `(8, 12, 13, 14)`, so the candidate sets are disjoint; rules 1 and 2 run first, so an internal code and an ECIA envelope are unreachable. This is the argument that makes the change safe (`009 FR-008`) and it is invisible from reading the code
- [ ] T012 [US1] In `app/utils/scan_router.py`, renumber the module docstring's rule list to five rules (internal → ECIA → element string → GTIN → free text), update the "Rule 4 is not structural" and "Rule 5" comments to "Rule 5"/"Rule 6" wording as appropriate, and note in the docstring that two rules now delegate their whitespace tolerance to a sibling parser rather than one. Keep the existing statement that classification is structural only and performs no database lookup — the new rule does not change that

**Checkpoint**: `nox -s tests` green and the new e2e test passes. Scanning a manufacturer's 2D barcode reaches the product. Shippable on its own.

---

## Phase 4: User Story 2 - What you wrote in the notes is findable (Priority: P2)

**Goal**: the catalogue's free-text search matches a product's notes on the same terms as every other field it searches, and the screen says so.

**Independent test**: seed two products, one with the search term only in its notes and one without it anywhere; search for the term; the first comes back and the second does not.

**Why it stands alone**: one disjunct in an existing `or_()` and one placeholder string. It touches no scan path and no route.

### Tests for User Story 2

- [ ] T013 [P] [US2] In `tests/unit/test_product_search.py`, extend the `catalogue` fixture (line 22) with a product whose `notes` carry a distinctive phrase, then add to `TestTextSearch` (line 128): a phrase held only in notes finds the product; a product with no notes is not returned for it; a term matching product A by description and product B by notes returns **both, once each** (this single case proves `009 FR-011` non-duplication and `009 FR-012` sameness together, and is the one most worth writing); and a notes match still obeys a category, tag or stock filter applied alongside it (`009 FR-013`)
- [ ] T014 [P] [US2] Do **not** write a case-insensitivity test, and record why in a comment beside the notes cases: SQLite's `LIKE` and MariaDB's `utf8mb4_*_ci` collation both fold ASCII case, so the two backends agree and such a test passes whether the code says `like` or `ilike` — it would assert nothing about which. `009 FR-012` is guaranteed by using the identical construct as the sibling clauses, not by a test

### Implementation for User Story 2

- [ ] T015 [US2] In `app/catalog_service.py`, add `Product.notes.like(pattern)` to the `or_(...)` in `search_products` (the block at lines 306–321, beside `Product.manufacturer.like(pattern)` at line 319). Use `.like()`, not `.ilike()` — matching its five siblings is what stops notes and description ever diverging. Update the method's `query` docstring line, which currently says "Matched against description, specifications, manufacturer part number and every recorded identifier value (FR-032)", to include notes and cite `009 FR-010`
- [ ] T016 [P] [US2] In `app/templates/product/search.html`, change the search input's placeholder (line 31) from `description, spec, part number or identifier` so that it names notes (`009 FR-014`). Keep it short enough to remain readable in the `col-md-4` field

**Checkpoint**: `nox -s tests` green. A phrase written in a product's notes finds it, and the box says notes are searched.

---

## Phase 5: User Story 3 - The code on the label is the way back to the product (Priority: P3)

**Goal**: the address formed from a product's printed code reaches that product, while the record-number address stays canonical and unbroken.

**Independent test**: seed a product, read its `internal_code`, request `/products/<code>`, and arrive at that product's page.

**Why it stands alone**: one new route. It reads an identifier that has existed since the product was created.

### Tests for User Story 3

- [ ] T017 [P] [US3] Create `tests/unit/test_product_routes.py` (there is no product-routes unit test file today; `tests/unit/test_routes.py` is the inventory half). Follow `tests/unit/test_scan_routes.py`'s shape — a `service` fixture over `test_storage`, the shared `client` fixture. Cover: a real code returns **302** to `/products/<id>`; the same code lowercased returns 302 to the same place; a well-formed code no product carries returns **404**; a segment that is not a well-formed code returns 404
- [ ] T018 [P] [US3] In the same file, add `TestExistingProductRoutesAreNotShadowed` asserting that `/products`, `/products/new`, `/products/capture`, `/products/reorder`, `/products/categories` and `/products/tags` each still resolve to their own endpoint (assert on `flask.request.url_rule.endpoint` via `app.url_map.bind('localhost').match(path)`, or on the response not being the redirect). Werkzeug ranks argument-free rules above parameterized ones so this holds — but it would fail silently and far from its cause, which is exactly the test worth writing
- [ ] T019 [P] [US3] In `tests/e2e/test_product_crud.py`, add `test_a_product_is_reachable_by_its_printed_code`: seed with `live_server.add_test_products([{'description': '...'}])[0]`, `page.goto(f"{live_server.url}/products/{product.internal_code}")`, and `expect(page.locator("#product-description")).to_have_text(...)`. `add_test_products` returns products whose `identifiers` are eager-loaded by `get_product`, so `internal_code` is readable off the detached instance

### Implementation for User Story 3

- [ ] T020 [US3] In `app/product/routes.py`, add `@bp.route('/products/<product_code>')` → `product_by_code(product_code)`: upper-case the segment, reject a non-code with `ItemNotFoundError`, look the product up with `service.find_product_by_identifier(code, id_type=IdentifierType.INTERNAL.value)`, raise `ItemNotFoundError` when it is `None`, and `redirect(url_for('product.product_detail', product_id=product.id))`. Import `internal_id` from `app.utils` and `IdentifierType` from `app.models`. Keep the handler thin — no ORM query, per Constitution II — and let the existing `ItemNotFoundError` handler render the 404
- [ ] T021 [US3] Write the route's docstring to record the two decisions a reader will otherwise undo: it **redirects** rather than rendering, so `009 FR-015`'s "same content and same actions" is structurally true and `product_detail`'s assembly of purchases, photos and prices is not duplicated; and it upper-cases locally rather than loosening `internal_id.is_internal_id`, because loosening that would make `witabc…` an internal code *to the scanner* and change an existing classification (`009 FR-008`). Note that Crockford's alphabet is uppercase-only, so folding is injective and `009 FR-018` is not at risk

**Checkpoint**: `nox -s tests` green and the new e2e test passes. All three stories complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: make the documentation stop stating the old behaviour, and prove nothing else moved.

- [ ] T022 [P] Update `docs/user-manual.md`: the sentence at line 749 lists what the catalogue search covers ("descriptions, specifications, part numbers and every recorded identifier at once, including internal codes") and must now include notes, agreeing exactly with the placeholder from T016; the "A scan always gets an answer" table at lines 557–566 needs a row for a manufacturer's 2D barcode, described as landing where a scanned retail barcode lands; and a sentence for the code-formed address belongs near the existing labels material. Match the manual's voice — no AI numbers or GS1 jargon
- [ ] T023 [P] Update the "Finding things" section of `docs/product-functionality-gap.md` (lines 93–106): strike through all three paragraphs and mark them *Built — feature 009*, following the treatment features 006 and 008 established in the same file. State what was actually built where it differs from what the paragraph described — in particular that the product address is an **additional** permanent address and the record number stays canonical, which is narrower than "a product's address is derived from its label"
- [ ] T024 Run `nox -s screenshots_headless` then `nox -s screenshots_verify`, and confirm `git status --porcelain` is empty. One template changed (T016), and Constitution IV requires the regeneration — but `tests/e2e/screenshot_config.yaml` defines no product-catalogue screenshot (`search_form.png` and `search_results.png` are the *inventory* advanced search), so **zero changed files is the expected outcome**. A diff under `docs/images/screenshots/` means something unintended changed; investigate rather than committing it
- [ ] T025 Run `nox -s tests` and `nox -s e2e` (give the e2e session a 15-minute tool timeout) and confirm no previously passing test newly fails — check `tests/unit/test_scan_router.py`, `test_gtin.py`, `test_ecia.py`, `test_scan_resolution.py`, `test_scan_routes.py`, `tests/e2e/test_wedge_scan.py` and `tests/e2e/test_ecia_scan.py` specifically. Confirm `git status --porcelain` is empty afterwards
- [ ] T026 Confirm no Alembic revision was created (`git status` shows nothing under `migrations/versions/`) and that `app/models.py`, `app/database.py` and `app/utils/gtin.py` are unmodified — their being untouched is the design's central claim, and a diff in any of them means the change went wider than it should have
- [ ] T027 Check the new and edited files satisfy `flake8`/`black`/`isort` individually. Do **not** run `nox -s lint` as a gate — it is red at baseline on pre-existing E501 violations — and do not reformat existing files, which destroys review signal

**Checkpoint**: ready for PR against `main`.

---

## Dependencies

### Story-level

```
Setup (T001–T002)
   │
   ├──> US1  (T003–T012)  ─┐
   ├──> US2  (T013–T016)  ─┼──> Polish (T022–T027)
   └──> US3  (T017–T021)  ─┘
```

**All three stories are fully independent of one another.** No story reads a file another story creates, and no story's tests exercise another story's code. They can be built in any order, by different people, or in parallel.

### Task-level, within stories

- **US1**: T003–T007 (tests, all different files) ∥ → T008 → T009 → T010 → T011 → T012. T008 must precede T010 (the classifier imports the module). T009, T011 and T012 are comment and docstring work on files already touched, so they are sequential with their predecessors.
- **US2**: T013 ∥ T014 → T015 ∥ T016. T015 and T016 are different files.
- **US3**: T017, T018 (same new file — sequential with each other), T019 (different file) → T020 → T021.
- **Polish**: T022 ∥ T023, then T024, T025, T026, T027 in order (each runs a suite or inspects the resulting tree).

### Parallel opportunities

- **Across stories**: everything after T002. Three people could take US1, US2 and US3 simultaneously with no coordination.
- **US1 tests**: T003/T004 (`test_gs1.py`), T005/T006 (`test_scan_router.py`) and T007 (`test_wedge_scan.py`) are three separate files — three parallel streams. T003 and T004 both write `test_gs1.py`, as do T005 and T006 for `test_scan_router.py`, so those pairs are sequential within their stream.
- **US2**: T013 and T014 are the same file and sequential; T015 and T016 are different files and parallel.
- **US3**: T017/T018 (new unit file) run parallel to T019 (e2e file).
- **Polish**: T022 and T023 are different documents.

---

## Implementation Strategy

### MVP

**User Story 1 alone.** It is the only one of the three where the operator does the right thing, gets an answer that looks like "you don't have this", and may then create a duplicate product for something already on the shelf. Ship T001–T012 plus the parts of T022 and T025 that cover it, and the worst failure mode is closed.

### Suggested order, which is not priority order

The phases are numbered by story priority, as the template requires. If you are building them one at a time, **risk order is a better build order**:

1. **US2 (notes)** — one line of service code, one placeholder. Lowest risk, immediate everyday value, and it warms up the test file.
2. **US3 (the code address)** — one route. Contained, and its only real risk (URL shadowing) is retired by T018.
3. **US1 (the barcode)** — most surface area, and the only story whose change sits on a path that already works. Doing it last means the suite is otherwise green when you make it.

Priority still says US1 matters most; this says US1 is the one you want the calmest environment for. If you can only ship one, ship US1.

### Incremental delivery

Each story is independently shippable and independently revertable. There is no build order that leaves the application in a broken intermediate state, because no story depends on another's code. Merging all three as one PR is reasonable given the total size (~5 production files), but splitting into three PRs costs nothing structurally.
