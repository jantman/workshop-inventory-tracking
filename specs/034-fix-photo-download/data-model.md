# Phase 1 Data Model: Photo Download Actually Downloads

**Feature**: `034-fix-photo-download` | **Date**: 2026-09-01

## No schema change

This feature adds no table, no column, no index and no constraint, and therefore **no
Alembic revision**. Everything the download needs is already stored. What follows
documents the two entities and — more to the point — the relationship between their
identifiers, because confusing them is the entire defect.

## Entities as they exist

### `Photo` (`photos`, `app/database.py:687`)

The stored file itself. One row per uploaded file, holding the bytes once.

| Field | Type | Null? | Relevance here |
|-------|------|-------|----------------|
| `id` | Integer PK | no | **The identifier the download endpoint takes** (R1). |
| `filename` | String(255) | **NOT NULL** | The name the file was uploaded under → `download_name`. |
| `content_type` | String(100) | **NOT NULL** | Constrained to `image/jpeg`, `image/png`, `image/webp`, `application/pdf`. Sent as the response mimetype. |
| `file_size` | Integer | NOT NULL | Not used by download; `CHECK file_size > 0`. |
| `original_data` | BLOB / MEDIUMBLOB | **NOT NULL** | The bytes the download returns — the original, never `thumbnail_data` or `medium_data`. |
| `thumbnail_data`, `medium_data` | BLOB | NOT NULL | Generated renditions. **Never** returned by download (FR-003). |
| `sha256_hash` | String(64) | nullable | Unused here. |

The three `NOT NULL` columns marked in bold are why no "content missing" branch is needed
(R3): a `Photo` row that exists is by construction complete.

### `ItemPhotoAssociation` (`item_photo_associations`)

The link putting a stored file on an inventory item. Fields: `id`, `ja_id`, `photo_id`,
`display_order`, `created_at`, plus a `photo` relationship. **It has no `filename`** —
reading one off it is fault 2 of the bug (`routes.py:3020`).

## The relationship that matters

```text
Photo (1) ──────< ItemPhotoAssociation (0..n) >────── InventoryItem
  │
  └─< ProductAttachment / PurchaseAttachment (0..n)
```

- A `Photo` may have **many** associations — one file shown on several items (the copy-
  photos feature creates these).
- A `Photo` may have **zero** associations — every product and purchase attachment is one.
- Therefore `photos.id` and `item_photo_associations.id` are **two independent
  sequences**. They coincide only on a database where every Photo has exactly one
  association and nothing else has ever created a Photo row. That describes a fresh test
  database and nothing else. Issue #131 records the live drift: association 53 against
  photo 43.

This is the invariant the feature is built on, and the one the tests must exercise
(FR-006, FR-008). It is also already documented in the codebase — see the comment at
`photo-manager.js:399-407` and the fixture docstring in
`tests/e2e/test_photo_bulk_delete.py`.

## Which id each existing route takes

| Route | Takes | Correct today? |
|-------|-------|----------------|
| `GET /api/photos/<id>?size=` | Photo id | yes |
| `DELETE /api/photos/<id>` | association id | yes (fixed by #102) |
| `GET /api/photos/<id>/download` | *both, incoherently* | **no — this feature** |

After this change the download row reads "Photo id", matching the `GET` above it.

## State transitions

None. Download is a read; no row changes state.
