# Feature Specification: McMaster Order Details Checklist

**Feature Branch**: `robot-army/issue-170-offer-the-order-page-details-checklist`

**Created**: 2026-09-27

**Status**: Draft

**Input**: GitHub issue #170, "Offer the order-page details checklist for McMaster orders,
not Amazon only"

## Background

Feature 044 (US3) made a captured Amazon order's page double as a checklist: how many of
the order's products still lack details, a "missing" or "captured" mark per line, and an
**Open listing** link on each line whose product is missing them. The owner opens each
listing, captures it with the browser extension as details-only, and lands back on the
order.

A captured McMaster-Carr order's page shows none of this. The reason recorded in the code
is that Amazon is "the one page-read order whose products are created without [details]
and whose listing address the catalog can build". The first half is true of McMaster too —
its order capture creates products with nothing but a description. The second half is
wrong: a McMaster product's page is `https://www.mcmaster.com/<part>/`, built from the part
number the order line already carries. And since feature 049, capturing that page as
details-only onto the order-created product works.

What does **not** carry over is 044 US4, the automatic per-line listing read at order
capture time: McMaster's product pages render client-side, so a background fetch returns
an empty shell. The checklist does not depend on it — it is a list of links the owner opens
by hand.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Work through a McMaster order's products from its page (Priority: P1)

The owner has captured a McMaster order. Its products were created with only a
description. They open the order's page and want to see which products still need details
and go straight to each one's McMaster page to capture it.

**Why this priority**: This is the whole of the reported gap.

**Independent Test**: Seed a McMaster order whose lines name products without details;
open the order page. It shows the progress banner, a "missing" mark per line and an
**Open listing** link to `https://www.mcmaster.com/<part>/` for each.

**Acceptance Scenarios**:

1. **Given** a captured McMaster order with two lines whose products have no details,
   **When** the owner opens the order page, **Then** it says 2 of 2 products still need
   details, marks each line "missing", and each line links to
   `https://www.mcmaster.com/<that line's part number>/`, opening in a new tab.
2. **Given** that order after one product has been given details (by any route),
   **When** the owner opens the order page, **Then** it says 1 of 2, the filled-in line
   reads "captured" with no link, and the other still reads "missing" with its link.
3. **Given** every product on the order has details, **When** the owner opens the page,
   **Then** it says every product on this order has its details.

---

### User Story 2 - Orders from other vendors are unchanged (Priority: P1)

**Why this priority**: The change replaces an Amazon-only rule with a per-vendor one; it
must not drop the checklist from Amazon orders or add it where it means nothing.

**Independent Test**: Open an Amazon order page (checklist as before, links to
`https://www.amazon.com/dp/<ASIN>`), a DigiKey order page and an order page for a vendor
no capture flow knows (no checklist on either).

**Acceptance Scenarios**:

1. **Given** a captured Amazon order, **When** its page is opened, **Then** the checklist
   and its Amazon listing links are exactly as before.
2. **Given** a captured DigiKey order, **When** its page is opened, **Then** no checklist
   is shown — DigiKey products arrive with details and no listing address is built for them.
3. **Given** purchases recorded by hand under a vendor with no order capture, **When**
   that order's page is opened, **Then** no checklist is shown and the page still renders.

### Edge Cases

- A McMaster line with no part number: marked "missing" if its product lacks details, but
  offers no link — there is no address to build (same as an Amazon line without an ASIN).
- A line with no product: no mark, as today.
- An order page with no lines ("not captured"): no checklist, as today.
- Two lines naming one product count once, as today.
- Capturing a McMaster order does **not** start any automatic per-line listing read; that
  remains Amazon-only (044 US4).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Whether an order page shows the details checklist MUST be decided by whether
  the order's vendor has a buildable product-listing address, not by naming one vendor.
- **FR-002**: Amazon's listing address MUST remain `https://www.amazon.com/dp/<ASIN>`.
- **FR-003**: McMaster-Carr's listing address MUST be `https://www.mcmaster.com/<part>/`,
  built from the line's part number.
- **FR-004**: DigiKey, and any vendor with no order capture, MUST have no listing address
  and so no checklist.
- **FR-005**: Each line's **Open listing** link MUST use its own vendor's address.
- **FR-006**: The explanation recorded in the code for which vendors get the checklist
  MUST state the actual reason (products created without details, and a listing address
  that can be built), and MUST NOT claim Amazon is the only vendor meeting it.
- **FR-007**: Automatic listing reads at order capture (044 US4) MUST remain Amazon-only.
- **FR-008**: Automated end-to-end coverage MUST exercise the McMaster checklist and the
  absence of a checklist on a DigiKey order.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a captured McMaster order page, every line whose product lacks details
  offers a working link to that part's McMaster page — 100% of such lines with a part
  number.
- **SC-002**: Amazon order pages render identically before and after the change; the
  existing Amazon checklist tests pass unmodified.
- **SC-003**: DigiKey order pages show no checklist.

## Assumptions

- McMaster's product page for a part is reachable at `https://www.mcmaster.com/<part>/`
  with the part number as stored (e.g. `91290A115`), per 028 research and issue #170.
- The banner's wording ("capture it with the browser extension … brings you back here")
  holds for McMaster: 049 made details-only capture find a McMaster order's product, and
  the return to the order is vendor-neutral (044 FR-020).
- The product page's own "missing details" link (044 FR-018) is out of scope; the issue
  asks only for the order page.
