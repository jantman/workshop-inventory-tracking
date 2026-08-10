# Feature Specification: Product Catalog & Purchase Tracking

**Feature Branch**: `product-catalog`
**Created**: 2026-08-02
**Status**: Draft
**Input**: Enhancement to an existing workshop inventory application, adding the ability to catalog and identify purchased parts, supplies, and components.

---

## Overview

The existing application manages metal stock inventory for a single-person hobby workshop. This feature extends it to catalog the other things the workshop buys: electronic, electrical, and hardware components and supplies, mostly unbranded imports from Amazon, plus well-labeled parts from industrial distributors.

The purpose is **identification, not inventory control**. When a part is picked up off a shelf months after purchase, the operator needs to know what it is, its key specifications, where it came from, and what it cost — without depending on a vendor product page that may have changed or disappeared. Today this information is transcribed by hand onto a printed label at the moment a package is unpacked, and no copy of that label is retained. This feature captures that information as durable, searchable data and removes the need to re-derive it from vendor pages.

The operator has an established inventory of tens of thousands of existing items. The overwhelming majority will never be cataloged, and that is expected and acceptable. The goal is to identify things acquired from this point forward, plus the occasional high-value existing item the operator chooses to enter by hand.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identify a part in hand (Priority: P1)

The operator finds an unlabeled or unfamiliar part on a shelf, or picks up a bin whose contents they no longer recognize. They scan the label on it — or the manufacturer's barcode on its packaging — and the system tells them what it is: description, specifications, what they paid, and when.

**Why this priority**: This is the core purpose of the entire feature. Everything else exists to make this moment work. If a scan reliably answers "what is this thing," the feature has delivered its central value even with nothing else built.

**Independent Test**: Enter a product, print its label, walk away, scan the label, and confirm the system displays the correct identifying information. Fully testable on its own.

**Acceptance Scenarios**:

1. **Given** a cataloged product with a printed label, **When** the operator scans that label, **Then** the system displays the product's description, specifications, purchase history, and location if recorded.
2. **Given** a cataloged product whose packaging carries a manufacturer barcode that was recorded, **When** the operator scans that barcode, **Then** the same product is displayed.
3. **Given** a barcode that matches nothing in the catalog, **When** the operator scans it, **Then** the system offers to create a new product with that identifier already attached, rather than showing an error.

---

### User Story 2 - Capture a purchase and produce a label (Priority: P1)

The operator buys something. When it arrives, they record what it is and print a label to put on the bin, box, or bag. The label carries the operator's own concise description and the purchase details, and it can be reprinted at any time if it wears out or a lot is split across containers.

**Why this priority**: Producing durable labels is the second half of the core loop and the activity that currently costs the most manual effort. Without it, there is nothing to scan in Story 1.

**Independent Test**: Record a purchase, author a description, print a label, and confirm the label is legible and complete. Reprint it and confirm the output is the same.

**Acceptance Scenarios**:

1. **Given** a received item, **When** the operator records its description, purchase details, and optional specifications, **Then** a product and its purchase are stored together.
2. **Given** a stored product, **When** the operator prints its label, **Then** the label carries the description, the purchase provenance, and a scannable code that resolves back to the product.
3. **Given** a previously printed label that is damaged or lost, **When** the operator requests a reprint, **Then** the label is reproduced without re-entering any information.
4. **Given** a stored product, **When** its label is printed, **Then** the code identifying the product appears both as a scannable symbol and as human-readable text.

---

### User Story 3 - Capture order details when the order is placed (Priority: P2)

Rather than reconstructing purchase information at unboxing time from a vendor page that may have changed, the operator captures it while placing the order, when the listing is in front of them. The vendor, item identifier, listing title, order date, and price are recorded then. Because the full listing — including specifications that may not survive to delivery — is visible at that moment, the operator may also author the label description up front. When the package arrives, that information is already waiting.

**Why this priority**: This removes the most error-prone and time-consuming step in the current workflow, but the feature is still valuable without it — Story 2 covers capture at receipt time. This makes the common case faster and more reliable.

**Independent Test**: From a vendor product page, trigger capture, then confirm a pending purchase exists with the correct details and can be completed when the item arrives.

**Acceptance Scenarios**:

1. **Given** the operator is viewing a vendor product listing, **When** they trigger capture, **Then** a purchase record is created with vendor, item identifier, listing title, order date, and price, marked as not yet received.
2. **Given** a captured purchase whose item identifier matches an existing product, **When** capture occurs, **Then** the purchase is attached to that existing product rather than creating a duplicate.
3. **Given** a captured purchase, **When** the package arrives and the operator opens it, **Then** the previously captured details are present and the operator confirms or amends them.
4. **Given** the operator authored a description at capture time, **When** the item is received, **Then** that description is presented for confirmation rather than requiring composition from scratch.

---

### User Story 4 - Catalog a distributor part from its own label (Priority: P2)

Parts from industrial distributors already arrive well-labeled with a machine-readable code carrying the manufacturer part number, quantity, and order references. The operator scans that code and the catalog entry is populated from it, without printing a new label — the distributor's own labeling is sufficient.

**Why this priority**: These parts don't need a printed label, so the value here is capturing them into the searchable catalog and purchase history cheaply. Lower priority than the Amazon-style flow because the identification problem is already partly solved by the distributor.

**Independent Test**: Scan a distributor's part label and confirm the manufacturer part number, quantity, and order reference are extracted into a draft catalog entry.

**Acceptance Scenarios**:

1. **Given** a distributor part label with a standard machine-readable code, **When** the operator scans it, **Then** the manufacturer part number, quantity, and order references are extracted and presented as a draft entry.
2. **Given** an extracted draft, **When** the operator reviews it, **Then** every extracted value remains editable before saving.
3. **Given** a scanned code that does not conform to the expected distributor format, **When** it is processed, **Then** the raw scan is surfaced for manual handling rather than failing silently.

---

### User Story 5 - Recognize repeat purchases and track price history (Priority: P2)

Some items are bought repeatedly. When the operator buys something they've purchased before, the system recognizes it as the same product and records the new purchase against it, building a visible history of what was paid and when.

**Why this priority**: Valuable for reordering decisions and avoiding duplicate catalog entries, but the core identification purpose works without it.

**Independent Test**: Record two purchases of the same product at different prices and dates, and confirm both appear in one product's history with the prices shown.

**Acceptance Scenarios**:

1. **Given** a product with a prior purchase, **When** the operator records a new purchase of the same product, **Then** both purchases appear in one chronological history.
2. **Given** a product with purchase history, **When** the operator views it, **Then** the most recent price paid is visible.
3. **Given** two visually similar but genuinely different variants, **When** they are cataloged, **Then** the operator can keep them as distinct products.

---

### User Story 6 - Know what to reorder (Priority: P3)

For the minority of items where running out actually matters — high-value or long-lead-time parts — the operator wants a heads-up before they're gone. They can flag an item as low regardless of whether its quantity is counted, and for items whose quantity is tracked, low status is raised automatically. A single view shows everything that needs reordering, with items already on the way clearly marked so they aren't ordered twice.

**Why this priority**: Genuinely useful but deliberately narrow. Most items in the workshop will never have quantity tracked or a reorder flag set, and that is intended. This serves the handful of parts where a stockout has real cost.

**Independent Test**: Flag one uncounted item as low and set another counted item below its threshold, then confirm both appear in the reorder view, and that an item with an outstanding order is marked as on the way.

**Acceptance Scenarios**:

1. **Given** an item whose quantity is not tracked, **When** the operator flags it as low, **Then** it appears in the reorder view.
2. **Given** an item whose quantity is tracked and has a reorder threshold, **When** its quantity falls to or below that threshold, **Then** it is shown as low without any manual action.
3. **Given** a low item with an order not yet received, **When** the reorder view is shown, **Then** that item is marked as already on the way.
4. **Given** a low item, **When** its outstanding order is marked received, **Then** it is no longer shown as low.

---

### User Story 7 - Classify and find things (Priority: P3)

The operator organizes products into a rough hierarchy of categories and can also tag them freely across categories. They can search the catalog by description, specification, identifier, or category and filter the results.

**Why this priority**: Improves retrieval as the catalog grows, but a small catalog is navigable without it, and the identification loop doesn't depend on it.

**Independent Test**: Assign several products to categories and tags, then confirm searching and filtering returns the expected subsets.

**Acceptance Scenarios**:

1. **Given** products assigned to categories, **When** the operator filters by a category, **Then** only products in that category and its sub-categories are shown.
2. **Given** products with tags that cut across categories, **When** the operator filters by a tag, **Then** the matching products are returned regardless of category.
3. **Given** a search term appearing in a description, specification, or identifier, **When** the operator searches, **Then** matching products are returned.
4. **Given** the operator needs a category that does not yet exist, **When** they enter it during product creation, **Then** it is created without a separate setup step.

---

### Edge Cases

- A scanned identifier is a manufacturer barcode that the operator has never associated with a product. The system must let them create the product with that identifier attached, not dead-end on "not found."
- The same real-world product is sold under several different vendor listings and identifiers. The operator must be able to keep it as one product with multiple purchases and multiple recorded identifiers.
- A vendor reuses an item identifier for a completely different product over time. The catalog must not silently conflate the two; product identity must not depend solely on a vendor's item identifier.
- A quantity is recorded and then not revisited for a long time. The system must convey that the count may be stale rather than presenting it as currently authoritative.
- A code prints on a label and then partially degrades on the shelf. The label must remain usable, because the same information is present in human-readable form.
- An item is received in a quantity or condition that differs from what was ordered. The operator must be able to amend the purchase at receipt.
- A distributor code does not parse. The raw contents must be surfaced for manual handling.
- The connection drops while the operator is part-way through composing a description. Their in-progress text must not be lost.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow products to be cataloged independently of any purchase, so that existing items can be entered by hand.
- **FR-002**: The system MUST keep products and purchases as distinct records, where one product may have many purchases over time.
- **FR-003**: The system MUST allow a product's identifying description to be authored and edited by the operator, and MUST treat this description as the authoritative human-readable identity of the product.
- **FR-004**: The system MUST record, for each purchase, at minimum the vendor, the vendor's item identifier, the order date, whether and when it was received, the quantity, and the price paid.
- **FR-005**: The system MUST allow a purchase to exist in an unreceived state and later be marked received.
- **FR-006**: The system MUST present, for any product, its full purchase history including dates, vendors, and prices, and MUST make the most recent price visible.
- **FR-007**: The system MUST store multiple identifiers of differing kinds against a single product, including manufacturer part numbers, retail/consumer barcodes, vendor item identifiers, and any code the system itself prints.
- **FR-008**: The system MUST NOT make a product's identity depend on a vendor's reusable item identifier, so that later reuse of that identifier by the vendor cannot corrupt the catalog.
- **FR-009**: The system MUST resolve equivalent forms of the same retail/consumer barcode to a single product, regardless of which length or form was scanned.
- **FR-010**: The system MUST detect and reject clearly invalid retail/consumer barcodes on entry, while allowing the operator to override and store one deliberately.
- **FR-011**: The system MUST produce, for any product, a printed label bearing the operator's description, the purchase provenance, and a scannable code that resolves back to that product.
- **FR-012**: The system MUST render the product-identifying code on the label in both scannable and human-readable form.
- **FR-013**: The system MUST allow any label to be reprinted on demand from the stored record, without re-entry.
- **FR-014**: The system MUST accept scanned input and route it to the correct outcome — internal product lookup, distributor-label interpretation, retail-barcode lookup, or general search — without the operator choosing the type first.
- **FR-015**: The system MUST distinguish codes it printed itself from codes originating elsewhere, so that a foreign code carrying a coincidentally similar value is not mistaken for one of the operator's products.
- **FR-016**: The system MUST interpret the standard machine-readable labels used by industrial electronics distributors, extracting at least the manufacturer part number, quantity, and order references.
- **FR-017**: The system MUST use interpreted distributor-label data to pre-fill a draft entry, leaving every value editable by the operator.
- **FR-018**: The system MUST, when a scan matches no existing record, offer creation of a new product with the scanned identifier pre-attached, rather than presenting an error.
- **FR-019**: The system MUST, when a scan matches an existing product during receiving, offer to add a purchase to that product rather than creating a duplicate.
- **FR-020**: The system MUST support capturing purchase details, and optionally a label description, at the time an order is placed, from the vendor's listing.
- **FR-021**: The system MUST attach an order-time capture to an existing product when the captured identifier matches one, and otherwise create a new product.
- **FR-022**: The system MUST allow quantity on hand to be tracked for some products and not others, and MUST visibly distinguish "tracked and none on hand" from "quantity not tracked."
- **FR-023**: The system MUST default new products to untracked quantity, so that tracking is a deliberate choice per product.
- **FR-024**: The system MUST convey the age of a tracked quantity, so that a long-unverified count is not presented as currently authoritative.
- **FR-025**: The system MUST allow the operator to manually flag a product as low or out regardless of whether its quantity is tracked.
- **FR-026**: The system MUST automatically treat a tracked product as low when its quantity falls to or below an operator-set reorder threshold.
- **FR-027**: The system MUST present a single reorder view combining manually flagged and automatically detected low products.
- **FR-028**: The system MUST indicate, within the reorder view, which low products already have an unreceived order outstanding, without the operator recording that state separately.
- **FR-029**: The system MUST clear a product's low status when an outstanding order for it is marked received.
- **FR-030**: The system MUST allow products to be organized in a hierarchy of categories of arbitrary depth, and MUST allow new categories to be created inline during product entry.
- **FR-031**: The system MUST allow products to carry free-form tags independent of their category, so that a product can be found along more than one dimension.
- **FR-032**: The system MUST allow searching across descriptions, specifications, identifiers, and part numbers, and filtering results by category, tag, and stock status.
- **FR-033**: The system MUST allow optional recording of a storage location for a product.
- **FR-034**: The system MUST allow arbitrary supporting files — datasheets, wiring diagrams, saved listings, photographs — to be attached to a product or a specific purchase, for the minority of items that warrant it.
- **FR-035**: The system MUST preserve an operator's in-progress entry against an interrupted connection, so that composed text is not lost.
- **FR-036**: The system MUST remain fully usable from a touch interface with no physical keyboard, so that a scan result can be read and acted on — quantity adjusted, low status set — on a handheld device.

### Key Entities

- **Product**: A distinct kind of thing the workshop holds. Carries the operator's identifying description, optional manufacturer and part number, optional specifications, an optional category, optional tags, optional location, and optional stock information. Has many identifiers and many purchases.
- **Purchase**: A single acquisition of a product. Carries the vendor, the vendor's item identifier, order date, received date, quantity, price, and order reference. Belongs to one product. May be outstanding (unreceived) or complete.
- **Identifier**: A coded name for a product, of a stated kind (manufacturer part number, retail/consumer barcode, vendor item identifier, distributor part number, or a code the system printed). A product may have several; a given identifier points to at most one product.
- **Category**: A position in a hierarchy used to classify products. Created as needed.
- **Tag**: A free-form label applied across categories for retrieval.
- **Attachment**: A supporting file associated with a product or a purchase.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A part bearing a system-printed label can be identified by a single scan, with no navigation to any external site and no network access beyond the application itself.
- **SC-002**: Recording a received purchase and producing its label requires the operator to author only the description and specifications; all mechanical purchase details are already present when captured at order time.
- **SC-003**: A worn or lost label can be reproduced without re-entering any information.
- **SC-004**: A part from an industrial distributor can be cataloged from its own label by scanning, without composing a description or printing a new label.
- **SC-005**: A repeat purchase of a previously cataloged product is recorded against the existing product, not as a duplicate, in the normal flow.
- **SC-006**: Every item flagged low or fallen below threshold appears in one reorder view, and items already on order are visibly distinguished there.
- **SC-007**: The distinction between "none on hand" and "not tracked" is unambiguous everywhere quantity is shown.
- **SC-008**: A scan of an unknown code leads directly to product creation with that code attached, never to a dead end.
- **SC-009**: The catalog can be searched and a specific product located by any of its description, specification, or identifier.
- **SC-010**: Every task that can be performed at the workshop cart can also be performed on a handheld touch device without a keyboard.

---

## Assumptions

### Scope boundaries

- This is a single-user application for one hobby workshop. There is no multi-user, permissions, sharing, or concurrency requirement. Throughput is on the order of tens of items received per month.
- The existing pre-enhancement inventory of tens of thousands of items will not be bulk-imported. Manual entry of individual existing items is supported; no bulk-import tooling, workflow, or interface is in scope, though nothing should preclude adding one later.
- Existing external identifiers (manufacturer, retail, vendor, distributor) are used wherever they exist. The operator does not want to invent an independent internal numbering scheme, beyond whatever minimal internal code is needed to link a printed label back to its record.
- Quantity and location tracking are optional per product and expected to be used only for a small minority of items. The system is fully useful for its identification purpose with quantity tracking never enabled.
- Identification is the goal, not inventory control. Consumption-event logging (decrementing counts as parts are used) is out of scope.

### Agreed technical constraints

These are boundaries already decided, stated as constraints on the solution rather than as design detail. They exist to keep later planning from re-opening settled questions.

- The feature extends the existing application. It MUST NOT introduce a separate service, a separate datastore, or a separate mobile application. It shares the existing application's authentication, deployment, storage, and backup.
- Label printing MUST reuse the application's existing label-printing capability. No new printer control language, driver, or printing path is to be introduced. In particular, native printer command languages such as SBPL are explicitly out of scope; the existing raster-image printing path is used.
- The user interface remains a single responsive interface serving both the workshop cart and, in future, tablets or handheld data terminals. A separate mobile-specific interface is out of scope.
- Barcode scanning uses the existing keyboard-style scanner input already supported by the application. No scanner-specific driver or vendor integration is to be introduced, so that future handheld scanners work unchanged.
- Automated or unattended scraping of vendor websites is out of scope. Order-time capture is an operator-initiated action while viewing a listing.
- Automatic generation of product descriptions or specifications by a language model is out of scope. Descriptions are authored by the operator, because they routinely contain knowledge not present in any listing and an incorrect specification printed on a durable label is a serious, silent failure. Language-model assistance, if ever added, is confined to search and retrieval where errors are visible and recoverable.
- Integration with distributor product APIs for catalog enrichment is out of scope for this feature. The design should not preclude adding such enrichment later, but no such integration is to be built now.
- An external-database lookup of retail barcodes is not relied upon. Coverage for the kinds of parts cataloged here is poor, so any such lookup could only ever be an optional convenience, and none is in scope.

### Environmental assumptions

- The workshop has network connectivity to the application from the point of use. Full offline operation with local storage and later synchronization is out of scope; the only resilience required is that a momentary interruption not discard in-progress entry.
- Labels are printed on direct-thermal media on the existing label printers, which do not support thermal-transfer. Long-term legibility in a workshop environment is a known limitation, mitigated by dual scannable/human-readable encoding and on-demand reprinting rather than by any change of printer or media within this feature.

### Open questions carried into planning

- **[NEEDS CLARIFICATION]**: Confirm the behaviour of the deployed barcode scanner with respect to the machine-readable label formats used, so that scan routing can rely on it. This affects Story 1 and Story 4 and should be settled early.
- **[NEEDS CLARIFICATION]**: Confirm which label sizes on the existing printers are in scope for product labels versus reserved for other uses.
- **[NEEDS CLARIFICATION]**: Decide whether recording explicit "same real-world product under different vendor listings" equivalence is wanted now or deferred; the edge case is acknowledged, but whether it needs dedicated support beyond multiple identifiers on one product is undecided.
