---

description: "Task list for feature implementation"
---

# Tasks: A Captured Barcode Becomes a Scannable Identifier

**Input**: Design documents from `/specs/016-promote-captured-gtin/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/README.md](./contracts/README.md), [quickstart.md](./quickstart.md)

**Tests**: Test tasks are **included and required**, not optional. Constitution Principle IV:
"Changes that alter behavior MUST land with tests covering that behavior." The classification matrix
belongs in the unit suite, which runs in under a second; E2E carries only the two claims unit tests
cannot make — that the operator is told, and that the barcode then scans.

**Organization**: Tasks are grouped by user story so each can be implemented, tested and shipped on
its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are in every task

## Path Conventions

Flask web application, server-rendered. This feature lives in `app/catalog_service.py`,
`app/models.py`, `app/product/routes.py` and their tests. **No migration, no template, no CSS, no
JavaScript.** If a task has you editing `migrations/`, `app/templates/` or `app/static/`, stop and
re-read [plan.md](./plan.md) — the schema and the pages already hold everything this writes.

---

## Phase 1: Setup

**Purpose**: Nothing to scaffold. The feature adds no dependency, no module and no configuration.

- [X] T001 Confirm work is on feature branch `issues/93` (cut during `/speckit-specify`), not `main` — constitution: non-trivial code changes go through a branch and a PR

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The two pieces every story needs — knowing which rows are barcode-named, and knowing
which rows a capture actually added.

**⚠️ No user story work can begin until this phase is complete.**

- [X] T002 Add `BARCODE_ROW_NAMES` (frozenset of `UPC`, `EAN`, `GTIN`, `ISBN`, `GTIN-13`, `UPC-A`) and `_is_barcode_row_name(name)` at module level in `app/catalog_service.py`, beside the existing `_clean`/`_corroborates` helpers. Fold with `' '.join(name.split()).upper()` and compare the **whole** name — `Manufacturer UPC` is not a `UPC` row (FR-001, [research.md](./research.md) §5)
- [X] T003 Change `CatalogService.merge_specifications` in `app/catalog_service.py` to return `List[Dict[str, str]]` — the validated entries it appended, in order — instead of the count. Update the docstring's `Returns:` block and the `logger.info` line to use `len(added)`. This is the carrier for FR-003; see [contracts/README.md](./contracts/README.md)
- [X] T004 Update the two assertions that consume that return value in `tests/unit/test_capture.py` (around lines 1162 and 1208) from comparing a number to comparing `len(...)`, and rename `test_it_returns_the_number_it_added` to match what it now returns
- [X] T005 [P] Add unit tests for the fold in `tests/unit/test_capture.py`: all six names promote-eligible; `upc`, `  UPC  `, `Upc` fold to the same thing; `Manufacturer UPC`, `UPC Code` and `Item UPC` do not match; a name that is `None` or empty does not match

**Checkpoint**: `nox -s tests` green. Nothing has changed behavior yet — a capture still promotes nothing.

---

## Phase 3: User Story 1 - A captured barcode is scannable off the box (Priority: P1) 🎯 MVP

**Goal**: A capture whose product information carries a valid barcode leaves the product findable by
scanning that barcode, and the confirmation page says so.

**Independent Test**: Capture the fixture listing, open the product, see the `GTIN` in the
Identifiers card, then scan that barcode and land on the product.

- [X] T006 [US1] Add `CatalogService._promote_barcode_rows(product_id, added)` to `app/catalog_service.py` and call it from `_apply_listing` with `merge_specifications`' return value. Per entry: skip unless `_is_barcode_row_name(name)`; `key = gtin_utils.normalize_and_validate(value)`; skip and log when `None`; otherwise `self.add_identifier(product_id, IdentifierType.GTIN.value, key)`. Call the **public** `add_identifier` — `_apply_listing` runs outside any open session. **No `override` parameter anywhere** (FR-002, FR-003, FR-004)
- [X] T007 [P] [US1] Add the `CapturedBarcode` dataclass to `app/models.py` beside `CaptureAssessment`, with `row_name`, `value`, `outcome`, `holder_id`, `holder_description` — plain values only, no ORM rows ([data-model.md](./data-model.md))
- [X] T008 [US1] Add the read-only `CatalogService.describe_captured_barcodes(product_id, listing)` to `app/catalog_service.py`, returning `List[CapturedBarcode]` in listing order, deduplicated by normalized key. Implement the `recorded` and `not_examined` outcomes now (`taken` and `unusable` arrive in US3 and US2). Comment the inference that makes `not_examined` sound: a valid barcode no product holds can only be a row the merge dropped, because every added row was either promoted or collided (FR-009, FR-010, [research.md](./research.md) §4)
- [X] T009 [US1] Add `_barcode_tally(notes)` to `app/product/routes.py` next to `_image_tally`, following its rule — one string, everything that did not land is named. Sentences per [contracts/README.md](./contracts/README.md)
- [X] T010 [US1] Wire it into `product_capture` in `app/product/routes.py`: after the `Captured.` flash and **before** the image block, call `describe_captured_barcodes(purchase.product_id, listing)` when `listing is not None` and flash the tally — `'success'` when every note is `recorded`, `'warning'` otherwise. Nothing when the list is empty (FR-013)
- [X] T011 [US1] Unit tests in `tests/unit/test_capture.py`: a valid `UPC` row promotes to a `GTIN` holding the 14-digit key and the row is *also* still a specification (FR-005); each of the other five names promotes the same way; equivalent `UPC`/`EAN` forms yield one identifier and one report entry; capturing the same listing twice yields one identifier, no error, and `recorded` both times (FR-009a); a product that already lists a `UPC` row gets **no** identifier and a `not_examined` note (FR-003); a listing with no barcode-named row returns an empty report and is otherwise byte-for-byte today's behavior (FR-013)
- [X] T012 [P] [US1] Add a `UPC` row with value `012345678905` to the tech-spec table in `tests/e2e/fixtures/amazon_listing.html`. That is the same constant `tests/e2e/test_wedge_scan.py` already calls `VALID_UPC_A`, whose 14-digit key is `VALID_GTIN_KEY = "00012345678905"` — reuse both rather than inventing a barcode
- [X] T013 [US1] E2E in `tests/e2e/test_product_page_capture.py`: capture the fixture listing, confirm it, assert the confirmation page's `.alert` contains the key, open the product, assert `#identifier-list` contains `GTIN` and the key, then scan the raw UPC through the global scan input (copy the `scan()` helper's shape from `tests/e2e/test_wedge_scan.py`) and assert you land on that product. Wait on `expect(...)` only — no `wait_for_timeout`, no `networkidle`
- [X] T014 [US1] Run `venv/bin/nox -s tests` (with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`) and fix what it says

**Checkpoint**: US1 is the whole point of issue #93 and stands alone. A captured barcode now scans.

---

## Phase 4: User Story 2 - A wrong barcode is never recorded unattended (Priority: P2)

**Goal**: A barcode-named row whose value is not a valid barcode records nothing, keeps its
specification row, and says why.

**Independent Test**: Capture with one digit of the UPC altered; no identifier exists, the row does,
and the page says it was not recorded.

**Note**: the *refusal* already works after T006 — `normalize_and_validate` returns `None` and the row
is skipped. What this story adds is the report branch and the coverage that proves the refusal is not
accidental.

- [X] T015 [US2] Add the `unusable` outcome to `describe_captured_barcodes` in `app/catalog_service.py` (tested **first**, before `recorded`: a value that is not a valid barcode cannot be held by anyone) and its sentence to `_barcode_tally` in `app/product/routes.py`. The note carries the raw value, since there is no key to name
- [X] T016 [US2] Unit tests in `tests/unit/test_capture.py`, one per refusal: bad check digit; all zeros; a value that is not all digits; an empty value; an ISBN-10 (ten digits, may end `X`) under an `ISBN` row, while an ISBN-13 promotes; two space-separated codes in one value. Each asserts **no identifier**, the specification row present, and — the one that would catch the worst regression — that no `ProductIdentifier` anywhere has `validation_overridden=True` (FR-004). Add one test that a refused row leaves the purchase, the other specification rows and the description intact (FR-011)
- [X] T017 [US2] E2E in `tests/e2e/test_product_page_capture.py`: capture a listing whose UPC has a corrupted check digit (serve a copy of the fixture with the digit altered, or alter it in the served markup), then assert the product's specification list contains the value, `#identifier-list` contains no `GTIN`, and the confirmation page said it was not recorded. Establish `#identifier-list` with a positive `expect` **before** the negative assertion (`CLAUDE.md`)
- [X] T018 [US2] Run `venv/bin/nox -s tests`

**Checkpoint**: US1 and US2 both hold. The feature records what it should and refuses what it should.

---

## Phase 5: User Story 3 - A barcode another product already holds is left alone (Priority: P3)

**Goal**: A collision writes nothing, moves nothing, and is reported with the name of the product
that holds the barcode.

**Independent Test**: Give a product a `GTIN`, capture a different listing carrying it, and confirm
the first product still holds it, the second has none, and the page says which product does.

- [X] T019 [US3] Catch `DuplicateItemError` (and `ValidationError`, belt and braces) per row in `_promote_barcode_rows` in `app/catalog_service.py`: log the colliding product id from `e.item_id` and continue to the next row. Neither may propagate — the purchase is already written and FR-011 forbids failing the capture. Do **not** add a pre-check for the same-product case: `add_identifier` already returns the existing row, which is FR-007
- [X] T020 [US3] Add the `taken` outcome to `describe_captured_barcodes` in `app/catalog_service.py` — `find_product_by_identifier(key, id_type='GTIN')` returns the holder, so fill `holder_id` and `holder_description` from it — and its sentence to `_barcode_tally` in `app/product/routes.py`, naming that product
- [X] T021 [US3] Unit tests in `tests/unit/test_capture.py`: a barcode held by another product leaves both products exactly as they were, keeps the captured row as a specification, and reports `taken` with the holder's id and description; the same barcode on the *same* product is a silent no-op with no duplicate row and no error (FR-006, FR-007)
- [X] T022 [US3] E2E in `tests/e2e/test_product_page_capture.py`: create a product carrying `00012345678905` as a `GTIN` through the product form (`create_product(..., identifier_type='GTIN', ...)`, as `tests/e2e/test_wedge_scan.py` does), capture the fixture listing onto a different product, and assert the confirmation page names the holding product and the captured product's `#identifier-list` has no `GTIN`

**Checkpoint**: All three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T023 [P] Document the behavior in `docs/user-manual.md`, in the capture section after the "repeat capture" paragraph (around line 945): a listing that publishes a UPC makes the product scannable by it; a value that fails its check digit stays a specification and is never stored as an identifier; a barcode another product holds is left alone and named; and the row stays in the specification list either way. Keep it to a short paragraph in the manual's voice
- [X] T024 Run `venv/bin/nox -s tests` — full unit suite green
- [X] T025 Run `venv/bin/nox -s e2e`. **The Bash tool caps at 10 minutes and this suite needs ~8–15**, so run it detached (background/`nohup`) and poll, rather than in the foreground
- [X] T026 Confirm `git status` is clean after the E2E run, and that the diff touches no file under `migrations/`, `app/templates/` or `app/static/` — no screenshot regeneration is expected or wanted for this feature
- [ ] T027 Walk [quickstart.md](./quickstart.md) "By hand" once against a scratch database. **Read step 2's warning first**: `B01N4OSKWE` already carries a `UPC` specification row, so re-capturing it correctly reports `not examined` and creates nothing — that is the rule firing, not a bug
- [ ] T028 Open the pull request from `issues/93`, noting the spec amendment made during planning ([research.md](./research.md) §3) so a reviewer does not have to rediscover why the report is state-shaped

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001)**: no dependencies
- **Foundational (T002–T005)**: blocks every story. T003 in particular — nothing can be promoted until the merge reports what it added
- **US1 (T006–T014)**: after Foundational. Delivers the feature
- **US2 (T015–T018)**: after US1, because it extends `describe_captured_barcodes` and `_barcode_tally`, which US1 creates
- **US3 (T019–T022)**: after US1, same reason. Independent of US2
- **Polish (T023–T028)**: after the stories you intend to ship

### Within Each Story

Service before route before tests, except where a test is in a file nothing else touches.

### Parallel Opportunities

This is a small feature and most of it lands in two files, so honest answer: **there is very little
parallelism, and marking same-file tasks `[P]` would only produce conflicts.** What genuinely can run
at the same time:

- **T005** — a test file no implementation task is editing at that moment
- **T007** — `app/models.py`, which nothing else in US1 touches
- **T012** — the E2E fixture, disjoint from all Python
- **T023** — documentation, disjoint from everything

US2 and US3 both edit `describe_captured_barcodes` and `_barcode_tally`, so they are sequential with
respect to each other even though their *stories* are independent.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. T001–T005 — foundational
2. T006–T014 — promotion, report, route, tests
3. **STOP and VALIDATE**: capture the fixture listing, scan the barcode, land on the product
4. That alone closes what issue #93 reported

### Incremental Delivery

1. Foundational → the merge reports what it added; no behavior change yet
2. US1 → a captured barcode scans (MVP)
3. US2 → a wrong barcode is provably never stored
4. US3 → a contested barcode is left alone and reported
5. Polish → manual, full suites, by-hand pass, PR

---

## Notes

- `[P]` = different files, no dependency on an incomplete task
- Commit after each task or logical group
- **No migration, no template, no JavaScript.** If any appears in the diff, the plan has been misread
- **There is no override path, and adding one is a spec violation** (FR-004). If a task tempts you toward `override=True`, re-read issue #93: nobody typed the value, so nobody would see the prompt
- Reuse `app/utils/gtin.py` as it is (FR-002). A second check-digit implementation is the one thing the issue names explicitly
- E2E waiting rules are not style: `CLAUDE.md` and Principle IV. Both pages here are server-rendered, so `expect()` on the flash text and on `#identifier-list` is the whole wait
