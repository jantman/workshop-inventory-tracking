---
baseline_commit: 51657b9b3ad012c6e9ad6a91de21425d769cadd5
---

# Story 1.1: Product entity and migration

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the workshop operator,
I want a Product table and domain model created alongside metal stock,
so that the catalog has a place to store products without disturbing existing inventory.

## Acceptance Criteria

1. **Given** the app running against the existing database at Alembic HEAD `8213852b0b94`, **When** the new migration is applied via `manage.py db upgrade`, **Then** a `products` table exists with an integer surrogate PK and columns for `manufacturer`, `mpn`, `description` (Label Description), `notes`, `category_path`, `attributes` (JSON), and created/updated timestamps (FR2).
2. **And** a `Product` ORM class lives on the shared `Base` in `app/database.py` following the enhanced-ORM pattern (AD-1), with any value objects/enums placed in `app/models.py`.
3. **And** existing metal-stock tables and behavior are unchanged (NFR9) — no existing migration, ORM class, or table is modified.
4. **And** `manage.py db downgrade 8213852b0b94` cleanly reverses the migration (drops `products` and its indexes), leaving the schema identical to the pre-upgrade HEAD.
5. **And** the `Product` ORM class round-trips through the storage layer: it persists and reloads via SQLAlchemy, the `attributes` JSON column round-trips a Python dict, and all FR2 fields except the PK/timestamps accept `NULL` (supporting backfill-forward creation, FR61 — enforced downstream in Story 1.3, not here).

## Scope Boundary — READ FIRST

This story creates the **minimal FR2 Product table only**. The ERD in the architecture spine shows the *eventual* shape of `products` with many more columns; **those are added by later stories via their own chained Alembic migrations — do NOT add them now.**

| Column(s) | Added by | Do NOT add in 1.1 |
| --- | --- | --- |
| `internal_id` (UNIQUE business key) | Epic 2 · Story 2.4 | ✅ excluded — it is service-generated with retry-on-collision and **no DB default** (AD-8); a half-baked nullable placeholder now would violate that. |
| `quantity_on_hand`, `quantity_verified_at`, `reorder_threshold`, `stock_status`, `stock_status_at`, `location`, `sub_location` | Epic 5 | ✅ excluded |
| `equivalent_group_id` FK | Epic 10 · Story 10.1 | ✅ excluded |
| `purchases` table + FK | **Story 1.2 (next)** | ✅ excluded |

Ship exactly: `id`, `manufacturer`, `mpn`, `description`, `notes`, `category_path`, `attributes`, `created_at`, `updated_at`. Nothing else.

## Tasks / Subtasks

- [x] **Task 1 — Add the `Product` ORM class to `app/database.py` (AC: #1, #2)**
  - [x] Define `class Product(Base)` with `__tablename__ = 'products'`, placed alongside `InventoryItem`/`Photo`, following the enhanced-ORM conventions in that file (module-level docstring style, `__repr__`, `to_dict()`).
  - [x] Columns (exact set — see Scope Boundary): id, manufacturer, mpn, description, notes, category_path (indexed), attributes (JSON), created_at, updated_at — as specified.
  - [x] Add `JSON` to the existing `from sqlalchemy import (...)` import line.
  - [x] Implement `__repr__` and a `to_dict()` returning the FR2 fields (mirrors `Photo.to_dict()` style; ISO-format the timestamps; returns `attributes` as-is).
  - [x] Left `app/models.py` untouched — no enums/value objects needed for 1.1's columns. `description` kept as `String(255)` (label text is short; matches surrounding convention).

- [x] **Task 2 — Create the Alembic migration (AC: #1, #3, #4)**
  - [x] Hand-wrote `migrations/versions/c10caa1431c6_add_products_table.py` modeled on `5d61d892776a_add_materials_taxonomy_table.py` (no live MariaDB at HEAD available for autogenerate; hand-write is deterministic and matches existing style).
  - [x] `down_revision = '8213852b0b94'` (verified via `ScriptDirectory`: single head, correct chain); revision `c10caa1431c6`.
  - [x] `upgrade()`: `op.create_table('products', …)` matching the ORM columns, `sa.PrimaryKeyConstraint('id')`, `sa.JSON()` for `attributes`, plus `op.create_index(op.f('ix_products_category_path'), …)`.
  - [x] `downgrade()`: drops the index then `op.drop_table('products')` (material_taxonomy ordering; PR #44 discipline).

- [x] **Task 3 — Verify the migration round-trips on real MariaDB (AC: #4)**
  - [x] Verified against a disposable **MariaDB 11.8** container (not the dev DB). `manage.py db upgrade` ran the full chain to `c10caa1431c6`; `products` created with `attributes` as `longtext … CHECK (json_valid(...))` (MariaDB JSON), `JSON_EXTRACT` functional, `ix_products_category_path` present.
  - [x] `manage.py db downgrade 8213852b0b94` cleanly removed `products` + index; `manage.py db current` returned to `8213852b0b94`; metal-stock tables (`inventory_items`, `item_photo_associations`, `material_taxonomy`, `photos`) intact (NFR9).

- [x] **Task 4 — Unit tests (AC: #2, #5)**
  - [x] Added `tests/unit/test_product_model.py` (7 tests, `unit` marker).
  - [x] Tests exercise the ORM class via the `test_storage` SQLite engine (`Base.metadata.create_all`). Column set asserted against `Product.__table__` to keep ORM/migration in lock-step.
  - [x] Asserts: persist/reload; `attributes` dict round-trip; all FR2 fields default `None`; timestamps auto-populate; `to_dict()` keys; `__repr__`.
  - [x] `venv/bin/nox -s tests` → **357 passed, 305 deselected, 0 failures** (no regressions, NFR9).

## Dev Notes

### Enhanced-ORM pattern (AD-1) — how to match `InventoryItem`
- One SQLAlchemy ORM class per entity on the **shared `Base`** already defined at `app/database.py:23` (`Base = declarative_base()`). Do **not** create a second `Base` and do **not** build a parallel dataclass-domain/ORM split — `app/models.py` holds *value objects/enums only* (bridged via `@hybrid_property`/`@property`), and 1.1 needs none.
- Follow the file's existing idioms: `Column(...)` with explicit types, `func.now()` for timestamp defaults (`app/database.py:76-77`), `__repr__`, and a `to_dict()` for later API/envelope use.
- The `Photo` class (`app/database.py:687`) is the closest recent precedent for a fresh, self-contained table with a `to_dict()` that excludes/simplifies heavy columns — mirror its structure.

### Timestamps convention — DECISION MADE
The codebase is inconsistent: `InventoryItem` uses `date_added`/`last_modified` (`app/database.py:76`), while the newer `Photo` uses `created_at`/`updated_at` (`app/database.py:714`). **Use `created_at`/`updated_at`** for all new catalog tables (matches the most recent precedent and reads naturally). Keep this consistent across Stories 1.1→1.5 so the catalog subsystem is internally uniform. *(Confirmed convention for all new catalog tables.)*

### JSON column (`attributes`) — cross-dialect behavior
- Use SQLAlchemy's **generic `sa.JSON`** type (`from sqlalchemy import JSON`). It maps to native `JSON` on MariaDB and to serialized `TEXT` on SQLite, so the same column definition works for both the migration (MariaDB) and unit tests (SQLite via `create_all`). This is the **first** JSON column in the project — there is no in-repo precedent, so verify the round-trip explicitly (Task 4).
- Store Specifications as a dict; treat `NULL` as "no specifications" at the app layer (do not add a server default in 1.1).

### Migrations (AD-14) — driven through `manage.py db`, NOT Flask-Migrate
- CLI wrapper: `app` uses raw Alembic via `manage.py` (`from alembic import command`). Commands: `manage.py db upgrade`, `db downgrade <rev>`, `db migrate -m "..."` (autogenerate), `db current`, `db history` (`manage.py:40-98`).
- All schema changes are Alembic migrations chained from HEAD — never `Base.metadata.create_all` outside tests (project-context.md critical rule). The migration **must** chain `down_revision = '8213852b0b94'`.
- Clean-downgrade pattern reference: `5d61d892776a_add_materials_taxonomy_table.py` — a textbook `create_table` + `create_index` / `drop_index` + `drop_table` pair. Copy its shape.

### What this story must NOT break (NFR9 — read the code you're near)
- `app/database.py` currently defines `InventoryItem`, `MaterialTaxonomy`, `Photo`, `ItemPhotoAssociation`. You are **adding** a class, not editing these. Adding a new class to `Base` changes what `Base.metadata.create_all` builds in tests — that is expected and desired; it must not alter existing tables.
- Existing migrations chain: `6e64cd1f734a → 5d61d892776a → … → 56dc95692b79 → 8213852b0b94` (HEAD). Your migration appends after HEAD; do not renumber or edit any existing migration.

### Regression lesson from PR #44 (issue #36) — MariaDB drop ordering
The most recent migration fix (`2d448ea`, "Fix alembic downgrade at 8213852b0b94 — index/FK drop order on MariaDB") learned that **MariaDB refuses to drop an index while it still backs a foreign key**, so child tables/indexes must be dropped before their parents (see the comment at `8213852b0b94…py:286-292`). Story 1.1's `products` has **no incoming FKs yet** (Story 1.2 adds `purchases.product_id`), so its downgrade is a plain `drop_index` → `drop_table`. **Carry this lesson forward:** when Story 1.2 adds the `purchases` FK, its downgrade must drop `purchases` before any `products` index/table it references.

### Testing standards (project-context.md + spine Testing convention)
- Run via **`venv/bin/nox -s tests`** — never bare `pytest`. `nox` env creation needs Python 3.13 on PATH: prefix with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`.
- Unit tests use SQLite through `MariaDBStorage` and **block the network** (`--blockage`) — no real HTTP/DB calls. The `test_storage` fixture (`tests/conftest.py:35-64`) builds a temp SQLite DB via `Base.metadata.create_all`.
- Migration up/down verification (Task 3) requires **real MariaDB** — use a local dev DB or the `mariadb_testcontainer` fixture (`tests/test_database.py`, used by integration/e2e). A dedicated migration round-trip test is optional here (no existing precedent to mirror); at minimum, verify manually per Task 3 and record the result in Completion Notes.

### Project Structure Notes
- New/changed files only: `app/database.py` (add `Product`), `migrations/versions/<hex>_add_products_table.py` (new), `tests/unit/test_product_model.py` (new). `app/models.py` unchanged. Matches the spine's Structural Seed source tree (`database.py + Product…`; `migrations/versions/<new>_catalog_tables.py`).
- No route, service, template, or `requirements.txt` change in this story — the service layer (`mariadb_catalog_service.py`) and the create/edit UI arrive in Story 1.3.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1: Product entity and migration]
- [Source: _bmad-output/planning-artifacts/architecture/architecture-workshop-inventory-tracking-2026-07-22/ARCHITECTURE-SPINE.md#AD-1] (enhanced-ORM pattern on shared Base)
- [Source: …/ARCHITECTURE-SPINE.md#AD-3] (integer surrogate PKs)
- [Source: …/ARCHITECTURE-SPINE.md#AD-14] (Alembic via `manage.py db`, chained from HEAD `8213852b0b94`, metal stock untouched)
- [Source: …/ARCHITECTURE-SPINE.md#Consistency Conventions] (Schemaless Specifications → MariaDB JSON column; ORM `PascalCase` singular / table `snake_case` plural; migration `versions/<12hex>_<slug>.py`)
- [Source: _bmad-output/planning-artifacts/epics.md#Requirements Inventory] (FR2, FR3, FR4, FR61, NFR2, NFR3, NFR9)
- [Source: _bmad-output/project-context.md#Critical Implementation Rules] (venv, nox, Alembic-only, Decimal-not-float, domain models pattern)
- [Existing code: app/database.py:25-93 (InventoryItem enhanced-ORM), :687-753 (Photo new-table + to_dict), :76-77 (func.now() timestamps)]
- [Existing code: migrations/versions/5d61d892776a_add_materials_taxonomy_table.py (clean create/drop migration template)]
- [Existing code: migrations/versions/8213852b0b94_…py:286-292 (MariaDB FK/index drop-order lesson, PR #44)]
- [Existing code: tests/conftest.py:35-64 (test_storage fixture; Base.metadata.create_all on SQLite)]
- [Existing code: manage.py:40-98 (db upgrade/downgrade/migrate/current/history commands)]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context) — bmad-dev-story workflow.

### Debug Log References

- Migration round-trip verified on a disposable `mariadb:11.8` Docker container (host port 13306, DB `inventory`), isolated from the dev DB in `.env`. Container removed after verification.
- Alembic chain validated with `ScriptDirectory`: `heads == ['c10caa1431c6']`, `down_revision == '8213852b0b94'`.
- Real-MariaDB DDL confirmed: `attributes` → `longtext … CHECK (json_valid(...))`; `JSON_EXTRACT(attributes,'$.a')` returns the stored value; `ix_products_category_path` present.

### Completion Notes List

- Implemented the minimal FR2 `products` table only — `internal_id` (Epic 2), stock/quantity/location fields (Epic 5), and `equivalent_group_id` (Epic 10) intentionally deferred per the Scope Boundary.
- Chose the `created_at`/`updated_at` timestamp convention for the catalog subsystem (confirmed with Jason during story creation).
- `attributes` uses SQLAlchemy generic `sa.JSON` — native JSON on MariaDB, serialized TEXT on SQLite — so the same definition serves both the migration and the unit tests. First JSON column in the project; round-trip explicitly tested on both backends.
- Unit tests validate the ORM class via `create_all` (SQLite); the Alembic migration validated separately on MariaDB. Column set asserted against `Product.__table__` so ORM/migration drift surfaces as a test failure.
- All 5 ACs satisfied; full unit suite green (357 passed); metal-stock schema and behavior unchanged (NFR9).

### File List

- `app/database.py` (modified) — added `JSON` import; added `Product` ORM class.
- `migrations/versions/c10caa1431c6_add_products_table.py` (new) — Alembic migration, chained from `8213852b0b94`.
- `tests/unit/test_product_model.py` (new) — 7 unit tests for the `Product` model.
- `_bmad-output/implementation-artifacts/1-1-product-entity-and-migration.md` (modified) — story tracking (this file).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — story status transitions.

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-23 | Story 1.1 implemented: `Product` ORM entity + `products` Alembic migration (FR2 columns) + 7 unit tests. Verified up/down migration on MariaDB 11.8; full suite green (357 passed). Status → review. |
