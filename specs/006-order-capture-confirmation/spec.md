# Feature Specification: Order Capture Confirmation

**Feature Branch**: `issues/58`

**Created**: 2026-08-08

**Status**: Draft

**Input**: GitHub issue #58 — "Order capture: author the description at capture, confirm it at receipt, and don't duplicate or mis-attach", with background in `docs/product-functionality-gap.md`. Reading the **price** off the listing is explicitly excluded: it is issue #56, points 2 and 3.

## Overview

Order capture exists because the vendor's listing is in front of the operator at the moment of ordering and will not be there weeks later when the box arrives. Whatever is not taken off the page at that moment has to be reconstructed afterwards from a page that may have been edited, relisted, or deleted.

As built, capture takes the listing's address and its title, and nothing else the operator would want to keep. The label description — the operator's own words for what this thing is, which is what gets printed and what gets searched — cannot be written at capture. The vendor's page title becomes the description by default, and it stays that way until somebody edits the product. When the box turns up, the receive screen shows that description read-only, so confirming it against the thing in hand means abandoning the receive screen, opening the product, editing it, saving, and navigating back.

Two further problems are silent rather than annoying. Capture recognizes a repeat of itself by vendor, item number and order date. When the listing's address yields no item number there is nothing to recognize, so a second click files a second purchase; and when two genuinely separate orders of the same item are placed on the same day, they collapse into one. Separately, when a vendor recycles an item number — Amazon does — capture attaches the new purchase to the old product without saying so, and that product's price history silently becomes a history of two different things.

This feature makes capture a step the operator completes rather than one that completes itself. A capture is drafted, shown, and confirmed; the description is authored there, while the listing is still on screen. Anything the system is unsure about — this looks like something you already captured, this item number already names a product — is put in front of the operator as a choice, not resolved behind their back. When the box arrives, the same description is editable in place on the receive screen.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Author the label description while the listing is on screen (Priority: P1)

The operator is looking at a vendor's listing for a 12 V 3 A barrel-jack power supply whose page title is a 180-character keyword salad. They capture the order and, in the same step, type what they will actually want to read on the label and find in a search: `12V 3A PSU, 5.5mm barrel`. That is what the product is called from then on. The vendor's title is kept too, as the record of what the listing said, but it is not what the operator has to live with.

**Why this priority**: This is the reason capture happens at order time at all. Everything else in this feature protects the value of a capture; this is the part that puts the value in.

**Independent Test**: Capture an order from a listing address, enter a description that differs from the listing title, confirm the capture, and verify the resulting product carries the entered description while the purchase still records the listing title as the vendor wrote it.

**Acceptance Scenarios**:

1. **Given** a listing address pasted into the capture form, **When** the operator enters a description and confirms, **Then** the created product's description is the entered text and the purchase records the listing title unchanged.
2. **Given** a capture in progress, **When** the operator leaves the description blank and confirms, **Then** the listing title is used as the description, as it is today, and the capture is not refused.
3. **Given** a capture in progress, **When** the operator also enters a manufacturer and a manufacturer part number, **Then** both are recorded against the product.
4. **Given** the operator clicks the bookmarklet on a vendor's listing, **When** the new tab opens, **Then** it presents the capture already filled in from the page's address and title, awaiting a description and a confirmation, and nothing has been recorded yet.
5. **Given** a bookmarklet capture awaiting confirmation, **When** the operator closes the tab without confirming, **Then** no product and no purchase exist as a result.
6. **Given** a capture that will attach to an existing product, **When** the confirmation step is shown, **Then** the description field is pre-filled with that product's current description, and confirming with it changed updates the product's description.

---

### User Story 2 - Confirm or correct the description when the box arrives (Priority: P2)

The box turns up. What is in it is a slightly different revision from what the listing showed, or the description written six weeks ago now reads wrong with the thing in hand. The operator corrects it on the receive screen, in the same action that marks the purchase received, and prints the label.

**Why this priority**: It closes the loop the feature is named for — the moment the workflow was designed around. It is second only because a description authored at capture is worth having even if correcting it still means a detour.

**Independent Test**: Receive a purchase whose product has a known description, change the description on the receive screen, submit, and verify the product carries the new description and the purchase is marked received.

**Acceptance Scenarios**:

1. **Given** an outstanding purchase, **When** the operator opens the receive screen, **Then** the product's description is shown in an editable field pre-filled with its current value.
2. **Given** the receive screen with an edited description, **When** the operator marks the purchase received, **Then** the product's description is updated and the purchase is recorded as received in the same action.
3. **Given** the receive screen, **When** the operator marks the purchase received without touching the description, **Then** the product's description is unchanged.
4. **Given** the receive screen, **When** the operator clears the description entirely and submits, **Then** the submission is refused with a message saying a description is required, and neither the description nor the received state is changed.
5. **Given** a purchase that was recorded by hand rather than captured, **When** it is received, **Then** the description is editable there in exactly the same way.
6. **Given** a purchase that has already been received, **When** the operator edits the description on the receive screen and submits, **Then** the description is updated and the already-received state is unchanged.

---

### User Story 3 - Don't file the same order twice, and don't merge two orders into one (Priority: P3)

The operator clicks the bookmarklet, gets distracted, and clicks it again. Or they order two of the same widget on the same day under separate orders because one is for a friend. Neither case should be decided silently: the first should not become two purchases, and the second should not become one.

**Why this priority**: A duplicate purchase and a swallowed purchase are both wrong records of what was spent and what is coming. It ranks below the description work because the damage is recoverable by hand once noticed.

**Independent Test**: Capture the same listing address twice on the same day and confirm both; verify the second capture warns that a matching capture already exists, names it, and creates a second purchase only if the operator says to.

**Acceptance Scenarios**:

1. **Given** a purchase already captured today from a listing, **When** the operator starts a capture of the same listing on the same day, **Then** the confirmation step says a matching capture already exists, identifies it, and offers both to open the existing one and to record this as a separate order.
2. **Given** that warning, **When** the operator chooses to record a separate order, **Then** a second purchase is created against the same product and both purchases exist independently.
3. **Given** that warning, **When** the operator chooses the existing capture, **Then** nothing new is created and they are taken to that purchase.
4. **Given** a listing whose address yields no vendor item number, **When** the same address is captured a second time on the same day, **Then** the duplicate warning is still raised, matched on the listing address.
5. **Given** a purchase captured yesterday, **When** the same listing is captured today, **Then** no duplicate warning is raised and a new purchase is recorded.
6. **Given** the same item number captured from two different vendors, **When** the second is captured, **Then** no duplicate warning is raised.

---

### User Story 4 - Be told when a vendor's item number already names something else (Priority: P4)

The operator captures a listing whose Amazon item number is one the catalogue has seen before — but the listing is for a completely different part, because the identifier was recycled. Instead of quietly appending a purchase to the old product and corrupting its price history, capture shows what that identifier currently names and asks whether this is the same thing.

**Why this priority**: The most damaging failure in the list, because it is invisible: nothing looks wrong afterwards, and the price history of a product silently becomes the price history of two products. It ranks last only because it is the rarest.

**Independent Test**: Record a product carrying a vendor item number, then capture a listing with that same item number and a conflicting manufacturer part number; verify the confirmation step names the existing product and requires a choice before anything is written.

**Acceptance Scenarios**:

1. **Given** an existing product carrying a vendor item number, **When** a capture yields that same item number for that same vendor, **Then** the confirmation step names the existing product, shows its description and manufacturer part number, and offers both to attach this purchase to it and to create a separate product.
2. **Given** that choice, **When** the operator attaches to the existing product, **Then** the purchase joins that product's history and no new product is created.
3. **Given** that choice, **When** the operator creates a separate product, **Then** a new product is created, the purchase is recorded against it, and the existing product is left untouched — including its identifiers.
4. **Given** a capture whose manufacturer and manufacturer part number are both supplied and both match the existing product's, **When** the capture is confirmed, **Then** it attaches to that product without asking.
5. **Given** a capture whose item number matches no existing product, **When** it is confirmed, **Then** a new product is created without asking.
6. **Given** a capture with no vendor item number at all, **When** it is confirmed, **Then** a new product is created without asking, since there is nothing to match on.

---

### Edge Cases

- **The bookmarklet is clicked twice in quick succession.** Two tabs open, each holding an unconfirmed draft. Nothing exists until one is confirmed; confirming the second raises the duplicate warning from Story 3.
- **A draft is abandoned.** Closing the tab, navigating away, or leaving the page open for a week leaves no trace: an unconfirmed capture is not a record of anything.
- **Confirming a draft whose matched product was deleted meanwhile.** Single-operator app, but the window exists. The confirmation must not fail obscurely; it creates the product it would have created had there been no match.
- **The item number matches an existing product and the operator chooses "separate product".** The vendor item number cannot be recorded against both products, because a vendor's item number is unique within that vendor. The new product is created and the purchase records the item number as the purchase's own vendor item id, without claiming the identifier from the existing product.
- **A description longer than the field allows.** Refused at the point of entry with the limit stated, not silently truncated — a truncated description is a wrong label.
- **A description that is only whitespace.** Treated as blank: at capture it falls back to the listing title, at receipt it is refused.
- **The listing address yields no vendor at all** (an address the system cannot read a host from). Capture is refused as it is today; vendor is required.
- **Two captures of the same listing on the same day, where the first has not been confirmed yet.** Only confirmed captures are matched against, so no warning is raised; the second confirmation warns about the first.
- **Receiving a purchase whose product has since been edited elsewhere.** The receive screen shows the product's description as it currently stands, not as it stood at capture.
- **A capture that attaches to an existing product and changes its description.** The product's description changes for all its purchases, past and future. This is a product-level fact and has one value; the operator changing it at capture is the operator deciding it.

## Requirements *(mandatory)*

### Authoring the description at capture

- **FR-001**: The capture flow MUST let the operator enter the product description before anything is recorded.
- **FR-002**: The capture flow MUST let the operator enter a manufacturer and a manufacturer part number before anything is recorded, both optional.
- **FR-003**: A capture confirmed with a blank description MUST use the listing title as the description, preserving today's behaviour for the operator who does not want to type one.
- **FR-004**: A capture MUST record the vendor's listing title against the purchase exactly as the vendor wrote it, whether or not the operator supplies a description.
- **FR-005**: When a capture will attach to an existing product, the description offered for editing MUST be that product's current description, and a change to it MUST update that product.
- **FR-006**: A description MUST be refused, with the limit stated and nothing recorded, when it exceeds the length a product description can hold; it MUST NOT be silently truncated.

### Confirm before writing

- **FR-007**: A capture MUST NOT create a product or a purchase until the operator confirms it.
- **FR-008**: The bookmarklet MUST land the operator on a confirmation step pre-filled from the listing's address and title, rather than recording the purchase outright.
- **FR-009**: An unconfirmed capture MUST leave no trace: abandoning it MUST NOT create, modify, or reserve anything.
- **FR-010**: The confirmation step MUST show everything that will be written — vendor, item number, listing title, description, manufacturer, part number, order date, quantity, price — and allow each to be corrected before confirming.
- **FR-011**: Confirming a capture MUST land the operator somewhere that identifies what was created, as it does today.

### Not duplicating a capture

- **FR-012**: Confirming a capture MUST warn when a purchase already exists for the same vendor, the same vendor item number, and the same order date.
- **FR-013**: When the capture has no vendor item number, the duplicate check MUST fall back to the listing address, so that a second capture of the same address on the same day is still recognized.
- **FR-014**: A duplicate warning MUST identify the existing purchase and offer both to open it and to record this capture as a separate purchase.
- **FR-015**: The system MUST NOT refuse or silently discard a capture that matches an existing purchase; whether it is a duplicate is the operator's decision.
- **FR-016**: Captures differing in vendor, in item number, or in order date MUST NOT be reported as duplicates.

### Not mis-attaching to a recycled identifier

- **FR-017**: When a capture's vendor item number already identifies a product for that vendor, the confirmation step MUST name that product and show enough of it — at least description and manufacturer part number — for the operator to judge whether it is the same thing.
- **FR-018**: The operator MUST be able to attach the purchase to the named product or to create a separate product for it, and the capture MUST NOT be written until they choose.
- **FR-019**: A capture MUST attach to the matched product without asking when the capture supplies both a manufacturer and a manufacturer part number and both match the matched product's.
- **FR-020**: Choosing to create a separate product MUST leave the previously matched product entirely unchanged, including its identifiers and its purchase history.
- **FR-021**: A capture whose item number matches no product, or which has no item number, MUST create a product without asking.

### Correcting the description at receipt

- **FR-022**: The receive screen MUST present the product's description as an editable field pre-filled with its current value.
- **FR-023**: Marking a purchase received MUST apply any change to the description in the same action.
- **FR-024**: Marking a purchase received with a blank description MUST be refused with a message naming the reason, and MUST change neither the description nor the received state.
- **FR-025**: The description MUST be editable on the receive screen for every purchase, whether it was captured or recorded by hand, and whether or not it has already been received.
- **FR-026**: Submitting the receive screen without changing the description MUST leave the product's description untouched.

### Key Entities

- **Product**: the operator's record of a distinct kind of thing, carrying the authoritative human-readable description, optionally a manufacturer and manufacturer part number, and the coded names it is known by. Its description is what the label prints and what search finds. Unchanged in shape by this feature; changed in who writes its description and when.
- **Purchase**: one acquisition of one product from one vendor, carrying the vendor's own item number and the listing title as the vendor wrote it, an order date and a received date. Two purchases of the same product on the same day from the same vendor are two purchases.
- **Product identifier**: a coded name for a product, of a stated kind, scoped to a vendor where the kind requires it. A vendor's item number names at most one product for that vendor at a time — which is precisely why a recycled one must be a question and not an assumption.
- **Captured order draft**: what a capture holds between reading the listing and the operator confirming it. It is not a record of anything: it has no identity, it is not stored, and abandoning it costs nothing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A product's label description can be authored without leaving the capture flow, in the same visit in which the order is captured.
- **SC-002**: A description entered at capture appears on the product with no further action, and the vendor's listing title is still retrievable from the purchase.
- **SC-003**: A description can be corrected and the purchase marked received in a single submission, with no navigation away from the receive screen.
- **SC-004**: Clicking the bookmarklet twice on one listing and confirming once produces exactly one purchase; confirming twice produces two, each an explicit decision.
- **SC-005**: Two separate orders of the same item on the same day from the same vendor can both be recorded, and both appear in the product's purchase history.
- **SC-006**: No purchase is ever attached to a product whose vendor item number was recycled without the operator having been shown that product and having chosen.
- **SC-007**: Abandoning a capture leaves the catalogue byte-for-byte as it was; no product, purchase, or identifier is created by starting one.
- **SC-008**: Every capture path in use today — the paste-a-URL form and the bookmarklet — still reaches a recorded purchase, and neither loses a field it records today.

## Assumptions

- **Capture becomes confirm-then-write, and this is a deliberate behaviour change.** Today the bookmarklet records the purchase on click and lands the operator on the receive screen after the fact. A description authored "while the listing is still in front of you" is not achievable while capture commits before the operator has typed anything, so the commit moves after the confirmation. The cost is one extra click on the fast path; the issue's premise requires it.
- **The description at capture is optional, not required.** Falling back to the listing title keeps the one-click case one click, and matches what capture does today.
- **Manufacturer and manufacturer part number are entered by the operator, not read off the page.** The listing shows them, and the operator can see them; reading them out of the page's markup is the same fragility the current capture deliberately avoided, and the corroboration rule in FR-019 works equally well with typed values.
- **Corroboration requires both the manufacturer and the part number.** One matching alone is not enough to skip the question: a manufacturer name matches across a vendor's whole catalogue, and a part number without a manufacturer is not unique.
- **Duplicate detection warns; it never decides.** Today's silent idempotency is replaced, not tightened. The system does not have enough information to tell a double click from a second order, and the operator does.
- **A product has one description.** Editing it at capture or at receipt changes it everywhere; there is no per-purchase description and this feature does not introduce one.
- **Price is out of scope.** Reading the price off the listing is issue #56. This feature does not change how price is entered, only that the price field is visible and correctable on the confirmation step along with everything else.
- **The paste-a-URL capture form remains the path that cannot break.** The bookmarklet only reaches this application under conditions the vendor's site controls and this feature does not change. The confirmation step must behave identically whichever path reached it, and the paste path is the one that can be tested.
- **No change to what receiving does to a tracked quantity.** The gap document flags that receiving updates the count and marks it freshly counted, contrary to the archived plan. That is a separate disagreement and is not touched here.
