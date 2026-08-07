# Implementation Plan: Keep the Catalogue Tidy

**Branch**: `issues/61` | **Date**: 2026-08-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-catalog-taxonomy-tidy/spec.md`

## Summary

Four independent slices, none of which needs new infrastructure:

1. **Category rename** is a bulk update of one column. There is no categories table — a category *is* the `products.category_path` string — so renaming `elctronics` to `electronics` means updating every product whose path equals that or begins with it plus a separator. The path arithmetic goes in `app/utils/category.py` as pure functions; the validation and the single-transaction update go in `CatalogService`.
2. **Tag rename and merge** operate on the existing `tags` / `product_tags` tables. A rename onto a free name is a column write; a rename onto an occupied one reassigns products to the survivor, skipping any that already carry it, and deletes the loser.
3. **Shared location/vendor vocabulary** widens what the application's existing field-suggestion endpoint draws on. The mechanism, the endpoint and the client component all already exist and are used by the metal stock forms; the work is to make the query read the catalogue's columns too and to wire the four catalogue inputs to the component that is already written.
4. **Product sub-location** is one nullable column, one Alembic revision, and the form/detail plumbing that goes with it.

Slices 1 and 2 add two page routes, two POST handlers and two service methods. Slice 3 relocates one existing method into a shared service and widens its query. Slice 4 is a migration. No new dependency, no new abstraction layer, no background work.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1.x (app-factory, blueprints), SQLAlchemy 2.0.x (legacy `Query` API, matching the surrounding files), Alembic, Jinja2 + Bootstrap 5.3.2. No new dependency.

**Storage**: MariaDB via PyMySQL. Touches `products` (adds `sub_location`, rewrites `category_path` in bulk), `tags`, `product_tags`, and reads `inventory_items` and `purchases`.

**Testing**: `nox -s tests` (pytest + SQLite through the `Storage` seam), `nox -s e2e` (Playwright, 15-minute tool timeout), `nox -s screenshots_headless` + `screenshots_verify` because templates and JS change.

**Target Platform**: Single Flask app on a home LAN, server-rendered HTML.

**Project Type**: Web application, single deployable. Existing structure; no new top-level directories.

**Performance Goals**: None stated and none measured. The catalogue holds tens of products; a rename touching every product under a category is a single UPDATE. No batching, progress reporting, or background job.

**Constraints**: Renames must be all-or-nothing (FR-007, FR-012) — satisfied by the existing `CatalogService._session()` context manager, which rolls back on any exception. Suggestions must never restrict entry (FR-018) — satisfied by keeping every field a plain `<input>`.

**Scale/Scope**: One operator, no concurrency. Roughly: 2 new pages, 4 new routes, 4 new service methods, 2 new pure functions, 1 Alembic revision, 1 relocated service module, 6 templates touched.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 design — see the second table.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | No new table for categories, no curated vocabulary lists, no preview endpoint (the confirmation counts come from data the page has already rendered), no redirect/alias machinery for renamed paths. One new module (`app/services/vocabulary.py`) and it is a *relocation* of an existing method to the shared home the constitution names, driven by a second real consumer — not speculative generality. **PASS** |
| **II. Layered Architecture Boundaries** | All new logic lands in services (`CatalogService`, `VocabularyService`) and pure utils (`app/utils/category.py`). The new routes stay thin: parse the form, call one service method, flash, redirect. No ORM query or raw SQL in a route. **PASS** |
| **III. Exact Numerics** | No measured quantity is touched. Nothing in this feature parses, stores or compares a dimension. **N/A** |
| **IV. Test Discipline Through Nox** | Unit tests for the pure path functions and both service methods; e2e for each user story. E2E waits are on observable state — the rename flows are form posts that navigate, so `expect()` on the resulting page content is the signal; the suggestion dropdown is the awaited-fetch case (pattern C: the dropdown's items are appended *after* the fetch resolves, so `expect(items).to_have_count(n)` is the whole wait). No new pytest marker needed. **PASS** |
| **V. MariaDB Is the Source of Truth** | `products.sub_location` ships as an Alembic revision with an exercised `downgrade`. No `create_all` outside fixtures, no hand-edited schema. The category rename is a data migration performed by the application at the operator's request, not by a revision. **PASS** |
| **VI. Item Lifecycle and History Invariants** | No add/move/shorten/edit/search path for inventory items is modified. The vocabulary query *reads* `inventory_items` including inactive rows — which is what the existing method already does, and reading cannot disturb the invariants. **PASS** |
| **Operating Context / Threat Model** | No auth, no sanitization layer. LIKE wildcards in operator input are escaped in the suggestion query — as the existing code already does — because an unescaped `%` returns wrong results, not because anyone is attacking. Category and tag names are rendered with Jinja's autoescaping and the existing `textContent`-based dropdown builder. **PASS** |
| **Technology Constraints** | Server-rendered Jinja + Bootstrap; no frontend framework, no build step. New JS is a plain IIFE matching `catalog-suggestions.js`. New code carries type hints and uses the project's `ValidationError` / `ItemNotFoundError`. **PASS** |
| **Development Workflow** | Feature branch `issues/61`, merged via PR. Templates, CSS and JS change, so `nox -s screenshots_headless` runs and its output is committed with the change; `nox -s screenshots_verify` must pass. **PASS — with an obligation recorded in tasks** |

No violations. The Complexity Tracking table is therefore omitted.

### Post-design re-check (after Phase 1)

Re-read after `data-model.md` and the contracts were written. Two things worth restating rather than new risks:

- **`app/services/vocabulary.py` is the only new module.** It contains no interface, no registry, and no configuration. It exists because `get_field_value_suggestions` gained a second caller and a second data source; leaving it on `MariaDBInventoryService` would have made the metal stock service the owner of the catalogue's vocabulary. Still **PASS** under Principle I.
- **The rename confirmation is computed in the browser from the rendered page.** The server re-validates and is authoritative, so a stale page cannot corrupt anything — it can only produce a refusal the operator did not expect, which is the correct failure. This avoids a preview endpoint that would exist to serve one modal. Still **PASS**.

## Project Structure

### Documentation (this feature)

```text
specs/004-catalog-taxonomy-tidy/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — decisions and rejected alternatives
├── data-model.md        # Phase 1 output — schema delta and rename semantics
├── quickstart.md        # Phase 1 output — how to run and validate
├── contracts/
│   ├── catalog-service.md      # New CatalogService methods
│   ├── vocabulary-service.md   # The relocated/widened suggestion service
│   └── http-routes.md          # New and changed HTTP surface
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── catalog_service.py                 # + rename_category, rename_tag, tag_list_with_counts
├── database.py                        # + Product.sub_location column and to_dict entry
├── utils/
│   └── category.py                    # + rename_descendant, would_nest_within (pure)
├── services/
│   └── vocabulary.py                  # NEW — the shared suggestion query
├── mariadb_inventory_service.py       # - get_field_value_suggestions, - FIELD_SUGGESTION_COLUMNS
├── main/
│   └── routes.py                      # field-suggestions endpoint calls VocabularyService
├── product/
│   └── routes.py                      # + tag list page, + 2 rename POST handlers, sub_location in form fields
├── static/js/
│   └── taxonomy-rename.js             # NEW — the rename confirmation modal
└── templates/product/
    ├── categories.html                # + per-row rename control
    ├── tags.html                      # NEW — tags in use, with counts
    ├── _form_fields.html              # + sub_location, + autocomplete dropdowns
    ├── _rename_modal.html             # NEW — shared by categories.html and tags.html
    ├── add.html                       # + field-autocomplete.js
    ├── edit.html                      # + field-autocomplete.js
    ├── detail.html                    # + sub_location display
    ├── purchase_add.html              # + vendor autocomplete
    └── capture.html                   # + vendor autocomplete

migrations/versions/
└── b1a0c0d10006_add_product_sub_location.py   # NEW

tests/
├── unit/
│   ├── test_category.py               # + rename path arithmetic
│   ├── test_catalog_service.py        # + rename_category, rename_tag
│   ├── test_vocabulary.py             # NEW — moved from test_mariadb_inventory_service.py, plus union cases
│   └── test_mariadb_inventory_service.py  # - the suggestion tests that moved
└── e2e/
    ├── test_category_rename.py        # NEW — US1
    ├── test_tag_rename.py             # NEW — US2
    ├── test_field_autocomplete.py     # + catalogue-side and cross-half cases (US3)
    └── test_product_crud.py           # + sub_location round-trip (US4)
```

**Structure Decision**: The existing layout is used unchanged. The catalogue already owns a blueprint (`app/product/`), a service (`app/catalog_service.py`), a template directory (`app/templates/product/`) and a pure-utility module for category paths (`app/utils/category.py`), and every part of this feature has an obvious home among them. The single addition is `app/services/vocabulary.py`, which sits in the directory the constitution designates for services shared between blueprints — which is exactly what a vocabulary read by both the inventory forms and the catalogue forms is.

## Implementation Notes by Slice

### Slice 1 — Category rename (US1, FR-001..FR-007)

`app/utils/category.py` gains two pure functions: one that rewrites a single path under a rename, and one that answers "would this rename put the category inside itself". Both are stdlib-only and unit-tested without a database, matching the module's existing contract.

`CatalogService.rename_category(old_path, new_path)` opens one session and, before mutating anything, checks in order: both paths canonicalize to something; they are not equal (a rename differing only in case or whitespace is a no-op and is reported as one); the target does not sit inside the source; no product *outside* the source subtree already sits at or under the target; every rewritten path still fits `MAX_CATEGORY_PATH_LENGTH`; and at least one product carries the source. Only then does it write. Any refusal raises `ValidationError` and the context manager rolls back, so FR-007 needs no extra machinery.

The categories page gains a rename control per row and a shared confirmation modal. The modal computes the affected-product total and detects a likely conflict from the paths and counts the page has already rendered — no preview endpoint. The server's validation is the authoritative one.

### Slice 2 — Tag rename and merge (US2, FR-008..FR-013)

A new `/products/tags` page lists tags with their product counts, which is what FR-013 asks for and what makes near-duplicates visible in the first place. `CatalogService.rename_tag(old_name, new_name)` normalizes the target the same way `_attach_tag` already does, then either writes the name or, when the target already exists, moves each product that does not already carry the survivor and deletes the loser. The `product_tags` composite primary key makes a duplicate row impossible, but the membership check is what keeps it from raising instead of succeeding.

Both handlers return a report — what happened, how many products, whether it merged — that the route flashes.

### Slice 3 — Shared vocabulary (US3, FR-014..FR-019)

`FIELD_SUGGESTION_COLUMNS` and `get_field_value_suggestions` move from `MariaDBInventoryService` into `app/services/vocabulary.py`, unchanged in behaviour for `thread_size` and `purchase_location` and widened for `location`, `sub_location` and `vendor` to also read `products.location`, `products.sub_location` and `purchases.vendor`. The existing endpoint path and JSON shape do not change, so the metal stock forms and `field-autocomplete.js` need no edit at all.

The catalogue side is markup: wrap the location, sub-location and vendor inputs in the `position-relative` + `dropdown-menu` pattern the inventory forms already use, and include `field-autocomplete.js`. Its DOM-ready block already binds `#location`, `#sub_location` (scoped by `#location`) and `#vendor` when a matching `-suggestions` dropdown exists, so no JavaScript is written for this slice.

### Slice 4 — Product sub-location (US4, FR-020..FR-023)

One Alembic revision adds `products.sub_location VARCHAR(100) NULL`, mirroring `inventory_items.sub_location`. The column threads through `Product.to_dict`, `CatalogService.create_product` / `update_product`, `_form_product_fields`, the shared form partial and the detail page. Existing products keep a NULL sub-location, which is an ordinary state (FR-023) and needs no backfill.

## Risks and Obligations

- **Screenshots.** `app/templates/product/**` and `app/static/js/**` both change, so the workflow gate requires `nox -s screenshots_headless` and committing the regenerated images. This is easy to forget and CI blocks on it.
- **The moved suggestion tests.** Relocating `get_field_value_suggestions` moves its unit tests too. They must move, not be rewritten from scratch, so the existing coverage of ranking, escaping and case-insensitive dedup is preserved rather than silently thinned.
- **`nox -s e2e` needs a 15-minute tool timeout** and the suite must leave the working tree clean.
