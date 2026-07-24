# Deferred Work Ledger

## Deferred from: code review of 1-3-product-create-edit-detail (2026-07-23)

- **Per-request SQLAlchemy engine/pool creation (systemic).** In production, `_get_storage_backend()` returns a fresh unconnected `MariaDBStorage()` (`engine=None` until `connect()`, which routes never call), so both `CatalogService` and the pre-existing `InventoryService` fall back to `_create_engine()` — building a new pooled engine from class-level `Config.SQLALCHEMY_DATABASE_URI` on every request, never disposed, and ignoring `storage.database_url`. Fix belongs at the app level (shared/app-scoped engine or connected storage singleton) and should cover both services at once. Refs: `app/mariadb_catalog_service.py:51-58`, `app/mariadb_inventory_service.py:140`, `app/main/routes.py:20-28`.
