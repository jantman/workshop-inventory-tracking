---
title: 'Typed identifier entity and uniqueness'
type: 'feature'
created: '2026-07-24'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
baseline_revision: '2a53631'
final_revision: 'd85ec7b'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** A Product can only be found by its own catalog columns; there is no way to attach the many codes printed on a part or its packaging (barcodes, ASINs, part numbers) so the product can be looked up by any of them (FR7), nor any guard against the same code being claimed by two products (FR8).

**Approach:** Introduce a `ProductIdentifier` entity (`product_identifiers` table) that stores multiple typed `(type, value)` identifiers per Product, add it via a chained Alembic migration, and expose add/list operations on `CatalogService`. Uniqueness is enforced by a DB `UNIQUE` constraint; the service catches the violation and raises a caught domain error that names the conflicting Product rather than letting an `IntegrityError` escape.

## Boundaries & Constraints

**Always:**
- Identifier types are the closed set `GTIN, ASIN, FNSKU, MPN, VENDOR_SKU, INTERNAL`, defined as an `Enum` in `app/models.py`; stored as the enum string value in a plain `String` column (NOT a DB `ENUM`) so later stories extend the set without a migration.
- Uniqueness is scoped per AD-9: `VENDOR_SKU`, `ASIN`, `FNSKU` are vendor-scoped; every other type is global. Enforce with ONE `UNIQUE(identifier_type, value, vendor_scope)` constraint, where `vendor_scope` is a `NOT NULL` string — `''` for global types, the supplied vendor for vendor-scoped types. Empty-string sentinel, never NULL (MySQL/SQLite both allow multiple NULLs in a UNIQUE index, which would silently defeat global uniqueness).
- All identifier mutation/query goes through `CatalogService` (AD-2); routes/ORM stay out of it. Follow the existing session pattern (flush + snapshot before commit; rollback + `log_audit_operation` on failure).
- A duplicate insert surfaces as a caught `ValidationError` naming the conflicting Product's id — mirroring how `add_attachment` raises `ValidationError` for domain violations — never a raw `IntegrityError`.
- The migration chains from head `f771284e1478` and leaves metal-stock / products / purchases / attachments untouched (NFR9, AD-14).

**Block If:**
- The intended uniqueness scope for a type cannot be reconciled with AD-9 (e.g. a new requirement demands manufacturer-scoped `MPN`). Do not invent a scope beyond global-vs-vendor.

**Never:**
- No GTIN normalization, check-digit validation, or `GTIN_UNVALIDATED` type (Story 2.2). No ASIN-on-purchase indexing (2.3). No `internal_id` generation or GS1 encode/decode (2.4/2.5). No UI/route/template changes — this story is entity + migration + service + tests only.
- No `float`; no raw SQL in routes; do not merge the dataclass/enum layer (`models.py`) with the ORM layer (`database.py`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Add each type | Existing product; type in the 6-value set, non-blank value | Row persists in `product_identifiers` with that type/value; snapshot returned | No error expected |
| Duplicate global pair | `(GTIN, '00012345678905')` already on product A; add same to product B | Rejected; `ValidationError` naming product A | Caught domain error, not `IntegrityError` |
| Same VENDOR_SKU, different vendors | Product A: `(VENDOR_SKU,'X', vendor='Acme')`; product B: `(VENDOR_SKU,'X', vendor='Zed')` | Both persist (vendor-scoped, distinct `vendor_scope`) | No error expected |
| Same value, same vendor scope | Both `(VENDOR_SKU,'X', vendor='Acme')` | Second rejected, `ValidationError` naming the first product | Caught domain error |
| GTIN with vendor supplied | `(GTIN,'X', vendor='Acme')` then `(GTIN,'X', vendor='Zed')` | Second rejected — GTIN is global, vendor ignored (`vendor_scope=''`) | Caught domain error |
| Blank / whitespace value | value `''` or `'   '` | Rejected before insert | `ValidationError` |
| Invalid type | type not in the enum | Rejected before insert | `ValidationError` |
| Unknown product | product_id with no row | Rejected before insert | `ValidationError` |

</intent-contract>

## Code Map

- `app/models.py` -- add `IdentifierType(Enum)` + `VENDOR_SCOPED_IDENTIFIER_TYPES` frozenset (scoping single source of truth). Follows existing `Enum` style (`ItemType`, etc.).
- `app/database.py` -- add `ProductIdentifier(Base)` ORM class (mirrors `Attachment`: integer PK, FK to `products.id`, one-directional `product` relationship, `to_dict()`, `__table_args__` UNIQUE).
- `migrations/versions/` -- new revision `add_product_identifiers_table`, `down_revision='f771284e1478'`. Template: `f771284e1478_add_attachments_table.py` (FK + constraint + index; single `drop_table` downgrade).
- `app/mariadb_catalog_service.py` -- add `add_identifier(...)` and `get_identifiers_for_product(...)`; import `IntegrityError`, `IdentifierType`, `VENDOR_SCOPED_IDENTIFIER_TYPES`, `ProductIdentifier`.
- `tests/unit/test_catalog_service.py` -- add a `TestCatalogServiceIdentifiers` class covering the I/O matrix (uses existing `catalog_service`/`test_storage` fixtures, SQLite).

## Tasks & Acceptance

**Execution:**
- [x] `app/models.py` -- define `IdentifierType(Enum)` with values `GTIN, ASIN, FNSKU, MPN, VENDOR_SKU, INTERNAL` (string value == name) and `VENDOR_SCOPED_IDENTIFIER_TYPES = frozenset({IdentifierType.VENDOR_SKU, IdentifierType.ASIN, IdentifierType.FNSKU})` -- closed type set + scoping authority for the service and DB layer.
- [x] `app/database.py` -- add `ProductIdentifier(Base)`: `id` PK; `product_id` FK→`products.id` NOT NULL indexed; `identifier_type` `String(32)` NOT NULL; `value` `String(255)` NOT NULL; `vendor_scope` `String(255)` NOT NULL server_default `''`; `created_at` write-once; `UniqueConstraint('identifier_type','value','vendor_scope', name='uq_product_identifiers_type_value_scope')`; one-directional `product` relationship; `to_dict()` -- persists typed identifiers with DB-enforced scoped uniqueness (FR7, AD-1/3/9).
- [x] `migrations/versions/<rev>_add_product_identifiers_table.py` -- `create_table` mirroring the ORM (FK, UNIQUE, `ix_product_identifiers_product_id`), `down_revision='f771284e1478'`, downgrade = single `drop_table` -- schema chained from head, stock/other catalog tables untouched (AD-14, NFR9).
- [x] `app/mariadb_catalog_service.py` -- `add_identifier(self, product_id, *, identifier_type, value, vendor=None) -> dict`: coerce `identifier_type` to `IdentifierType` (raise `ValidationError` if invalid); trim `value`, raise `ValidationError` if blank; verify the product exists (else `ValidationError`); compute `vendor_scope = (vendor or '').strip() if identifier_type in VENDOR_SCOPED_IDENTIFIER_TYPES else ''`; insert; on `IntegrityError` rollback, re-query the conflicting row and raise `ValidationError` naming that Product's id; return `to_dict()` snapshot -- caught domain error, never raw `IntegrityError` (FR8). Add `get_identifiers_for_product(self, product_id) -> List[ProductIdentifier]` (dedicated query, ordered by `created_at, id`), matching `get_attachments_for_product`.
- [x] `tests/unit/test_catalog_service.py` -- add `TestCatalogServiceIdentifiers` covering every I/O-matrix row (each type persists; global dup rejected with conflicting-product id in the message and no `IntegrityError`; vendor-scoped same-value-different-vendor both succeed; same-vendor dup rejected; GTIN ignores vendor; blank value, invalid type, unknown product each raise `ValidationError`; `get_identifiers_for_product`).

**Acceptance Criteria:**
- Given an existing Product, when I add identifiers of type GTIN, ASIN, FNSKU, MPN, VENDOR_SKU, and INTERNAL, then each persists in `product_identifiers` with its type (FR7).
- Given `(type, value)` already exists in the same scope on another Product, when I add the same pair, then the add is rejected with a caught `ValidationError` naming the conflicting Product, and no `IntegrityError` reaches the caller (FR8).
- Given two Products and a vendor-scoped type, when each stores the same value under a different vendor, then both persist (AD-9 vendor scoping); when they share the same vendor, the second is rejected.
- Given `nox -s tests`, when the suite runs, then the new identifier unit tests pass and the existing catalog tests remain green.

## Review Triage Log

### 2026-07-24 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 2, low 1)
- defer: 1: (high 0, medium 1, low 0)
- reject: 6
- addressed_findings:
  - `[low]` `[patch]` Non-string `value` (e.g. an integer barcode) is now coerced to `str` before `.strip()` — previously raised a raw `AttributeError` that escaped the ValidationError contract. Added coercion test.
  - `[medium]` `[patch]` Added `IDENTIFIER_MAX_LENGTH` (255) bounds on `value` and `vendor` raised as `ValidationError` before insert — previously an overlong string surfaced as an uncaught MariaDB `DataError` (not `IntegrityError`, so not caught). Follows the `add_attachment` precedent. Added test.
  - `[medium]` `[patch]` The `except IntegrityError` handler now re-raises when the conflict re-query finds no row — previously any non-uniqueness integrity failure (e.g. a concurrently-deleted product FK) was mislabeled as `"already exists on product ?"`. The duplicate message now also names the vendor scope for vendor-scoped conflicts.
  - Rejected (by-design / consistent with established patterns): vendor-scoped type with no vendor collapsing to the `''` sentinel (spec makes vendor inert in 2.1; it arrives in 2.3/7); detached-ORM return from `get_identifiers_for_product` (matches `get_attachments_for_product`); `created_at=None` in the pre-commit snapshot (matches `add_attachment`/`record_purchase`); `str` `product_id` coercion (routes use typed converters); double-rollback on the duplicate path (inner rollback is required before the re-query); FK without `ondelete` (matches `Attachment`).
  - Deferred: SQLite (case-sensitive `BINARY`) vs MariaDB (case-insensitive default collation) uniqueness parity — logged to the deferred-work ledger.

## Design Notes

**Scope key reconciles the AC with AD-9.** The story AC states `(type, value)` uniqueness; AD-9 makes `VENDOR_SKU/ASIN/FNSKU` vendor-scoped. A single `UNIQUE(identifier_type, value, vendor_scope)` satisfies both: within one scope the pair is unique (AC), while vendor-scoped types differ by `vendor_scope` and may repeat across vendors (AD-9). Global types force `vendor_scope=''`, so the vendor argument is inert for them.

**SQLite vs MariaDB invariants (two-tier note).** Unit tests on SQLite DO enforce the `UNIQUE` and `NOT NULL` constraints this story depends on, so the domain-error conversion is fully exercised. SQLite does NOT enforce the FK by default, but the service validates product existence in-app before insert, so no tested behavior relies on FK enforcement. The migration mirrors the ORM; `manage.py db upgrade` confirms the MariaDB round trip.

**Conflict message shape (golden example):**
```python
existing = (session.query(ProductIdentifier)
            .filter_by(identifier_type=itype.value, value=value, vendor_scope=scope)
            .first())
raise ValidationError(
    f"Identifier {itype.value} '{value}' already exists on product "
    f"{existing.product_id}.", field='value', value=value)
```

## Verification

**Commands:**
- `PATH="$HOME/.pyenv/versions/3.13.12/bin:$PATH" venv/bin/nox -s tests` -- expected: all tests pass, including the new `TestCatalogServiceIdentifiers`.
- `venv/bin/python manage.py db upgrade && venv/bin/python manage.py db downgrade -1` -- expected: the new migration applies and reverses cleanly against the configured DB (creates/drops `product_identifiers`, leaving other tables intact). If no DB is configured in this environment, inspect the generated migration for ORM parity instead.

## Auto Run Result

Status: done

**Summary.** Added the `ProductIdentifier` entity so a Product can carry multiple typed identifiers (`GTIN, ASIN, FNSKU, MPN, VENDOR_SKU, INTERNAL`) and be looked up by any code printed on it (FR7), with DB-enforced scoped uniqueness (AD-9: `VENDOR_SKU/ASIN/FNSKU` vendor-scoped, others global) surfaced through `CatalogService.add_identifier` as a caught `ValidationError` naming the conflicting Product — never a raw `IntegrityError` (FR8). No UI/routes (out of scope for 2.1).

**Files changed.**
- `app/models.py` — `IdentifierType(Enum)` + `VENDOR_SCOPED_IDENTIFIER_TYPES` (type set + scoping authority).
- `app/database.py` — `ProductIdentifier(Base)` ORM (FK to `products`, `UNIQUE(identifier_type, value, vendor_scope)`, `to_dict()`).
- `migrations/versions/3beb9dff5e41_add_product_identifiers_table.py` — chained migration (head `f771284e1478`), mirrors the ORM; single `drop_table` downgrade.
- `app/mariadb_catalog_service.py` — `add_identifier` + `get_identifiers_for_product`; `IDENTIFIER_MAX_LENGTH` bound; import of `IntegrityError`/models.
- `tests/unit/test_catalog_service.py` — `TestCatalogServiceIdentifiers` (12 cases incl. the review-driven length/coercion tests).

**Review findings.** 3 patches applied (1 low, 2 medium: non-string coercion, length bounds, IntegrityError re-raise + scoped conflict message); 1 medium deferred (SQLite↔MariaDB collation parity → deferred-work ledger); 6 rejected as by-design/consistent with established patterns. No intent gaps, no spec repairs.

**Verification.** `nox -s tests`: **436 passed, 305 deselected** (green; +new identifier tests, existing catalog tests intact). During step-03 verification I found and fixed a stray misplaced assertion the implementer's edit had relocated out of `test_get_attachment_data`. The `manage.py db upgrade` round trip was not run (no DB configured in this environment); the migration was confirmed by inspection to mirror the ORM exactly.

**Residual risks.** (1) The deferred collation parity means uniqueness case-semantics differ test↔prod for case-varying values — latent, no live caller yet. (2) Story 2.1 has no route/UI wiring; the service surface is exercised only by unit tests until later epics consume it.
