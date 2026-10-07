# Feature Specification: Bulk Receive and Bulk Label Printing on the Order Page

**Feature Branch**: `robot-army/issue-194-order-page-bulk-receive-and-bulk-label`

**Created**: 2026-10-07

**Status**: Draft

**Input**: User description: "Order page bulk receive and bulk label print (GitHub issue #194). The order page (such as `/products/orders/Amazon/XXX-XXXXXXX-XXXXXXX` or `/products/orders/McMaster-Carr/FOO`) should allow (1) selecting/checking one or more products and bulk printing their labels, and (2) selecting one or more products and receiving them on a given date, with their ordered quantity."

## Background

A captured order's page lists its lines — one per purchase — with each line's product,
quantity and state, and a Receive button on every outstanding line. Receiving a line today
means opening its receipt screen, confirming, and coming back: one round trip per line. When
a box arrives holding a whole order, that is several round trips that each confirm exactly
what was ordered. Printing labels for the products that just arrived is likewise one product
page at a time, although the products list already offers selecting several and printing
them together.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive several lines at once (Priority: P1)

A box arrives with most of an order in it. On the order page the owner ticks the lines that
arrived, picks the date they arrived (today unless changed), and receives them in one action.
Each ticked line is marked received on that date with the quantity that was ordered, and the
page shows them as received.

**Why this priority**: This is the round trip the issue is about removing, and it changes
stock, so it carries the most value and the most care.

**Independent Test**: Seed an order with three outstanding lines, tick two, set a date,
receive; those two read "received" on that date, the third is still outstanding, and each
counted product's quantity rose by its line's ordered quantity.

**Acceptance Scenarios**:

1. **Given** an order with three outstanding lines, **When** the owner ticks two of them and
   receives them with today's date, **Then** both are marked received today with their
   ordered quantities, the third stays outstanding, and the page confirms how many were
   received.
2. **Given** a ticked line whose product has a tracked count of 4 and an ordered quantity of
   10, **When** it is received in bulk, **Then** the product's count becomes 14 and the date
   of its last count does not change — exactly as receiving it singly without ticking
   "I counted" would.
3. **Given** the owner sets the received date to 3 October, **When** they receive the ticked
   lines, **Then** each is recorded as received on 3 October.
4. **Given** every outstanding line is ticked and received, **When** the page reloads,
   **Then** it reports the whole order received.

---

### User Story 2 - Print labels for several products at once (Priority: P1)

After unpacking, the owner ticks the lines whose products need labels and prints them all
together, choosing the label type and how many labels per product, the same way the products
list does it.

**Why this priority**: The other half of the issue; independent of receiving and equally
asked for.

**Independent Test**: On an order with three lines, tick two, open Print Labels; the dialog
lists those two products, and printing sends one label request per product.

**Acceptance Scenarios**:

1. **Given** an order page, **When** the owner ticks two lines and presses Print Labels,
   **Then** the label dialog lists the two products and prints a label for each with the
   chosen type and count.
2. **Given** two ticked lines that name the same product, **When** labels are printed,
   **Then** that product is printed once, not twice.
3. **Given** a received line, **When** it is ticked, **Then** its product's label can still
   be printed — labels are not limited to outstanding lines.

---

### User Story 3 - Selection that reads clearly (Priority: P2)

The owner can tick lines one by one or all at once with a single header checkbox, sees how
many are ticked, and cannot press either bulk action with nothing ticked.

**Why this priority**: Supports both P1 stories; the actions work without it but it is what
makes them comfortable on a long order.

**Independent Test**: Tick the header checkbox; every selectable line is ticked and the
count reflects it; untick one and the header shows a partial state.

**Acceptance Scenarios**:

1. **Given** nothing is ticked, **Then** the Print Labels and Receive actions are unavailable.
2. **Given** the header checkbox is ticked, **Then** every selectable line is ticked.

### Edge Cases

- **Received lines in the selection**: ticking a line that is already received and pressing
  Receive does not receive it again or touch its date or the stock count; the confirmation
  says how many were received and how many were already received and skipped.
- **Only received lines ticked**: Receive reports that nothing was outstanding among the
  ticked lines and changes nothing.
- **A date before the order date**: the receipt is refused, as it is for a single line, and
  **none** of the ticked lines is received — a bulk receipt never half-happens.
- **A date in an unreadable form or blank**: blank means today, as on the single receipt
  screen; an unreadable date is refused with nothing received.
- **A line whose product was deleted**: it has no checkbox — there is no product to label and
  nothing for a receipt to add to.
- **A line with no recorded quantity**: received with no quantity change, as a single receipt
  with the quantity left alone would be.
- **Received in another tab meanwhile**: a line that was outstanding when the page loaded but
  received since is skipped as already received, not received twice.
- **An order with no lines** ("nothing captured"): no checkboxes and no bulk actions.
- The per-line Receive button, which allows amending quantity, price, description and notes,
  stays as it is for a line that arrived differently from how it was ordered.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The order page MUST show a checkbox on every line that has a product, and a
  header checkbox that ticks or unticks all of them, showing a partial state when some are
  ticked.
- **FR-002**: The order page MUST offer a Print Labels action, unavailable while nothing is
  ticked, that opens the same label dialog the products list uses (label type, labels per
  product, progress, per-product failures) for the products of the ticked lines.
- **FR-003**: Label printing MUST print each distinct product once, however many ticked lines
  name it, and MUST produce the same label as printing from that product's own page.
- **FR-004**: The order page MUST offer a Receive action, unavailable while nothing is ticked,
  with a received date that defaults to today.
- **FR-005**: Receiving MUST mark each ticked outstanding line received on the chosen date
  with its ordered quantity, with exactly the effects of receiving that line singly without
  amendments and without "I counted": the product's tracked count rises by the quantity, the
  count's date does not move, and a manual low flag is cleared.
- **FR-006**: Receiving MUST skip ticked lines that are already received, leaving their date
  and the stock count untouched.
- **FR-007**: Receiving MUST be all-or-nothing: if the date is refused for any ticked line,
  no line is received, and the owner is told why.
- **FR-008**: After receiving, the owner MUST return to the same order page, which shows the
  updated states and a message stating how many lines were received and, if any, how many
  were skipped as already received.
- **FR-009**: The existing per-line Receive button and receipt screen MUST be unchanged.

### Key Entities

- **Order line**: one purchase on the order — its product, ordered quantity, and whether and
  when it was received. Bulk receive changes only its received date (and, through it, its
  product's count, as single receipt does).
- **Product label**: the existing per-product label; nothing about its content changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Receiving N lines of an order that arrived as ordered takes one action on the
  order page instead of N visits to the receipt screen.
- **SC-002**: Labels for N products on an order are printed from one dialog instead of N
  product pages.
- **SC-003**: For any line, receiving it in bulk and receiving it singly with nothing amended
  leave the line and its product in identical states.
- **SC-004**: A bulk receipt refused for any reason leaves every ticked line exactly as it
  was.

## Assumptions

- "With their ordered quantity" means the quantity recorded on the line; bulk receive offers
  no per-line amendment. A line that arrived short or different is received through its
  existing Receive button, which allows that.
- One received date applies to every line received in one action.
- Bulk receive never asserts "I counted what is on the shelf"; that stays an explicit act on
  the single receipt screen.
- One set of checkboxes drives both actions. Labels act on every ticked line's product;
  receiving acts on the ticked lines that are outstanding.
- Applies to every vendor's order page, since all vendors share one order page.
