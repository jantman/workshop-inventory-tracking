# Deferred Work Ledger

## Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)

- **Per-request SQLAlchemy engine/pool creation (systemic).** In production, `_get_storage_backend()` returns a fresh unconnected `MariaDBStorage()` (`engine=None` until `connect()`, which routes never call), so both `CatalogService` and the pre-existing `InventoryService` fall back to `_create_engine()` — building a new pooled engine from class-level `Config.SQLALCHEMY_DATABASE_URI` on every request, never disposed, and ignoring `storage.database_url`. Fix belongs at the app level (shared/app-scoped engine or connected storage singleton) and should cover both services at once. Refs: `app/mariadb_catalog_service.py:51-58`, `app/mariadb_inventory_service.py:140`, `app/main/routes.py:20-28`.

- source_spec: `_bmad-output/implementation-artifacts/2-1-typed-identifier-entity-and-uniqueness.md`
  summary: `product_identifiers` uniqueness is case-sensitive under SQLite (unit tests) but case-insensitive under MariaDB's default collation, so identifier case-semantics differ between test and prod.
  evidence: SQLite's default `BINARY` collation is case-sensitive; MariaDB's default `utf8mb4_*_ci` is case-insensitive. The `uq_product_identifiers_type_value_scope` index therefore enforces different uniqueness for case-differing values (e.g. `B01abc` vs `B01ABC`) in prod vs the passing unit tests. No live caller yet; resolving well needs a per-type case-semantics decision (numeric GTIN / uppercase INTERNAL & ASIN are case-stable; MPN / VENDOR_SKU may not be) — e.g. pin a binary collation on the key columns or fold case explicitly.
