---
baseline_commit: dbcaeaccb390f5e11234bc6cc8061e7fb0af0822
---

# Story 1.2: Purchase entity and migration

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the workshop operator,
I want a Purchase table linked to Products,
so that I can record acquisitions, including orders still in flight.

## Acceptance Criteria

1. **Given** the `products` table exists (Story 1.1, at Alembic HEAD `c10caa1431c6`), **When** the Purchase migration is applied via `manage.py db upgrade`, **Then** a `purchases` table exists with an integer surrogate PK and a `product_id` FK to `products.id` such that one Product has zero or more Purchases (FR1, AD-3).
2. **And** the table carries `vendor`, `vendor_sku`, `order_date`, nullable `received_date`, `quantity`, `unit_price`, `order_number`, `source_url`, and a `request_key` column with a **UNIQUE** constraint (FR18, AD-9).
3. **And** a Purchase can be created with a `NULL` `received_date` (order in flight → On Order, FR19).
4. **And** a `Purchase` ORM class lives on the shared `Base` in `app/database.py` following the enhanced-ORM pattern (AD-1), with a SQLAlchemy `relationship()` wiring `Product.purchases` ↔ `Purchase.product` (AD-3).
5. **And** existing metal-stock tables/behavior and the `products` table are unchanged (NFR9), and `manage.py db downgrade c10caa1431c6` cleanly reverses the migration (drops `purchases`, its FK, and its indexes), leaving the schema identical to HEAD `c10caa1431c6`.
6. **And** the ORM round-trips through the storage layer: a `Purchase` persists and reloads; `product.purchases` and `purchase.product` navigate correctly; `unit_price` round-trips as `Decimal`; a `NULL` `request_key` is allowed on multiple rows while a duplicate **non-null** `request_key` is rejected (idempotency substrate for AD-9).

## Scope Boundary — READ FIRST

This story delivers the **`purchases` schema + ORM + relationship only**. It does **not** build the recording UI, the REST capture endpoint, purchase-history display, "Last paid", de-dup, or idempotent-capture *logic* — those are later stories. The `request_key` UNIQUE **column** is created here (AD-9 says the Epic-1 schema owns it); the idempotency *behavior* that uses it lands in Epic 7 (Story 7.4).

| Concern | Owned by | In 1.2? |
| --- | --- | --- |
| `purchases` table, FK, `request_key` UNIQUE column, ORM + relationship | **Story 1.2 (this)** | ✅ |
| Purchase recording via service/REST + history + "Last paid" | Story 1.4 | ❌ |
| Create/edit/detail Product UI | Story 1.3 | ❌ |
| ASIN indexing, VENDOR_SKU de-dup, ASIN confirm-not-merge | Epic 2 / Epic 7 | ❌ |
| Idempotent capture *behavior* on `request_key`; `order_date` default-to-today | Epic 7 (7.1, 7.4) | ❌ |
| Attachments referencing `purchase_id` | Story 1.5 | ❌ |

Ship exactly the `purchases` table below plus the `Product.purchases` relationship. Nothing else. Do **not** add service methods, routes, or forms.

## Tasks / Subtasks

- [x] **Task 1 — Add the `Purchase` ORM class + wire the relationship (AC: #1, #2, #4)**
  - [x] Added `Date` to the `from sqlalchemy import (...)` line in `app/database.py`.
  - [x] Defined `class Purchase(Base)` (`__tablename__ = 'purchases'`) just after `Product`, matching its style (`__repr__`, `to_dict()`).
  - [x] Columns implemented as specified: `product_id` NOT NULL + FK + index; all other business fields nullable; `unit_price` `Numeric(10,2)`; `order_date`/`received_date` `Date`; `request_key` nullable; `created_at`/`updated_at`.
  - [x] `__table_args__ = (UniqueConstraint('request_key', name='uq_purchases_request_key'),)`.
  - [x] `Purchase.product = relationship('Product', back_populates='purchases')`.
  - [x] Edited the `Product` class to add `purchases = relationship('Purchase', back_populates='product')` (ORM-only; no `products` schema change).
  - [x] `Purchase.__repr__` + `to_dict()` mirror `Product`/`InventoryItem` (ISO dates/timestamps; `float(unit_price)` at the JSON boundary).
  - [x] `app/models.py` left untouched.

- [x] **Task 2 — Create the Alembic migration (AC: #1, #2, #5)**
  - [x] Hand-wrote `migrations/versions/46393d2e6c96_add_purchases_table.py`.
  - [x] `down_revision = 'c10caa1431c6'`; verified with `ScriptDirectory` that heads collapse to `46393d2e6c96`.
  - [x] `upgrade()`: `create_table('purchases', …)` with `ForeignKeyConstraint(['product_id'],['products.id'])`, `PrimaryKeyConstraint('id')`, `UniqueConstraint('request_key', name='uq_purchases_request_key')`, `Numeric(10,2)`/`Date`; plus `create_index(op.f('ix_purchases_product_id'), …)`.
  - [x] `downgrade()`: single `op.drop_table('purchases')` (no preceding `drop_index` — PR #44 lesson).

- [x] **Task 3 — Verify the migration round-trips on real MariaDB (AC: #3, #5)**
  - [x] Verified on a disposable **MariaDB 11.8** container (port 13306), not the dev DB. `manage.py db upgrade` → head `46393d2e6c96`; `SHOW CREATE TABLE purchases` confirmed: `product_id int NOT NULL`, `CONSTRAINT purchases_ibfk_1 FOREIGN KEY (product_id) REFERENCES products (id)`, `uq_purchases_request_key` UNIQUE, `received_date date DEFAULT NULL`, `unit_price decimal(10,2)`, `ix_purchases_product_id`.
  - [x] MariaDB semantics: two `request_key = NULL` rows both inserted (count 3 incl. one non-null); duplicate non-null `request_key` → `ERROR 1062`; orphan `product_id` → `ERROR 1452` (FK enforced).
  - [x] `manage.py db downgrade c10caa1431c6` (with rows + FK present) cleanly dropped `purchases`; `products` + metal-stock tables intact; `manage.py db current` = `c10caa1431c6`. Container removed.

- [x] **Task 4 — Unit tests (AC: #4, #6)**
  - [x] Added `tests/unit/test_purchase_model.py` (10 tests, `unit` marker). Column set asserted against `Purchase.__table__`.
  - [x] Tests: persist/reload; `product.purchases` ↔ `purchase.product` nav; `received_date=None`; `unit_price` Decimal round-trip; duplicate non-null `request_key` → `IntegrityError` (with rollback) **and** two NULL `request_key` rows both persist; optional-field defaults; `to_dict()`; `__repr__`.
  - [x] Used `session.expire_all()` (not `expunge_all`) for the reload assertions to avoid `DetachedInstanceError` while still forcing a DB re-read. Did not unit-test DB-level FK rejection (SQLite `foreign_keys=OFF`); FK verified on MariaDB (Task 3).
  - [x] `venv/bin/nox -s tests` → **367 passed** (357 baseline + 10 new), 0 failures, no regressions (NFR9).

## Dev Notes

### Previous story intelligence — proven patterns from Story 1.1 (merged, PR #45)
Story 1.1 established the exact playbook this story reuses. Do not re-derive:
- **Hand-write the migration** (don't rely on `manage.py db migrate` autogenerate — it needs a live MariaDB at HEAD and can mis-render types/indexes). Model on `c10caa1431c6_add_products_table.py`.
- **Verify migrations on a throwaway `mariadb:11.8` Docker container** (host port 13306), never the `.env` dev DB (`127.0.0.1:3306/inventory` holds real data). Full recipe in Task 3.
- **Two-layer validation:** the ORM class is validated by unit tests via SQLite `create_all`; the Alembic migration is validated separately on MariaDB. They can silently diverge — so assert the column set against `<Model>.__table__` in the unit tests.
- **`created_at`/`updated_at`** is the confirmed timestamp convention for all catalog tables (Jason confirmed during 1.1). Use it here too.
- Story 1.1's full unit suite baseline is **357 passed**; keep it green.

### The FK + downgrade ⚠️ (PR #44 / issue #36) — this is the story where it matters
Story 1.1's Dev Notes flagged this forward: `purchases` introduces the **first cross-table FK** in the catalog subsystem (`product_id → products.id`), and on MariaDB that FK is backed by an index (`ix_purchases_product_id`). The merged fix `2d448ea` learned that **MariaDB refuses to `DROP INDEX` while the index still backs a live foreign key**. Therefore:
- **Upgrade:** create the table (with the FK) and the index normally.
- **Downgrade:** issue **only** `op.drop_table('purchases')`. `DROP TABLE` tears down the FK, both indexes, and the table in one atomic step. Do **not** add a preceding `op.drop_index(...)` — that is exactly the ordering that failed in #36. (Contrast Story 1.1, where `ix_products_category_path` did **not** back an FK, so drop_index-then-drop_table was safe. Different situation — don't copy that ordering here.)

### `request_key` UNIQUE + NULL semantics (AD-9) — the idempotency substrate
- Both **MariaDB/MySQL and SQLite** allow **multiple NULLs** in a UNIQUE constraint while rejecting duplicate non-null values. That is precisely the wanted behavior: purchases without an idempotency key coexist freely; two capture attempts carrying the *same* `request_key` collide at the DB. Story 1.2 provides only the constraint; Epic 7 Story 7.4 relies on it (idempotent unit = whole capture transaction; UNIQUE violation caught as a **domain error**, not raw `IntegrityError`). Do not add app-level check-then-insert here.
- This NULL-tolerant behavior is testable on SQLite (Task 4) and confirmed on MariaDB (Task 3).

### Types & nullability rationale
- **Money:** `unit_price` is `Numeric(10, 2)` → `decimal.Decimal`, matching `InventoryItem.purchase_price`. Never `float` for money (project-context critical rule). `to_dict()` serializes via `float(...)` only at the JSON boundary, as `InventoryItem` does.
  - *SQLite caveat:* SQLite has no native decimal; SQLAlchemy converts float↔Decimal and emits a `SAWarning`. Expected — use a clean 2-dp value (e.g. `Decimal('12.50')`) in the round-trip test and compare as `Decimal`. Authoritative `decimal(10,2)` precision is verified on MariaDB (Task 3).
- **Dates:** `order_date`/`received_date` are `sa.Date` (calendar dates per the architecture ERD), not `DateTime`. `received_date IS NULL` is the On-Order signal (FR19). `order_date` is nullable here; its "default to capture date when omitted" (FR48) is **service-layer** logic in Epic 7, not a DB default.
- **Nullability:** only `product_id` is `NOT NULL` (structural integrity). Every other business column is nullable to preserve the backfill-forward / partial-capture principle (FR61) established in Story 1.1 — stricter service-layer validation arrives in Story 1.4 / Epic 7, not the schema.
- **No `ON DELETE` clause:** product deletion is not a flow in this phase; leave the FK at the default (RESTRICT). Do not add CASCADE.

### Enhanced-ORM pattern (AD-1) — matching the merged `Product`
- One ORM class on the shared `Base` at `app/database.py` (do not add a second `Base`; do not build a parallel dataclass/ORM split — `app/models.py` stays untouched for 1.2).
- Bidirectional `relationship()` with `back_populates` on both sides (AD-3 wants relationships expressed via `relationship()`, not raw joins). `relationship` is already imported (used by `ItemPhotoAssociation`, `app/database.py:779`).
- Reference implementations in the same file: `Product` (`app/database.py:819`, the closest sibling — copy its shape), `InventoryItem.to_dict()` (`app/database.py:577`, the `float()`-on-`Numeric` precedent), `ItemPhotoAssociation` (`app/database.py:755`, the existing FK + `relationship()` + index precedent).

### What this story must NOT break (NFR9)
- You are **adding** a `Purchase` class and **editing** `Product` only to add the `purchases` relationship (no column/schema change to `products`). Do not touch `InventoryItem`, `MaterialTaxonomy`, `Photo`, `ItemPhotoAssociation`, or any existing migration.
- Migration chain today: `… → 8213852b0b94 → c10caa1431c6` (HEAD). Your migration appends after `c10caa1431c6`. Do not renumber or edit existing migrations.

### Testing standards (project-context.md + spine Testing convention)
- Run via **`venv/bin/nox -s tests`** — never bare `pytest`. `nox` env creation needs Python 3.13 on PATH: prefix with `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH"`.
- Unit tests use SQLite through `MariaDBStorage` and block the network. Build a session with `sessionmaker(bind=test_storage.engine)` (the pattern in `test_product_model.py` / `test_mariadb_inventory_service.py:762`).
- The migration up/down verification (Task 3) requires real MariaDB (JSON/FK/decimal/index DDL differ from SQLite). No dedicated migration test file exists; verify manually per Task 3 and record the result in Completion Notes.

### Project Structure Notes
- New/changed files only: `app/database.py` (add `Purchase`, add `Date` import, add `Product.purchases` relationship), `migrations/versions/<hex>_add_purchases_table.py` (new), `tests/unit/test_purchase_model.py` (new). `app/models.py` unchanged. Matches the spine's Structural Seed (`database.py + … Purchase …`; `migrations/versions/<new>_catalog_tables.py`).
- No route/service/template/`requirements.txt` change in this story.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2: Purchase entity and migration] (AC, FR18/FR19)
- [Source: …/ARCHITECTURE-SPINE.md#AD-3] (integer surrogate PKs; `relationship()` FKs; `internal_id` is not a join target)
- [Source: …/ARCHITECTURE-SPINE.md#AD-9] (`purchases.request_key` UNIQUE owned by the Epic-1 schema; idempotency = whole capture transaction; UNIQUE violations → domain errors)
- [Source: …/ARCHITECTURE-SPINE.md#AD-14] (Alembic via `manage.py db`, chained from HEAD; metal stock untouched)
- [Source: …/ARCHITECTURE-SPINE.md#Structural Seed] (`purchases` ERD: columns, `request_key UK "nullable; idempotency"`, `received_date "nullable = On Order"`, `order_date "defaults to capture date"`)
- [Source: …/ARCHITECTURE-SPINE.md#Consistency Conventions] (Money = `Decimal`/`ROUND_HALF_UP`; Dates tolerant, `order_date` service-defaulted; table `snake_case` plural)
- [Source: _bmad-output/implementation-artifacts/1-1-product-entity-and-migration.md] (previous-story playbook: hand-written migration, disposable-container verification, ORM/migration lock-step, PR #44 forward-flag)
- [Existing code: app/database.py:819 (merged `Product` class — sibling to copy), :577 (`InventoryItem.to_dict()` float-on-Numeric), :755-792 (`ItemPhotoAssociation` FK + relationship + index precedent), :9 (import line to extend with `Date`)]
- [Existing code: migrations/versions/c10caa1431c6_add_products_table.py (Story 1.1 migration template), :8213852b0b94…py:286-292 (PR #44 MariaDB FK/index drop-order lesson)]
- [Existing code: tests/unit/test_product_model.py (unit-test shape, column-set assertion, session pattern)]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context) — bmad-dev-story workflow.

### Debug Log References

- Migration round-trip verified on a disposable `mariadb:11.8` Docker container (host port 13306, DB `inventory`), isolated from the `.env` dev DB. Container removed after verification.
- Alembic chain validated with `ScriptDirectory`: `heads == ['46393d2e6c96']`, `down_revision == 'c10caa1431c6'`.
- Real-MariaDB behavior confirmed: FK `purchases_ibfk_1 (product_id → products.id)`; `uq_purchases_request_key` UNIQUE tolerates multiple NULLs (2 NULL rows inserted) but rejects a duplicate non-null (`ERROR 1062`); orphan FK rejected (`ERROR 1452`); downgrade with rows + live FK present succeeds via a single `DROP TABLE` (PR #44 lesson holds).
- One test-only fix during RED→GREEN: initial tests used `session.expunge_all()` then accessed `.id` on the detached instances → `DetachedInstanceError`. Switched to `session.expire_all()` (keeps instances session-bound, still forces a DB reload).

### Completion Notes List

- Delivered the `purchases` schema + `Purchase` ORM + bidirectional `Product`↔`Purchase` relationship only. Recording UI/REST, history, "Last paid", de-dup, and idempotency *behavior* are deferred to Story 1.4 / Epic 7 per the Scope Boundary; the `request_key` UNIQUE *column* is created here (AD-9).
- `product_id` is the only NOT-NULL business column; all other fields nullable for backfill-forward / partial capture (FR61). `order_date` default-to-capture-date is service-layer logic (Epic 7), not a DB default.
- Money is `Numeric(10,2)` → `Decimal` (never float), matching `InventoryItem.purchase_price`; `to_dict()` casts to `float` only at the JSON boundary.
- The first cross-table FK in the catalog subsystem — the downgrade is a single `op.drop_table('purchases')` (verified with data + FK present), the exact fix pattern from issue #36 / PR #44.
- All 6 ACs satisfied; full unit suite green (367 passed); metal-stock and `products` schema unchanged (NFR9).

### File List

- `app/database.py` (modified) — added `Date` import; added `Purchase` ORM class; added `Product.purchases` relationship.
- `migrations/versions/46393d2e6c96_add_purchases_table.py` (new) — Alembic migration, chained from `c10caa1431c6`.
- `tests/unit/test_purchase_model.py` (new) — 10 unit tests for the `Purchase` model and the Product↔Purchase relationship.
- `_bmad-output/implementation-artifacts/1-2-purchase-entity-and-migration.md` (modified) — story tracking (this file).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — story status transitions.

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-23 | Story 1.2 implemented: `Purchase` ORM entity + `Product`↔`Purchase` relationship + `purchases` Alembic migration (FK to products, nullable UNIQUE `request_key`) + 10 unit tests. Verified up/down migration + FK/UNIQUE semantics on MariaDB 11.8; full suite green (367 passed). Status → review. |
