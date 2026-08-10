# Implementation Plan: Product Catalog Documentation Overhaul

**Branch**: `issues/53` (spec directory `011-catalog-docs-overhaul`) | **Date**: 2026-08-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-catalog-docs-overhaul/spec.md`

## Summary

Four deliverables, one of which is real work and three of which are bounded sweeps.

The real work is **re-levelling the manual** (FR-001–FR-007): eleven of the catalog's twelve
`###` subsections become `##` top-level sections (*Distributor Labels* stays nested, under
*Scanning Products*), the unheaded intro prose gains a twelfth heading, the catalog block
moves down past *Batch Operations* so the manual reads as two contiguous halves, and the
contents page is regrouped to show those halves. The manual goes from 14 `##` sections to 25.
No guidance is dropped; prose moves, splits and is re-titled — the full map is in
[data-model.md](./data-model.md).

The three sweeps are the **spelling fix** (FR-008–FR-014), the **README** (FR-015–FR-017) and
the **catalog screenshots** (FR-018–FR-023). The screenshots are the only part that writes
code: six new tests in the existing `tests/e2e/test_screenshot_generation.py`, seeded through
`live_server.add_test_products()` — which already exists for exactly this purpose — and
captured with the existing `ScreenshotGenerator`.

Phase 0 research settled four things that change the shape of the work; all four are in
[research.md](./research.md), and two of them correct figures carried in the spec:

1. **Only one anchor reference exists** in the entire repository (`docs/user-manual.md:10`,
   the manual's own contents entry). FR-006/FR-007 are therefore a one-line concern, not a
   cross-document link hunt.
2. **FR-011 is 10 renames, not 85.** The 85 identifier occurrences are *references* driven by
   just two pytest fixtures named `catalogue` (71 references in one file, 20 in another) plus
   eight test function names. Ten edits propagate mechanically; the compiler-equivalent here
   is the test suite, which fails loudly on a missed reference. This materially lowers the
   risk recorded against FR-011 in the spec — the recommendation is now to **keep** it.
3. **`tests/e2e/screenshot_config.yaml` is dead.** The generation suite does not read it. It
   declares 20 screenshots of which 9 do not exist, and its `test:` keys name functions that
   do not exist. Adding catalog entries to it would accomplish nothing while implying it
   drives generation.
4. **`docs/images/screenshots/VERIFICATION.md` is already stale** — it reports 8 screenshots
   against 12 on disk, dated 2025-12-17. FR-023 requires correct totals, so this gets fixed
   as part of the work rather than inherited.

Two documents beyond the manual carry the British spelling and are in FR-008's scope:
`docs/spec-product-catalog.md` (22) and `docs/product-functionality-gap.md` (5).

## Technical Context

**Language/Version**: Python 3.13 (nox sessions pin it; system Python is 3.14)

**Primary Dependencies**: Playwright (screenshot capture), Pillow (PNG optimization and
verification), pytest, nox. No new dependency.

**Storage**: MariaDB via the e2e `live_server` fixture. No schema change, no migration.

**Testing**: `nox -s tests` (unit), `nox -s e2e` (excludes `-m screenshot`),
`nox -s screenshots_headless` (generation), `nox -s screenshots_verify` (quality gate).
The `screenshot` marker is already registered in `pytest.ini`; no new marker is needed.

**Target Platform**: Documentation rendered on GitHub and read locally; the application
itself is a LAN-only Flask app.

**Project Type**: Documentation change to an existing web application, plus additions to an
existing e2e screenshot suite.

**Performance Goals**: The six new screenshot tests must not push
`nox -s screenshots_headless` beyond a few minutes. They seed through the service layer
rather than driving forms, which costs milliseconds instead of ~3 seconds per product.
`nox -s e2e` must be unaffected — it excludes these tests.

**Constraints**: Every generated PNG under 500 KB, RGB mode, valid PNG
(`nox -s screenshots_verify`). Running any standard test session must leave the working tree
clean. No fixed-duration waits in any new e2e code.

**Scale/Scope**: One manual (1,817 lines → ~1,850), one README, one `CLAUDE.md`, two other
docs, six new screenshots, six new tests, ten identifier renames, ~70 prose spelling edits.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Verdict |
|---|---|---|
| **I. Simplicity First** | The temptation here is to make screenshot generation config-driven by reviving `screenshot_config.yaml`. Research shows that config is already dead and lying. The plan extends the existing hardcoded test file with six functions in the established shape, and adds no abstraction. Seeding reuses `add_test_products()` rather than adding a fixture layer. | **PASS** |
| **II. Layered Architecture Boundaries** | Screenshot seeding goes through `CatalogService` (the services layer), which is what `add_test_products()` already does. No route, no raw SQL, no ORM query added anywhere. `backdate_product()` writes one column directly, but it already exists and is already justified in its own docstring — this plan uses it, it does not extend it. | **PASS** |
| **III. Exact Numerics** | No measurement code changes. Seeded purchase prices must be `Decimal`, matching every existing fixture. | **PASS** (constraint recorded) |
| **IV. Test Discipline Through Nox** | Three binding rules. (a) New screenshot tests carry `@pytest.mark.screenshot` + `@pytest.mark.e2e`, so `-m "e2e and not screenshot"` excludes them and an e2e run leaves the tree clean. (b) No `wait_for_timeout`, `time.sleep` or `networkidle` — each capture waits on a named element, listed per-screenshot in the manifest. (c) Run through nox, never bare pytest. Marker already registered. | **PASS** |
| **V. MariaDB Is the Source of Truth** | No schema change, no migration, no Google Sheets involvement. | **PASS** (N/A) |
| **VI. Item Lifecycle and History Invariants** | No inventory item is created, shortened or deactivated by this feature. Catalog products are a separate table with no JA ID. | **PASS** (N/A) |

**Post-Phase-1 re-check**: still PASS. The Phase 1 design added no abstraction — the
screenshot manifest is a documentation artifact describing six test functions, not a runtime
config. The one judgment call surfaced by the design is recorded in Complexity Tracking below
and is a *removal*, not an addition.

## Project Structure

### Documentation (this feature)

```text
specs/011-catalog-docs-overhaul/
├── plan.md                          # This file
├── spec.md                          # Feature specification
├── research.md                      # Phase 0: five findings, with measurements
├── data-model.md                    # Phase 1: section inventory + old→new heading map
├── quickstart.md                    # Phase 1: how to validate every FR
├── checklists/
│   └── requirements.md              # Spec quality checklist (from /speckit-specify)
├── contracts/
│   ├── screenshot-manifest.md       # The six captures: page, seed, wait, embed target
│   └── spelling-scope.md            # Exact in/out scope, measured, with the rename list
└── tasks.md                         # Phase 2 (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
docs/
├── user-manual.md                   # REWRITTEN: catalog re-levelled to ## and moved down
├── spec-product-catalog.md          # spelling only (22 occurrences)
├── product-functionality-gap.md     # spelling only (5 occurrences)
└── images/screenshots/
    ├── GENERATION_GUIDE.md          # counts updated: 12 → 18
    ├── VERIFICATION.md              # regenerated (already stale: says 8, disk has 12)
    ├── metadata.json                # regenerated by the suite
    └── user-manual/
        ├── product_search.png       # NEW — also embedded in README
        ├── product_detail.png       # NEW
        ├── product_add_form.png     # NEW
        ├── order_capture.png        # NEW
        ├── reorder_list.png         # NEW
        └── category_tree.png        # NEW

README.md                            # catalog in Features, doc link, one screenshot
CLAUDE.md                            # standing spelling rule + its exclusions

tests/e2e/
└── test_screenshot_generation.py    # +6 test functions, +1 seeding helper

app/templates/product/
├── reorder.html                     # user-visible "catalogue" → "catalog"
└── detail.html                      # user-visible "catalogue" → "catalog"

app/**, tests/**                     # comments/docstrings (~70) + 10 identifier renames
```

**Structure Decision**: No new files outside the spec directory except six PNGs. The
screenshot tests extend `tests/e2e/test_screenshot_generation.py` in place rather than
forming a `test_screenshot_catalog.py`, because `nox -s screenshots` selects by path
(`tests/e2e/test_screenshot_generation.py`) — a new file would silently not be generated
unless the noxfile changed too. Keeping one file keeps the noxfile untouched.

## Complexity Tracking

No constitutional violations require justification. One judgment call is recorded here
because it is a deliberate decision not to act:

| Item | Decision | Reasoning |
|---|---|---|
| `tests/e2e/screenshot_config.yaml` is dead config that already misdescribes the suite, and this feature makes it more wrong (6 more real screenshots it will not list) | **Leave it. Do not extend it, do not delete it.** Record the finding in research.md and flag it as deferred. | Extending it is worse than useless — it would imply the YAML drives generation when nothing reads it. Deleting it is the constitutionally-preferred outcome under Principle I, but `tests/unit/test_screenshot_infrastructure.py` exercises the loader against it, so deletion means removing a loader module and its unit tests. That is a cleanup with its own reasoning, not a documentation overhaul, and folding it in here would hide it inside a docs diff. |
