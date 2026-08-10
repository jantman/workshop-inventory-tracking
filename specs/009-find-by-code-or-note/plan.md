# Implementation Plan: Find By Any Code Or Note

**Branch**: `issues/62` | **Date**: 2026-08-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-find-by-code-or-note/spec.md`

## Summary

Three unrelated holes in "find the thing I'm holding", closed by four small changes to existing read paths and one new pure module.

1. **A manufacturer's 2D barcode resolves.** A new `app/utils/gs1.py` recognizes a GS1 element string opening with application identifier `01` and hands the 14 digits it carries — verbatim and unjudged — to the classifier's **existing** GTIN arm. From that point the scan *is* a barcode scan: same validation, same lookup, same three outcomes, no new scan kind, no service change, no route change, no template change.
2. **Notes are searched.** One disjunct added to the `or_(...)` already in `CatalogService.search_products`, plus the search box's stated coverage and the user manual's matching sentence.
3. **The printed code is an address.** One new route, `/products/<product_code>`, that validates the code, looks it up, and redirects to the canonical record-number URL.

Nothing is stored. No table, no column, no Alembic revision. The whole feature reads data the catalogue already holds.

## Technical Context

**Language/Version**: Python 3.13 (pinned by the nox sessions; the system Python is 3.14)

**Primary Dependencies**: Flask 3.1.x (app-factory), SQLAlchemy 2.0.x legacy `Query` API, Jinja2 + Bootstrap 5.3.2. **No new dependency** — the recognizer is `re` and `str` methods.

**Storage**: MariaDB via PyMySQL in production, SQLite through the same `Storage` ABC in unit tests. **No schema change and no migration.**

**Testing**: `nox -s tests` (unit, network blocked, sub-second), `nox -s e2e` (Playwright, 15-minute tool timeout), `nox -s screenshots_headless` / `screenshots_verify`

**Target Platform**: Flask app on a home LAN, one operator, no login

**Project Type**: Server-rendered web application, single project

**Performance Goals**: None. No measurement motivates any change here, so none is made. The notes clause is one more disjunct in a query that already scans the same rows.

**Constraints**: `git status --porcelain` must be empty after any test session. `app/utils/gs1.py` must stay pure (standard library only) like its three siblings. No scan that resolves today may resolve differently.

**Scale/Scope**: 5 production files (1 new), ~4 test files, 2 documentation files. A few hundred lines including tests.

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1 design. No violations, so the Complexity Tracking table is omitted.*

| Principle | Assessment |
|---|---|
| **I — Simplicity First** | The largest new artifact is one pure function. No abstraction, no configuration knob, no new dependency. Three deliberate refusals are recorded in `research.md`: no general GS1 parser (R1/R6), no application-wide AIM-prefix handling (R4), and no custom Werkzeug URL converter (R8). The code-formed address **redirects** rather than re-rendering, which removes a second copy of a handler instead of adding one. |
| **II — Layered Boundaries** | Preserved exactly. Parsing goes in `app/utils/` beside its three siblings; the search change is in `CatalogService`; the new route is four lines and holds no ORM query or raw SQL, reaching the database only through `find_product_by_identifier`. |
| **III — Exact Numerics** | Not engaged. No measured quantity is read or written. |
| **IV — Test Discipline** | Unit tests carry the classification matrix (a pure function deserves an exhaustive table, not a browser); e2e covers only the three wiring paths. No new pytest marker. All e2e waits are `expect(...)` on a freshly loaded page — no `wait_for_timeout`, no `networkidle`, no snapshot read against an unestablished region. One template changes, so the screenshot sessions run; no screenshot covers the product catalogue, so the tree stays clean. |
| **V — MariaDB Source of Truth** | No schema change, therefore no Alembic revision. `data-model.md` states this explicitly so that "should I write a migration?" has a written answer: no, and a migration appearing in this feature means the design was misunderstood. |
| **VI — Item Lifecycle Invariants** | Not engaged. This feature never touches `InventoryItem`. |
| **Operating Context / Threat Model** | No sanitization layer is added. Input validation here is correctness-shaped: a malformed code 404s because it names no product, not because it might be hostile. |
| **Workflow gates** | Feature branch `issues/62` → PR, per the repo's existing convention. `nox -s tests` and `nox -s e2e` green before merge. `nox -s lint` is red at baseline (pre-existing E501) and is advisory; new files should satisfy it. |

**Post-design re-check**: unchanged. Phase 1 introduced one module, one function, one route and one query disjunct — the design got smaller as it was specified, not larger. Nothing in `contracts/` requires a new layer, a new dependency, or a new error-handling path.

## Project Structure

### Documentation (this feature)

```text
specs/009-find-by-code-or-note/
├── plan.md                          # This file
├── spec.md
├── research.md                      # Phase 0: ten decisions, with rejects
├── data-model.md                    # Phase 1: "nothing is stored", stated and defended
├── quickstart.md                    # Phase 1: how to validate, and what each proof is worth
├── contracts/
│   ├── scan-classification.md       # gs1.py + scan_router.py, full input matrices
│   └── search-and-addressing.md     # search_products + the new route
├── checklists/
│   └── requirements.md
└── tasks.md                         # Phase 2 — NOT created by /speckit-plan
```

### Source code

```text
app/
├── utils/
│   ├── gs1.py               # NEW  — decode_trade_item_number(); pure, stdlib only
│   ├── scan_router.py       # EDIT — rule 3 inserted; rules 3+4 share one GTIN arm
│   ├── gtin.py              #        read-only: owns validity, and keeps owning it
│   ├── ecia.py              #        read-only
│   └── internal_id.py       #        read-only: NOT loosened to accept lowercase
├── catalog_service.py       # EDIT — one disjunct in search_products' or_()
├── product/routes.py        # EDIT — GET /products/<product_code>
└── templates/product/
    └── search.html          # EDIT — the search box names notes

tests/
├── unit/
│   ├── test_gs1.py          # NEW  — the recognizer, exhaustively
│   ├── test_scan_router.py  # EDIT — new class; precedence and no-regression cases
│   ├── test_product_search.py  # EDIT — notes cases in TestTextSearch
│   └── test_routes.py       # EDIT — the code route, and the route-shadowing guard
└── e2e/
    ├── test_wedge_scan.py   # EDIT — one manufacturer-2D-barcode test
    └── test_product_crud.py # EDIT — one code-formed-address test

docs/
├── user-manual.md                  # EDIT — the searched-fields sentence; the scan table
└── product-functionality-gap.md    # EDIT — "Finding things", struck through as built
```

**Structure Decision**: The existing single-project Flask layout, unchanged. The one new file lands in `app/utils/`, which is already decomposed one-module-per-encoding — `internal_id.py` for this shop's codes, `ecia.py` for ISO/IEC 15434 envelopes, `gtin.py` for what a valid trade item number *is*. A GS1 element string is a fourth encoding and specifically not a GTIN: it is a wrapper that carries one. Keeping "find the number in the payload" apart from "is the number valid" is what lets both rules reach the catalogue through a single `normalize_and_validate` call, which is the design's central claim.

## The three changes, in dependency order

**None of the three depends on another.** They share an issue, not a mechanism, and each is independently shippable and independently testable. Build them in whatever order suits; the ordering below is by risk.

### 1. Notes in the search (lowest risk)

One line in `app/catalog_service.py`, plus the placeholder in `search.html` and the sentence at `docs/user-manual.md:749`. FR-011 (no duplicate rows) and FR-013 (other filters still bind) are structural — an `or_` disjunct on a column of the same row cannot multiply it, and the other filters are separate conjoined `.filter()` calls.

One thing to get right and one trap. Right: use `.like()`, matching its five siblings, so notes can never diverge from description (FR-012). Trap: do not write a case-insensitivity test — SQLite and MariaDB agree about `LIKE` folding, so it would pass whether the code said `like` or `ilike` and prove nothing. Assert sameness instead.

### 2. The code-formed address (contained risk)

One route in `app/product/routes.py`. Upper-case, validate with `internal_id.is_internal_id`, look up, redirect to `product_detail`. `internal_id.is_internal_id` is **not** loosened — doing so would make `witabc…` an internal code to the scanner, changing an existing classification for a convenience that belongs to one route.

The risk here is not the handler, it is the URL rule. `/products/<product_code>` sits on the same path shape as six static rules. Werkzeug ranks argument-free rules above parameterized ones, so they keep their handlers — but that fails silently and far from its cause if it is ever wrong. The test enumerating `/products`, `/products/new`, `/products/capture`, `/products/reorder`, `/products/categories` and `/products/tags` ships with the route.

### 3. The trade-item element string (most surface, but provably contained)

`app/utils/gs1.py`, then one rule in `scan_router.py`. The whole of the risk is FR-008 — "no scan that resolves today resolves differently" — and it is provable rather than hopeful:

- a rule-3 match needs ≥16 characters, and `gtin.ACCEPTED_LENGTHS` is `(8, 12, 13, 14)`: **disjoint sets**, so a bare GTIN cannot be stolen;
- rules 1 and 2 run first, so an internal code and an ECIA envelope cannot be stolen either.

That argument belongs in a comment at the call site. It is the reason the change is safe and it is not visible from reading the code.

Two properties are worth asserting structurally rather than only behaviourally, because they are the design: `scan_router.py` contains no `'01'` literal and exactly one `normalize_and_validate` call, and `gs1.py` imports only from the standard library.

## Risks and how each is retired

| Risk | Retired by |
|---|---|
| The new rule captures a scan that resolves today | The disjoint-length argument above, plus regression cases in `test_scan_router.py` pinning every existing vector |
| The recognizer starts validating, so `gtin.py` stops owning validity | Three explicit tests: a bad check digit and the all-zero no-read are **returned** by the extractor and **refused** by the classifier |
| The new URL rule shadows an existing `/products/…` page | A test enumerating all six static routes |
| A prose tail turns into a barcode (`'…134352 RES 10K'`) | The digit-or-GS-or-nothing tail rule, with the rejection cases in the matrix |
| The screen and the manual disagree about what is searched | Both edited in the same change; `docs/user-manual.md:749` is named in `research.md` R10 |
| Someone writes a migration | `data-model.md` opens by stating there is none and why |

## Phase 0 & 1 artifacts

- **[research.md](research.md)** — ten decisions with rejected alternatives. R1 (where the recognizer lives) and R4 (AIM prefixes scoped to the new rule) are the two places `main` needs a different answer from the archived `archive/bmad-product-catalog` design, because that branch had an `app/utils/gs1.py` and a `strip_aim_prefix` that `main` does not. R5 records the Python fact the transmission handling turns on: `'\x1d'.isspace()` is `True`, so `strip()` absorbs a bare leading GS but not one that followed an AIM identifier.
- **[data-model.md](data-model.md)** — no schema change, stated and defended; the entities read; where each validation rule lives.
- **[contracts/scan-classification.md](contracts/scan-classification.md)** — the recognizer's full input matrix, the five-rule precedence, the shared-arm code shape, and the before/after classification table.
- **[contracts/search-and-addressing.md](contracts/search-and-addressing.md)** — the search clause and its structural properties; the route's four response cases; the template edit.
- **[quickstart.md](quickstart.md)** — commands, per-scenario proofs, the regression checklist, and the e2e waiting rules that apply.
