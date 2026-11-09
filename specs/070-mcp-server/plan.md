# Implementation Plan: MCP Server

**Branch**: `robot-army/issue-222-mcp-server` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/070-mcp-server/spec.md`

## Summary

Serve an MCP endpoint at `POST /mcp` from the existing Flask app: a new `mcp` blueprint
speaking stateless Streamable HTTP with JSON responses (no SDK, no new dependency), and a
small in-code tool registry whose handlers call the same code the web operations use —
`InventoryService` / `CatalogService` directly where the logic lives there, and helpers
extracted (mechanically, behavior-preserving) from the route functions where the logic
currently sits inline (search-filter building, edit, shorten, move, label printing).
24 tools cover the ten capabilities the issue names plus reference lookups. Documented in
the user manual with connection steps for Claude Code and Claude Desktop.

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: Flask 3.1 (existing). No new packages (research R1).

**Storage**: MariaDB via existing services; no schema change, no migration.

**Testing**: nox — `tests` (unit, SQLite, `client` fixture), `e2e` (live server + Playwright)

**Target Platform**: the existing Linux container behind gunicorn on the LAN

**Project Type**: web service (server-rendered Flask app + JSON APIs)

**Performance Goals**: none beyond "a tool call is as fast as the page doing the same thing"

**Constraints**: parity with web validation (FR-006); exact decimals (FR-007); item history
invariants (FR-008); sync WSGI only

**Scale/Scope**: one user, one or two assistant clients; 24 tools

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Simplicity First | **Pass.** No SDK, no ASGI server, no sessions, no streaming: four JSON-RPC methods on one route. Tool registry is a list of dataclass entries, not a plugin system. Extracted helpers stay in their route modules rather than spawning a new service layer. Paging is a slice of the existing result list. |
| II. Layered Architecture | **Pass, with a noted shortcut.** The MCP blueprint is a route module: it does no ORM or SQL, it calls services and the existing route-level helpers. The helpers it reuses (`_process_item_creation`, the newly-extracted `_edit_item_from_form`, `_shorten_from_form`, `_move_items`, label helpers) already live in route modules; importing them across blueprints is the minimal way to guarantee parity. Moving them into a service is the tidier long-term shape and is out of scope (see Complexity Tracking). Storage comes from `app.config['STORAGE_BACKEND']` via the existing `_get_*_service()` factories. |
| III. Exact Numerics | **Pass.** Measurement inputs are passed as strings to the existing `_parse_dimension_value` / form parsers; numbers given as JSON numbers are converted with `str()` first, never through float arithmetic in new code. Outputs are decimal strings. (Existing `float` usage inside `_parse_item_from_form` / `shorten_item` is pre-existing and untouched.) |
| IV. Test Discipline | **Pass.** Unit tests through the `client` fixture; one e2e file using `expect()` waits only and `live_server` seeding; no new markers; tests run via nox. Printing is short-circuited by `TESTING`. |
| V. MariaDB source of truth | **Pass.** No schema change. |
| VI. Item lifecycle & history | **Pass.** Shorten/move/edit/add tools call the same code paths as the web; no tool deletes. An e2e test shortens via MCP and asserts the history in the UI. Existing e2e active-status/history tests continue to cover the refactored route paths. |
| Threat model | **Pass.** No auth (constitution forbids adding one); `csrf.exempt` like the existing JSON APIs; no Origin hardening (research R7). |
| Screenshots | Not triggered: no template/CSS/JS change. |

Post-design re-check: unchanged — Phase 1 introduced no new dependency, storage or layer.

## Project Structure

### Documentation (this feature)

`specs/070-mcp-server/`: `plan.md`, `research.md`, `data-model.md`, `quickstart.md`,
`contracts/mcp-endpoint.md`, `tasks.md` (next phase).

### Source Code

Files a contributor edits for this feature:

- `app/mcp/__init__.py` — blueprint `mcp` (new)
- `app/mcp/routes.py` — `POST /mcp` JSON-RPC handling, version negotiation (new)
- `app/mcp/tools.py` — `Tool` registry, argument checking, `ToolError` (new)
- `app/mcp/item_tools.py`, `app/mcp/product_tools.py`, `app/mcp/lookup_tools.py` — handlers (new)
- `app/__init__.py` — register blueprint, `csrf.exempt` it
- `app/main/routes.py` — extract `_build_search_filter`, `_edit_item_from_form`, `_shorten_from_form`, `_move_items`, `_print_item_label`; add `_item_to_form_data`
- `app/product/routes.py` — extract `_print_product_label`
- `tests/unit/test_mcp_protocol.py`, `tests/unit/test_mcp_item_tools.py`, `tests/unit/test_mcp_product_tools.py` (new)
- `tests/e2e/test_mcp_server.py` (new)
- `docs/user-manual.md` (new "MCP Server" section + TOC), `README.md` (one line)

**Structure Decision**: one new blueprint package beside `main`, `product`, `handheld`,
`admin`, following the existing blueprint layout.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| MCP blueprint imports private helpers from `app.main.routes` / `app.product.routes` (Principle II prefers business logic in services) | Parity (FR-006) requires the tools to run exactly the code the web runs; that code is in route modules today | Moving add/edit/shorten/move into `InventoryService` first would be a large refactor of heavily-tested paths, unrelated to this issue; reimplementing in the tools would break parity |
