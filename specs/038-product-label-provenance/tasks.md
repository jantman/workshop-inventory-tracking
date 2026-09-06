---

description: "Task list for feature 038 — product label provenance"
---

# Tasks: Product label provenance — identity, per-unit price, copy count

**Input**: Design documents from `specs/038-product-label-provenance/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/)

**Tests**: Test tasks are **mandatory** here, not optional. Constitution IV: "Changes that alter
behavior MUST land with tests covering that behavior." Every story below therefore carries its own
tests, and each story's tests must pass before the next story begins.

**Organization**: Grouped by user story. US1 and US2 are both P1 and both ship value alone; US3 is
P3 and can be dropped whole without touching the other two.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel — different file, no dependency on an incomplete task
- **[Story]**: US1, US2, US3 per [spec.md](./spec.md)

## Path Conventions

Flask web app, existing layout. Sources under `app/`, tests under `tests/unit/` and `tests/e2e/`.
No new files are created in `app/`.

---

## Phase 1: Setup

**Purpose**: Establish the baseline the change is measured against. No project initialization is
needed — this is a change to an existing, working feature.

- [X] T001 Run `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` and confirm green, so that any later failure is attributable to this feature rather than inherited.
- [X] T002 Capture the current no-provenance PNG bytes as the SC-006 baseline: compose `app/services/product_label.py::compose_product_label` with `description='Blue widget, 10mm'`, `code='WIT0123456789'`, no provenance, on `Sato 2x4`, and save the digest to the scratchpad for comparison in T012.

**Checkpoint**: Baseline recorded, suite green.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Reshape provenance from one string into a list of lines, and re-budget the label's
bands so a second line can exist without shrinking the code band. **This phase deliberately
changes no observable output** — with one provenance line the new arithmetic reduces to the old
arithmetic exactly, so a label composed before and after this phase is identical.

**⚠️ CRITICAL**: US1 and US2 both edit `format_provenance`. Neither can begin until this is done.

- [X] T003 In `app/services/product_label.py`, change `format_provenance(purchase)` to return `List[str]` instead of `Optional[str]` — `[]` when `purchase is None`, otherwise a one-element list holding today's vendor/date/price line. Update the docstring to describe a list of lines.
- [X] T004 In `app/services/product_label.py`, rename the `provenance: Optional[str]` parameter of `compose_product_label` and `_compose_panel` to `provenance_lines: Optional[Sequence[str]]`, importing `Sequence` and `List` from `typing`. Rename, do not widen — per [research.md](./research.md#decision-3), a widened `Sequence[str]` silently accepts a `str` and draws one line per character.
- [X] T005 In `app/services/product_label.py`, rewrite `_draw_provenance` to take a sequence of lines: fit **one** font to the widest line via the existing `_fit_font`, then draw each line into its own `int(height_px * PROVENANCE_BAND)` slice, truncating each with the existing `_truncate`. Return the y coordinate below the last line.
- [X] T006 In `app/services/product_label.py::_compose_panel`, implement the band budget from [data-model.md](./data-model.md#the-labels-vertical-budget): `provenance_height = int(H * PROVENANCE_BAND) * N`; `description_height = int(H * (DESCRIPTION_BAND + PROVENANCE_BAND)) - provenance_height` when `N > 0`, else `int(H * DESCRIPTION_BAND)`; `code_height` is the remainder. Add a comment naming FR-006 — the second line is paid for by the description, never by the code.
- [X] T007 In `app/services/product_label.py`, rename `print_product_label`'s `provenance` parameter to `provenance_lines`, pass it through to `compose_product_label`, and update the TESTING short-circuit log line to report the list. Leave `num_copies` alone — it is already correct.
- [X] T008 In `app/product/routes.py::api_print_product_label`, update the `format_provenance` / `print_product_label` call sites to the new names. Behaviour is unchanged at this point.
- [X] T009 In `tests/unit/test_product_label.py`, update the module-level `compose()` helper to pass `provenance_lines=['Amazon  2026-01-14  $12.34']`, and update every call that overrides `provenance=` (including the `provenance=None` cases) to `provenance_lines=`.
- [X] T010 In `tests/unit/test_product_label.py::TestProvenanceLine`, update the four existing assertions to expect lists rather than strings (`['Amazon  2026-01-14  $12.34']`, `[]`, `['Amazon']`, `['Amazon  $0.10']`). The `ea` suffix arrives in US1, not here.
- [X] T011 In `tests/unit/test_product_label.py`, add a test asserting that `provenance_lines=None` and `provenance_lines=[]` compose to identical bytes, and that a one-line label's barcode starts at the same row as it did with the old single-string parameter (use the existing `first_dense_row` helper).
- [X] T012 Run `nox -s tests`; additionally confirm the no-provenance PNG digest still matches the T002 baseline (SC-006).

**Checkpoint**: Provenance is a list, the band budget is in place, and nothing about a printed label has changed. Both P1 stories can now proceed.

---

## Phase 3: User Story 1 — Read the price on a bag and know what it means (Priority: P1) 🎯 MVP

**Goal**: A printed unit price says it is a unit price.

**Independent test**: Compose a label for a product whose latest purchase has a unit price and read
the provenance text — it shows `$6.50 ea`, not `$6.50`. Delivers value with nothing else built.

- [X] T013 [US1] In `app/services/product_label.py::format_provenance`, change the price fragment to `f"${purchase.unit_price} ea"`. Keep the existing `str()`-on-`Decimal` rendering and the existing `is not None` test so a zero price still prints and no arithmetic touches the value (Constitution III, FR-009).
- [X] T014 [P] [US1] In `tests/unit/test_product_label.py::TestProvenanceLine`, assert `format_provenance(_FakePurchase('Amazon', datetime(2026, 1, 14), Decimal('6.50')))` is `['Amazon  2026-01-14  $6.50 ea']`.
- [X] T015 [P] [US1] In `tests/unit/test_product_label.py::TestProvenanceLine`, assert a zero price prints as `$0.00 ea` (a recorded price, not a missing one) and that a `None` price yields neither a price nor a stray `ea`.
- [X] T016 [P] [US1] In `tests/unit/test_product_label.py::TestProvenanceLine`, extend `test_the_price_never_passes_through_a_float` so it still asserts exact `Decimal` round-tripping now that a suffix is appended — `Decimal('0.10')` renders `$0.10 ea`, never `$0.1 ea`.
- [X] T017 [US1] Run `nox -s tests`.

**Checkpoint**: US1 complete and shippable on its own.

---

## Phase 4: User Story 2 — Identify and re-order a part from the label alone (Priority: P1)

**Goal**: The manufacturer and manufacturer part number reach the label, on their own line, without
the code band giving up any space.

**Independent test**: Compose a label for a product carrying `MEAN WELL` / `IRM-05-5` and confirm
both appear, and that the barcode starts no lower than on the equivalent one-line label.

- [X] T018 [US2] In `app/services/product_label.py::format_provenance`, add `manufacturer: Optional[str] = None` and `part_number: Optional[str] = None` keyword parameters. Build the identity line by joining the non-empty, stripped values with two spaces, and prepend it to the returned list when it is non-empty. Emit no empty string into the list.
- [X] T019 [US2] In `app/services/product_label.py::format_provenance`, ensure the purchase line is built independently of the identity line so that a product with a manufacturer but no purchase still gets provenance (FR-004) — the early `return None` on `purchase is None` must not short-circuit the identity line.
- [X] T020 [US2] In `app/product/routes.py::api_print_product_label`, pass `manufacturer=product.manufacturer` and `part_number=product.manufacturer_part_number` to `format_provenance`. Keep the existing `get_latest_purchase` call and its "not history[-1]" comment intact.
- [X] T021 [P] [US2] In `tests/unit/test_product_label.py::TestProvenanceLine`, add a parametrized test covering all eight present/absent combinations of manufacturer, part number and purchase from [data-model.md](./data-model.md#the-eight-combinations-sc-003), asserting the exact list each produces (SC-003).
- [X] T022 [P] [US2] In `tests/unit/test_product_label.py::TestProvenanceLine`, assert that whitespace-only and empty-string manufacturer or part number are treated as absent — no blank field, no doubled separator, no trailing separator (FR-003).
- [X] T023 [P] [US2] In `tests/unit/test_product_label.py`, add a test parametrized over every entry in `LABEL_TYPES` asserting `first_dense_row` with two provenance lines is **not greater than** with one — the code band did not move down, so it did not shrink (FR-006, SC-004).
- [X] T024 [P] [US2] In `tests/unit/test_product_label.py::TestTruncation`, assert that an implausibly long identity line composes to the stock's exact dimensions and leaves ink in the bottom band — it truncates rather than overflowing or displacing the code (FR-007).
- [X] T025 [P] [US2] In `tests/unit/test_product_routes.py`, add a test that `POST /api/products/<id>/label` for a product with a manufacturer and part number logs/compose-calls with both lines present, using the `TESTING` short-circuit rather than reaching the printer.
- [X] T026 [US2] In `app/templates/product/detail.html`, update the product label modal's `form-text` help (currently "the description, where it came from, and the code") to name the manufacturer and part number as well, so the screen describes the label that is actually printed.
- [X] T027 [US2] Run `nox -s tests`.

**Checkpoint**: US1 + US2 complete. The label content work of issue #141 is done and shippable without US3.

---

## Phase 5: User Story 3 — Print several copies in one go (Priority: P3)

**Goal**: The product label dialog accepts a copy count of 1–99, like the item label dialog.

**Independent test**: Set the count to 5 in the modal, print, and confirm five labels were
requested. Separable — dropping this phase leaves US1 and US2 intact.

- [X] T028 [US3] In `app/product/routes.py::api_print_product_label`, read `label_count` from the JSON body defaulting to `1`; reject non-`int` and `bool` with `"label_count must be a whole number"` and values outside 1–99 with `"label_count must be between 1 and 99"`, both as `400` with `success: false`, before anything is printed. Mirror the messages in `app/main/routes.py` exactly — see [research.md](./research.md#decision-5) for why this is duplicated rather than extracted.
- [X] T029 [US3] In `app/product/routes.py::api_print_product_label`, pass the validated count as `num_copies` to `print_product_label`, include `label_count` in the success payload, and pluralize the success message when the count exceeds 1.
- [X] T030 [P] [US3] In `app/templates/product/detail.html`, add a `<input type="number" id="product-label-count" min="1" max="99" step="1" value="1">` with its label and help text to the product label modal body, below the stock select, matching the item modal's control in `app/static/js/label-printing-modal.js`.
- [X] T031 [US3] In `app/static/js/product-label-modal.js`, read `#product-label-count` in `print()` and include `label_count` in the POST body. Do **not** persist the count to `localStorage` — the stock is remembered, the count is per-job. Depends on T030.
- [X] T032 [P] [US3] In `tests/unit/test_product_routes.py`, add tests for the `label_count` contract in [contracts/product-label-api.md](./contracts/product-label-api.md): accepted at absent, 1 and 99; rejected at 0, 100, `2.5`, `"3"` and `true`; and a rejected request prints nothing.
- [X] T033 [US3] In `tests/e2e/test_label_print.py`, add a test that sets `#product-label-count` to 3 and prints, waiting on `#product-label-alert` for the outcome — the alert is populated only after the POST resolves, so it cannot predate the response (pattern C). No fixed waits, no `networkidle`.
- [X] T034 [US3] Run `nox -s tests`.

**Checkpoint**: All three stories complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T035 (not needed — see note) Regenerate documentation screenshots — `nox -s screenshots_headless` then `nox -s screenshots_verify` — because `app/templates/product/detail.html` changed (Constitution, Development Workflow). Screenshots churn on every run; commit only those whose content actually differs.
- [X] T036 [P] Grep `docs/` and `README.md` for any description of what a product label carries and update it to include the manufacturer, part number and per-unit price marker.
- [X] T037 [P] Verify American spelling in everything touched — `grep -ric "catalogue" README.md docs/ app/ tests/` must return nothing (CLAUDE.md).
- [X] T038 Run the full `nox -s tests` suite and confirm the working tree is clean afterwards apart from intended screenshot changes (Constitution IV).
- [X] T039 Run `nox -s e2e` detached with a 20-minute budget (`nohup ... &` then poll) — it outlasts a 10-minute tool cap and a cold start exceeds 15 minutes.
- [X] T040 Re-read [spec.md](./spec.md)'s Success Criteria and confirm each of SC-001 … SC-006 is covered by a test that would fail if the behaviour regressed.

**T035 note — screenshots were deliberately not regenerated.** The only template change is
inside the product label modal, which is `display: none` until opened and is never opened by
`test_screenshot_product_detail`. The change therefore cannot appear in any committed
screenshot, so a regeneration would have produced font-rasterization churn and nothing else —
which is precisely what `.github/workflows/screenshots.yml` documents as the reason that check
stopped being a gate and became a reminder (issue #77).

**Success criteria coverage (T040):**

| Criterion | Test |
|---|---|
| SC-001 manufacturer and part number readable from the label alone | `test_manufacturer_and_part_number_lead`, `test_the_label_carries_the_manufacturer_and_part_number` |
| SC-002 the price is identifiable as per-unit | `test_the_price_says_it_is_per_unit` |
| SC-003 eight combinations, no blank or doubled separator | `test_every_combination_degrades_gracefully` |
| SC-004 code band no smaller, every stock | `test_a_second_provenance_line_does_not_shrink_the_code_band` |
| SC-005 N copies in one pass | `test_several_copies_print_in_one_pass`, `test_an_accepted_count_reaches_the_printer` |
| SC-006 byte-identical where nothing was gained | `test_the_old_cases_are_unchanged_to_the_pixel`, `test_no_provenance_composes_identically_whether_none_or_empty` |


---

## Dependencies

```
Phase 1 (T001-T002)
   ↓
Phase 2 Foundational (T003-T012)  ← blocks everything
   ↓
   ├─→ Phase 3 US1 (T013-T017)   P1, independently shippable
   │        ↓
   ├─→ Phase 4 US2 (T018-T027)   P1, independently shippable
   │        ↓
   └─→ Phase 5 US3 (T028-T034)   P3, separable — drop whole if unwanted
            ↓
        Phase 6 Polish (T035-T040)
```

Within Phase 2 the ordering is strict: T003 → T004 → T005 → T006 → T007 → T008, all in the same
file, then the test updates T009 → T010 → T011, then T012.

US1 and US2 both edit `format_provenance` and so are sequenced rather than parallel, even though
either could ship without the other. US3 touches different files entirely and could be done first
if the copy count were the priority — it is not.

## Parallel opportunities

- **Phase 3**: T014, T015, T016 are independent assertions in the same test class and can be
  written together.
- **Phase 4**: T021–T025 are five independent tests across two test files.
- **Phase 5**: T030 (template) and T032 (route tests) are independent of each other; T031 depends
  on T030.
- **Phase 6**: T036 and T037 are independent greps.

## Implementation strategy

**MVP is Phase 2 + Phase 3** — the plumbing plus the `ea` suffix. That alone removes the wrong
answer the issue opens with, in three characters.

**The full P1 deliverable is through Phase 4**, which is what issue #141 actually asks for.

**Phase 5 is the issue's own "happy to split it out"** — it is included because it is the same file
and the same trip, and it is last so that dropping it costs nothing already built.
