# Implementation Plan: Bulk Move to a Single Location by Scanning

**Branch**: `robot-army/issue-223-bulk-move-to-single-location` | **Date**: 2026-11-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/069-bulk-move-single-location/spec.md`

## Summary

IDs scanned back to back on a move page form a *scanned group* that waits for one
destination; the next location queues the whole group, and a sub-location scanned straight
after applies to the whole group. This is the handed-over group from 026 (`pendingMoves`,
`handleBulkLocationInput`, `bulkGroupIds`, `applySubLocationToGroup`) reached by scanning
instead of by a list page, so almost all of the machinery already exists. The change is in
`MoveManager`'s state machine (one new state, `group_location`), a small client-rendered
"awaiting a destination" list in the two move templates, the product subclass's
`isLocation`, the e2e scan waiter, and the user manual. No server change.

## Technical Context

**Language/Version**: JavaScript (browser, no build step) and Jinja2 templates; Python 3.13 for tests

**Primary Dependencies**: Bootstrap 5 (already loaded); Playwright for e2e

**Storage**: N/A — the group lives only in the page, like the queue

**Testing**: `nox -s e2e` (Playwright); `nox -s tests` must stay green (no Python change expected)

**Target Platform**: Desktop browser and the TC52 handheld Move screen

**Project Type**: Flask web application

**Performance Goals**: N/A (one lookup per scanned subject, as today)

**Constraints**: Existing one-at-a-time flow and handoff flow unchanged (FR-006, FR-015); batch-move endpoints unchanged (FR-013)

**Scale/Scope**: Groups of a few to a few dozen subjects

## Constitution Check

| Principle | Assessment |
|---|---|
| I. Simplicity First | Pass. Reuses 026's pending-group machinery instead of adding a parallel mode; no toggle, no new endpoint. One new state name. |
| II. Layered Architecture | Pass. Client-side only; batch-move routes/services untouched. |
| III. Exact Numerics | N/A — no measurements. |
| IV. Test Discipline | Pass. New behaviour covered by e2e tests run through `nox -s e2e`; waits are on observable state (group row count, queue count, alert count) via `waits.scan_on_move_page`; no fixed waits. Tests asserting the replaced abandon rule are rewritten, not deleted. |
| V. MariaDB source of truth | N/A — no schema or storage change. |
| VI. Item history invariants | Pass. Moves still go through the existing batch-move endpoints, which preserve the one-active-row rule. |
| Workflow: screenshots | Template/JS changes → regenerate screenshots and commit those that actually change (`move_items.png`), verified with `nox -s screenshots_verify`. |

Post-design re-check: unchanged — the design adds no layer, dependency or server code.

## Project Structure

### Documentation (this feature)

`spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/move-manager-group.md`,
`quickstart.md`, `tasks.md` in `specs/069-bulk-move-single-location/`.

### Source Code (files touched)

- `app/static/js/move-manager.js` — `group_location` state, group add/remove, rendering, DONE/hint/Clear All handling
- `app/static/js/product-move.js` — `isLocation` treats `group_location` as a location-waiting state
- `app/templates/move/_scan_move.html` and `app/templates/handheld/move.html` — the "awaiting a destination" list markup and updated instructions
- `tests/e2e/waits.py` — `scan_on_move_page` transitions for the new state
- `tests/e2e/test_bulk_scan_group.py` (new) — the feature's tests; updates to `test_product_move.py`, `test_move_long_session.py` and any other test asserting the abandon rule
- `docs/user-manual.md` — Move Items / Move Products workflow
- `specs/057-product-location-move/contracts/move-manager.md` is a frozen spec and is **not** edited; the new contract is in this feature's `contracts/`.

**Structure Decision**: Existing Flask app layout; no new modules.

## Complexity Tracking

None.
