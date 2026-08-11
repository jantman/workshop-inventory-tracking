# Feature Specification: Label Print Count

**Feature Branch**: `013-label-print-count`

**Created**: 2026-08-11

**Status**: Draft

**Input**: GitHub issue #86 — "Label Printing Dialogs Count / Quantity": *Label printing (both when adding/editing a single material inventory item as well as when bulk printing labels for multiple items) should support a quantity/count of labels to print. The UI input field for this should default to 1. When bulk printing labels for multiple items, the each item's label should be printed the specified quantity/count number of times.*

> **A note on the word.** The issue says "quantity/count". This spec says **label count** throughout,
> and reserves "quantity" for its existing meaning on the Add Item form — *how many items to create*.
> The two numbers meet in the same flow (create 8 items, print 2 labels each), so they do not get to
> share a name. See the Terminology section.

## Terminology

- **Label count** — how many copies of a label to print. The thing this feature adds. Range 1–99,
  defaults to 1.
- **Quantity** — the existing Add Item form field: how many inventory items to create. Untouched by
  this feature, and never used here to mean anything else.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Print several copies of one item's label (Priority: P1)

A workshop user has just added — or is editing — a single inventory item and wants more than one
barcode label for it: one for the end of the stock, one for the rack tag, one spare. Today the print
dialog gives them exactly one label per press, so they press it three times and wait through three
round trips. They want to say "3" once.

**Why this priority**: This is the smaller, self-contained half of the request and it exercises the
whole label count concept end to end — the input, its default, its validation, and the printer
receiving more than one copy. Shipping only this is already useful on its own.

**Independent Test**: Open the print dialog from the Add Item form (or the Edit Item form), set the
label count to 3, choose a label type, and print. Three labels for that JA ID come out; the dialog
reports the outcome once, not three times.

**Acceptance Scenarios**:

1. **Given** the print dialog is open for a JA ID, **When** the user looks at the label count input,
   **Then** it shows 1.
2. **Given** the print dialog is open with a label type selected and the label count left at its
   default, **When** the user prints, **Then** exactly one label for that JA ID is produced —
   identical to today's behavior.
3. **Given** the print dialog is open with a label type selected, **When** the user sets the label
   count to 3 and prints, **Then** three labels for that JA ID are produced.
4. **Given** the user printed with a label count of 3 and then reopens the print dialog, **When** the
   dialog appears, **Then** the label count input has reset to 1 (the label type selection continues
   to behave as it does today).
5. **Given** the print dialog is open, **When** the user enters a label count that is not a whole
   number of at least 1 (blank, 0, negative, fractional, or text) and presses print, **Then** no
   label is printed and the user is told the label count is invalid.

---

### User Story 2 - Print several copies of each item's label in a bulk run (Priority: P2)

A user selects a batch of items on the inventory list page and prints labels for all of them. They
want two labels per item — the stock and the bin — without running the batch twice.

**Why this priority**: It depends on the same label count concept as Story 1 but multiplies it across
a batch, and it is where the count is most valuable (a 12-item batch at 2 copies is 24 presses
saved). It is second only because Story 1 is the smaller slice that proves the mechanism.

**Independent Test**: Select three items on the inventory list, open the bulk print dialog, set the
label count to 2, choose a label type, and print. Six labels come out — two for each of the three JA
IDs — and the progress display makes clear that the run covered three items at two copies each.

**Acceptance Scenarios**:

1. **Given** the bulk print dialog is open for a set of selected items, **When** the user looks at
   the label count input, **Then** it shows 1.
2. **Given** three items are selected and the label count is left at its default, **When** the user
   prints, **Then** exactly three labels are produced — identical to today's behavior.
3. **Given** three items are selected, **When** the user sets the label count to 2 and prints,
   **Then** six labels are produced: two for each selected item.
4. **Given** a bulk run with a label count greater than 1, **When** the labels are produced, **Then**
   all copies for one item are produced consecutively before the next item's copies begin, so the
   output can be sorted by picking up groups rather than interleaved singles.
5. **Given** a bulk run of several items at a label count greater than 1, **When** one item's labels
   fail to print, **Then** the run continues to the remaining items and the summary identifies which
   item failed, exactly as it does today for single-copy runs.
6. **Given** the bulk print dialog is open, **When** the user enters a label count that is not a
   whole number of at least 1 and presses print, **Then** no labels are printed and the user is told
   the label count is invalid.
7. **Given** a bulk run has completed, **When** the user reopens the bulk print dialog, **Then** the
   label count input has reset to 1.

---

### User Story 3 - Label a batch of items straight after creating them (Priority: P3)

A user adds a run of identical stock — say eight lengths of the same bar — through the Add Item
form's bulk creation, and is offered a print dialog for the eight new JA IDs on the spot. They want
two labels for each. Today that dialog cannot print anything at all: it asks for a label *size* from
a list of sizes the printer has never heard of, and every press fails. So this story is a repair
plus a label count.

**Why this priority**: It is the most natural moment to print — the items exist, their IDs are on
screen, and the stock is in the user's hands. It is third because it is the only story that has to
fix a broken path before it can add anything, and because the same labels can be obtained today from
the inventory list (Story 2) as a workaround.

**Independent Test**: Create four items through bulk Add Item, and in the dialog that follows pick a
label type, set the label count to 2, and print. Eight labels come out — two for each of the four new
JA IDs — with no failures reported.

**Acceptance Scenarios**:

1. **Given** a bulk creation has just completed and its print dialog is open, **When** the user
   opens the label type list, **Then** it offers the same label types every other print dialog
   offers, and none of the fixed sizes it lists today.
2. **Given** that dialog with a label type selected and the label count left at its default, **When**
   the user prints, **Then** one label is produced for each newly created JA ID and the run reports
   no failures — the outcome the user expects today and does not get.
3. **Given** that dialog with a label type selected, **When** the user sets the label count to 2 and
   prints, **Then** two labels are produced for each newly created JA ID, grouped per item.
4. **Given** an item quantity of 8 was used to create the batch, **When** the print dialog appears,
   **Then** its label count still starts at 1 — the number of items created does not seed the number
   of labels per item.
5. **Given** that dialog is open, **When** the user dismisses it without printing, **Then** the
   created items are unaffected — printing is an offer, never a condition of the creation.

---

### Edge Cases

- **A label count of 1 must be indistinguishable from today.** The default path is the overwhelmingly
  common one; it must not gain an extra confirmation, an extra delay, or a differently worded
  result message.
- **A label count above the allowed maximum.** The user MUST be prevented from starting a run that
  exceeds the maximum (see FR-004) and told what the maximum is, rather than having the number
  silently clamped.
- **The user changes the label count but never picks a label type.** The existing "no label type
  selected" behavior wins; a label count does not make an otherwise-invalid dialog printable.
- **Partial failure part-way through an item's copies.** If some of an item's copies are produced
  and then printing fails, the reported outcome MUST NOT claim the full requested count was
  produced.
- **Bulk selection of zero items.** Unchanged: the existing "select items first" behavior applies
  before the label count is ever consulted.
- **Label type persistence is unaffected.** Where the label type is remembered between dialog
  openings today, it still is; the label count is not remembered (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every inventory-item label printing dialog in scope MUST present a label count input
  alongside the existing label type selection.
- **FR-002**: The label count input MUST show `1` whenever the dialog is opened, including after a
  previous print from the same dialog used a different label count.
- **FR-003**: A print MUST produce the requested number of copies of each label it would produce at a
  label count of 1. In a bulk run this means each selected item's label is produced the requested
  number of times — the label count multiplies the batch, it does not divide it.
- **FR-004**: The system MUST accept only whole numbers from 1 through 99 as a label count, and MUST
  refuse to print — with a message naming the problem — when the entered value is outside that range
  or is not a whole number.
- **FR-005**: A refused label count MUST leave the dialog open with the user's other selections
  intact, so the value can be corrected without starting over.
- **FR-006**: A single label count MUST apply to the whole bulk run. Per-item label counts are not
  offered.
- **FR-007**: In a bulk run, all copies of one item's label MUST be produced consecutively before
  the next item's copies begin.
- **FR-008**: The bulk progress and completion display MUST report the run in terms the user can
  reconcile against the stack of labels in their hand — how many items were covered and how many
  labels that amounted to.
- **FR-009**: Failure reporting MUST continue to identify the failing item and MUST NOT report a
  larger number of labels produced than were actually produced.
- **FR-010**: Existing behavior at a label count of 1 MUST be preserved unchanged across every dialog
  in scope, including label type persistence, validation of the JA ID, and dialog dismissal behavior.
- **FR-011**: The label count input MUST appear on these inventory-item label printing surfaces, and
  on no others:
  1. The single-item print dialog reached from the **Add Item** form.
  2. The single-item print dialog reached from the **Edit Item** form.
  3. The bulk print dialog reached from the **inventory list** page.
  4. The bulk print dialog offered **after a bulk Add Item creation**.
- **FR-012**: The post-bulk-Add print dialog MUST be repaired as part of this feature, because it
  cannot currently produce a label at all. Specifically: it MUST offer the same set of label types
  every other printing dialog offers, and a print from it MUST actually produce labels for the newly
  created JA IDs. Its present fixed list of label *sizes* — which the printing path does not accept
  and which corresponds to no label the system can produce — MUST be replaced, not extended.
- **FR-013**: Once repaired, the post-bulk-Add dialog MUST behave like the inventory list bulk
  dialog: same label type choices, same label count semantics (FR-003, FR-006, FR-007), same
  per-item failure reporting (FR-009), and the same progress and completion reporting (FR-008).
- **FR-014**: The label count control MUST be labeled so that it cannot be read as the Add Item
  form's item quantity. On the post-bulk-Add dialog in particular, where the two numbers appear
  seconds apart in one flow, the control MUST make clear it means labels per item.

### Key Entities

- **Print request**: What the user asks for when they press print — a set of one or more JA IDs, one
  label type, and one label count. Its outcome is a number of labels produced and a list of items
  that failed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who wants N copies of one item's label can obtain them with a single press of
  the print control, for any N from 1 to 99.
- **SC-002**: A user who sets a label count of N for M selected items obtains exactly N × M labels
  from a single bulk run.
- **SC-003**: Every dialog in scope opens with the label count showing 1, so a user who ignores the
  new input entirely gets exactly the behavior they got before this feature existed.
- **SC-004**: No label count a user can type into the input causes an unreported print, an unbounded
  print run, or a success message that overstates what was produced.
- **SC-005**: After a bulk run, the completion summary lets the user verify their stack of labels
  against it without counting the selected items themselves.
- **SC-006**: The print dialog offered after a bulk item creation produces labels — its success rate
  goes from zero labels for any press to one label per created item at the default label count.
- **SC-007**: The four surfaces in scope offer the same label types and the same label count
  behavior, so a user who learns one dialog has learned all four.
- **SC-008**: A user who has just created 8 items and is looking at the print dialog can tell at a
  glance which number on screen means items and which means labels per item.

## Assumptions

- **Scope is inventory-item (JA ID barcode) labels only.** The product label printing on the product
  detail page is a different label with a different composition path and is not covered by issue
  #86, which speaks of "material inventory item" labels. It is out of scope.
- **Repairing the post-bulk-Add dialog is in scope; implementing the search page's dialog is not.**
  The first is a broken control on a surface this feature must touch anyway — leaving it broken
  while adding a label count to it would ship a label count input on a dialog that prints nothing.
  The second is an absent feature rather than a broken one, and building it is not what issue #86
  asked for.
- **The label count is not remembered between dialog openings.** It resets to 1 every time. The label
  type is remembered on the Add Item form today because it is a stable preference for a user with
  one printer; a label count is a per-occasion decision, and a remembered "10" that the user forgets
  about is a wasted roll of labels.
- **The maximum of 99 is a guard rail, not a capability limit.** It exists so a typo in a numeric
  input cannot start a print run that empties the label stock. A hobby workshop has no use case for
  100+ copies of one barcode.
- **The label count is a whole number.** Fractions and decimals are rejected rather than rounded.
- **No new label type, label layout, or printer configuration is introduced.** The existing label
  types remain the only choices, and each copy is byte-identical to the single label printed today.
- **The printing itself remains synchronous from the user's point of view** — the dialog reports the
  outcome when the run finishes. Per the project's simplicity principle, no queue or background job
  is introduced to handle larger counts.

## Out of Scope

- **The inventory search page's bulk print dialog.** It opens and lists the selected items, but it
  has never had label types or a print action behind it. Implementing it is a separate piece of
  work; this feature neither adds a label count to it nor removes it.
- Product labels printed from the product detail page.
- Collation options (interleaving copies across items rather than grouping them per item).
- Different label counts for different items within one bulk run.
- Remembering the label count across dialog openings or sessions.
- Any change to the Add Item form's item quantity field.
- Any change to label content, size, or the set of available label types.
- Reprinting from a history of past print runs.
