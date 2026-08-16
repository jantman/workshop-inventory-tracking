# Implementation Plan: Delete Several Product Photos at Once

**Branch**: `issues/96` | **Date**: 2026-08-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/015-bulk-delete-attachments/spec.md`

## Summary

Pruning an over-captured product gallery currently costs one trash-button press and one full page
reload per image. This adds a checkbox to every tile in the product **Attachments** card, a
select-all, and a single "Delete Selected (N)" button that confirms once and then deletes the
selection — and applies the same two corrections to the inventory item photo gallery, which has the
checkboxes already but no select-all and a confirmation for every photo in the batch.

**The approach is deliberately thin: no new endpoint, no service change, no schema change, no
migration, no Python.** The browser calls the existing `DELETE /api/attachments/<id>` once per
selected attachment, sequentially. Everything else is template markup and two JavaScript files. See
[research.md](./research.md) §1 for why a bulk endpoint was rejected.

## Technical Context

**Language/Version**: Python 3.13 (untouched here), browser JavaScript (ES2017+, no build step)

**Primary Dependencies**: Flask 3.1.x, Jinja2, Bootstrap 5.3.2 — all already present; this feature
adds none

**Storage**: MariaDB via SQLAlchemy 2.0.x. **No schema change and no Alembic revision** — see
[data-model.md](./data-model.md)

**Testing**: Playwright E2E through `nox -s e2e`. No new unit tests, because there is no new Python;
see [research.md](./research.md) §8

**Target Platform**: Server-rendered web UI on a home LAN, one user, desktop and phone browsers

**Project Type**: Flask web application, server-rendered

**Performance Goals**: None. The realistic worst case is a couple of dozen thumbnails on one page;
deletes are issued one at a time on purpose ([research.md](./research.md) §2)

**Constraints**: No frontend framework or build step (constitution, Technology Constraints). Existing
DOM hooks in the Attachments card and the photo gallery are load-bearing for the E2E suite and must
keep their names — see [contracts/README.md](./contracts/README.md)

**Scale/Scope**: Three files changed, two E2E test files extended, one screenshot regenerated

## Constitution Check

*GATE: passed before Phase 0, re-checked after Phase 1 design — see the re-check at the end.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** (non-negotiable) | **Pass, and it is the governing principle here.** No new endpoint, no new service method, no abstraction, no configuration knob, no new dependency. Issue #96 offered a bulk endpoint or a loop over the existing one; the loop is chosen because at this scale it is genuinely simpler, and the constitution forbids optimizing without a measurement. Story 3 is a *deletion* of duplicated confirmation logic, not an addition. |
| **II. Layered Architecture Boundaries** | **Pass, vacuously.** No Python changes at all — no route, no service, no storage, no model. The layering cannot be violated by a change that does not cross it. |
| **III. Exact Numerics** | **Not applicable.** No measurement, dimension or quantity is read or written. The only number is a count of selected tiles. |
| **IV. Test Discipline Through Nox** | **Pass, with obligations.** Coverage is E2E, run via `nox -s e2e` with a ≥15-minute timeout. No new pytest marker. All waits must be on observable state — no `wait_for_timeout`, no `networkidle` (see [quickstart.md](./quickstart.md) for the specific signals). The run must leave the working tree clean. |
| **V. MariaDB Is the Source of Truth** | **Pass.** No schema change, so no Alembic revision — which is the tell that the plan is right, not an omission. Deletion still goes through `PhotoService`, so photo-byte reclamation is inherited, not reimplemented (FR-011). |
| **VI. Item Lifecycle and History Invariants** | **Not applicable.** Nothing here touches JA IDs, active rows, shortening history or parent-child links. Product attachments and item photos carry no history semantics. |
| **Operating Context / Threat Model** | **Pass.** CSRF stays as it is — the attachment route is already called through `csrfFetch` and continues to be. No new validation layer, no hardening, nothing added against an attacker who does not exist. |
| **Development Workflow** | **Obligations.** Feature branch + PR (`issues/96`) — required, since this is a non-trivial code change. `app/templates/**` and `app/static/js/**` change, so screenshots MUST be regenerated and committed, and `nox -s screenshots_verify` must pass. |

**Gate result: PASS.** No violations, so [Complexity Tracking](#complexity-tracking) is empty.

One judgment call worth stating rather than burying: **the bulk delete confirms and the single
delete does not.** That is not an inconsistency introduced by carelessness — issue #96 asks for the
confirmation, FR-012 freezes the single delete's behavior, and one tile is a cheap mistake to notice
while a selection is not. It is recorded in the spec's Assumptions so a later reader does not
"fix" it in either direction.

## Project Structure

### Documentation (this feature)

```text
specs/015-bulk-delete-attachments/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: decisions, with what was rejected
├── data-model.md        # Phase 1: no schema change; transient client state
├── quickstart.md        # Phase 1: how to validate, automated and by hand
├── contracts/
│   └── README.md        # Phase 1: consumed HTTP contracts + new DOM hooks
├── checklists/
│   └── requirements.md  # Spec quality checklist (all pass)
└── tasks.md             # Phase 2 — NOT created by /speckit-plan
```

### Source Code (repository root)

```text
app/
├── templates/product/
│   └── detail.html                    # MODIFIED: per-tile checkbox; select-all +
│                                      #   "Delete Selected" toolbar above the grid
└── static/js/
    ├── product-attachments.js         # MODIFIED: selection wiring, one confirmation,
    │                                  #   sequential delete loop, partial-failure path
    └── photo-manager.js               # MODIFIED: select-all; split deletePhoto so the
                                       #   batch confirms once instead of N+1 times

tests/e2e/
├── test_product_attachments.py        # MODIFIED: selection, select-all, bulk delete
└── test_photo_upload.py               # MODIFIED: item gallery select-all + one confirm
                                       #   (or a sibling file if it reads better there)

docs/images/screenshots/
└── user-manual/photo_gallery.png      # REGENERATED via nox -s screenshots_headless
```

**Not touched, and deliberately so**: `app/product/routes.py`, `app/photo_service.py`,
`app/database.py`, `app/main/routes.py`, `migrations/`. If a task starts editing one of these, the
plan has been misread — the whole point of [research.md](./research.md) §1 is that the backend
already does this correctly.

**Structure Decision**: The existing Flask layout. This feature lives entirely in the presentation
layer (`app/templates/`, `app/static/js/`) plus its E2E coverage, which is exactly what a change to
selection-and-confirmation UI should touch.

## Implementation Notes

The detail that is easy to get wrong, gathered in one place so `/speckit-tasks` can turn it into
steps.

### Product Attachments card (`detail.html` + `product-attachments.js`)

- The tile checkbox goes in the card-body row that already holds the filename and the trash button —
  **not** inside the `<a>` wrapping the thumbnail, or ticking it navigates to the full image.
- Render the select-all / "Delete Selected" toolbar only when the product has at least one
  attachment (`{% if attachments %}`), so it does not appear over an empty grid.
- `#no-attachments` must stay **absent** while attachments exist. An existing E2E test asserts
  `to_have_count(0)` on it; turning it into a permanently-present hidden element breaks that test and
  the contract in [contracts/README.md](./contracts/README.md).
- Delete loop: confirm once → `for` over the checked ids, `await` each `csrfFetch` **one at a time**
  → treat `204` and `404` as removed, anything else as failed. Then: no failures ⇒
  `window.location.reload()`; any failure ⇒ remove the removed tiles, leave the rest, and put the
  message through the existing `showAlert` into `#attachment-alerts`.
- Disable the delete button while the batch is in flight, so a second press cannot start a second
  loop over ids that are already being deleted.
- Leave `.delete-attachment-btn`, upload, and paste exactly as they are (FR-012, FR-013).

### Item photo gallery (`photo-manager.js`)

- Extract the removal from `deletePhoto` into a confirmation-free helper. `deletePhoto` keeps its own
  `confirm` and calls the helper (FR-017 — the single-photo path must not change). `deleteSelectedPhotos`
  confirms once, then calls the helper per selected photo (FR-015).
- Collapse the per-photo success toast for the batch into one summary toast. Twelve toasts for one
  action is the same defect as twelve confirmations; the single-photo delete keeps its single toast.
- Put the select-all checkbox inside the existing `.gallery-actions` block, which is already omitted
  when `isReadOnly` — that is how FR-016's read-only rule is satisfied, rather than by a new
  condition.
- Iterate over a **copy** of the selected list. The helper splices entries out of `this.photos`, and
  mutating the array being iterated is how a batch silently skips half its members.

### Tests

- Assert the *number* of confirmations, not just their text — the N+1 bug this fixes passes any test
  that only checks that a dialog appeared. Register a `page.on('dialog', ...)` handler that records
  messages and assert exactly one; `page.once` would leave a second prompt un-dismissed and hang the
  page instead of failing cleanly.
- Wait on state, never on a duration. The success path reloads, so `expect(CARDS).to_have_count(n)`
  is the signal. Before any negative assertion, establish the grid with a positive `expect` first —
  a `count()` taken mid-reload reads zero and passes trivially (`CLAUDE.md`).

## Complexity Tracking

No constitution violations, so nothing to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | | |

## Post-Design Constitution Re-check

Re-evaluated after Phase 1. **PASS, unchanged.**

The design produced no new endpoint, no new module, no new dependency, no new abstraction and no
migration. It removes duplicated confirmation logic in `photo-manager.js` rather than adding a layer
on top of it. The three obligations it carries out of the gate — E2E coverage through nox with
state-based waits, regenerated screenshots, and a feature branch with a PR — are workflow
requirements, not design compromises.
