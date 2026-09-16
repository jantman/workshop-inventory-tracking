# Feature Specification: Print labels for selected products from the All Products view

**Feature Branch**: `robot-army/issue-157-print-labels-from-all-products-view`

**Created**: 2026-09-15

**Status**: Draft

**Input**: GitHub issue #157 — "Print Labels from \"All Products\" view"

## Context

The inventory items list lets the operator tick a checkbox on each row, then print labels for
everything ticked in one pass: one dialog asks for the label size and how many copies of each, and
the operator watches a progress readout while the labels go to the printer.

The products list offers nothing equivalent. A product label can be printed one product at a time,
from that product's own page, which means navigating to a product, printing, navigating back, and
repeating. Labelling a tray of newly-received parts is therefore a per-product round trip through
the catalog, and the operator loses their place in the filtered list every time.

The result the operator wants is the one the items list already gives them: filter or search the
list down to the products they are holding, tick those rows, choose a label size and a copy count
once, and have the labels come out.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Print labels for several products in one pass (Priority: P1)

The operator has just received a box of parts. They open the products list, find the products they
are holding, tick the checkbox on each of those rows, and click a button to print labels. A dialog
asks which label size to use and how many copies of each label to print. They confirm, watch the
progress, and collect the labels.

**Why this priority**: This is the whole of the request. Without it the feature does not exist, and
with it the operator's task goes from N round trips through the catalog to one.

**Independent Test**: Open the products list with several products present, tick two or more rows,
open the print dialog, choose a label size, confirm, and verify a label is produced for each ticked
product. Delivers the issue's value on its own.

**Acceptance Scenarios**:

1. **Given** the products list showing several products, **When** the operator ticks the checkboxes
   on three rows and activates the print-labels action, **Then** a dialog opens offering the
   available label sizes and a copy count.
2. **Given** that dialog with a label size chosen and a copy count of 1, **When** the operator
   confirms, **Then** exactly one label is produced for each of the three ticked products, each
   carrying that product's own content.
3. **Given** that dialog with a label size chosen and a copy count of 4, **When** the operator
   confirms, **Then** four identical labels are produced for each ticked product — twelve in all.
4. **Given** a completed print run, **When** the operator reads the dialog, **Then** it reports how
   many labels were produced and the operator can dismiss it.
5. **Given** the products list, **When** no rows are ticked, **Then** the print-labels action is
   unavailable, and no dialog can be opened.

---

### User Story 2 - Select and deselect without losing track (Priority: P2)

The operator narrows the list with the existing search and filters, then ticks rows. They can tick
every row on the list at once with a single control, and clear the selection the same way. At all
times the interface tells them how many products are selected.

**Why this priority**: Selection is what the first story is built on, and the items list already
behaves this way; matching it is what makes the products list feel like the same application. It is
separated because the core print path is usable with per-row ticking alone.

**Independent Test**: Tick rows individually and via the select-all control, confirm the displayed
count matches, and confirm clearing the selection empties it. Testable without printing anything.

**Acceptance Scenarios**:

1. **Given** a products list, **When** the operator activates the select-all control, **Then** every
   product row currently listed becomes selected and the displayed count equals the number of rows
   listed.
2. **Given** every row selected, **When** the operator activates the select-all control again,
   **Then** no rows are selected and the print-labels action becomes unavailable.
3. **Given** some but not all rows selected, **When** the operator reads the select-all control,
   **Then** it presents itself as partially selected rather than as either fully on or fully off.
4. **Given** rows selected, **When** the operator changes the search or filters and the list is
   re-rendered, **Then** the selection reflects what is now listed — no product that is not visible
   in the list remains selected and counted.
5. **Given** a products list showing no products at all, **When** the operator looks for the
   selection and print controls, **Then** nothing offers to print labels for an empty selection.

---

### User Story 3 - Know what happened when a label fails to print (Priority: P2)

A print run covering several products hits a failure on one of them. The operator is told which
product failed, and the remaining products still get their labels.

**Why this priority**: A silent partial failure is worse than no feature, because the operator walks
away believing a bag is labelled when it is not. It is not P1 only because the happy path has to
exist first.

**Independent Test**: Trigger a print run in which one product's label cannot be produced, and
confirm the dialog names that product, reports the reduced success count, and that the other
products' labels were still produced.

**Acceptance Scenarios**:

1. **Given** a selection of five products where one cannot be labelled, **When** the run completes,
   **Then** the dialog reports four successes, names the one failure, and the operator can still
   dismiss the dialog.
2. **Given** a print run in progress, **When** the operator watches the dialog, **Then** it shows
   which product of how many is currently being printed.
3. **Given** a copy count the system will not accept, **When** the operator confirms, **Then** the
   dialog reports the accepted range and nothing at all is printed — not even for the first product
   in the selection.

---

### Edge Cases

- **Nothing selected.** The print action is unavailable; the dialog cannot be reached.
- **One product selected.** Works exactly as several do; the dialog does not change shape for a
  selection of one, and the wording does not read as though a count were plural.
- **A copy count outside the accepted whole-number range (below 1, above 99, fractional, or not a
  number).** Refused with a message naming the accepted range, before anything is printed. This is
  the same range and the same refusal the item and single-product label paths already apply.
- **No label size chosen.** The confirm action is unavailable until one is chosen.
- **A product deleted or edited between selection and printing.** Each label is composed from the
  stored record at print time, so an edit is reflected; a product that no longer exists is reported
  as a failure and does not abort the rest of the run.
- **The label printer is unavailable.** Every product fails, each is named, and the dialog reports
  zero successes rather than appearing to succeed.
- **Reopening the dialog after a run.** The dialog returns to its starting state — the copy count
  back to its default and no stale progress or error text from the previous run.
- **A product with no purchase history, manufacturer, or part number.** Labels as it does today from
  the single-product path; bulk printing changes nothing about label content.
- **A very large selection.** The run is still reported product by product and completes; there is no
  cap beyond what the operator selects.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The products list MUST let the operator select individual product rows and MUST show
  how many products are currently selected.
- **FR-002**: The products list MUST offer a control that selects all currently listed products and
  a way to clear the selection.
- **FR-003**: The select-all control MUST distinguish three states — none selected, all selected,
  and some selected — and MUST NOT present a partial selection as either extreme.
- **FR-004**: The products list MUST offer a print-labels action that is available only while at
  least one product is selected.
- **FR-005**: The print-labels action MUST open a dialog offering the label sizes the system
  supports, drawn from the same source the item and single-product label dialogs use, so the three
  never disagree about what sizes exist.
- **FR-006**: The dialog MUST accept a copy count meaning "how many copies of each selected
  product's label", defaulting to 1.
- **FR-007**: The copy count MUST be validated as a whole number from 1 to 99 inclusive — the range
  the item and single-product label paths already accept. A value outside it MUST be refused with a
  message naming the range, and MUST result in nothing being printed.
- **FR-008**: Confirming MUST produce, for each selected product, the number of labels requested,
  each composed from that product's own stored record.
- **FR-009**: Label content MUST be identical to what the existing single-product label path
  produces for the same product and label size. This feature adds a way to request labels, not a
  new kind of label.
- **FR-010**: While a run is in progress the dialog MUST show progress, naming which product of how
  many is currently being handled.
- **FR-011**: A failure on one product MUST NOT abort the run. The remaining selected products MUST
  still be attempted.
- **FR-012**: On completion the dialog MUST report the total number of labels produced and MUST name
  every product that failed.
- **FR-013**: Reopening the dialog MUST present it in its starting state, with no progress, errors,
  or copy count carried over from a previous run.
- **FR-014**: The existing single-product label path and the existing inventory-item bulk label path
  MUST continue to behave exactly as they do today.
- **FR-015**: Selection MUST be scoped to what the list currently shows: when the list is filtered,
  searched, or re-rendered, a product that is no longer listed MUST NOT remain selected.

### Key Entities

- **Product**: A catalog record that can be labelled. Already carries everything a label needs —
  description, internal code, manufacturer, part number, and a purchase history.
- **Selection**: The set of products the operator has ticked in the list. Exists only while the page
  is open and is not persisted.
- **Label size**: One of the label stocks the system supports. The same set is offered wherever a
  label can be printed.
- **Print run**: One pass through the selection, producing the requested number of copies per
  product and yielding a per-product success or failure.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Labelling N products takes one pass through one dialog for any N the operator can
  select, rather than N visits to N product pages. For N = 10 this replaces at least 20 page
  navigations with zero.
- **SC-002**: For every selected product and every copy count from 1 to 99, the number of labels
  produced equals the number of selected products multiplied by the copy count.
- **SC-003**: A label printed for a product via the list produces the same content as a label
  printed for that same product from its own page at the same size — verified field for field.
- **SC-004**: When one product in a selection of five fails, the other four are still printed, and
  the operator can name the failed product from the dialog alone without consulting logs.
- **SC-005**: A refused copy count results in zero labels printed, verified across the whole
  selection and not only the first product.
- **SC-006**: The label sizes offered on the products list are the same set offered on the items
  list, with no size present in one and absent from the other.

## Assumptions

- **Reuse over reinvention.** The issue asks to reuse as much existing code as possible. The
  behaviour specified here is deliberately the behaviour the inventory items list already has, so
  that the existing selection, dialog, progress, and per-product printing machinery can be reused
  rather than a second, divergent implementation written. Where this spec and the items list differ
  in wording, the items list's observable behaviour is the intent.
- **The copy count means copies per product**, not a total to divide across the selection. This
  matches the items list, where the count is per item.
- **Selection is not persisted** across page loads, filter changes, or navigation. Nothing in the
  request suggests otherwise, and the items list does not persist it either.
- **Label content is out of scope.** What appears on a product label was settled by the
  product-label-provenance work; this feature only changes how many labels can be asked for at once
  and from where.
- **No pagination concern.** The products list renders the products matching the current filters
  without pagination, so "all currently listed" and "all matching" are the same set. If that ever
  changes, FR-002 means "all currently listed".
- **Single operator, LAN-only.** Per the project constitution, there is no concurrency, permission,
  or abuse concern to design around; a print run is one person pressing one button.
