# Research: Close the Product Label Dialog When Printing Finishes

## R1 — How long to wait before closing

- **Decision**: 2000 ms after the success message is shown.
- **Rationale**: `label-printing-modal.js` (the JA ID dialog) already does exactly this with
  `setTimeout(() => this.hide(), 2000)`, and the manual documents it as "automatically closes
  after successful printing". Using the same value makes the two dialogs behave alike, and the
  confirmation stays readable.
- **Alternatives considered**: closing immediately, which hides the confirmation, including
  the bulk run's label count; and a configurable delay, which nothing needs.

## R2 — What counts as "printing finished"

- **Decision**: Close only when everything succeeded. On the detail page that means
  `data.success`. In the bulk dialog it means `failureCount === 0` at the end of a run.
- **Rationale**: A failure report exists to be read, and a dialog that closes over it loses
  the names of the failed products. A refused count never starts a run, so it never reaches
  the close.
- **Alternatives considered**: closing on any completion. That would throw away the failure
  list.

## R3 — Scope within the shared bulk dialog

- **Decision**: An opt-in `closeOnSuccess` constructor option on `BulkLabelPrintDialog`,
  passed by the two product callers. The inventory list keeps today's behavior.
- **Rationale**: The issue is about Products. The inventory list's bulk dialog is the same
  class, but changing it is outside what was asked. One boolean expresses the difference
  between today's callers. Turning it on for the inventory list later is a one-line change.
- **Alternatives considered**: changing the class for every caller, which widens the scope
  beyond the issue; and putting the timer in each caller's `onFinished`, which duplicates the
  timer and its cancellation in two files and leaves the class unable to cancel on reset.

## R4 — A stale timer closing a reopened dialog

- **Decision**: Keep the timer handle. Clear it when the dialog opens and when it is hidden:
  `reset()` in the bulk dialog, and `open()` plus a `hidden.bs.modal` listener on the detail
  page.
- **Rationale**: Without this, Cancel → reopen within two seconds would close the new dialog
  under the owner (FR-005).

## R5 — Hiding the detail page's modal

- **Decision**: `bootstrap.Modal.getOrCreateInstance(this.modalEl).hide()`.
- **Rationale**: `open()` calls `new bootstrap.Modal(el)` on each open, and Bootstrap returns
  the same instance for an element. `getOrCreateInstance` addresses that instance without
  keeping another reference. The bulk dialog does the same with its own modal element.
