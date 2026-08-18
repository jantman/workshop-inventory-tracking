# Implementation Plan: Category and Location on the Capture Confirmation Page

**Branch**: `issues/99` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/018-capture-category-location/spec.md`

## Summary

Add `category_path`, `location` and `sub_location` to the capture confirmation form so a
captured product is filed at capture time instead of on a second visit.

The database already has all three columns on `Product`, nullable, and `create_product` and
`update_product` already accept and validate all three. The suggestion endpoints
(`/api/categories`, `/api/inventory/field-suggestions/<field>`) already serve both halves of
the app. So the work is threading three strings from a form through `capture_order` to the
calls that already know what to do with them, plus the markup and two script tags.

The one genuinely new decision is FR-010: `_clean` and `category_utils.canonical` both turn
blank into `None`, and `None` passed to `update_product` **clears** the column. So on the
attach-to-existing path the three fields must be passed by *presence*, not by value — a key
is added to the update only when the operator actually stated something. See
[research.md](./research.md) §3.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory), SQLAlchemy 2.0.x legacy `Query` API,
Jinja2 + Bootstrap 5.3.2 server-rendered templates, vanilla JS (no build step)

**Storage**: MariaDB via `MariaDBStorage`. **No schema change and no Alembic revision** —
`products.category_path` (String 512), `products.location` (String 100) and
`products.sub_location` (String 100) already exist and are already nullable
(`app/database.py:842-847`).

**Testing**: `nox -s tests` (pytest, SQLite through the same `Storage` interface),
`nox -s e2e` (Playwright, 15-minute tool timeout)

**Target Platform**: Linux, single-user, LAN-only

**Project Type**: Server-rendered Flask web application (blueprints + services)

**Performance Goals**: None applicable. Three form fields add no query to the capture POST,
which already takes 8-15 seconds for a full image gallery.

**Constraints**: The three values must reach `capture_order` before the duplicate and
recycled-identifier questions are settled, because an over-length category path must be
refused without having written anything (matching the existing "nothing below writes" rule).

**Scale/Scope**: One operator. Two templates, one service method, one route, two script
tags. No new endpoint.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Verdict | Notes |
|---|---|---|
| **I. Simplicity First** | PASS | No new endpoint, table, migration, abstraction or config knob. The three values reuse `create_product`/`update_product` parameters that already exist. The only structural change is extracting an existing Jinja block into a partial so two pages share it — a move, not a layer, and it is what makes FR-007/FR-008 true by construction rather than by vigilance. |
| **II. Layered Architecture Boundaries** | PASS | The route reads three form fields and passes them on; every write stays inside `CatalogService`. No ORM query enters `app/product/routes.py`. |
| **III. Exact Numerics** | N/A | Nothing measured. All three values are free-form strings. No `Decimal`, no `float`, no arithmetic. |
| **IV. Test Discipline Through Nox** | PASS | Unit tests extend `tests/unit/test_capture.py` and `tests/unit/test_product_routes.py`; E2E extends `tests/e2e/test_order_capture.py`. No new pytest marker. Every new wait names an element (see [quickstart.md](./quickstart.md) §Waiting). |
| **V. MariaDB Is the Source of Truth** | PASS | No schema change, so no revision. Nothing is added to the legacy Sheets export path. |
| **VI. Item Lifecycle and History Invariants** | N/A | This touches `products`, not `inventory_items`. FR-007 shares a *vocabulary* with `inventory_items.sub_location` — it reads that column through `VocabularyService` and never writes to it. No JA ID, active row or parent-child relationship is involved. |

**Operating context**: LAN-only, single trusted operator. Validation here serves correctness
(a bad category path breaks the filing) and not defense. CSRF is already on the capture form
and is untouched.

**Post-design re-check**: unchanged. Phase 1 added no entity, no endpoint and no dependency.
The Complexity Tracking table below stays empty.

**Screenshot gate** (Development Workflow, not a principle): `capture.html` changes, so
`docs/images/screenshots/user-manual/order_capture.png` goes stale and must be regenerated and
committed with the change. `product_add_form.png` must come back byte-identical — it is the
check that the `_form_fields.html` extraction was a faithful move. See
[research.md](./research.md) §8.

## Project Structure

### Documentation (this feature)

```text
specs/018-capture-category-location/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── capture-form.md      # The POST field set of /products/capture
│   └── capture-order.md     # CatalogService.capture_order signature
├── checklists/
│   └── requirements.md  # From /speckit-specify
└── tasks.md             # Phase 2 output (/speckit-tasks - NOT created here)
```

### Source Code (repository root)

```text
app/
├── templates/product/
│   ├── _classification_fields.html   # NEW - the three rows, extracted verbatim
│   ├── _form_fields.html             # includes the partial in place of the block
│   └── capture.html                  # includes the partial + two script tags
├── product/
│   └── routes.py                     # product_capture: read 3 fields, pass them on
└── catalog_service.py                # capture_order: 3 params, threaded to
                                      # create_product / update_product

tests/
├── unit/
│   ├── test_capture.py               # service behaviour: new vs existing product
│   └── test_product_routes.py        # the route passes the form through
└── e2e/
    └── test_order_capture.py         # the form files a product, survives a question
```

**Structure Decision**: The existing layout, unchanged. This feature adds exactly one file —
a Jinja partial under `app/templates/product/` — and edits four. Route code stays in the
`product` blueprint, business logic stays in `app/catalog_service.py`, and the templates keep
the `_leading_underscore` convention already used for `_form_fields.html`, `_layout.html` and
`_rename_modal.html`.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.
