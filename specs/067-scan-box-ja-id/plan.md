# Implementation Plan: JA IDs in the Header Scan Box

**Branch**: `robot-army/issue-215-add-ja-id-support-to-the-header-scan` | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/067-scan-box-ja-id/spec.md`

## Summary

Teach the scan path one new rule: a scan that is a JA ID (`JA` + six digits, case-insensitive,
whitespace-tolerant) classifies as `ScanKind.JA_ID`, resolves to a new outcome `'item'`, and
`POST /api/scan` answers it with the URL of that item's edit page. The edit page already handles a
missing JA ID (flash "not found", redirect to the inventory list) and an inactive-only one (it
loads the canonical row), so resolution needs no lookup. Then delete the JA ID Quick Lookup box,
its handler in `main.js`, its CSS, and move its e2e coverage onto the scan box.

## Technical Context

**Language/Version**: Python 3.13; vanilla JS in `app/static/js/`

**Primary Dependencies**: Flask 3.1, Jinja2, Bootstrap 5.3 (no new dependencies)

**Storage**: MariaDB — not touched (no schema change, no new query)

**Testing**: `nox -s tests` (unit: `test_scan_router.py`, `test_scan_resolution.py`, `test_scan_routes.py`), `nox -s e2e` (Playwright)

**Target Platform**: LAN-only Flask web app

**Project Type**: Server-rendered web application

**Performance Goals**: N/A (one regex match per scan)

**Constraints**: Existing scan resolutions must be unchanged (SC-003)

**Scale/Scope**: ~6 source files, 3 unit test files, 2 e2e files, user manual

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Simplicity First | PASS | One new rule, one new outcome, no lookup; net code removed (the lookup box). No new abstraction beyond a sibling grammar module, which is the existing idiom in `scan_router`. |
| II. Layered Architecture | PASS | Grammar in `app/utils/`, kind in `app/models.py`, resolution in `CatalogService`, URL in the route. Route stays thin. |
| III. Exact Numerics | N/A | No measurements. |
| IV. Test Discipline | PASS | Unit tests for classifier/resolution/route; e2e moved onto `#global-scan-input`, waiting on URL (state), seeded via `live_server.add_test_data`. Run via nox. |
| V. MariaDB Source of Truth | N/A | No schema change. |
| VI. Item History Invariants | PASS | Read-only navigation to an existing page; `get_canonical_item` already covers the inactive-only case. Existing `test_edit_inactive_item_via_search.py` keeps covering it via the scan box. |
| Workflow: screenshots | Action | Templates/CSS/JS change → regenerate screenshots, commit only those that actually show the header change (screenshots churn per run). |

**Post-design re-check**: PASS — design below adds no violations.

## Project Structure

### Documentation (this feature)

`spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/scan-contract.md`, `quickstart.md`, `tasks.md` in `specs/067-scan-box-ja-id/`.

### Source Code (files this feature edits)

- `app/utils/ja_id.py` (new) — `normalize_ja_id(scan) -> Optional[str]`
- `app/utils/scan_router.py` — rule 0: JA ID
- `app/models.py` — `ScanKind.JA_ID`; `ScanResolution` docstring gains `'item'`
- `app/catalog_service.py` — `resolve_scan` returns `'item'` for `JA_ID`
- `app/product/routes.py` — `api_scan` maps `'item'` to `main.inventory_edit`
- `app/static/js/scan-capture.js` — comment no longer says "a product"
- `app/templates/base.html` — remove lookup box; scan box title mentions JA IDs
- `app/static/js/main.js` — remove `setupJaIdLookup` and its call
- `app/static/css/main.css` — remove `#ja-id-lookup` rules
- `tests/unit/test_scan_router.py`, `test_scan_resolution.py`, `test_scan_routes.py`
- `tests/e2e/test_ja_id_lookup.py` → rewritten against the scan box; `tests/e2e/test_edit_inactive_item_via_search.py` locator change
- `docs/user-manual.md` — scanning table row

**Structure Decision**: Existing single Flask project layout; no new directories.

## Complexity Tracking

None.
