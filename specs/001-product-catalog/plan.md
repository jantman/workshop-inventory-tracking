# Implementation Plan: Product Catalog & Purchase Tracking

**Branch**: `product-catalog` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-product-catalog/spec.md`

## Summary

Extend the existing Flask inventory application with a product catalogue whose purpose is
**identification, not inventory control**: record what a purchased part is, what it cost, and
where it came from, so that scanning a label months later answers "what is this thing" without
reaching a vendor page.

The technical approach is additive and stays inside the existing application. Five new tables
(`products`, `purchases`, `product_identifiers`, `tags`, `product_tags`) plus an attachment
association reach MariaDB through Alembic migrations. Business logic lands in a new
`CatalogService` following the established `InventoryService` pattern; routes live in a new
`product` blueprint alongside `main` and `admin`. The parsing and encoding rules — GTIN
normalization, ECIA distributor-label grammar, internal-code encoding, category paths, scan
classification — go in **pure standard-library modules under `app/utils/`** with no Flask, DB,
or config imports, so the whole decision surface is unit-testable without an app context.

Two areas need genuinely new code rather than reuse:

- **Label composition.** The existing `BarcodeLabelGenerator` renders a barcode plus its own
  value and nothing else, so it cannot satisfy FR-011 (description + provenance + code). The
  plan composes the label image with Pillow — already a dependency — and hands the PNG to the
  existing `LpPrinter.print_images()`. Same raster path, same `lp` options, no new printer
  language or driver, which is exactly what the spec's constraint protects.
- **Order-time capture.** FR-020 needs an operator-initiated capture while a vendor listing is
  on screen. A bookmarklet that POSTs the current page's fields to the app satisfies it with no
  browser extension, no separate service, and no scraping.

**Prior art.** A previous BMAD-driven effort implemented much of this on unmerged branches
(furthest: `backup/story/5-4-derived-on-order-and-recently-received`, 96 commits ahead of
`main`). Per the decision recorded during planning, **this plan targets a fresh implementation
from `main`** and carries over no code. Those branches are consulted in
[research.md](./research.md) as evidence for four hard-won decisions — ECIA field grammar, GTIN
normalization, internal-code ownership, and scan-classification precedence — because they
represent real work against real hardware and re-deriving them from scratch would be waste.
Where this plan departs from what those branches built, [research.md](./research.md) says so and
why.

## Technical Context

**Language/Version**: Python 3.13 (nox `DEFAULT_PYTHON`; requires pyenv 3.13 on PATH)

**Primary Dependencies**: Flask 3.1.3 (app-factory), SQLAlchemy 2.0.51 (legacy `Query` style to
match surrounding code), Alembic 1.18.5, PyMySQL, Flask-WTF (CSRF), Jinja2 + Bootstrap 5.3.2
server-rendered UI, Pillow (label composition, already present), PyMuPDF (PDF thumbnails,
already present), `pt-p710bt-label-maker` (`LpPrinter` raster print path, already present)

**New dependencies**: none. Every requirement below is met with the standard library or a
package already in `requirements.txt`. See [research.md](./research.md) §2 for why the internal
label code deliberately avoids a DataMatrix encoder and a GS1 element-string grammar.

**Storage**: MariaDB via PyMySQL, sole source of truth. Five new tables plus one association
table, each introduced by a reversible Alembic revision applied through `python manage.py db`.
SQLite in-memory stands in for MariaDB in unit tests through the same models.

**Testing**: `nox -s tests` (pytest, unit, SQLite, network blocked via `--blockage`),
`nox -s e2e` (Playwright, **20-minute tool timeout required**), `nox -s coverage`,
`nox -s screenshots_headless` + `screenshots_verify`. Fixtures come from `tests/conftest.py`
(`test_storage` → `app` → `client`). `--strict-markers` is on, so any new marker must be
registered in `pytest.ini` first.

**Target Platform**: Linux server on a home LAN, reached from a workshop-cart browser and, in
future, a handheld touch device. No authentication layer, no Internet exposure.

**Project Type**: Server-rendered Flask web application (single project, existing layout).

**Performance Goals**: None specified and none to be invented. Throughput is tens of received
items per month by one person. No caching, batching, async, or background jobs without a
measured problem (Constitution I).

**Constraints**: `Decimal` for every price — never `float` (Constitution III). Product identity
must not depend on a vendor's reusable item identifier (FR-008). The existing JA-ID inventory
tables and their history invariants must be left untouched (Constitution VI). CSRF stays
enabled everywhere except the single documented `POST /api/capture` exemption (see Complexity
Tracking). In-progress entry must survive a momentary connection drop (FR-035), which is a
client-side draft, not an offline-sync layer.

**Scale/Scope**: Catalogue grows by tens of products per month; low thousands over the
application's life. Roughly 12 new templates, 1 new blueprint, 1 new service, 5 pure utility
modules, ~6 Alembic revisions. The pre-existing 30k-item metal-stock inventory is explicitly
**not** imported.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Pre-Phase-0 | Post-Phase-1 |
|---|---|---|---|
| **I. Simplicity First** | No new service/datastore/dependency; no scale machinery; no speculative abstraction | **PASS** — additive to the existing app; zero new packages | **PASS** — see three simplifications recorded below |
| **II. Layered Architecture** | Dataclasses in `models.py`; ORM in `database.py`; business logic in a service; routes thin | **PASS** | **PASS** — `CatalogService` mirrors `InventoryService`; see note on the Storage ABC |
| **III. Exact Numerics** | `Decimal` for money and measurements, never `float` | **PASS** | **PASS** — `Numeric(10,2)` for price; quantities are discrete `Integer` counts |
| **IV. Test Discipline** | Run via nox; register markers; mock HTTP; use conftest fixtures; behavior changes ship with tests | **PASS** | **PASS** — pure `app/utils/` modules are unit-testable with no app context |
| **V. MariaDB + Alembic** | Reversible revisions, downgrade exercised, MariaDB-safe operation ordering | **PASS** | **PASS** — see [data-model.md](./data-model.md) §Migrations |
| **VI. Item Lifecycle Invariants** | JA-ID history semantics preserved | **PASS** — feature adds tables and does not modify `inventory_items` | **PASS** |
| **Threat model** | No auth layer, no hardening, validation for correctness only | **PASS** — validate because bad data breaks the inventory | **PASS** |
| **Workflow** | Feature branch + PR; CI green; **screenshots regenerated for UI changes** | **PASS** | **PASS** — screenshot regeneration is an explicit task, not an afterthought |

### Simplifications taken under Principle I

Recorded here because each is a place where an obvious-looking richer design was rejected, and a
later reader should find the reason rather than re-derive it:

1. **No GS1 element string and no DataMatrix for the internal code.** A `WIT`-prefixed
   Crockford-base32 token in a Code128 symbol satisfies FR-015 ownership with the barcode
   encoder already installed. GS1 AI 96 would add FNC1 transmission variance — scanners disagree
   about whether FNC1 arrives as `0x1D`, as a substitute, or stripped — that exists only because
   of the encoding choice. See [research.md](./research.md) §2.
2. **No equivalence relation between products.** Deferred in the spec's Assumptions; multiple
   identifiers and multiple purchases on one product cover the observed need.
3. **No background job and no stored status for reorder state.** "Low" and "on order" are
   **derived by query** at view time. No denormalized status column can drift if there is no
   denormalized status column. See [research.md](./research.md) §10.

### Note on the Storage ABC

Constitution II says every persistence path goes through the `Storage` ABC. As built, that ABC
is sheet-shaped (`read_all(sheet_name)`, `write_row`, …) — a Google Sheets legacy — and the real
persistence path is already `InventoryService`, which takes `storage.engine` and builds its own
`sessionmaker`. **`CatalogService` follows the `InventoryService` precedent** rather than forcing
catalogue queries through a row-and-sheet interface that cannot express them. This is a
pre-existing tension between the constitution's wording and the codebase, not one this feature
introduces; the plan does not widen it and does not invent a third pattern. Flagging it for the
PR review conversation rather than silently picking a side.

## Project Structure

### Documentation (this feature)

```text
specs/001-product-catalog/
├── plan.md               # This file
├── spec.md               # Feature specification
├── research.md           # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
│   ├── http-api.md       # Routes and JSON payloads
│   ├── scan-contract.md  # Scan classification + resolution contract
│   └── label-contract.md # Label composition and print contract
├── checklists/
│   └── requirements.md   # Spec quality checklist (complete)
└── tasks.md              # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── models.py                     # EXTEND: IdentifierType, ScanKind, StockStatus enums;
│                                 #         Product/Purchase/ScanClassification dataclasses
├── database.py                   # EXTEND: Product, Purchase, ProductIdentifier, Tag,
│                                 #         ProductTag, ProductAttachment ORM models
├── catalog_service.py            # NEW: all catalogue business logic
├── product/                      # NEW blueprint package (peer of main/ and admin/)
│   ├── __init__.py
│   └── routes.py                 # Thin routes; no ORM queries, no raw SQL
├── utils/                        # NEW pure modules — stdlib only, no Flask/DB/config
│   ├── gtin.py                   # GTIN-8/12/13/14 normalization + check digit (FR-009/010)
│   ├── ecia.py                   # ISO/IEC 15434 format-06 grammar (FR-016)
│   ├── internal_id.py            # Crockford base32 internal code (FR-015)
│   ├── category.py               # Materialized category path normalization (FR-030)
│   └── scan_router.py            # Classification precedence (FR-014)
├── services/
│   └── product_label.py          # NEW: Pillow label composition → existing LpPrinter
├── photo_service.py              # EXTEND: attachments on product/purchase (FR-034)
├── templates/product/            # NEW: add, edit, detail, search, categories,
│                                 #      purchase_add, receive, reorder
└── static/js/                    # NEW: scan-capture.js, product-form.js (draft persistence)

migrations/versions/              # NEW: ~6 reversible Alembic revisions

tests/
├── unit/                         # test_gtin, test_ecia, test_internal_id, test_category,
│                                 # test_scan_router, test_catalog_service, test_product_routes,
│                                 # test_product_label
└── e2e/                          # test_product_crud, test_wedge_scan, test_label_print,
                                  # test_reorder_view, test_order_capture
```

**Structure Decision**: Single project, extending the existing Flask layout. Two structural
choices worth stating:

- **A new `app/product/` blueprint** rather than appending to `app/main/routes.py`. That file is
  already ~2900 lines; the prior effort's approach of adding product routes into it took it past
  6500. A third blueprint package alongside `main` and `admin` uses the pattern the constitution
  already names, adds no new layer, and keeps Principle I's "a reader should be able to follow
  any file top to bottom" achievable.
- **Pure modules in `app/utils/`** for every parsing/encoding rule. This is not speculative
  abstraction — it is what makes the rules testable in the sub-second unit suite with no app
  context and no database, and it keeps one definition of each grammar so encoder and decoder
  cannot drift.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

No violations. The Constitution Check passes at both gates. The two items that most resemble
added complexity are recorded here for the reviewer rather than left implicit:

| Item | Why it is not a violation |
|---|---|
| New `app/services/product_label.py` composing label images with Pillow | The spec's constraint fences off new *printer control languages and driver paths* (SBPL explicitly). This composes a PNG and hands it to the same `LpPrinter.print_images()` with the same `lp` options. FR-011 is unsatisfiable without it: `BarcodeLabelGenerator` can only render a barcode plus its own value. |
| New `app/product/` blueprint package | Uses the existing blueprint-package pattern named in the constitution's module-placement rule. The alternative — a 6500-line `main/routes.py` — is the less simple outcome. |
| `POST /api/capture` exempted from CSRF | The constitution says CSRF protection stays enabled, and it does everywhere else. This one endpoint is exempt because the bookmarklet posts from the vendor's origin (FR-020), and the exemption is proportionate under the constitution's own stated threat model: LAN-only, one trusted user, hostile input explicitly out of scope. **Bounds**: it is the only exemption, it carries an inline comment saying why, and `quickstart.md`'s pre-merge checklist verifies both. Recorded here rather than left in `contracts/http-api.md` so the PR reviewer sees it without going looking. |

## Phase Status

- [x] Phase 0 — [research.md](./research.md): 11 decisions, no unresolved unknowns
- [x] Phase 1 — [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- [x] Constitution re-check after Phase 1 design — PASS
- [ ] Phase 2 — `tasks.md` (run `/speckit-tasks`)
