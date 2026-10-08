# Feature Specification: Edit Purchases and Orders

**Feature Branch**: `robot-army/issue-192-product-purchases-allow-editing`

**Created**: 2026-10-07

**Status**: Draft

**Input**: User description: "Product purchases - allow editing purchases and orders (GitHub issue #192). I've run into a few minor order capture bugs. I've opened issues for them, but this leaves me with an invalid purchase record for a product. The only current ways to fix this are direct database access, or deleting the relevant purchase for the product and then using \"Add a Purchase\" to re-create it properly, but this added purchase does not get matched to the original order. Please implement editing of captured orders, purchases, etc. via the UI so that problems identified post-order-capture can be corrected."

## Background

A purchase records one acquisition of one product: who sold it, the vendor's item number and
listing, when it was ordered and received, how many and at what price, the vendor's pack (where
it sold a pack), the order numbers, which line of the order it came from, and notes. An *order*
is not stored separately — it is the set of purchases carrying the same vendor and order
number, and the order page is built from them.

Today a purchase can be recorded, received (amending quantity, price and notes on the way) and
deleted, but not edited. When an order capture gets something wrong — a pack quantity read as
the item count, a price, a date — the owner's only fixes are editing the database by hand or
deleting the purchase and recording it again by hand. The re-recorded purchase lacks the order
line it came from, so it no longer lines up with the order it belongs to.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Correct a purchase in place (Priority: P1)

The owner notices that a captured purchase is wrong — say it records 1 item at $13.23 when the
order was one pack of 100. From the product page, or from the order page, they open that
purchase's Edit screen, which shows every recorded detail already filled in, correct the
quantity, unit price and pack fields, and save. The purchase now reads correctly everywhere,
and it is still the same line of the same order.

**Why this priority**: This is the whole of the issue's complaint: an invalid purchase record
that cannot be fixed without losing its link to the order.

**Independent Test**: Seed a purchase on an order, edit its quantity and unit price, save; the
product page and the order page both show the new values, and the order still lists the line
in the same position.

**Acceptance Scenarios**:

1. **Given** a captured purchase on an order, **When** the owner opens its Edit screen,
   **Then** every editable field is pre-filled with the stored value.
2. **Given** that Edit screen, **When** the owner changes the quantity, unit price, pack size
   and pack price and saves, **Then** the purchase stores exactly those values and the owner
   lands back where they came from with a confirmation.
3. **Given** a purchase opened for editing from its order page, **When** it is saved, **Then**
   it is still listed on that order, as the same line.
4. **Given** the owner enters an invalid value (a quantity of zero, a negative price, a
   received date before the order date, a pack size of 1, a pack size without a pack price),
   **When** they save, **Then** nothing is changed, the problem is named, and everything they
   typed is still on the form.
5. **Given** the owner opens Edit and clicks Cancel, **Then** nothing changes and they return
   where they came from.

---

### User Story 2 - Re-attach a purchase to its order (Priority: P1)

The owner has already worked around a bad capture by deleting a purchase and recording it again
with "Add a Purchase". That purchase is not on the order page. They open it for editing, enter
the order number (and, if they know it, the order line number), save, and the purchase now
appears as a line on that order.

**Why this priority**: The issue names this exact gap: a re-created purchase "does not get
matched to the original order". Editing the order fields is what closes it.

**Independent Test**: Seed an order with two lines and a separate hand-recorded purchase of the
same vendor with no order number; edit the latter to carry the order's number; the order page
lists three lines.

**Acceptance Scenarios**:

1. **Given** a hand-recorded purchase with no order number, **When** the owner sets its
   supplier order number to an existing order's number from the same vendor, **Then** that
   order's page lists it as one of its lines.
2. **Given** a purchase whose order number is set to a different order, **When** saved,
   **Then** it leaves the old order's page and appears on the new one.
3. **Given** the owner sets an order line number that another purchase on the same order
   already has, **When** they save, **Then** it is refused, naming the conflict.

---

### User Story 3 - Correct a whole order (Priority: P2)

A capture recorded the wrong order date, or the wrong order number, or the wrong customer
reference for every line of an order. From the order page the owner opens "Edit Order", which
shows the order's number, order date and customer reference, corrects them, and saves; every
line of that order is updated together, and the owner lands on the order page at its (possibly
new) address.

**Why this priority**: The same correction as Story 1 multiplied by the number of lines; useful
but achievable, slowly, one purchase at a time with Story 1 alone.

**Independent Test**: Seed an order with three lines; change its order date and order number
through Edit Order; the order page at the new number lists three lines with the new date, and
the old number's page reports nothing captured.

**Acceptance Scenarios**:

1. **Given** an order with three lines, **When** the owner changes its order date, **Then**
   all three lines carry the new date.
2. **Given** an order, **When** the owner changes its order number to one not used by any other
   order from that vendor, **Then** all of its lines carry the new number and the owner lands on
   the order's page at the new number.
3. **Given** the owner changes the order number to one another order from that vendor already
   uses, **When** they save, **Then** nothing changes and the conflict is named (orders are
   never merged by this screen).
4. **Given** a new order date later than the received date of one of the lines, **When** the
   owner saves, **Then** nothing changes and the problem is named.
5. **Given** the order fields are left blank where they had a value, **When** saved, **Then**
   the order number is refused as required, while order date and customer reference are cleared.

---

### Edge Cases

- A purchase deleted (or edited) in another tab between opening Edit and saving: saving a
  deleted purchase reports it as not found rather than reporting success.
- An order edited whose lines all disappeared in another tab: reported as nothing to edit.
- Clearing a received date on a received purchase makes it outstanding again; the product's
  stock count is not changed (as with delete, the catalog cannot know whether that receipt
  moved a count, so it does not guess).
- Setting a received date on an outstanding purchase through Edit is not offered: receiving is
  done through Receive, which is what adds to the stock count. Edit only corrects or clears the
  date of something already received.
- Changing quantity on an already-received purchase does not change the product's stock count;
  the product page's own controls fix a count.
- Changing a purchase's vendor or order number moves it between orders; a purchase left with a
  blank order number is simply on no order, as a hand-recorded one is.
- Fields Edit does not expose (the vendor's internal order id, when the record was added) are
  kept exactly as they were.

## Requirements *(mandatory)*

### Functional Requirements

**Editing one purchase**

- **FR-001**: Every purchase MUST offer an Edit action wherever it is listed with per-purchase
  actions — the product page's purchase history and the order page's lines.
- **FR-002**: The Edit screen MUST show and allow changing: vendor, vendor item number, listing
  title, listing address, order date, received date (only for a purchase already received),
  quantity, unit price, pack size, pack price, customer order reference, supplier order number,
  order line number, and notes. Each field MUST be pre-filled with the stored value.
- **FR-003**: Saving MUST apply the same validation used when a purchase is recorded: vendor
  required; quantity a whole number above zero or blank; prices non-negative and exact to the
  cent, never stored through floating point; received date not before order date.
- **FR-004**: Pack size and pack price MUST be both blank or both set, and pack size MUST NOT be
  1. Order line number MUST be a whole number above zero or blank.
- **FR-005**: An order line number MUST NOT be saved if another purchase with the same vendor
  and supplier order number already carries it.
- **FR-006**: A refused save MUST change nothing, name the problem, and redisplay everything
  the owner typed.
- **FR-007**: Editing a purchase MUST NOT change the product's stock count, its count date, or
  its stock flag — including when quantity changes or a received date is cleared.
- **FR-008**: Fields not shown on the Edit screen MUST be preserved unchanged, as MUST the
  purchase's attachments.
- **FR-009**: After saving or cancelling, the owner MUST return to where they opened Edit from:
  the order page (at the purchase's order after the save, if it still has one) or the product
  page.

**Editing an order**

- **FR-010**: The order page MUST offer an "Edit Order" action whenever the order has lines.
- **FR-011**: The Edit Order screen MUST show and allow changing the order number, the order
  date and the customer order reference, pre-filled from the order's lines; where lines
  disagree on a value, the screen MUST say so and saving MUST set every line to the value
  entered.
- **FR-012**: Saving MUST update every line of the order together, or none of them.
- **FR-013**: The order number MUST be required, and MUST be refused if another order from the
  same vendor already uses it.
- **FR-014**: The new order date MUST be refused if it is after any line's received date.
- **FR-015**: After saving, the owner MUST land on the order page at its new number with a
  confirmation stating how many lines were updated.

### Key Entities

- **Purchase**: one acquisition of one product; every field listed in FR-002 belongs to it.
- **Order**: not stored; the purchases sharing a vendor and supplier order number. Editing an
  order is editing those fields on all of its purchases at once.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every field a capture records about a purchase that the owner can see can be
  corrected through the UI, with no database access.
- **SC-002**: A mis-captured order line can be corrected in one visit to one screen, and
  afterwards is still listed on its order as the same line.
- **SC-003**: A purchase recorded by hand can be attached to an existing order in one edit.
- **SC-004**: No edit, accepted or refused, changes any product's stock count.
- **SC-005**: An order-wide correction to date, number or reference is one save regardless of
  how many lines the order has.

## Assumptions

- Moving a purchase to a different product is out of scope; deleting it and recording it on the
  right product, then using Story 2 to re-attach it to its order, covers that case.
- The order's vendor is not editable from Edit Order (it decides how the order is captured and
  received); a single purchase's vendor can be changed from its own Edit screen.
- Editing a product's own details is already possible and is unchanged.
- Adding a new line to an order is done by recording a purchase on the product and editing it
  onto the order (Story 2); no separate "add line" action is added.
- Single user, no concurrency control beyond reporting a purchase or order that has vanished.
