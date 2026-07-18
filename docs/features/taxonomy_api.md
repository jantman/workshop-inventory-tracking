# Feature: Taxonomy API

**IMPORTANT:** You MUST read and understand the instructions in the `README.md` document in this directory, and MUST ALWAYS follow those requirements during feature implementation.

## Requirements

An API endpoint should be added, if not already present, to return the hierarchical materials taxonomy. Then add support for retrieving this taxonomy in `app/api_client.py` and document the API endpoint in the "REST API" section of the user guide. Add/update tests as applicable.

## Implementation Plan

### Background / findings

- The hierarchical materials taxonomy is stored in the `material_taxonomy` table, modeled by `MaterialTaxonomy` (`app/database.py:615`). It is a single self-referential table with a 3-level scheme: `level` 1 = Category, 2 = Family, 3 = Material; `parent` holds the parent row's `name` (categories have `parent = NULL`).
- The canonical tree builder is `MariaDBMaterialsAdminService.get_taxonomy_overview(include_inactive=False)` (`app/mariadb_materials_admin_service.py:52`), which the admin UI uses. It returns a nested list of category → `children` (families) → `children` (materials), each node carrying `id, name, level, active, notes, sort_order` (plus `parent` on families/materials and `aliases` on materials).
- An existing endpoint `GET /api/materials/hierarchy` (`app/main/routes.py:1200`) also returns a tree, but: (a) its docstring says "(for testing)" which is **inaccurate** — it is production code consumed by the material-selector autocomplete (`app/static/js/material-selector.js:96`); (b) it reimplements tree-building inline; (c) its shape is frontend-tailored (`hierarchy`/`families`/`materials` + a `summary` block) and omits `id`/`active`/`aliases`/`parent`/`sort_order`; (d) it has **no test coverage**.
- Decision (approved): add a clean, general-purpose public endpoint rather than blessing the frontend-tailored shape. Leave `/api/materials/hierarchy` behavior untouched (the frontend depends on it) but correct its misleading docstring.

### Scope (single Milestone — prefix `Taxonomy API`)

**Task 1 — New endpoint `GET /api/taxonomy`** (`app/main/routes.py`)
- Add `@bp.route('/api/taxonomy')` returning the canonical tree via `MariaDBMaterialsAdminService(_get_storage_backend()).get_taxonomy_overview(...)` (same service/storage pattern as `app/admin/routes.py`).
- Optional query param `include_inactive` (`true`/`false`, default `false`), matching the service's capability.
- Response envelope follows the established convention: `{"success": true, "taxonomy": [...]}` on success; `{"success": false, "error": "..."}` with HTTP 500 on failure.
- Fix the stale `"""...(for testing)"""` docstring on the existing `materials_hierarchy()` route to accurately state it powers the material-selector UI.

**Task 2 — Client support** (`app/api_client.py`)
- Add a frozen `TaxonomyResult` dataclass (`success`, `taxonomy: list`, `errors`, `http_status`, `raw`) mirroring the existing result dataclasses.
- Add `WorkshopInventoryClient.get_taxonomy(*, include_inactive=False) -> TaxonomyResult`, calling `GET /api/taxonomy`, following the existing HTTP-error-never-raises / network-error-raises contract and error-shaping used by the other methods.
- Export `TaxonomyResult` in `__all__`.

**Task 3 — Documentation** (`docs/user-manual.md`)
- Add a `GET /api/taxonomy` subsection under "REST API" documenting the query param, response shape (with a nested example), node fields, and status codes.
- Update the "Python client" subsection to mention `get_taxonomy(...)` / `TaxonomyResult`.

**Task 4 — Tests**
- Unit tests in `tests/unit/test_api_client.py`: success, `include_inactive` param propagation, HTTP-error → `success=False`, non-JSON/non-dict handling (mirroring existing patterns).
- E2E tests in `tests/e2e/test_api_client.py` (and/or a route test): hit the live endpoint, assert the nested structure and envelope, and exercise the client's `get_taxonomy()` against the running server.

### Completion steps (per features README)

1. Run the full unit suite and the full e2e suite via `nox` (e2e with a ≥15-minute Bash timeout) and ensure **all** tests pass.
2. Update any other affected docs (`README.md`, deployment/testing/troubleshooting guides) if applicable.
3. Update this feature document with progress.
4. Commit on a feature branch with the `Taxonomy API - 1.x` prefix; open a PR when complete.

### Progress

**Status: Implementation complete; all tests passing.** (Milestone `Taxonomy API - 1`)

- ✅ Task 1 — Added `GET /api/taxonomy` (`app/main/routes.py`) reusing `MariaDBMaterialsAdminService.get_taxonomy_overview()`, with optional `include_inactive` query param and a `_normalize_taxonomy_aliases()` pass that converts the raw comma-separated `aliases` column into a proper list. Corrected the stale `(for testing)` docstring on `materials_hierarchy()`.
- ✅ Task 2 — Added `TaxonomyResult` dataclass and `WorkshopInventoryClient.get_taxonomy(include_inactive=False)` to `app/api_client.py`; exported `TaxonomyResult` in `__all__`.
- ✅ Task 3 — Documented `GET /api/taxonomy` in `docs/user-manual.md` (REST API section + Python client example/summary). Also updated `README.md` feature blurb and `docs/development-testing-guide.md` public-surface list.
- ✅ Task 4 — Added unit tests (`TestGetTaxonomy` in `tests/unit/test_api_client.py`) and e2e tests (`TestApiClientTaxonomy` in `tests/e2e/test_api_client.py`).
- ✅ Full unit suite: 350 passed.
- ✅ Full e2e suite: 304 passed, 1 skipped (ran to completion in ~19 min).

### Implementation note

`aliases` normalization: `get_taxonomy_overview()` (shared with the admin UI) emits the raw `MaterialTaxonomy.aliases` string. Rather than change that shared method (and risk the admin UI), the new endpoint normalizes aliases to a list locally, so the public API contract is consistently list-typed.

### Open questions

None currently.
