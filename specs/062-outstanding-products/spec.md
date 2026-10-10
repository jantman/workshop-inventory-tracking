# Feature Specification: Outstanding Products Page

**Feature Branch**: `robot-army/issue-200-outstanding-product-receiving-page`

**Created**: 2026-10-10

**Status**: Draft

**Input**: User description: "Outstanding product / receiving page (GitHub issue #200). Right now if multiple orders have yet to be received, and arrive at once, I need to navigate to the Captured Orders page, then open each order in its own tab, and receive the relevant items from each (printing labels at this time if needed). I would like a new "Outstanding Products" page that provides a single view of outstanding products and allows me to receive them and print labels all from one view regardless of how many separate orders the products are from."

## Background

Feature 060 gave each order page checkboxes, a Receive Selected action (one received date,
ordered quantities, all-or-nothing) and a Print Labels action. Those work one order at a
time. When boxes from several orders arrive on the same day, the owner still has to open
Captured Orders, open each order with outstanding lines, and repeat the receive and label
steps on each one.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See everything still on its way, in one list (Priority: P1)

The owner opens **Products → Outstanding Products** and sees every purchase that has not been
received, from every order and every vendor. Each row shows the product, the vendor, the
order it belongs to (with a link to that order's page), the order date and the ordered
quantity.

**Why this priority**: Without the single list, neither action can work across orders. The
list is useful even before anything is received from it.

**Independent Test**: Seed two orders from different vendors, each with outstanding and
received lines, plus one outstanding purchase that has no order number. The page lists
exactly the three or more outstanding purchases, each showing its order (or that it has
none), and lists no received ones.

**Acceptance Scenarios**:

1. **Given** outstanding lines on two orders from different vendors, **When** the owner
   opens Outstanding Products, **Then** every outstanding line from both orders is listed,
   and received lines from those orders are not.
2. **Given** an outstanding purchase recorded without an order number, **When** the page is
   opened, **Then** it is listed and shows that it has no order.
3. **Given** a listed line, **When** the owner clicks its order, **Then** that order's page
   opens.
4. **Given** nothing is outstanding, **When** the page is opened, **Then** it says nothing
   is outstanding and offers no actions.

---

### User Story 2 - Receive lines from several orders at once (Priority: P1)

Boxes from several orders arrive together. On Outstanding Products the owner ticks the
lines that arrived, whichever orders they come from, picks the date they arrived (today
unless changed), and receives them in one action. Each ticked line is received on that date
with its ordered quantity, and the page reloads without them.

**Why this priority**: This is the round trip the issue asks to remove. It changes stock,
so it needs the most care.

**Independent Test**: Seed two orders with two outstanding lines each. Tick one line from
each order and receive. Those two lines are received on the chosen date, the other two stay
outstanding, and each counted product's quantity rises by its line's ordered quantity.

**Acceptance Scenarios**:

1. **Given** outstanding lines on two orders, **When** the owner ticks one line from each
   and receives them, **Then** both are marked received with their ordered quantities, both
   disappear from the page, the unticked lines remain, and a message says how many were
   received.
2. **Given** a ticked line whose product has a tracked count of 4 and an ordered quantity of
   10, **When** it is received from this page, **Then** the count becomes 14, the date of
   the last count does not change, and any manual low or out flag is cleared. These are
   exactly the effects of receiving that line on its order page.
3. **Given** the owner sets the received date to 3 October, **When** they receive the ticked
   lines, **Then** each is recorded as received on 3 October.

---

### User Story 3 - Print labels for products from several orders at once (Priority: P1)

After unpacking, the owner ticks the lines whose products need labels, from whichever
orders, and prints them together. They choose the label type and the number of labels per
product, as on the products list and the order page.

**Why this priority**: This is the other half of the issue. It does not depend on
receiving, and the issue asks for it just as directly.

**Independent Test**: Tick lines from two orders and open Print Labels. The dialog lists
those products, and printing sends one label request per distinct product.

**Acceptance Scenarios**:

1. **Given** lines ticked from two orders, **When** the owner presses Print Labels,
   **Then** the label dialog lists each ticked line's product and prints a label for each
   with the chosen type and count.
2. **Given** two ticked lines (on the same order or on different orders) that name the same
   product, **When** labels are printed, **Then** that product is printed once.

---

### User Story 4 - Find the page and work the selection comfortably (Priority: P2)

The page is reachable from the Products menu, next to Captured Orders. The owner can tick
lines one at a time or all at once with a header checkbox, and can see how many are ticked.
Neither action can be pressed while nothing is ticked.

**Why this priority**: Both P1 actions work without this story, but it is what makes a long
list comfortable to use.

**Acceptance Scenarios**:

1. **Given** nothing is ticked, **Then** Print Labels and Receive Selected are unavailable.
2. **Given** the header checkbox is ticked, **Then** every selectable line is ticked and the
   count shows that number. Unticking one line leaves the header checkbox partly ticked.
3. **Given** any page in the app, **When** the owner opens the Products menu, **Then**
   Outstanding Products is listed.

### Edge Cases

- **A date before an order's date**: the receipt is refused with the reason, and **none**
  of the ticked lines is received, even when the date is only too early for one of them. A
  bulk receipt never half-happens, on this page as on an order page.
- **Blank or unreadable date**: a blank date means today. An unreadable date is refused and
  nothing is received.
- **A line received elsewhere meanwhile** (an order page, another tab): it is skipped and
  counted as already received. It is not received twice, and its date and the stock count
  are not touched.
- **A ticked line deleted meanwhile**: the receipt is refused and nothing is received. The
  owner reloads and sees the current list.
- **A line whose product was deleted**: it is listed, but it has no checkbox. There is no
  product to label and nothing for a receipt to add to. It can still be dealt with from its
  order page.
- **A line with no recorded quantity**: it is received with no quantity change, as on the
  order page.
- **A line that arrived differently from how it was ordered** (short, a different price, a
  corrected description): every line keeps its own Receive button, which opens the existing
  single-receipt screen where those amendments are made.
- **Ordering**: lines from the same order sit together, oldest order first (the order that
  has waited longest is the likeliest to be in today's box). Undated orders and lines with
  no order come last.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide an Outstanding Products page listing every purchase
  that has not been received, across every order and every vendor, including purchases that
  belong to no order. Received purchases MUST NOT be listed.
- **FR-002**: Each row MUST show the product (linked to its page), the vendor, the order
  number linked to that order's page (or an indication that there is none), the order date,
  the vendor's part number where there is one, and the ordered quantity.
- **FR-003**: Rows MUST be grouped by order, with orders sorted oldest first. Undated orders
  come after dated ones, and purchases with no order come last.
- **FR-004**: The page MUST show a checkbox on every row that has a product, plus a header
  checkbox that ticks or unticks all of them and shows a partial state when only some are
  ticked. It MUST show how many rows are ticked.
- **FR-005**: The page MUST offer a Print Labels action that is unavailable while nothing is
  ticked. It opens the same label dialog as the products list and the order page (label
  type, labels per product, progress, per-product failures) and prints each distinct ticked
  product once. Each label MUST be identical to one printed from that product's own page.
- **FR-006**: The page MUST offer a Receive Selected action that is unavailable while
  nothing is ticked, with one received date that defaults to today.
- **FR-007**: Receiving MUST mark each ticked outstanding row received on the chosen date
  with its ordered quantity. The effects MUST be exactly those of receiving the line from
  its order page: the product's tracked count rises by the quantity, the count's date does
  not move, and a manual low or out flag is cleared.
- **FR-008**: Receiving MUST skip ticked rows that have been received since the page
  loaded, and leave their date and stock count untouched.
- **FR-009**: Receiving MUST be all-or-nothing. If the date is refused for any ticked row,
  or a ticked row no longer exists, no row is received and the owner is told why.
- **FR-010**: After receiving, the owner MUST land back on Outstanding Products. The page
  MUST show a message giving how many rows were received and, if any, how many were skipped
  as already received.
- **FR-011**: Every row MUST keep a Receive button that opens the existing single-receipt
  screen for that purchase.
- **FR-012**: The Products menu MUST link to Outstanding Products.
- **FR-013**: The order page's bulk actions, the single-receipt screen and the Captured
  Orders page MUST behave exactly as they do today.

### Key Entities

- **Outstanding purchase**: a purchase with no received date, shown with its product, its
  vendor, the order it belongs to (vendor plus order number, if any), the order date and the
  ordered quantity. Nothing new is stored. The list is worked out from the purchases each
  time the page opens, as Captured Orders is.
- **Product label**: the existing per-product label. Its content does not change.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Receiving lines that arrived together from N different orders takes one
  action on one page, instead of opening N order pages.
- **SC-002**: Printing labels for products from N different orders takes one dialog,
  instead of N.
- **SC-003**: For any line, receiving it from Outstanding Products and receiving it from its
  order page leave the line and its product in identical states.
- **SC-004**: A refused receipt leaves every ticked line exactly as it was.
- **SC-005**: The page lists every outstanding purchase and no received one: its row count
  equals the number of purchases with no received date.

## Assumptions

- "Outstanding product" means an outstanding **purchase line**, not a product. A product
  ordered on two orders that have not arrived appears twice, because those are two receipts.
  Labels are deduplicated per product (FR-005).
- Purchases with no order number (hand-recorded, or captured from a single listing) are
  outstanding too and are included. Leaving them out would make the page an incomplete
  answer to "what is still on its way?".
- The receipt matches 060's bulk receive: the ordered quantity, one date for all ticked
  lines, no "I counted". Amending a line stays on the single-receipt screen.
- No filtering, search or paging. A home workshop has tens of outstanding lines at most
  (Constitution I).
- Captured Orders is left unchanged. The new page sits next to it in the Products menu.
