# Implementation Plan: Stock Fit Search

**Branch**: `issues/100` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/027-stock-fit-search/spec.md`

## Summary

Stock search stops comparing a request's Length to a record's Length and starts asking
whether the piece the operator needs can be **cut out of** the piece on the shelf. Every
inventory row is reduced at read time to one of two solids — a box or a cylinder — and the
requested piece is tested against it in every orientation, across shapes. A 0.5 × 4 × 3 bar
answers a request for 0.5 × 3 × 4; a 3" square bar and a 6" cube both answer a request for a
2" round.

That is one new pure module, one new service method, one new page, and one optional column on
the results table three pages already share. Nothing is persisted, no column is added, and
there is no migration — the four dimension columns the fit test reads already exist and are
already nullable.

The work has three parts that can be built and proved in order: the geometry
([contracts/fit-rules.md](./contracts/fit-rules.md), and where nearly all the tests go), the
service and route that feed it ([contracts/find-stock-api.md](./contracts/find-stock-api.md)),
and the page that reuses the existing table to show it.

Fifteen decisions sit behind this, each recorded with what in the code settled it — see
[research.md](./research.md). Three of them are worth reading before any code is written:
**D4** (compare squares, never take a square root, because Principle III bars `float` from
comparisons), **D6** (what "closest fit" is actually measured as, which is not the literal
reading of FR-019), and **D15** (a stated narrowing of "active by default" to "active
always").

## Technical Context

**Language/Version**: Python 3.13 (the nox sessions pin it; put it on `PATH` via pyenv)

**Primary Dependencies**: Flask 3.1.x (app-factory), SQLAlchemy 2.0.x (legacy `Query` style),
Jinja2 + Bootstrap 5.3.2, vanilla ES6 modules — no build step, no frontend framework. **No new
dependency**; nothing is added to `requirements.txt`. The only import this feature needs that
the code does not already use is `decimal`, which is everywhere already.

**Storage**: MariaDB via PyMySQL in production, SQLite through the same `Storage` ABC in unit
tests. **No schema change and no Alembic revision** (D12) — `length`, `width`, `thickness` and
`wall_thickness` are already `Numeric(10, 4), nullable=True` (`app/database.py:37-40`) and
nothing new is written.

**Testing**: `nox -s tests` (pytest, network blocked), `nox -s e2e` (Playwright,
`-m "e2e and not screenshot"`, 15-minute tool timeout, run detached — the tool clamps at 10
minutes and the suite runs about 13m 45s warm), `nox -s screenshots_headless` +
`screenshots_verify`. No new pytest marker.

**Target Platform**: Linux, home LAN, single trusted user, no authentication

**Project Type**: Server-rendered Flask web application

**Performance Goals**: SC-005 asks for results within two seconds. Nothing about this design
is expected to approach that: the query is one indexed `active` + `material IN (…)` filter,
and the per-candidate work is at most five evaluations of a function doing a dozen `Decimal`
comparisons (fit-rules §5). **No index, cache or batching is added** — Principle I requires a
measurement first, and the plain version is what there is to measure (D5).

**Constraints**: `Decimal` only, never `float`, including in comparison — which is why the
geometry compares squared quantities rather than taking a square root (D4, Principle III).
E2E tests wait on observable state, never elapsed time (Principle IV). Touching
`app/templates/**` and `app/static/js/**` obliges regenerating documentation screenshots in
the same change (Development Workflow). The existing advanced search and its four e2e files
must not move (FR-026).

**Scale/Scope**: One user, one workshop. Two new source files, one new template, one new
front-end module, four changed files, and the tests, screenshots and manual section that
follow them.

## Constitution Check

*GATE: checked before Phase 0 and re-checked after Phase 1 design. Both passes recorded.*

| Principle | Assessment | Verdict |
|---|---|---|
| **I. Simplicity First** | Two envelope kinds and four fit rules, which is the smallest model that satisfies FR-006 in both directions — a bounding-box-only model would return a Ø2" bar for a 2"×2" square request (D2). No new dependency. No cache, no index, no pre-filter (D5). One deliberate expansion is tracked below. Two things that look like extras are not: the crosswise cylinder rule (F4) is required by FR-006, not optional; and `show_fit_column` is a parameter with a real call site today, on a macro already parameterized three other ways. | **Pass, with one tracked justification** |
| **II. Layered Architecture** | Geometry is a pure module in `app/utils/`, the home `scan_router.py`, `gtin.py` and `ecia.py` already establish for pure algorithms (D1). Business logic and the single query live in `InventoryService.find_stock()`. The routes parse, call, and jsonify — no SQL, no ORM. No new layer, no repository, no DTO tier. | **Pass** |
| **III. Exact Numerics** | `Decimal` throughout. The rules compare **squares** rather than taking a square root, so no rounding step enters a comparison (D4). `PI` appears in exactly one place — the second term of the sort key — and never in a figure shown to the operator; the displayed comparison is exact subtraction (fit-rules §6). The constant is the one `Dimensions.volume()` already uses. | **Pass** |
| **IV. Test Discipline** | Everything through nox. Nearly all coverage is in the sub-second unit suite because the geometry is pure and fixture-free. The e2e test's waits are named per action in [quickstart.md](./quickstart.md), all `expect()`-based; no `wait_for_timeout`, no unobservable condition. No new marker. Screenshots stay out of the e2e session and are regenerated by their own. | **Pass** |
| **V. MariaDB Is the Source of Truth** | No schema change, no migration, no `create_all` outside fixtures. Nothing to downgrade. Google Sheets is not touched. | **Pass** |
| **VI. Item Lifecycle and History Invariants** | Read-only feature: no row is added, deactivated, shortened or re-parented. The query filters to `active == True`, which is this principle's own rule for anything presenting current inventory (D15). | **Pass** |
| **Operating Context** | No authentication, roles or hardening added. The request validation exists because a zero-length request produces nonsense results, not because input might be hostile — the reason the constitution permits validation. | **Pass** |

**Post-Phase-1 re-check**: unchanged. Phase 1 added no dependency, no layer and no persistence.
The two places it could have failed the gate were both caught and closed in design rather than
in review: the square root that Principle III would have barred (D4), and the second rule table
that Principle I would have called duplication (D3, and Complexity Tracking below).

## Project Structure

### Documentation (this feature)

```text
specs/027-stock-fit-search/
├── plan.md              # This file
├── research.md          # Phase 0 — the fifteen decisions
├── data-model.md        # Phase 1 — the types, and every path touched
├── quickstart.md        # Phase 1 — how to run it and how to prove it
├── contracts/
│   ├── fit-rules.md     #   the normative geometry: envelopes, four rules, ordering
│   └── find-stock-api.md#   the two routes, the payloads, the shared-table keys
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 — created by /speckit-tasks, not by this command
```

### Source Code (repository root)

```text
app/
├── utils/
│   └── fit.py                           # NEW — envelopes, the four fit rules, the sort
│                                        #   key. Pure Decimal; imports only models enums
├── mariadb_inventory_service.py         # CHANGED — find_stock(); one query, active +
│                                        #   material IN descendants. search_active_items
│                                        #   is NOT touched (FR-026)
├── main/
│   └── routes.py                        # CHANGED — GET /inventory/find-stock and
│                                        #   POST /api/inventory/find-stock; thin
├── templates/
│   ├── base.html                        # CHANGED — one nav entry beside "Search Items"
│   └── inventory/
│       ├── find-stock.html              # NEW — the form; calls the shared table macro
│       │                                #   with show_fit_column=True
│       └── _item_table.html             # CHANGED — one optional column, default off
└── static/js/
    ├── inventory-find-stock.js          # NEW — submit, fetch, setItems, counters
    └── components/
        └── inventory-table.js           # CHANGED — showFitColumn, one <td>, one
                                         #   getSortValue case

tests/
├── unit/
│   ├── test_fit.py                      # NEW — the geometry, enumerated; and the
│   │                                    #   taxonomy-agreement test (D3)
│   ├── test_mariadb_inventory_service.py# CHANGED — ordering, counters, material, active
│   └── test_routes.py                   # CHANGED — the six 400s, the success payload
└── e2e/
    ├── test_find_stock.py               # NEW — one pass per user story, plus the
    │                                    #   FR-028 no-regression check on list/search
    ├── pages/find_stock_page.py         # NEW — reuses InventoryTableMixin
    └── screenshot_config.yaml           # CHANGED — find_stock_form, beside search_form

docs/
├── user-manual.md                       # CHANGED — a section for the new search
└── images/screenshots/                  # CHANGED — regenerated (D14)
```

**Structure Decision**: The existing layout, unchanged. The one genuinely new thing is
`app/utils/fit.py`, placed by the precedent of the pure algorithm modules already in that
directory (D1). Everything else extends a file that already does the same job for the
advanced search or the inventory list.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| A second (type, shape) table — `app/utils/fit.py` alongside `app/taxonomy.py` | The two answer different questions. Taxonomy states *which fields a record must contain*; fit states *what solid those fields describe*. The field list does not determine the solid: `Plate`/`Square` and `Bar`/`Square` both come from the taxonomy table, require different fields, and yield differently-shaped boxes. | *Deriving the envelope from taxonomy's required-fields list alone* fails on the facts above (D3). *Merging the geometry into `taxonomy.py`* would make one module answer two questions — which is how `specs/012-round-plate-dimensions/` found three rule tables that disagreed. The mitigation is a unit test that walks every combination taxonomy declares and asserts `fit.py` reads exactly the fields taxonomy requires or declares the combination non-evaluable. Two tables checked mechanically against each other beat one table serving two purposes. |
