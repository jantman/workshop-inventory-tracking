# Implementation Plan: Fix Add & Continue With Quantity Greater Than One

**Branch**: `issues/52` (spec directory `010-fix-bulk-add-continue`) | **Date**: 2026-08-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-fix-bulk-add-continue/spec.md`

## Summary

The Add Item form submits twice for one press of **Add & Continue**. The button is
`type="submit"` inside the form *and* carries a click listener that calls
`handleSubmit(null, true)` — with a null event, so nothing calls `preventDefault()`. The click
handler runs, then the click's default action submits the form, firing the `submit` listener and
running the same handler a second time. At quantity 1 the duplication is invisible and
load-bearing. At quantity > 1 both passes take the `await fetch(...)` branch, so two concurrent
bulk creations race — they either collide on JA IDs (error beside the success dialog) or
serialize and record twice the requested items.

The fix collapses the two entry points into one: delete the click listener, derive which button
was pressed from `event.submitter` on the single `submit` listener, and carry that through a
persistent hidden field instead of an appended one. A re-entrancy guard covers repeated presses
and Enter-key submission. Finally, the bulk path learns to honor "continue": when the bulk
label-printing dialog closes after a continue submission, the page navigates back to the Add
form, which is exactly what the single-item path already does via a server redirect.

This is entirely client-side. No route, service, storage, schema, or migration change is needed
or made.

## Technical Context

**Language/Version**: Python 3.13 (unchanged by this work); browser JavaScript (ES2017+, no build
step)

**Primary Dependencies**: Flask 3.1.x, Jinja2 templates, Bootstrap 5.3.2 — all existing. No new
dependency.

**Storage**: MariaDB via the existing `Storage`/`InventoryService` layers. **Untouched** — no
schema change, no Alembic revision.

**Testing**: pytest via `nox` sessions (`tests`, `e2e`). New coverage is end-to-end
(Playwright), because the defect lives in browser event wiring that unit tests cannot reach.

**Target Platform**: Server-rendered Flask app on a home LAN, single user, modern desktop Chrome.

**Project Type**: Web application, server-rendered HTML with progressive-enhancement JavaScript.

**Performance Goals**: None specific. The relevant budget is the e2e suite: it runs in ~8m13s and
must not regress by more than the cost of the new scenarios (target: under 30s added).

**Constraints**:
- E2E tests must wait on observable state, never elapsed time (Constitution IV, `CLAUDE.md`).
- `event.submitter` is required. Baseline across all current browsers; the app targets one
  desktop Chrome on a LAN, and Playwright's bundled Chromium supports it.
- The existing quantity-1 behavior of **Add**, **Add & Continue**, and the quantity > 1 behavior
  of **Add** are all currently correct and covered — they are a regression surface, not a
  target (FR-011).

**Scale/Scope**: Three files changed (`app/static/js/inventory-add.js`,
`app/templates/inventory/add.html`, `tests/e2e/test_bulk_creation.py`). Roughly 40 lines of
production change, most of it deletion.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design — see the bottom of
this section.*

| Principle | Assessment |
|-----------|------------|
| **I. Simplicity First (NON-NEGOTIABLE)** | **PASS.** The change is net-negative in moving parts: one event listener deleted, one runtime DOM append replaced by a static field, one dead method removed. No submission framework, no request-deduplication layer, no queue. The one addition is a boolean re-entrancy flag. |
| **II. Layered Architecture Boundaries** | **PASS (not engaged).** No route, service, or storage code changes. `app/main/routes.py` is read during planning and left alone. |
| **III. Exact Numerics** | **PASS (not engaged).** No measurement parsing, formatting, or comparison is touched. |
| **IV. Test Discipline Through Nox** | **PASS, with obligations.** New tests go in `tests/e2e/test_bulk_creation.py` under the existing `e2e` marker — no new marker to register. Every new wait is an `expect()` or a `wait_for_function` on page state; no `wait_for_timeout`, no `time.sleep`, no `networkidle`. Both `nox -s tests` and `nox -s e2e` must pass. The e2e session gets a 15-minute tool timeout. |
| **V. MariaDB Is the Source of Truth** | **PASS (not engaged).** No schema change, therefore no Alembic revision and no `downgrade` to exercise. |
| **VI. Item Lifecycle and History Invariants** | **PASS, and directly served.** This *is* an add-path integrity fix: today one user action can produce twice the intended active rows. FR-002 and FR-004 encode the invariant. Because the add path changes, the full e2e suite — including the active-status and history tests — must pass, not just the new file. |
| **Operating Context / Threat Model** | **PASS.** CSRF stays as-is: the token is a hidden field inside the form, so it rides along in the `FormData` for the AJAX path unchanged. No hardening added. |
| **Development Workflow / Screenshots** | **PASS with a documented judgment.** The change touches `app/templates/**` and `app/static/js/**`, which triggers `.github/workflows/screenshots.yml`. That workflow is an informational reminder — it stopped diffing in CI because font rasterization differs per machine (issue #77) — and it explicitly blocks nothing. This change alters a `type` attribute and adds a hidden input; neither renders. Screenshots are **not** regenerated, because regeneration would produce byte-different PNGs for zero visual difference. See [research.md](./research.md) D6. |

**Note on a stale constitution claim** (no action taken here, flagged for the author): Constitution
§ Development Workflow states "CI blocks merge on stale screenshots." `.github/workflows/screenshots.yml`
says the opposite in its own header comment and in the body of the comment it posts. The workflow is
the current truth. Correcting the constitution is a governance change outside this feature's scope.

**Post-Phase-1 re-check**: No gate moved. Phase 1 produced no new entities, no contract change
(the existing form and JSON contract are *documented*, not altered), and no new dependency. The
design is smaller than the problem allowed for, which is the outcome Principle I asks for.

## Project Structure

### Documentation (this feature)

```text
specs/010-fix-bulk-add-continue/
├── spec.md                          # Feature specification
├── plan.md                          # This file
├── research.md                      # Phase 0: the seven decisions behind the fix
├── data-model.md                    # Phase 1: why no persistent model changes; client state
├── quickstart.md                    # Phase 1: how to reproduce, verify, and validate
├── contracts/
│   └── add-item-submission.md       # Phase 1: the POST /inventory/add contract as it stands
├── checklists/
│   └── requirements.md              # Spec quality checklist (from /speckit-specify)
└── tasks.md                         # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── static/js/
│   └── inventory-add.js             # CHANGED: single submit path, submitter detection,
│                                    #          re-entrancy guard, continue-after-bulk,
│                                    #          delete dead clearFormForContinue()
├── templates/inventory/
│   └── add.html                     # CHANGED: persistent hidden submit_type field
└── main/
    └── routes.py                    # UNCHANGED (read only; see research.md D5)

tests/
├── e2e/
│   ├── test_bulk_creation.py        # CHANGED: submit-via-continue helper + 4 new tests
│   ├── test_add_item.py             # UNCHANGED (regression surface for quantity-1 continue)
│   ├── pages/add_item_page.py       # UNCHANGED (submit_and_continue keeps working)
│   └── waits.py                     # UNCHANGED (wait_for_modal_shown/hidden already exist)
└── unit/
    └── test_routes.py               # UNCHANGED (regression surface; server behavior is stable)
```

**Structure Decision**: No new modules, directories, or layers. The defect is in existing browser
event wiring, so the change lands in the two files that own that wiring plus the e2e file that
already covers bulk creation through the form (`tests/e2e/test_bulk_creation.py`). Placing the new
tests beside the existing bulk tests keeps the whole quantity-to-create behavior in one file and
lets them reuse `BulkCreationPage`.

## Correction to the record

The `/speckit-specify` commit message (`c8b18a5`) and my summary of it stated that no e2e test
drives the Add form with a quantity above 1. That is wrong: `tests/e2e/test_bulk_creation.py`
has driven bulk creation through the form since the feature landed — eight tests, all clicking
`#submit-btn`. The accurate gap, and the one FR-012 actually names, is narrower: no test uses
**Add & Continue** with a quantity above 1, which is why the button-specific double-submission
was never exercised. FR-012 in the spec is correct as written; only the commit narrative
overstated it.

## Complexity Tracking

> No Constitution Check violations. Table intentionally empty.
