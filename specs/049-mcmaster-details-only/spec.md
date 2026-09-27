# Feature Specification: McMaster Details-Only Capture

**Feature Branch**: `robot-army/issue-171-mcmaster-order-products-can-t-have`

**Created**: 2026-09-27

**Status**: Draft

**Input**: GitHub issue #171, "McMaster order products can't have details added:
find_listing_match only looks up VENDOR identifiers"

## Background

Feature 044 let the owner capture a product listing *onto* a product that an order had
already created — adding the listing's photos, description and specification rows without
recording a second purchase. It was built and tested against Amazon.

For McMaster-Carr it does not work. A McMaster order creates each line's product carrying
the McMaster part number as a **distributor** identifier. A McMaster product-page capture
records the same part number as a **vendor** identifier, and every "does this item number
already name a product?" question the product-page capture asks looks only for a vendor
identifier. So the product the order created is invisible to it:

- the confirmation page never offers "add this listing's details, record no purchase", and
  offers only "this is a separate order — record it anyway";
- recording it creates a **second product** for the same McMaster part.

Feature 028 (FR-012, US2 scenario 2) specified that a McMaster product-page capture record
the part number as a distributor identifier. Shipped behaviour recorded a vendor
identifier instead, and 028's verification recorded that as a deliberate deviation. This
feature brings the code into line with 028 as specified.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add a McMaster listing's details to the product its order created (Priority: P1)

The owner has captured a McMaster order. One of its parts arrived with nothing but a
description, so they open that part's product page on mcmaster.com and capture it, wanting
its photos and specification rows on the product the order created — and no second
purchase, because they bought it once.

**Why this priority**: This is the reported defect, and it is the only way to get a
McMaster listing's details onto an order-created product at all.

**Independent Test**: Capture a McMaster order with one line, then capture that line's
product page. The confirmation page names the product the order created and offers to add
the listing's details without recording a purchase; choosing it updates that product and
records nothing.

**Acceptance Scenarios**:

1. **Given** a McMaster order has been captured and created a product for part `91290A115`,
   **When** the owner captures the McMaster product page for `91290A115`, **Then** the
   confirmation page identifies that product and offers "add the listing's details, record
   no purchase" — exactly as it does for an Amazon product created by an Amazon order.
2. **Given** that same page, **When** the owner chooses details-only and submits, **Then**
   the listing's specification rows and photos land on the order-created product, no
   purchase is recorded, and the product's counts are unchanged.
3. **Given** that same page, **When** the order's line is the purchase the capture would
   repeat, **Then** the page puts one question naming the order (044 FR-009), not the
   generic "record it anyway" warning.

---

### User Story 2 - A product page captured first is found by its own later captures (Priority: P1)

The owner captures a McMaster product page first — recording a purchase — and later
captures the same product page again (or the order that contains that part).

**Why this priority**: Changing which kind of identifier a product-page capture records
must not break the reverse direction, which works today, nor make a product invisible to
the next capture of its own page.

**Independent Test**: Capture a McMaster product page as a purchase, then capture the same
page again; the confirmation page names the product the first capture created and offers
details-only. Separately, capture the order containing that part; the order line lands on
the existing product rather than creating a new one.

**Acceptance Scenarios**:

1. **Given** a McMaster product-page capture created a product for part `91290A115`,
   **When** the owner captures the order containing `91290A115`, **Then** the order line
   attaches to that product and no second product is created.
2. **Given** that same product, **When** the owner captures the same product page again,
   **Then** the confirmation page identifies it and offers details-only.
3. **Given** a McMaster product-page capture creates a product, **Then** that product carries
   the part number as a distributor identifier scoped to McMaster-Carr (028 FR-012, US2
   scenario 2), the same kind the order capture records.

---

### User Story 3 - A McMaster purchase capture after an order lands on the order's product (Priority: P2)

The owner captures a McMaster order and later captures one of its parts' product pages as a
genuinely separate purchase (for instance a reorder).

**Why this priority**: Today this silently creates a second product for the same part. It
is the same lookup defect as US1, surfacing on the purchase path rather than the details
path.

**Independent Test**: Capture a McMaster order, then capture one of its parts' product pages
and record the purchase. The purchase attaches to (or asks about) the order-created product;
no second product appears for that part number.

**Acceptance Scenarios**:

1. **Given** an order-created McMaster product for part `91290A115`, **When** a product-page
   capture for `91290A115` records a purchase, **Then** the purchase is on that product —
   or, where manufacturer and part number do not corroborate, the owner is asked about it
   exactly as for any other matched item number — and no second product is created.

---

### Edge Cases

- **Amazon is untouched.** Amazon captures record and look up the same kind of identifier
  they do today; every Amazon capture, details-only or purchase, behaves exactly as before.
- **DigiKey.** A DigiKey order also records its part numbers as distributor identifiers. The
  browser extension has no DigiKey product-page reader, so a DigiKey product reaches these
  questions only through the paste-a-URL form with an item number the owner typed. After
  this feature that number finds the DigiKey product the order created — the same vendor's
  same part number naming the same thing — where before it silently created a second
  product. This is intended.
- **A product carrying the vendor-kind McMaster identifier** (recorded by a product-page
  capture before this feature) is still found by every lookup; nothing needs rewriting.
- **Another vendor's identifier with the same value** is never matched: every lookup remains
  scoped to the capture's own vendor.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the confirmation page asks whether a listing's item number already names a
  product, it MUST find a product carrying that number as either a vendor or a distributor
  identifier, scoped to the capture's vendor.
- **FR-002**: When a purchase capture asks whether its item number already names a product
  (to attach, or to ask), it MUST resolve the same way as FR-001, so the two questions
  always agree about which product an item number names.
- **FR-003**: A McMaster-Carr product-page capture that creates a product MUST record the
  part number as a distributor identifier scoped to McMaster-Carr (028 FR-012).
- **FR-004**: Every other vendor's product-page capture MUST record exactly the identifier
  it records today.
- **FR-005**: No lookup may match an identifier scoped to a different vendor.
- **FR-006**: Automated tests MUST cover McMaster details-only in both directions — order
  then product page, and product page then order — and a McMaster purchase capture after an
  order.
- **FR-007**: No data migration is required or performed; products already recorded either
  way continue to be found.

### Key Entities

- **Product identifier**: a value naming a product, with a kind (vendor, distributor, …) and,
  for vendor-scoped kinds, the vendor whose identifier it is. A McMaster part number is a
  distributor identifier scoped to McMaster-Carr.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a McMaster part captured from an order, capturing its product page offers
  details-only in 100% of cases, as it already does for Amazon.
- **SC-002**: Capturing a McMaster part through both an order and its product page, in either
  order, leaves exactly one product for that part number.
- **SC-003**: Every existing Amazon capture test passes unchanged.
- **SC-004**: The owner can attach a McMaster listing's photos and specification rows to an
  order-created product without recording a purchase.

## Assumptions

- Single installation; the only McMaster products in the live catalog came from the order
  that surfaced this issue, so no historical data needs converting (and FR-001's "either
  kind" covers any that exists).
- `specs/028-*` and `specs/044-*` are the frozen record and are not edited; this spec
  supersedes 028 verification §A6's deviation.
