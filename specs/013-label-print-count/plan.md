# Implementation Plan: Label Print Count

**Branch**: `issues/86` (feature directory `013-label-print-count`) | **Date**: 2026-08-11 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-label-print-count/spec.md`

## Summary

Add a **label count** (1–99, default 1) to the four inventory-item label printing dialogs, and repair
the one of those four that has never been able to print.

The printing service already has the mechanism. `generate_and_print_label()` in
`app/services/label_printer.py:76` takes a `num_copies` parameter that builds a list of N identical
images for one `lp` job — and nothing has ever passed it a value other than the default, because
`print_label_for_ja_id()` does not thread it through. So the backend work is threading one integer
from the request body down two function calls, plus validating it at the route. No new printing path,
no new dependency, no schema change, no migration.

The frontend work is a number input on four dialogs, one shared read-and-validate helper so the
bounds and the error text cannot drift apart across them (SC-007), and the payload change from
`{ja_id, label_type}` to `{ja_id, label_type, label_count}`. The repair of the post-bulk-Add dialog
(FR-012) is a separate concern that lands in the same files: swap its invented list of label *sizes*
for the real label types from `/api/labels/types`, and send `label_type` — the field the endpoint has
always required and never received from that dialog.

## Technical Context

**Language/Version**: Python 3.13 (pinned by the nox sessions), vanilla ES2015+ browser JavaScript

**Primary Dependencies**: Flask; `pt_p710bt_label_maker` (`BarcodeLabelGenerator`, `FlagModeGenerator`, `LpPrinter`); Bootstrap 5 modals. No new dependency is introduced.

**Storage**: MariaDB — **not touched**. A label count is a property of one print request, never persisted. No model, no table, no Alembic revision.

**Testing**: `nox -s tests` (pytest unit, network blocked, SQLite through the `Storage` ABC), `nox -s e2e` (Playwright, 15-minute tool timeout, run in the background)

**Target Platform**: Flask app on the workshop LAN, driving a CUPS-attached Sato label printer via `lp`

**Project Type**: Server-rendered Flask web application with per-page vanilla JS

**Performance Goals**: None beyond "the dialog reports the outcome when the run finishes". A bulk run is already one HTTP request per item; this feature does not add a request per copy (see research.md, Decision 2).

**Constraints**: Printing MUST remain short-circuited under `TESTING` / `DISABLE_LABEL_PRINTING` — no test may reach `LpPrinter.print_images()`, which drives real hardware. Label count is a **count**, not a measurement: `int`, not `Decimal` (see Constitution Check III).

**Scale/Scope**: 4 dialogs, 1 endpoint, 2 service functions, 1 new ~30-line JS helper. Maximum 99 copies of one barcode.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment | Verdict |
|-----------|------------|---------|
| **I. Simplicity First** | The count rides on the existing `num_copies` mechanism instead of a new one. No queue or background job for large counts (Assumptions). No caching. The one new abstraction — a shared JS read-and-validate helper — serves **four** existing call sites whose consistency is a stated requirement (SC-007), so it is not speculative generality. The 99 ceiling is a typo guard, not a configuration knob: it is a constant, not a setting. | **PASS** |
| **II. Layered Architecture Boundaries** | The route validates and delegates; all printing logic stays in `app/services/label_printer.py`. No ORM or SQL is involved at all — printing does not read or write the database. | **PASS** |
| **III. Exact Numerics** | `Decimal` governs *physical measurements*. A label count is a cardinality — how many pieces of paper — and `int` is the correct type. Using `Decimal` here would be cargo cult. Fractional counts are rejected, not rounded (FR-004), so no rounding mode arises. | **PASS** (principle does not apply; recorded so the absence is deliberate) |
| **IV. Test Discipline Through Nox** | Unit tests for route validation and service wiring; e2e for each of the four dialogs. New e2e waits on observable state only — the payload of the intercepted request and the rendered alert/summary text. No new pytest marker. `nox -s tests` and `nox -s e2e` both gate the change. | **PASS** |
| **V. MariaDB Is the Source of Truth** | No schema change, therefore no Alembic revision. Nothing to migrate, nothing to reverse. | **PASS** (not engaged) |
| **VI. Item Lifecycle and History Invariants** | Printing is read-only with respect to inventory. The FR-012 repair touches the dialog *offered after* bulk creation, never the creation itself — Story 3 scenario 5 pins that: dismissing the dialog leaves the created items untouched. The existing `tests/e2e/test_bulk_creation.py` suite guards the creation path and must stay green. | **PASS** |

**Post-Phase-1 re-check**: unchanged. See "Constitution Re-check After Design" below.

## Project Structure

### Documentation (this feature)

```text
specs/013-label-print-count/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── labels-print-api.md   # Phase 1 output
├── checklists/
│   └── requirements.md  # /speckit-specify output
├── spec.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
app/
├── main/
│   └── routes.py                        # MODIFY  /api/labels/print: accept + validate label_count
├── services/
│   └── label_printer.py                 # MODIFY  thread the count; rename num_copies -> label_count
├── static/js/
│   ├── label-count.js                   # NEW     shared read + validate helper (window.LabelCount)
│   ├── label-printing-modal.js          # MODIFY  single-item dialog: input, payload, reset, message
│   ├── inventory-list.js                # MODIFY  list bulk dialog: input, payload, progress, summary
│   └── inventory-add.js                 # MODIFY  post-bulk-Add dialog: REPAIR + input, payload, summary
└── templates/inventory/
    ├── add.html                         # MODIFY  bulk modal: label types replace sizes; count input; script tag
    ├── edit.html                        # MODIFY  script tag for label-count.js
    └── list.html                        # MODIFY  bulk modal: count input; script tag

tests/
├── unit/
│   └── test_label_printer.py            # MODIFY  route validation + service wiring for the count
└── e2e/
    ├── test_label_printing.py           # MODIFY  single-item dialog count (Add + Edit)
    ├── test_bulk_label_printing_list.py # MODIFY  list bulk dialog count
    └── test_bulk_creation.py            # MODIFY  post-bulk-Add dialog: it prints now, and honors a count
```

**Structure Decision**: The existing Flask layout is used as-is. The only new file is
`app/static/js/label-count.js`; everything else is a modification. Nothing is added under
`app/models.py`, `app/database.py`, `app/storage.py`, or `migrations/` because this feature persists
nothing.

## Approach

### Backend — three small changes

1. **`generate_and_print_label()`**: rename the existing `num_copies` parameter to `label_count` for
   one word across the feature. It is referenced only inside `label_printer.py` (5 lines, zero test
   references), so the rename is free. Its body already does the right thing.
2. **`print_label_for_ja_id(ja_id, label_type, label_count=1)`**: accept the count and pass it down.
   The default keeps every existing caller and test valid.
3. **`POST /api/labels/print`**: read `label_count` from the body, default 1 when absent, validate it
   is a whole number in 1–99, and 400 with a message naming the problem otherwise. Full rules and
   wire format in [contracts/labels-print-api.md](./contracts/labels-print-api.md).

Absent-means-1 is what keeps FR-010 cheap: every existing caller that has not been updated yet keeps
working, so the four dialogs can be converted one at a time.

### Frontend — one helper, four dialogs

`app/static/js/label-count.js` exposes a single global (matching the `window.showLabelPrintingModal`
precedent already in `label-printing-modal.js`, and readable from `inventory-list.js` even though
that file is loaded as an ES module):

```js
window.readLabelCount(inputId) -> { ok: true, value: n } | { ok: false, error: "..." }
```

It owns the 1–99 bounds and the error wording, so the four dialogs cannot drift (SC-007). The markup
is the same three lines on each dialog — `<input type="number" min="1" max="99" step="1" value="1">`
— where the `min`/`max` attributes provide the spinner affordance and the helper provides the actual
gate. The gate is deliberately **not** browser constraint validation: every print button is
`type="button"`, so constraint validation would never fire, and a browser validation bubble is not
observable from an e2e test (see CLAUDE.md, "Submissions that never happen are silent"). The helper
returns text that the dialog renders into its existing alert region.

**Labeling** (FR-014, SC-008): the single-item dialog says **"Number of labels"**; the two bulk
dialogs say **"Labels per item"**. On the post-bulk-Add dialog that phrasing is doing real work — the
user has just typed a *quantity* of 8 items into the form behind it.

### The FR-012 repair, concretely

`app/templates/inventory/add.html:443` offers a `<select id="bulk-label-size">` with three invented
sizes (`2.25x1.25`, `2.25x0.5`, `custom`), and `app/static/js/inventory-add.js:868` posts
`{ja_id, label_size}`. The endpoint requires `label_type` and rejects the request 400, so every press
of "Print All Labels" on that dialog has always failed. Three changes fix it:

1. Replace the select's fixed options with the same API-populated label-type select the other three
   dialogs use, and rename the element to `bulk-label-type` so nothing reads as a size.
2. Post `label_type` (and now `label_count`).
3. Adopt the list page's error handling: `inventory-add.js` currently reports `response.statusText`
   and never parses `data.error`, so the endpoint's actual message is discarded. Match
   `inventory-list.js:231`.

### Reporting

- **Single-item dialog**: `Label printed successfully for {ja_id}` is kept verbatim at count 1;
  at count > 1 it becomes `{n} labels printed successfully for {ja_id}`.
- **Bulk progress**: `Printing {i} of {m}: {ja_id}` is kept verbatim, with ` ({n} labels)` appended
  only when the count exceeds 1.
- **Bulk completion**: `Complete: {labels} labels for {items} items, {failed} failed` at every count.
  This rewords today's `Complete: 3 printed, 0 failed`; the reasoning is in research.md, Decision 5.

## Complexity Tracking

> No Constitution Check violations. This table records the two judgment calls that could look like
> violations to a later reader, and why they are not.

| Looks like | Why it is not a violation | Simpler alternative rejected because |
|------------|---------------------------|--------------------------------------|
| A new shared JS helper (`label-count.js`) for a 6-line validation | Principle I bars abstraction for *one* implementation. This has four, and SC-007 makes their agreement a requirement rather than a nicety. | Inlining the check four times invites exactly the drift the spec forbids — the post-bulk-Add dialog is already the cautionary tale of a fourth copy going its own way. |
| Repairing the post-bulk-Add dialog inside a feature about counts | Shipping a label count input on a dialog that returns 400 on every press would be delivering a visible non-feature. The user scoped the repair in when the alternative was put to them. | Filing it as a separate issue leaves this feature knowingly incomplete on one of its four stated surfaces. |

## Constitution Re-check After Design

Re-evaluated against the Phase 1 artifacts (`data-model.md`, `contracts/labels-print-api.md`,
`quickstart.md`): **all gates still pass, no new violations.** The design added no persistence, no
layer, no dependency, and no configuration. The one new file is a browser helper. `data-model.md`
describes a request-shaped value object that exists for the duration of one HTTP call and is never
stored, which is why it produces no migration and engages Principle V not at all.

## Phase Status

- [x] Phase 0 — research complete → [research.md](./research.md)
- [x] Phase 1 — design complete → [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)
- [ ] Phase 2 — tasks (`/speckit-tasks`)
