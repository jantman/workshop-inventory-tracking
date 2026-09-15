# Feature Specification: Capture Product Details for Products an Order Created

**Feature Branch**: `robot-army/issue-156-amazon-order-capture-workflow-bug`

**Created**: 2026-09-15

**Status**: Draft

**Input**: User description: "issue #156 on this repo — Amazon order capture workflow bug", plus the
workflow agreed with the issue's author before specifying (recorded under *Decisions agreed before
specifying* below).

## Background

The operator captures an Amazon order from its Order Details page with the bookmarklet. Every new
product that capture creates carries only what the order page states: a description, the item
number (ASIN) and the purchase. No brand, part number, specifications, barcodes or pictures.

The order review promises a way to fill those in later (`specs/029-whole-order-capture/spec.md`
FR-027, and the note on the order review page): *"capture the item's own listing page afterwards. It
attaches to the same product … and it recognizes the purchase this order recorded rather than
writing a second purchase."* That promise was never kept. Running the bookmarklet on the listing
raises two warnings — "You may have captured this already" and "This item number already names
something" — and every answer to them records another purchase. The product's details can
therefore only be added by corrupting the purchase history, which is the reported defect.

### Decisions agreed before specifying

These were settled with the issue's author and are requirements, not open questions:

- **A. Details-only capture.** A listing capture that matches an existing product can update that
  product's details without recording a purchase — for any matched product, not only those an order
  created.
- **B. Show and choose.** Details the product lacks are filled; details it already holds that differ
  from the listing are shown side by side, and nothing is overwritten unless the operator chooses
  it, field by field.
- **C. Order checklist.** After an order capture, the order's page lists each line with whether its
  product's details are captured, and links to the listing to capture them.
- **D. Auto-fetch.** An order capture reads each line's own listing page as well, so one capture can
  produce fully-detailed products. Lines whose listing could not be read fall back to the checklist.
  This deliberately reverses `specs/029-whole-order-capture/spec.md` FR-025.
- **E. Warnings.** The operator is warned before a choice that makes the catalog harder to put
  right.

## User Scenarios & Testing *(mandatory)*

The operator is the only user. Every scenario is one person bringing a real purchase into the
catalog and wanting both the purchase and the product's full details recorded, once each.

### User Story 1 - Add a listing's details to a product without recording a purchase (Priority: P1)

The operator has a product in the catalog that is missing details — because an order capture
created it, or because details were never captured for some other reason. They open that item's
listing and click the bookmarklet. The confirmation page recognizes the product by its item number
and offers to update that product's details only. They confirm, and the product gains the listing's
brand, part number, specifications, barcodes and pictures. No purchase is recorded, and the
product's purchases, quantity and stock are exactly as they were.

**Why this priority**: This is part 1 of the issue and the core of the defect. On its own it gives
the operator a way to repair every thin product already in the catalog, including the ones the
reported order created.

**Independent Test**: Create a product holding only a description and an item number, with one
purchase. Capture a listing for that item number and choose details-only. The product carries the
listing's details, and it still has exactly one purchase.

**Acceptance Scenarios**:

1. **Given** a product holding item number X, **When** the operator captures a listing whose item
   number is X, **Then** the confirmation page names that product and offers "update this product's
   details only — don't record a purchase" alongside the existing choice of recording a purchase.
2. **Given** that choice selected, **When** the operator confirms, **Then** the product gains every
   detail it lacked (manufacturer, part number, specification rows, barcodes, pictures), and no
   purchase is created, changed or deleted.
3. **Given** a product that already holds a manufacturer, part number, description or specification
   row whose value differs from the listing's, **When** the details-only confirmation page is shown,
   **Then** each differing value is shown beside the listing's value with its own choice to replace
   it, and each defaults to keeping the current value.
4. **Given** that page, **When** the operator confirms having chosen to replace some differing
   values and not others, **Then** exactly the chosen values are replaced and every other current
   value is unchanged.
5. **Given** a product that already holds everything the listing yields, with identical values,
   **When** the operator captures the listing details-only, **Then** the page says there is nothing
   new to add, and confirming changes nothing — no duplicate specification rows, barcodes or
   pictures.
6. **Given** a details-only capture has been confirmed once, **When** the operator captures the same
   listing details-only again, **Then** nothing is duplicated.
7. **Given** a listing whose item number matches no product, **When** it is captured, **Then**
   details-only is not offered and the capture behaves as it does today.

---

### User Story 2 - A listing capture after an order capture asks one clear question (Priority: P1)

The operator has captured an order, and one of its lines created a product. They now capture that
item's listing, which is exactly what the order review told them to do. Instead of two warnings
whose every answer records a second purchase, they see one message: this is the item from order
*number*, add the listing's details to it. Details-only is already selected, so confirming does the
right thing. Recording a separate purchase is still available, for the case where they really have
bought it again, and choosing it explains what it will do.

**Why this priority**: This is the exact path the operator followed in the issue, and the path the
order review tells them to take. User Story 1 makes a correct outcome possible; this story makes it
the obvious one.

**Independent Test**: Capture an order containing item X, then capture the listing for X, and
confirm without changing anything. The product gains the listing's details, and the catalog still
holds exactly one purchase for X.

**Acceptance Scenarios**:

1. **Given** a purchase for item X recorded by an order capture, attached to the product holding X,
   **When** the operator captures the listing for X within the window in which the two are already
   recognized as possibly one purchase, **Then** the confirmation page shows a single message
   naming the order and the product, instead of the two separate warnings shown today.
2. **Given** that message, **When** the page is first shown, **Then** "add the listing's details to
   this product — don't record a purchase" is the selected choice.
3. **Given** that message, **When** the operator confirms without changing the choice, **Then** the
   outcome is that of User Story 1 scenario 2, and the operator lands on that order's page (User
   Story 3).
4. **Given** that message, **When** the operator selects recording a separate purchase, **Then**
   the page states plainly, before they confirm, that this records a second purchase of the item
   alongside the one the order recorded. On confirming, the purchase is recorded and the listing's
   details are applied to the product under the same show-and-choose rule.
5. **Given** a listing capture for item X where a product holds X but no order-captured purchase
   matches, **When** the page is shown, **Then** no order is named and recording a purchase stays
   the selected choice, since a new purchase is the likely intent. Details-only is still offered
   (User Story 1).

---

### User Story 3 - The order's page guides the operator through its products' details (Priority: P2)

Straight after confirming an order capture, the operator lands on the order's page. Each line shows
whether its product's details are captured, and the page says how many are still missing. Each
missing line has a link that opens the item's listing. The operator follows a link, runs the
bookmarklet, confirms (User Story 2), and is brought back to the order's page, where that line now
reads as captured. When every line reads as captured, the page says the order is complete.

**Why this priority**: This is part 2 of the issue, the guided process. It depends on User Stories 1
and 2 to be useful. It is also what remains once auto-fetch (User Story 4) has done what it can, so
it is the process's floor.

**Independent Test**: Capture an order of three new items without listing details, then open the
order's page. It reports three products missing details, each with a link to its listing. Capture
one listing details-only and you are returned to the page, which now reports two.

**Acceptance Scenarios**:

1. **Given** an Amazon order has just been confirmed, **When** the operator lands on its page,
   **Then** each line shows whether its product's details are captured or missing, and the page
   states how many lines are still missing details.
2. **Given** a line whose product is missing details, **When** the page is shown, **Then** the line
   offers a link that opens the item's own listing page in a new tab, with a one-line reminder to
   run the bookmarklet there.
3. **Given** the operator completes a details-only capture for a product on that order, **When**
   the capture is confirmed, **Then** they are returned to the order's page, and that line reads as
   captured.
4. **Given** every line's product has its details captured, **When** the order's page is shown,
   **Then** it states the order is complete and shows no missing-details prompts.
5. **Given** a product missing details, **When** the operator opens that product's own page, **Then**
   it states that the details are missing and offers the same link to the listing.
6. **Given** products created from order lines before this feature shipped, holding only what the
   order page stated, **When** their order's page or their own page is shown, **Then** they read as
   missing details, so products already in the catalog can be repaired the same way.

---

### User Story 4 - One order capture reads every line's listing too (Priority: P3)

The operator clicks the bookmarklet on an Amazon Order Details page. As well as reading the order,
it opens each line's own listing in the background, showing its progress, and sends everything
together. The order review shows, per line, what its listing yielded. Confirming creates products
that already carry their brand, part number, specifications, barcodes and pictures. Any line whose
listing could not be read is marked on the review as missing details, and the order's page then
guides the operator through just those lines (User Story 3).

**Why this priority**: Most convenient, and it makes the common case one click. But it depends on
reading many pages from Amazon in one go, which can be throttled or refused, and User Stories 1–3
already give a complete, correct process. So it comes last, and its failures degrade into User
Story 3 rather than into anything the operator has to untangle.

**Independent Test**: Run the order capture against an order page whose lines' listings are
readable, and confirm. Each new product carries its listing's details. Make one line's listing
unreadable: that line's product is created with what the order stated, and it reads as missing
details on the order's page.

**Acceptance Scenarios**:

1. **Given** an Amazon Order Details page, **When** the operator runs the bookmarklet, **Then** it
   reads each line's listing and shows its progress on the page (for example "reading listing 3 of
   5") until it hands off to the review.
2. **Given** every line's listing was read, **When** the review is shown, **Then** each line states
   what its listing yielded — brand, number of specifications, number of pictures, whether a barcode
   was found — using the same summary a single-listing capture shows today.
3. **Given** that review, **When** the operator confirms, **Then** each product the capture creates
   carries its listing's details, exactly as though the listing had been captured on its own.
4. **Given** an order line whose product already exists, **When** its listing was read, **Then**
   the listing fills details that product lacks and overwrites nothing. The review says so, and any
   differing values are left for a details-only capture of that listing (User Story 1).
5. **Given** a line whose listing could not be fetched or read, or came back as something other
   than the listing (a sign-in, robot-check or error page), **When** the review is shown, **Then**
   that line is marked "details not read" with the reason, and the rest of the order is unaffected.
6. **Given** that line is confirmed, **When** the operator lands on the order's page, **Then** that
   line reads as missing details and offers the link to capture them (User Story 3).
7. **Given** no line's listing could be read, **When** the review is shown, **Then** the order can
   still be reviewed and confirmed exactly as it can today, and the review states that details will
   need capturing afterwards.

---

### Edge Cases

- **The listing redirects to a different item number** (a variant or a replacement listing): the
  order line's own item number stays the product's identity. The listing's details are applied only
  when the listing read is recognizably for that item; otherwise the line is marked "details not
  read" with the reason.
- **Two lines of one order share an item number**: the listing is read once and applied to the one
  product both lines name.
- **A barcode the listing yields already belongs to another product**: it is not moved. The existing
  rule for promoting barcodes applies, and the operator is told it was not added.
- **The listing yields a picture the product already holds** (from an earlier capture of the same
  listing): it is not added a second time.
- **A picture fails to download**: the rest of the capture still completes, and the operator is told
  how many pictures could not be saved, as a single-listing capture does today.
- **Details-only is chosen, but the operator has also typed a description, category or location on
  the confirmation page**: those typed values are details like any other. They fill an empty field,
  or stand as the proposed replacement for a differing one under the same per-field choice.
- **The operator files the listing as a different product although its item number names an
  existing one**: before confirming, the page says what that choice means — the new product will not
  carry the item number, so later order and listing captures will not find it, and the existing
  product stays without the listing's details.
- **The operator abandons the process part-way**: nothing is lost or half-written. Each capture is
  complete in itself, and the order's page and the products' own pages keep reporting what is still
  missing.
- **A details-only capture of a product that belongs to no order**: after confirming, the operator
  lands on the product's page.
- **A product whose purchases belong to more than one order**: after a details-only capture, the
  operator is returned to the order named in the confirmation message if there was one, and
  otherwise to the product's page.
- **A large order** (say twenty lines): the bookmarklet reads the listings one after another,
  keeping its progress visible. A failure on one line does not stop the rest.

## Requirements *(mandatory)*

### Functional Requirements

#### Details-only capture

- **FR-001**: When a single-listing capture's vendor item number identifies an existing product, the
  confirmation page MUST offer the choice to update that product's details without recording a
  purchase, whatever path created the product.
- **FR-002**: A details-only capture MUST NOT create, change or delete any purchase. It MUST NOT
  change the product's quantity, stock status or reorder threshold.
- **FR-003**: A details-only capture MUST fill each detail the product lacks from the listing:
  manufacturer, part number, description, category, location, specification rows, barcodes and
  pictures.
- **FR-004**: Where the product already holds a value that differs from the listing's (or from what
  the operator typed on the confirmation page), the page MUST show the current value beside the
  proposed value, with a per-value choice to replace it. Every such choice MUST default to keeping
  the current value. This covers description, manufacturer, part number, category, location, and
  each specification row by name.
- **FR-005**: Confirming a details-only capture MUST replace exactly the values the operator chose,
  and MUST leave every other current value unchanged.
- **FR-006**: A details-only capture MUST NOT duplicate any specification row, barcode or picture the
  product already holds. Repeating the same details-only capture MUST change nothing.
- **FR-007**: When the listing yields nothing the product does not already hold with the same value,
  the confirmation page MUST say so before the operator confirms.
- **FR-008**: The show-and-choose rule of FR-004 and FR-005 MUST also govern the details a listing
  capture applies to an existing product when the operator records a purchase with it. Today that
  capture silently keeps some existing values and ignores others.

#### One question after an order capture

- **FR-009**: When a listing capture matches both an existing product by item number and a purchase
  an order capture recorded for that item (by the existing cross-path rule, spec 033), the
  confirmation page MUST present one message naming the order and the product, in place of the two
  separate warnings.
- **FR-010**: In that case the details-only choice MUST be selected when the page is first shown.
- **FR-011**: In that case recording a separate purchase MUST remain available. Before the operator
  confirms it, the page MUST state that it records a second purchase of the item alongside the one
  the order recorded.
- **FR-012**: When a listing matches an existing product but no order-captured purchase, recording a
  purchase MUST remain the selected choice, and details-only MUST still be offered.
- **FR-013**: Choosing to file a listing as a different product when its item number names an
  existing one MUST be preceded by a statement of the consequence: the new product will not carry
  the item number, and the existing product will not receive the listing's details.

#### Order checklist

- **FR-014**: Each product MUST be distinguishable as having its listing details captured or
  missing. A product is captured once a listing's details have been applied to it by any capture
  path. A product created from an order line with no listing details applied is missing.
- **FR-015**: Products created from order lines before this feature shipped, with no listing details
  applied since, MUST read as missing details. Products created by a single-listing capture MUST read
  as captured.
- **FR-016**: The page of an Amazon order MUST show, for each line, whether its product's details are
  captured or missing, and how many lines are still missing. When none are missing, it MUST say the
  order is complete.
- **FR-017**: Each line whose product is missing details MUST offer a link that opens the item's own
  listing page, with a reminder to run the bookmarklet there.
- **FR-018**: A product's own page MUST state when its details are missing, and offer the same link
  when its item's listing address is known.
- **FR-019**: After confirming an order capture, the operator MUST land on that order's page. This is
  already true and MUST stay true.
- **FR-020**: After confirming a details-only capture whose confirmation message named an order
  (FR-009), the operator MUST land on that order's page. Otherwise they MUST land on the product's
  page.
- **FR-021**: The note on the order review that promises a later listing capture will attach without
  a second purchase MUST describe the behavior this feature delivers, and nothing more.

#### Auto-fetch on the order page

- **FR-022**: When run on an Amazon Order Details page, the bookmarklet MUST also read each line's
  own listing page, reading the same details a single-listing capture reads, and MUST send them with
  the order. This supersedes spec 029 FR-025.
- **FR-023**: While reading listings, the bookmarklet MUST show visible progress on the page until it
  hands off to the review.
- **FR-024**: A listing that cannot be fetched, is not recognizably the listing for that line's item,
  or yields nothing readable MUST NOT stop the capture. That line MUST be marked on the review as
  "details not read", with a short reason.
- **FR-025**: The order review MUST show, per line, what its listing yielded, in the same terms the
  single-listing confirmation page uses.
- **FR-026**: For a line that creates a new product, confirming MUST apply the listing's details to
  the product exactly as a single-listing capture would, and the product MUST read as captured.
- **FR-027**: For a line whose product already exists, confirming MUST fill only details the product
  lacks and MUST overwrite nothing. The review MUST say this, so the operator knows differing values
  can be reviewed with a details-only capture.
- **FR-028**: A line marked "details not read" MUST be written exactly as an order capture writes it
  today, and its product MUST read as missing details.
- **FR-029**: None of the order capture's existing questions — same-purchase adoption, conflicting
  item numbers, re-captured lines — MAY change in meaning because listing details were read.

#### General

- **FR-030**: Every capture path MUST write all it writes in one step, or nothing. An interrupted or
  refused confirmation MUST leave the catalog as it was, except that pictures, which are saved after
  the step completes, may fall short as they can today.
- **FR-031**: Details-only capture (FR-001 to FR-013) applies to any vendor whose listings the
  bookmarklet captures. The order checklist and auto-fetch (FR-016, FR-017, FR-022 to FR-028) apply
  to Amazon orders.

### Key Entities *(include if feature involves data)*

- **Product**: gains a readable state of whether listing details have been captured for it. Its
  existing details (description, manufacturer, part number, category, location, specification rows,
  barcodes, pictures) are what a details-only capture fills or, with consent, replaces.
- **Purchase**: unchanged. A details-only capture never touches one.
- **Order**: still derived from the purchases that carry its number, as today. Its page gains a
  per-line details status and a count of lines still missing details.
- **Listing capture**: what the bookmarklet read from one listing page. It can now arrive on its own
  (single-listing and details-only captures) or once per line of an order (auto-fetch). The
  catalog does not retain it, as today.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The reported scenario works. After capturing an Amazon order and then capturing one of
  its items' listings, confirming the page as first shown leaves that product with its listing's
  details and exactly one purchase for that order line. No box has to be ticked or choice changed.
- **SC-002**: Any product in the catalog, including every product created from an order line before
  this feature shipped, can be given its listing's details in one listing capture, without its count
  of purchases changing.
- **SC-003**: No existing product value is replaced by any capture unless the operator chose to
  replace that specific value.
- **SC-004**: For an Amazon order whose lines' listings are readable, one bookmarklet click and one
  confirmation produce products carrying their full listing details, with no per-product capture
  needed.
- **SC-005**: The operator can tell, from the order's page alone, which of its products still need
  details, and get from there to each listing in one click.
- **SC-006**: An order capture in which some or all listings could not be read still records the
  whole order correctly, and every product left without details is reported on the order's page.
- **SC-007**: Reading listings adds no more than about five seconds per line to an order capture in
  normal conditions. The operator sees progress throughout, never an unresponsive page.

## Assumptions

- **Details-only is chosen per capture, not remembered.** No mode is stored between captures. The
  bookmarklet stays the same single bookmarklet; the confirmation page decides what to offer from
  what the listing matches.
- **Recognition reuses what exists.** "This listing matches a product" means its item number
  identifies the product, as today. "This listing matches an order-captured purchase" is the existing
  cross-path rule and window from spec 033. Neither rule is redefined here.
- **Auto-fetched details never overwrite.** An order review already asks the operator several
  questions per line. Adding a per-value show-and-choose to it for existing products would make it
  unwieldy, so auto-fetch fills blanks only (FR-027) and leaves differing values to a details-only
  capture.
- **Reading listings happens in the operator's browser, from the page they are on**, the way the
  product-page capture already reads a listing. The application itself does not contact Amazon.
- **Listings are read one after another.** A twenty-line order is rare for this operator, and the
  cost is waiting with progress visible. Reading faster is not attempted without a measured need.
- **What "captured" means for existing data** is derived from what the product already holds or how
  it was created, so no manual marking of old products is needed. The plan decides how.
- **The order checklist and auto-fetch are Amazon-only.** Amazon orders are the only page-read orders
  whose products are created without details. DigiKey already enriches from its own API, and
  McMaster orders are unchanged by this feature.
- **Out of scope**: capturing listings for items in an order before the order is captured (covered
  by spec 033); bulk re-capture of many products at once outside an order; changing what a
  single-listing capture reads from the page.
