# Implementation Plan: Close the Product Label Dialog When Printing Finishes

**Branch**: `robot-army/issue-202-dismiss-product-label-printing-modal` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/064-autoclose-product-label-modal/spec.md`

## Summary

There are two product label dialogs, and both get the JA ID dialog's behavior: after a fully
successful print, wait two seconds and close.

- **Product detail** (`product-label-modal.js`): when the POST succeeds, schedule a hide in
  2000 ms. Cancel any pending hide when the dialog opens and when it is hidden, so that a stale
  timer cannot close a reopened dialog (FR-005).
- **Bulk dialog** (`BulkLabelPrintDialog` in `bulk-label-print.js`), shared by Products, an
  order's page and Outstanding Products: a new constructor option, `closeOnSuccess`, off by
  default. When it is set and a run ends with `failureCount === 0`, schedule a hide in
  2000 ms. `reset()`, which runs on open and on `hidden.bs.modal`, cancels a pending hide. The
  two product callers (`product-list-labels.js`, `order-bulk-actions.js`) pass
  `closeOnSuccess: true`. The inventory list does not pass it, so its dialog is unchanged.

The existing reset-on-hidden already returns the bulk dialog to a clean state, and
`open()` already clears the detail dialog's alert (FR-006).

## Technical Context

**Language/Version**: vanilla JavaScript (browser); Python 3.13 for tests

**Primary Dependencies**: Bootstrap 5 modal. Nothing new.

**Storage**: none. No data or schema change.

**Testing**: Playwright e2e via `nox -s e2e`. JavaScript has no unit test harness here.

**Target Platform**: LAN web app

**Project Type**: web application (server-rendered)

**Performance Goals / Constraints / Scale**: N/A

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Simplicity First** | ✅ A timer in two places, mirroring `label-printing-modal.js`. The single new option, `closeOnSuccess`, captures a real difference between today's callers (product versus inventory list) rather than a hypothetical one. No new file, no dependency. |
| **II. Layered Architecture** | ✅ Front end only. No route or service change. |
| **III. Exact Numerics** | ✅ N/A. |
| **IV. Test Discipline** | ✅ The e2e tests cover each of the four pages: they wait for the modal to be hidden after success, using the existing `wait_for_modal_hidden`, a state wait rather than a duration. Failure paths assert the dialog is still open after the run completes, which is safe because nothing would close it. Tests that clicked Cancel or Done after a successful print now wait for the auto-close instead, which removes a click-versus-timer race. No `wait_for_timeout`. |
| **V. MariaDB Source of Truth** | ✅ N/A. |
| **VI. Item Lifecycle Invariants** | ✅ N/A. |
| **Threat model** | ✅ N/A. |
| **Screenshots** | `app/static/js/**` changes, but nothing rendered at rest changes. The dialog looks the same and only disappears sooner, so no screenshot is regenerated. |

**Post-design re-check**: ✅ Unchanged after Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/064-autoclose-product-label-modal/
├── plan.md
├── research.md
├── quickstart.md
├── contracts/
│   └── auto-close.md
└── tasks.md
```

No `data-model.md`. The feature touches no data.

### Source Code (repository root)

```text
app/static/js/
├── product-label-modal.js     # schedule/cancel hide after a successful print
├── bulk-label-print.js        # closeOnSuccess option; cancel pending hide in reset()
├── product-list-labels.js     # pass closeOnSuccess: true
└── order-bulk-actions.js      # pass closeOnSuccess: true (order page + Outstanding)

tests/e2e/
├── test_label_print.py                    # auto-close, failure stays open, reopen test
├── test_bulk_label_printing_products.py   # auto-close, failure stays open, reopen test
├── test_order_bulk_actions.py             # auto-close after the run
└── test_outstanding_products.py           # auto-close after the run

docs/user-manual.md            # one line in each product label section
```

**Structure Decision**: Existing files only.

## Complexity Tracking

No violations.
