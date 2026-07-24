---
baseline_commit: 34d76e56a7b145c8a86706df61c6e0fcedb579f0
---

# Story 1.5: Attachments on product or purchase

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the workshop operator,
I want to attach datasheets, diagrams, or photos to a Product or a Purchase,
so that reference material lives with the record and survives with my backups.

## Acceptance Criteria

1. **Given** a Product detail view, **When** I upload a PDF datasheet (or an image), **Then** the file is stored as a BLOB in the database (AD-12) and is retrievable/viewable from the Product view via a direct link (FR5).
2. **Given** the `attachments` table, **When** a row is written, **Then** exactly one of `product_id` / `purchase_id` is non-null — enforced by a DB `CHECK ((product_id IS NULL) <> (purchase_id IS NULL))` **and** an application invariant that rejects both-null or both-set as a caught domain error (not a raw `IntegrityError`) (AD-12).
3. **And** the new migration is chained from HEAD `46393d2e6c96`, `manage.py db downgrade 46393d2e6c96` cleanly reverses it, and existing metal-stock / product / purchase tables are unchanged (NFR9, AD-14).
4. **And** all attachment logic (store, list, retrieve) lives in `CatalogService`; routes contain no ORM/SQL (AD-2). The attachment list on the detail page does not load BLOB bytes.
5. **And** the full test suite passes with new service tests, route tests (including a multipart upload), and a MariaDB migration round-trip verification.

## Scope Boundary — READ FIRST

This story adds an `attachments` table (BLOB-in-DB, AD-12), the `CatalogService` store/list/retrieve surface, a **browser upload on the Product detail view**, and a **serve route**. It closes Epic 1.

| Concern | Owned by | In 1.5? |
| --- | --- | --- |
| `attachments` schema (XOR one-owner), migration, ORM | **Story 1.5 (this)** | ✅ |
| Upload from the **Product** detail page + list + serve/download | **Story 1.5 (this)** | ✅ |
| **Purchase**-attachment UI | later | ❌ — the schema/service support `purchase_id` (XOR is meaningful + tested), but there is no Purchase detail surface yet, so no purchase upload UI this story |
| Attachment **size caps beyond the MEDIUMBLOB limit / PDF thumbnailing** (PyMuPDF) | Epic 8 (Deferred in the spine) | ❌ — 1.5 enforces a simple app-level size limit only |
| Delete / replace attachment | later | ❌ — AC covers upload + retrieve; delete is not required |
| Programmatic REST attachment API + api_client method | later (Epic 8) | ❌ — 1.5's upload/serve are browser routes (CSRF-protected form + a GET serve), not an AD-13 JSON endpoint |

## Tasks / Subtasks

- [x] **Task 1 — `Attachment` ORM model + `attachments` migration (AC: #1, #2, #3)**
  - [x] Added `class Attachment(Base)` in the catalog section: `product_id`/`purchase_id` nullable FKs (indexed), `filename`, `content_type`, `file_size`, `content` (`LargeBinary().with_variant(MEDIUMBLOB,'mysql')`), `created_at` (write-once).
  - [x] `__table_args__`: `ck_attachment_one_owner` (XOR) + `ck_attachment_positive_file_size`.
  - [x] One-directional `relationship('Product')`/`relationship('Purchase')` (no back_populates); BLOB-free `to_dict()`.
  - [x] `migrations/versions/f771284e1478_add_attachments_table.py`, `down_revision='46393d2e6c96'` (verified single head). `upgrade` creates the table with both FKs, both CHECKs, PK, and the two indexes; `content` as MEDIUMBLOB variant. `downgrade` is a single `op.drop_table('attachments')` (PR #44 discipline).

- [x] **Task 2 — `CatalogService` attachment methods (AC: #1, #2, #4)**
  - [x] `ATTACHMENT_ALLOWED_TYPES` (pdf/jpeg/png/webp/gif — **excludes svg**) + `ATTACHMENT_MAX_SIZE = 16MB`; whitelist enforced app-side only.
  - [x] `add_attachment(...) -> dict` — raises `ValidationError` for XOR violation / empty / oversize / disallowed type / missing owner; else flush→snapshot→commit; returns BLOB-free snapshot.
  - [x] `get_attachments_for_product` uses `defer(Attachment.content)` (never loads BLOBs when listing); ordered; `[]` for none.
  - [x] `get_attachment_data -> (bytes, content_type, filename) | None`. `ValidationError` propagates (not swallowed).

- [x] **Task 3 — Routes: upload + serve; detail list (AC: #1, #4)**
  - [x] `product_detail` also fetches `attachments` (deferred BLOB) and passes them.
  - [x] `product_upload_attachment` (`/products/<id>/attachments`, POST, CSRF-protected multipart) — 404 if product missing; no-file → flash+redirect; delegates to `add_attachment`; catches `ValidationError` → flash; success flash + redirect.
  - [x] `serve_attachment` (`/attachments/<id>`) — 404 if missing; `send_file(BytesIO, mimetype, download_name)` + `X-Content-Type-Options: nosniff`.

- [x] **Task 4 — Detail template: attachments card (AC: #1)**
  - [x] "Attachments" card: list (filename → serve URL, content_type + KB size), empty-state, and a CSRF-protected `enctype="multipart/form-data"` upload form.

- [x] **Task 5 — Verify the migration on real MariaDB (AC: #2, #3)**
  - [x] MariaDB 11.8 container: `SHOW CREATE TABLE attachments` confirmed `content mediumblob NOT NULL`, FKs `attachments_ibfk_1/2` → products/purchases, `ck_attachment_one_owner` + `ck_attachment_positive_file_size`, both indexes.
  - [x] XOR enforced on MariaDB: one-owner INSERT OK; both-owners → `ERROR 4025` (`ck_attachment_one_owner`); no-owner → `ERROR 4025`.
  - [x] `downgrade 46393d2e6c96` (row present) dropped `attachments` cleanly; products/purchases/metal-stock intact; `current` = `46393d2e6c96`. Container removed.

- [x] **Task 6 — Tests (AC: #1–#5)**
  - [x] `test_catalog_service.py` — +10 (product/purchase attach, XOR both/neither → ValidationError, oversize, disallowed type, empty, missing owner, order+empty, get_attachment_data + None).
  - [x] `test_product_routes.py` — +6 (detail card+form, multipart upload persists, no-file flash, upload-missing-product 404, serve bytes+content-type+nosniff, serve-missing 404). Introduces the repo's first Flask-client multipart test.
  - [x] `venv/bin/nox -s tests` → **416 passed** (400 baseline + 16 new), 0 failures, no regressions.

## Dev Notes

### AD-12 — BLOB-in-DB, exactly one owner
- Bytes live in a DB BLOB column (backed up with the database), matching the `Photo` precedent — **not** the filesystem. Column idiom: `LargeBinary().with_variant(MEDIUMBLOB, 'mysql')` (`database.py:707-708`).
- The one-owner rule is enforced **twice** (belt-and-suspenders, as AD-12 says "CHECK … / application invariant"): the DB `CHECK ((product_id IS NULL) <> (purchase_id IS NULL))` AND the service's XOR guard. The service guard fires first and raises a **caught `ValidationError`** so the operator sees a clean message, never a raw `IntegrityError` — the same "UNIQUE/constraint violations surface as domain errors" philosophy as AD-9.

### Testing split — different from Story 1.2's FK
- **The XOR CHECK IS enforced by SQLite** (verified empirically: both-set and both-null both raise `CHECK constraint failed`). So unlike Story 1.2's foreign key (which SQLite ignores unless `PRAGMA foreign_keys=ON`), the DB-level XOR is exercised by the unit suite via `Base.metadata.create_all` — plus the app-level guard. Task 6 tests the app-level `ValidationError`; the DB CHECK is a backstop also verified on MariaDB (Task 5).
- **The MEDIUMBLOB size ceiling and the two FKs still need MariaDB verification** (SQLite's `LargeBinary` has no length cap and doesn't enforce FKs by default), so Task 5's container round-trip is mandatory — same rationale as 1.1/1.2.
- **New pattern:** there is no existing Flask-test-client multipart upload in the repo (`upload_photo` is exercised via the `requests`-based api_client / e2e only). Task 6 introduces `client.post(url, data={'file': (io.BytesIO(b'…'), 'name.pdf')}, content_type='multipart/form-data')` — spelled out so you don't hunt for a template that isn't there.

### Upload/serve — mirror `Photo`, but simpler and CSRF-protected
- `upload_photo` (`routes.py:2856`) is `@csrf.exempt` JSON/AJAX. **1.5 diverges deliberately:** the attachment upload is a plain **CSRF-protected browser multipart form** on the product detail page (consistent with the 1.3/1.4 catalog browser-form convention — hidden `csrf_token()`, flash+redirect). Read bytes via `file.read()`, MIME via `file.content_type` (`routes.py:2864-2879`).
- Serve mirrors `get_photo_data`/`download_photo` (`routes.py:2957-3001`): `send_file(io.BytesIO(bytes), mimetype=content_type, as_attachment=False, download_name=filename)`. Add `X-Content-Type-Options: nosniff`. Inline viewing is safe because the whitelist admits only PDF/raster images (no HTML, no SVG).
- **Do NOT set a global `MAX_CONTENT_LENGTH`** — none exists today, and a global cap below `PhotoService.MAX_FILE_SIZE` (20 MB) would regress photo uploads (NFR9). Enforce the attachment size at the service level instead (read-then-check-`len`, same as `PhotoService`; whole file is read into memory — acceptable at this scale).
- Attachment logic goes on **`CatalogService`** (not a separate `AttachmentService`) to keep the catalog surface unified per AD-2 — even though `Photo` uses a standalone `PhotoService`. Reuse the merged `CatalogService` session/audit/flush-snapshot patterns.

### Previous story intelligence (1.1–1.4, all merged)
- Migration playbook (from 1.1/1.2): hand-write, chain from HEAD, verify on a throwaway `mariadb:11.8` container, single `drop_table` on downgrade for a table with FKs (PR #44). Alembic HEAD is `46393d2e6c96` (1.3/1.4 added no migrations).
- `created_at` convention; flush-before-commit snapshot (avoids false-failure on post-commit refresh); dedicated queries not detached-relationship navigation; `session.expire_all()` (not `expunge_all`) when re-reading in a test; `ValidationError` for domain rejections; catalog audit logger already registered (`logger_name='mariadb_catalog_service'`). Baseline suite: **400 passed**.
- The 1.3-review **deferred** per-request engine/pool item (systemic, `deferred-work.md`) — don't touch it; reuse `_get_catalog_service()`.

### What this story must NOT break (NFR9)
- Additive: new `Attachment` class + migration, new `CatalogService` methods, `product_detail` modification + 2 new routes, `detail.html` extension, new tests. Do NOT touch `InventoryItem`/`Photo`/`ItemPhotoAssociation`, `PhotoService`, existing migrations, or `Product`/`Purchase` (Attachment's relationships are one-directional). No dependency change (Pillow already present for test fixtures).

### Project Structure Notes
- New: `migrations/versions/<hex>_add_attachments_table.py`. Modified: `app/database.py` (Attachment), `app/mariadb_catalog_service.py` (methods + constants), `app/main/routes.py` (`product_detail` + upload/serve routes + `defer` import consideration), `app/templates/product/detail.html`. Tests appended to `test_catalog_service.py`, `test_product_routes.py`. Matches the spine Structural Seed (`attachments` table; AD-12).

### References
- [Source: epics.md#Story 1.5: Attachments on product or purchase] (AC, FR5) · [#FR Coverage Map] (FR5 → Epic 1)
- [Source: ARCHITECTURE-SPINE.md#AD-12] (BLOB-in-DB; `CHECK ((product_id IS NULL) <> (purchase_id IS NULL))`; Photo precedent) · [#AD-2] (logic in CatalogService) · [#AD-3] (relationships via `relationship()`) · [#AD-14] (Alembic from HEAD; metal stock untouched) · [#Deferred] (attachment size limits / PDF thumbnailing → Epic 8)
- [Source: 1-1…/1-2… story files] (migration + MariaDB-container playbook, PR #44 downgrade lesson) · [1-3…/1-4… story files] (CatalogService/route/detail patterns; ValidationError; deferred engine item)
- [Existing code: app/database.py:687-742 (`Photo` — BLOB column idiom, CheckConstraints, BLOB-free `to_dict`), :9/:11 (`LargeBinary`/`CheckConstraint`/`MEDIUMBLOB` imports); app/photo_service.py:68-140 (store), :166-195 (retrieve), :44-52 (size/type constants); app/main/routes.py:2856-2907 (upload), :2931-3001 (serve/download via `send_file`); app/exceptions.py:17-28 (`ValidationError` + `.field`)]
- [Existing code: migrations/versions/8213852b0b94_…py:44 & dce1254cd381_…py (MEDIUMBLOB migration column idiom); migrations/versions/46393d2e6c96_add_purchases_table.py (current HEAD; single-drop_table downgrade with an FK)]
- [Existing code: tests/unit/test_photo_service.py:55-107 (Pillow/PDF byte fixtures), :349-398 (store test); tests/conftest.py:35-79 (fixtures) — note: NO prior Flask-client multipart test exists to copy]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (Opus 4.8, 1M context) — bmad-dev-story workflow.

### Debug Log References

- Migration verified on a disposable `mariadb:11.8` container (port 13306), isolated from the `.env` dev DB. Container removed after.
- Alembic chain: `heads == ['f771284e1478']`, `down_revision == '46393d2e6c96'`.
- MariaDB DDL: `content mediumblob NOT NULL`; FKs `attachments_ibfk_1` (→products), `attachments_ibfk_2` (→purchases); CHECKs `ck_attachment_one_owner` + `ck_attachment_positive_file_size`; indexes on both FK columns.
- XOR enforced on MariaDB (`ERROR 4025` for both-owners and no-owner). Also enforced on SQLite (unit tests) — verified during story creation — so the app-level `ValidationError` guard and the DB CHECK are both exercised.
- Downgrade with a row present dropped `attachments` cleanly via a single `DROP TABLE` (PR #44 lesson holds for the two FK-backing indexes).

### Completion Notes List

- Closes Epic 1: `attachments` table (BLOB-in-DB, AD-12), `CatalogService` store/list/retrieve, a CSRF-protected browser upload on the product detail page, and an inline serve route.
- **Dual XOR enforcement** (AD-12 "CHECK … / application invariant"): the service raises a caught `ValidationError` for both-set/neither/oversize/bad-type/missing-owner; the DB `ck_attachment_one_owner` CHECK is the backstop. Unlike 1.2's FK, the CHECK is enforced by SQLite too, so it's covered by the unit suite as well as the MariaDB round-trip.
- **BLOB never over-fetched:** `get_attachments_for_product` uses `defer(Attachment.content)` for listing; `to_dict()` excludes the bytes; only `serve_attachment` loads the content.
- **Security:** content-type whitelist excludes `image/svg+xml` (script-carrying); serve sets `X-Content-Type-Options: nosniff`; inline viewing is safe since only PDF/raster images are admitted. No global `MAX_CONTENT_LENGTH` set (would regress the 20 MB photo uploads, NFR9) — size enforced app-side.
- **New test pattern:** first Flask-test-client multipart upload in the repo (`data={'file': (BytesIO, name)}`, `content_type='multipart/form-data'`).
- Attachment logic lives on `CatalogService` (unified catalog surface, AD-2), not a separate service like `Photo`. Scope honored: product-attachment UI only (schema/service support `purchase_id`, tested); no delete/thumbnailing (later/Epic 8).
- All 5 ACs satisfied; full suite **416 passed**; `Photo`/`PhotoService`/`Product`/`Purchase`/existing migrations untouched (NFR9).

### File List

- `app/database.py` (modified) — `Attachment` ORM class.
- `migrations/versions/f771284e1478_add_attachments_table.py` (new) — Alembic migration, chained from `46393d2e6c96`.
- `app/mariadb_catalog_service.py` (modified) — `add_attachment`/`get_attachments_for_product`/`get_attachment_data`; `ATTACHMENT_ALLOWED_TYPES`/`ATTACHMENT_MAX_SIZE`; `Attachment`/`defer`/`ValidationError`/`Tuple` imports.
- `app/main/routes.py` (modified) — `product_detail` fetches attachments; new `product_upload_attachment` + `serve_attachment` routes.
- `app/templates/product/detail.html` (modified) — Attachments card (list + upload form).
- `tests/unit/test_catalog_service.py` (modified) — +10 attachment tests.
- `tests/unit/test_product_routes.py` (modified) — +6 attachment route tests.
- `_bmad-output/implementation-artifacts/1-5-attachments-on-product-or-purchase.md`, `sprint-status.yaml` (modified) — tracking.

## Change Log

| Date | Change |
| --- | --- |
| 2026-07-24 | Story 1.5 implemented: `attachments` table (BLOB-in-DB, XOR one-owner CHECK) + `CatalogService` store/list/retrieve + product-detail upload/serve + 16 tests. Verified DDL/XOR/downgrade on MariaDB 11.8. Full suite green (416 passed). Closes Epic 1. Status → review. |
