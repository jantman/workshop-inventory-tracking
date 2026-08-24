# Implementation Plan: Fix the item hand-off into Move and Shorten

**Branch**: `issues/106` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/026-fix-bulk-move-handoff/spec.md`

## Summary

Four controls hand items to a working page and all four lose them: both Bulk Move Selected
buttons, and the row-level Move and Shorten actions. The receiving pages never read what they
were handed. The fix is to settle on one hand-off convention (`ja_id`, comma-separated, a
single item being a list of one), have both pages read it, and give the Move page one new
entry state in which a preselected group is assigned a single destination and then queued as
ordinary moves — after which every existing downstream path is unchanged.

Issue #107 rides along because it lives in the state machine this work must touch. Its cause is
not established; three code paths reproduce the report and reproduction is the first task, not
an assumption. See [research.md](./research.md) R3.

The coverage requirements (FR-019 to FR-022) are load-bearing, not paperwork: the reason five
defects shipped is that every move test navigates to the page directly and so bypasses the only
broken part. See [research.md](./research.md) R4.

## Technical Context

**Language/Version**: Python 3.13; browser-side ES modules, no build step

**Primary Dependencies**: Flask 3.1.x (app-factory), Jinja2 + Bootstrap 5.3.2, SQLAlchemy 2.0.x.
No new dependency is introduced by this feature.

**Storage**: MariaDB via the existing `Storage` ABC. **This feature adds no schema change and no
Alembic revision** — it moves items through the paths that already exist.

**Testing**: pytest via `nox -s tests`; Playwright via `nox -s e2e`. Run detached, budget 20
minutes (`CLAUDE.md`); the suite is ~13m 45s warm against a 15-minute gate.

**Target Platform**: single Flask app on a home LAN, one user, no authentication.

**Project Type**: server-rendered web application with vanilla-JS page controllers.

**Performance Goals**: none set. Nothing here is on a measured hot path, and per Principle I no
optimization is warranted without a measurement. The one bounded concern is that a large
preselected group establishes each item's current location before the page settles; the
existing per-item fetch in `finalizeCurrentMove` is reused rather than replaced, and if that
proves slow *in use* it becomes its own change with a measurement behind it.

**Constraints**: e2e tests must wait on observable state, never elapsed time (Principle IV). A
test session must leave the working tree clean. Touching `app/templates/**` or
`app/static/js/**` requires regenerating documentation screenshots.

**Scale/Scope**: 4 JS files, 2 templates, 2 routes, plus tests. No models, no services, no
storage layer changes.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1. Both passes clean.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | **Pass.** One query-parameter convention rather than two; one new state rather than a parallel bulk pipeline; no cap, knob, or abstraction added. Explicitly rejected as speculative generality: supporting both parameter names, making `scannerDelay` configurable, a per-row destination editor. Scope was *widened* during specification (three sibling hand-offs plus #107), which is worth naming — the justification is that they are the same defect in the same seam and fixing one while leaving three identical dead links is the larger long-term cost. |
| **II. Layered Architecture Boundaries** | **Pass.** Both routes stay thin: they read a query parameter and pass a list to the template. No ORM query or raw SQL enters a route. No new layer, repository, or DTO tier. Item lookup continues through the existing `/api/items/{ja_id}` endpoint. |
| **III. Exact Numerics** | **Not engaged.** This feature touches identifiers and locations — strings — and no measured quantity. No `Decimal` is introduced and no `float` is introduced. |
| **IV. Test Discipline Through Nox** | **Pass, and directly advanced.** All runs via `nox`. No `wait_for_timeout`, `time.sleep`, or `networkidle` is added; waits use `expect()` and the existing `waits.py` helpers (see research R4 for the pattern per transition). No new pytest marker is needed. FR-019 to FR-022 exist to close the coverage seam that let these defects ship, which is this principle's stated purpose — "write the test that would have caught the bug". |
| **V. MariaDB Is the Source of Truth** | **Pass.** No schema change, therefore no migration. Nothing here treats Sheets as live storage. |
| **VI. Item Lifecycle and History Invariants** | **Engaged and constrained.** This touches the move and shorten paths. Preselected items become ordinary queued moves and execute through the existing batch-move path, so the one-active-row-per-JA-ID invariant is preserved by reuse rather than by new code. Two obligations follow: inactive items must be rejected from a hand-off (FR-005) rather than queued, and the existing active-status and history e2e tests must still pass. |

**Operating context**: the hand-off carries data between the app's own pages for one trusted
user on a LAN. Per the constitution's threat model, handed-off JA IDs are validated because a
bad identifier breaks the move, not because it might be hostile. No sanitization layer is added.

**Workflow gates**: this is a non-trivial code change, so it lands on `issues/106` via pull
request. It modifies `app/templates/**` and `app/static/js/**`, so documentation screenshots
must be regenerated with `nox -s screenshots_headless` and committed alongside — and per
`CLAUDE.md`, screenshot churn should be measured before anything is committed.

## Project Structure

### Documentation (this feature)

```text
specs/026-fix-bulk-move-handoff/
├── spec.md
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── handoff.md       # Phase 1 output — the hand-off and page-state contract
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── main/
│   └── routes.py                       # inventory_move(), inventory_shorten(): read ja_id
├── templates/inventory/
│   ├── move.html                       # render preselected items for the page controller
│   └── shorten.html                    # prefill #source-ja-id / name="source_ja_id"
└── static/js/
    ├── inventory-move.js               # new bulk_location entry state; #107 fixes
    ├── inventory-shorten.js            # consume the prefilled item
    ├── inventory-list.js               # bulkMoveSelected(): items= -> ja_id=
    ├── inventory-search.js             # handleBulkMove(): unchanged name, shared helper
    └── components/
        ├── item-actions.js             # showMoveDialog / showShortenDialog
        └── inventory-table.js          # row dropdown Move / Shorten hrefs

tests/
├── unit/
│   └── test_routes.py                  # route-level hand-off parsing
└── e2e/
    ├── test_bulk_move_handoff.py       # NEW — drives the real controls (FR-019)
    ├── test_move_long_session.py       # NEW — 14-pair session, no-newline path (FR-020/021)
    ├── pages/                          # page objects for the list/search Options menu
    └── waits.py                        # extend only if a transition needs a new signal
```

**Structure Decision**: the existing layout is used as-is. This is a defect fix inside a
server-rendered Flask app with per-page vanilla-JS controllers; it introduces no new module,
package, or directory beyond two e2e test files. Route changes stay in the `main` blueprint,
page behavior stays in the per-page controller that already owns it, and the two shared
components (`item-actions.js`, `inventory-table.js`) are edited in place because they are
already the single source of the row-action links.

## Complexity Tracking

> No Constitution Check violations. Nothing to justify.

The two judgment calls worth recording, neither of which is a violation:

| Call | Why | What bounds it |
|---|---|---|
| Scope covers four hand-offs and #107, not just issue #106 | Same defect in the same seam; fixing one of four identical dead links leaves three traps and a second chance to re-split the convention | Row-level Duplicate is explicitly out of scope despite appearing to share the defect (spec, Assumptions); bulk deactivate stays unimplemented |
| #107's fix targets a failure class rather than one trigger | Root cause is unestablished and three paths reproduce the report; picking one would be guesswork | Reproduction precedes any behavior change; no state-machine rewrite; `scannerDelay` is not made configurable |
