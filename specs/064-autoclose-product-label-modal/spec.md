# Feature Specification: Close the Product Label Dialog When Printing Finishes

**Feature Branch**: `robot-army/issue-202-dismiss-product-label-printing-modal`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Issue #202 — Dismiss product label printing modal when printing finishes. For Products, after printing labels, the modal does not auto-dismiss when printing is complete. It should, on all pages that have it."

## Background

Product labels are printed from a dialog on four pages:

- **Product detail**: a single-product dialog (Print Label).
- **Products** (`/products`): the bulk dialog for the ticked products.
- **An order's page**: the bulk dialog for the products on the ticked lines.
- **Outstanding Products**: the same bulk dialog as an order's page.

When printing finishes, each of these stays open. The single-product dialog shows a success
message, and the bulk dialog shows a "Complete: …" line and a **Done** button. The owner then
has to close it by hand. The JA ID (inventory item) label dialog already closes itself two
seconds after a successful print, which leaves time to read the confirmation. The product
dialogs should do the same.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The product detail dialog closes after a successful print (Priority: P1)

The owner opens a product, chooses Print Label, picks a stock and prints. The success message
appears, and shortly afterwards the dialog closes without the owner doing anything.

**Why this priority**: This is the most common way a single product label gets printed.

**Independent Test**: Open a product's detail page, print one label, see the success message,
and then see the dialog close by itself.

**Acceptance Scenarios**:

1. **Given** the Print Label dialog is open with a stock chosen, **When** the print succeeds,
   **Then** the success message is shown and the dialog closes by itself shortly afterwards.
2. **Given** the print fails, **When** the error is shown, **Then** the dialog stays open so
   the owner can read the error and retry.
3. **Given** the dialog closed after a print, **When** the owner opens it again, **Then** it
   opens normally with no leftover message and stays open until the owner prints or cancels.

---

### User Story 2 - The bulk product label dialog closes after a successful run (Priority: P1)

On Products, an order's page or Outstanding Products, the owner ticks rows, chooses Print
Labels, and prints. When every label has printed, the "Complete: …" summary appears, and
shortly afterwards the dialog closes by itself.

**Why this priority**: The issue says "on all pages that have it". These three pages share
one dialog.

**Independent Test**: On each of the three pages, tick two rows and print. Once the run
completes with no failures, the dialog closes without Done being pressed.

**Acceptance Scenarios**:

1. **Given** a run in which every label prints, **When** it completes, **Then** the summary
   is shown and the dialog closes by itself shortly afterwards.
2. **Given** a run in which one or more labels fail, **When** it completes, **Then** the
   dialog stays open showing the failures, and the owner closes it with Done.
3. **Given** a count the dialog refuses, **When** the owner presses Print, **Then** the dialog
   stays open with the warning, as it does today.

---

### Edge Cases

- **Owner closes the dialog during the pause**: it closes as normal. If they then reopen it
  before the pause would have ended, the reopened dialog is not closed by the earlier print.
- **Partial failure in a bulk run**: the dialog does not close, because the owner needs to see
  which entries failed.
- **Inventory (JA ID) label dialogs**: the single-item dialog already closes itself and is
  unchanged. The inventory list's bulk dialog is not a product dialog, and it is out of scope.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After a successful print, the product detail page's label dialog MUST show its
  success message and then close itself after a short pause.
- **FR-002**: After a bulk product label run in which every entry printed, the bulk dialog on
  Products, an order's page and Outstanding Products MUST show its completion summary and then
  close itself after a short pause.
- **FR-003**: The pause MUST match the JA ID label dialog's (two seconds), so the confirmation
  can be read and the product and item dialogs behave alike.
- **FR-004**: A dialog MUST NOT close itself when any part of the print failed, or when the
  print was refused before it started.
- **FR-005**: A pending automatic close MUST NOT close a dialog that the owner closed and
  reopened in the meantime.
- **FR-006**: A dialog closed automatically MUST reopen in the same clean state as one closed
  by hand.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all four product label pages, a fully successful print needs no click after
  Print. Today it needs one more to close the dialog.
- **SC-002**: The confirmation stays readable for about two seconds before the dialog closes.
- **SC-003**: Every print with a failure keeps the dialog open.

## Assumptions

- "Printing is complete" means the print request(s) succeeded. A failure is not completion
  the owner wants hidden.
- The inventory list's bulk dialog shares code with the product bulk dialog, but the issue
  names Products only, so its behavior is left as it is.
