# Feature Specification: Whole-Order Capture for Every Vendor

**Feature Branch**: `issues/122`

**Created**: 2026-08-25

**Status**: Draft

**Input**: GitHub issue #122 — "SPIKE - Complete Order Capture": *"We now have the ability to capture products from Amazon, DigiKey, and possibly also McMaster-Carr. However, I usually order more than one product at a time. It would be great if we had the ability to capture an entire order, including all products in it. Please research what would be required to make this work in this application. Update this issue with your findings, both in general for this application and for these three vendors specifically. If any of these flows are already implemented, please say so clearly."*

## Overview

The spike asked which of the three vendors can capture a whole order. The answer is two of them, and the third is the one the operator uses most.

**DigiKey has had whole-order capture since feature 024.** A sales order number is typed once, DigiKey's own published data supplies every line, and the box is received a bag at a time by scanning the 2D label each bag already carries. **McMaster-Carr has had it since feature 028**, by the other available route: the bookmarklet reads the order off the order-history page in the operator's signed-in browser, because McMaster's interface requires an application review a one-person workshop will not pass. **Amazon has not.** Amazon capture is still what it was on day one — one listing, one bookmarklet click, one purchase — and an Amazon order of fourteen items is fourteen separate captures, each one a visit back to a listing page the operator has already left.

So the gap the issue is complaining about is Amazon's, and closing it is this feature's first job.

Its second job is a consequence of how the first two were built. Order capture was specified twice and implemented twice, and the two implementations are near-copies: two order-reading paths, two review models, two confirmation orchestrations of about a hundred and fifty lines each, two review templates, two order screens, two result types, and a receiving path that decides where a scan lands by asking which vendor it was. Everything genuinely vendor-specific in that pile is small — how an order is read, what identifies a line, and what a scan of a package can be expected to name. Everything else is the same feature written out twice. Adding Amazon as a third copy would be the wrong shape of work: it would triple the surface on which a fix has to be applied three times, and the project has already paid that tax once — two defects found in review of the McMaster PR were the McMaster copy of behaviour the DigiKey copy had already had corrected.

This is not abstraction for its own sake, which the constitution forbids. It is the case the constitution's rule is written to permit: three implementations exist, their differences are known rather than guessed at, and the shared part has been through two rounds of review already. The test of whether it worked is not that the code is prettier — it is that a fourth vendor is a reader and a handful of statements about that vendor, not a fourth copy of a feature.

The third job is the one that only becomes visible once three vendors are in play. A captured order today is reachable only by knowing its number and typing it, or by being redirected onto it by a scan. That is survivable when orders arrive labelled; it is not survivable across three vendors and several weeks, when what the operator wants to know is *what is still on its way from anyone*. Nothing in the catalog answers that question.

What none of this changes is what the two existing capture paths already decided, because those decisions were right and none of them is vendor-specific: nothing is written until the operator confirms it; the label description is authored while the vendor's data is on screen; anything the system is unsure about is put in front of the operator as a choice rather than resolved behind their back; and a value the operator typed always beats a value a selector found.

### What Amazon makes hard

Amazon is not DigiKey and it is not quite McMaster either, and two differences drive most of the requirements below.

**Amazon publishes nothing, and the order page is thin.** There is no consumer order interface to read an order back from, so the order has to come off the page — the McMaster route. But where a McMaster order line carries the part number that *is* the product's name, an Amazon order line carries a title, a quantity, a price and a link. The rich detail the existing Amazon capture writes — the gallery, the specification rows, the bullet points, the barcodes — lives on the listing page, one page per line, and it is not on the order page at all. A whole-order capture therefore produces thinner products than fourteen single captures would, and the spec has to say so plainly rather than quietly hand over a catalog full of title-only records.

**An Amazon package does not name the line it came from.** DigiKey's bag label names its sales order and its part; McMaster's names its part. Amazon's box names neither — the packing slip identifies the order at best, and the item inside carries whatever barcode the manufacturer put on it, which the catalog only knows if it captured the listing page that stated it. Receiving an Amazon order is therefore a screen-driven act rather than a scan-driven one, and the order screen stops being a progress display and becomes the place the work is actually done.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture a whole Amazon order from its page (Priority: P1)

The operator has just placed an Amazon order with eleven items in it. Instead of opening eleven listings and capturing each, they open the order in their Amazon account and click the same bookmarklet they already use. The catalog shows every item the page yielded — its title, how many were ordered, what each cost — and, for each, whether the catalog already holds a product for it. The operator writes the label description for the ones that are new, ticks off the two lines they do not want cataloged, and confirms. Eleven outstanding purchases exist against the right products, filed under the order number, and nothing was typed that Amazon already stated.

**Why this priority**: It is the gap the issue is about, and it is the entry point for everything else here — there is nothing to receive and nothing to list until an order can be captured. On its own it already delivers the value: the purchases are recorded, the reorder list stops suggesting things that are on the way, and the products exist before the box does.

**Independent Test**: Capture a known Amazon order from its order page, confirm the review, and verify that every included line became one outstanding purchase against a product carrying that line's ASIN, with the quantity and unit price the page stated and the order's number and date.

**Acceptance Scenarios**:

1. **Given** an Amazon order page open in the operator's signed-in browser, **When** they click the capture bookmarklet, **Then** the catalog shows a review listing every line it read — title, quantity, unit price, and the item's ASIN — together with the order number and order date, and nothing has been recorded yet.
2. **Given** that review, **When** the operator confirms it, **Then** one outstanding purchase is recorded per included line, each carrying the vendor `Amazon`, the order number, the order date, the line's quantity and the line's unit price.
3. **Given** a line whose ASIN already names a product in the catalog, **When** the review is shown, **Then** that line names the matched product and offers to attach the purchase to it rather than offering to author a new description.
4. **Given** a line the catalog has never seen, **When** the review is shown, **Then** it offers an editable description pre-filled from Amazon's title, and confirming creates a product carrying it.
5. **Given** a line the operator does not want cataloged — a consumable, a gift, a digital item — **When** they exclude it and confirm, **Then** no product and no purchase results from that line and every other line is captured normally.
6. **Given** the review, **When** the operator closes the tab without confirming, **Then** no product, no purchase and no stored file exists as a result.
7. **Given** an order page whose markup has changed so that one field no longer reads, **When** the order is captured, **Then** every other field on every line still captures and the review names what was lost before the operator confirms.
8. **Given** the review, **When** it is shown, **Then** it states how many lines it read, so that a page that yielded four of eleven is visibly that rather than a short order.

---

### User Story 2 - Receive an Amazon order as the boxes turn up (Priority: P2)

Over the following week the order arrives in four boxes. The operator opens the captured order, sees the eleven lines with the seven still outstanding marked as such, and receives each item as they unpack it — correcting a quantity where Amazon sent fewer, marking one line as never having arrived. When the last box is empty the order screen says whether anything is still outstanding, and the operator can see at a glance that one line is.

**Why this priority**: It is the payoff Story 1 is performed for, and for Amazon it carries more weight than it does for the other two vendors, because there is no label to scan and the screen is the only way to do it. It ranks second only because it is worthless without a captured order to receive against.

**Independent Test**: Capture an Amazon order, then receive three of its lines from the order screen, and verify each purchase is recorded received with the quantity entered, the counted products' quantities rose accordingly, and the screen reports the remaining lines as outstanding.

**Acceptance Scenarios**:

1. **Given** a captured Amazon order, **When** the operator opens it, **Then** they see every line with its product, quantity, unit price and whether it is outstanding or received, and how many lines are still outstanding.
2. **Given** an outstanding line, **When** the operator receives it from the order screen, **Then** the purchase is recorded received, a counted product's quantity rises by the received quantity, and any manual low or out flag on that product is cleared — exactly as receiving does today.
3. **Given** an outstanding line, **When** the operator receives it with a quantity different from the one ordered, **Then** the received quantity is what is recorded and what the product's count rises by.
4. **Given** a line that is already received, **When** the order screen is shown, **Then** it is shown as received and cannot be received a second time.
5. **Given** a product that carries a barcode the catalog knows, **When** that barcode is scanned while exactly one line naming it is outstanding, **Then** the operator lands on the receipt for that line, as scanning already does for the other two vendors.
6. **Given** an order number that names no captured order, **When** it is opened, **Then** the catalog says it is not captured and offers a way forward, rather than an error or a 404.

---

### User Story 3 - One order flow, and one place that lists what is on its way (Priority: P3)

The operator has an open order with each of the three vendors. Rather than remembering three order numbers and typing them into three different screens, they open one list of captured orders, see all three with their dates and how many lines of each are still outstanding, and click into whichever box just arrived. Behind that list, all three vendors' orders are reviewed, confirmed, displayed and received by one flow rather than three, so a fix applied to any of it is applied to all of it.

**Why this priority**: It is the part with no new user-facing capability behind it and it can be demonstrated last — but it is what makes the first two sustainable, and it is the difference between adding a fourth vendor later and rewriting this feature a fourth time. See the assumption below about why it is nonetheless expected to be built first.

**Independent Test**: Capture one order from each vendor, open the captured-orders list, and verify all three appear with their vendor, number, date and outstanding count, each linking to an order screen that behaves identically for all three; and verify the pre-existing DigiKey and McMaster test suites pass unchanged.

**Acceptance Scenarios**:

1. **Given** captured orders from more than one vendor, **When** the operator opens the captured-orders list, **Then** each order appears with its vendor, its number, its date and how many of its lines are still outstanding, most recent first.
2. **Given** that list, **When** an order has nothing outstanding, **Then** it is distinguishable at a glance from one that has.
3. **Given** an order from any vendor, **When** its order screen is opened, **Then** it presents the same information and the same actions as an order from any other vendor, differing only where the vendor genuinely differs.
4. **Given** the existing DigiKey and McMaster capture, review, order-screen, scanning and receiving behaviour, **When** this feature is complete, **Then** all of it behaves exactly as it did before, demonstrated by the existing tests passing unchanged.
5. **Given** a scan that names outstanding lines on more than one captured order, **When** it is resolved, **Then** the operator is shown the candidates and chooses, for every vendor rather than for one.

---

### Edge Cases

- **The same item appears twice on one order page.** Amazon states no line number, so two lines naming the same ASIN cannot be told apart by anything the page provides. A re-capture must not pair a line to the wrong purchase, and must not silently merge the two into one — this is the failure that corrupted data in feature 024 when pairing was positional (FR-018).
- **An order page yields no lines at all.** Rendered late, signed out, or a page that is not an order. This must be a plain statement and a way forward, never an empty review indistinguishable from an order with nothing in it.
- **One order, several shipments, arriving days apart.** Handled per line from the order screen; the order is not received as a unit.
- **A line is cancelled or refunded after capture.** A re-capture reports the purchase the page no longer carries and never deletes it — the operator cancels it deliberately.
- **A quantity or price changed between capture and re-capture.** Shown against what is recorded, applied only on confirmation.
- **A line is a digital item, a subscription, a gift card, or a shipping charge.** Excludable like any other line; nothing about it may refuse the capture.
- **An Amazon order captured from its page and then captured again from a listing page.** The second capture is the existing single-listing path against a product that now exists; the existing duplicate handling applies and the operator chooses.
- **The bookmarklet is clicked on the Amazon orders *list* rather than on one order.** Many orders, not one — this must not be read as an order.
- **A line's price is stated for a multipack.** Amazon prices a listing, not a unit; what is recorded is what the page stated, per the assumption below.

## Requirements *(mandatory)*

### Capturing an Amazon order

- **FR-001**: The operator MUST be able to capture a whole Amazon order by clicking the existing capture bookmarklet while an Amazon order's own page is open, with no order number typed and no per-line action.
- **FR-002**: The capture MUST read the order from the page in the operator's own signed-in browser session. It MUST NOT require Amazon credentials, an application registration, or any configuration held by the application, and MUST NOT depend on the application being able to fetch an Amazon page itself.
- **FR-003**: The capture MUST present every line the page yielded for review — the item's title, its ASIN, the quantity and the unit price — together with the order's number and its date, before anything is recorded.
- **FR-004**: The review MUST state how many lines it read.
- **FR-005**: Nothing MUST be recorded until the operator confirms the review. An abandoned review MUST leave no product, no purchase and no stored file.
- **FR-006**: Because Amazon cannot be re-read at confirmation time, what the review displays MUST be what confirming it writes, carried through the confirmation without a second read of any page.
- **FR-007**: The review MUST state, for each line, whether the catalog already holds a product for it, and MUST name that product.
- **FR-008**: The review MUST let the operator author the label description for each line that would create a new product, pre-filled with Amazon's title.
- **FR-009**: The review MUST let the operator exclude any line, and an excluded line MUST produce neither a product nor a purchase while every other line is captured normally.
- **FR-010**: Confirming a review MUST record one purchase per included line, against the matched or newly created product, carrying the vendor `Amazon`, the line's quantity, the line's unit price, the order's date and the order's number.
- **FR-011**: A purchase recorded by this capture MUST be outstanding — not received — regardless of what the order page says about delivery.
- **FR-012**: A product created by this capture MUST carry the line's ASIN as a vendor-scoped identifier, in the same way a single Amazon capture records an ASIN today.
- **FR-013**: The catalog MUST record the Amazon order number against each captured purchase in the same first-class field the other vendors' order numbers already occupy, such that all of an order's purchases can be found from it.
- **FR-014**: A capture MUST NOT record a second purchase for a line it has already captured from the same order number.
- **FR-015**: Re-capturing an order MUST show which of its lines are already captured, offer any line that is not, and report any previously captured purchase the page no longer carries without deleting it.
- **FR-016**: Where a re-capture finds a changed quantity or unit price on an already-captured line, it MUST show the change against what is recorded and apply it only if the operator confirms it.
- **FR-017**: Where a line's ASIN already names a product whose identity contradicts the line's, the capture MUST name that product and require a choice — attach to it, or create a separate product — before writing anything.
- **FR-018**: The catalog MUST record which line of the order each captured purchase came from, and MUST NOT rely on the item's identity alone to re-establish that pairing later. Where the order page states no line number of its own, the recorded line identity MUST still distinguish two lines naming the same item, and a re-capture MUST NOT pair a line to another line's purchase.
- **FR-019**: A line whose ASIN cannot be read MUST be capturable on its title alone, or excludable, and MUST NOT cause the capture to be refused.
- **FR-020**: A capture that fails for any reason MUST leave nothing partially recorded, and MUST be safe to retry.
- **FR-021**: A field that cannot be read MUST cost that field alone. No unreadable field may cost another field, another line, or the capture.
- **FR-022**: The review MUST name which fields or lines came back incomplete, and confirming MUST carry that statement forward, so the operator knows which records to look over after leaving the page.
- **FR-023**: A page from which no order line can be read MUST produce a plain statement to that effect and a way forward, and MUST NOT produce an empty review indistinguishable from an order with no lines.
- **FR-024**: A page listing many orders MUST NOT be read as an order.

### What an order-page capture knows, and what it does not

- **FR-025**: A product created from an order line MUST be recorded from what the order page stated, and the capture MUST NOT be delayed by fetching each line's listing page.
- **FR-026**: The catalog MUST make plain — on the review, and on the products the capture creates — that a product created from an order line carries only what the order page stated, so the operator is not left believing a title-only record is all the listing had.
- **FR-027**: The operator MUST be able to fill in such a product later by running the existing single-listing capture against the same item, and doing so MUST attach to the existing product rather than create a second one.

### Seeing and receiving an order

- **FR-028**: The operator MUST be able to open a captured order from any vendor and see all of its lines, each showing its product, quantity, unit price and whether it is outstanding or received.
- **FR-029**: A captured order MUST show how many of its lines are still outstanding.
- **FR-030**: The operator MUST be able to mark any outstanding line received from the order screen, amending its quantity there, with the same effect receiving a purchase has today — the purchase is received, a counted product's quantity rises by the received quantity, and a manual low or out flag is cleared.
- **FR-031**: A line that is already received MUST be shown as received and MUST NOT be receivable a second time.
- **FR-032**: An order number that names no captured order MUST render as "not captured", with a way forward, rather than as an error or a 404.
- **FR-033**: The operator MUST be able to see, in one place, every captured order that still has outstanding lines, showing for each its vendor, its number, its date and how many lines remain outstanding, and MUST be able to open any of them from there.
- **FR-034**: That list MUST be reachable from the application's navigation, and MUST NOT require the operator to know an order number.

### One order flow for every vendor

- **FR-035**: Reviewing an order, confirming it, displaying it and receiving from it MUST be one flow used by every vendor, rather than one flow per vendor.
- **FR-036**: What remains vendor-specific MUST be limited to how an order is read, what identifies one of its lines, what identifiers a captured line writes, and what a scan of a delivered package can be expected to name.
- **FR-037**: Adding a further vendor MUST NOT require a further copy of the review, the confirmation, the order screen or the receiving path.
- **FR-038**: Where a scan names outstanding lines on more than one captured order, the catalog MUST show the candidates and let the operator choose, for every vendor rather than for one, and MUST NOT pick one.
- **FR-039**: Where a scan names exactly one outstanding line, it MUST take the operator to the receipt for that line, for every vendor.
- **FR-040**: Where a scan names no outstanding line, it MUST behave exactly as it does today — the product opens if the catalog holds it, and the create-a-product path is offered if it does not.

### Not breaking what exists

- **FR-041**: Every existing capture path MUST behave exactly as it does today: the Amazon single-listing bookmarklet capture, the paste-a-URL capture, the DigiKey order and part captures, the McMaster order and product captures, scanning, manual purchase entry and receiving.
- **FR-042**: The operator MUST continue to use one bookmarklet for all vendors, and MUST NOT have to re-drag it to get Amazon order support.
- **FR-043**: Where the bookmarklet is clicked on a page it does not recognize, the capture MUST behave exactly as it does today for that page.
- **FR-044**: Every order already captured before this feature MUST remain openable, receivable and correct afterwards.

### Key Entities

- **Order**: One order placed with one vendor, identified by that vendor's own order number and carrying an order date. Derived from the purchases captured against it rather than stored as a record of its own, exactly as the DigiKey and McMaster orders already are.
- **Order Line**: One line of that order — an item, a quantity and a price. Captured, it becomes one Purchase against one Product; excluded, it becomes nothing. Its position within the order is part of its identity, because two lines can name the same item and no vendor guarantees to number them.
- **Purchase**: The existing record of one acquisition of one product. Already carries a supplier order number and a line number; this feature adds Amazon as a third vendor writing them and changes neither.
- **Product**: The existing record of a distinct kind of thing the workshop holds. Its identity is its own record and never a vendor's item number.
- **Product Identifier**: The existing coded names a product carries. This feature writes an ASIN, vendor-scoped to Amazon, exactly as a single Amazon capture does today.
- **Captured Listing**: The existing carrier for what was read off a vendor's page. An Amazon order line fills in far less of it than an Amazon listing page does, which is what FR-026 requires be made visible.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An eleven-line Amazon order is captured — read, reviewed, described and confirmed — in under five minutes, against the roughly half an hour eleven single captures take today, with nothing typed that the order page already stated.
- **SC-002**: Every line of a captured order becomes exactly one outstanding purchase or one deliberately excluded line. No line is silently dropped and no line produces two purchases.
- **SC-003**: Capturing the same unchanged order a second time records nothing new.
- **SC-004**: Every line whose item the catalog already holds attaches to that existing product; none creates a duplicate.
- **SC-005**: An order containing the same item on two separate lines captures as two purchases, and re-capturing it pairs each line to its own purchase — verified by applying a quantity change to one line and observing the other is untouched.
- **SC-006**: With the order page's markup changed so that a given field no longer reads, every other field on every line still captures, and the operator is told which field was lost before they confirm.
- **SC-007**: No failed or abandoned capture leaves a partial record behind — measured as: after any failure or abandonment, the number of products and purchases is unchanged.
- **SC-008**: At any point during unpacking, the operator can see from one screen how many of an order's lines are still outstanding and which they are.
- **SC-009**: With open orders from all three vendors, the operator can see every one of them, and what remains outstanding on each, from a single screen without typing an order number.
- **SC-010**: Receiving a line from the order screen takes one action and no searching, and leaves the product's count and stock flags exactly as receiving that purchase by any other route would.
- **SC-011**: Every capture, scan, order-screen and receiving workflow that worked before this feature works identically after it, demonstrated by the existing test suite passing unchanged.
- **SC-012**: Reviewing, confirming, displaying and receiving an order is implemented once rather than once per vendor — measured as: no vendor has its own copy of any of those four, and the vendor-specific remainder is limited to what FR-036 names.

## Assumptions

- **DigiKey and McMaster order capture are already built, and this feature does not re-do them.** Feature 024 shipped DigiKey's and feature 028 shipped McMaster's; both are merged. What this feature does to them is consolidate them with Amazon's onto one flow without changing what they do, which is why SC-011 is stated as the existing tests passing unchanged rather than as new behaviour.
- **Amazon has no consumer order interface to read an order back from.** Amazon's published interfaces are for sellers, not for a customer reading their own retail orders, so the order must come off the page the operator is looking at. This is the same conclusion the McMaster feature reached for a different reason, and it is why FR-002 forbids credentials and server-side fetching. The exact shape of the order page — its address, and where on it the lines, quantities, prices and order number sit — is a live-site investigation for the planning phase, exactly as the McMaster page shape was (feature 028 closed it as a plan TBD, and it changed the design when it landed).
- **The order page is read in the operator's signed-in browser, by the bookmarklet the catalog already hands out.** No second bookmarklet, no extension, no stored Amazon session. This is settled by the existing design rather than chosen here.
- **Reading a vendor's markup is accepted as fragile, and the loss is bounded and stated.** Each field's extraction is independent and optional, so a selector that stops matching costs that one field; and because a field missing from one line of eleven is not something the operator will notice, FR-022 requires the loss be named. This is the trade the Amazon single capture already made and the McMaster order capture already extended to lines.
- **An order-page capture does not fetch each line's listing page, and the products it creates are thinner for it.** The existing single capture takes eight to fifteen seconds for one listing's gallery, so eleven of them would be a capture measured in minutes; and the application cannot fetch Amazon pages itself in any case, which is the reason the bookmarklet exists. So an order capture records what the order page stated, says so (FR-026), and leaves the existing single capture available to fill any line in later (FR-027). **If whole-order capture should instead pull each line's full listing detail, this assumption is the one to overturn, and it changes the scope materially.**
- **What is recorded for a line is the price and quantity the order page states, and both are already per-unit.** Amazon's order page states a unit price and a quantity per line directly (research.md §5, §6), so unlike McMaster there is no pack arithmetic to do — nothing is computed, the page's figures are recorded, and both remain editable on the review. *(This assumption originally said the opposite — that Amazon priced a listing rather than a unit and there was nothing to compute from. The live-site investigation disproved it; it makes the Amazon capture simpler than the McMaster one, not harder.)*
- **Amazon receiving is screen-driven, not scan-driven.** An Amazon package carries nothing that names the order line it belongs to, and an item's own barcode is only known to the catalog if a listing capture recorded it — which, per the assumption above, an order capture does not. So the order screen is the primary receiving path for Amazon (US2), and scanning remains available for the products that do carry a known barcode (FR-039), rather than being the mechanism it is for the other two vendors.
- **Story 3 is prioritized by value but expected to be implemented first.** The stories are ordered by what they deliver to the operator, and consolidation delivers nothing directly. But building Amazon as a third copy and then merging three copies is more work than merging two and extending the result, and it briefly triples the surface that a defect has to be fixed on. The planning phase is expected to unify first and land Amazon on the unified flow; the priorities say what matters, not what order to type it in.
- **Consolidation is warranted here despite Simplicity First.** The constitution forbids abstraction for a single implementation. This is three, their differences are known from two shipped features rather than anticipated, and the duplication has already cost a round of defects that had to be fixed twice. The test of the consolidation is FR-037 — a fourth vendor is a reader, not a fourth copy — and not whether the code reads better.
- **Receiving stays all-or-nothing per line.** The existing model represents outstanding as "no received date", with no partial state, and adding one would touch every screen that reads a purchase. Split shipments are handled per line, visibly, per the edge case above.
- **Capture happens when the order is placed, not when it arrives.** That is the point of capture and what makes the reorder list's "on the way" marking correct. Capturing an order that has already arrived is allowed and works; its lines are simply received immediately afterwards.
